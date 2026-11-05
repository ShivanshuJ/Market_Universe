"""Offline backend: answers the same endpoints from saved fixtures (demo fallback, no network, no credits)."""
import json

from .config import ROOT

FIX = ROOT / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _page(items, body, key):
    limit = int(body.get("limit") or 100)
    off = int(body.get("cursor") or 0)
    chunk = items[off:off + limit]
    nxt = str(off + limit) if off + limit < len(items) else None
    return {key: chunk, "next_cursor": nxt, "total_count": len(items)}


def answer(path, body):
    if path == "/company/identify":
        q = json.dumps(body).lower()
        if "groww" in q:
            ident = _load("groww_identify.json")
            if body.get("domains"):
                ident = [{**ident[0], "matched_on": body["domains"][0], "match_type": "domain",
                          "matches": [m for m in ident[0]["matches"]
                                      if m["company_data"]["basic_info"].get("primary_domain") == body["domains"][0]]}]
            return ident
        key = (body.get("names") or body.get("domains") or [""])[0]
        return [{"matched_on": key, "match_type": "name", "matches": []}]
    if path == "/company/enrich":
        return _load("groww_enrich.json")
    if path == "/person/search":
        if "employment_details.end_date" in json.dumps(body.get("filters")):
            name = "groww_exits.json"
            if not (FIX / name).exists():
                return {"profiles": [], "next_cursor": None, "total_count": 0}
            return _page(_load(name), body, "profiles")
        return _page(_load("groww_people.json"), body, "profiles")
    if path == "/job/search":
        return _page(_load("groww_jobs.json"), body, "job_listings")
    raise RuntimeError("offline fixtures have no answer for " + path)
