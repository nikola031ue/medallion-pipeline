import io
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BUCKET = os.environ["BUCKET_NAME"]
BRONZE_PREFIX = os.environ["BRONZE_PREFIX"]
SILVER_POSTS_PREFIX = os.environ["SILVER_POSTS_PREFIX"]
SILVER_USERS_PREFIX = os.environ["SILVER_USERS_PREFIX"]
ITEM_TYPES = os.environ["HN_ITEM_TYPES"].split(",")

KNOWN_TYPES = {"story", "comment", "ask_hn", "show_hn", "job", "poll"}

s3 = boto3.client("s3")


class _TagStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def strip_html(text: str) -> str:
    if not text:
        return ""
    stripper = _TagStripper()
    stripper.feed(text)
    return stripper.get_text()


def ts_to_iso(unix_ts) -> str | None:
    if unix_ts is None:
        return None
    return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc).isoformat()


def resolve_post_type(hit: dict) -> str:
    for tag in hit.get("_tags", []):
        if tag in KNOWN_TYPES:
            return tag
    return "story"


def resolve_content(hit: dict) -> str:
    for field in ("comment_text", "story_text", "title"):
        val = hit.get(field)
        if val:
            return strip_html(val)
    return ""


def _write_parquet(df: pd.DataFrame, key: str) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.read(), ContentType="application/octet-stream")


def lambda_handler(event, context):
    yesterday = date.today() - timedelta(days=1)
    year = yesterday.strftime("%Y")
    month = yesterday.strftime("%m")
    day = yesterday.strftime("%d")

    posts = []
    users: dict[str, dict] = {}

    for item_type in ITEM_TYPES:
        key = f"{BRONZE_PREFIX}/year={year}/month={month}/day={day}/{item_type}.json"
        try:
            obj = s3.get_object(Bucket=BUCKET, Key=key)
            hits = json.loads(obj["Body"].read())
        except Exception as exc:
            print(f"Skipping {item_type}: {exc}")
            continue

        for hit in hits:
            post_id = hit.get("objectID")
            author = hit.get("author")
            if not post_id or not author:
                continue

            posts.append({
                "post_id": str(post_id),
                "author_username": author,
                "content_text": resolve_content(hit),
                "created_at": ts_to_iso(hit.get("created_at_i")),
                "post_type": resolve_post_type(hit),
            })

            if author not in users:
                users[author] = {
                    "user_id": str(uuid.uuid4()),
                    "username": author,
                    "platform": "HackerNews",
                    "karma_score": None,
                    "is_verified": None,
                    "created_at": None,
                }

    if not posts:
        print("No posts found for yesterday, nothing to write")
        return

    posts_df = pd.DataFrame(posts).drop_duplicates(subset=["post_id"])
    users_df = pd.DataFrame(list(users.values()))

    posts_key = f"{SILVER_POSTS_PREFIX}/year={year}/month={month}/day={day}/data.parquet"
    _write_parquet(posts_df, posts_key)
    print(f"Written {len(posts_df)} posts → s3://{BUCKET}/{posts_key}")

    users_key = f"{SILVER_USERS_PREFIX}/platform=HackerNews/data.parquet"
    _write_parquet(users_df.drop(columns=["platform"]), users_key)
    print(f"Written {len(users_df)} users → s3://{BUCKET}/{users_key}")
