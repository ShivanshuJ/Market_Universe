"""Claim Court: every claim a straightforward tool would make is put on trial against traps we met in real data.

A claim ends as SURVIVED, WEAKENED or KILLED. A KILLED claim shows the naive number next to the audited one.
Everything here is plain code over the saved analysis and people records: no model, no network, no credits.
A model (optional) may read the verdicts, but it never decides them.
"""
import datetime as dt
import hashlib
import json
import statistics

from . import analysis

KILLED, WEAKENED, SURVIVED = "killed", "weakened", "survived"
ORDER = {KILLED: 0, WEAKENED: 1, SURVIVED: 2}


def _t(name, result, detail):
    """One attack on a claim. result: pass | warn | fail."""
    return {"name": name, "result": result, "detail": detail}


def _verdict(tests):
    rs = [t["result"] for t in tests]
    return KILLED if "fail" in rs else WEAKENED if "warn" in rs else SURVIVED


def _claim(cid, title, by, text, tests, naive=None, audited=None, why="", cols=None, rows=None, kill_line=None):
    return {"id": cid, "title": title, "by": by, "claim": text, "tests": tests, "verdict": _verdict(tests),
            "naive": naive, "audited": audited, "why": why, "cols": cols or [], "rows": rows or [], "kill_line": kill_line}


# ------------------------------------------------------------------ pace under different assumptions
def pace_label(counts, k=0):
    """Label from monthly counts, ignoring the last k (still-filling) months."""
    n = len(counts) - k
    if n < 4:
        return "too few to judge"
    series = counts[:n]
    recent, prev = series[-6:], series[:-6]
    if not prev or sum(series) < analysis.MIN_TOTAL_FOR_LABEL:
        return "too few to judge"
    ra, pa = sum(recent) / len(recent), sum(prev) / len(prev)
    if pa == 0:
        return "growing" if sum(recent) >= 5 else "steady"
    if ra >= analysis.GROW_RATIO * pa:
        return "growing"
    if ra <= analysis.FADE_RATIO * pa and sum(prev) >= analysis.MIN_TOTAL_FOR_LABEL:
        return "fading"
    return "steady"


