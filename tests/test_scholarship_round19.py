"""Round 19: catalog audit (missing vs not applicable), discovery yield, deadline changes, unreachable sources and
resuming an interrupted registry run. Offline."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from scholarship_agent.audit import audit, discovery_yield, field_status, known_keys  # noqa: E402
from scholarship_agent.discovery import Discovery  # noqa: E402
from scholarship_agent.models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, FundingComponent,  # noqa: E402
                                      NationalityRule, Opportunity, VerificationStatus)


def quoted(field, value):
    """the evidence an official page gives for a value (round 25: no quotation, no "present")"""
    return Evidence(field=field, value=value, source_url="https://www.example.ac.uk/scholarships/x", snippet="quoted text")
from scholarship_agent.net import Fetcher  # noqa: E402
from scholarship_agent.normalize import normalize_url  # noqa: E402
from scholarship_agent.registry import Source  # noqa: E402
from scholarship_agent.service import ScholarshipService  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from test_scholarship_agent import LISTING, OFFICIAL, SOURCES, FakeTransport, fx  # noqa: E402

TODAY = date(2026, 10, 17)


def opp(**kw):
    base = dict(id="sch_x", title="Example Scholarship", provider_name="Example University",
                info_url="https://www.example.ac.uk/scholarships/x", source_authority="1_official_programme_page")
    return Opportunity(**(base | kw))


def dl(kind, d=None, certainty=DeadlineCertainty.CONFIRMED, approximate=None):
    return Deadline(kind=kind, certainty=certainty, date=d, approximate=approximate)


class TestFieldStatus(unittest.TestCase):
    def test_silent_page_is_not_stated_never_assumed(self):
        fs = field_status(opp(), TODAY)
        for f in ("eligible_countries", "study_levels", "funding_components", "application_period", "deadline"):
            self.assertEqual(fs[f]["state"], "not_stated", f)
        self.assertEqual(fs["official_source"]["state"], "present")

    def test_rolling_admission_has_no_deadline_or_window(self):
        fs = field_status(opp(deadlines=[dl(DeadlineKind.ROLLING, approximate="rolling")]), TODAY)
        self.assertEqual((fs["deadline"]["state"], fs["application_period"]["state"]), ("not_applicable", "not_applicable"))

    def test_announced_later_is_not_published(self):
        o = opp(deadlines=[dl(DeadlineKind.SCHOLARSHIP, certainty=DeadlineCertainty.UNKNOWN,
                              approximate="not yet published")])
        self.assertEqual(field_status(o, TODAY)["deadline"]["state"], "not_published")

    def test_present_outdated_and_approximate_deadlines(self):
        self.assertEqual(field_status(opp(deadlines=[dl(DeadlineKind.SCHOLARSHIP, "2027-01-15")],
                                          evidence=[quoted("deadline.scholarship", "2027-01-15")]), TODAY)["deadline"],
                         {"state": "present", "detail": "2027-01-15"})
        self.assertEqual(field_status(opp(deadlines=[dl(DeadlineKind.SCHOLARSHIP, "2027-01-15")]), TODAY)["deadline"]["state"],
                         "unsupported")
        old = opp(deadlines=[dl(DeadlineKind.SCHOLARSHIP, "2025-01-15", DeadlineCertainty.HISTORICAL)])
        self.assertEqual(field_status(old, TODAY)["deadline"]["state"], "outdated")
        approx = opp(deadlines=[dl(DeadlineKind.SCHOLARSHIP, certainty=DeadlineCertainty.EXPECTED,
                                   approximate="usually in November")])
        self.assertEqual(field_status(approx, TODAY)["deadline"]["state"], "approximate")

    def test_institution_only_date_is_not_an_applicant_deadline(self):
        fs = field_status(opp(deadlines=[dl(DeadlineKind.INSTITUTIONAL, "2027-01-15")]), TODAY)
        self.assertEqual(fs["deadline"]["state"], "not_stated")

    def test_admission_programme_funding_not_applicable_but_scholarship_is_not_stated(self):
        self.assertEqual(field_status(opp(opportunity_type="admission_programme"), TODAY)["funding_components"]["state"],
                         "not_applicable")
        unclear = opp(funding=[FundingComponent(kind="other", covered=None)])
        self.assertEqual(field_status(unclear, TODAY)["funding_components"]["state"], "needs_review")

    def test_nationality_states(self):
        self.assertEqual(field_status(opp(nationality=NationalityRule(mode="any"), evidence=[quoted("nationality", "any")]),
                                      TODAY)["eligible_countries"]["state"], "present")
        nr = NationalityRule(note="needs review: eligibility is a group of countries with an exception")
        self.assertEqual(field_status(opp(nationality=nr), TODAY)["eligible_countries"]["state"], "needs_review")

    def test_aggregator_record_is_unofficial(self):
        o = opp(info_url="https://scholarhub.example.com/x", source_authority="6_aggregator_or_search_result")
        self.assertEqual(field_status(o, TODAY)["official_source"]["state"], "unofficial")

    def test_status_is_stored_with_the_record_and_audit_counts_it(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d))
            st.save_opportunity(opp(deadlines=[dl(DeadlineKind.ROLLING, approximate="rolling")]), "k", "u")
            self.assertEqual(st.get_opportunity("sch_x").field_status["deadline"]["state"], "not_applicable")
            st.close()
        a = audit([opp(), opp(id="sch_y", title="Other", info_url="https://www.example.ac.uk/scholarships/x")], TODAY)
        self.assertEqual(a["by_field"]["deadline"], {"not_stated": 2})
        self.assertEqual(a["possible_duplicates"], [["sch_x", "sch_y"]])


class TestDiscoveryYield(unittest.TestCase):
    def test_counts_programmes_not_urls_and_separates_new_and_verified(self):
        a = opp(destination_countries=["GB"], study_levels=["master", "phd"],
                verification_status=VerificationStatus.CONFIRMED)
        b = opp(id="sch_b", title="Ernst Mach Grant", info_url="https://www.example.ac.uk/new", destination_countries=["GB"],
                study_levels=["master"])
        agg = opp(id="sch_c", title="Listing", info_url="https://agg.example.com/x",
                  source_authority="6_aggregator_or_search_result")
        y = discovery_yield([a, b, agg], known_keys([a]))
        self.assertEqual(y["totals"], {"records": 3, "official_programmes": 2, "new": 1, "verified": 1,
                                       "identity_needs_review": 0, "not_a_programme": 0})
        self.assertEqual(y["by_country"], [{"country": "GB", "official_programmes": 2, "new": 1, "verified": 1}])
        gb_master = next(r for r in y["by_country_level"] if r["country"] == "GB" and r["level"] == "master")
        self.assertEqual((gb_master["official_programmes"], gb_master["new"]), (2, 1))


class TestBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.t = FakeTransport({OFFICIAL: fx("official_page.html"), LISTING: fx("listing.html")})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def svc(self, today=TODAY):
        return ScholarshipService(self.store, Fetcher(self.t, min_interval=0, sleep=lambda s: None), search=None,
                                  today=today, sources=SOURCES, extractor_llm=None)

    def test_rescraping_merges_and_a_changed_deadline_moves_to_history(self):
        s = self.svc()
        s.scrape([OFFICIAL], provider="Example University")
        s.scrape([OFFICIAL], provider="Example University")
        self.assertEqual(len(self.store.list_opportunities()), 1)
        o = self.store.list_opportunities()[0]
        s.verify(o.id)
        self.t.pages = {k: v.replace("15 January 2027", "29 January 2027") for k, v in self.t.pages.items()}
        r = s.verify(o.id)
        self.assertEqual([(c["from"], c["to"]) for c in r["deadline_changes"]], [("2027-01-15", "2027-01-29")])
        o = self.store.get_opportunity(o.id)
        sch = [d.date for d in o.deadlines if d.kind == DeadlineKind.SCHOLARSHIP and d.date >= "2026"]
        self.assertEqual(sch, ["2027-01-29"])
        self.assertIn("2027-01-15", [h["date"] for h in self.store.deadline_history(o.id)])

    def test_unreachable_source_says_values_may_be_out_of_date(self):
        s = self.svc()
        s.scrape([OFFICIAL], provider="Example University")
        o = self.store.list_opportunities()[0]
        self.t.pages = {}
        s.verify(o.id)
        o = self.store.get_opportunity(o.id)
        self.assertEqual(o.verification_status, VerificationStatus.SOURCE_UNAVAILABLE)
        self.assertIn("could not be re-read", o.verification_reason)

    def test_interrupted_registry_run_resumes_after_the_finished_sources(self):
        second = "https://www.example.ac.uk/scholarships/research"
        sources = [Source(id="one", name="One", url=OFFICIAL, provider="Example University", kind="opportunity",
                          countries=["GB"], official_domains=["example.ac.uk"]),
                   Source(id="two", name="Two", url=second, provider="Example University", kind="opportunity",
                          countries=["GB"], official_domains=["example.ac.uk"])]
        self.t.pages[normalize_url(second)] = fx("research.html")
        stop = {"on": True}

        def transport(url, headers):   # the process is killed while fetching the second source
            if stop["on"] and url == second:
                raise KeyboardInterrupt
            return self.t(url, headers)
        d = Discovery(self.store, Fetcher(transport, min_interval=0, sleep=lambda s: None), None, TODAY, sources)
        with self.assertRaises(KeyboardInterrupt):
            d.run(use_search=False)
        job = self.store.jobs(1)[0]["id"]
        stop["on"] = False
        self.t.calls.clear()
        d.run(use_search=False, resume_job=job)
        self.assertNotIn(OFFICIAL, self.t.calls)
        self.assertIn(second, self.t.calls)
        self.assertEqual(self.store.job(job)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
