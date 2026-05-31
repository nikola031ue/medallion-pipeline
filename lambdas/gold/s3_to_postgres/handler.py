import io
import os
import re

import boto3
import pandas as pd
from sqlalchemy import create_engine

BUCKET = os.environ["BUCKET_NAME"]
GOLD_PREFIX = os.environ["GOLD_PREFIX"]
PG_HOST = os.environ["PG_HOST"]
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DB = os.environ.get("PG_DB", "superset")
PG_USER = os.environ.get("PG_USER", "superset")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "superset")

s3 = boto3.client("s3")

TABLES = [
    "fact_posts_by_type",
    "daily_users_metric",
    "top_x_users_by_followers",
    "top_hn_users_max_karma",
    "top_hn_users_min_karma",
    "top_hn_stories_by_score",
    "top_hn_jobs_by_score",
    "data_quality_kpi",
]


def _list_parquet_keys(prefix: str) -> list[str]:
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                keys.append(obj["Key"])
    return keys


def _read_parquet(key: str) -> pd.DataFrame:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))
    except Exception as exc:
        print(f"Skip {key}: {exc}")
        return pd.DataFrame()


def _extract_partition(key: str, partition_name: str) -> str | None:
    match = re.search(rf"{partition_name}=([^/]+)", key)
    return match.group(1) if match else None


def _load_table(table_name: str) -> pd.DataFrame:
    keys = _list_parquet_keys(f"{GOLD_PREFIX}/{table_name}/")
    if not keys:
        return pd.DataFrame()

    frames = []
    for key in keys:
        df = _read_parquet(key)
        if df.empty:
            continue
        # daily_users_metric stores platform only in the S3 path, not in the file
        if table_name == "daily_users_metric" and "platform" not in df.columns:
            platform = _extract_partition(key, "platform")
            if platform:
                df["platform"] = platform
        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def lambda_handler(event, context):
    engine = create_engine(
        f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    )

    synced = []
    failed = []

    for table in TABLES:
        try:
            df = _load_table(table)
            if df.empty:
                print(f"No data for {table}, skipping")
                continue
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.date
            with engine.begin() as conn:
                df.to_sql(table, conn, if_exists="replace", index=False)
            print(f"Synced {len(df)} rows → {table}")
            synced.append(table)
        except Exception as exc:
            print(f"ERROR {table}: {exc}")
            failed.append(table)

    engine.dispose()

    if failed:
        raise RuntimeError(f"Failed tables: {failed}")

    return {"status": "ok", "synced": synced}
