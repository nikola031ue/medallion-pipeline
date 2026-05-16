import json
import os
import time
from datetime import date, datetime, timedelta, timezone

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BUCKET = os.environ["BUCKET_NAME"]
BASE = os.environ["HN_API_BASE"]
TYPES = os.environ["HN_ITEM_TYPES"].split(",")
PREFIX = os.environ["BRONZE_PREFIX"]

HOUR = 3600
QUARTER = 900

s3 = boto3.client("s3")


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


SESSION = _make_session()


def lambda_handler(event, context):
    yesterday = date.today() - timedelta(days=1)
    day_start = int(
        datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=timezone.utc).timestamp()
    )
    day_end = day_start + 86400

    year = yesterday.strftime("%Y")
    month = yesterday.strftime("%m")
    day = yesterday.strftime("%d")

    failed = []
    for item_type in TYPES:
        try:
            hits = fetch_all_hits(item_type, day_start, day_end)

            seen = set()
            unique = [h for h in hits if not (h["objectID"] in seen or seen.add(h["objectID"]))]

            key = f"{PREFIX}/year={year}/month={month}/day={day}/{item_type}.json"
            s3.put_object(
                Bucket=BUCKET,
                Key=key,
                Body=json.dumps(unique, ensure_ascii=False),
                ContentType="application/json",
            )
            print(f"Wrote {len(unique)} items ({item_type}) → s3://{BUCKET}/{key}")
        except Exception as exc:
            print(f"ERROR ({item_type}): {exc}")
            failed.append(item_type)

    if failed:
        raise RuntimeError(f"Failed to fetch types: {failed}")


def fetch_all_hits(tag: str, start_ts: int, end_ts: int, window: int = HOUR) -> list:
    """Collect all hits in [start_ts, end_ts) using time-windowed pagination.

    Algolia caps results at 1 000 per query. If a window fills up,
    it is sub-divided to quarter-hour granularity to avoid silent truncation.
    """
    all_hits = []
    cursor = start_ts
    while cursor < end_ts:
        w_end = min(cursor + window, end_ts)
        window_hits = _paginate_window(tag, cursor, w_end)
        if len(window_hits) >= 1000 and window > QUARTER:
            all_hits.extend(fetch_all_hits(tag, cursor, w_end, window=QUARTER))
        else:
            all_hits.extend(window_hits)
        cursor = w_end
    return all_hits


def _paginate_window(tag: str, start_ts: int, end_ts: int) -> list:
    hits = []
    page = 0
    while True:
        resp = SESSION.get(
            f"{BASE}/search_by_date",
            params={
                "tags": tag,
                "numericFilters": f"created_at_i>{start_ts},created_at_i<{end_ts}",
                "hitsPerPage": 1000,
                "page": page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        hits.extend(data["hits"])
        page += 1
        if page >= data.get("nbPages", 1) or page >= 50:
            break
        time.sleep(0.1)
    return hits
