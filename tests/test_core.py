"""Run: python -m unittest discover -s tests -v   (no network, no credits)"""
import datetime as dt
import json
import os
import tempfile
import unittest

from app import analysis, brief
from app.config import ROOT
from app.crustdata import Client
from app.pipeline import execute, new_run
from app.store import Store

CID = 5894
TODAY = dt.date(2026, 11, 6)


def person(pid, start, dept="Engineering & Technology", sub="Software Engineering", past=None, name="P"):
    return {"id": pid, "cid": CID, "name": name + str(pid), "title": "SDE", "start": start, "seniority": "Entry Level",
            "dept": dept, "subdept": sub, "confident": True, "n_current_at_company": 1, "past": past or []}


class Classify(unittest.TestCase):
    def test_new_when_no_earlier_role_here(self):
        p = person(1, "2026-03-01", past=[{"cid": 99, "name": "Flipkart", "title": "x", "start": "2020-01-01", "end": "2026-02-01"}])
        self.assertEqual(analysis.classify(p), "new")

    def test_relisted_when_earlier_same_company_role_ended_just_before(self):
        p = person(2, "2026-07-01", past=[{"cid": CID, "name": "Groww", "title": "x", "start": "2023-07-01", "end": "2026-06-01"}])
        self.assertEqual(analysis.classify(p), "relisted")

    def test_relisted_when_earlier_role_is_open_ended_or_overlaps(self):
        p = person(3, "2026-07-01", past=[{"cid": CID, "name": "Groww", "title": "x", "start": "2023-07-01", "end": ""}])
        self.assertEqual(analysis.classify(p), "relisted")

    def test_returning_after_long_gap_counts_as_a_hire(self):
        p = person(4, "2026-07-01", past=[{"cid": CID, "name": "Groww", "title": "x", "start": "2019-01-01", "end": "2022-01-01"}])
        self.assertEqual(analysis.classify(p), "returning")


class Analyze(unittest.TestCase):
    def test_relisted_never_inflate_hires_and_unplaced_is_not_guessed(self):
        ppl = [person(1, "2026-04-01"), person(2, "2026-05-01", dept=None, sub=None),
               person(3, "2026-04-01", past=[{"cid": CID, "name": "Groww", "title": "x", "start": "2020-01-01", "end": "2026-03-15"}])]
        a = analysis.analyze(ppl, "2025-11-01", TODAY)
        self.assertEqual(a["counts"]["external"], 2)
        self.assertEqual(a["counts"]["relisted"], 1)
        self.assertEqual(a["counts"]["unplaced"], 1)
        self.assertIn("Unplaced", [d["name"] for d in a["depts"]])
        self.assertTrue(any("re-recorded" in w for w in a["warnings"]))

    def test_same_person_listed_twice_in_one_dept_is_counted_by_profile_not_role(self):
        a = analysis.analyze([person(1, "2026-04-01")], "2025-11-01", TODAY)
        self.assertEqual(a["counts"]["external"], 1)

    def test_people_before_window_are_ignored_not_counted(self):
        a = analysis.analyze([person(1, "2025-01-01")], "2025-11-01", TODAY)
        self.assertEqual(a["counts"]["external"], 0)
        self.assertEqual(a["counts"]["outside_window"], 1)

    def test_momentum_labels(self):
        d = lambda s: dt.date.fromisoformat(s)
        grow = [d("2026-08-01")] * 9 + [d("2026-01-01")] * 3
        fade = [d("2026-08-01")] * 2 + [d("2026-01-01")] * 10
        self.assertEqual(analysis.momentum(grow, TODAY)["label"], "growing")
        self.assertEqual(analysis.momentum(fade, TODAY)["label"], "fading")
        self.assertEqual(analysis.momentum([d("2026-08-01")] * 3, TODAY)["label"], "too few to judge")

    def test_team_made_of_one_vague_title_is_flagged_unreliable(self):
        ppl = [dict(person(i, "2026-04-01", dept="Retail & Hospitality", sub="Retail Store Management"),
                    title="Assistant Manager") for i in range(8)]
        a = analysis.analyze(ppl, "2025-11-01", TODAY)
        sub = a["depts"][0]["sub"][0]
        self.assertTrue(sub["unreliable"])
        self.assertTrue(any("left out of conclusions" in w for w in a["warnings"]))
        facts = brief.build_facts("X", a, CID)
        self.assertFalse(any("Retail Store Management" in f["text"] for f in facts))

    def test_capped_pull_switches_off_growth_labels(self):
        ppl = [person(i, "2026-09-01") for i in range(12)]
        a = analysis.analyze(ppl, "2025-11-01", TODAY, truncated=True)
        self.assertTrue(a["overall_momentum"]["label"].startswith("not comparable"))
        self.assertTrue(all(d["momentum"]["label"].startswith("not comparable") for d in a["depts"]))
        self.assertTrue(any("capped" in w for w in a["warnings"]))

    def test_headcount_conflict_is_flagged(self):
        co = {"range": "501-1000", "headcount": {"total": 3155, "last_date": "2026-09-25", "growth_percent": {},
              "by_role": {}, "timeseries": []}, "hiring": {"openings_count": 1}}
        a = analysis.analyze([person(1, "2026-04-01")], "2025-11-01", TODAY, company=co)
        self.assertTrue(a["headcount"]["conflict"])
        self.assertTrue(any("disagree" in w for w in a["warnings"]))

    def test_headcount_series_is_flagged_when_old(self):
        co = {"range": "501-1000", "headcount": {"total": 600, "last_date": "2026-08-01", "growth_percent": {},
              "by_role": {}, "timeseries": []}, "hiring": {"openings_count": None}}
        a = analysis.analyze([], "2025-11-01", TODAY, company=co)
        self.assertFalse(a["headcount"]["conflict"])
        self.assertTrue(any("days old" in w for w in a["warnings"]))


