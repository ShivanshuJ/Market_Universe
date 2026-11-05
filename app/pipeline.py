"""The run: parse -> resolve -> context -> people -> jobs -> analyse -> brief.

Every step's output is saved. If the process dies, resume() skips finished steps and continues, and the client
cache means repeated calls never spend credits twice.
"""
import datetime as dt
import os
import re
import time
import uuid

from . import analysis, brief
from .config import settings
from .crustdata import BudgetExceeded, Client, CrustdataError, OutOfCredits

STEPS = ["parse", "resolve", "context", "people", "jobs", "exits", "analyse", "brief"]
RANGE_RANK = {"1": 0, "2-10": 1, "11-50": 2, "51-200": 3, "201-500": 4, "501-1000": 5, "1001-5000": 6,
              "5001-10000": 7, "10001+": 8}
STOP = {"which", "what", "who", "show", "tell", "find", "how", "where", "when", "is", "are", "the", "a", "an", "i",
        "we", "our", "do", "does", "give", "list", "teams", "team", "india", "indian", "please", "can", "could",
        "and", "of", "at", "in", "on", "for", "to", "its", "their"}


class NeedsHuman(Exception):
    """The answer would change the result, so we stop and ask instead of guessing."""


def new_run(store, request, company=None, offline=None):
    run_id = uuid.uuid4().hex[:10]
    s = settings()
    start = (dt.date.today() - dt.timedelta(days=s["window_days"])).isoformat()
    off = s["offline"] if offline is None else offline
    if off:
        start = "2025-11-06"  # the saved fixtures cover roles starting or ending on/after this date
    store.create_run(run_id, request, {"company": company, "offline": off, "window_start": start, "exits": True})
    return run_id


# ------------------------------------------------------------------ steps
def step_parse(ctx):
    req, override = ctx["run"]["request"], ctx["run"]["params"].get("company")
    domain = re.search(r"\b([a-z0-9-]+\.(?:com|in|io|ai|co|org|net|app)(?:\.[a-z]{2})?)\b", req, re.I)
    name = (override or "").strip()
    if not name and not domain:
        words = re.findall(r"[A-Za-z0-9&'.-]+", req)
        cand = []
        for w in words:
            if w[0].isupper() and w.lower() not in STOP:
                cand.append(w.rstrip("'s") if w.endswith("'s") else w)
            elif cand:
                break
        name = " ".join(cand)
    if not name and not domain:
        raise NeedsHuman("Could not tell which company the request is about. Type it in the Company box.")
    return {"company_query": name or domain.group(1), "domain": domain.group(1) if domain and not name else None,
            "goal": "growth and direction of teams", "message": "Company to check: %s" % (name or domain.group(1))}


SUFFIXES = {"inc", "ltd", "limited", "pvt", "private", "llp", "llc", "plc", "corp", "corporation", "company", "co",
            "technologies", "technology", "labs", "solutions", "services", "payments", "india", "pte", "gmbh", "ag"}


def name_variants(name):
    """'Cashfree Payments Pvt Ltd' -> ['Cashfree Payments Pvt', 'Cashfree Payments', 'Cashfree']"""
    toks = re.sub(r"[(),.]", " ", name).split()
    out = []
    while len(toks) > 1 and toks[-1].lower() in SUFFIXES:
        toks = toks[:-1]
        out.append(" ".join(toks))
    return out


def _lookup(cl, body):
    res = cl.call("/company/identify", body)
    cands = []
    for m in ((res[0]["matches"] if res else []) or []):
        bi = m["company_data"].get("basic_info") or {}
        cands.append({"id": m["company_data"]["crustdata_company_id"], "name": bi.get("name"),
                      "domain": bi.get("primary_domain"), "range": bi.get("employee_count_range"),
                      "type": bi.get("company_type"), "score": m.get("confidence_score"),
                      "rank": RANGE_RANK.get(bi.get("employee_count_range") or "", -1)})
    return cands


def _pick(cands, want):
    """Best candidate: name match first, then the biggest company with a website. Returns (best, ties)."""
    pool = [c for c in cands if (c["name"] or "").lower() == want.lower()] or cands
    pool = sorted(pool, key=lambda c: (c["rank"], bool(c["domain"])), reverse=True)
    best = pool[0]
    ties = [c for c in pool if c["rank"] == best["rank"] and c["domain"] and c["id"] != best["id"]]
    return best, ties


