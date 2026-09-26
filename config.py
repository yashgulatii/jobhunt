"""
Central config: the 10 tracked role buckets, search keyword variants,
cities, and experience-filtering rules. Edit this file to tune the tool —
nothing else needs to change.
"""

# Each role has SEVERAL search-query variants. Real postings rarely use
# the literal word "fresher" — they just don't mention senior-level years.
# So queries here are short, natural job-title phrases (2-3 words), and
# the fresher/junior filtering happens separately via EXPERIENCE_MAX_YEARS
# and TITLE_EXCLUDE_KEYWORDS below, not by cramming qualifiers into the
# search string (that's what caused zero matches before — Adzuna/Jooble
# both do an AND-match across every word in the query).
ROLES = [
    {
        "id": "soc-analyst", "category": "core", "title": "SOC Analyst",
        "queries": ["SOC Analyst", "Security Operations Analyst", "Cyber Security Analyst"],
    },
    {
        "id": "vapt", "category": "core", "title": "VAPT / Pentester",
        "queries": ["Penetration Tester", "VAPT Engineer", "Ethical Hacker", "Security Consultant"],
    },
    {
        "id": "appsec", "category": "core", "title": "AppSec Engineer",
        "queries": ["Application Security Engineer", "AppSec Engineer", "Product Security Engineer"],
    },
    {
        "id": "grc", "category": "core", "title": "GRC / Compliance Analyst",
        "queries": ["GRC Analyst", "Compliance Analyst", "IT Risk Analyst", "Information Security Analyst"],
    },
    {
        "id": "cti", "category": "core", "title": "Cyber Threat Intel Analyst",
        "queries": ["Threat Intelligence Analyst", "Cyber Threat Analyst"],
    },
    {
        "id": "noc", "category": "adjacent", "title": "NOC Engineer",
        "queries": ["NOC Engineer", "Network Operations Analyst"],
    },
    {
        "id": "tech-support", "category": "adjacent", "title": "Technical Support Executive",
        "queries": ["Technical Support Executive", "IT Help Desk", "Desktop Support Engineer", "Service Desk Analyst"],
    },
    {
        "id": "sysadmin", "category": "adjacent", "title": "System / Network Admin",
        "queries": ["System Administrator", "Network Administrator", "IT Administrator"],
    },
    {
        "id": "qa-engineer", "category": "adjacent", "title": "QA / Test Engineer",
        "queries": ["QA Engineer", "Software Test Engineer", "SDET"],
    },
    {
        "id": "it-auditor", "category": "adjacent", "title": "IT Auditor",
        "queries": ["IT Auditor", "IS Auditor", "Internal Auditor IT"],
    },
]

# City-level searches, plus "India" once per role to catch remote/pan-India
# postings that aren't tagged to a specific city.
CITIES = ["Delhi", "Bangalore", "Hyderabad", "Chandigarh"]
NATIONAL_LOCATION = "India"

ADZUNA_COUNTRY = "in"              # Adzuna country code for India
JOOBLE_COUNTRY_SUBDOMAIN = "in"    # Jooble's India subdomain

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
