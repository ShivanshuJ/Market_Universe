"""Build the offline fixtures from raw API responses saved while exploring.

usage: python scripts/make_fixtures.py RAW_DIR
RAW_DIR must hold: ident_name.json, enrich.json, groww_joiners.json (raw /person/search profiles), jobs.json
(Optionally run scripts/fetch_jobs_fixture.py first to save ~100 job postings into RAW_DIR/jobs_full.json.)
"""
import json
import pathlib
import sys

raw = pathlib.Path(sys.argv[1])
out = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
out.mkdir(exist_ok=True)


def load(n):
    return json.loads((raw / n).read_text(encoding="utf-8"))


def dump(n, obj):
    (out / n).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(n, (out / n).stat().st_size // 1024, "KB")


# company identify: keep the matches, drop long descriptions
ident = load("ident_name.json")
for m in ident[0]["matches"]:
    bi = m["company_data"]["basic_info"]
    for k in ("description", "logo_permalink", "industries"):
        bi.pop(k, None)
dump("groww_identify.json", ident)

# company enrich: drop the heavy by_function timeseries and long text
enrich = load("enrich.json")
cd = enrich[0]["matches"][0]["company_data"]
cd["basic_info"].pop("description", None)
cd["basic_info"].pop("logo_permalink", None)
cd["headcount"].pop("by_function_timeseries", None)
for k in ("by_skill_absolute", "by_skill_percent", "by_region_percent", "by_role_percent",
          "by_role_growth_6m_pct", "by_role_growth_yoy_pct"):
    cd["headcount"].pop(k, None)
cd["hiring"].pop("open_jobs_timeseries", None)
for grp in ("decision_makers", "founders", "cxos"):
    cd["people"][grp] = [{"crustdata_person_id": x.get("crustdata_person_id"),
                          "basic_profile": {"name": x["basic_profile"].get("name"),
                                            "current_title": x["basic_profile"].get("current_title")}}
                         for x in cd["people"].get(grp, [])][:8]
cd.pop("funding", None)
dump("groww_enrich.json", enrich)

# people: keep just what slim_person reads
people = []
for p in load("groww_joiners.json"):
    ed = p["experience"]["employment_details"]
    keep = ("crustdata_company_id", "name", "title", "start_date", "end_date", "seniority_level")
    people.append({
        "crustdata_person_id": p["crustdata_person_id"],
        "basic_profile": {"name": p["basic_profile"].get("name"),
                          "normalized_title": p["basic_profile"].get("normalized_title")},
        "experience": {"employment_details": {
            "current": [{k: r.get(k) for k in keep} for r in ed.get("current", [])],
            "past": [{k: r.get(k) for k in keep} for r in ed.get("past", [])]}}})
dump("groww_people.json", people)

jobs_full = raw / "jobs_full.json"
jobs = json.loads(jobs_full.read_text(encoding="utf-8")) if jobs_full.exists() else load("jobs.json")["job_listings"]
dump("groww_jobs.json", jobs)
