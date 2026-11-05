"""Turns computed analysis into a sourced decision brief for a strategy team.

1. build_facts(): every number the brief may use, each with an id, a source and the people behind it.
2. template_brief(): deterministic brief (always works, no model).
3. llm_brief(): optional model rewrite. It may only cite fact ids and may only use numbers that appear in
   the facts; anything else is rejected and the template brief is used instead.
"""
import json
import re
import urllib.error
import urllib.request


def _pct(x):
    return "%d%%" % round(100 * x)


def build_facts(name, a, company_id, court=None, thesis=None):
    facts = []

    def add(text, source, evidence=None):
        fid = "F%d" % (len(facts) + 1)
        facts.append({"id": fid, "text": text, "source": source, "evidence": (evidence or [])[:80]})
        return fid

    c, w = a["counts"], a["window"]
    add("%d external joiners started a current %s role between %s and %s." % (c["external"], name, w["start"], w["end"]),
        "Crustdata Person Search: current role at company id %s, start date on or after %s" % (company_id, w["start"]))
    if c["relisted"]:
        add("%d more profiles with a role starting in the same window were excluded: they already held an earlier "
            "%s role that ended at most %d days before, so the new entry is a re-recorded role, not a hire."
            % (c["relisted"], name, a["thresholds"]["relist_gap_days"]),
            "Crustdata Person Search: earlier roles at the same company id on the same profile")
    if court and court["summary"]["tried"]:
        cs = court["summary"]
        add("Claim Court tried %d claims: %d killed, %d weakened, %d survived.%s" % (
            cs["tried"], cs["killed"], cs["weakened"], cs["survived"],
            (" Killed: " + "; ".join(cs["kills"][:3]) + ".") if cs["kills"] else ""),
            "X-Ray Claim Court: each claim attacked with the checks listed on the page")
    if thesis:
        t = thesis[0]
        add("Thesis (%s confidence): %s. %d of %d independent checks support it%s." % (
            t["confidence"], t["statement"], t["passes"], t["judged"],
            ("; it is %.1fx as common as at the other companies run" % t["lift"]) if t.get("lift") else ""),
            "X-Ray thesis engine: distinctiveness, senior anchor, feeder pool, open demand, momentum, exits", t["evidence"])
    hc = a.get("headcount")
    if hc and hc.get("total"):
        g = (hc.get("growth_percent") or {}).get("yoy")
        dw = hc.get("delta_window")
        add("Headcount series shows %s people as of %s%s%s." % (
            format(hc["total"], ","), hc.get("last_date"),
            "; growth over the last year is %.1f%%" % g if g is not None else "",
            "; it changed by %+d since %s" % (dw, w["start"]) if dw is not None else ""),
            "Crustdata Company Enrich: headcount.timeseries")
    om = a["overall_momentum"]
    add("Pace: %d external joiners in the last 6 months versus %d in the 6 months before (%s). The most recent weeks "
        "are under-counted because profiles update with a lag, so read months, not weeks."
        % (om["last6"], om["prev"], om["label"]),
        "Crustdata Person Search: start dates of external joiners")
    real = [d for d in a["depts"] if d["name"] != "Unplaced"]
    if hc and hc.get("total") and c["external"]:
        add("External hires equal %.1f%% of headcount (%d of %s)." % (100.0 * c["external"] / hc["total"], c["external"], format(hc["total"], ",")),
            "Real external hires divided by the headcount series")
    for d in real[:4]:
        m = d["momentum"]
        add("%s: %d external joiners (%s of %d). Last 6 months: %d, the 6 months before: %d (%s)."
            % (d["name"], d["external"], _pct(d["share"]), c["external"], m["last6"], m["prev"], m["label"]),
            "Crustdata Person Search: normalized department of the current role", d["evidence"])
    subs = [(d["name"], s) for d in real for s in d["sub"] if not s["name"].startswith("(") and not s["unreliable"]]
    for dname, s in [x for x in sorted(subs, key=lambda x: -x[1]["count"]) if x[1]["count"] >= 5][:4]:
        rep = [p for p in s["top_prev"] if p["n"] >= 2][:3]
        prev = ", ".join("%s (%d)" % (p["name"], p["n"]) for p in rep) or "no single one stands out"
        add("%s (in %s): %d external joiners; typical titles: %s. Most common previous employers: %s."
            % (s["name"], dname, s["count"], "; ".join(s["titles"][:2]) or "n/a", prev),
            "Crustdata Person Search: normalized sub-department and previous roles", s["evidence"])
    sn = a.get("senior") or {}
    if sn.get("list"):
        cnt = sn["counts"]
        parts = ", ".join("%d %s%s" % (cnt[k], k, "" if cnt[k] == 1 else "s" if k != "CXO" else "")
                          for k in ("CXO", "Vice President", "Director") if cnt.get(k))
        top = "; ".join("%s (from %s)" % (s["title"], s["prev"] or "unknown") for s in sn["list"][:3])
        n_s = len(sn["list"])
        add("%d senior %s (%s) joined in the window. The most senior: %s." % (n_s, "hire" if n_s == 1 else "hires", parts, top),
            "Crustdata Person Search: seniority level of the current role", [s["id"] for s in sn["list"]])
    ex = a.get("exits")
    if ex:
        add("%d people left %s in the window (net %+d against %d external hires). A further %d people had a role end but "
            "still work there (promotions or moves). Median time in the role they left: %s months."
            % (ex["left"], name, ex["net_total"], c["external"], ex["internal_moves"], ex["median_tenure_months"]),
            "Crustdata Person Search: roles at the company that ended in the window, minus people who still hold a role there")
        dest = [d for d in ex["destinations"] if d["cid"] or d["name"] != "no current role listed"][:4]
        if dest:
            add("Where leavers went: %s." % ", ".join("%s (%d)" % (d["name"], d["n"]) for d in dest),
                "Crustdata Person Search: current employer of people who left")
        nets = [x for x in ex["net_by_dept"] if x["dept"] != "Unplaced"]
        if nets:
            ups, downs = nets[:2], [x for x in nets[::-1][:2] if x["net"] < 0]
            bits = ["%s %+d" % (x["dept"], x["net"]) for x in ups + downs]
            add("Net change by team (hires minus exits, grouped by job-title keywords so approximate): %s." % ", ".join(bits),
                "Hires and exits grouped by keywords in the job title")
    o = a.get("open_roles")
    if o and o["count_pulled"]:
        if o.get("categories") and o.get("total_reported"):
            add("Job search lists %d postings in total; by the data's own category the largest are %s." % (
                o["total_reported"], ", ".join("%s (%d)" % (x["name"], x["n"]) for x in o["categories"][:4])),
                "Crustdata Job Search: group_by job_details.category over all postings")
        else:
            top = sorted(o["by_dept"].items(), key=lambda kv: -kv[1])[:3]
            add("Job search returned %d postings; by title the largest groups are %s." % (
                o["count_pulled"], ", ".join("%s (%d)" % kv for kv in top)),
                "Crustdata Job Search: titles classified by keyword")
    if c["unplaced"]:
        add("%d of %d external joiners have no department in the data (%s)."
            % (c["unplaced"], c["external"], _pct(c["unplaced"] / c["external"])),
            "Crustdata Person Search: normalized_title.department is empty")
    return facts


