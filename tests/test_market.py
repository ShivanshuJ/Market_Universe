import datetime as dt
import unittest

from app import market


def series(vals, start=dt.date(2024, 1, 1)):
    return [{"date": (start + dt.timedelta(weeks=i)).isoformat(), "employee_count": v} for i, v in enumerate(vals)]


class FakeClient:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def call(self, path, body=None):
        self.calls.append((path, body))
        r = self.routes[path]
        return r(body) if callable(r) else r


class Pure(unittest.TestCase):
    def test_series_too_short(self):
        self.assertIsNone(market.series_stats(series([10, 11, 12])))

    def test_series_fall(self):
        vals = [100] * 10 + [400] * 10 + [400 - 10 * i for i in range(1, 31)] + [100] * 20
        st = market.series_stats(series(vals))
        self.assertEqual(st["peak"], 400)
        self.assertEqual(st["now"], 100)
        self.assertAlmostEqual(st["drop"], 0.75)
        self.assertGreater(st["steepest"]["drop"], 0.3)
        self.assertLessEqual(len(st["spark"]), 48)

    def test_series_growth(self):
        st = market.series_stats(series(list(range(100, 200))))
        self.assertGreater(st["g12"], 0)
        self.assertEqual(st["drop"], 0.0)

    def test_verdicts(self):
        self.assertEqual(market.perf_verdict(None), "unknown")
        self.assertEqual(market.perf_verdict(45), "surging")
        self.assertEqual(market.perf_verdict(10), "growing")
        self.assertEqual(market.perf_verdict(0), "steady")
        self.assertEqual(market.perf_verdict(-15), "shrinking")
        self.assertEqual(market.perf_verdict(-40), "contracting")

    def test_rival_score_prefers_close_size_and_rank(self):
        a = market.rival_score(0, 10, 500, 500)
        b = market.rival_score(9, 10, 2000, 500)
        self.assertGreater(a, b)
        self.assertEqual(market.size_closeness(0, 500), 0.0)

    def test_pick_themes_drops_generic(self):
        th = [{"theme": "Software Engineering"}, {"theme": "Data Science & Analytics"}, {"theme": "Product Management"}]
        self.assertEqual([t["theme"] for t in market.pick_themes(th)], ["Data Science & Analytics"])
        only_generic = [{"theme": "Software Engineering"}]
        self.assertEqual(len(market.pick_themes(only_generic)), 1)
        self.assertEqual(market.pick_themes([]), [])

    def test_future_score_monotonic(self):
        self.assertGreater(market.future_score(30, 100, 5, 20, 0, 10), market.future_score(3, 100, 0, 0, 5, 10))

    def test_related(self):
        self.assertTrue(market.related("Games24x7", "Games24x7 lays off staff"))
        self.assertFalse(market.related("Games24x7", "Unrelated company news"))
        self.assertFalse(market.related("The Private Limited", "anything"))


