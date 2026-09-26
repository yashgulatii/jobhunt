"""
Central config: the 10 tracked role buckets and target cities.
Edit this file to add/remove roles or cities — nothing else needs to change.
"""

# category: "core" = direct cybersecurity roles, "adjacent" = supports the
# cybersecurity path while paying the bills.
ROLES = [
    {"id": "soc-analyst",      "category": "core",     "title": "SOC Analyst",              "query": "SOC Analyst L1 fresher"},
    {"id": "vapt",             "category": "core",     "title": "VAPT / Pentester",          "query": "VAPT penetration tester fresher"},
    {"id": "appsec",           "category": "core",     "title": "AppSec Engineer",           "query": "application security engineer fresher"},
    {"id": "grc",              "category": "core",     "title": "GRC / Compliance Analyst",  "query": "GRC compliance analyst fresher"},
    {"id": "cti",              "category": "core",     "title": "Cyber Threat Intel Analyst","query": "cyber threat intelligence analyst fresher"},
    {"id": "noc",              "category": "adjacent", "title": "NOC Engineer",              "query": "NOC engineer fresher"},
    {"id": "tech-support",     "category": "adjacent", "title": "Technical Support Executive","query": "technical support executive IT helpdesk fresher"},
    {"id": "sysadmin",         "category": "adjacent", "title": "System / Network Admin",    "query": "system administrator network administrator fresher"},
    {"id": "qa-engineer",      "category": "adjacent", "title": "QA / Test Engineer",        "query": "QA test engineer fresher"},
    {"id": "it-auditor",       "category": "adjacent", "title": "IT Auditor",                "query": "IT auditor internal audit fresher"},
]

CITIES = ["Delhi", "Bangalore", "Hyderabad", "Chandigarh"]

# Adzuna country code for India
ADZUNA_COUNTRY = "in"
# Jooble's India subdomain
JOOBLE_COUNTRY_SUBDOMAIN = "in"

# How many days old a posting can be and still be pulled in
MAX_DAYS_OLD = 3

# Data file the dashboard reads (served by GitHub Pages from /docs)
DATA_FILE = "docs/data/jobs.json"