class Brief(unittest.TestCase):
    def test_model_brief_with_invented_number_is_rejected(self):
        facts = [{"id": "F1", "text": "235 external joiners.", "source": "x", "evidence": []}]
        ok, probs = brief.verify_brief({"headline": "There were 999 hires", "findings": [
            {"text": "235 joiners", "fact_ids": ["F1"]}], "actions": []}, facts)
        self.assertFalse(ok)
        self.assertIn("999", probs[0])

    def test_model_brief_citing_missing_fact_is_rejected(self):
        facts = [{"id": "F1", "text": "235 external joiners.", "source": "x", "evidence": []}]
        ok, _ = brief.verify_brief({"headline": "ok", "findings": [{"text": "235", "fact_ids": ["F9"]}], "actions": []}, facts)
        self.assertFalse(ok)

    def test_brief_with_only_fact_numbers_passes(self):
        facts = [{"id": "F1", "text": "235 external joiners, 14.6% growth.", "source": "x", "evidence": []}]
        ok, _ = brief.verify_brief({"headline": "235 hires", "findings": [{"text": "growth 14.6%", "fact_ids": ["F1"]}],
                                    "actions": []}, facts)
        self.assertTrue(ok)


class EndToEndOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        os.environ["XRAY_DB"] = self.db
        os.environ.pop("XRAY_CRASH_AFTER", None)
        self.store = Store(self.db)

    def test_full_run_on_saved_groww_fixtures(self):
        rid = new_run(self.store, "Which teams at Groww are growing fastest?", offline=True)
        self.assertEqual(execute(self.store, rid), "done")
        res = self.store.get_run(rid)["result"]
        self.assertEqual(res["company"]["id"], 5894)
        c = res["analysis"]["counts"]
        self.assertEqual(c["external"] + c["relisted"], c["in_window"])
        self.assertGreater(c["relisted"], 100)  # the re-recorded-role trap is really in the data
        self.assertTrue(all(f["text"] for f in res["facts"]))

    def test_resume_skips_finished_steps(self):
        rid = new_run(self.store, "Groww hiring", offline=True)
        self.store.step_put(rid, "parse", "done", output={"company_query": "Groww", "domain": None, "message": "kept"})
        execute(self.store, rid)
        evs = [e["kind"] for e in self.store.events_after(rid, 0)]
        self.assertIn("step_skipped", evs)

    def test_unknown_company_asks_a_human_instead_of_guessing(self):
        rid = new_run(self.store, "Which teams at Zzyzx are growing?", offline=True)
        self.assertEqual(execute(self.store, rid), "needs_input")
        self.assertEqual(self.store.get_run(rid)["status"], "needs_input")

    def test_request_without_a_company_asks_a_human(self):
        rid = new_run(self.store, "which teams are growing fastest?", offline=True)
        self.assertEqual(execute(self.store, rid), "needs_input")


