"""Market view: give it your company; it finds the rivals, the companies heading where you are heading, and the ones that fell.

  Present  rivals found by meaning and size, each with how it is performing now
  Future   companies outside your rivals that are building toward what YOU are building (read from your own hiring)
  Past     companies that were big and are much smaller now, with the shape of the fall and linked reports

Everything is derived from Crustdata data. Causes of a fall are only ever shown as "reported by <link>"; we never guess them.
"""
import datetime as dt
import math
import re
import time
import uuid

from . import pipeline, thesis as thesismod
from .config import settings
from .crustdata import BudgetExceeded, Client, CrustdataError, OutOfCredits

# the page's definition of "fell": stated on screen as well
FALL_MIN_PEAK = 300      # people at the peak
FALL_MIN_DROP = 0.40     # share of the peak that is gone
FUNDED_MIN_USD = 40_000_000
GENERIC_THEMES = {"General & Regional Management", "Software Engineering", "Product Management", "Vice President Leadership",
                  "Executive Leadership", "Project & Program Management", "Cloud & DevOps Engineering", "Mobile Development"}
COUNTRY_NAMES = {"IND": "India", "USA": "United States", "GBR": "United Kingdom", "SGP": "Singapore", "ARE": "United Arab Emirates",
                 "CAN": "Canada", "AUS": "Australia", "DEU": "Germany", "FRA": "France", "NLD": "Netherlands"}
COUNTRY_CODES = {"IND": "IN", "USA": "US", "GBR": "GB", "SGP": "SG", "ARE": "AE", "CAN": "CA", "AUS": "AU", "DEU": "DE", "FRA": "FR", "NLD": "NL"}
THEME_QUERIES = {
    "Wealth & Relationship Management": "wealth management and private banking advisory",
    "Machine Learning & AI Engineering": "machine learning and artificial intelligence products",
    "Channel & Partner Sales": "channel partnerships and distribution platform",
    "Credit & Debt Management": "credit, lending and debt collection",
    "Marketing Strategy & Planning": "growth marketing and brand",
    "Data Science & Analytics": "data science and analytics platform",
    "Industry & Specialist Sales": "enterprise and industry specialist sales",
    "Quantitative & Applied Analytics": "quantitative research and trading",
}
PLACEHOLDER_NAMES = pipeline.PLACEHOLDERS


