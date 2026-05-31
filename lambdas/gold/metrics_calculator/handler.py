import io
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BUCKET = os.environ["BUCKET_NAME"]
BRONZE_HN_PREFIX = os.environ["BRONZE_HN_PREFIX"]
BRONZE_TWITTER_KEY = os.environ["BRONZE_TWITTER_KEY"]
SILVER_PREFIX = os.environ["SILVER_PREFIX"]
GOLD_PREFIX = os.environ["GOLD_PREFIX"]
HN_USER_API = "https://hacker-news.firebaseio.com/v0/user/{}.json"
TOP_N = 10

s3 = boto3.client("s3")


def _read_parquet(key: str) -> pd.DataFrame:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))
    except Exception as exc:
        print(f"Skip {key}: {exc}")
        return pd.DataFrame()


def _read_json(key: str) -> list:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(obj["Body"].read())
    except Exception as exc:
        print(f"Skip {key}: {exc}")
        return []


def _write(df: pd.DataFrame, key: str) -> None:
    if df.empty:
        print(f"Empty, skipping {key}")
        return
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), buf)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.read(), ContentType="application/octet-stream")
    print(f"Written {len(df)} rows → {key}")


def _fetch_karma(username: str) -> tuple[str, int | None]:
    try:
        with urllib.request.urlopen(HN_USER_API.format(username), timeout=5) as resp:
            data = json.loads(resp.read())
            return username, data.get("karma")
    except Exception:
        return username, None


def fetch_karma_bulk(usernames: list[str], max_workers: int = 20) -> dict[str, int | None]:
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_karma, u): u for u in usernames}
        for future in as_completed(futures):
            username, karma = future.result()
            results[username] = karma
    return results


def lambda_handler(event, context):
    yesterday = date.today() - timedelta(days=1)
    y, m, d = yesterday.strftime("%Y"), yesterday.strftime("%m"), yesterday.strftime("%d")
    date_str = yesterday.isoformat()

    hn_posts = _read_parquet(f"{SILVER_PREFIX}/posts/year={y}/month={m}/day={d}/data.parquet")
    hn_users = _read_parquet(f"{SILVER_PREFIX}/users/platform=HackerNews/data.parquet")
    x_users = _read_parquet(f"{SILVER_PREFIX}/users/platform=X/data.parquet")

    failed = []

    # 1. Broj objava po tipu na HN (dnevno)
    try:
        if not hn_posts.empty:
            posts_by_type = (
                hn_posts.groupby("post_type").size()
                .reset_index(name="count")
                .assign(platform="HackerNews", date=date_str)
            )
            _write(posts_by_type, f"{GOLD_PREFIX}/fact_posts_by_type/date={date_str}/data.parquet")
    except Exception as exc:
        print(f"ERROR fact_posts_by_type: {exc}")
        failed.append("fact_posts_by_type")

    # 2 & 3. daily_users_metric — total_users i new_users po platformi (dnevno)
    try:
        # HackerNews — new_users = distinktni autori iz jucerasnjih postova
        hn_new_users = hn_posts["author_username"].nunique() if not hn_posts.empty else 0
        hn_row = pd.DataFrame([{
            "date": date_str,
            "total_users": len(hn_users),
            "new_users": hn_new_users,
        }])
        _write(hn_row, f"{GOLD_PREFIX}/daily_users_metric/platform=HackerNews/date={date_str}/data.parquet")

        # X — new_users = korisnici ciji user_created odgovara jucerasnjem datumu
        obj = s3.get_object(Bucket=BUCKET, Key=BRONZE_TWITTER_KEY)
        tw_full = pd.read_csv(io.BytesIO(obj["Body"].read()), dtype=str).fillna("")
        x_new_users = tw_full[tw_full["user_created"].str.startswith(date_str)]["user_name"].nunique()
        x_row = pd.DataFrame([{
            "date": date_str,
            "total_users": len(x_users),
            "new_users": int(x_new_users),
        }])
        _write(x_row, f"{GOLD_PREFIX}/daily_users_metric/platform=X/date={date_str}/data.parquet")
    except Exception as exc:
        print(f"ERROR daily_users_metric: {exc}")
        failed.append("daily_users_metric")

    # 4. Top 10 X korisnika po broju pratilaca (iz bronze)
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=BRONZE_TWITTER_KEY)
        tw = pd.read_csv(io.BytesIO(obj["Body"].read()), dtype=str).fillna("0")
        tw["user_followers"] = pd.to_numeric(tw["user_followers"], errors="coerce").fillna(0).astype(int)
        top_x = (
            tw[["user_name", "user_followers", "user_verified"]]
            .drop_duplicates(subset=["user_name"])
            .nlargest(TOP_N, "user_followers")
            .rename(columns={"user_name": "username"})
        )
        _write(top_x, f"{GOLD_PREFIX}/top_x_users_by_followers/data.parquet")
    except Exception as exc:
        print(f"ERROR top_x_users: {exc}")
        failed.append("top_x_users")

    # 5 & 6. Top 10 HN korisnika sa najvećim i najmanjim karma score-om (Firebase API)
    try:
        if not hn_posts.empty:
            unique_users = hn_posts["author_username"].dropna().unique().tolist()
            print(f"Fetching karma for {len(unique_users)} HN users...")
            karma_map = fetch_karma_bulk(unique_users)

            karma_df = pd.DataFrame([
                {"username": u, "karma_score": k, "date": date_str}
                for u, k in karma_map.items()
                if k is not None
            ])

            if not karma_df.empty:
                top_max = karma_df.nlargest(TOP_N, "karma_score")
                _write(top_max, f"{GOLD_PREFIX}/top_hn_users_max_karma/date={date_str}/data.parquet")

                top_min = karma_df.nsmallest(TOP_N, "karma_score")
                _write(top_min, f"{GOLD_PREFIX}/top_hn_users_min_karma/date={date_str}/data.parquet")
    except Exception as exc:
        print(f"ERROR top_hn_karma: {exc}")
        failed.append("top_hn_karma")

    # 7 & 8. Top 10 HN story i job objava po score (iz bronze)
    for item_type in ("story", "job"):
        try:
            hits = _read_json(f"{BRONZE_HN_PREFIX}/year={y}/month={m}/day={d}/{item_type}.json")
            if hits:
                rows = [
                    {
                        "post_id": h.get("objectID", ""),
                        "title": h.get("title", ""),
                        "author": h.get("author", ""),
                        "score": int(h.get("points") or 0),
                        "date": date_str,
                    }
                    for h in hits if h.get("objectID")
                ]
                plural = "stories" if item_type == "story" else f"{item_type}s"
                top = pd.DataFrame(rows).nlargest(TOP_N, "score")
                _write(top, f"{GOLD_PREFIX}/top_hn_{plural}_by_score/date={date_str}/data.parquet")
        except Exception as exc:
            print(f"ERROR top_hn_{item_type}s: {exc}")
            failed.append(f"top_hn_{item_type}s")

    if failed:
        raise RuntimeError(f"Failed metrics: {failed}")
