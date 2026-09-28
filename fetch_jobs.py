"""
Pulls fresh postings from Adzuna and Jooble (both official, key-based APIs
— no scraping) for a rotating slice of role-query x location combinations,
rejects anything that clearly needs more than EXPERIENCE_MAX_YEARS before
it's even stored, dedupes against what's already saved, and appends the
rest with score=None (score_jobs.py fills that in next).

Rotation: with ~31 query variants x 5 locations (4 cities + national) that's
~155 combos. Querying all of them every run would blow through free-tier
API quotas fast for no benefit — postings don't change minute to minute.
N_BUCKETS is set to match the number of scheduled runs per day (11), so
the bucket key is derived from (hour*60+minute)//30, which lands on 11
consecutive, distinct values across the 9-2 IST window — every combo gets
queried exactly once per day, spread evenly, with no state to persist
between runs.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

from config import (
    ROLES, CITIES, NATIONAL_LOCATION, ADZUNA_COUNTRY, JOOBLE_COUNTRY_SUBDOMAIN,
    MAX_DAYS_OLD, RESULTS_PER_QUERY, EXPERIENCE_MAX_YEARS, TITLE_EXCLUDE_KEYWORDS,
    DATA_FILE,
)

ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY")
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY")

N_BUCKETS = 11

YR = r"(?:years?|yrs?|yr)"  # covers "years", "year", "yrs", "yr"

YEARS_PATTERNS = [
    re.compile(rf"(\d+)\s*(?:-|to|–)\s*\d+\s*\+?\s*{YR}", re.I),      # "2-5 years", "2 to 5 yrs"
    re.compile(rf"(\d+)\s*\+\s*{YR}", re.I),                          # "3+ yrs"
    re.compile(rf"(?:minimum|min\.?|at least)\s*(?:of\s*)?(\d+)\s*{YR}", re.I),  # "min. 2 yrs"
    re.compile(rf"\bexp(?:erience)?\W{{0,4}}(\d+)\s*(?:-|to|–)?\s*\d*\+?\s*{YR}?", re.I),  # "Exp: 2-5 Yrs", "Experience - 3 Years"
]


def clean_text(raw):
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_min_years(text):
    """Smallest 'years required' figure found in the text, or None if the
    posting doesn't state a number — treated as fresher-friendly by default."""
    candidates = []
    for pattern in YEARS_PATTERNS:
        for m in pattern.finditer(text):
            candidates.append(int(m.group(1)))
    return min(candidates) if candidates else None


def passes_experience_filter(title, description):
    low_title = title.lower()
    if any(kw in low_title for kw in TITLE_EXCLUDE_KEYWORDS):
        return False
    min_years = extract_min_years(f"{title} {description}")
    if min_years is not None and min_years > EXPERIENCE_MAX_YEARS:
        return False
    return True


def all_combos():
    combos = []
    for role in ROLES:
        for query in role["queries"]:
            for city in CITIES + [NATIONAL_LOCATION]:
                combos.append((role, query, city))
    return combos


def current_bucket():
    now = datetime.now(timezone.utc)
    slot = (now.hour * 60 + now.minute) // 30
    return slot % N_BUCKETS


def job_key(url, title, company):
    raw = f"{url}|{title}|{company}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fetch_adzuna(query, location):
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return []
    url = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": RESULTS_PER_QUERY,
        "what": query,
        "where": location,
        "max_days_old": MAX_DAYS_OLD,
        "content-type": "application/json",
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        print(f"[adzuna] {query!r} / {location} failed: {e}", file=sys.stderr)
        return []

    jobs = []
    for r in results:
        jobs.append({
            "source": "adzuna",
            "title": clean_text(r.get("title", "")),
            "company": (r.get("company") or {}).get("display_name", "Unknown"),
            "location": (r.get("location") or {}).get("display_name", location),
            "url": r.get("redirect_url"),
            "description": clean_text(r.get("description", ""))[:2000],
            "salary_min": r.get("salary_min"),
            "salary_max": r.get("salary_max"),
            "posted": r.get("created"),
        })
    return jobs


def fetch_jooble(query, location):
    if not JOOBLE_API_KEY:
        return []
    url = f"https://{JOOBLE_COUNTRY_SUBDOMAIN}.jooble.org/api/{JOOBLE_API_KEY}"
    body = {"keywords": query, "location": location}
    try:
        resp = requests.post(url, json=body, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[jooble] {query!r} / {location} failed: {e}", file=sys.stderr)
        return []

    jobs = []
    for r in results:
        jobs.append({
            "source": "jooble",
            "title": clean_text(r.get("title", "")),
            "company": r.get("company") or "Unknown",
            "location": r.get("location") or location,
            "url": r.get("link"),
            "description": clean_text(r.get("snippet", ""))[:2000],
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

    print(f"Bucket {bucket}/{N_BUCKETS} — {len(my_combos)} of {len(combos)} total combos this run")

    raw_found = 0
    rejected_experience = 0
    rejected_duplicate = 0
    new_jobs = []

    for role, query, location in my_combos:
        found = fetch_adzuna(query, location) + fetch_jooble(query, location)
        raw_found += len(found)
        for j in found:
            if not j.get("url") or not j.get("title"):
                continue
            if not passes_experience_filter(j["title"], j["description"]):
                rejected_experience += 1
                continue
            key = job_key(j["url"], j["title"], j["company"])
            if key in existing_keys:
                rejected_duplicate += 1
                continue
            j["key"] = key
            j["role_id"] = role["id"]
            j["role_title"] = role["title"]
            j["category"] = role["category"]
            j["matched_query"] = query
            j["fetched_at"] = datetime.now(timezone.utc).isoformat()
            j["score"] = None
            j["verdict"] = None
            j["reasons"] = None
            existing_keys.add(key)
            new_jobs.append(j)
        time.sleep(0.3)  # be polite to both APIs

    print(f"Raw results: {raw_found} | rejected (experience): {rejected_experience} | "
          f"rejected (duplicate): {rejected_duplicate} | new: {len(new_jobs)}")
    save(existing + new_jobs)


if __name__ == "__main__":
    main()