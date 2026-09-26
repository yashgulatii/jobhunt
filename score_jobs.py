"""
Scores every posting that doesn't have a score yet.

Three layers, cheapest first:
1. Heuristic red-flag regex (free, instant) — upfront-payment language,
   off-platform-only contact, guaranteed-offer phrasing. Result is passed
   to the LLM as a hint rather than used standalone, so it sharpens the
   model's read instead of being a second, disagreeing opinion.
2. LLM batch scoring — jobs are grouped into batches of BATCH_SIZE and
   scored in ONE call per batch instead of one call per job. This is the
   main token/request optimization: a shared system prompt + N short job
   summaries costs far fewer tokens than N separate calls each repeating
   the full instructions, and it uses N times fewer requests against
   free-tier rate limits.
3. Provider fallback — primary is OpenRouter's DeepSeek V3 (`:free`,
   no card, stronger reasoning than Llama for this kind of judgment call).
   If OpenRouter 429s (its free daily cap is tighter than Groq's) or is
   unreachable, the same batch retries against Groq's Llama 3.3 70B
   automatically. Only if both fail does a job fall back to heuristics-only.

None of this replaces your own judgment before you apply — it's a triage
layer so you spend your 9-2 window on what's worth a closer look, not a
verdict to trust blindly. Always independently verify a company before
sharing personal info or paying anything, same as you already do.

Note: there is no free Claude API — Anthropic doesn't offer one. If you
ever want to swap a provider in for Claude anyway (better judgment on
ambiguous postings, real cost, needs a funded console account), point a
new entry in PROVIDERS at https://api.anthropic.com/v1/messages with
model "claude-haiku-4-5-20251001" — the request/response shape differs
slightly from the OpenAI-style ones here, so call_chat() would need a
small branch for it.
"""
import json
import os
import re
import sys
import time

import requests

from config import DATA_FILE

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

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

BATCH_SIZE = 6                 # jobs per LLM call
DESCRIPTION_BUDGET = 400       # chars of description sent per job — enough
                                # for scam/experience signals, not the whole posting
MAX_RETRIES_PER_PROVIDER = 2
RETRY_BACKOFF_SECONDS = 3

RED_FLAG_PATTERNS = [
    (r"registration fee|security deposit|processing fee|refundable deposit", "asks for money upfront"),
    (r"\bwhatsapp only\b|\btelegram only\b|contact.*whatsapp", "pushes contact off-platform to WhatsApp/Telegram"),
    (r"work from home.*earn.*(per day|daily)", "vague high-daily-earnings WFH pitch"),
    (r"no interview|instant offer|guaranteed job|100% placement", "skips normal hiring process"),
    (r"send.*aadhaar|send.*pan card|bank details.*before joining", "asks for sensitive ID/bank info pre-hire"),
]

SYSTEM_PROMPT = """You review Indian fresher-level (0-1 years experience) job postings for two things:
1. Legitimacy: is this a real hiring post, or a scam/low-quality posting (fake job, MLM,
   unpaid-fee scheme, data-harvesting form)?
2. Experience fit: despite being labeled fresher-friendly, does the actual description
   imply more than 1 year is really expected?

Weigh: is the company name specific and checkable, is compensation realistic for an
Indian fresher role, is the language generic/mass-posted, does it ask for money or
sensitive documents before hiring, is there pressure/urgency language.

Respond with ONLY a JSON array, no markdown fences, no other text — one object per
job, in the same order given, each shaped exactly like:
{"score": <integer 0-100, 100=clearly legitimate and fresher-appropriate>, "verdict": "<likely legitimate|use caution|high risk>", "reasons": ["<short reason>", "..."]}"""


class RateLimited(Exception):
    pass


def heuristic_flags(text):
    flags = []
    low = text.lower()
    for pattern, label in RED_FLAG_PATTERNS:
        if re.search(pattern, low):
            flags.append(label)
    return flags


def build_batch_prompt(batch):
    lines = []
    for i, (job, flags) in enumerate(batch):
        desc = job.get("description", "")[:DESCRIPTION_BUDGET]
        lines.append(
            f"[{i}] Title: {job['title']} | Company: {job['company']} | "
            f"Source: {job['source']} | Heuristic flags: {flags or 'none'}\n"
            f"Description: {desc}"
        )
    return "\n\n".join(lines)


def call_chat(provider, messages, max_tokens):
    resp = requests.post(
        provider["url"],
        headers={"Authorization": f"Bearer {provider['key']}", "content-type": "application/json"},
        json={"model": provider["model"], "messages": messages, "max_tokens": max_tokens, "temperature": 0.2},
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


def score_batch(batch):
    """batch: list of (job, heuristic_flags). Returns list of result dicts
    (or None per item on total failure), same order as input."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_batch_prompt(batch)},
    ]
    max_tokens = 120 * len(batch)  # scales with batch size, not a fixed guess

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


def main():
    if not os.path.exists(DATA_FILE):
        print("No data file yet — run fetch_jobs.py first.")
        return

    with open(DATA_FILE) as f:
        jobs = json.load(f)

    unscored = [j for j in jobs if j.get("score") is None]
    print(f"{len(unscored)} postings need scoring")

    scored_count = 0
    for start in range(0, len(unscored), BATCH_SIZE):
        chunk = unscored[start:start + BATCH_SIZE]
        prepared = [(j, heuristic_flags(j.get("description", "") + " " + j.get("title", ""))) for j in chunk]

        results = score_batch(prepared)

        if results:
            for job, (_, flags), result in zip(chunk, prepared, results):
                job["score"] = result.get("score")
                job["verdict"] = result.get("verdict")
                job["reasons"] = result.get("reasons", []) + ([f"heuristic: {f}" for f in flags] if flags else [])
                scored_count += 1
        else:
            # Both providers failed for this batch — fall back to
            # heuristics-only rather than leaving jobs stuck pending forever.
            for job, (_, flags) in prepared:
                if flags:
                    job["score"], job["verdict"] = 20, "high risk"
                    job["reasons"] = [f"heuristic: {f}" for f in flags]
                else:
                    job["score"], job["verdict"] = 55, "use caution"
                    job["reasons"] = ["AI scoring unavailable this run — no obvious red flags found, verify manually"]
                scored_count += 1

    with open(DATA_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

    print(f"Scored {scored_count} postings")


if __name__ == "__main__":
    main()
