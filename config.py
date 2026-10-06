"""
Central config: tracked role buckets, search keyword variants, cities,
and experience-filtering rules. Edit this file to tune the tool —
nothing else needs to change.

IMPORTANT on `queries`: these are SEARCH discovery terms only, used to
cast a wide net on Adzuna/Jooble. Adzuna/Jooble rank by loose relevance
across title+description, not an exact title match, so a query like "QA
Engineer" can and does return postings that merely mention testing in
passing. Which role a job actually gets tagged as is decided LATER, in
score_jobs.py, by having the AI read the real title+description and
classify it against `desc` below — not by which query happened to
surface it. `desc` is what the AI sees to make that call, so keep it a
sharp, distinguishing one-liner, not a restatement of the title.
"""

ROLES = [
    {
        "id": "soc-analyst", "category": "core", "title": "SOC Analyst",
        "queries": ["SOC Analyst", "Security Operations Analyst", "Cyber Security Analyst"],
        "desc": "Monitors security alerts/SIEM, triages and responds to incidents in a Security Operations Center.",
    },
    {
        "id": "vapt", "category": "core", "title": "VAPT / Pentester",
        "queries": ["Penetration Tester", "VAPT Engineer", "Ethical Hacker", "Security Consultant"],
        "desc": "Performs penetration testing, vulnerability assessment, or ethical hacking engagements.",
    },
    {
        "id": "appsec", "category": "core", "title": "AppSec Engineer",
        "queries": ["Application Security Engineer", "AppSec Engineer", "Product Security Engineer"],
        "desc": "Reviews application or code security, secure SDLC, product/application security engineering.",
    },
    {
        "id": "grc", "category": "core", "title": "GRC / Compliance Analyst",
        "queries": ["GRC Analyst", "Compliance Analyst", "IT Risk Analyst", "Information Security Analyst"],
        "desc": "Governance, risk, and compliance work — IT risk assessments, security policy, audits of controls.",
    },
    {
        "id": "cti", "category": "core", "title": "Cyber Threat Intel Analyst",
        "queries": ["Threat Intelligence Analyst", "Cyber Threat Analyst"],
        "desc": "Researches threat actors, indicators of compromise, produces threat intelligence reporting.",
    },
    {
        "id": "noc", "category": "adjacent", "title": "NOC Engineer",
        "queries": ["NOC Engineer", "Network Operations Analyst"],
        "desc": "Monitors network operations center dashboards, network uptime, infrastructure alerting — not security-focused.",
    },
    {
        "id": "tech-support", "category": "adjacent", "title": "Technical Support Executive",
        "queries": ["Technical Support Executive", "IT Help Desk", "Desktop Support Engineer", "Service Desk Analyst"],
        "desc": "IT helpdesk, desktop support, or service desk — troubleshooting for end users, ticket resolution.",
    },
    {
        "id": "sysadmin", "category": "adjacent", "title": "System / Network Admin",
        "queries": ["System Administrator", "Network Administrator", "IT Administrator"],
        "desc": "Administers servers, networks, or Windows/Linux systems — IT infrastructure upkeep, not a helpdesk role.",
    },
    {
        "id": "qa-engineer", "category": "adjacent", "title": "QA / Test Engineer",
        "queries": ["QA Engineer", "Software Test Engineer", "SDET"],
        "desc": "Software testing — writing/executing test cases, QA or SDET work on an engineering team.",
    },
    {
        "id": "it-auditor", "category": "adjacent", "title": "IT Auditor",
        "queries": ["IT Auditor", "IS Auditor", "Internal Auditor IT"],
        "desc": "Internal or IS audit of IT controls and processes — distinct from GRC's ongoing risk/policy work.",
    },
    {
        "id": "mis-executive", "category": "mis", "title": "MIS Executive",
        "queries": ["MIS Executive", "MIS Analyst", "MIS Reporting Executive", "Excel MIS"],
        "desc": "Maintains MIS reports/dashboards — heavy Excel/SQL reporting and data compilation for management. Not a security or dev role.",
    },
]

# Role catalog the AI classifier is constrained to — built from ROLES so
# there's exactly one place this list is maintained. "unmatched" is always
# offered as an explicit escape hatch so the model isn't forced to pick a
# wrong role when a posting is just noise from the fuzzy keyword search.
ROLE_CATALOG = [{"id": r["id"], "title": r["title"], "desc": r["desc"]} for r in ROLES]

# City-level searches, plus "India" once per role to catch remote/pan-India
# postings that aren't tagged to a specific city.
CITIES = ["Delhi", "Bangalore", "Hyderabad", "Chandigarh"]
NATIONAL_LOCATION = "India"

ADZUNA_COUNTRY = "in"              # Adzuna country code for India

MAX_DAYS_OLD = 5          # posting age window
RESULTS_PER_QUERY = 20    # per API, per query/location combo

# --- Experience filtering: keep this to 0-1 years, drop everything else ---
EXPERIENCE_MAX_YEARS = 1

# If any of these appear in the title, the posting is dropped before it's
# even stored (saves LLM tokens/calls on things that are obviously not a
# fresher role).
TITLE_EXCLUDE_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "manager", "principal", "director",
    "architect", "head of", "vp ", "vice president", "staff engineer",
    "sme", "10+ years", "8+ years", "7+ years", "6+ years", "5+ years",
]

DATA_FILE = "docs/data/jobs.json"   # served by GitHub Pages from /docs
