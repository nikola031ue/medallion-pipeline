import io
import os
from datetime import date, timedelta

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BUCKET = os.environ["BUCKET_NAME"]
SILVER_PREFIX = os.environ["SILVER_PREFIX"]
GOLD_PREFIX = os.environ["GOLD_PREFIX"]

USERS_KEY_COLUMNS = ["user_id", "username", "platform"]
POSTS_KEY_COLUMNS = ["post_id", "author_username", "content_text", "post_type", "created_at"]

s3 = boto3.client("s3")


def _read_parquet(key: str) -> pd.DataFrame:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))
    except Exception as exc:
        print(f"Skip {key}: {exc}")
        return pd.DataFrame()


def _write(df: pd.DataFrame, key: str) -> None:
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), buf)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.read(), ContentType="application/octet-stream")
    print(f"Written {len(df)} rows → {key}")


def calculate_data_quality_score(
    df: pd.DataFrame,
    key_columns: list[str],
    table_name: str,
    platform: str,
    date_str: str,
) -> dict:
    total_rows = len(df)
    if total_rows == 0:
        return {
            "table_name": table_name,
            "platform": platform,
            "total_rows": 0,
            "non_null_rows": 0,
            "data_quality_score": 0.0,
            "date": date_str,
        }
    available_columns = [col for col in key_columns if col in df.columns]
    non_null_mask = df[available_columns].apply(
        lambda col: col.notna() & (col.astype(str).str.strip() != "")
    ).all(axis=1)
    non_null_rows = int(non_null_mask.sum())
    score = round((non_null_rows / total_rows) * 100, 2)
    return {
        "table_name": table_name,
        "platform": platform,
        "total_rows": total_rows,
        "non_null_rows": non_null_rows,
        "data_quality_score": score,
        "date": date_str,
    }


def lambda_handler(event, context):
    yesterday = date.today() - timedelta(days=1)
    y, m, d = yesterday.strftime("%Y"), yesterday.strftime("%m"), yesterday.strftime("%d")
    date_str = yesterday.isoformat()

    results = []

    # Users tabela — HackerNews i X
    for platform in ("HackerNews", "X"):
        df = _read_parquet(f"{SILVER_PREFIX}/users/platform={platform}/data.parquet")
        if not df.empty:
            df["platform"] = platform
        results.append(
            calculate_data_quality_score(df, USERS_KEY_COLUMNS, "users", platform, date_str)
        )

    # Posts tabela — HackerNews (dnevna particija)
    hn_posts = _read_parquet(f"{SILVER_PREFIX}/posts/year={y}/month={m}/day={d}/data.parquet")
    results.append(
        calculate_data_quality_score(hn_posts, POSTS_KEY_COLUMNS, "posts", "HackerNews", date_str)
    )

    # Posts tabela — X
    x_posts = _read_parquet(f"{SILVER_PREFIX}/posts/platform=X/data.parquet")
    results.append(
        calculate_data_quality_score(x_posts, POSTS_KEY_COLUMNS, "posts", "X", date_str)
    )

    kpi_df = pd.DataFrame(results)
    _write(kpi_df, f"{GOLD_PREFIX}/data_quality_kpi/date={date_str}/data.parquet")
    print(f"Data quality KPI written for {date_str}")

    return {"status": "ok", "date": date_str, "tables_checked": len(results)}