# ------------------------------------------------------------------ pure helpers (tested)
def series_stats(ts):
    """Peak, now, the steepest half-year fall and a small sparkline, from the weekly headcount series."""
    vals = [(t["date"], t["employee_count"]) for t in (ts or []) if t.get("employee_count") is not None]
    if len(vals) < 8:
        return None
    peak = max(vals, key=lambda x: x[1])
    now = vals[-1]

    def growth(weeks):
        if len(vals) <= weeks or not vals[-1 - weeks][1]:
            return None
        return round(100.0 * (vals[-1][1] / vals[-1 - weeks][1] - 1), 1)

    w, best = 26, (0.0, None, None, None, None)
    for i in range(len(vals) - w):
        a, b = vals[i][1], vals[i + w][1]
        if a >= 20 and 1 - b / a > best[0]:
            best = (1 - b / a, vals[i][0], vals[i + w][0], a, b)
    step = max(1, len(vals) // 48)
    return {"peak": peak[1], "peak_date": peak[0], "now": now[1], "now_date": now[0],
            "drop": round(1 - now[1] / peak[1], 3) if peak[1] else 0.0, "g12": growth(52), "g6": growth(26),
            "steepest": {"drop": round(best[0], 3), "from": best[1], "to": best[2], "from_n": best[3], "to_n": best[4]} if best[1] else None,
            "first": vals[0][0], "spark": [v for _, v in vals[::step]][-48:]}


def perf_verdict(g12):
    if g12 is None:
        return "unknown"
    return ("surging" if g12 >= 30 else "growing" if g12 >= 8 else "steady" if g12 > -8 else "shrinking" if g12 > -25 else "contracting")


def size_closeness(total, mine):
    if not total or not mine:
        return 0.0
    return max(0.0, 1 - abs(math.log(total / mine)) / math.log(4))


def rival_score(position, n, total, mine):
    """Meaning of the company (rank from semantic search) counts a little more than size closeness."""
    return round(0.6 * (1 - position / max(n, 1)) + 0.4 * size_closeness(total, mine), 4)


def pick_themes(theses, limit=2):
    """The strategies we are pursuing, read from our own hiring: the standing-out teams, minus generic ones."""
    out = [t for t in (theses or []) if t["theme"] not in GENERIC_THEMES][:limit]
    return out or (theses or [])[:1]


def theme_query(theme, industry):
    return THEME_QUERIES.get(theme) or ("%s %s" % (theme.lower().replace("&", "and"), industry or "")).strip()


def future_score(staff, headcount, posts, g12, position, n):
    share = (staff / headcount) if headcount else 0
    return round(0.5 * min(share / 0.15, 1) + 0.25 * min(posts / 5, 1) + 0.15 * min(max(g12 or 0, 0) / 50, 1) + 0.10 * (1 - position / max(n, 1)), 4)


def country_filter_value(code):
    return COUNTRY_NAMES.get(code, code)


def related(name, text):
    """Does a search result talk about this company? First distinctive word of its name must appear."""
    toks = [t for t in re.findall(r"[a-z0-9]{3,}", (name or "").lower()) if t not in {"the", "pvt", "ltd", "private", "limited", "inc", "technologies", "india"}]
    return bool(toks) and toks[0] in (text or "").lower()


# ------------------------------------------------------------------ steps (each takes a client so tests can stand in)
def company_profile(cl, cid):
    r = cl.call("/company/enrich", {"crustdata_company_ids": [cid], "fields": [
        "basic_info", "locations.country", "taxonomy.professional_network_industry", "headcount.total", "headcount.timeseries", "headcount.growth_percent"]})
    d = r[0]["matches"][0]["company_data"]
    bi, hc = d.get("basic_info") or {}, d.get("headcount") or {}
    st = series_stats(hc.get("timeseries"))
    total = hc.get("total") or (st or {}).get("now") or 0
    return {"id": cid, "name": bi.get("name"), "domain": bi.get("primary_domain"), "range": bi.get("employee_count_range"),
            "description": (bi.get("description") or "")[:600], "industry": (d.get("taxonomy") or {}).get("professional_network_industry"),
            "country": (d.get("locations") or {}).get("country"), "headcount": total, "stats": st}


PERF_FIELDS = ["basic_info.name", "basic_info.primary_domain", "basic_info.year_founded", "basic_info.company_type",
               "headcount.total", "headcount.timeseries", "headcount.growth_percent",
               "funding.last_round_type", "funding.last_fundraise_date", "funding.total_investment_usd",
               "employee_reviews.overall_rating", "followers.yoy_percent", "taxonomy.professional_network_industry", "revenue.acquisition_status"]


def perf_card(cd, mine=None):
    bi, hc, fu = cd.get("basic_info") or {}, cd.get("headcount") or {}, cd.get("funding") or {}
    st = series_stats(hc.get("timeseries"))
    g12 = (st or {}).get("g12")
    if g12 is None:
        g12 = (hc.get("growth_percent") or {}).get("yoy")
    rv = ((cd.get("employee_reviews") or {}).get("overall_rating") or {})
    total = hc.get("total") or (st or {}).get("now")
    flags = []
    if st and (dt.date.today() - dt.date.fromisoformat(st["now_date"][:10])).days > 30:
        flags.append("headcount series is %d days old" % (dt.date.today() - dt.date.fromisoformat(st["now_date"][:10])).days)
    if not st:
        flags.append("no usable headcount history")
    return {"id": cd.get("crustdata_company_id"), "name": bi.get("name"), "domain": bi.get("primary_domain"), "headcount": total,
            "founded": bi.get("year_founded"), "g12": g12, "g6": (st or {}).get("g6"), "verdict": perf_verdict(g12),
            "spark": (st or {}).get("spark") or [], "rating": rv.get("rating"), "reviews": rv.get("total_count"),
            "followers_yoy": (cd.get("followers") or {}).get("yoy_percent"), "last_round": fu.get("last_round_type"),
            "last_round_date": fu.get("last_fundraise_date"), "raised_usd": fu.get("total_investment_usd"),
            "industry": (cd.get("taxonomy") or {}).get("professional_network_industry"), "flags": flags,
            "acquired": ((cd.get("revenue") or {}).get("acquisition_status") == "acquired")}


def enrich_many(cl, ids, fields):
    out = {}
    for i in range(0, len(ids), 20):
        r = cl.call("/company/enrich", {"crustdata_company_ids": ids[i:i + 20], "fields": fields})
        for e in r or []:
            for m in e.get("matches", [])[:1]:
                out[m["company_data"]["crustdata_company_id"]] = m["company_data"]
    return out


def find_rivals(cl, me, limit=8):
    mine = me["headcount"] or 500
    q = ("%s. %s" % (me.get("industry") or "", me.get("description") or "")).strip()
    cands, pos = [], {}
    for lo, hi in ((0.25, 4), (0.1, 10)):  # widen once if the first band is thin
        conds = [{"field": "headcount.total", "type": "=>", "value": int(mine * lo)}, {"field": "headcount.total", "type": "=<", "value": int(mine * hi)}]
        if me.get("country"):
            conds.insert(0, {"field": "locations.country", "type": "=", "value": country_filter_value(me["country"])})
        r = cl.call("/company/search", {"search": {"query": q, "mode": "hybrid"}, "filters": {"op": "and", "conditions": conds},
                                        "fields": ["basic_info.name", "basic_info.primary_domain", "headcount.total"], "limit": 30})
        cands = [c for c in (r or {}).get("companies", []) if c["crustdata_company_id"] != me["id"]
                 and (c["basic_info"].get("name") or "").strip().lower() not in PLACEHOLDER_NAMES]
        if len(cands) >= 5:
            break
    n = len(cands)
    for i, c in enumerate(cands):
        pos[c["crustdata_company_id"]] = i
    data = enrich_many(cl, [c["crustdata_company_id"] for c in cands[:20]] + [me["id"]], PERF_FIELDS)
    cards = []
    for c in cands[:20]:
        cd = data.get(c["crustdata_company_id"])
        if not cd:
            continue
        card = perf_card(cd)
        if not card["headcount"]:
            continue
        card["score"] = rival_score(pos[c["crustdata_company_id"]], n, card["headcount"], mine)
        cards.append(card)
    cards.sort(key=lambda x: -x["score"])
    cards = cards[:limit]
    for x in cards:  # open postings: job search total is more reliable than the company record's field
        try:
            x["open_roles"] = cl.call("/job/search", {"filters": {"field": "company.basic_info.crustdata_company_id", "type": "=", "value": x["id"]},
                                                      "fields": ["job_details"], "limit": 1}).get("total_count")
        except CrustdataError:
            x["open_roles"] = None
    return cards, (perf_card(data[me["id"]]) if me["id"] in data else None)


def find_future(cl, me, themes, exclude_ids, per_theme=3, total=6):
    """Companies outside the rivals that are building what we are building. Evidence: team titles, open roles, growth."""
    found = {}
    for th in themes:
        kw = thesismod.keywords(th["theme"])
        q = theme_query(th["theme"], me.get("industry"))
        conds = [{"field": "headcount.total", "type": "=<", "value": max(int((me["headcount"] or 500) * 1.0), 50)},
                 {"field": "headcount.total", "type": "=>", "value": 15}]
        if me.get("country"):
            conds.insert(0, {"field": "locations.country", "type": "=", "value": country_filter_value(me["country"])})
        r = cl.call("/company/search", {"search": {"query": q, "mode": "hybrid"}, "filters": {"op": "and", "conditions": conds},
                                        "fields": ["basic_info.name", "basic_info.primary_domain", "basic_info.year_founded", "headcount.total", "headcount.growth_percent",
                                                   "funding.last_round_type", "funding.total_investment_usd"], "limit": 25})
        cs = [c for c in (r or {}).get("companies", []) if c["crustdata_company_id"] not in exclude_ids and c["crustdata_company_id"] != me["id"]
              and (c["basic_info"].get("name") or "").strip().lower() not in PLACEHOLDER_NAMES]
        scored = []
        for i, c in enumerate(cs):
            cid, hc = c["crustdata_company_id"], (c.get("headcount") or {})
            staff = cl.call("/person/search", {"filters": {"op": "and", "conditions": [
                {"field": "experience.employment_details.current.company_id", "type": "=", "value": cid},
                {"field": "experience.employment_details.current.title", "type": "(.)", "value": kw[0]}]},
                "fields": ["basic_profile"], "limit": 1}).get("total_count", 0)
            posts = cl.call("/job/search", {"filters": {"op": "and", "conditions": [
                {"field": "company.basic_info.crustdata_company_id", "type": "=", "value": cid},
                {"field": "job_details.title", "type": "(.)", "value": kw[0]}]},
                "fields": ["job_details"], "limit": 1}).get("total_count", 0)
            if staff < 3 and posts < 2:
                continue
            g12 = (hc.get("growth_percent") or {}).get("12m")
            scored.append({"id": cid, "name": c["basic_info"].get("name"), "domain": c["basic_info"].get("primary_domain"),
                           "founded": c["basic_info"].get("year_founded"), "headcount": hc.get("total"), "g12": g12,
                           "theme": th["theme"], "theme_query": q, "keyword": kw[0], "staff": staff, "posts": posts,
                           "share": round(staff / hc["total"], 3) if hc.get("total") else None,
                           "funding": (c.get("funding") or {}).get("last_round_type"), "raised_usd": (c.get("funding") or {}).get("total_investment_usd"),
                           "score": future_score(staff, hc.get("total") or 0, posts, g12, i, len(cs))})
        scored.sort(key=lambda x: -x["score"])
        for x in scored[:per_theme]:
            found.setdefault(x["id"], x)
    out = sorted(found.values(), key=lambda x: -x["score"])[:total]
    mine = me["headcount"] or 0
    for x in out:
        why = []
        if mine and x["headcount"]:
            why.append("%.0fx smaller than you" % (mine / x["headcount"]) if mine / x["headcount"] >= 1.5 else "about your size")
        if x["founded"] and x["founded"] >= dt.date.today().year - 8:
            why.append("founded %s" % x["founded"])
        x["why_not_rival"] = ", ".join(why) or "not matched to your market by description"
    return out


def find_fallen(cl, me, limit=6):
    """Once big, much smaller now. Candidates: well funded and shrinking; confirmed from the weekly series (peak vs now)."""
    conds = [{"field": "funding.total_investment_usd", "type": "=>", "value": FUNDED_MIN_USD},
             {"field": "headcount.total", "type": "=<", "value": 1500},
             {"field": "headcount.growth_percent.12m", "type": "=<", "value": -10}]
    if me.get("country"):
        conds.insert(0, {"field": "locations.country", "type": "=", "value": country_filter_value(me["country"])})
    r = cl.call("/company/search", {"search": {"query": me.get("industry") or me.get("description") or "company", "mode": "hybrid"},
                                    "filters": {"op": "and", "conditions": conds},
                                    "fields": ["basic_info.name", "basic_info.primary_domain", "headcount.total", "funding.total_investment_usd"], "limit": 40})
    ids = [c["crustdata_company_id"] for c in (r or {}).get("companies", []) if c["crustdata_company_id"] != me["id"]]
    data = enrich_many(cl, ids, ["basic_info.name", "basic_info.primary_domain", "headcount.timeseries", "funding.total_investment_usd",
                                 "taxonomy.professional_network_industry", "revenue.acquisition_status"])
    out = []
    for cid, d in data.items():
        st = series_stats((d.get("headcount") or {}).get("timeseries"))
        if not st or st["peak"] < FALL_MIN_PEAK or st["drop"] < FALL_MIN_DROP:
            continue
        ind = (d.get("taxonomy") or {}).get("professional_network_industry")
        out.append({"id": cid, "name": d["basic_info"].get("name"), "domain": d["basic_info"].get("primary_domain"), "stats": st,
                    "raised_usd": (d.get("funding") or {}).get("total_investment_usd"), "industry": ind,
                    "same_industry": bool(ind and ind == me.get("industry")),
                    "acquired": (d.get("revenue") or {}).get("acquisition_status") == "acquired"})
    out.sort(key=lambda x: (not x["same_industry"], -x["stats"]["peak"]))
    out = out[:limit]
    code = COUNTRY_CODES.get(me.get("country"))
    for x in out:
        x["coverage"] = incident_links(cl, x["name"], code)
    return out


def incident_links(cl, name, country_code=None, keep=3):
    """What the web reports about the fall, as links only. We never summarise a cause ourselves."""
    body = {"query": "%s layoffs decline shutdown reasons" % name, "sources": ["news", "web"]}
    if country_code:
        body["location"] = country_code
    try:
        res = cl.call("/web/search/live", body).get("results") or []
    except CrustdataError:
        return []
    hits = [r for r in res if related(name, (r.get("title") or "") + " " + (r.get("snippet") or ""))]
    return [{"title": r.get("title"), "snippet": (r.get("snippet") or "")[:240], "url": r.get("url")} for r in hits[:keep]]


# ------------------------------------------------------------------ the run
STEPS = ["resolve", "self", "rivals", "future", "past"]


def new_market_run(store, company):
    run_id = uuid.uuid4().hex[:10]
    store.create_run(run_id, "Market view for %s" % company, {"kind": "market", "company": company})
    return run_id


def execute_market(store, run_id, client=None, analyse_self=None):
    s = settings()
    run = store.get_run(run_id)
    emit = lambda kind, data: store.add_event(run_id, kind, data)
    cl = client or Client(s["crustdata_key"], store, run_id=run_id, budget=s["market_budget"], offline=False,
                          on_warn=lambda m: emit("warning", {"message": m}))
    analyse_self = analyse_self or _analyse_self
    out, t0 = {}, time.time()
    store.update_run(run_id, status="running", error=None)
    emit("run_start", {"run_id": run_id, "resumed": bool(store.steps(run_id))})

    def me_of(o):
        return o["resolve"]["me"]

    def s_resolve():
        ctx = {"run": {"request": run["params"]["company"], "params": {"company": run["params"]["company"]}}, "client": cl, "out": {}, "emit": emit}
        ctx["out"]["parse"] = pipeline.step_parse(ctx)
        res = pipeline.step_resolve(ctx)
        me = company_profile(cl, res["company"]["id"])
        return {"me": me, "assumed": res.get("assumed"), "message": "%s: %s, about %s people%s" % (
            me["name"], me.get("industry") or "industry unknown", format(me["headcount"], ","), " [assumed match]" if res.get("assumed") else "")}

    def s_self():
        me = me_of(out)
        info = analyse_self(store, me["name"], emit)
        themes = pick_themes(info["theses"])
        return {"self": info, "themes": themes, "message": ("What you are doing now: %s" % ", ".join("%s (%s)" % (t["theme"], t["confidence"]) for t in themes))
                if themes else "Not enough profile data to say what you are building"}

    def s_rivals():
        rivals, mine = find_rivals(cl, me_of(out))
        return {"rivals": rivals, "mine": mine, "message": "%d rivals found: %s" % (len(rivals), ", ".join(r["name"] for r in rivals[:5]))}

    def s_future():
        themes = out["self"]["themes"]
        ids = {r["id"] for r in out["rivals"]["rivals"]}
        fut = find_future(cl, me_of(out), themes, ids) if themes else []
        return {"future": fut, "message": "%d companies heading where you are heading" % len(fut)}

    def s_past():
        fallen = find_fallen(cl, me_of(out))
        return {"fallen": fallen, "message": "%d companies that fell by %d%% or more from a peak of %d+ people" % (len(fallen), round(100 * FALL_MIN_DROP), FALL_MIN_PEAK)}

    funcs = {"resolve": s_resolve, "self": s_self, "rivals": s_rivals, "future": s_future, "past": s_past}
    for name in STEPS:
        done = store.step_get(run_id, name)
        if done and done["status"] == "done":
            out[name] = done["output"]
            emit("step_skipped", {"step": name, "message": (done["output"].get("message") or "") + " (resumed, not repeated)"})
            continue
        emit("step_start", {"step": name})
        started = time.time()
        try:
            result = funcs[name]()
        except pipeline.NeedsHuman as e:
            store.step_put(run_id, name, "needs_input", error=str(e), started=started)
            store.update_run(run_id, status="needs_input", error=str(e))
            emit("needs_input", {"step": name, "message": str(e)})
            return "needs_input"
        except (OutOfCredits, BudgetExceeded, CrustdataError, Exception) as e:  # noqa: BLE001
            store.step_put(run_id, name, "failed", error=str(e), started=started)
            store.update_run(run_id, status="failed", error="%s: %s" % (name, e))
            emit("error", {"step": name, "message": str(e), "hint": "Finished steps and API responses are saved. Resume to continue."})
            return "failed"
        out[name] = result
        store.step_put(run_id, name, "done", output=result, started=started)
        emit("step_done", {"step": name, "message": result.get("message", ""), "seconds": round(time.time() - started, 2)})

    me = me_of(out)
    result = {"kind": "market", "company": me, "assumed": out["resolve"].get("assumed"),
              "self": {"theses": out["self"]["self"]["theses"], "run_id": out["self"]["self"]["run_id"], "court": out["self"]["self"].get("court"),
                       "themes": out["self"]["themes"]},
              "present": {"rivals": out["rivals"]["rivals"], "me": out["rivals"]["mine"]},
              "future": {"companies": out["future"]["future"]},
              "past": {"companies": out["past"]["fallen"], "criteria": {"min_peak": FALL_MIN_PEAK, "min_drop": FALL_MIN_DROP, "min_raised_usd": FUNDED_MIN_USD}},
              "credits": round(cl.spent, 2), "seconds": round(time.time() - t0, 1)}
    store.update_run(run_id, status="done", result=result)
    emit("done", {"run_id": run_id, "credits": result["credits"]})
    return "done"


def _analyse_self(store, name, emit):
    """The existing company analysis, run on you: it tells us what you are building and how trustworthy that read is."""
    emit("progress", {"step": "self", "message": "reading %s's own hiring (people-level)" % name})
    rid = pipeline.new_run(store, "Which teams at %s are growing fastest?" % name, company=name)
    status = pipeline.execute(store, rid)
    if status != "done":
        raise CrustdataError(0, "the analysis of %s ended with status %s" % (name, status))
    res = store.get_run(rid)["result"]
    return {"run_id": rid, "theses": (res.get("thesis") or {}).get("theses") or [], "court": (res.get("court") or {}).get("summary")}


# ------------------------------------------------------------------ company dossier (loaded when a card is opened)
DOSSIER_FIELDS = ["basic_info", "locations", "taxonomy.categories", "taxonomy.professional_network_industry", "headcount.total",
                  "headcount.growth_absolute", "headcount.growth_percent", "headcount.by_role_percent", "headcount.by_role_growth_6m_pct",
                  "headcount.by_region_percent", "funding", "employee_reviews", "news", "revenue.estimated", "revenue.acquisition_status",
                  "headcount.timeseries", "followers"]
RATING_LABELS = [("work_life_balance_rating", "Work-life balance"), ("culture_and_values_rating", "Culture"), ("senior_management_rating", "Senior management"),
                 ("compensation_and_benefits_rating", "Pay and benefits"), ("career_opportunities_rating", "Career growth")]


def _top(d, n, key_min=0.0):
    return sorted(((k, v) for k, v in (d or {}).items() if v is not None and v > key_min), key=lambda kv: -kv[1])[:n]


def build_dossier(cd, jobs_total, job_titles, full=False):
    """Everything worth knowing about one company in a screen, plus plain 'what this means' lines computed by rules."""
    bi, hc, fu = cd.get("basic_info") or {}, cd.get("headcount") or {}, cd.get("funding") or {}
    loc, rv, rev = cd.get("locations") or {}, cd.get("employee_reviews") or {}, cd.get("revenue") or {}
    st = series_stats(hc.get("timeseries"))
    ga, gp = hc.get("growth_absolute") or {}, hc.get("growth_percent") or {}
    role_pct, role_g = hc.get("by_role_percent") or {}, hc.get("by_role_growth_6m_pct") or {}
    teams = [{"name": k, "share": round(v, 1), "g6": round(role_g[k], 1) if role_g.get(k) is not None else None} for k, v in _top(role_pct, 10 if full else 5)]
    big = {k: v for k, v in role_g.items() if v is not None and (role_pct.get(k) or 0) >= 2}  # ignore tiny teams for "fastest"
    fastest = max(big.items(), key=lambda kv: kv[1]) if big else None
    # regions: keep city-level entries only (drop country/state roll-ups that double count)
    regions = [(k, v) for k, v in _top(hc.get("by_region_percent"), 12) if "," not in k and "Greater" not in k and "Area" not in k and "Region" not in k and k != "India"][:8 if full else 4]
    ratings = [{"label": lab, "value": rv[k]} for k, lab in RATING_LABELS if rv.get(k)]
    overall = (rv.get("overall_rating") or {})
    rounds = []
    for m in (fu.get("milestones") or [])[:10 if full else 5]:
        if m.get("is_fund"):
            continue
        rounds.append({"date": (m.get("date") or "")[:7], "type": (m.get("round_type") or "").replace("_", " "), "amount_usd": m.get("amount_usd"),
                       "investors": (m.get("investors") or "")[:90]})
    news = [{"title": n.get("article_title"), "publisher": n.get("article_publisher_name"), "date": n.get("article_publish_date"), "url": n.get("article_url")}
            for n in sorted((cd.get("news") or []), key=lambda n: n.get("article_publish_date") or "", reverse=True)[:10 if full else 5] if n.get("article_title")]
    est = (rev.get("estimated") or {})
    reads = []
    if teams:
        r = "Biggest team: %s (%s%% of staff)" % (teams[0]["name"], teams[0]["share"])
        if fastest:
            r += "; fastest-growing team of size: %s (%+.0f%% in 6 months)" % (fastest[0], fastest[1])
        reads.append(r + ".")
    if ratings and len(ratings) >= 3:
        lo, hi = min(ratings, key=lambda x: x["value"]), max(ratings, key=lambda x: x["value"])
        if hi["value"] - lo["value"] >= 1.0:
            reads.append("Employees rate %s lowest (%.1f) and %s highest (%.1f): a gap worth watching for retention." % (lo["label"].lower(), lo["value"], hi["label"].lower(), hi["value"]))
    if rounds and rounds[0]["amount_usd"]:
        reads.append("Latest round: $%dM %s in %s%s." % (round(rounds[0]["amount_usd"] / 1e6), rounds[0]["type"], rounds[0]["date"], (" from " + rounds[0]["investors"]) if rounds[0]["investors"] else ""))
    if st and st["drop"] >= 0.25:
        reads.append("Headcount is %d%% below its peak of %s (%s)." % (round(100 * st["drop"]), format(st["peak"], ","), st["peak_date"][:7]))
    if jobs_total is not None and hc.get("total"):
        reads.append("%s open roles is %.0f%% of current headcount." % (format(jobs_total, ","), 100.0 * jobs_total / hc["total"]))
    return {"id": cd.get("crustdata_company_id"), "name": bi.get("name"), "domain": bi.get("primary_domain"), "website": bi.get("website"),
            "description": (bi.get("description") or "")[:420], "type": bi.get("company_type"), "founded": bi.get("year_founded"),
            "hq": ", ".join(x for x in (loc.get("city"), loc.get("state")) if x), "categories": ((cd.get("taxonomy") or {}).get("categories") or [])[:6],
            "headcount": hc.get("total"), "added_12m": ga.get("yoy"), "added_6m": ga.get("six_months"), "g12": gp.get("yoy"),
            "stats": st, "teams": teams, "cities": [{"name": k, "share": round(v, 1)} for k, v in regions],
            "ratings": ratings, "rating": overall.get("rating"), "reviews": overall.get("total_count"),
            "raised_usd": fu.get("total_investment_usd"), "round_count": fu.get("num_funding_rounds"), "rounds": rounds,
            "logo": bi.get("logo_permalink"), "linkedin": bi.get("professional_network_url"), "followers": (cd.get("followers") or {}).get("count"),
            "followers_yoy": (cd.get("followers") or {}).get("yoy_percent"), "series": _series(hc.get("timeseries")) if full else None,
            "revenue_band": [est.get("lower_bound_usd"), est.get("upper_bound_usd")] if est.get("lower_bound_usd") else None,
            "acquired": rev.get("acquisition_status") == "acquired",
            "open_roles": jobs_total, "role_titles": job_titles, "news": news, "reads": reads}


def _series(ts, n=120):
    vals = [(t["date"][:10], t["employee_count"]) for t in (ts or []) if t.get("employee_count") is not None]
    step = max(1, len(vals) // n)
    out = vals[::step]
    if vals and out[-1] != vals[-1]:
        out.append(vals[-1])
    return out


def company_dossier(cl, cid, full=False):
    r = cl.call("/company/enrich", {"crustdata_company_ids": [cid], "fields": DOSSIER_FIELDS})
    cd = r[0]["matches"][0]["company_data"]
    total, titles = None, []
    try:
        j = cl.call("/job/search", {"filters": {"field": "company.basic_info.crustdata_company_id", "type": "=", "value": cid},
                                    "fields": ["job_details"], "limit": 40 if full else 12})
        total = j.get("total_count")
        seen = []
        for x in j.get("job_listings") or []:
            t = (x.get("job_details") or {}).get("title")
            if t and t not in seen:
                seen.append(t)
        titles = seen[:14 if full else 6]
    except CrustdataError:
        pass
    return build_dossier(cd, total, titles, full)
