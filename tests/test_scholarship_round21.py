"""Round 21: multilingual programme-page vocabulary (languages.json "page" blocks), page type with a confidence kept
apart from programme identity, and uncertain pages sent to review. Offline."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from scholarship_agent import languages  # noqa: E402
from scholarship_agent.discovery import Discovery  # noqa: E402
from scholarship_agent.extract import Page, classify_page  # noqa: E402
from scholarship_agent.identity import identity  # noqa: E402
from scholarship_agent.models import Opportunity  # noqa: E402
from scholarship_agent.net import Fetcher  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from test_scholarship_agent import FakeTransport  # noqa: E402


def page(url, title, body, lang=""):
    attr = f' lang="{lang}"' if lang else ""
    return Page(url, f"<html{attr}><head><title>{title}</title></head><body><h1>{title}</h1>{body}</body></html>")


VI = ("<p>Học bổng dành cho sinh viên có hoàn cảnh khó khăn. Đối tượng: sinh viên năm nhất.</p>"
      "<p>Quyền lợi: miễn 100% học phí. Hồ sơ đăng ký gồm đơn và bảng điểm. Hạn nộp hồ sơ: 30/11/2026.</p>")
PT = ("<p>Quem pode participar: servidores municipais. Inscrição pelo edital de concessão.</p>"
      "<p>Valor da bolsa: R$ 1.000 por mês. Período de inscrição até 30 de novembro de 2026.</p>")
UR = "<p>اسکالرشپ کے لیے اہلیت اور شرائط۔ درخواست کی آخری تاریخ 30 نومبر ہے۔</p>"


class TestVocabulary(unittest.TestCase):
    def test_every_page_block_names_its_sources(self):
        for code, lang in languages.languages().items():
            block = lang.get("page")
            if block:
                self.assertTrue(block.get("sources"), code)
                self.assertTrue(set(block) - {"sources"} <= set(languages.PAGE_GROUPS), code)

    def test_vietnamese_portuguese_and_urdu_programme_pages(self):
        for url, title, body in (("https://truong.example.edu.vn/hoc-bong-khuyen-hoc", "Học bổng khuyến học Nguyễn Văn A", VI),
                                 ("https://prefeitura.example.gov.br/bolsa-de-estudos", "Bolsa de Estudos Servidor", PT),
                                 ("https://college.example.edu.pk/ur/scholarship", "وظیفہ پروگرام", UR)):
            c = classify_page(page(url, title, body))
            self.assertEqual(c["kind"], "opportunity", (title, c))

    def test_language_detection_reads_vietnamese_and_urdu(self):
        self.assertEqual(languages.detect("Học bổng dành cho sinh viên của trường và các đối tượng được hỗ trợ trong năm")[0], "vi")
        self.assertEqual(languages.detect("یہ اسکالرشپ طلباء کے لیے ہے اور درخواست کی آخری تاریخ ہے")[0], "ur")

    def test_listing_news_and_guidance_words(self):
        self.assertEqual(classify_page(page("https://u.example.ac.id/", "Beasiswa Tersedia",
                                            "<p>Daftar beasiswa: Beasiswa A, Beasiswa B, Beasiswa C untuk mahasiswa baru "
                                            "dan mahasiswa aktif di universitas ini.</p>"))["kind"], "listing")
        self.assertEqual(classify_page(page("https://u.example.ac.id/x", "Pengumuman Lulus Seleksi Beasiswa",
                                            VI))["kind"], "news")
        self.assertEqual(classify_page(page("https://u.example.edu.vn/a", "Cách săn học bổng du học A-Z", VI))["kind"],
                         "guidance")

    def test_institution_home_page_that_only_mentions_scholarships(self):
        c = classify_page(page("https://www.uni.example.edu.eg/", "Future University",
                               "<p>Admissions are open. Apply online. Tuition fees and scholarships.</p>"))
        self.assertEqual(c["kind"], "not_relevant")


class TestConfidenceAndIdentity(unittest.TestCase):
    def test_unknown_language_is_uncertain_not_rejected(self):
        c = classify_page(page("https://x.example.gov.et/", "ነፃ የትምህርት ዕድል", "<p>ለተማሪዎች የሚሰጥ ዕድል። " * 8 + "</p>"))
        self.assertEqual(c["confidence"], "low")
        o = Opportunity(id="x", title="ነፃ የትምህርት ዕድል", provider_name="Ministry", source_authority="3_official_government_agency")
        idn = identity(o, page_kind=c["kind"], kind_confidence=c["confidence"], kind_reason=c["reason"])
        self.assertEqual(idn["state"], "needs_review")

    def test_confident_non_programme_is_rejected_and_thin_programme_goes_to_review(self):
        o = Opportunity(id="x", title="Ada Lovelace Scholarship", provider_name="Example University",
                        source_authority="1_official_programme_page")
        self.assertEqual(identity(o, page_kind="listing")["state"], "rejected")
        self.assertEqual(identity(o, page_kind="opportunity", kind_confidence="low", kind_reason="thin")["state"],
                         "needs_review")

    def test_search_discovery_keeps_an_uncertain_page_for_review(self):
        url = "https://www.example.gov.et/scholarship"
        html = ("<html><head><title>ነፃ የትምህርት ዕድል scholarship</title></head><body><p>"
                + "ለተማሪዎች scholarship የሚሰጥ ዕድል። " * 6 + "</p></body></html>")
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d))
            disc = Discovery(st, Fetcher(FakeTransport({url: html}), min_interval=0, sleep=lambda s: None), None,
                             date(2026, 10, 18), [])
            from scholarship_agent.discovery import DiscoveryResult
            from scholarship_agent.models import SourceType
            disc.ingest_url(st.start_job("t", {}), url, provider="Ministry", provider_type="government",
                            source_type=SourceType.SEARCH_RESULT, countries_hint=[], result=DiscoveryResult(job_id=1),
                            discovered_via="search:test")
            opps = st.list_opportunities()
            self.assertEqual(len(opps), 1)
            self.assertEqual((opps[0].page_type, opps[0].programme_identity["state"]), ("unknown", "needs_review"))
            st.close()


if __name__ == "__main__":
    unittest.main()
