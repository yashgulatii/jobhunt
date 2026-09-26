"""
Scores every posting that doesn't have a score yet.

Two layers, cheapest first:
1. Heuristic red-flag check (free, instant) — catches the obvious stuff:
   upfront-payment language, personal-only contact channels, generic
   mass-posted phrasing.
2. Claude call (Haiku — cheap, fast) — reads the full description and gives
   a 0-100 legitimacy score with reasons, informed by the heuristic flags.

This does NOT replace your own judgment before you apply — it's a triage
layer so you spend your 9-2 window on the postings worth a closer look,
not a verdict to trust blindly. Always independently verify the company
before sharing any personal info, same as you already do.
"""
import json
import os
import re
import sys

import requests

from config import DATA_FILE

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"

RED_FLAG_PATTERNS = [
    (r"registration fee|security deposit|processing fee|refundable deposit", "asks for money upfront"),
    (r"\bwhatsapp only\b|\btelegram only\b|contact.*whatsapp", "pushes contact off-platform to WhatsApp/Telegram"),
    (r"work from home.*earn.*(per day|daily)", "vague high-daily-earnings WFH pitch"),
    (r"no interview|instant offer|guaranteed job|100% placement", "skips normal hiring process"),
    (r"send.*aadhaar|send.*pan card|bank details.*before joining", "asks for sensitive ID/bank info pre-hire"),
]


def heuristic_flags(text):
    flags = []
    low = text.lower()
    for pattern, label in RED_FLAG_PATTERNS:
        if re.search(pattern, low):
            flags.append(label)
    return flags


def score_with_claude(job, flags):
    if not ANTHROPIC_API_KEY:
        return None

    prompt = f"""Assess whether this job posting looks like a legitimate hiring post or a
scam/low-quality posting (fake job, MLM, unpaid-fee scheme, data-harvesting form, etc).

Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Source: {job['source']}
Description: {job['description'][:1500]}

Automated heuristic flags already found: {flags if flags else "none"}

Consider: is the company name specific and checkable, is compensation realistic for
a fresher role in India, is the language generic/mass-posted, does it ask for money
or sensitive documents before hiring, is there pressure/urgency language.

Return ONLY valid JSON, no markdown fences, no other text, in exactly this shape:
{{"score": <integer 0-100, 100=clearly legitimate>, "verdict": "<one of: likely legitimate, use caution, high risk>", "reasons": ["<short reason>", "..."]}}
"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        print(f"[claude] scoring failed for {job.get('url')}: {e}", file=sys.stderr)
        return None


def main():
    if not os.path.exists(DATA_FILE):
        print("No data file yet — run fetch_jobs.py first.")
        return

    with open(DATA_FILE) as f:
        jobs = json.load(f)

    scored_count = 0
    for job in jobs:
        if job.get("score") is not None:
            continue

        flags = heuristic_flags(job.get("description", "") + " " + job.get("title", ""))
        result = score_with_claude(job, flags)

        if result:
            job["score"] = result.get("score")
            job["verdict"] = result.get("verdict")
            job["reasons"] = result.get("reasons", []) + ([f"heuristic: {f}" for f in flags] if flags else [])
        elif flags:
            # No AI available/failed but heuristics fired — flag it anyway rather
            # than silently leaving it unscored.
            job["score"] = 20
            job["verdict"] = "high risk"
            job["reasons"] = [f"heuristic: {f}" for f in flags]
        else:
            job["score"] = None  # leave for next run to retry

        scored_count += 1

    with open(DATA_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

    print(f"Scored {scored_count} postings")


if __name__ == "__main__":
    main()
