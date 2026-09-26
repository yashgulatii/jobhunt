# Job Search Console

Automated fresher-role (0-1 years) tracker for cybersecurity + adjacent
roles across Delhi/NCR, Bangalore, Hyderabad, Chandigarh + pan-India.
Runs on GitHub Actions — no server, no cost.

## What it does

- Every 30 min, 9:00 AM-2:00 PM IST, pulls fresh postings from **Adzuna**
  and **Jooble** (both official APIs — not scraping LinkedIn/Naukri; see
  "Why no LinkedIn/Naukri scraping" below), across ~31 keyword variants
  of the 10 tracked roles x 5 locations.
- Drops anything that isn't a 0-1 year fit *before* it's even stored —
  title blacklist (Senior/Lead/5+ years/etc.) plus a regex scan for
  stated years-of-experience requirements.
- Batch-scores everything that survives for legitimacy: heuristic
  red-flag regex first, then an LLM call (multiple jobs per call, not
  one each — see "Why batching" below) for a 0-100 score + reasons.
  Primary is OpenRouter's free DeepSeek V3; if that's rate-limited it
  automatically retries on Groq's free Llama 3.3 70B.
- Publishes results to a dashboard (`docs/index.html`, served free via
  GitHub Pages) with filters by role, city, category, and minimum score.

## Setup (15-20 minutes, one-time)

1. **Create the repo.** Push this folder to a new GitHub repo (public or
   private, either works with GitHub Pages on a free account for public
   repos; private repos need GitHub Pro for Pages).

2. **Get your API keys** (all free, no card required anywhere):
   - Adzuna: register at https://developer.adzuna.com/ → gives you an
     `app_id` and `app_key`.
   - Jooble: register at https://jooble.org/api/about → gives you an API key.
   - OpenRouter: create a free key at https://openrouter.ai/keys. Free
     models need no purchase, but are capped at 50 requests/day until
     you've bought $10 of credits once (lifetime, not recurring) — after
     that it's 1,000/day. With batching (6 jobs/call) 50/day already
     covers ~300 postings, so start without paying anything.
   - Groq: create a free key at https://console.groq.com/keys (no card —
     same provider Vyomayana already uses). This is the fallback if
     OpenRouter's daily cap is hit; Groq's free tier is a flat 1,000
     requests/day with no purchase needed.

3. **Add them as repo secrets.** In your repo: Settings → Secrets and
   variables → Actions → New repository secret. Add:
   - `ADZUNA_APP_ID`
   - `ADZUNA_APP_KEY`
   - `JOOBLE_API_KEY`
   - `OPENROUTER_API_KEY`
   - `GROQ_API_KEY`

4. **Enable GitHub Pages.** Settings → Pages → Source: "Deploy from a
   branch" → Branch: `main`, folder: `/docs`. Your dashboard will be live
   at `https://<your-username>.github.io/<repo-name>/`.

5. **Enable the workflow.** Actions tab → you may need to click "I
   understand my workflows, go ahead and enable them" the first time.
   Trigger one manual run via Actions → Job Search Automation → Run
   workflow, then check that run's logs — `fetch_jobs.py` prints raw
   results found / rejected-for-experience / rejected-duplicate / new,
   and `score_jobs.py` prints how many it scored. That log line is the
   fastest way to tell "no postings this run" (normal, keep waiting)
   apart from "something's actually broken" (check the error in the log).

## About the "no jobs matched" issue

The first version of this tool baked words like "fresher" and "L1" into
the search query itself. Adzuna and Jooble both do an AND-match across
every word in the query — most real postings don't contain the literal
word "fresher," so that filtered the search down to zero. Fixed now:
queries are short, natural job titles (e.g. just "SOC Analyst"), and
fresher-suitability is enforced afterward via the experience filter
instead of baked into the search string.

## There's no free Claude model

Anthropic doesn't offer one — every "free Claude" guide online is
actually routing a different open-weight model (Llama, DeepSeek, Qwen)
through something like OpenRouter and just keeping the `claude` CLI name.
DeepSeek V3 (this tool's primary scorer) is a genuinely strong free
alternative for this kind of judgment call, not an imitation of Claude.

## Why no LinkedIn/Naukri scraping

Both explicitly forbid automated scraping in their ToS, and LinkedIn has
sued scrapers as recently as this year — the post-*hiQ v. LinkedIn* case
law protects public scraping from *criminal* liability, not from account
bans or civil contract claims. You're actively using your LinkedIn
profile for outreach right now; an account flag would cost you more than
this tool saves you. Adzuna already aggregates Indeed and thousands of
other boards under one official API, so you're not losing much coverage —
for LinkedIn specifically, keep using their own job-alert emails and
check manually during your 9-2 window.

## Why batching

Scoring each posting with its own LLM call means paying for the full
system prompt every single time, and burns one request per job against
free-tier rate limits. `score_jobs.py` groups postings into batches of 6
and scores a whole batch in one call — the instructions are sent once,
descriptions are trimmed to 400 characters (enough to catch scam/
experience signals, not the whole posting), and `max_tokens` scales with
batch size instead of being a flat guess. This is what makes the 50-
requests/day OpenRouter free tier actually workable at this volume.

## Editing the tracked roles/keywords/cities

Everything lives in `config.py`:
- `ROLES` — each has a list of search-query variants (`queries`), not
  just one. Add more phrasings to widen the net for a role.
- `CITIES` / `NATIONAL_LOCATION` — add a city and it's automatically
  included in the rotation.
- `EXPERIENCE_MAX_YEARS` / `TITLE_EXCLUDE_KEYWORDS` — tune the fresher
  filter here if it's too strict or too loose.

## The legitimacy score is a triage tool, not a verdict

It catches the obvious patterns (upfront fees, off-platform-only contact,
guaranteed-offer language) and gives you a fast read on the rest. Still
independently verify any company before sharing personal info or paying
anything, the same way you already do.

## Quota note

With ~155 role/city/keyword combinations and 11 scheduled runs/day, the
fetcher covers roughly 1/11th per run (a full sweep completes once daily,
evenly spread — see the docstring in `fetch_jobs.py` for the exact
bucketing math). If you still hit API limits, check each provider's
dashboard and trim `queries` or `CITIES` in `config.py`.
