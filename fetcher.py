"""
fetcher.py — Job Search Agent: Fetcher step

Pulls job listings from the JSearch API (RapidAPI) using the /search-v2
endpoint with cursor-based pagination, and upserts results into the
`jobs` table in Postgres.

Env vars expected (put these in a .env file and load with python-dotenv,
or set them in your shell):
    RAPIDAPI_KEY        - your RapidAPI key for JSearch
    DB_HOST             - default: localhost
    DB_PORT             - default: 5432
    DB_NAME             - default: job_search_agent
    DB_USER             - default: postgres
    DB_PASSWORD         - your postgres password

Usage:
    python fetcher.py --query "generative ai developer in Hyderabad" --pages 2
"""

import os
import sys
import argparse
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timezone
from dotenv import load_dotenv
from db_config import get_db_conn

load_dotenv()

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_URL = f"https://{JSEARCH_HOST}/search-v2"

SOURCE_MAP = {
    "linkedin.com": "linkedin",
    "indeed.com": "indeed",
    "naukri.com": "naukri",
    "glassdoor.com": "glassdoor",
}


def guess_source(apply_link: str) -> str:
    if not apply_link:
        return "other"
    for domain, name in SOURCE_MAP.items():
        if domain in apply_link:
            return name
    return "google_jobs"


def fetch_jobs(query: str, max_pages: int = 1, country: str = "in") -> list[dict]:
    """Calls JSearch /search-v2 with cursor pagination, returns raw job dicts."""
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        sys.exit("ERROR: RAPIDAPI_KEY environment variable not set.")

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": JSEARCH_HOST,
    }

    all_jobs = []
    cursor = None

    for page_num in range(max_pages):
        params = {"query": query, "country": country}
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        # Response shape: {"data": {"jobs": [...], "cursor": "..."}}
        inner = payload.get("data", {})
        jobs = inner.get("jobs", [])
        all_jobs.extend(jobs)

        cursor = inner.get("cursor")
        if not cursor or not jobs:
            break  # no more pages

    return all_jobs


def normalize_job(raw: dict) -> dict:
    """Maps a raw JSearch job dict to jobs table columns."""
    apply_link = raw.get("job_apply_link") or raw.get("job_google_link") or ""

    posted_ts = raw.get("job_posted_at_timestamp")
    posted_at = (
        datetime.fromtimestamp(posted_ts, tz=timezone.utc) if posted_ts else None
    )

    return {
        "external_job_id": raw.get("job_id"),
        "source": guess_source(apply_link),
        "title": raw.get("job_title", "Unknown title"),
        "company_name": raw.get("employer_name", "Unknown company"),
        "location": raw.get("job_city") or raw.get("job_country"),
        "is_remote": bool(raw.get("job_is_remote", False)),
        "employment_type": raw.get("job_employment_type"),
        "description": raw.get("job_description"),
        "salary_min": raw.get("job_min_salary"),
        "salary_max": raw.get("job_max_salary"),
        "salary_currency": raw.get("job_salary_currency"),
        "apply_link": apply_link,
        "posted_at": posted_at,
    }


UPSERT_SQL = """
INSERT INTO jobs (
    external_job_id, source, title, company_name, location, is_remote,
    employment_type, description, salary_min, salary_max, salary_currency,
    apply_link, posted_at
)
VALUES %s
ON CONFLICT (external_job_id, source)
DO UPDATE SET
    title            = EXCLUDED.title,
    company_name     = EXCLUDED.company_name,
    location         = EXCLUDED.location,
    is_remote        = EXCLUDED.is_remote,
    employment_type  = EXCLUDED.employment_type,
    description      = EXCLUDED.description,
    salary_min       = EXCLUDED.salary_min,
    salary_max       = EXCLUDED.salary_max,
    salary_currency  = EXCLUDED.salary_currency,
    apply_link       = EXCLUDED.apply_link,
    posted_at        = EXCLUDED.posted_at,
    fetched_at       = now();
"""


def upsert_jobs(jobs: list[dict]) -> int:
    if not jobs:
        return 0

    rows = [
        (
            j["external_job_id"], j["source"], j["title"], j["company_name"],
            j["location"], j["is_remote"], j["employment_type"], j["description"],
            j["salary_min"], j["salary_max"], j["salary_currency"],
            j["apply_link"], j["posted_at"],
        )
        for j in jobs
        if j["external_job_id"]  # skip anything without an id
    ]

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(cur, UPSERT_SQL, rows)
        return len(rows)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch jobs from JSearch and load into Postgres")
    parser.add_argument("--query", required=True, help="Search query, e.g. 'genai developer in hyderabad'")
    parser.add_argument("--pages", type=int, default=1, help="Number of result pages to fetch")
    parser.add_argument("--country", default="in", help="Country code for JSearch query, default 'in'")
    args = parser.parse_args()

    print(f"Fetching jobs for query: {args.query!r} ({args.pages} page(s))...")
    raw_jobs = fetch_jobs(args.query, args.pages, args.country)
    print(f"Fetched {len(raw_jobs)} raw listings from JSearch.")

    normalized = [normalize_job(j) for j in raw_jobs]
    inserted = upsert_jobs(normalized)
    print(f"Upserted {inserted} rows into jobs table.")


if __name__ == "__main__":
    main()