def _top_dept_names(a, n=2):
    return [d for d in a["depts"] if d["name"] != "Unplaced"][:n]


def tldr_text(name, a, court=None):
    """Two plain sentences a busy reader can repeat. Built only from computed numbers."""
    c = a["counts"]
    tops = _top_dept_names(a, 2)
    s = "%s added %d real hires since %s (%d re-recorded roles removed)" % (name, c["external"], a["window"]["start"], c["relisted"])
    if tops:
        s += ", led by " + " and ".join("%s (%d)" % (d["name"], d["external"]) for d in tops)
    s += "."
    if court and court["summary"]["killed"]:
        cs = court["summary"]
        s += " X-Ray rejected %d naive claim%s, e.g. %s." % (cs["killed"], "" if cs["killed"] == 1 else "s", cs["headline_kill"] or "see the court")
    return s


def template_brief(name, a, facts, court=None, thesis=None):
    fid = {}
    for f in facts:  # map first words to ids so findings can cite them
        fid.setdefault(f["text"].split(":")[0].split(" (")[0][:40], f["id"])
    c = a["counts"]
    tops = _top_dept_names(a, 2)
    findings = []
    for f in facts:
        conf = "high" if f["id"] in ("F1", "F2") else "medium"
        findings.append({"text": f["text"], "fact_ids": [f["id"]], "confidence": conf})
    subs = [(d["name"], s) for d in a["depts"] if d["name"] != "Unplaced" for s in d["sub"]
            if not s["name"].startswith("(") and s["count"] >= 5 and not s["unreliable"]]
    subs.sort(key=lambda x: -x[1]["count"])
    om = a["overall_momentum"]
    inference = None
    if subs:
        s1 = subs[0][1]
        # the biggest cluster outside core engineering is the more distinctive signal
        others = [x for x in subs if x[0] != "Engineering & Technology"]
        s2 = others[0][1] if others else (subs[1][1] if len(subs) > 1 else None)
        if s2 and s2 is not s1:
            names = "%s (the largest team) and, beyond that, %s" % (s1["name"], s2["name"])
        else:
            names = s1["name"]
        basis = [f["id"] for f in facts if s1["name"] in f["text"] or (s2 and s2["name"] in f["text"])]
        conf = "low" if (c["external"] < 150 or c["unplaced"] / max(1, c["external"]) > 0.25 or a["counts"]["truncated"]) else "medium"
        inference = {
            "text": "Hiring since %s is concentrated in %s. That points to continued investment there, but it is an "
                    "inference from public profile data, not a confirmed plan." % (a["window"]["start"], names),
            "confidence": conf, "basis_fact_ids": basis}
    if thesis:
        t = thesis[0]
        fid = [f["id"] for f in facts if f["text"].startswith("Thesis")]
        inference = {"text": "%s. %d of %d independent checks support it. It rests on public profile data, so it is a lean, not a plan. %s" % (
            t["statement"], t["passes"], t["judged"], t["falsifier"]),
            "confidence": {"strong": "high", "moderate": "medium", "weak": "low"}[t["confidence"]], "basis_fact_ids": fid}
    head = "%s: %d external hires in the window" % (name, c["external"])
    if tops:
        head += ", mostly " + " and ".join("%s (%d)" % (d["name"], d["external"]) for d in tops)
    if om["label"] in ("growing", "fading"):
        head += "; the hiring pace is %s (%d in the last 6 months vs %d before)" % (om["label"], om["last6"], om["prev"])
    ex = a.get("exits")
    if ex:
        head += "; %d people left, so net tracked change is %+d" % (ex["left"], ex["net_total"])
    actions = []
    if subs:
        actions.append("Track monthly external hiring in %s; a sustained rise would strengthen the inference." % subs[0][1]["name"])
        if subs[0][1]["top_prev"]:
            actions.append("Review the previous-employer pool (%s) as the likely source of their talent."
                           % ", ".join(p["name"] for p in subs[0][1]["top_prev"][:3]))
    o = a.get("open_roles")
    if o and o["count_pulled"]:
        actions.append("Compare these hires against the open roles listed (%d found) to see what they are still trying to fill." % o["count_pulled"])
    return {"headline": head + ".", "tldr": tldr_text(name, a, court), "findings": findings, "inference": inference,
            "caveats": list(a["warnings"]) + ["Public profile data lags reality by up to 30 days and cannot show reporting lines or internal plans."],
            "actions": actions, "generated_by": "template"}


