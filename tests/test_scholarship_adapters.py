"""DAAD, Erasmus Mundus and EURAXESS adapters against representative fixtures (no network).

DAAD and Erasmus Mundus fixtures are trimmed copies of the providers' real public data files
(retrieved 2026-10-17); the EURAXESS offer fixture is synthetic (see its README).
"""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.adapters import DAADAdapter, ErasmusMundusAdapter, EuraxessAdapter  # noqa: E402
from scholarship_agent.adapters.daad import BASE, detail_url, parse_taffy  # noqa: E402
from scholarship_agent.adapters.erasmus_mundus import CATALOGUE, RSS, parse_cards, parse_rss  # noqa: E402
from scholarship_agent.adapters.euraxess import SITEMAP, label_values  # noqa: E402
from scholarship_agent.models import DeadlineCertainty, VerificationStatus  # noqa: E402
from scholarship_agent.net import Fetcher, Response  # noqa: E402
from scholarship_agent.normalize import normalize_url  # noqa: E402
from scholarship_agent.service import ScholarshipService  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "scholarship" / "adapters"
TODAY = date(2026, 10, 17)


class Transport:
    def __init__(self, pages):
        self.pages = {normalize_url(k): v for k, v in pages.items()}
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return Response(url, 404, "text/plain", "")
        v = self.pages.get(normalize_url(url))
        if v is None:
            return Response(url, 404, "text/html", "")
        ctype = "text/javascript" if url.endswith(".js") else "application/rss+xml" if "rss" in url else \
            "application/xml" if url.endswith(".xml") else "text/html"
        return Response(url, 200, ctype, v)


def fetcher(pages):
    return Fetcher(Transport(pages), min_interval=0, sleep=lambda s: None)


def daad_pages(with_detail=False):
    pages = {BASE + f + ".js": (FIX / "daad" / f"{f}.js").read_text(encoding="utf-8")
             for f in ("scholarships", "deadlines", "origin", "status", "intentions", "subjectgroups")}
    if with_detail:
        pages[detail_url(50015171)] = (FIX / "daad" / "detail_50015171.html").read_text(encoding="utf-8")
    return pages


class TestDAAD(unittest.TestCase):
    def test_parse_taffy_reads_json_only(self):
        self.assertEqual(parse_taffy('var x = TAFFY([{"a":1}]);'), [{"a": 1}])
        with self.assertRaises(ValueError):
            parse_taffy("alert(1)")

    def test_normalizes_dataset(self):
        res = DAADAdapter(fetcher(daad_pages()), today=TODAY).run()
        self.assertEqual(len(res.records), 3)
        erp = next(r for r in res.records if r.provider_metadata["daad_prog_id"] == 50015171)
        self.assertTrue(erp.title.startswith("ERP Study Scholarships"))
        self.assertEqual(erp.destination_countries, ["DE"])
        self.assertEqual(erp.study_levels, ["master"])
        self.assertEqual(erp.nationality.mode, "include")
        self.assertEqual(len(erp.nationality.countries), 12)
        # per-origin deadlines: future ones confirmed, past ones historical, never merged into one guess
        certs = {d.date: d.certainty for d in erp.deadlines}
        self.assertEqual(certs.get("2026-11-16"), DeadlineCertainty.CONFIRMED)
        self.assertEqual(certs.get("2025-12-01"), DeadlineCertainty.HISTORICAL)
        self.assertTrue(erp.provider_metadata["deadlines_by_origin"])
        self.assertTrue(all(e.source_url.startswith(BASE) for e in erp.evidence))
        self.assertEqual(erp.verification_status, VerificationStatus.EXTRACTED)
        foreign = next(r for r in res.records if not r.provider_metadata["is_daad"])
        self.assertNotIn("DAAD", foreign.provider_name)

    def test_detail_page_adds_funding_and_duration(self):
        res = DAADAdapter(fetcher(daad_pages(True)), today=TODAY, details=True, detail_limit=3).run()
        erp = next(r for r in res.records if r.provider_metadata["daad_prog_id"] == 50015171)
        st = next(c for c in erp.funding if c.kind == "stipend")
        self.assertEqual((st.amount, st.currency, st.period), (992.0, "EUR", "month"))
        self.assertEqual(erp.funding_duration, "18-24 months")
        self.assertIn("insurance", {c.kind for c in erp.funding})
        self.assertEqual(len(res.failures), 2)  # the other two detail pages are not in the fixture

    def test_missing_dataset_is_a_failure_not_a_crash(self):
        res = DAADAdapter(fetcher({}), today=TODAY).run()
        self.assertEqual(res.records, [])
        self.assertTrue(res.failures)


class TestErasmusMundus(unittest.TestCase):
    def pages(self):
        return {RSS: (FIX / "erasmus_mundus" / "rss.xml").read_text(encoding="utf-8"),
                CATALOGUE: (FIX / "erasmus_mundus" / "catalogue_page0.html").read_text(encoding="utf-8"),
                CATALOGUE + "?page=1": (FIX / "erasmus_mundus" / "catalogue_page1.html").read_text(encoding="utf-8")}

    def test_parsers(self):
        items = parse_rss(self.pages()[RSS])
        self.assertEqual(len(items), 3)
        self.assertIn("EMJMD Universities", items[0]["categories"])
        cards = parse_cards(self.pages()[CATALOGUE])
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]["acronym"], "MultiDiverse")

    def test_programmes_vs_legacy_projects(self):
        res = ErasmusMundusAdapter(fetcher(self.pages()), today=TODAY).run()
        self.assertEqual(len(res.records), 6)  # 3 cards + 3 feed-only entries
        types = {r.title[:30]: r.opportunity_type for r in res.records}
        self.assertEqual(sum(t == "admission_programme" for t in types.values()), 4)
        legacy = [r for r in res.records if r.opportunity_type == "funded_project"]
        self.assertEqual(len(legacy), 2)
        self.assertTrue(all("historical_mobility_project" in r.tags for r in legacy))
        telme = next(r for r in res.records if r.title.startswith("Teaching, designing"))
        self.assertEqual(telme.funding_duration, "24 months / 120 ECTS")
        self.assertIn("UNIVERSITY OF LIMERICK", telme.provider_metadata["universities"])
        # the catalogue never states scholarship terms: they stay unknown, flagged
        self.assertEqual(telme.nationality.mode, "unknown")
        self.assertFalse(telme.deadlines)
        self.assertTrue(any("consortium" in u for u in telme.uncertainties))
        self.assertEqual(len(res.failures), 0)