# ------------------------------------------------------------------ the court
def run_court(a, people, window_start, today, company=None, resolve=None, jobs_total=None):
    c, ws = a["counts"], window_start
    months = a["window"]["months"]
    ext_m, rel_m = a["monthly"]["external"], a["monthly"]["relisted"]
    gap = a["thresholds"]["relist_gap_days"]
    claims = []

    # ---- C1: "N people joined since <date>"
    raw, real, rel = c["in_window"], c["external"], c["relisted"]
    share = rel / raw if raw else 0
    alts = {g: analysis.analyze(people, ws, today, gap_days=g) for g in (60, 180)}
    alt_ext = {g: alts[g]["counts"]["external"] for g in alts}
    spread = (max([real] + list(alt_ext.values())) - min([real] + list(alt_ext.values()))) / real if real else 0
    ic = c.get("intern_conversions", 0)
    ex_rows = [{"a": e["n"], "b": "%s (%s to %s)" % (e["pt"], (e["ps"] or "")[:7], (e["pe"] or "")[:7]), "c": "%s (from %s)" % (e["t"], e["s"][:7])}
               for e in a.get("relisted_examples", [])[:14]]
    claims.append(_claim(
        "C1", "How many people joined?", "naive tool", "%d people joined since %s" % (raw, ws),
        [_t("Re-recorded roles", "fail" if share >= .25 else "warn" if share >= .10 else "pass",
            "%d of %d (%d%%) already held an earlier role here that ended within %d days: promotions or restructures, not hires"
            % (rel, raw, round(100 * share), gap)),
         _t("Rule sensitivity", "pass" if spread <= .10 else "warn",
            "Real hires would be %d at a 60-day rule, %d at %d days, %d at 180 days" % (alt_ext[60], real, gap, alt_ext[180]))]
        + ([_t("Intern conversions", "warn",
               "%d of the re-recorded roles are interns who became full-time. That is a new full-time seat, so a generous reading counts them: real hires would be %d" % (ic, real + ic))] if ic else []),
        naive={"label": "raw joiners", "value": raw},
        audited={"label": "real hires", "value": real, "note": ("strict count; up to %d if intern conversions count" % (real + ic)) if ic else None},
        why="%d%% of the raw count were people already on the payroll." % round(100 * share),
        cols=["Person", "Earlier role at this company", "Role now recorded"], rows=ex_rows,
        kill_line="%d 'joiners' became %d real hires" % (raw, real)))

    # ---- C2: spike months
    med = statistics.median([ext_m[m] + rel_m[m] for m in months]) if months else 0
    spikes = sorted([m for m in months if rel_m[m] >= 10 and ext_m[m] + rel_m[m] >= max(2 * med, med + 10)
                     and rel_m[m] / (ext_m[m] + rel_m[m]) >= .5], key=lambda m: -rel_m[m])[:2]
    for i, m in enumerate(spikes):
        rm, em = rel_m[m], ext_m[m]
        rows = [{"a": e["n"], "b": "%s (%s to %s)" % (e["pt"], (e["ps"] or "")[:7], (e["pe"] or "")[:7]), "c": e["t"]}
                for e in a.get("relisted_examples", []) if e["s"][:7] == m][:14]
        claims.append(_claim(
            "C2%s" % ("" if i == 0 else chr(98 + i - 1)), "A hiring spike in %s?" % m, "naive tool",
            "%d people were hired in %s" % (rm + em, m),
            [_t("Re-recorded roles", "fail", "%d of the %d that month (%d%%) were re-recorded roles, concentrated in one month"
                % (rm, rm + em, round(100 * rm / (rm + em)))),
             _t("Against a normal month", "warn", "The median month shows %d raw joiners; this month shows %d" % (med, rm + em))],
            naive={"label": "raw joiners in " + m, "value": rm + em}, audited={"label": "real hires in " + m, "value": em},
            why="The spike is mostly profile restructuring, not hiring.", cols=["Person", "Earlier role", "Role now recorded"], rows=rows,
            kill_line="%s: %d 'hires' were really %d" % (m, rm + em, em)))

    # ---- C3: pace
    om = a["overall_momentum"]
    base = om["label"]
    if base.startswith("not comparable"):
        claims.append(_claim("C3", "Is hiring speeding up or slowing?", "X-Ray", "Pace cannot be judged: capped sample",
                             [_t("Sample size", "warn", "The people pull was capped (newest first), so comparing halves of the window would fake growth")],
                             why="X-Ray withholds a pace label when the sample is capped."))
    else:
        counts = [ext_m[m] for m in months]
        labs = {k: pace_label(counts, k) for k in (0, 1, 2)}
        gap_labs = {g: pace_label([alts[g]["monthly"]["external"][m] for m in months], 0) for g in alts}
        directional = {l for l in list(labs.values()) + list(gap_labs.values()) if l in ("growing", "fading")}
        stable = len(set(labs.values())) == 1 and len(set(gap_labs.values()) | {labs[0]}) == 1
        flips = {"growing", "fading"} <= directional
        claims.append(_claim(
            "C3", "Is hiring speeding up or slowing?", "X-Ray", "Hiring pace is %s (%d in the last 6 months vs %d before)" % (base, om["last6"], om["prev"]),
            [_t("Profile-lag test", "pass" if len(set(labs.values())) == 1 else "fail" if flips else "warn",
                "Ignoring the latest 0, 1, 2 months gives: %s, %s, %s (recent months are under-counted because profiles update late)" % (labs[0], labs[1], labs[2])),
             _t("Rule sensitivity", "pass" if len(set(gap_labs.values()) | {labs[0]}) == 1 else "warn",
                "At a 60-day rule: %s; at 180 days: %s" % (gap_labs[60], gap_labs[180]))],
            why="The label is %s." % ("stable under every assumption we tried" if stable else "sensitive to how recent months are treated; treat it as a lean, not a fact"),
            kill_line=("'%s' pace flips with profile lag" % base) if flips else None))

    # ---- C4: largest team
    real_depts = [d for d in a["depts"] if d["name"] != analysis.UNPLACED]
    if len(real_depts) >= 2:
        d1, d2 = real_depts[0], real_depts[1]
        lead, unp = d1["external"] - d2["external"], c["unplaced"]
        claims.append(_claim(
            "C4", "Which team is hiring the most?", "X-Ray", "%s is the largest team of new hires (%d, ahead of %s by %d)" % (d1["name"], d1["external"], d2["name"], lead),
            [_t("Missing team labels", "pass" if lead > unp else "warn",
                "%d hires have no team label; the lead over #2 is %d, so the ranking %s" % (unp, lead, "cannot change" if lead > unp else "could change"))],
            why="The ranking holds even if every unlabelled hire joined the runner-up." if lead > unp else "Unlabelled hires could reorder the top two."))

    # ---- C5: sub-teams
    subs = [(d["name"], s) for d in real_depts for s in d["sub"] if s["count"] >= 5 and not s["name"].startswith("(")]
    for dn, s in [x for x in subs if x[1].get("unreliable")][:3]:
        claims.append(_claim(
            "C5", "Is '%s' a real team?" % s["name"], "naive tool", "'%s' is a team of %d new hires" % (s["name"], s["count"]),
            [_t("Title check", "fail", "%s, so the label says little about what they do" % s["unreliable"])],
            naive={"label": "team size", "value": s["count"]}, audited={"label": "usable team signal", "value": 0},
            why="A team made of one vague title is a labelling artefact.", kill_line="'%s' (%d people) is a labelling artefact" % (s["name"], s["count"])))
    for dn, s in [x for x in subs if not x[1].get("unreliable")][:2]:
        top = s["top_prev"][0] if s["top_prev"] else None
        claims.append(_claim(
            "C5", "Is '%s' a real team?" % s["name"], "X-Ray", "%s has %d new hires (in %s)" % (s["name"], s["count"], dn),
            [_t("Title check", "pass", "Typical titles: %s" % "; ".join(s["titles"][:2])),
             _t("Source concentration", "pass", ("Most common previous employer: %s (%d)" % (top["name"], top["n"])) if top else "No dominant previous employer")],
            why="Titles are specific, so the label means something."))

    # ---- C6: senior hires
    sa = (a.get("senior") or {}).get("audit") or {}
    if sa.get("tagged"):
        rem = sa["tagged"] - sa["kept"]
        claims.append(_claim(
            "C6", "How many senior leaders joined?", "naive tool", "%d senior leaders joined" % sa["tagged"],
            [_t("Title audit", "fail" if rem and rem / sa["tagged"] >= .25 else "warn" if rem else "pass",
                ("%d of %d tagged senior have assistant, intern or advisor titles" % (rem, sa["tagged"])) if rem else "Every senior-tagged title reads as senior")],
            naive={"label": "tagged senior", "value": sa["tagged"]}, audited={"label": "senior titles", "value": sa["kept"]},
            why="The data tags some assistants as senior." if rem else "Titles are consistent with the tags.",
            cols=["Removed title", "Tagged as"], rows=[{"a": r["title"], "b": r["level"]} for r in sa.get("removed", [])[:10]],
            kill_line=("%d 'senior' hires were %d once titles were checked" % (sa["tagged"], sa["kept"])) if rem and rem / sa["tagged"] >= .25 else None))

    # ---- C7: net change vs the headcount series
    ex, hc = a.get("exits"), a.get("headcount")
    if ex:
        net, dw = ex["net_total"], (hc or {}).get("delta_window")
        tests = []
        if dw is not None:
            disagree = (net < 0) != (dw < 0) and abs(net) >= 10
            tests.append(_t("Headcount series", "fail" if disagree else "pass",
                            "Hires minus exits is %+d but the headcount series moved %+d over the same window" % (net, dw)))
        tests.append(_t("Completeness", "warn" if ex.get("truncated") else "pass",
                        "The exits pull was capped" if ex.get("truncated") else "Exits were pulled in full"))
        claims.append(_claim(
            "C7", "Is the company growing or shrinking?", "naive tool", "Net change is %+d (%d real hires minus %d who left)" % (net, real, ex["left"]),
            tests, naive={"label": "hires minus exits", "value": net},
            audited={"label": "headcount series", "value": dw} if dw is not None else None,
            why="Hires minus exits only counts profiles we can match; it is a movement count, not a headcount.",
            kill_line=("net %+d disagrees with the headcount series (%+d)" % (net, dw)) if tests and tests[0]["result"] == "fail" else None))

    # ---- C8: company size
    if hc and hc.get("range") and hc.get("total") is not None:
        claims.append(_claim(
            "C8", "How big is the company?", "naive tool", "The company has %s people" % hc["range"],
            [_t("Two sources", "fail" if hc.get("conflict") else "pass",
                ("The size range says %s but the headcount series says %s" % (hc["range"], format(hc["total"], ","))) if hc.get("conflict") else "Range and series agree")],
            naive={"label": "size range", "value": hc["range"]}, audited={"label": "headcount series", "value": hc["total"]},
            why="The series is used; the range record is stale." if hc.get("conflict") else "",
            kill_line=("size says %s; the series says %s" % (hc["range"], format(hc["total"], ","))) if hc.get("conflict") else None))

    # ---- C9: open roles
    if hc and hc.get("openings_field") is not None and jobs_total is not None:
        diff = abs((hc["openings_field"] or 0) - jobs_total)
        claims.append(_claim(
            "C9", "How many roles are open?", "naive tool", "%s open roles (company record)" % hc["openings_field"],
            [_t("Two sources", "fail" if diff > 10 else "pass", "Job search lists %d postings against the company record's %s" % (jobs_total, hc["openings_field"]))],
            naive={"label": "company record", "value": hc["openings_field"]}, audited={"label": "job search", "value": jobs_total},
            why="Job search is used.", kill_line=("open roles: %s vs %d" % (hc["openings_field"], jobs_total)) if diff > 10 else None))

    # ---- C10: completeness / coverage
    cp = c.get("current_profiles")
    if cp and hc and hc.get("total"):
        cov = min(1.0, cp / hc["total"])
        upper = round(real / cov) if cov else real
        claims.append(_claim(
            "C10", "Does the count include everyone?", "X-Ray", "%d real hires is a complete count" % real,
            [_t("Profile coverage", "pass" if cov >= .9 else "warn",
                "%s profiles on record for about %s people (%d%% coverage), so the true figure may be up to about %d" % (format(cp, ","), format(hc["total"], ","), round(100 * cov), upper))],
            naive={"label": "counted", "value": real}, audited={"label": "plausible upper bound", "value": upper},
            why="The count is a lower bound; the range assumes unprofiled people were hired at the same rate."))

    # ---- C11: identity
    if resolve:
        asm = resolve.get("assumed")
        claims.append(_claim(
            "C11", "Is this the right company?", "X-Ray", "The request means %s" % (resolve["company"]["name"]),
            [_t("Name match", "warn" if asm else "pass", asm or "The company name matched exactly"),
             _t("Look-alikes", "warn" if len(resolve.get("alternates") or []) >= 5 else "pass",
                "%d other records share the name and were set aside (smaller or no website)" % len(resolve.get("alternates") or []))],
            why="Weak matches ask for the website instead of guessing."))

    # ---- C12: freshness
    if hc and hc.get("last_date"):
        lag = (today - dt.date.fromisoformat(hc["last_date"][:10])).days
        claims.append(_claim(
            "C12", "Is the data current?", "X-Ray", "The picture is as of %s" % hc["last_date"],
            [_t("Series age", "warn" if lag > 21 else "pass", "The headcount series ends %d days ago" % lag)],
            why="Profile data lags real life by up to a month."))

    claims.sort(key=lambda x: (ORDER[x["verdict"]], x["id"]))
    n = {v: sum(1 for x in claims if x["verdict"] == v) for v in ORDER}
    kills = [x["kill_line"] for x in claims if x["verdict"] == KILLED and x.get("kill_line")]
    table = []
    for x in claims:
        if x.get("naive") and x.get("audited") and x["naive"]["value"] != x["audited"]["value"]:
            table.append({"metric": x["title"], "naive": x["naive"], "audited": x["audited"], "verdict": x["verdict"], "id": x["id"]})
    cal = calibrate_headcount((hc or {}).get("timeseries") or [])
    preds = make_predictions(a, jobs_total, today)
    return {"claims": claims, "summary": {"tried": len(claims), "killed": n[KILLED], "weakened": n[WEAKENED], "survived": n[SURVIVED],
                                          "headline_kill": kills[0] if kills else None, "kills": kills[:4]},
            "table": table, "predictions": preds, "calibration": cal}


