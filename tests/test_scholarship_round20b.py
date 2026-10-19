"""Round 20, part 2: page types and programme identity carried through discovery, verification and the catalog
audit. The brief's cases: portal vs named programme, catalogue vs programme, guidance vs announcement, aggregator
pointing at an official page, expired vs open cycle, incomplete official page, unreachable source, conflicting and
ambiguous evidence, and one programme reached through two pages. Offline."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from scholarship_agent.audit import field_status  # noqa: E402
from scholarship_agent.discovery import Discovery  # noqa: E402
from scholarship_agent.extract import Page, page_kind  # noqa: E402
from scholarship_agent.identity import page_type  # noqa: E402
from scholarship_agent.models import VerificationStatus  # noqa: E402
from scholarship_agent.net import Fetcher  # noqa: E402
from scholarship_agent.registry import Source  # noqa: E402
from scholarship_agent.service import ScholarshipService  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from test_scholarship_agent import FakeTransport  # noqa: E402

TODAY = date(2026, 10, 17)
BASE = "https://www.example.ac.uk"
PROG = BASE + "/scholarships/ada-lovelace-scholarship"
PORTAL = BASE + "/scholarships"
GUIDE = BASE + "/study/how-to-find-funding"
NEWS = BASE + "/news/2026/09/student-receives-award"
AGG = "https://scholarhub.example.com/ada-lovelace"
SOURCES = [Source(id="ex", name="Example University scholarships", url=PORTAL, provider="Example University",
                  provider_type="university", countries=["GB"], kind="listing", official_domains=["example.ac.uk"])]


def programme_html(deadline="15 January 2027", extra=""):
    return (f"<html><head><title>Ada Lovelace Scholarship | Example University</title></head><body>"
            f"<h1>Ada Lovelace Scholarship</h1>"
            f"<p>The Ada Lovelace Scholarship is offered by Example University to master's students in computing.</p>"
            f"<h2>Eligibility</h2><p>Applicants must be citizens of Kenya or Ghana.</p>"
            f"<h2>What the scholarship covers</h2><p>The scholarship covers full tuition fees and a monthly stipend "
            f"of GBP 1,200.</p><h2>How to apply</h2><p>Submit the online application form with your CV.</p>"
            f"<p>The scholarship application deadline is {deadline}.</p>{extra}</body></html>")


PORTAL_HTML = ("<html><head><title>Scholarships database | Example University</title></head><body>"
               "<h1>Scholarships database</h1><p>Search our scholarships for international students.</p>"
               + "".join(f"<p><a href='{BASE}/scholarships/s{i}'>Example Award {i} Scholarship</a></p>" for i in range(14))
               + "<p>Funding covers tuition fees and stipend. Applications and eligibility vary.</p></body></html>")
GUIDE_HTML = ("<html><head><title>How to find funding for your studies | Example University</title></head><body>"
              "<h1>How to find funding for your studies</h1><p>This guide explains the types of scholarships, "
              "loans and grants students can look for, and how to prepare a strong application.</p></body></html>")
NEWS_HTML = ("<html><head><title>Student receives national award | Example University</title></head><body>"
             "<h1>Student receives national award</h1><p>Published 12 September 2026. A master's student received "
             "the Ada Lovelace Scholarship at a ceremony this week.</p></body></html>")
AGG_HTML = ("<html><head><title>Ada Lovelace Scholarship 2027 (Fully Funded)</title></head><body><h1>Ada Lovelace "
            "Scholarship 2027</h1><p>Fully funded scholarship. Deadline: 15 January 2027. Eligibility: Kenya, Ghana."
            f"</p><p><a href='{PROG}'>Official website</a></p></body></html>")


def page(url, html):
    from scholarship_agent.net import Response
    from scholarship_agent.extract import page_from_response
    return page_from_response(Response(url, 200, "text/html", html))


class TestPageTypes(unittest.TestCase):
    def test_portal_versus_named_programme(self):
        self.assertEqual(page_type(page_kind(page(PROG, programme_html()))[0]), "scholarship_program")
        self.assertEqual(page_type(page_kind(page(PORTAL, PORTAL_HTML))[0]), "scholarship_catalog")

    def test_government_catalogue_versus_specific_programme(self):
        cat = ("<html><head><title>Katalog Beasiswa | Kementerian Pendidikan</title></head><body><h1>Katalog Beasiswa"
               "</h1>" + "".join(f"<p>Beasiswa Program {i}</p>" for i in range(10)) +
               "<p>Persyaratan, pendaftaran dan biaya berbeda untuk setiap beasiswa.</p></body></html>")
        self.assertEqual(page_type(page_kind(page("https://kemdik.go.id/katalog", cat))[0]), "scholarship_catalog")

    def test_guidance_versus_announcement(self):
        self.assertEqual(page_type(page_kind(page(GUIDE, GUIDE_HTML))[0]), "general_guidance")
        self.assertEqual(page_type(page_kind(page(NEWS, NEWS_HTML))[0]), "announcement")

    def test_aggregator_type_ignores_page_content(self):
        self.assertEqual(page_type("opportunity", aggregator=True), "aggregator")
        self.assertEqual(page_type(""), "unknown")


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.t = FakeTransport({PROG: programme_html(), PORTAL: PORTAL_HTML, GUIDE: GUIDE_HTML, NEWS: NEWS_HTML,
                                AGG: AGG_HTML})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def svc(self, today=TODAY):
        return ScholarshipService(self.store, Fetcher(self.t, min_interval=0, sleep=lambda s: None), search=None,
                                  today=today, sources=SOURCES, extractor_llm=None)

    def only(self):
        opps = self.store.list_opportunities()
        self.assertEqual(len(opps), 1, [o.title for o in opps])
        return opps[0]


class Pipeline(_Base):
    def test_named_official_programme_is_verified_with_its_type_and_identity(self):
        s = self.svc()
        s.scrape([PROG], provider="Example University")
        o = self.only()
        r = s.verify(o.id)
        o = self.store.get_opportunity(o.id)
        self.assertEqual((o.page_type, r["programme_identity"]["state"]), ("scholarship_program", "confirmed"))
        self.assertEqual(o.verification_status, VerificationStatus.CONFIRMED)
        self.assertEqual(o.field_status["programme_identity"]["state"], "confirmed")

    def test_official_catalogue_is_never_verified_as_a_programme(self):
        s = self.svc()
        s.scrape([PORTAL], provider="Example University")   # a user asked for this page: kept, but classified
        o = self.only()
        r = s.verify(o.id)
        o = self.store.get_opportunity(o.id)
        self.assertEqual(o.page_type, "scholarship_catalog")
        self.assertEqual(r["programme_identity"]["state"], "rejected")
        self.assertNotEqual(o.verification_status, VerificationStatus.CONFIRMED)
        self.assertEqual(o.field_status["programme_identity"]["state"], "rejected")

    def test_registry_programme_source_that_is_a_portal_is_kept_but_rejected(self):
        src = [Source(id="p", name="Example University scholarships", url=PORTAL, provider="Example University",
                      kind="opportunity", countries=["GB"], official_domains=["example.ac.uk"])]
        d = Discovery(self.store, Fetcher(self.t, min_interval=0, sleep=lambda s: None), None, TODAY, src)
        d.run(use_search=False)
        # the classifier can be wrong about a page a person registered as a programme: kept and flagged, not dropped
        o = self.only()
        self.assertEqual((o.page_type, o.field_status["programme_identity"]["state"]), ("scholarship_catalog", "rejected"))

    def test_aggregator_record_needs_review_and_is_never_verified(self):
        s = self.svc()
        s.scrape([AGG])
        o = self.only()
        self.assertEqual(o.page_type, "aggregator")
        self.assertEqual(o.field_status["programme_identity"]["state"], "needs_review")
        s.verify(o.id)   # no official source known for the aggregator page: it stays unverified
        self.assertNotEqual(self.store.get_opportunity(o.id).verification_status, VerificationStatus.CONFIRMED)

    def test_expired_versus_open_cycle(self):
        s = self.svc(date(2027, 3, 1))
        s.scrape([PROG], provider="Example University")
        o = self.only()
        s.verify(o.id)
        fs = self.store.get_opportunity(o.id).field_status
        self.assertEqual(fs["deadline"]["state"], "outdated")
        self.assertEqual(fs["programme_identity"]["state"], "confirmed")   # an old cycle is still that programme
        self.t.pages = {k: programme_html("15 January 2028") for k in self.t.pages}
        s.verify(o.id)
        self.assertEqual(self.store.get_opportunity(o.id).field_status["deadline"]["state"], "present")

    def test_incomplete_official_page_keeps_identity_and_invents_nothing(self):
        bare = ("<html><head><title>Ada Lovelace Scholarship | Example University</title></head><body><h1>Ada "
                "Lovelace Scholarship</h1><p>The Ada Lovelace Scholarship is offered by Example University. "
                "Eligibility criteria and how to apply will be announced.</p><p>The scholarship supports students."
                "</p></body></html>")
        self.t.pages = {k: bare for k in self.t.pages}
        s = self.svc()
        s.scrape([PROG], provider="Example University")
        fs = self.only().field_status
        self.assertEqual(fs["programme_identity"]["state"], "confirmed")
        for f in ("eligible_countries", "funding_components", "deadline"):
            self.assertIn(fs[f]["state"], ("not_stated", "not_published"), f)

    def test_unreachable_source_is_not_verified(self):
        s = self.svc()
        s.scrape([PROG], provider="Example University")
        o = self.only()
        self.t.pages = {}
        s.verify(o.id)
        o = self.store.get_opportunity(o.id)
        self.assertEqual(o.verification_status, VerificationStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(o.page_type, "scholarship_program")   # the last known type is kept, not re-guessed

    def test_conflicting_pages_and_ambiguous_title_go_to_review(self):
        s = self.svc()
        s.scrape([PROG], provider="Example University")
        other = PROG + "-eligibility"
        self.t.pages[other.replace("https://www.", "https://")] = programme_html("29 January 2027")
        s.scrape([other], provider="Example University")
        o = self.only()
        self.assertEqual(o.verification_status, VerificationStatus.CONFLICTING)
        # a programme-like page whose title names no programme ("Postgraduate Research Scholarship")
        generic = ("<html><head><title>Postgraduate Research Scholarship | Example University</title></head><body>"
                   "<h1>Postgraduate Research Scholarship</h1>"
                   "<p>Applicants must be citizens of Kenya. The scholarship covers tuition fees and a stipend. "
                   "How to apply: submit the form. Deadline 15 January 2027.</p></body></html>")
        self.t.pages[(BASE + "/s/x").replace("https://www.", "https://")] = generic
        s.scrape([BASE + "/s/x"], provider="Example University")
        rec = next(x for x in self.store.list_opportunities() if x.info_url.endswith("/s/x"))
        r = s.verify(rec.id)
        self.assertEqual(r["programme_identity"]["state"], "needs_review")
        self.assertNotEqual(self.store.get_opportunity(rec.id).verification_status, VerificationStatus.CONFIRMED)

    def test_one_programme_reached_through_two_pages_is_one_record(self):
        s = self.svc()
        s.scrape([PROG], provider="Example University")
        mirror = BASE + "/international/ada-lovelace"
        self.t.pages[mirror.replace("https://www.", "https://")] = programme_html()
        s.scrape([mirror], provider="Example University")
        o = self.only()
        self.assertEqual(len({e.source_url for e in o.evidence}), 2)   # both pages kept as provenance


class TestOneRuleEverywhere(_Base):
    def test_discovery_verification_and_audit_agree(self):
        s = self.svc()
        for url in (PROG, BASE + "/s/generic"):
            self.t.pages[url.replace("https://www.", "https://")] = self.t.pages.get(url.replace("https://www.", "https://")) \
                or programme_html().replace("Ada Lovelace Scholarship", "Postgraduate Research Scholarship")
            s.scrape([url], provider="Example University")
        for o in self.store.list_opportunities():
            found = (o.page_type, o.programme_identity["state"])
            self.assertEqual(o.field_status["programme_identity"]["state"], found[1])   # audit reads what discovery stored
            r = s.verify(o.id)
            o2 = self.store.get_opportunity(o.id)
            self.assertEqual((o2.page_type, r["programme_identity"]["state"]), found, o.title)


class TestFieldStatusTypes(unittest.TestCase):
    def test_stored_types_reach_the_audit(self):
        from scholarship_agent.models import Opportunity
        o = Opportunity(id="x", title="Example Database", provider_name="Example University",
                        info_url=PORTAL, source_authority="2_official_provider_page", page_type="scholarship_catalog")
        fs = field_status(o, TODAY)
        self.assertEqual((fs["page_type"]["state"], fs["programme_identity"]["state"]), ("scholarship_catalog", "rejected"))


if __name__ == "__main__":
    unittest.main()
