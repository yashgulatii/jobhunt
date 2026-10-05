"""
Classifies and scores every posting that isn't role_confirmed yet.

This is the step that actually reads each job and decides what it is —
fetch_jobs.py only tags a `candidate_role_id` (a hint, from whichever
search query surfaced the posting). A job is never shown on either
dashboard until role_confirmed is True, so a mistagged posting never
appears under the wrong role — it just stays pending until a real
AI pass classifies it, instead of leaking in via the fallback a
previous version of this script had.

One LLM call per batch does three things at once, on purpose — a single
well-specified call is both cheaper AND more accurate than three separate
calls, because the model sees all the context together:
1. Classify: which role in ROLE_CATALOG does this ACTUALLY match, reading
   the real title+description — or "unmatched" if none of them fit. A
   posting classified "unmatched" is dropped entirely; it's noise from
   the fuzzy keyword search, not a tagging error to paper over.
2. Legitimacy: real hiring post vs scam/low-quality, informed by a cheap
   heuristic red-flag pre-check so the model isn't finding the obvious
   stuff from scratch.
3. Experience fit: does the actual description imply more than
   EXPERIENCE_MAX_YEARS despite surviving the regex pre-filter.

Provider: primary is OpenRouter's free DeepSeek V3 (no card, stronger
reasoning than Llama for a judgment call like this); Groq's free Llama
3.3 70B is the automatic fallback if OpenRouter is rate-limited.

If BOTH providers fail for a batch, those jobs are left pending (not
finalized with a guessed score) and retried on the next scheduled run —
accuracy over availability, since a wrongly-classified or unverified
posting showing up on either dashboard is the exact bug being fixed here.

This does NOT replace your own judgment — it's a triage layer. Always
independently verify a company before sharing personal info or paying
anything, same as you already do.

There's no free Claude API — Anthropic doesn't offer one. To swap a
provider in for Claude anyway (real cost, needs a funded console
account), point a new PROVIDERS entry at
https://api.anthropic.com/v1/messages with model
"claude-haiku-4-5-20251001" — its request/response shape differs from
the OpenAI-style ones here, so call_chat() would need a small branch.
"""
import json
import os
import re
import sys
import time

import requests

from config import DATA_FILE, ROLES, ROLE_CATALOG

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

ROLES_BY_ID = {r["id"]: r for r in ROLES}

# Tried in order. Each must speak the OpenAI chat-completions format.
PROVIDERS = [
    {
        "name": "openrouter",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": OPENROUTER_API_KEY,
        "model": "deepseek/deepseek-chat:free",
    },
    {
        "name": "groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key": GROQ_API_KEY,
        "model": "llama-3.3-70b-versatile",
    },
]

BATCH_SIZE = 5                 # jobs per LLM call (slightly smaller than before —
                                # each job now needs more output: role_id + score + verdict + reasons)
DESCRIPTION_BUDGET = 450       # chars of description sent per job
MAX_RETRIES_PER_PROVIDER = 2
RETRY_BACKOFF_SECONDS = 3

RED_FLAG_PATTERNS = [
    (r"registration fee|security deposit|processing fee|refundable deposit", "asks for money upfront"),
    (r"\bwhatsapp only\b|\btelegram only\b|contact.*whatsapp", "pushes contact off-platform to WhatsApp/Telegram"),
    (r"work from home.*earn.*(per day|daily)", "vague high-daily-earnings WFH pitch"),
    (r"no interview|instant offer|guaranteed job|100% placement", "skips normal hiring process"),
    (r"send.*aadhaar|send.*pan card|bank details.*before joining", "asks for sensitive ID/bank info pre-hire"),
]


class RateLimited(Exception):
    pass


def heuristic_flags(text):
    flags = []
    low = text.lower()
    for pattern, label in RED_FLAG_PATTERNS:
        if re.search(pattern, low):
            flags.append(label)
    return flags


def build_catalog_block():
    lines = [f'- "{r["id"]}": {r["title"]} — {r["desc"]}' for r in ROLE_CATALOG]
    return "\n".join(lines)


def build_system_prompt():
    return f"""You review Indian fresher-level (0-1 year experience) job postings. For EACH
job you do three things:

1. CLASSIFY which role it actually is, based on the real title+description —
   not any label it arrived with. Pick exactly one id from this catalog, or
   "unmatched" if none genuinely fit (don't force a weak match):
{build_catalog_block()}

2. LEGITIMACY: real hiring post, or scam/low-quality (fake job, MLM, unpaid-fee
   scheme, data-harvesting form)? Weigh: is the company specific and checkable,
   is pay realistic for an Indian fresher, is the language generic/mass-posted,
   does it ask for money or sensitive documents pre-hire, is there pressure/
   urgency language. A heuristic red-flag pre-check is given as a hint per job —
   use it, don't ignore it, but you can override it if the full text disagrees.

3. EXPERIENCE FIT: does the description really expect more than 1 year despite
   passing an initial filter? Factor this into the score if so.

Respond with ONLY a JSON array, no markdown fences, no other text — one object
per job, SAME ORDER as given, each shaped exactly like:
{{"role_id": "<catalog id or \\"unmatched\\">", "score": <integer 0-100, 100=clearly legitimate and fresher-appropriate; irrelevant if role_id is "unmatched">, "verdict": "<likely legitimate|use caution|high risk>", "reasons": ["<short reason>", "..."]}}"""


