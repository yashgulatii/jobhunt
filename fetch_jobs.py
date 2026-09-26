"""
Pulls fresh postings from Adzuna and Jooble (both official, key-based APIs —
no scraping) for a rotating slice of the 40 role x city combinations, dedupes
against what's already stored, and appends new postings with score=None
(score_jobs.py fills that in next).

Why a "rotating slice" instead of querying all 40 combos every run:
GitHub Actions fires this on a cron every 30 min for 5 hours (11 runs/day).
Querying all 40 combos every run would burn through free-tier API quotas
fast for no benefit — postings don't change that often. Instead each run
covers 1 of 4 buckets, so the full 40-combo sweep completes every ~4 runs
(~2 hours) while still catching new posts same-day.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

from config import ROLES, CITIES, ADZUNA_COUNTRY, JOOBLE_COUNTRY_SUBDOMAIN, MAX_DAYS_OLD, DATA_FILE

ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY")
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY")

N_BUCKETS = 4


def all_combos():
    combos = []
    for role in ROLES:
        for city in CITIES:
            combos.append((role, city))
    return combos


def current_bucket():
    # Deterministic bucket based on hour-of-day so consecutive runs cover
    # different slices without needing to persist state between runs.
    return datetime.now(timezone.utc).hour % N_BUCKETS


def job_key(url, title, company):
    raw = f"{url}|{title}|{company}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fetch_adzuna(query, city):
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return []
    url = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": 15,
        "what": query,
        "where": city,
        "max_days_old": MAX_DAYS_OLD,
        "content-type": "application/json",
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        print(f"[adzuna] {query} / {city} failed: {e}", file=sys.stderr)
        return []

    jobs = []
    for r in results:
        jobs.append({
            "source": "adzuna",
            "title": r.get("title", "").strip(),
            "company": (r.get("company") or {}).get("display_name", "Unknown"),
            "location": (r.get("location") or {}).get("display_name", city),
            "url": r.get("redirect_url"),
            "description": (r.get("description") or "")[:2000],
            "salary_min": r.get("salary_min"),
            "salary_max": r.get("salary_max"),
            "posted": r.get("created"),
        })
    return jobs


def fetch_jooble(query, city):
    if not JOOBLE_API_KEY:
        return []
    url = f"https://{JOOBLE_COUNTRY_SUBDOMAIN}.jooble.org/api/{JOOBLE_API_KEY}"
    body = {"keywords": query, "location": city}
    try:
        resp = requests.post(url, json=body, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[jooble] {query} / {city} failed: {e}", file=sys.stderr)
        return []

    jobs = []
    for r in results:
        jobs.append({
            "source": "jooble",
            "title": (r.get("title") or "").strip(),
            "company": r.get("company") or "Unknown",
            "location": r.get("location") or city,
            "url": r.get("link"),
            "description": (r.get("snippet") or "")[:2000],
            "salary_min": None,
            "salary_max": None,
            "posted": r.get("updated"),
        })
    return jobs


def load_existing():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE) as f:
        return json.load(f)


def save(jobs):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


def main():
    existing = load_existing()
    existing_keys = {j["key"] for j in existing}

    combos = all_combos()
    bucket = current_bucket()
    my_combos = [c for i, c in enumerate(combos) if i % N_BUCKETS == bucket]

    print(f"Bucket {bucket}/{N_BUCKETS} — {len(my_combos)} combos this run")

    new_jobs = []
    for role, city in my_combos:
        found = fetch_adzuna(role["query"], city) + fetch_jooble(role["query"], city)
        for j in found:
            if not j.get("url") or not j.get("title"):
                continue
            key = job_key(j["url"], j["title"], j["company"])
            if key in existing_keys:
                continue
            j["key"] = key
            j["role_id"] = role["id"]
            j["role_title"] = role["title"]
            j["category"] = role["category"]
            j["fetched_at"] = datetime.now(timezone.utc).isoformat()
            j["score"] = None
            j["verdict"] = None
            j["reasons"] = None
            existing_keys.add(key)
            new_jobs.append(j)
        time.sleep(0.5)  # be polite to both APIs

    print(f"Found {len(new_jobs)} new postings")
    save(existing + new_jobs)


if __name__ == "__main__":
    main()