def _m(cid, name, domain, rng):
    return {"confidence_score": 1.0, "company_data": {"crustdata_company_id": cid, "basic_info": {
        "name": name, "primary_domain": domain, "employee_count_range": rng, "company_type": "Privately Held"}}}


class FakeClient:
    """Answers Company Identify from a table: {(lowercased name, exact?): [matches]}."""
    def __init__(self, table):
        self.table = table

    def call(self, path, body, **kw):
        n = body["names"][0]
        return [{"matched_on": n, "matches": self.table.get((n.lower(), bool(body.get("exact_match"))), [])}]


class Resolve(unittest.TestCase):
    def ctx(self, q, table):
        from app.pipeline import step_parse
        c = {"run": {"request": q, "params": {}}, "client": FakeClient(table), "out": {}, "emit": lambda *a: None}
        c["out"]["parse"] = step_parse(c)
        return c

    def test_shorter_name_matching_a_far_bigger_company_asks_a_human(self):
        from app.pipeline import NeedsHuman, step_resolve
        t = {("groww inc", True): [_m(2, "Groww Inc", "groww.ca", "2-10")],
             ("groww", True): [_m(1, "Groww", "groww.in", "501-1000")]}
        with self.assertRaises(NeedsHuman) as cm:
            step_resolve(self.ctx("hiring at Groww Inc", t))
        self.assertIn("groww.in", str(cm.exception))

    def test_legal_suffixes_are_tried_and_the_assumption_is_reported(self):
        from app.pipeline import step_resolve
        t = {("cashfree", True): [_m(7, "Cashfree", "cashfree.com", "501-1000")]}
        out = step_resolve(self.ctx("hiring at Cashfree Payments Pvt Ltd", t))
        self.assertEqual(out["company"]["id"], 7)
        self.assertTrue(out["assumed"])

    def test_near_match_is_used_but_flagged(self):
        from app.pipeline import step_resolve
        t = {("gorww", False): [_m(1, "Groww", "groww.in", "501-1000")]}
        out = step_resolve(self.ctx("hiring at Gorww", t))
        self.assertEqual(out["company"]["id"], 1)
        self.assertIn("taken to mean", out["assumed"])

    def test_real_incident_no_broker_is_not_read_as_no_and_never_runs_on_a_placeholder(self):
        from app.pipeline import NeedsHuman, phrase_company, step_resolve
        # "No broker" (meant NoBroker) used to be read as "No", fuzzy-matched "No-Company" and ran
        self.assertEqual(phrase_company("Which teams at No broker are growing fastest, and what next?"), "No broker")
        t = {("no broker", False): [_m(9, "No-Company", "nocompany.no", "10001+")]}
        with self.assertRaises(NeedsHuman):
            step_resolve(self.ctx("Which teams at No broker are growing fastest?", t))

    def test_weak_near_match_asks_instead_of_guessing(self):
        from app.pipeline import NeedsHuman, step_resolve
        t = {("no broker", False): [_m(9, "Brokerly Holdings", "brokerly.com", "10001+")]}
        with self.assertRaises(NeedsHuman) as cm:
            step_resolve(self.ctx("Which teams at No broker are growing fastest?", t))
        self.assertIn("Give the website", str(cm.exception))

    def test_company_phrase_extraction_on_the_requests_we_have_seen(self):
        from app.pipeline import phrase_company
        cases = {
            "Which teams at Groww are growing fastest, and what does it say about what they will invest in next?": "Groww",
            "Show me how Cashfree is hiring and which teams are growing": "Cashfree",
            "What is CRED investing in? Show me which teams are growing.": "CRED",
            "what is going on at Cashfree Payments Pvt Ltd": "Cashfree Payments Pvt Ltd",
            "hiring at Acme": "Acme",
            "Which teams at Optiver are growing fastest and have people graduated from IIT": "Optiver",
        }
        for text, want in cases.items():
            self.assertEqual(phrase_company(text), want, text)
        self.assertEqual(phrase_company("teams?"), "")

    def test_placeholder_entities_are_never_resolved(self):
        from app.pipeline import NeedsHuman, step_resolve
        t = {("freelance", True): [_m(5, "Freelance", "freelance.com", "10001+")]}
        with self.assertRaises(NeedsHuman):
            step_resolve(self.ctx("hiring at Freelance", t))

    def test_small_typo_is_still_accepted(self):
        from app.pipeline import _similar
        self.assertGreaterEqual(_similar("Gorww", "Groww"), 0.8)
        self.assertLess(_similar("No broker", "No-Company"), 0.8)

    def test_two_equally_big_companies_with_the_same_name_ask_a_human(self):
        from app.pipeline import NeedsHuman, step_resolve
        t = {("acme", True): [_m(1, "ACME", "acme.ua", "11-50"), _m(2, "ACME", "acmefurnace.net", "11-50")]}
        with self.assertRaises(NeedsHuman):
            step_resolve(self.ctx("hiring at Acme", t))