def build_batch_prompt(batch):
    lines = []
    for i, (job, flags) in enumerate(batch):
        desc = job.get("description", "")[:DESCRIPTION_BUDGET]
        lines.append(
            f"[{i}] Title: {job['title']} | Company: {job['company']} | "
            f"Found via search for: {job.get('candidate_role_title', '?')} | "
            f"Heuristic flags: {flags or 'none'}\n"
            f"Description: {desc}"
        )
    return "\n\n".join(lines)


def call_chat(provider, messages, max_tokens):
    resp = requests.post(
        provider["url"],
        headers={"Authorization": f"Bearer {provider['key']}", "content-type": "application/json"},
        json={"model": provider["model"], "messages": messages, "max_tokens": max_tokens, "temperature": 0.1},
        timeout=45,
    )
    if resp.status_code == 429:
        raise RateLimited(provider["name"])
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def parse_json_array(text, expected_len):
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list) or len(parsed) != expected_len:
        raise ValueError(f"expected array of {expected_len}, got {type(parsed)} len={len(parsed) if isinstance(parsed, list) else '?'}")
    return parsed


def score_batch(batch, system_prompt):
    """batch: list of (job, heuristic_flags). Returns list of result dicts,
    or None if both providers failed (caller leaves the batch pending)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_batch_prompt(batch)},
    ]
    max_tokens = 150 * len(batch)  # scales with batch size, not a fixed guess

    for provider in PROVIDERS:
        if not provider["key"]:
            continue
        for attempt in range(MAX_RETRIES_PER_PROVIDER):
            try:
                raw = call_chat(provider, messages, max_tokens)
                return parse_json_array(raw, len(batch))
            except RateLimited:
                print(f"[{provider['name']}] rate limited, trying next provider", file=sys.stderr)
                break  # don't retry same provider on 429, move to next provider
            except Exception as e:
                print(f"[{provider['name']}] attempt {attempt + 1} failed: {e}", file=sys.stderr)
                time.sleep(RETRY_BACKOFF_SECONDS)
    return None


def apply_result(job, result):
    """Returns True if the job should be kept, False if it should be dropped."""
    role_id = result.get("role_id")

    if role_id == "unmatched":
        return False

    role = ROLES_BY_ID.get(role_id)
    if role is None:
        # Model returned something outside the catalog — fall back to the
        # search-match hint rather than dropping a possibly-good job over
        # a formatting slip, but say clearly that it's unverified.
        job["role_id"] = job["candidate_role_id"]
        job["role_title"] = job["candidate_role_title"]
        job["category"] = job["candidate_category"]
        job["role_confirmed"] = False
        job["score"] = result.get("score")
        job["verdict"] = result.get("verdict")
        job["reasons"] = (result.get("reasons", [])
                           + ["role unverified — AI returned an unrecognized role id, using search-match fallback"])
        return True

    job["role_id"] = role["id"]
    job["role_title"] = role["title"]
    job["category"] = role["category"]
    job["role_confirmed"] = True
    job["score"] = result.get("score")
    job["verdict"] = result.get("verdict")
    job["reasons"] = result.get("reasons", [])
    return True


def main():
    if not os.path.exists(DATA_FILE):
        print("No data file yet — run fetch_jobs.py first.")
        return

    with open(DATA_FILE) as f:
        jobs = json.load(f)

    pending = [j for j in jobs if not j.get("role_confirmed")]
    already_done = [j for j in jobs if j.get("role_confirmed")]
    print(f"{len(pending)} postings need classification+scoring, {len(already_done)} already confirmed")

    system_prompt = build_system_prompt()
    kept_from_pending = []
    dropped_unmatched = 0
    left_pending = 0

    for start in range(0, len(pending), BATCH_SIZE):
        chunk = pending[start:start + BATCH_SIZE]
        prepared = [(j, heuristic_flags(j.get("description", "") + " " + j.get("title", ""))) for j in chunk]

        results = score_batch(prepared, system_prompt)

        if results is None:
            # Both providers failed — leave this batch pending for next run
            # rather than guessing. Accuracy over availability.
            kept_from_pending.extend(chunk)
            left_pending += len(chunk)
            continue

        for job, result in zip(chunk, results):
            if apply_result(job, result):
                kept_from_pending.append(job)
            else:
                dropped_unmatched += 1

    final_jobs = already_done + kept_from_pending

    with open(DATA_FILE, "w") as f:
        json.dump(final_jobs, f, indent=2)

    print(f"Classified: {len(pending) - left_pending - dropped_unmatched} | "
          f"dropped (unmatched/noise): {dropped_unmatched} | "
          f"left pending (both providers unavailable): {left_pending}")


if __name__ == "__main__":
    main()
