"""Pure analysis: no network, no model. Everything the brief says is computed here, from the raw records.

Hard case handled here: a "recent joiner" whose profile already shows an earlier role at the SAME company
is usually a re-recorded role (promotion, restructure, entity change), not a hire. Counting them inflated
Groww's last-12-month "joiners" by about 2x in our first look.
"""
import collections
import datetime as dt
import re

# ---- documented thresholds (also in README) ----
RELIST_GAP_DAYS = 120      # earlier same-company role ended within this many days of the new one starting => re-recorded
MOMENTUM_SPLIT_DAYS = 183  # last ~6 months vs the months before
MIN_TOTAL_FOR_LABEL = 8    # smaller groups get no growing/fading label
GROW_RATIO = 1.5
FADE_RATIO = 0.5

UNPLACED = "Unplaced"

# A sub-department built mostly from one vague title says little about what the team does.
GENERIC_TITLES = {"manager", "assistant manager", "senior manager", "associate", "senior associate", "executive",
                  "senior executive", "analyst", "senior analyst", "consultant", "specialist", "lead",
                  "associate director", "intern", "trainee", "officer", "senior officer", "team lead"}
GENERIC_SHARE = 0.7
MIN_CONFIDENT_SHARE = 0.5


def pdate(s):
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------ slimming raw API records
def slim_person(p, cid):
    """Keep only what the analysis reads. Returns None if the person has no current role at `cid`."""
    ed = ((p.get("experience") or {}).get("employment_details")) or {}
    cur = [r for r in (ed.get("current") or []) if r.get("crustdata_company_id") == cid]
    if not cur:
        return None
    cur.sort(key=lambda r: r.get("start_date") or "", reverse=True)
    r = cur[0]
    bp = p.get("basic_profile") or {}
    nt = bp.get("normalized_title") or {}
    past = []
    for x in ed.get("past") or []:
        past.append({"cid": x.get("crustdata_company_id"), "name": x.get("name"), "title": x.get("title"),
                     "start": (x.get("start_date") or "")[:10], "end": (x.get("end_date") or "")[:10]})
    past.sort(key=lambda x: x["end"] or "9999", reverse=True)
    return {
        "id": p.get("crustdata_person_id"), "cid": cid, "name": bp.get("name"),
        "title": r.get("title"), "start": (r.get("start_date") or "")[:10],
        "seniority": r.get("seniority_level"),
        "dept": nt.get("department") or None, "subdept": nt.get("sub_department") or None,
        "confident": bool(nt.get("confident")),
        "n_current_at_company": len(cur),
        "past": past[:14],
    }


def slim_company(enrich):
    try:
        d = enrich[0]["matches"][0]["company_data"]
    except (IndexError, KeyError, TypeError):
        return None
    bi, hc = d.get("basic_info") or {}, d.get("headcount") or {}
    ts = hc.get("timeseries") or []
    ts_small = []
    if ts:
        last = pdate(ts[-1]["date"])
        cutoff = last - dt.timedelta(days=800) if last else None
        pts = [t for t in ts if cutoff is None or (pdate(t["date"]) and pdate(t["date"]) >= cutoff)]
        ts_small = pts[::4]
        if pts and (not ts_small or ts_small[-1] != pts[-1]):
            ts_small.append(pts[-1])
    hiring = d.get("hiring") or {}
    ppl = d.get("people") or {}
    leaders, seen = [], set()
    for grp in ("founders", "cxos"):
        for x in ppl.get(grp) or []:
            pid = x.get("crustdata_person_id")
            if pid in seen:
                continue
            seen.add(pid)
            leaders.append({"id": pid, "name": (x.get("basic_profile") or {}).get("name"),
                            "title": (x.get("basic_profile") or {}).get("current_title"), "group": grp})
    traffic = {}
    for dom, t in ((d.get("web_traffic") or {}).get("domain_traffic") or {}).items():
        traffic = {"domain": dom, "monthly_visitors": t.get("monthly_visitors"), "qoq_pct": t.get("qoq_pct")}
        break
    return {
        "id": d.get("crustdata_company_id"), "name": bi.get("name"), "domain": bi.get("primary_domain"),
        "range": bi.get("employee_count_range"), "year_founded": bi.get("year_founded"),
        "type": bi.get("company_type"),
        "headcount": {"total": hc.get("total"), "growth_percent": hc.get("growth_percent"),
                      "by_role": hc.get("by_role_absolute"), "timeseries": ts_small,
                      "last_date": ts[-1]["date"] if ts else None},
        "hiring": {"openings_count": hiring.get("openings_count"),
                   "recent_titles": hiring.get("recent_titles_csv")},
        "leaders": leaders[:8], "traffic": traffic,
    }


