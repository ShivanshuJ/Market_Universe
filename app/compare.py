"""Side-by-side comparison of saved runs (rivals), including talent that moved between them.
Pure code over saved results: no network, no credits."""


def _pct(x):
    return "%d%%" % round(100 * x)


def compare(results):
    cos = []
    for r in results:
        a, c = r["analysis"], r["company"]
        hc = (a.get("headcount") or {}).get("total")
        ex = a.get("exits") or {}
        ext = a["counts"]["external"]
        cos.append({
            "id": c["id"], "name": c["name"], "domain": c.get("domain"), "headcount": hc, "external": ext,
            "intensity": round(100.0 * ext / hc, 1) if hc else None,
            "pace": a["overall_momentum"], "left": ex.get("left"), "net": ex.get("net_total"),
            "senior": len((a.get("senior") or {}).get("list") or []), "window": a["window"]["start"],
            "capped": bool(a["counts"].get("truncated")),
            "unplaced_share": round(a["counts"]["unplaced"] / ext, 3) if ext else 0,
            "depts": {d["name"]: {"n": d["external"], "share": d["share"], "label": d["momentum"]["label"]}
                      for d in a["depts"]},
            "prev": a.get("prev_employers") or [], "dest": ex.get("destinations") or [],
        })

    totals = {}
    for c in cos:
        for k, v in c["depts"].items():
            if k != "Unplaced":
                totals[k] = totals.get(k, 0) + v["n"]
    dept_order = [k for k, _ in sorted(totals.items(), key=lambda kv: -kv[1])][:9]
    matrix = [{"dept": d, "cells": [c["depts"].get(d, {"n": 0, "share": 0, "label": "-"}) for c in cos]} for d in dept_order]

    ids = {c["id"]: c for c in cos}
    flows = {}
    for b in cos:  # b hired from a
        for pe in b["prev"]:
            if pe.get("cid") in ids and pe["cid"] != b["id"]:
                f = flows.setdefault((pe["cid"], b["id"]), {"from": ids[pe["cid"]]["name"], "to": b["name"],
                                                           "hired_side": 0, "exit_side": 0})
                f["hired_side"] += pe["n"]
    for a_ in cos:  # a_ lost people who now work at b
        for d in a_["dest"]:
            if d.get("cid") in ids and d["cid"] != a_["id"]:
                f = flows.setdefault((a_["id"], d["cid"]), {"from": a_["name"], "to": ids[d["cid"]]["name"],
                                                           "hired_side": 0, "exit_side": 0})
                f["exit_side"] += d["n"]
    flow_list = sorted(flows.values(), key=lambda f: -(f["hired_side"] + f["exit_side"]))

    feeders = {}
    for c in cos:
        for pe in c["prev"]:
            key = pe.get("cid") or pe["name"].lower()
            if pe.get("cid") in ids:
                continue
            f = feeders.setdefault(key, {"name": pe["name"], "by": {}, "total": 0})
            f["by"][c["name"]] = f["by"].get(c["name"], 0) + pe["n"]
            f["total"] += pe["n"]
    shared = sorted([f for f in feeders.values() if len(f["by"]) >= 2], key=lambda f: -f["total"])[:10]

    insights, caveats = [], []
    inten = [c for c in cos if c["intensity"] is not None]
    if len(inten) >= 2:
        hi = max(inten, key=lambda c: c["intensity"])
        lo = min(inten, key=lambda c: c["intensity"])
        insights.append("Hiring intensity (external hires as a share of headcount): %s is highest at %.1f%% (%d hires, "
                        "%s people); %s is lowest at %.1f%%." % (hi["name"], hi["intensity"], hi["external"],
                                                                format(hi["headcount"], ","), lo["name"], lo["intensity"]))
    for d in dept_order[:4]:
        row = [(c["name"], c["depts"].get(d, {"share": 0, "n": 0})) for c in cos]
        top = max(row, key=lambda x: x[1]["share"])
        insights.append("%s: the largest share of new hires is at %s (%s, %d people)." % (
            d, top[0], _pct(top[1]["share"]), top[1]["n"]))
    for f in flow_list[:3]:
        s = "%d people hired by %s came from %s" % (f["hired_side"], f["to"], f["from"]) if f["hired_side"] else None
        t = "%d people who left %s now work at %s" % (f["exit_side"], f["from"], f["to"]) if f["exit_side"] else None
        check = ""
        if f["hired_side"] and f["exit_side"]:
            check = " (the hiring side and the exit side %s)" % ("agree" if f["hired_side"] == f["exit_side"] else "differ slightly")
        insights.append("Talent moving between rivals: " + "; ".join(x for x in (s, t) if x) + check + ".")
    if not flow_list:
        insights.append("No tracked hires moved directly between these companies in the window.")
    if shared:
        f = shared[0]
        insights.append("%s supplied people to %d of the companies (%s)." % (
            f["name"], len(f["by"]), ", ".join("%s %d" % kv for kv in f["by"].items())))
    paces = [c for c in cos if c["pace"]["label"] not in ("too few to judge",) and not c["pace"]["label"].startswith("not")]
    if paces:
        insights.append("Hiring pace (last 6 months vs the 6 months before): " + "; ".join(
            "%s %d vs %d (%s)" % (c["name"], c["pace"]["last6"], c["pace"]["prev"], c["pace"]["label"]) for c in paces) + ".")
    if len({c["window"] for c in cos}) > 1:
        caveats.append("The runs use different window start dates (%s), so counts are not strictly comparable." %
                       ", ".join(sorted({c["window"] for c in cos})))
    for c in cos:
        if c["capped"]:
            caveats.append("%s was capped, so its numbers are a lower bound." % c["name"])
        if c["unplaced_share"] > 0.25:
            caveats.append("%s has %s of hires with no department, so its team shares are less reliable." % (
                c["name"], _pct(c["unplaced_share"])))
    caveats.append("Moves between rivals are only counted when the previous employer's company record is the same one "
                   "as the rival (matched by id, not by name).")
    return {"companies": [{k: v for k, v in c.items() if k not in ("prev", "dest", "depts")} for c in cos],
            "matrix": matrix, "flows": flow_list, "shared_feeders": shared, "insights": insights, "caveats": caveats}