class Guards(unittest.TestCase):
    def test_budget_guard_stops_before_any_network_call(self):
        from app.crustdata import BudgetExceeded
        st = Store(os.path.join(tempfile.mkdtemp(), "b.db"))
        cl = Client("k", st, budget=1.0)
        cl.spent = 1.0
        with self.assertRaises(BudgetExceeded):
            cl.call("/person/search", {"x": 1})

    def test_different_wording_gives_identical_numbers(self):
        os.environ["XRAY_DB"] = os.path.join(tempfile.mkdtemp(), "w.db")
        st = Store(os.environ["XRAY_DB"])
        counts = []
        for q in ("Which teams at Groww are growing fastest?", "how is GROWW hiring lately", "Tell me what Groww is investing in"):
            rid = new_run(st, q, offline=True)
            self.assertEqual(execute(st, rid), "done")
            counts.append(st.get_run(rid)["result"]["analysis"]["counts"])
        self.assertEqual(counts[0], counts[1])
        self.assertEqual(counts[0], counts[2])


def raw_leaver(pid, left_end, still_here=False, dest=None, seniority="Entry Level", title="SDE"):
    cur = [{"crustdata_company_id": dest[0], "name": dest[1], "title": "Eng", "start_date": "2026-06-01", "is_default": True}] if dest else []
    if still_here:
        cur.append({"crustdata_company_id": CID, "name": "Groww", "title": "SDE 2", "start_date": left_end + "T00:00:00"})
    return {"crustdata_person_id": pid, "basic_profile": {"name": "L%d" % pid}, "experience": {"employment_details": {
        "current": cur, "past": [{"crustdata_company_id": CID, "name": "Groww", "title": title, "start_date": "2024-01-01T00:00:00",
                                  "end_date": left_end + "T00:00:00", "seniority_level": seniority}]}}}


class Exits(unittest.TestCase):
    def test_promotion_is_not_an_exit_and_leavers_are_counted_with_destination(self):
        raw = [raw_leaver(1, "2026-05-01", still_here=True), raw_leaver(2, "2026-05-10", dest=(77, "Rival")),
               raw_leaver(3, "2026-06-10", dest=None, seniority="Vice President", title="VP Product")]
        leavers = [analysis.slim_leaver(p, CID) for p in raw]
        a = analysis.analyze([person(9, "2026-04-01")], "2025-11-01", TODAY, leavers=leavers)
        ex = a["exits"]
        self.assertEqual((ex["role_ends"], ex["internal_moves"], ex["left"]), (3, 1, 2))
        self.assertEqual(ex["net_total"], 1 - 2)
        self.assertEqual(ex["destinations"][0]["cid"], 77)
        self.assertEqual(ex["senior_leavers"][0]["level"], "Vice President")
        self.assertTrue(any("Exits:" in w for w in a["warnings"]))

    def test_net_disagreeing_with_headcount_series_is_flagged(self):
        co = {"range": "501-1000", "headcount": {"total": 700, "last_date": "2026-11-01", "growth_percent": {}, "by_role": {},
              "timeseries": [{"date": "2025-12-01", "employee_count": 500}, {"date": "2026-11-01", "employee_count": 700}]},
              "hiring": {"openings_count": None}}
        leavers = [analysis.slim_leaver(raw_leaver(i, "2026-05-01", dest=(5, "X")), CID) for i in range(30)]
        a = analysis.analyze([person(1, "2026-04-01")], "2025-11-01", TODAY, company=co, leavers=leavers)
        self.assertTrue(any("headcount series changed" in w for w in a["warnings"]))