_DEPT_RULES = [
    ("Engineering & Technology", r"engineer|developer|sde|devops|android|ios|frontend|backend|full.?stack|\bqa\b|sre|architect|data scien|machine learning|\bml\b|\bai\b"),
    ("Product & Design", r"product|design|ux|\bui\b"),
    ("Legal & Compliance", r"complian|legal|risk|audit|counsel"),
    ("Finance & Accounting", r"financ|account|wealth|treasury|\btax\b|credit|invest"),
    ("Marketing", r"market|content|brand|growth|seo|social media|communicat"),
    ("Sales & Revenue", r"\bsales\b|business development|relationship|partnership"),
    ("People & HR", r"\bhr\b|talent|recruit|people partner|human resource"),
    ("Customer Service & Support", r"support|customer|service"),
    ("Operations & Logistics", r"operations|procurement|logistic|admin"),
    ("Data & Analytics", r"analyst|analytics|business intelligence|\bbi\b"),
]


def title_to_dept(title):
    t = (title or "").lower()
    for dept, rx in _DEPT_RULES:
        if re.search(rx, t):
            return dept
    return UNPLACED


def slim_jobs(listings, today):
    out = []
    for j in listings or []:
        jd, md = j.get("job_details") or {}, j.get("metadata") or {}
        added = pdate(md.get("date_added"))
        out.append({"id": jd.get("job_id"), "title": jd.get("title"), "url": jd.get("url"),
                    "source": jd.get("source"), "reposted": bool(jd.get("reposted_job")),
                    "added": (md.get("date_added") or "")[:10],
                    "age_days": (today - added).days if added else None,
                    "dept": title_to_dept(jd.get("title"))})
    return out


# ------------------------------------------------------------------ classification
def classify(person, gap=None):
    """'new' | 'returning' | 'relisted'. Uses the earlier same-company roles on the profile.
    `gap` (days) is the re-recorded-role threshold; the court re-runs this with other values."""
    gap = RELIST_GAP_DAYS if gap is None else gap
    start = pdate(person["start"])
    same = [x for x in person["past"] if x.get("cid") == person["cid"]]
    if not same:
        return "new"
    gaps = []
    for x in same:
        end = pdate(x["end"])
        if end is None or start is None:
            gaps.append(0)  # open-ended earlier role: a continuation
        else:
            gaps.append((start - end).days)
    return "relisted" if min(gaps) <= gap else "returning"


def _norm_emp(name):
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    n = re.sub(r"\b(limited|ltd|pvt|private|llp|inc|india|technologies|technology|formerly)\b", " ", n)
    return " ".join(n.split())


def prev_employer(person):
    """Most recent earlier employer that is not the same company."""
    for x in person["past"]:
        if x.get("cid") != person["cid"] and x.get("name"):
            return x["name"], (x.get("cid") or _norm_emp(x["name"]))
    return None, None


SENIOR_LEVELS = {"CXO": 0, "Vice President": 1, "Director": 2}
INTERN = re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)
# The data tags some assistants, interns and advisors as senior; their titles give them away.
NOISE_SENIOR = re.compile(r"(executive|personal|admin\w*)\s+assistant|assistant\s+to\b|\bintern\b|trainee|advis[eo]r|"
                          r"\bto (the )?(ceo|chief|md|managing|chairman|founder)|office of|ceo office|secretary|apprentice", re.I)