# ------------------------------------------------------------------ predictions on the record
BAND = 0.04  # a headcount call is right if it lands within +/-4% of the expected value


def _trend(points):
    d = [points[i + 1] - points[i] for i in range(len(points) - 1)]
    return sum(d) / len(d) if d else 0.0


def calibrate_headcount(ts):
    """How often would 'trend over the last 3 steps' have landed within the band 2 steps ahead, vs 'no change'?"""
    v = [t["employee_count"] for t in ts if t.get("employee_count")]
    n = hits = flat = 0
    for i in range(3, len(v) - 2):
        expect = v[i] + 2 * _trend(v[i - 3:i + 1])
        actual = v[i + 2]
        n += 1
        hits += abs(actual - expect) / expect <= BAND
        flat += abs(actual - v[i]) / v[i] <= BAND
    return {"windows": n, "trend_rate": round(hits / n, 2) if n else None, "flat_rate": round(flat / n, 2) if n else None}


def make_predictions(a, jobs_total, today):
    """Dated, checkable calls. They are scored later against fresh data by `python -m app.cli score`."""
    hc, out = a.get("headcount") or {}, []
    due = (today + dt.timedelta(days=56)).isoformat()
    ts = [t["employee_count"] for t in (hc.get("timeseries") or []) if t.get("employee_count")]
    if len(ts) >= 4 and hc.get("total"):
        exp = hc["total"] + 2 * _trend(ts[-4:])
        lo, hi = int(exp * (1 - BAND)), int(exp * (1 + BAND))
        out.append({"kind": "headcount_band", "due": due, "spec": {"lo": lo, "hi": hi},
                    "statement": "Headcount on %s will be between %s and %s (today: %s)" % (due, format(lo, ","), format(hi, ","), format(hc["total"], ","))})
    if jobs_total and jobs_total >= 10:
        fl = int(jobs_total * 0.8)
        out.append({"kind": "postings_floor", "due": due, "spec": {"floor": fl},
                    "statement": "Job postings on %s will be at least %d (today: %d)" % (due, fl, jobs_total)})
    return out


