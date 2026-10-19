"""Country-by-country strategy: planning, pagination, caching/incremental runs, retries, coverage,
provider checks and key redaction. Offline: FixtureSearch / fake JSON getters only."""

import json
import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.discovery import Discovery  # noqa: E402
from scholarship_agent.net import Fetcher, Response  # noqa: E402
from scholarship_agent.normalize import normalize_url  # noqa: E402
from scholarship_agent.search import BraveSearch, FixtureSearch, SearchError, SearchHit, SearxngSearch  # noqa: E402
from scholarship_agent.service import ScholarshipService  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from scholarship_agent.strategy import (QUERY_CATEGORIES, StrategyConfig, StrategyRunner, check_provider,  # noqa: E402
                                        coverage_report, plan, target_countries)

FIX = REPO / "tests" / "fixtures" / "scholarship"
TODAY = date(2026, 10, 17)
OPP = "https://www.example.ac.id/beasiswa"


class Transport:
    def __init__(self, pages):
        self.pages = {normalize_url(k): v for k, v in pages.items()}

    def __call__(self, url, headers):
        if url.endswith("/robots.txt"):
            return Response(url, 404, "text/plain", "")
        v = self.pages.get(normalize_url(url))
        return Response(url, 200, "text/html", v) if v else Response(url, 404, "text/html", "")


class TestPlan(unittest.TestCase):
    def test_plan_spans_all_countries_and_categories(self):
        cfg = StrategyConfig()
        self.assertEqual(len(target_countries(cfg)), 231)
        qs = plan(StrategyConfig(countries=["ID", "FJ", "SN"], queries_per_country=10))
        self.assertEqual({q["country"] for q in qs}, {"ID", "FJ", "SN"})
        cats = {q["category"] for q in qs if q["country"] == "ID"}
        self.assertTrue({"government", "university", "domestic", "local_language", "research"} <= cats)
        self.assertIn("beasiswa site:.id", [q["query"] for q in qs])
        self.assertIn("bourse d'études site:.sn", [q["query"] for q in qs])
        self.assertFalse(any(q["category"] == "local_language" for q in qs if q["country"] == "FJ"))

    def test_regions_and_validation(self):
        africa = target_countries(StrategyConfig(regions=["Africa"]))
        self.assertIn("KE", africa)
        self.assertNotIn("DE", africa)
        with self.assertRaises(ValueError):
            StrategyConfig.load({"categories": ["astrology"]})
        with self.assertRaises(ValueError):
            StrategyConfig.load({"budget": 3})
        self.assertGreaterEqual(len(QUERY_CATEGORIES), 10)


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        page = (FIX / "id_beasiswa.html").read_text()
        self.fetcher = Fetcher(Transport({OPP: page}), min_interval=0, sleep=lambda s: None)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def runner(self, provider, **cfg):
        d = Discovery(self.store, self.fetcher, None, TODAY, [])
        c = StrategyConfig(**({"countries": ["ID"], "queries_per_country": 2, "results_per_page": 2} | cfg))
        return StrategyRunner(self.store, d, provider, c, sleep=lambda s: None, today=TODAY)

    def test_run_records_queries_urls_and_candidates(self):
        hits = [SearchHit(OPP, "Beasiswa"), SearchHit("https://news.example.com/x", "scholarship news"),
                SearchHit("https://www.example.ac.id/beasiswa?utm_source=x", "dup")]
        rep = self.runner(FixtureSearch({"*": hits}), pages_per_query=2).run()
        self.assertEqual(rep["countries_searched"], ["ID"])
        self.assertEqual(rep["queries_executed"], 4)   # 2 queries x 2 pages (page 2 has 1 hit)
        self.assertEqual(rep["urls_discovered"], 6)
        self.assertEqual(rep["urls_new"], 2)           # utm duplicate and re-seen URLs are not new
        self.assertEqual(rep["pages_retrieved"], 1)
        self.assertEqual(rep["pages_failed"], 1)       # news.example.com is not in the fixture -> 404
        self.assertEqual(rep["candidates"]["new"], 1)
        cov = coverage_report(self.store)
        self.assertEqual(cov["countries_searched"], 1)
        self.assertEqual(cov["urls_by_status"].get("opportunity"), 1)

    def test_incremental_rerun_uses_cache(self):
        p = FixtureSearch({"*": [SearchHit(OPP, "x")]})
        self.runner(p).run()
        n = len(p.queries)
        rep2 = self.runner(p).run()
        self.assertEqual(len(p.queries), n)        # no new provider calls
        self.assertEqual(rep2["queries_from_cache"], 2)
        self.assertEqual(rep2["urls_new"], 0)

    def test_errors_are_retried_then_reported(self):
        class Flaky(FixtureSearch):
            def __init__(self):
                super().__init__({})
                self.calls = 0

            def search(self, query, limit=10, lang="en", page=0):
                self.calls += 1
                raise SearchError("HTTP 503")
        p = Flaky()
        rep = self.runner(p, queries_per_country=1).run()
        self.assertEqual(p.calls, 3)
        self.assertEqual(rep["countries_failed"], ["ID"])
        self.assertEqual(rep["query_errors"][0]["error"], "HTTP 503")

    def test_auth_errors_are_not_retried(self):
        class Denied(FixtureSearch):
            calls = 0

            def search(self, *a, **k):
                Denied.calls += 1
                raise SearchError("HTTP 401")
        self.runner(Denied({}), queries_per_country=1).run()
        self.assertEqual(Denied.calls, 1)

    def test_unavailable_provider_does_nothing(self):
        rep = self.runner(BraveSearch(api_key="")).run()
        self.assertIn("unavailable", rep["provider"])
        self.assertEqual(rep["queries_executed"], 0)