# ------------------------------------------------------------------ optional model rewrite
SYSTEM = ("You write a one-page competitive brief for a strategy team. You may ONLY use facts from the list the user "
          "gives you. Every finding must cite fact ids. Do not use any number that does not appear in the facts. "
          "Separate what the data shows (findings) from what you infer (inference), and give the inference a "
          "confidence of low, medium or high. Never claim to know internal plans. Write a plain-English 'tldr' of at "
          "most 40 words that a busy executive could repeat, and lead with the single most decision-relevant point, "
          "not with the largest team. Reply with JSON only.")


def _numbers(text):
    out = set()
    for m in re.findall(r"\d[\d,]*\.?\d*", text or ""):
        out.add(m.replace(",", "").rstrip("."))
    return out


def _brief_text(b):
    parts = [b.get("headline", ""), b.get("tldr", "")]
    for f in b.get("findings", []):
        parts.append(f.get("text", ""))
    inf = b.get("inference") or {}
    parts.append(inf.get("text", ""))
    parts += b.get("actions", [])
    return " ".join(parts)


def verify_brief(b, facts):
    """Returns (ok, problems). Cited ids must exist; every number must appear in the facts."""
    ids = {f["id"] for f in facts}
    allowed = set()
    for f in facts:
        allowed |= _numbers(f["text"])
    problems = []
    for f in b.get("findings", []):
        if not f.get("fact_ids") or any(i not in ids for i in f["fact_ids"]):
            problems.append("finding cites a fact id that does not exist: %s" % f.get("fact_ids"))
    bad = sorted(n for n in _numbers(_brief_text(b)) if n not in allowed)
    if bad:
        problems.append("numbers not found in facts: %s" % ", ".join(bad))
    return (not problems), problems


def llm_brief(name, a, facts, key, model):
    if not key:
        return None, "no model key"
    user = ("Company: %s\nFacts (JSON):\n%s\n\nReturn JSON: {\"headline\": str, \"tldr\": str, \"findings\": [{\"text\": str, "
            "\"fact_ids\": [str], \"confidence\": \"low|medium|high\"}], \"inference\": {\"text\": str, "
            "\"confidence\": \"low|medium|high\", \"basis_fact_ids\": [str]}, \"actions\": [str]}"
            % (name, json.dumps([{"id": f["id"], "text": f["text"]} for f in facts])))
    body = {"model": model, "max_tokens": 1800, "system": SYSTEM, "messages": [{"role": "user", "content": user}]}
    try:
        text = call_model(body, key)
        b = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as e:
        return None, "model call failed: %s" % e
    ok, problems = verify_brief(b, facts)
    if not ok:
        return None, "; ".join(problems)
    if not b.get("tldr"):
        b["tldr"] = tldr_text(name, a)
    b["caveats"] = list(a["warnings"]) + ["Public profile data lags reality by up to 30 days and cannot show reporting lines or internal plans."]
    b["generated_by"] = "model (%s), numbers verified against facts" % model
    return b, None


def call_model(body, key):
    """One Messages API call; isolated so tests can replace it."""
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=90).read().decode("utf-8"))
    return "".join(p.get("text", "") for p in r.get("content", []))
