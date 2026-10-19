"""Round 25: catalogue quality. Cycle status, funding type, programme-specific eligibility, evidence for every
"present" value, and the count of programmes an applicant could decide on. Offline; the classifier is unchanged."""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent.audit import audit, cycle_status, complete_with_evidence, field_status, funding_type  # noqa: E402
from scholarship_agent.models import (Deadline, DeadlineCertainty as C, DeadlineKind as K, Evidence,  # noqa: E402
                                      FundingComponent, NationalityRule, Opportunity)

TODAY = date(2026, 10, 18)
URL = "https://www.example.ac.uk/scholarships/ada"


def ev(field, value, url=URL):
    return Evidence(field=field, value=value, source_url=url, snippet="quoted from the page")


def opp(**kw):
    base = dict(id="sch_a", title="Ada Lovelace Scholarship", provider_name="Example University", info_url=URL,
                source_authority="1_official_programme_page", page_type="scholarship_program",
                programme_identity={"state": "confirmed", "name": "Ada Lovelace", "reasons": []})
    return Opportunity(**(base | kw))


def dl(kind, d=None, cert=C.CONFIRMED, approx=None):
    return Deadline(kind=kind, certainty=cert, date=d, approximate=approx)


class TestCycle(unittest.TestCase):
    def state(self, *deadlines):
        return cycle_status(opp(deadlines=list(deadlines)), TODAY)["state"]

    def test_states(self):
        self.assertEqual(self.state(dl(K.SCHOLARSHIP, "2027-01-15")), "open")
        self.assertEqual(self.state(dl(K.OPENING, "2026-11-01"), dl(K.SCHOLARSHIP, "2027-01-15")), "upcoming")
        self.assertEqual(self.state(dl(K.OPENING, "2026-12-01")), "upcoming")
        self.assertEqual(self.state(dl(K.SCHOLARSHIP, "2026-03-01", C.HISTORICAL)), "closed")
        self.assertEqual(self.state(dl(K.SCHOLARSHIP, cert=C.UNKNOWN, approx="not yet published")), "not_announced")
        # round 33: an approximate date ("usually in November") says nothing about the current cycle
        self.assertEqual(self.state(dl(K.SCHOLARSHIP, cert=C.EXPECTED, approx="usually in November")), "not_stated")
        self.assertEqual(self.state(dl(K.ROLLING, approx="rolling")), "rolling")
        self.assertEqual(self.state(), "not_stated")
        self.assertEqual(self.state(dl(K.INSTITUTIONAL, "2027-01-15")), "not_stated")   # not an applicant date


class TestFunding(unittest.TestCase):
    def kind(self, *components):
        return funding_type(opp(funding=list(components)))["state"]

    def test_types(self):
        self.assertEqual(self.kind(FundingComponent("tuition", full=True), FundingComponent("stipend")), "fully_funded")
        self.assertEqual(self.kind(FundingComponent("tuition", full=True)), "tuition_funded")
        self.assertEqual(self.kind(FundingComponent("stipend")), "stipend_only")
        self.assertEqual(self.kind(FundingComponent("tuition", full=False), FundingComponent("stipend")), "partially_funded")
        self.assertEqual(self.kind(FundingComponent("tuition"), FundingComponent("stipend")), "funding_unclear")
        self.assertEqual(self.kind(FundingComponent("other", covered=None)), "funding_unclear")
        self.assertEqual(self.kind(), "not_stated")


class TestEligibilityAndEvidence(unittest.TestCase):
    def test_eligibility_from_a_catalogue_page_needs_review(self):
        o = opp(page_type="scholarship_catalog", nationality=NationalityRule(mode="include", countries=["KE"]),
                evidence=[ev("nationality", "include:KE")])
        self.assertEqual(field_status(o, TODAY)["eligible_countries"]["state"], "needs_review")

    def test_eligibility_quoted_only_from_another_page_needs_review(self):
        o = opp(nationality=NationalityRule(mode="include", countries=["KE"]),
                evidence=[ev("nationality", "include:KE", "https://www.example.ac.uk/international/funding")])
        self.assertEqual(field_status(o, TODAY)["eligible_countries"]["state"], "needs_review")

    def test_value_without_a_quotation_is_unsupported(self):
        o = opp(study_levels=["master"], nationality=NationalityRule(mode="include", countries=["KE"]))
        fs = field_status(o, TODAY)
        self.assertEqual((fs["study_levels"]["state"], fs["eligible_countries"]["state"]), ("unsupported", "unsupported"))


class TestCompleteWithEvidence(unittest.TestCase):
    def ready(self):
        return opp(nationality=NationalityRule(mode="include", countries=["KE"]), study_levels=["master"],
                   funding=[FundingComponent("tuition", full=True), FundingComponent("stipend")],
                   deadlines=[dl(K.SCHOLARSHIP, "2027-01-15")],
                   evidence=[ev("nationality", "include:KE"), ev("study_levels", "master"),
                             ev("funding.tuition", True), ev("deadline.scholarship", "2027-01-15")])

    def test_complete_record_is_ready_and_counted(self):
        self.assertEqual(complete_with_evidence(field_status(self.ready(), TODAY)), (True, []))
        a = audit([self.ready(), opp(id="sch_b", title="Other Scholarship")], TODAY)
        self.assertEqual((a["complete_with_evidence"], a["complete_with_evidence_and_open_or_upcoming"]), (1, 1))
        # filled and quoted is not verified: nothing in these records was confirmed on an official page
        self.assertEqual((a["tiers"]["recognized_programmes"], a["tiers"]["verified_identity"],
                          a["tiers"]["application_ready"]), (2, 0, 0))
        self.assertIn("eligible_countries", a["confirmed_programmes_missing"])

    def test_closed_cycle_is_known_information(self):
        o = self.ready()
        o.deadlines = [dl(K.SCHOLARSHIP, "2026-03-01", C.HISTORICAL)]
        self.assertTrue(complete_with_evidence(field_status(o, TODAY))[0])

    def test_unconfirmed_identity_or_unclear_funding_is_not_ready(self):
        o = self.ready()
        o.programme_identity = {"state": "needs_review", "reasons": ["generic title"]}
        self.assertEqual(complete_with_evidence(field_status(o, TODAY))[1], ["programme_identity"])
        o = self.ready()
        o.funding = [FundingComponent("other", covered=None)]
        self.assertIn("funding_type", complete_with_evidence(field_status(o, TODAY))[1])


if __name__ == "__main__":
    unittest.main()