def prediction_hash(company_id, made_at, p):
    blob = json.dumps({"company": company_id, "made": made_at, "kind": p["kind"], "due": p["due"], "spec": p["spec"], "s": p["statement"]},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def score_due(store, client, today):
    """Check every prediction whose date has passed against fresh data. Returns what was scored."""
    scored = []
    for p in store.due_predictions(today.isoformat()):
        spec = json.loads(p["spec"])
        if p["kind"] == "headcount_band":
            r = client.call("/company/enrich", {"crustdata_company_ids": [p["company_id"]], "fields": ["headcount.timeseries"]}, use_cache=False)
            ts = r[0]["matches"][0]["company_data"]["headcount"]["timeseries"]
            obs = ts[-1]["employee_count"]
            hit = spec["lo"] <= obs <= spec["hi"]
        else:
            r = client.call("/job/search", {"filters": {"field": "company.basic_info.crustdata_company_id", "type": "=", "value": p["company_id"]},
                                            "fields": ["job_details"], "limit": 1}, use_cache=False)
            obs = r.get("total_count")
            hit = obs is not None and obs >= spec["floor"]
        store.update_prediction(p["id"], "hit" if hit else "miss", obs)
        scored.append({"id": p["id"], "statement": p["statement"], "observed": obs, "status": "hit" if hit else "miss"})
    return scored