class SeniorAndCompare(unittest.TestCase):
    def test_senior_hires_are_listed_newest_first_within_level(self):
        ppl = [dict(person(1, "2026-02-01"), seniority="Director"), dict(person(2, "2026-05-01"), seniority="Director"),
               dict(person(3, "2026-03-01"), seniority="Vice President"), person(4, "2026-03-01")]
        s = analysis.analyze(ppl, "2025-11-01", TODAY)["senior"]
        self.assertEqual([x["id"] for x in s["list"]], [3, 2, 1])
        self.assertEqual(s["counts"], {"Vice President": 1, "Director": 2})

    def test_talent_flow_between_rivals_is_matched_by_company_id(self):
        from app.compare import compare

        def res(cid, name, prev, dest):
            ppl = [dict(person(i, "2026-04-01"), cid=cid, past=[{"cid": p, "name": n, "title": "x", "start": "2020-01-01",
                                                                 "end": "2026-03-01"}]) for i, (p, n) in enumerate(prev)]
            a = analysis.analyze(ppl, "2025-11-01", TODAY, company={"range": "501-1000", "headcount": {
                "total": 1000, "last_date": "2026-11-01", "growth_percent": {}, "by_role": {}, "timeseries": []},
                "hiring": {"openings_count": None}})
            a["exits"] = {"left": 5, "net_total": 0, "destinations": dest}
            return {"company": {"id": cid, "name": name}, "analysis": a}
        A = res(1, "Alpha", [(2, "Beta"), (9, "Other")], [])
        B = res(2, "Beta", [(9, "Other")], [{"name": "Alpha", "cid": 1, "n": 1}])
        out = compare([A, B])
        flow = [f for f in out["flows"] if f["from"] == "Beta" and f["to"] == "Alpha"][0]
        self.assertEqual(flow["hired_side"], 1)
        self.assertTrue(any(f["name"] == "Other" and len(f["by"]) == 2 for f in out["shared_feeders"]))


class Export(unittest.TestCase):
    def test_exports_render_and_are_marked_as_drafts(self):
        from app import export
        os.environ["XRAY_DB"] = os.path.join(tempfile.mkdtemp(), "e.db")
        st = Store(os.environ["XRAY_DB"])
        rid = new_run(st, "Which teams at Groww are growing fastest?", offline=True)
        execute(st, rid)
        res = st.get_run(rid)["result"]
        self.assertIn("Draft only", export.email_draft(res))
        self.assertIn("## Sources", export.render_markdown(res))
        self.assertIn("<h1>", export.render_html(res))
        self.assertIsNotNone(res["analysis"]["exits"])  # offline fixtures now carry exits too


class ModelPath(unittest.TestCase):
    """The model path is exercised with a stand-in for the API (no key needed)."""

    def setUp(self):
        os.environ["XRAY_DB"] = os.path.join(tempfile.mkdtemp(), "m.db")
        st = Store(os.environ["XRAY_DB"])
        rid = new_run(st, "Which teams at Groww are growing fastest?", offline=True)
        execute(st, rid)
        self.res = st.get_run(rid)["result"]

    def _reply(self, tldr):
        f1 = self.res["facts"][0]
        return json.dumps({"headline": f1["text"], "tldr": tldr,
                           "findings": [{"text": f1["text"], "fact_ids": [f1["id"]], "confidence": "high"}],
                           "inference": {"text": "A cautious read.", "confidence": "low", "basis_fact_ids": [f1["id"]]},
                           "actions": []})

    def test_checked_model_brief_is_accepted(self):
        from unittest import mock
        n = self.res["analysis"]["counts"]["external"]
        with mock.patch.object(brief, "call_model", return_value=self._reply("Groww added %d real hires." % n)):
            b, why = brief.llm_brief("Groww", self.res["analysis"], self.res["facts"], "k", "m")
        self.assertIsNone(why)
        self.assertTrue(b["generated_by"].startswith("model"))
        self.assertIn(str(n), b["tldr"])

    def test_model_summary_with_an_invented_number_falls_back(self):
        from unittest import mock
        with mock.patch.object(brief, "call_model", return_value=self._reply("Groww added 99999 real hires.")):
            b, why = brief.llm_brief("Groww", self.res["analysis"], self.res["facts"], "k", "m")
        self.assertIsNone(b)
        self.assertIn("99999", why)

    def test_template_always_has_a_plain_tldr_built_from_numbers(self):
        t = self.res["brief"]["tldr"]
        self.assertIn(str(self.res["analysis"]["counts"]["external"]), t)


RELIST = [{"cid": CID, "name": "Groww", "title": "Analyst", "start": "2023-01-01", "end": "2026-03-15"}]