class TestEuraxess(unittest.TestCase):
    def test_run_only_reads_allowed_pages_and_returns_leads(self):
        pages = {SITEMAP: (FIX / "euraxess" / "sitemap.xml").read_text(),
                 "https://euraxess.ec.europa.eu/worldwide/japan/careers-and-funding": (FIX / "euraxess" / "worldwide_japan.html").read_text(),
                 "https://euraxess.ec.europa.eu/worldwide/india/jobs-funding": (FIX / "euraxess" / "worldwide_india.html").read_text()}
        f = fetcher(pages)
        res = EuraxessAdapter(f, today=TODAY).run()
        self.assertEqual(res.records, [])
        urls = {l["url"] for l in res.leads}
        self.assertIn("https://www.jsps.go.jp/english/e-fellow/", urls)
        self.assertIn("https://www.example-foundation.in/fellowship-programme", urls)
        from urllib.parse import urlsplit
        self.assertFalse(any(urlsplit(c).path.startswith("/jobs") for c in f.transport.calls))
        self.assertTrue(any("disallows /jobs/*" in n for n in res.notes))

    def test_import_saved_offer(self):
        html = (FIX / "euraxess" / "offer_saved.html").read_text()
        lv = label_values(html)
        self.assertEqual(lv["researcher profile"], "First Stage Researcher (R1)")
        opp = EuraxessAdapter(fetcher({}), today=TODAY).import_saved(html, "https://euraxess.ec.europa.eu/jobs/123456")
        self.assertEqual(opp.opportunity_type, "research_position")
        self.assertEqual(opp.study_levels, ["phd"])
        self.assertEqual(opp.destination_countries, ["NO"])
        d = next(x for x in opp.deadlines if x.date == "2027-01-15")
        self.assertEqual((d.time, d.timezone, d.certainty), ("23:59", "Europe/Oslo", DeadlineCertainty.CONFIRMED))
        self.assertEqual(opp.nationality.mode, "any")
        self.assertEqual(opp.funding_duration, "36 months")
        with self.assertRaises(ValueError):
            EuraxessAdapter(fetcher({}), today=TODAY).import_saved(html, "https://evil.example.com/jobs/1")


class TestServiceAdapters(unittest.TestCase):
    def test_run_adapter_persists_and_dedups(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            svc = ScholarshipService(store, fetcher(daad_pages()), search=None, today=TODAY, sources=[], extractor_llm=None)
            out = svc.run_adapter("daad")
            self.assertEqual((out["records"], out["new"]), (3, 3))
            again = svc.run_adapter("daad")
            self.assertEqual((again["new"], again["merged"], again["refreshed"]), (0, 0, 3))   # round 49: replaced
            self.assertEqual(len(store.list_opportunities()), 3)
            with self.assertRaises(ValueError):
                svc.run_adapter("nope")
            store.close()


class TestAdapterDedup(unittest.TestCase):
    def test_same_adapter_distinct_ids_are_not_merged(self):
        from scholarship_agent.discovery import Discovery, DiscoveryResult
        from scholarship_agent.models import Opportunity
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            d = Discovery(store, fetcher({}), None, TODAY, [])
            res = DiscoveryResult(job_id=0)
            a = Opportunity(id="sch_a", title="Research Grants - Doctoral Programmes in Germany", provider_name="DAAD",
                            discovered_via="adapter:daad")
            b = Opportunity(id="sch_b", title="Research Grants - Doctoral Programmes in Germany 2027", provider_name="DAAD",
                            discovered_via="adapter:daad")
            d.persist(0, a, "", res)
            d.persist(0, b, "", res)
            self.assertEqual(len(store.list_opportunities()), 2)
            c = Opportunity(id="sch_c", title="Research Grants - Doctoral Programmes in Germany", provider_name="DAAD",
                            discovered_via="source:de-daad")
            d.persist(0, c, "", res)  # a scraped page of the same programme still merges
            self.assertEqual(len(store.list_opportunities()), 2)
            store.close()


class TestAdapterVerification(unittest.TestCase):
    def test_verifying_an_adapter_record_reads_the_detail_page_not_the_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            f = fetcher(daad_pages(with_detail=True))
            svc = ScholarshipService(store, f, search=None, today=TODAY, sources=[], extractor_llm=None)
            svc.run_adapter("daad")
            erp = next(o for o in store.list_opportunities() if o.provider_metadata.get("daad_prog_id") == 50015171)
            n_before = len(f.transport.calls)
            r = svc.verify(erp.id)
            fetched = f.transport.calls[n_before:]
            self.assertFalse(any(u.endswith(".js") for u in fetched))
            self.assertEqual(r["conflicts"], [])
            self.assertIn("eligibility", r["core_fields_confirmed"])  # the dataset's origin list counts
            self.assertNotEqual(r["status"], "conflicting")
            store.close()


if __name__ == "__main__":
    unittest.main()