class TestProviders(unittest.TestCase):
    def test_pagination_parameters(self):
        seen = []
        BraveSearch(api_key="k", get=lambda u, h: seen.append(u) or {"web": {"results": []}}).search("q", 10, "id", 2)
        SearxngSearch(base="http://localhost:8888", get=lambda u, h: seen.append(u) or {"results": []}).search("q", 10, "id", 2)
        self.assertIn("offset=2", seen[0])
        self.assertIn("search_lang=id", seen[0])
        self.assertIn("pageno=3", seen[1])

    def test_errors_never_carry_the_key(self):
        def boom(url, headers):
            raise urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
        with self.assertRaises(SearchError) as cm:
            BraveSearch(api_key="sk-secret-999", get=boom).search("q")
        self.assertNotIn("sk-secret-999", str(cm.exception))
        self.assertEqual(str(cm.exception), "HTTP 401")

    def test_provider_check_is_recorded_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            p = BraveSearch(api_key="sk-secret-999", get=lambda u, h: {"web": {"results": [{"url": "https://a.gov/s"}]}})
            out = check_provider(store, p, "beasiswa")
            self.assertTrue(out["ok"])
            self.assertEqual(out["urls"], ["https://a.gov/s"])
            dumped = json.dumps(store.provider_checks()) + json.dumps(out)
            self.assertNotIn("sk-secret-999", dumped)
            self.assertFalse(check_provider(store, BraveSearch(api_key=""))["ok"])
            store.close()

    def test_service_without_provider_says_so(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            for k in ("BRAVE_SEARCH_API_KEY", "SEARXNG_URL"):
                os.environ.pop(k, None)
            store = Store(Path(tmp))
            svc = ScholarshipService(store, Fetcher(Transport({})), sources=[], extractor_llm=None)
            out = svc.search_check()
            self.assertFalse(out["ok"])
            self.assertIn("BRAVE_SEARCH_API_KEY", out["error"])
            with self.assertRaises(ValueError):
                svc.strategy_run(countries=["ID"])
            store.close()


class TestMigration(unittest.TestCase):
    def test_v1_database_upgrades_in_place(self):
        import sqlite3
        from scholarship_agent.store import CATALOG_MIGRATIONS
        with tempfile.TemporaryDirectory() as tmp:
            c = sqlite3.connect(str(Path(tmp) / "catalog.db"))
            c.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
            c.executescript(CATALOG_MIGRATIONS[0])
            c.execute("INSERT INTO schema_version VALUES (1)")
            c.execute("INSERT INTO opportunities (id, title, data) VALUES ('sch_1', 'Kept', '{\"id\":\"sch_1\",\"title\":\"Kept\",\"provider_name\":\"p\"}')")
            c.commit()
            c.close()
            s = Store(Path(tmp))
            self.assertEqual(s.get_opportunity("sch_1").title, "Kept")
            self.assertEqual(s.catalog.execute("SELECT MAX(version) FROM schema_version").fetchone()[0], len(CATALOG_MIGRATIONS))
            s.see_url("u", "u", "ID", "government", "x")
            s.close()


class TestFreshnessAndReport(unittest.TestCase):
    def test_priority_and_report(self):
        from scholarship_agent import freshness
        from scholarship_agent.models import Opportunity
        today = TODAY
        soon = Opportunity.from_dict({"id": "a", "title": "Soon", "provider_name": "p", "deadlines": [
            {"kind": "scholarship", "certainty": "confirmed", "date": "2026-11-01"}], "nationality": {"mode": "any"},
            "funding": [{"kind": "stipend", "amount": 1}], "last_verified_at": "2026-10-15T00:00:00+00:00"})
        past = Opportunity.from_dict({"id": "b", "title": "Past", "provider_name": "p", "deadlines": [
            {"kind": "scholarship", "certainty": "historical", "date": "2026-01-08"}],
            "last_verified_at": "2026-10-16T00:00:00+00:00"})
        fresh_ok = Opportunity.from_dict({"id": "c", "title": "Ok", "provider_name": "p", "deadlines": [
            {"kind": "scholarship", "certainty": "confirmed", "date": "2027-06-01"}], "nationality": {"mode": "any"},
            "funding": [{"kind": "stipend", "amount": 1}], "last_verified_at": "2026-10-16T00:00:00+00:00"})
        cfg = freshness.schedule()
        p_soon, p_past, p_ok = (freshness.priority(o, today, cfg) for o in (soon, past, fresh_ok))
        self.assertFalse(p_soon["due"])                      # verified 2 days ago; upcoming deadlines recheck every 3 days
        self.assertEqual(p_soon["next_check"], "2026-10-18")
        self.assertGreater(p_soon["priority"], p_ok["priority"])
        self.assertTrue(any("past-cycle" in r for r in p_past["reasons"]))
        self.assertFalse(p_ok["due"])
        self.assertEqual(p_ok["next_check"], "2026-10-30")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            page = (FIX / "official_page.html").read_text()
            url = "https://www.example.ac.uk/scholarships/excellence"
            f = Fetcher(Transport({url: page}), min_interval=0, sleep=lambda s: None)
            svc = ScholarshipService(store, f, search=None, today=TODAY, sources=[], extractor_llm=None)
            svc.scrape([url])
            plan_ = svc.refresh(plan_only=True)
            self.assertEqual(plan_["due"], 1)
            svc.refresh()
            rep = svc.discovery_report()
            self.assertEqual(rep["candidates"]["unique_records"], 1)
            self.assertEqual(rep["pages"]["retrieved"], 1)
            self.assertEqual(rep["verification"]["record_level_verified_against_official_source"], 1)
            self.assertEqual(rep["verification"]["field_level"]["confirmed_current_deadline"], 1)
            self.assertEqual(rep["configuration"]["search_provider"], "none configured")
            store.close()


if __name__ == "__main__":
    unittest.main()
