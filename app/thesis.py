"""Thesis engine: turns counts into a testable claim about what a company is building.

A thesis is a team that stands out ("Groww is building out Wealth & Relationship Management"). It is only stated if it
survives six independent checks, each drawn from a different part of the data, and it always says what would change our mind.
It is code, not a model: every signal is a number you can click through to the people behind it.

  1. Distinctiveness  how much more of the hiring is in this team than at the other companies we have run
  2. Senior anchor    a Director, VP or C-level hire whose title is about this team
  3. Feeder pool      the hires come from the same few employers (a deliberate pipeline, not random hiring)
  4. Open demand      job postings that ask for more of the same
  5. Momentum         the team is still hiring once the latest, still-filling month is ignored
  6. Exits            people in the same function are not leaving as fast as they arrive
"""
import collections
import re

from . import analysis

STOP = {"and", "management", "engineering", "services", "operations", "development", "planning", "strategy", "general",
        "other", "support", "analytics", "business", "regional", "applied", "specialist"}
MIN_HIRES = 6


def keywords(sub_name):
    toks = [t for t in re.findall(r"[a-z]{3,}", sub_name.lower()) if t not in STOP]
    return toks or [t for t in re.findall(r"[a-z]{3,}", sub_name.lower())][:2]


def peer_profiles(store, exclude_company_id, min_hires=50):
    """Team mix of every other company already run (latest run each). This is the baseline for 'distinctive'."""
    seen, out = {}, []
    for r in store.list_runs(300):
        if r["status"] != "done":
            continue
        run = store.get_run(r["id"])
        res = run["result"] or {}
        co = res.get("company") or {}
        cid = co.get("id")
        if cid is None or cid == exclude_company_id or cid in seen:
            continue
        a = res.get("analysis") or {}
        n = (a.get("counts") or {}).get("external", 0)
        if n < min_hires or (co.get("name") or "").strip().lower() in {"no-company", "no company"}:
            continue
        shares = {}
        for d in a.get("depts", []):
            for s in d.get("sub", []):
                shares[s["name"]] = s["count"] / n
        seen[cid] = True
        out.append({"company": co["name"], "n": n, "shares": shares})
    return out


def _momentum_ok(monthly, months):
    """Is the team still hiring once the unfinished latest month is ignored? Returns (result, detail)."""
    counts = [monthly.get(m, 0) for m in months][:-1]  # drop the month still filling
    if sum(counts) < MIN_HIRES:
        return "skip", "too few hires to judge a trend"
    recent, prev = sum(counts[-3:]), sum(counts[-6:-3])
    if prev == 0:
        return ("pass" if recent >= 2 else "skip"), "%d hires in the last 3 full months, none in the 3 before" % recent
    ok = recent >= 0.5 * prev
    return ("pass" if ok else "fail"), "%d hires in the last 3 full months against %d in the 3 before" % (recent, prev)