def court_for(people, company=None, **kw):
    from app import court
    jobs_total = kw.pop("jobs_total", None)
    a = analysis.analyze(people, "2025-11-01", TODAY, company=company, **kw)
    return a, court.run_court(a, people, "2025-11-01", TODAY, company=company, jobs_total=jobs_total)


class ClaimCourt(unittest.TestCase):
    def verdicts(self, ct):
        return {c["id"]: c["verdict"] for c in ct["claims"]}

    def test_naive_joiner_count_is_killed_when_many_are_rerecorded_roles(self):
        people = [person(i, "2026-02-01") for i in range(10)] + [person(100 + i, "2026-04-01", past=RELIST) for i in range(10)]
        _, ct = court_for(people)
        c1 = [c for c in ct["claims"] if c["id"] == "C1"][0]
        self.assertEqual(c1["verdict"], "killed")
        self.assertEqual((c1["naive"]["value"], c1["audited"]["value"]), (20, 10))
        self.assertIn("20 'joiners' became 10", ct["summary"]["headline_kill"])

    def test_intern_conversions_are_shown_as_a_generous_reading_not_hidden(self):
        intern = [{"cid": CID, "name": "Groww", "title": "SDE Intern", "start": "2025-08-01", "end": "2026-03-20"}]
        people = [person(i, "2026-02-01") for i in range(6)] + [dict(person(50 + i, "2026-04-01", past=intern), title="SDE 1") for i in range(4)]
        a, ct = court_for(people)
        self.assertEqual(a["counts"]["intern_conversions"], 4)
        c1 = [c for c in ct["claims"] if c["id"] == "C1"][0]
        self.assertIn("up to 10", c1["audited"]["note"])
        self.assertTrue(any(t["name"] == "Intern conversions" for t in c1["tests"]))

    def test_spike_month_made_of_rerecorded_roles_is_killed(self):
        people = []
        for m in ("2026-01", "2026-02", "2026-03", "2026-05", "2026-06"):
            people += [person(len(people) + i, m + "-10") for i in range(4)]
        people += [person(500 + i, "2026-04-10", past=RELIST) for i in range(30)] + [person(900, "2026-04-10")]
        _, ct = court_for(people)
        spikes = [c for c in ct["claims"] if c["id"].startswith("C2")]
        self.assertTrue(spikes and spikes[0]["verdict"] == "killed")
        self.assertIn("2026-04", spikes[0]["title"])

    def test_pace_label_is_stable_for_flat_hiring_and_flips_when_last_month_is_dropped(self):
        from app import court
        self.assertEqual({court.pace_label([8] * 13, k) for k in (0, 1, 2)}, {"steady"})
        lagged = [10] * 7 + [6] * 5 + [0]  # only the unfinished last month collapses
        self.assertEqual((court.pace_label(lagged, 0), court.pace_label(lagged, 1)), ("fading", "steady"))

    def test_assistant_tagged_senior_is_audited_out(self):
        people = [dict(person(1, "2026-03-01"), seniority="CXO", title="Executive Assistant to Chief Executive Officer"),
                  dict(person(2, "2026-03-01"), seniority="CXO", title="Chief Financial Officer"),
                  dict(person(3, "2026-03-01"), seniority="Vice President", title="Assistant Vice President - Risk")]
        a, ct = court_for(people)
        self.assertEqual(a["senior"]["audit"], {"tagged": 3, "kept": 2, "removed": [{"id": 1, "title": "Executive Assistant to Chief Executive Officer", "level": "CXO"}]})
        c6 = [c for c in ct["claims"] if c["id"] == "C6"][0]
        self.assertEqual(c6["verdict"], "killed" if 1 / 3 >= .25 else "weakened")

    def test_conflicting_size_sources_are_killed_and_coverage_gives_an_upper_bound(self):
        co = {"range": "501-1000", "headcount": {"total": 3000, "last_date": "2026-11-01", "growth_percent": {}, "by_role": {}, "timeseries": []},
              "hiring": {"openings_count": 1}}
        people = [person(i, "2026-03-01") for i in range(10)]
        a, ct = court_for(people, company=co, jobs_total=296, current_profiles=2000)
        v = self.verdicts(ct)
        self.assertEqual((v["C8"], v["C9"], v["C10"]), ("killed", "killed", "weakened"))
        c10 = [c for c in ct["claims"] if c["id"] == "C10"][0]
        self.assertEqual(c10["audited"]["value"], round(10 / (2000 / 3000)))

    def test_net_that_contradicts_the_series_is_killed(self):
        co = {"range": "501-1000", "headcount": {"total": 700, "last_date": "2026-11-01", "growth_percent": {}, "by_role": {},
              "timeseries": [{"date": "2025-12-01", "employee_count": 500}, {"date": "2026-11-01", "employee_count": 700}]},
              "hiring": {"openings_count": None}}
        leavers = [analysis.slim_leaver(raw_leaver(i, "2026-05-01", dest=(5, "X")), CID) for i in range(30)]
        _, ct = court_for([person(1, "2026-04-01")], company=co, leavers=leavers)
        self.assertEqual(self.verdicts(ct)["C7"], "killed")


