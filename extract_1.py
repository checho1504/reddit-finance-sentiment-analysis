import os
import time
import datetime
import requests
import pandas as pd


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; reddit-finance-analysis/1.0; by u/Alive-Friendship-359)"
}

SUBREDDITS = [
    "wallstreetbets",
    "investing",
    "stocks",
    "StockMarket",
    "SecurityAnalysis",
    "ValueInvesting",
    "dividends",
    "options",
    "Daytrading",
    "pennystocks",
]

FEEDS = {
    "new": "new.json",
    "top_month": "top.json?t=month",
    "top_year": "top.json?t=year",
}

ENDPOINTS = {}

for subreddit in SUBREDDITS:
    for feed_name, feed_path in FEEDS.items():
        endpoint_name = f"{subreddit}_{feed_name}"
        url = f"https://www.reddit.com/r/{subreddit}/{feed_path}"

        ENDPOINTS[endpoint_name] = {
            "subreddit": subreddit,
            "feed": feed_name,
            "url": url,
        }


FILE_NAME = r"c:\Users\Usuario\Desktop\code\Reddit_project\finance_reddit_posts.csv"

MAX_PAGES = 10
RATE_LIMIT_S = 5

# No posts before May 18, 2025
CUTOFF_UTC = datetime.datetime(
    2025, 1, 1, tzinfo=datetime.timezone.utc
).timestamp()

COLUMNS = [
    "post_id",
    "title",
    "score",
    "comments",
    "author",
    "created",
    "source_endpoint",
]


# Load existing data

if os.path.exists(FILE_NAME):
    existing_df = pd.read_csv(
        FILE_NAME,
        engine="python",
        on_bad_lines="skip"
    )

    existing_df["post_id"] = existing_df["post_id"].astype(str)
    seen_ids = set(existing_df["post_id"])

    print(f"Existing unique posts: {len(seen_ids)}")
else:
    seen_ids = set()
    print("No existing file found. Starting fresh.")


# Helper function

def fetch_page(url: str, params: dict, retries: int = 3):
    """GET with retry / back-off on Reddit errors."""
    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=30
            )

            print(
                "  Rate headers:",
                "used=", r.headers.get("x-ratelimit-used"),
                "remaining=", r.headers.get("x-ratelimit-remaining"),
                "reset=", r.headers.get("x-ratelimit-reset")
            )

            if r.status_code == 429:
                wait = int(float(r.headers.get("Retry-After", 60)))
                print(f"  Rate-limited. Waiting {wait}s ...")
                time.sleep(wait)
                continue

            if r.status_code in [500, 502, 503, 504]:
                wait = 15 * (attempt + 1)
                print(f"  Reddit server error {r.status_code}. Waiting {wait}s ...")
                print(f"  URL tried: {r.url}")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        except requests.RequestException as e:
            print(f"  Request error (attempt {attempt + 1}): {e}")

            try:
                print(f"  URL tried: {r.url}")
            except UnboundLocalError:
                pass

            time.sleep(10 * (attempt + 1))

    return None

def collect_endpoint(endpoint_name: str, endpoint_info: dict, seen_ids: set) -> list:
    
    feed_name = endpoint_info["feed"]
    base_url = endpoint_info["url"]

    new_rows = []
    after = None
    is_new_feed = feed_name == "new"
    hit_cutoff = False

    for page in range(MAX_PAGES):
        params = {"limit": 100}

        if after:
            params["after"] = after

        data = fetch_page(base_url, params)

        if data is None:
            break

        posts = data["data"]["children"]

        if not posts:
            print(f"  No more posts for {endpoint_name}.")
            break

        new_count = 0

        for post in posts:
            p = post["data"]

            post_id = str(p["id"])
            utc = float(p["created_utc"])

            # For "new", once we hit older-than-cutoff posts, stop.
            # For hot/rising/top, skip old posts but keep checking the rest.
            if utc < CUTOFF_UTC:
                if is_new_feed:
                    print(f"  Hit cutoff — stopping pagination for {endpoint_name}.")
                    hit_cutoff = True
                    break
                else:
                    continue

            if post_id not in seen_ids:
                new_rows.append({
                    "post_id": post_id,
                    "title": p.get("title"),
                    "score": p.get("score"),
                    "comments": p.get("num_comments"),
                    "author": p.get("author"),
                    "created": utc,
                    "source_endpoint": endpoint_name,
                })

                seen_ids.add(post_id)
                new_count += 1

        print(
            f"  {endpoint_name} | page {page + 1:02d} | "
            f"new: {new_count:3d} | total new this endpoint: {len(new_rows)}"
        )

        if hit_cutoff:
            break

        after = data["data"].get("after")

        if after is None:
            print(f"  Reached end of pageable results for {endpoint_name}.")
            break

        time.sleep(RATE_LIMIT_S)

    return new_rows


# Collection loop

all_new_rows = []

for endpoint_name, endpoint_info in ENDPOINTS.items():
    print(f"\n{'-' * 50}")
    print(f"Endpoint: {endpoint_name}")

    rows = collect_endpoint(
        endpoint_name,
        endpoint_info,
        seen_ids
    )

    all_new_rows.extend(rows)


# Save results

if all_new_rows:
    new_df = pd.DataFrame(all_new_rows)

    # Force exact same column structure as your existing CSV
    new_df = new_df[COLUMNS]

    # Convert Unix timestamp to readable datetime
    new_df["created"] = pd.to_datetime(new_df["created"], unit="s")

    write_header = not os.path.exists(FILE_NAME)

    new_df.to_csv(
        FILE_NAME,
        mode="a",
        header=write_header,
        index=False,
        encoding="utf-8"
    )

    print(f"\nSaved {len(new_df)} new unique posts -> {FILE_NAME}")
    print(f"Total unique posts now: {len(seen_ids)}")

else:
    print("\nNo new unique posts found this run.")