def slim_leaver(p, cid):
    """A person with a role at `cid` that ended. Returns None if no ended role there is on the profile."""
    ed = ((p.get("experience") or {}).get("employment_details")) or {}
    cur = ed.get("current") or []
    still = any(r.get("crustdata_company_id") == cid for r in cur)
    left = [x for x in (ed.get("past") or []) if x.get("crustdata_company_id") == cid and x.get("end_date")]
    if not left:
        return None
    left.sort(key=lambda x: x.get("end_date") or "", reverse=True)
    r = left[0]
    elsewhere = [x for x in cur if x.get("crustdata_company_id") != cid]
    elsewhere.sort(key=lambda x: (bool(x.get("is_default")), x.get("start_date") or ""), reverse=True)
    dest = None
    if elsewhere:
        d = elsewhere[0]
        dest = {"cid": d.get("crustdata_company_id"), "name": d.get("name"), "title": d.get("title")}
    return {"id": p.get("crustdata_person_id"), "name": (p.get("basic_profile") or {}).get("name"),
            "title": r.get("title"), "start": (r.get("start_date") or "")[:10], "end": (r.get("end_date") or "")[:10],
            "seniority": r.get("seniority_level"), "still_here": still, "dest": dest,
            "dept_kw": title_to_dept(r.get("title"))}


