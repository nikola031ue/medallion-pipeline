import hashlib
import io
import os
import uuid

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BUCKET = os.environ["BUCKET_NAME"]
BRONZE_KEY = os.environ["BRONZE_KEY"]
SILVER_POSTS_PREFIX = os.environ["SILVER_POSTS_PREFIX"]
SILVER_USERS_PREFIX = os.environ["SILVER_USERS_PREFIX"]

s3 = boto3.client("s3")


def _post_id(row) -> str:
    raw = f"{row['user_name']}|{row['date']}|{row['text']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _to_iso(val: str) -> str | None:
    if not val or val == "nan":
        return None
    try:
        return pd.Timestamp(val).isoformat()
    except Exception:
        return None


def _write_parquet(df: pd.DataFrame, key: str) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.read(), ContentType="application/octet-stream")


def lambda_handler(event, context):
    obj = s3.get_object(Bucket=BUCKET, Key=BRONZE_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()), dtype=str).fillna("")

    posts_df = pd.DataFrame({
        "post_id": df.apply(_post_id, axis=1),
        "author_username": df["user_name"],
        "content_text": df["text"],
        "created_at": df["date"].apply(_to_iso),
        "post_type": df["is_retweet"].str.lower().map({"true": "retweet", "false": "tweet"}).fillna("tweet"),
    }).drop_duplicates(subset=["post_id"])

    users_raw = (
        df[["user_name", "user_verified", "user_created"]]
        .drop_duplicates(subset=["user_name"])
        .reset_index(drop=True)
    )
    users_df = pd.DataFrame({
        "user_id": [str(uuid.uuid4()) for _ in range(len(users_raw))],
        "username": users_raw["user_name"],
        "platform": "X",
        "karma_score": None,
        "is_verified": users_raw["user_verified"].str.lower().map({"true": True, "false": False}),
        "created_at": users_raw["user_created"].apply(_to_iso),
    })

    _write_parquet(posts_df, f"{SILVER_POSTS_PREFIX}/platform=X/data.parquet")
    print(f"Written {len(posts_df)} posts → silver/posts/platform=X/")

    _write_parquet(users_df, f"{SILVER_USERS_PREFIX}/platform=X/data.parquet")
    print(f"Written {len(users_df)} users → silver/users/platform=X/")