def _desc(c):
    return "%s (%s, size %s)" % (c["name"], c["domain"] or "no website", c["range"] or "unknown")


def step_resolve(ctx):
    cl, p = ctx["client"], ctx["out"]["parse"]
    q = p["company_query"]
    if p.get("domain"):
        cands = _lookup(cl, {"domains": [p["domain"]]})
        name = q
    else:
        names = [q] + name_variants(q)
        exact = {n: _lookup(cl, {"names": [n], "exact_match": True}) for n in names}
        hit = [n for n in names if exact[n]]
        cands, name = [], q
        if hit:
            name, cands = hit[0], exact[hit[0]]
            qb, _ = _pick(cands, name)
            for v in names[1:]:  # a shorter form of the name that matches a far bigger company
                if exact[v] and v != name:
                    vb, _ = _pick(exact[v], v)
                    if vb["rank"] >= qb["rank"] + 3:
                        raise NeedsHuman("'%s' matches %s, but '%s' matches %s. Give the website to choose."
                                         % (name, _desc(qb), v, _desc(vb)))
        else:
            for n in names:  # nothing matches exactly: allow near matches, but say so
                cands = _lookup(cl, {"names": [n], "exact_match": False})
                if cands:
                    name = n
                    break
    if not cands:
        raise NeedsHuman("No company matched '%s'. Check the spelling or give its website." % q)
    best, ties = _pick(cands, name)
    if ties:
        raise NeedsHuman("'%s' matches several companies of the same size: %s. Give the website to choose."
                         % (q, ", ".join(_desc(c) for c in [best] + ties[:3])))
    others = [c for c in cands if c["id"] != best["id"]]
    msg = "Resolved '%s' to %s (%s, id %s, size %s)" % (q, best["name"], best["domain"], best["id"], best["range"])
    assumed = None
    if (best["name"] or "").lower() != q.lower() and not p.get("domain"):
        assumed = "'%s' was taken to mean %s (%s); no company has exactly that name. Check this is the right one." % (
            q, best["name"], best["domain"])
        msg += " [assumed]"
    if others:
        msg += "; %d other records share that name and were set aside (smaller or no website)" % len(others)
    return {"company": best, "alternates": others[:6], "assumed": assumed, "message": msg}


def step_context(ctx):
    cid = ctx["out"]["resolve"]["company"]["id"]
    res = ctx["client"].call("/company/enrich", {"crustdata_company_ids": [cid],
                             "fields": ["basic_info", "headcount", "hiring", "people", "web_traffic"]})
    co = analysis.slim_company(res)
    if not co:
        raise CrustdataError(0, "company enrich returned no record for id %s" % cid)
    h = co["headcount"]
    return {"company": co, "message": "Headcount series: %s people as of %s (%d points kept)" % (
        h.get("total"), h.get("last_date"), len(h.get("timeseries") or []))}


def step_people(ctx):
    s, cl = settings(), ctx["client"]
    cid = ctx["out"]["resolve"]["company"]["id"]
    ws = ctx["run"]["params"]["window_start"]
    flt = {"op": "and", "conditions": [
        {"field": "experience.employment_details.current.company_id", "type": "=", "value": cid},
        {"field": "experience.employment_details.current.start_date", "type": "=>", "value": ws}]}
    people, cursor, total, truncated, pages = [], None, None, False, 0
    est_per_person = 0.23
    use_sort = True
    while True:
        body = {"filters": flt, "fields": ["basic_profile", "experience"], "limit": 100}
        if use_sort:
            body["sorts"] = [{"field": "experience.employment_details.start_date", "order": "desc"}]
        if cursor:
            body["cursor"] = cursor
        try:
            d = cl.call("/person/search", body)
        except CrustdataError as e:
            if use_sort and e.status == 400 and not cursor:
                use_sort = False  # sort not allowed here: retry unsorted and say so
                ctx["emit"]("warning", {"message": "Sorting by start date was rejected; pulling unsorted."})
                continue
            raise
        pages += 1
        total = d.get("total_count", total)
        for raw in d.get("profiles") or []:
            sp = analysis.slim_person(raw, cid)
            if sp:
                people.append(sp)
        ctx["emit"]("progress", {"step": "people", "message": "pulled %d of %s people" % (len(people), total)})
        cursor = d.get("next_cursor")
        if not cursor or not d.get("profiles"):
            break
        if len(people) >= s["max_people"]:
            truncated = True
            break
        rem = cl.remaining_budget()
        if rem is not None and rem < 100 * est_per_person:
            truncated = True
            ctx["emit"]("warning", {"message": "Stopping the people pull: not enough credit budget left for another page."})
            break
    return {"people": people, "total_reported": total, "truncated": truncated, "pages": pages,
            "message": "Pulled %d people with a current role starting on/after %s (reported total %s)%s" % (
                len(people), ws, total, " [capped]" if truncated else "")}