def analyze_exits(leavers, window_start, today, ext_people, truncated=False):
    ws = pdate(window_start)
    ends = [l for l in leavers if pdate(l["end"]) and pdate(l["end"]) >= ws]
    internal = [l for l in ends if l["still_here"]]
    gone = [l for l in ends if not l["still_here"]]
    months = _months(ws, today)
    exit_m = collections.Counter(l["end"][:7] for l in gone)
    hire_m = collections.Counter(p["start"][:7] for p, _ in ext_people)
    hires_kw = collections.Counter(title_to_dept(p["title"]) for p, _ in ext_people)
    exits_kw = collections.Counter(l["dept_kw"] for l in gone)
    net = [{"dept": d, "hires": hires_kw.get(d, 0), "exits": exits_kw.get(d, 0),
            "net": hires_kw.get(d, 0) - exits_kw.get(d, 0)}
           for d in set(hires_kw) | set(exits_kw)]
    net.sort(key=lambda x: -x["net"])
    dest, dname = collections.Counter(), {}
    for l in gone:
        d = l["dest"]
        key = (d.get("cid") or _norm_emp(d.get("name"))) if d else None
        dest[key] += 1
        if d:
            dname.setdefault(key, d.get("name"))
    tenure = sorted(((pdate(l["end"]) - pdate(l["start"])).days / 30.4) for l in gone if pdate(l["start"]) and pdate(l["end"]))
    senior = sorted([l for l in gone if l["seniority"] in SENIOR_LEVELS], key=lambda l: l["end"], reverse=True)
    senior = sorted(senior, key=lambda l: SENIOR_LEVELS[l["seniority"]])[:15]
    return {
        "role_ends": len(ends), "internal_moves": len(internal), "left": len(gone), "truncated": truncated,
        "monthly": {m: {"hires": hire_m.get(m, 0), "exits": exit_m.get(m, 0)} for m in months},
        "net_total": len(ext_people) - len(gone),
        "titles": [{"t": l["title"], "e": l["end"]} for l in gone][:700],  # lets the thesis engine see who left from a team
        "net_by_dept": net,
        "destinations": [{"name": dname.get(k) or "no current role listed", "cid": k if isinstance(k, int) else None, "n": n}
                         for k, n in dest.most_common(12)],
        "median_tenure_months": round(tenure[len(tenure) // 2], 1) if tenure else None,
        "senior_leavers": [{"id": l["id"], "name": l["name"], "title": l["title"], "end": l["end"], "level": l["seniority"],
                            "to": (l["dest"] or {}).get("name")} for l in senior],
    }


def _months(start, end):
    y, m, out = start.year, start.month, []
    while (y, m) <= (end.year, end.month):
        out.append("%04d-%02d" % (y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _range_bounds(rng):
    m = re.match(r"^\s*(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)", rng or "")
    if m:
        return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    m = re.match(r"^\s*(\d[\d,]*)\+", rng or "")
    if m:
        return int(m.group(1).replace(",", "")), None
    return None, None


def momentum(starts, today, capped=False):
    split = today - dt.timedelta(days=MOMENTUM_SPLIT_DAYS)
    last = sum(1 for s in starts if s >= split)
    prev = len(starts) - last
    total = len(starts)
    if capped:
        # a capped pull keeps the newest people first, so comparing halves of the window would be an artefact
        label = "not comparable: capped sample"
    elif total < MIN_TOTAL_FOR_LABEL:
        label = "too few to judge"
    elif prev == 0:
        label = "growing" if last >= 5 else "steady"
    elif last >= GROW_RATIO * prev:
        label = "growing"
    elif last <= FADE_RATIO * prev and prev >= MIN_TOTAL_FOR_LABEL:
        label = "fading"
    else:
        label = "steady"
    return {"last6": last, "prev": prev, "label": label}


# ------------------------------------------------------------------ main analysis
def analyze(people, window_start, today, company=None, jobs=None, pulled_total=None, truncated=False,
            leavers=None, exits_truncated=False, gap_days=None, current_profiles=None):
    """people: slim_person dicts. company: slim_company dict. jobs: slim_jobs list.
    gap_days overrides the re-recorded-role threshold (used by the court's sensitivity tests)."""
    ws = pdate(window_start)
    gap = RELIST_GAP_DAYS if gap_days is None else gap_days
    kinds = collections.Counter()
    ext = []  # external joiners (new + returning)
    relisted_by_month = collections.Counter()
    relisted_examples = []
    intern_conv = 0
    outside = 0
    multi = 0
    for p in people:
        s = pdate(p["start"])
        if s is None or s < ws:
            outside += 1
            continue
        if p.get("n_current_at_company", 1) > 1:
            multi += 1
        k = classify(p, gap)
        kinds[k] += 1
        if k == "relisted":
            relisted_by_month[p["start"][:7]] += 1
            if INTERN.search(" ".join(x.get("title") or "" for x in p["past"] if x.get("cid") == p["cid"])) and not INTERN.search(p["title"] or ""):
                intern_conv += 1  # an intern who became full-time: arguably a real new seat
            if len(relisted_examples) < 150:
                earlier = [x for x in p["past"] if x.get("cid") == p["cid"]]
                e = sorted(earlier, key=lambda x: x["end"] or "9999", reverse=True)[0] if earlier else {}
                relisted_examples.append({"id": p["id"], "n": p["name"], "t": p["title"], "s": p["start"],
                                          "pt": e.get("title"), "ps": e.get("start"), "pe": e.get("end")})
        else:
            ext.append((p, k))

    months = _months(ws, today)
    ext_by_month = collections.Counter(p["start"][:7] for p, _ in ext)
    n_ext = len(ext)

    # per department
    by_dept = collections.defaultdict(list)
    for p, k in ext:
        by_dept[p["dept"] or UNPLACED].append((p, k))
    depts = []
    evidence = {}
    for name, rows in sorted(by_dept.items(), key=lambda kv: -len(kv[1])):
        starts = [pdate(p["start"]) for p, _ in rows]
        mo = collections.Counter(p["start"][:7] for p, _ in rows)
        subs = collections.defaultdict(list)
        for p, _ in rows:
            subs[p["subdept"] or "(no sub-department)"].append(p)
        sub_list = []
        for sname, sp in sorted(subs.items(), key=lambda kv: -len(kv[1])):
            prev = collections.Counter()
            disp = {}
            for p in sp:
                nm, key = prev_employer(p)
                if nm:
                    prev[key] += 1
                    disp.setdefault(key, nm)
            tcount = collections.Counter((p["title"] or "").strip().lower() for p in sp)
            top_t, top_n = (tcount.most_common(1) or [("", 0)])[0]
            conf_share = sum(1 for p in sp if p.get("confident")) / len(sp)
            reason = None
            if len(sp) >= 5 and top_t in GENERIC_TITLES and top_n / len(sp) >= GENERIC_SHARE:
                reason = "%d of %d people are titled just '%s'" % (top_n, len(sp), top_t)
            elif len(sp) >= 5 and conf_share < MIN_CONFIDENT_SHARE:
                reason = "the department tag is low-confidence for most of its %d people" % len(sp)
            sub_list.append({"name": sname, "count": len(sp), "unreliable": reason,
                             "monthly": dict(collections.Counter(p["start"][:7] for p in sp)),
                             "top_prev": [{"name": disp[k], "n": n} for k, n in prev.most_common(4)],
                             "titles": [t for t, _ in collections.Counter(p["title"] for p in sp).most_common(3)],
                             "evidence": [p["id"] for p in sorted(sp, key=lambda q: q["start"], reverse=True)[:60]]})
        prev = collections.Counter()
        disp = {}
        for p, _ in rows:
            nm, key = prev_employer(p)
            if nm:
                prev[key] += 1
                disp.setdefault(key, nm)
        depts.append({"name": name, "external": len(rows), "share": round(len(rows) / n_ext, 4) if n_ext else 0,
                      "returning": sum(1 for _, k in rows if k == "returning"),
                      "monthly": dict(mo), "momentum": momentum(starts, today, truncated),
                      "sub": sub_list, "top_prev": [{"name": disp[k], "n": n} for k, n in prev.most_common(5)],
                      "evidence": [p["id"] for p, _ in sorted(rows, key=lambda r: r[0]["start"], reverse=True)[:80]]})

    for p, k in ext:
        nm, pkey = prev_employer(p)
        evidence[str(p["id"])] = {"n": p["name"], "t": p["title"], "s": p["start"], "p": nm, "k": k,
                                  "d": p["dept"] or UNPLACED, "pc": pkey if isinstance(pkey, int) else None,
                                  "l": p.get("seniority")}

    prev_all = collections.Counter()
    disp_all = {}
    for p, _ in ext:
        nm, key = prev_employer(p)
        if nm:
            prev_all[key] += 1
            disp_all.setdefault(key, nm)

    senior, senior_removed = [], []
    for p, k in ext:
        if p.get("seniority") in SENIOR_LEVELS:
            nm, pkey = prev_employer(p)
            row = {"id": p["id"], "name": p["name"], "title": p["title"], "start": p["start"],
                   "level": p["seniority"], "dept": p["dept"] or UNPLACED, "prev": nm,
                   "pc": pkey if isinstance(pkey, int) else None, "kind": k}
            if NOISE_SENIOR.search(p["title"] or ""):
                senior_removed.append(row)  # tagged senior by the data, but the title says assistant/intern/advisor
            else:
                senior.append(row)
    senior.sort(key=lambda s: s["start"], reverse=True)               # newest first ...
    senior.sort(key=lambda s: SENIOR_LEVELS[s["level"]])              # ... within each level (stable sort)
    senior_counts = collections.Counter(s["level"] for s in senior)
    senior_audit = {"tagged": len(senior) + len(senior_removed), "kept": len(senior),
                    "removed": [{"id": r["id"], "title": r["title"], "level": r["level"]} for r in senior_removed][:20]}
    exits = analyze_exits(leavers, window_start, today, ext, exits_truncated) if leavers is not None else None

    unplaced_n = len(by_dept.get(UNPLACED, []))
    warnings = []
    if kinds["relisted"]:
        warnings.append("%d of %d people with a current role starting in the window already had an earlier role at "
                        "this company (gap <= %d days). They look like re-recorded roles, not hires, so they are "
                        "excluded from joiner counts." % (kinds["relisted"], sum(kinds.values()), gap))
    if kinds["returning"]:
        warnings.append("%d joiners are returning ex-employees (earlier role ended more than %d days before). "
                        "They are counted as hires." % (kinds["returning"], gap))
    for d in depts:
        for s in d["sub"]:
            if s["unreliable"]:
                warnings.append("Team '%s' (%d people) is left out of conclusions: %s, so the label says little about "
                                "what they do." % (s["name"], s["count"], s["unreliable"]))
    if unplaced_n:
        warnings.append("%d of %d external joiners (%.0f%%) have no department in the data and are shown as '%s' "
                        "instead of being guessed." % (unplaced_n, n_ext, 100 * unplaced_n / n_ext, UNPLACED))
    if truncated:
        warnings.append("People pull was capped by the credit/people limit (newest joiners first), so counts are a "
                        "lower bound and growing/fading labels are switched off.")
    if multi:
        warnings.append("%d people list more than one current role here; the most recent start date was used." % multi)

    if exits:
        warnings.append("Exits: %d roles ended in the window, but %d of those people still work here (promotions or "
                        "moves), so %d are counted as leavers. Exits are grouped by the title of the role they left "
                        "(keywords), because the data's department tag describes their new job. Per-team net change is "
                        "approximate, and recent exits are under-counted for the same profile-lag reason as hires."
                        % (exits["role_ends"], exits["internal_moves"], exits["left"]))
        if exits["truncated"]:
            warnings.append("The exits pull was capped, so exit counts are a lower bound and net change is overstated.")

    hc = None
    if company:
        h = company["headcount"]
        lo, hi = _range_bounds(company.get("range"))
        total = h.get("total")
        conflict = bool(total and lo is not None and (total < lo or (hi is not None and total > hi)))
        hc = {"total": total, "range": company.get("range"), "conflict": conflict,
              "growth_percent": h.get("growth_percent"), "last_date": h.get("last_date"),
              "timeseries": h.get("timeseries"), "by_role": h.get("by_role"),
              "openings_field": (company.get("hiring") or {}).get("openings_count")}
        ts = h.get("timeseries") or []
        base = next((t for t in ts if t["date"] >= window_start), None)
        hc["delta_window"] = (ts[-1]["employee_count"] - base["employee_count"]) if (base and ts) else None
        dw = hc["delta_window"]
        if exits and dw is not None and (exits["net_total"] < 0) != (dw < 0) and abs(exits["net_total"]) >= 10:
            warnings.append("Tracked hires minus exits is %+d, but the headcount series changed by %+d over the same "
                            "window. They are measured differently (profiles we can match vs a modelled series), so "
                            "treat the net figure as a rough guide, not a headcount." % (exits["net_total"], dw))
        if conflict:
            warnings.append("Company size sources disagree: size range says '%s' but the headcount series says %s. "
                            "The headcount series is used." % (company.get("range"), total))
        if h.get("last_date"):
            lag = (today - pdate(h["last_date"])).days
            if lag > 21:
                warnings.append("Headcount series ends %s (%d days old)." % (h["last_date"], lag))

    open_roles = None
    if jobs is not None:
        by = collections.Counter(j["dept"] for j in jobs)
        open_roles = {"count_pulled": len(jobs), "by_dept": dict(by),
                      "jobs": jobs[:60], "reposted": sum(1 for j in jobs if j["reposted"])}
        if company and (company["hiring"].get("openings_count") is not None) and \
                abs((company["hiring"]["openings_count"] or 0) - len(jobs)) > 10:
            warnings.append("Open-role counts disagree: company record says %s, job search returned %d. "
                            "Job search is used; roles are classified from titles." %
                            (company["hiring"]["openings_count"], len(jobs)))

    return {
        "window": {"start": window_start, "end": today.isoformat(), "months": months},
        "counts": {"pulled": len(people), "in_window": sum(kinds.values()), "external": n_ext,
                   "new": kinds["new"], "returning": kinds["returning"], "relisted": kinds["relisted"],
                   "unplaced": unplaced_n, "outside_window": outside,
                   "pulled_total_reported": pulled_total, "truncated": truncated,
                   "current_profiles": current_profiles, "intern_conversions": intern_conv},
        "relisted_examples": relisted_examples,
        "monthly": {"external": {m: ext_by_month.get(m, 0) for m in months},
                    "relisted": {m: relisted_by_month.get(m, 0) for m in months}},
        "depts": depts,
        "overall_momentum": momentum([pdate(p["start"]) for p, _ in ext], today, truncated),
        "prev_employers": [{"name": disp_all[k], "n": n, "cid": k if isinstance(k, int) else None}
                           for k, n in prev_all.most_common(40)],
        "senior": {"counts": dict(senior_counts), "list": senior[:40], "audit": senior_audit},
        "exits": exits,
        "headcount": hc, "open_roles": open_roles, "evidence": evidence, "warnings": warnings,
        "thresholds": {"relist_gap_days": gap, "momentum_split_days": MOMENTUM_SPLIT_DAYS,
                       "min_total_for_label": MIN_TOTAL_FOR_LABEL, "grow_ratio": GROW_RATIO,
                       "fade_ratio": FADE_RATIO},
    }
