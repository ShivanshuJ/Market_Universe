"""Experiment: which senior seats opened in the last year and were never backfilled or advertised?
usage: python scripts/vacancy_probe.py COMPANY_ID WINDOW_START"""
import datetime as dt
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
from app import analysis
from app.config import settings
from app.crustdata import Client
from app.store import Store

cid, ws = int(sys.argv[1]), sys.argv[2]
s = settings()
cl = Client(s["crustdata_key"], Store(s["db"]), budget=60)
SENIOR = ["CXO", "Vice President", "Director"]
CUR = "experience.employment_details.current."

SEATS = [  # ordered: first match wins
    ("CEO", r"\bceo\b|chief executive|managing director|\bfounder\b"),
    ("CFO / Finance head", r"\bcfo\b|chief financial|head of finance|vp.? finance|finance head|financial controller|fp&a"),
    ("CTO / Engineering head", r"\bcto\b|chief technology|head of engineering|vp.? engineering|engineering head|director.? engineering|vice president.? engineering|software engineering"),
    ("CPO / Product head", r"\bcpo\b|chief product|head of product|vp.? product|product head|director.? product|vice president.? product"),
    ("CMO / Marketing head", r"\bcmo\b|chief marketing|head of marketing|vp.? marketing|marketing head|director.? marketing|growth"),
    ("COO / Operations head", r"\bcoo\b|chief operating|head of operations|vp.? operations|operations head|director.? operations"),
    ("Sales / Revenue head", r"\bcro\b|chief revenue|head of sales|vp.? sales|sales head|director.? sales|business head|revenue|enterprise sales|business development"),
    ("Data / AI head", r"head of data|data science|chief data|\bcdo\b|machine learning|\bai\b|analytics"),
    ("People / HR head", r"\bchro\b|chief people|head of people|\bhr\b|human resources|talent|people operations"),
    ("Legal / Compliance / Risk head", r"legal|compliance|general counsel|risk|\bgrc\b|audit"),
    ("Customer / Support head", r"customer success|customer support|customer experience|head of support|customer service"),
    ("Security / IT head", r"\bciso\b|security|information technology|head of it|\bit head\b|infrastructure"),
    ("Strategy / Partnerships head", r"strategy|partnership|corporate development|alliances"),
    ("Design head", r"\bdesign\b"),
]


def seat(title):
    t = (title or "").lower()
    for name, rx in SEATS:
        if re.search(rx, t):
            return name
    return None


def pull(flt, slim):
    out, cursor = [], None
    while True:
        body = {"filters": flt, "fields": ["basic_profile", "experience"], "limit": 100}
        if cursor:
            body["cursor"] = cursor
        d = cl.call("/person/search", body)
        for p in d.get("profiles") or []:
            x = slim(p)
            if x:
                out.append(x)
        cursor = d.get("next_cursor")
        if not cursor or not d.get("profiles"):
            return out


# 1) senior leavers (seat ended in the window, person no longer here)
ex_flt = {"op": "and", "conditions": [
    {"field": "experience.employment_details.company_id", "type": "=", "value": cid},
    {"field": "experience.employment_details.end_date", "type": "=>", "value": ws}]}
leavers = [l for l in pull(ex_flt, lambda p: analysis.slim_leaver(p, cid))
           if not l["still_here"] and l["seniority"] in SENIOR and l["end"] >= ws]

# 2) everyone senior who works here now
cur_flt = {"op": "and", "conditions": [
    {"field": CUR + "company_id", "type": "=", "value": cid},
    {"field": CUR + "seniority_level", "type": "in", "value": SENIOR}]}
now_senior = pull(cur_flt, lambda p: analysis.slim_person(p, cid))
print("senior leavers in window: %d | senior people now: %d" % (len(leavers), len(now_senior)))

# 3) classify each leaver's seat
rows = []
for l in sorted(leavers, key=lambda x: x["end"], reverse=True):
    sname = seat(l["title"])
    if not sname:
        continue
    end = dt.date.fromisoformat(l["end"])
    successors = [p for p in now_senior if seat(p["title"]) == sname and p["start"] and
                  dt.date.fromisoformat(p["start"]) >= end - dt.timedelta(days=90)]
    peers = [p for p in now_senior if seat(p["title"]) == sname and p["start"] and
             dt.date.fromisoformat(p["start"]) < end - dt.timedelta(days=90)]
    rows.append({"seat": sname, "left": l, "successors": successors, "peers": peers})

# 4) is the seat publicly advertised? (job search by seat words, senior titles only, since the leaver left)
SEARCH_WORDS = {"CFO / Finance head": "finance", "CTO / Engineering head": "engineering", "CPO / Product head": "product",
                "CMO / Marketing head": "marketing", "COO / Operations head": "operations", "Sales / Revenue head": "sales",
                "Data / AI head": "data", "People / HR head": "people", "Legal / Compliance / Risk head": "compliance",
                "Customer / Support head": "customer", "Security / IT head": "security", "Strategy / Partnerships head": "strategy",
                "Design head": "design", "CEO": "chief executive"}
senior_rx = re.compile(r"\b(head|director|vp|vice president|chief|cxo|gm|general manager|lead)\b", re.I)
jobs_cache = {}


def advertised(sname, since):
    w = SEARCH_WORDS.get(sname)
    if not w:
        return []
    if w not in jobs_cache:
        d = cl.call("/job/search", {"filters": {"op": "and", "conditions": [
            {"field": "company.basic_info.crustdata_company_id", "type": "=", "value": cid},
            {"field": "job_details.title", "type": "(.)", "value": w}]},
            "fields": ["job_details", "metadata"], "limit": 100})
        jobs_cache[w] = d.get("job_listings") or []
    return [j for j in jobs_cache[w] if senior_rx.search(j["job_details"]["title"] or "")
            and (j["metadata"]["date_added"] or "")[:10] >= since]


out = {"backfilled": [], "covered": [], "posted": [], "quiet": []}
for r in rows:
    l = r["left"]
    if r["successors"]:
        kind = "backfilled"
    elif r["peers"] and l["seniority"] != "CXO":
        kind = "covered"
    else:
        ads = advertised(r["seat"], l["end"])
        kind = "posted" if ads else "quiet"
        r["ads"] = [a["job_details"]["title"] for a in ads][:3]
    out[kind].append(r)
print("RESULT:", {k: len(v) for k, v in out.items()})
for kind in ("quiet", "posted"):
    print("\n== %s" % kind.upper())
    for r in out[kind][:12]:
        l = r["left"]
        days = (dt.date.today() - dt.date.fromisoformat(l["end"])).days
        print("  %-30s left %s (%3dd ago) | %s | %s -> now %s %s" % (
            r["seat"], l["end"], days, l["seniority"], l["title"][:42], (l["dest"] or {}).get("name") or "no current role",
            ("| ads: %s" % r.get("ads")) if r.get("ads") else ""))
print("\ncredits spent this script: %.2f" % cl.spent)