def step_jobs(ctx):
    cid = ctx["out"]["resolve"]["company"]["id"]
    flt = {"field": "company.basic_info.crustdata_company_id", "type": "=", "value": cid}
    body = {"filters": flt, "fields": ["job_details", "metadata"], "limit": 100,
            "sorts": [{"field": "metadata.date_added", "order": "desc"}]}
    d = ctx["client"].call("/job/search", body)
    jobs = analysis.slim_jobs(d.get("job_listings"), dt.date.today())
    cats = []
    try:  # counts over ALL postings by the data's own category (free: no records returned)
        agg = ctx["client"].call("/job/search", {"filters": flt, "limit": 0, "aggregations": [
            {"type": "group_by", "field": "job_details.category", "agg": "count", "size": 8}]})
        for a in agg.get("aggregations") or []:
            cats = [{"name": b["key"], "n": b["count"]} for b in a.get("buckets") or []]
    except CrustdataError as e:
        ctx["emit"]("warning", {"message": "Job category counts unavailable: %s" % str(e)[:120]})
    return {"jobs": jobs, "total_reported": d.get("total_count"), "categories": cats,
            "message": "Job search: %d of %s postings kept%s" % (
                len(jobs), d.get("total_count"), "; %d categories counted over all" % len(cats) if cats else "")}


def step_exits(ctx):
    """People whose role at this company ended in the window. Needs a same-entry match (company id AND end date on
    the same role), which the all-roles paths give. Those who still hold a role here are internal moves, not exits."""
    s, cl = settings(), ctx["client"]
    if ctx["run"]["params"].get("exits") is False:
        return {"leavers": None, "truncated": False, "message": "Exits skipped for this run"}
    cid = ctx["out"]["resolve"]["company"]["id"]
    ws = ctx["run"]["params"]["window_start"]
    flt = {"op": "and", "conditions": [
        {"field": "experience.employment_details.company_id", "type": "=", "value": cid},
        {"field": "experience.employment_details.end_date", "type": "=>", "value": ws}]}
    leavers, cursor, total, truncated = [], None, None, False
    while True:
        body = {"filters": flt, "fields": ["basic_profile", "experience"], "limit": 100}
        if cursor:
            body["cursor"] = cursor
        d = cl.call("/person/search", body)
        total = d.get("total_count", total)
        for raw in d.get("profiles") or []:
            sl = analysis.slim_leaver(raw, cid)
            if sl:
                leavers.append(sl)
        ctx["emit"]("progress", {"step": "exits", "message": "pulled %d of %s people with an ended role" % (len(leavers), total)})
        cursor = d.get("next_cursor")
        if not cursor or not d.get("profiles"):
            break
        rem = cl.remaining_budget()
        if len(leavers) >= s["max_exits"] or (rem is not None and rem < 100 * 0.23):
            truncated = True
            ctx["emit"]("warning", {"message": "Stopping the exits pull at %d people (people cap or credit budget)." % len(leavers)})
            break
    return {"leavers": leavers, "truncated": truncated, "total_reported": total,
            "message": "Exits: %d people with a role here that ended on/after %s (reported total %s)%s" % (
                len(leavers), ws, total, " [capped]" if truncated else "")}


def step_analyse(ctx):
    o = ctx["out"]
    ex = o.get("exits") or {}
    a = analysis.analyze(o["people"]["people"], ctx["run"]["params"]["window_start"], dt.date.today(),
                         company=o["context"]["company"], jobs=o["jobs"]["jobs"],
                         pulled_total=o["people"]["total_reported"], truncated=o["people"]["truncated"],
                         leavers=ex.get("leavers"), exits_truncated=bool(ex.get("truncated")))
    c = a["counts"]
    if a.get("open_roles") is not None:
        a["open_roles"]["categories"] = o["jobs"].get("categories") or []
        a["open_roles"]["total_reported"] = o["jobs"].get("total_reported")
    if o["resolve"].get("assumed"):
        a["warnings"].insert(0, o["resolve"]["assumed"])
    return {"analysis": a, "message": "%d external joiners (%d re-recorded roles excluded, %d returning, %d unplaced)" % (
        c["external"], c["relisted"], c["returning"], c["unplaced"])}