def build_theses(a, company, jobs, peers, window_months=12, limit=3):
    months = a["window"]["months"]
    n_ext = a["counts"]["external"]
    if not n_ext:
        return []
    ev = a.get("evidence", {})
    seniors = (a.get("senior") or {}).get("list") or []
    ex_titles = [t["t"].lower() for t in ((a.get("exits") or {}).get("titles") or [])]
    jtitles = [(j.get("title") or "").lower() for j in (jobs or [])]
    cands = []
    for d in a["depts"]:
        if d["name"] == analysis.UNPLACED:
            continue
        for s in d["sub"]:
            if s["count"] < MIN_HIRES or s["name"].startswith("(") or s.get("unreliable"):
                continue
            kw = keywords(s["name"])
            share = s["count"] / n_ext
            sig = []

            # 1. distinctiveness against the other companies we have run
            if peers:
                pm = sum(p["shares"].get(s["name"], 0) for p in peers) / len(peers)
                lift = share / max(pm, 0.005)
                lines = ", ".join("%s %d%%" % (p["company"], round(100 * p["shares"].get(s["name"], 0))) for p in peers[:4])
                res = "pass" if lift >= 2 else "fail"
                sig.append({"id": "distinct", "name": "Distinctive", "result": res,
                            "detail": "%d%% of %s's hires are in this team against %d%% on average at the others (%s): %.1fx" % (
                                round(100 * share), company, round(100 * pm), lines, lift), "lift": round(lift, 1)})
            else:
                sig.append({"id": "distinct", "name": "Distinctive", "result": "skip",
                            "detail": "no other company has been run yet, so there is nothing to compare against", "lift": None})

            # 2. a senior hire whose title is about this team
            anchors = [x for x in seniors if any(k in (x["title"] or "").lower() for k in kw)]
            sig.append({"id": "anchor", "name": "Senior anchor", "result": "pass" if anchors else "fail",
                        "detail": ("%s, joined %s%s" % (anchors[0]["title"], anchors[0]["start"], (" from " + anchors[0]["prev"]) if anchors[0].get("prev") else ""))
                        if anchors else "no Director, VP or C-level hire has a title about this team"})

            # 3. the hires come from the same few employers
            prevs = collections.Counter(ev[str(i)]["p"] for i in s["evidence"] if str(i) in ev and ev[str(i)].get("p"))
            known = sum(prevs.values())
            repeat = sum(n for n in prevs.values() if n >= 2)
            if known >= 5:
                top = ", ".join("%s (%d)" % kv for kv in prevs.most_common(3))
                sig.append({"id": "feeder", "name": "Feeder pool", "result": "pass" if repeat / known >= 0.25 else "fail",
                            "detail": "%d of %d hires with a known previous employer came from an employer that supplied two or more: %s" % (repeat, known, top),
                            "feeders": [k for k, _ in prevs.most_common(3)]})
            else:
                sig.append({"id": "feeder", "name": "Feeder pool", "result": "skip", "detail": "too few hires with a known previous employer"})

            # 4. open roles asking for more of the same
            hit = [t for t in jtitles if any(k in t for k in kw)]
            if len(jtitles) >= 30 or hit:
                sig.append({"id": "demand", "name": "Open demand", "result": "pass" if len(hit) >= 2 else "fail",
                            "detail": "%d of %d open postings read as this team%s" % (len(hit), len(jtitles), (": " + "; ".join(h.title() for h in hit[:2])) if hit else "")})
            else:
                sig.append({"id": "demand", "name": "Open demand", "result": "skip", "detail": "too few postings to judge"})

            # 5. still hiring
            r5, d5 = _momentum_ok(s["monthly"], months)
            sig.append({"id": "momentum", "name": "Momentum", "result": r5, "detail": d5})

            # 6. people in the same function leaving
            gone = sum(1 for t in ex_titles if any(k in t for k in kw))
            if ex_titles:
                ratio = gone / s["count"]
                sig.append({"id": "exits", "name": "Exits", "result": "pass" if ratio <= 0.5 else "fail" if ratio > 0.8 else "skip",
                            "detail": "%d people with a title about this team left, against %d hired (%s)" % (
                                gone, s["count"], "not a revolving door" if ratio <= 0.5 else "leaving about as fast as they arrive" if ratio > 0.8 else "mixed")})
            else:
                sig.append({"id": "exits", "name": "Exits", "result": "skip", "detail": "exits were not pulled for this run"})

            passes = sum(1 for x in sig if x["result"] == "pass")
            fails = sum(1 for x in sig if x["result"] == "fail")
            judged = passes + fails
            conf = "strong" if passes >= 5 or (passes >= 4 and fails == 0) else "moderate" if passes >= 3 and passes > fails else "weak"
            verb = {"strong": "is building out", "moderate": "appears to be building out", "weak": "may be building out"}[conf]
            lift = next((x["lift"] for x in sig if x["id"] == "distinct"), None)
            per60 = s["count"] / window_months * 2
            floor = max(2, round(0.4 * per60))
            cands.append({
                "id": "T-" + re.sub(r"[^a-z0-9]+", "-", s["name"].lower()).strip("-"),
                "theme": s["name"], "dept": d["name"], "hires": s["count"], "share": round(share, 3),
                "statement": "%s %s %s (%d of its %d real hires)" % (company, verb, s["name"], s["count"], n_ext),
                "confidence": conf, "passes": passes, "fails": fails, "judged": judged, "signals": sig, "lift": lift,
                "feeders": next((x.get("feeders") for x in sig if x["id"] == "feeder" and x.get("feeders")), []),
                "falsifier": "If fewer than %d further %s hires appear in the next 60 days, or people in that function start leaving faster than they arrive, treat this as a one-off, not a build-out." % (floor, s["name"]),
                "evidence": s["evidence"][:40]})
    # prefer theses that stand out, then ones with more support
    cands.sort(key=lambda t: (t["passes"] - t["fails"], (t["lift"] or 0) >= 2, t["lift"] or 0, t["hires"]), reverse=True)
    return cands[:limit]
