"""Round 22: pages that did not load are "not assessed", kept apart from "not a programme"; Malay vocabulary.
Offline."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from scholarship_agent.discovery import Discovery, DiscoveryResult  # noqa: E402
from scholarship_agent.extract import Page, classify_page  # noqa: E402
from scholarship_agent.identity import identity  # noqa: E402
from scholarship_agent.models import Opportunity, SourceType  # noqa: E402
from scholarship_agent.net import Fetcher  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from test_scholarship_agent import FakeTransport  # noqa: E402

JS_SHELL = ("<html><head><title>Beasiswa LPDP</title>" + "<script src='a.js'></script>" * 6 +
            "</head><body><div id='root'></div></body></html>")
EMPTY = "<html><head><title>ITB FinAid</title></head><body></body></html>"
LOGIN = ("<html><head><title>Student portal</title></head><body><p>Please log in to continue. Username Password "
         "Forgot password? This system is for registered applicants of the bursary programme only.</p></body></html>")
SPACED = "<html><body><p>" + " ".join("SYARAT-SYARAT BIASISWA KERAJAAN NEGERI SABAH UNIVERSITI TEMPATAN") + "</p></body></html>"
MS = ("<html><head><title>Biasiswa Sagong Tasi</title></head><body><h1>Biasiswa Sagong Tasi</h1>"
      "<p>Syarat kelayakan: pemohon warganegara Malaysia yang lahir di Selangor.</p><p>Kadar pembiayaan: yuran "
      "pengajian dan elaun sara diri. Borang permohonan dibuka sehingga tarikh tutup 30 November 2026.</p></body></html>")


class TestNotLoaded(unittest.TestCase):
    def test_shell_empty_login_and_spaced_text_are_not_assessed(self):
        for name, html in (("js", JS_SHELL), ("empty", EMPTY), ("login", LOGIN), ("spaced", SPACED)):
            c = classify_page(Page("https://x.example.go.id/", html))
            self.assertEqual(c["kind"], "not_loaded", name)

    def test_identity_is_not_assessed_rather_than_rejected(self):
        o = Opportunity(id="x", title="Beasiswa LPDP", provider_name="LPDP", source_authority="3_official_government_agency")
        idn = identity(o, page_kind="not_loaded", kind_reason="almost no text but many scripts")
        self.assertEqual(idn["state"], "not_assessed")

    def test_search_discovery_logs_not_loaded_apart_from_skipped(self):
        url = "https://beasiswa.example.go.id/"
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d))
            disc = Discovery(st, Fetcher(FakeTransport({url: JS_SHELL}), min_interval=0, sleep=lambda s: None), None,
                             date(2026, 10, 18), [])
            res = DiscoveryResult(job_id=1)
            job = st.start_job("t", {})
            self.assertIsNone(disc.ingest_url(job, url, provider="x", provider_type="other",
                                              source_type=SourceType.SEARCH_RESULT, countries_hint=[], result=res,
                                              discovered_via="search:test"))
            self.assertEqual([r["outcome"] for r in st.ingestion(job)], ["not_loaded"])
            self.assertEqual(res.skipped_by_kind, {"not_loaded": 1})
            st.close()

    def test_registry_page_that_did_not_load_is_kept_not_assessed(self):
        url = "https://beasiswa.example.go.id/"
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d))
            disc = Discovery(st, Fetcher(FakeTransport({url: JS_SHELL}), min_interval=0, sleep=lambda s: None), None,
                             date(2026, 10, 18), [])
            disc.ingest_url(st.start_job("t", {}), url, provider="LPDP", provider_type="government",
                            source_type=SourceType.OFFICIAL, countries_hint=[], result=DiscoveryResult(job_id=1),
                            discovered_via="source:x", require_opportunity=False)
            o = st.list_opportunities()[0]
            self.assertEqual((o.page_type, o.programme_identity["state"]), ("not_loaded", "not_assessed"))
            st.close()


class TestMalay(unittest.TestCase):
    def test_malay_programme_page(self):
        c = classify_page(Page("https://danapendidikan.example.gov.my/biasiswa-sagong-tasi", MS))
        self.assertEqual((c["kind"], c["confidence"]), ("opportunity", "high"))


if __name__ == "__main__":
    unittest.main()