def step_brief(ctx):
    s, o = settings(), ctx["out"]
    co = o["resolve"]["company"]
    a = o["analyse"]["analysis"]
    facts = brief.build_facts(co["name"], a, co["id"])
    b, why = (None, "no model key")
    if s["anthropic_key"]:
        b, why = brief.llm_brief(co["name"], a, facts, s["anthropic_key"], s["model"])
    note = None
    if b is None:
        b = brief.template_brief(co["name"], a, facts)
        note = "template brief used (%s)" % why
    return {"brief": b, "facts": facts, "message": "Brief written: %s%s" % (b["generated_by"], " - " + note if note else "")}


FUNCS = {"parse": step_parse, "resolve": step_resolve, "context": step_context, "people": step_people,
         "jobs": step_jobs, "exits": step_exits, "analyse": step_analyse, "brief": step_brief}


# ------------------------------------------------------------------ runner
def execute(store, run_id):
    """Run (or resume) a run. Finished steps are skipped."""
    s = settings()
    run = store.get_run(run_id)
    if not run:
        raise KeyError(run_id)

    def emit(kind, data):
        store.add_event(run_id, kind, data)

    client = Client(s["crustdata_key"], store, run_id=run_id, budget=s["budget"],
                    offline=bool(run["params"].get("offline")),
                    on_warn=lambda m: emit("warning", {"message": m}))
    out = {}
    store.update_run(run_id, status="running", error=None)
    emit("run_start", {"run_id": run_id, "resumed": bool(store.steps(run_id))})
    t0 = time.time()
    for name in STEPS:
        done = store.step_get(run_id, name)
        if done and done["status"] == "done":
            out[name] = done["output"]
            emit("step_skipped", {"step": name, "message": done["output"].get("message", "") + " (resumed, not repeated)"})
            continue
        emit("step_start", {"step": name})
        started = time.time()
        ctx = {"run": store.get_run(run_id), "client": client, "out": out, "emit": emit}
        try:
            result = FUNCS[name](ctx)
        except NeedsHuman as e:
            store.step_put(run_id, name, "needs_input", error=str(e), started=started)
            store.update_run(run_id, status="needs_input", error=str(e))
            emit("needs_input", {"step": name, "message": str(e)})
            return "needs_input"
        except (OutOfCredits, BudgetExceeded, CrustdataError, Exception) as e:  # noqa: BLE001
            store.step_put(run_id, name, "failed", error=str(e), started=started)
            store.update_run(run_id, status="failed", error="%s: %s" % (name, e))
            emit("error", {"step": name, "message": str(e),
                           "hint": "Credits are safe: finished steps and API responses are saved. Resume to continue."})
            return "failed"
        out[name] = result
        store.step_put(run_id, name, "done", output=result, started=started)
        emit("step_done", {"step": name, "message": result.get("message", ""), "seconds": round(time.time() - started, 2)})
        if s["crash_after"] == name:  # demo hook: simulate the process dying right after a step
            emit("crash", {"step": name, "message": "Simulated crash after '%s'. Resume to continue." % name})
            os._exit(3)

    co = out["resolve"]["company"]
    result = {"company": {**co, "alternates": out["resolve"]["alternates"],
                          "enrich": {k: v for k, v in out["context"]["company"].items() if k != "headcount"}},
              "request": run["request"], "window": out["analyse"]["analysis"]["window"],
              "analysis": out["analyse"]["analysis"], "brief": out["brief"]["brief"], "facts": out["brief"]["facts"],
              "warnings": out["analyse"]["analysis"]["warnings"],
              "credits": round(client.spent, 2), "api_calls": client.calls, "cache_hits": client.cache_hits,
              "seconds": round(time.time() - t0, 1), "offline": bool(run["params"].get("offline"))}
    store.update_run(run_id, status="done", result=result)
    emit("done", {"run_id": run_id, "credits": result["credits"], "cache_hits": client.cache_hits})
    return "done"
