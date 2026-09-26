# Job Search Console

Automated fresher-role tracker for cybersecurity + adjacent roles across
Delhi/NCR, Bangalore, Hyderabad, Chandigarh. Runs on GitHub Actions —
no server, no cost beyond free API tiers.

## What it does

- Every 30 min, 9:00 AM-2:00 PM IST, pulls fresh postings from **Adzuna**
  and **Jooble** (both official APIs — not scraping LinkedIn/Naukri; see
  "Why no LinkedIn/Naukri scraping" below).
- Runs every new posting through a legitimacy check: heuristic red-flag
  patterns first, then a Claude call for a 0-100 score + reasons.
- Publishes results to a dashboard (`docs/index.html`, served free via
  GitHub Pages) with filters by role, city, category, and minimum score.

## Setup (15 minutes, one-time)

1. **Create the repo.** Push this folder to a new GitHub repo (public or
   private, either works with GitHub Pages on a free account for public
   repos; private repos need GitHub Pro for Pages).

2. **Get your API keys** (all free tiers):
   - Adzuna: register at https://developer.adzuna.com/ → gives you an
     `app_id` and `app_key`.
   - Jooble: register at https://jooble.org/api/about → gives you an API key.
   - Anthropic: create a key at https://console.anthropic.com/ (this is a
     paid-per-use API, but Haiku scoring is cheap — a few hundred postings
     a month costs cents, not dollars).

3. **Add them as repo secrets.** In your repo: Settings → Secrets and
   variables → Actions → New repository secret. Add:
   - `ADZUNA_APP_ID`
   - `ADZUNA_APP_KEY`
   - `JOOBLE_API_KEY`
   - `ANTHROPIC_API_KEY`

4. **Enable GitHub Pages.** Settings → Pages → Source: "Deploy from a
   branch" → Branch: `main`, folder: `/docs`. Your dashboard will be live
   at `https://<your-username>.github.io/<repo-name>/`.

5. **Enable the workflow.** Actions tab → you may need to click "I
   understand my workflows, go ahead and enable them" the first time.
   Trigger one manual run via Actions → Job Search Automation → Run
   workflow, to confirm secrets are wired correctly before waiting for
   the schedule.

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

## Editing the tracked roles/cities

Everything lives in `config.py` — add/remove entries in `ROLES` or
`CITIES` and the fetcher picks it up on the next run automatically.

## The legitimacy score is a triage tool, not a verdict

It catches the obvious patterns (upfront fees, off-platform-only contact,
guaranteed-offer language) and gives you a fast read on the rest. Still
independently verify any company before sharing personal info or paying
anything, the same way you already do.

## Quota note

Adzuna and Jooble free tiers have monthly call limits. The fetcher
spreads its 40 role x city combinations across 4 buckets (one per run) so
it doesn't burn through quota in a single day — a full sweep completes
roughly every 2 hours during the window. If you hit limits anyway, check
each provider's dashboard and either upgrade or drop a couple of the
lower-priority combos in `config.py`.