class Finders(unittest.TestCase):
    def test_fallen_filters_and_flags(self):
        big = series([50] * 5 + [500] * 10 + [150] * 30)
        small_peak = series([50] * 5 + [120] * 10 + [30] * 30)
        flat = series([400] * 45)

        def enrich(body):
            ts = {1: big, 2: small_peak, 3: flat}
            return [{"matches": [{"company_data": {"crustdata_company_id": i, "basic_info": {"name": "Co%d" % i, "primary_domain": "c%d.com" % i},
                                                   "headcount": {"timeseries": ts[i]}, "taxonomy": {"professional_network_industry": "X"},
                                                   "revenue": {"acquisition_status": "acquired" if i == 1 else None}}}]} for i in body["crustdata_company_ids"]]
        cl = FakeClient({"/company/search": {"companies": [{"crustdata_company_id": i} for i in (1, 2, 3, 99)]},
                         "/company/enrich": enrich,
                         "/web/search/live": {"results": [{"title": "Co1 collapses", "snippet": "x", "url": "u"}, {"title": "Other", "snippet": "y", "url": "v"}]}})
        out = market.find_fallen(cl, {"id": 99, "industry": "X", "country": None})
        self.assertEqual([x["name"] for x in out], ["Co1"])
        self.assertTrue(out[0]["acquired"])
        self.assertTrue(out[0]["same_industry"])
        self.assertEqual(len(out[0]["coverage"]), 1)
        self.assertEqual(out[0]["coverage"][0]["url"], "u")

    def test_future_requires_evidence_and_excludes_rivals(self):
        cands = [{"crustdata_company_id": i, "basic_info": {"name": "N%d" % i, "primary_domain": "n.com", "year_founded": 2022},
                  "headcount": {"total": 100, "growth_percent": {"12m": 30}}, "funding": {}} for i in (1, 2, 3)]

        def person(body):
            cid = body["filters"]["conditions"][0]["value"]
            return {"total_count": 10 if cid == 1 else 0}
        cl = FakeClient({"/company/search": {"companies": cands}, "/person/search": person, "/job/search": lambda b: {"total_count": 0}})
        out = market.find_future(cl, {"id": 50, "headcount": 1000, "industry": "Fintech", "country": None},
                                 [{"theme": "Data Science & Analytics"}], exclude_ids={2})
        self.assertEqual([x["id"] for x in out], [1])
        self.assertIn("smaller", out[0]["why_not_rival"])


if __name__ == "__main__":
    unittest.main()


class Dossier(unittest.TestCase):
    def test_build_dossier_reads(self):
        cd = {"crustdata_company_id": 1, "basic_info": {"name": "Acme", "year_founded": 2019},
              "headcount": {"total": 1000, "growth_absolute": {"yoy": 100}, "growth_percent": {"yoy": 11},
                            "by_role_percent": {"Engineering": 30.0, "Sales": 10.0, "Legal": 1.0},
                            "by_role_growth_6m_pct": {"Engineering": 5.0, "Sales": 40.0, "Legal": 90.0},
                            "by_region_percent": {"Pune": 40.0, "India": 80.0, "Maharashtra, India": 50.0, "Pune Area, India": 3.0, "Mumbai Metropolitan Region": 9.0}},
              "employee_reviews": {"work_life_balance_rating": 2.0, "culture_and_values_rating": 3.0, "compensation_and_benefits_rating": 4.0,
                                   "overall_rating": {"rating": 3.2, "total_count": 50}},
              "funding": {"total_investment_usd": 5e7, "milestones": [{"date": "2026-01-05", "amount_usd": 3e7, "round_type": "series_b", "investors": "VC", "is_fund": False}]},
              "news": [{"article_title": "Old", "article_publish_date": "2025-01-01"}, {"article_title": "New", "article_publish_date": "2026-01-01"}]}
        d = market.build_dossier(cd, 50, ["Dev"])
        self.assertEqual(d["teams"][0]["name"], "Engineering")
        self.assertEqual([c["name"] for c in d["cities"]], ["Pune"])  # roll-ups removed
        self.assertEqual(d["news"][0]["title"], "New")
        joined = " ".join(d["reads"])
        self.assertIn("Sales", joined)  # fastest team of size ignores tiny Legal
        self.assertNotIn("Legal", joined)
        self.assertIn("work-life balance lowest", joined)
        self.assertIn("5% of current headcount", joined)


class CallLog(unittest.TestCase):
    def test_log_records_cache_and_brief(self):
        from app import crustdata as c
        start = c.LOG[-1]["id"] if c.LOG else 0
        c.log_call("/company/search", {"search": {"query": "wealth management"}}, "live", 0.6, 120)
        c.log_call("/company/enrich", {"crustdata_company_ids": [1, 2]}, "cache")
        rows = c.log_since(start)
        self.assertEqual([r["source"] for r in rows], ["live", "cache"])
        self.assertEqual(rows[0]["what"], "wealth management")
        self.assertEqual(rows[1]["what"], "2 companies")
        self.assertNotIn("body", rows[0])