WEALTH = "Wealth & Relationship Management"


def wealth_people(n=14, extra_senior=True):
    """n wealth hires spread over Apr-Oct 2026, mostly from the same two banks, plus a VP of Private Wealth."""
    out = []
    for i in range(n):
        bank = "Bank A" if i % 2 == 0 else "Bank B"
        prev = [{"cid": 900 + (i % 2), "name": bank, "title": "RM", "start": "2020-01-01", "end": "2026-02-01"}]
        month = 4 + (i % 7)
        out.append(dict(person(300 + i, "2026-%02d-10" % month, dept="Finance & Accounting", sub=WEALTH, past=prev), title="Wealth Partner"))
    if extra_senior:
        out.append(dict(person(399, "2026-05-01", dept="Finance & Accounting", sub=WEALTH,
                               past=[{"cid": 900, "name": "Bank A", "title": "VP", "start": "2018-01-01", "end": "2026-03-01"}]),
                        seniority="Vice President", title="Vice President - Private Wealth"))
    out += [person(500 + i, "2026-06-10", sub="Software Engineering") for i in range(10)]
    return out


class ThesisEngine(unittest.TestCase):
    JOBS = [{"title": "Relationship Manager - Wealth"}, {"title": "Private Wealth Advisor"}] + [{"title": "Backend Engineer"}] * 40

    def theses(self, people, peers, leavers=None):
        from app import thesis
        a = analysis.analyze(people, "2025-11-01", TODAY, leavers=leavers)
        return thesis.build_theses(a, "Acme", self.JOBS, peers)

    def test_a_team_nobody_else_has_gets_a_strong_thesis_with_an_evidence_chain(self):
        peers = [{"company": "Peer", "n": 100, "shares": {WEALTH: 0.0, "Software Engineering": 0.2}}]
        t = self.theses(wealth_people(), peers, leavers=[])[0]
        self.assertEqual(t["theme"], WEALTH)
        res = {s["id"]: s["result"] for s in t["signals"]}
        self.assertEqual((res["distinct"], res["anchor"], res["feeder"], res["demand"], res["momentum"]), ("pass",) * 5)
        self.assertEqual(t["confidence"], "strong")
        self.assertGreaterEqual(t["lift"], 2)
        self.assertIn("is building out", t["statement"])
        self.assertIn("60 days", t["falsifier"])

    def test_the_biggest_team_is_not_a_thesis_when_every_peer_has_it_too(self):
        peers = [{"company": "Peer", "n": 100, "shares": {WEALTH: 0.07, "Software Engineering": 0.36}}]
        out = {t["theme"]: t for t in self.theses(wealth_people(), peers, leavers=[])}
        se = out["Software Engineering"]
        self.assertEqual([s["result"] for s in se["signals"] if s["id"] == "distinct"], ["fail"])
        self.assertNotEqual(se["confidence"], "strong")

    def test_without_peers_distinctiveness_is_skipped_not_invented(self):
        t = self.theses(wealth_people(), [], leavers=[])[0]
        self.assertEqual([s["result"] for s in t["signals"] if s["id"] == "distinct"], ["skip"])
        self.assertIsNone(t["lift"])

    def test_a_revolving_door_fails_the_exits_check(self):
        peers = [{"company": "Peer", "n": 100, "shares": {WEALTH: 0.0}}]
        leavers = [analysis.slim_leaver(raw_leaver(i, "2026-06-01", dest=(5, "X"), title="Wealth Partner"), CID) for i in range(16)]
        t = self.theses(wealth_people(), peers, leavers=leavers)[0]
        self.assertEqual([s["result"] for s in t["signals"] if s["id"] == "exits"], ["fail"])

    def test_keywords_come_from_the_team_name(self):
        from app import thesis
        self.assertEqual(thesis.keywords(WEALTH), ["wealth", "relationship"])

    def test_a_full_run_states_a_thesis_and_puts_it_on_trial(self):
        os.environ["XRAY_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
        st = Store(os.environ["XRAY_DB"])
        rid = new_run(st, "Which teams at Groww are growing fastest?", offline=True)
        self.assertEqual(execute(st, rid), "done")
        res = st.get_run(rid)["result"]
        self.assertTrue(res["thesis"]["theses"])
        self.assertTrue(any(c["id"] == "C13" for c in res["court"]["claims"]))
        self.assertTrue(res["brief"]["inference"]["text"].startswith(res["thesis"]["theses"][0]["statement"]))


class Predictions(unittest.TestCase):
    def test_hash_is_deterministic_and_changes_with_the_call(self):
        from app import court
        p = {"kind": "postings_floor", "due": "2027-01-01", "spec": {"floor": 80}, "statement": "x"}
        h1 = court.prediction_hash(5, "2026-11-06", p)
        self.assertEqual(h1, court.prediction_hash(5, "2026-11-06", dict(p)))
        self.assertNotEqual(h1, court.prediction_hash(5, "2026-11-06", dict(p, spec={"floor": 81})))

    def test_calibration_compares_the_rule_with_no_change(self):
        from app import court
        ts = [{"employee_count": 1000 + 20 * i} for i in range(20)]  # steady growth: the trend rule should beat "no change"
        cal = court.calibrate_headcount(ts)
        self.assertGreater(cal["windows"], 5)
        self.assertGreaterEqual(cal["trend_rate"], cal["flat_rate"])

    def test_due_predictions_are_scored_against_fresh_data_and_future_ones_are_left_alone(self):
        from app import court
        st = Store(os.path.join(tempfile.mkdtemp(), "p.db"))
        mk = lambda due, lo, hi: {"kind": "headcount_band", "due": due, "spec": {"lo": lo, "hi": hi}, "statement": "hc " + due}
        a, b = mk("2026-11-01", 3000, 3200), mk("2099-01-01", 1, 2)
        for p in (a, b):
            p["hash"] = court.prediction_hash(7, "2026-09-01", p)
        st.add_predictions("r", 7, "Co", "2026-09-01", [a, b])

        class Fake:
            def call(self, path, body, **kw):
                return [{"matches": [{"company_data": {"headcount": {"timeseries": [{"employee_count": 3100}]}}}]}]
        out = court.score_due(st, Fake(), TODAY)
        self.assertEqual([o["status"] for o in out], ["hit"])
        self.assertEqual({p["status"] for p in st.list_predictions()}, {"hit", "pending"})

    def test_a_full_run_stores_hashed_calls_and_a_court(self):
        os.environ["XRAY_DB"] = os.path.join(tempfile.mkdtemp(), "c.db")
        st = Store(os.environ["XRAY_DB"])
        rid = new_run(st, "Which teams at Groww are growing fastest?", offline=True)
        self.assertEqual(execute(st, rid), "done")
        res = st.get_run(rid)["result"]
        self.assertGreaterEqual(res["court"]["summary"]["killed"], 1)
        self.assertEqual(len(st.list_predictions()), len(res["court"]["predictions"]))
        self.assertTrue(all(len(p["id"]) == 64 for p in st.list_predictions()))
        self.assertIn("Market Universe rejected", res["brief"]["tldr"])


class CacheNeverRespends(unittest.TestCase):
    def test_second_identical_call_is_served_from_cache(self):
        tmp = tempfile.mkdtemp()
        st = Store(os.path.join(tmp, "c.db"))
        cl = Client("k", st, offline=True)
        body = {"names": ["Groww"], "exact_match": True}
        cl.call("/company/identify", body)
        st.cache_put("manual", "/x", {"a": 1}, 0)
        first = cl.cache_hits
        # offline answers are not cached; emulate a live response in the cache and check it is reused
        import hashlib
        key = hashlib.sha256(("POST" + "/company/identify" + json.dumps(body, sort_keys=True)).encode()).hexdigest()
        st.cache_put(key, "/company/identify", [{"cached": True}], 0.0)
        self.assertEqual(cl.call("/company/identify", body), [{"cached": True}])
        self.assertEqual(cl.cache_hits, first + 1)


if __name__ == "__main__":
    unittest.main()
