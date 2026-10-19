"""Round 26: reporting tiers (lead -> recognised -> verified identity -> verified eligibility -> verified current
cycle -> verified funding -> human-reviewed application-ready) and the set K benchmark scorer. Offline."""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "heldout_k"))

from scholarship_agent.audit import REVIEWED_TAG, tiers  # noqa: E402
from scholarship_agent.models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, FundingComponent,  # noqa: E402
                                      NationalityRule, Opportunity, VerificationStatus)

TODAY = date(2026, 10, 18)
URL = "https://www.example.ac.uk/scholarships/ada"


def ok(field, value):
    return Evidence(field=field, value=value, source_url=URL, snippet="quoted", status=VerificationStatus.CONFIRMED,
                    authority="1_official_programme_page")


def verified(**kw):
    base = dict(id="sch_a", title="Ada Lovelace Scholarship", provider_name="Example University", info_url=URL,
                source_authority="1_official_programme_page", page_type="scholarship_program",
                programme_identity={"state": "confirmed", "reasons": []}, verification_status=VerificationStatus.CONFIRMED,
                nationality=NationalityRule(mode="include", countries=["KE"]),
                deadlines=[Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=DeadlineCertainty.CONFIRMED, date="2027-01-15")],
                funding=[FundingComponent("tuition", full=True)],
                evidence=[ok("nationality", "include:KE"), ok("deadline.scholarship", "2027-01-15"), ok("funding.tuition", True)])
    return Opportunity(**(base | kw))


class TestTiers(unittest.TestCase):
    def test_each_tier_needs_official_confirmation_and_ready_needs_a_person(self):
        unverified = verified(id="sch_b", verification_status=VerificationStatus.EXTRACTED)
        no_cycle = verified(id="sch_c", evidence=[ok("nationality", "include:KE"), ok("funding.tuition", True)])
        reviewed = verified(id="sch_d", tags=[REVIEWED_TAG])
        catalogue = verified(id="sch_e", page_type="scholarship_catalog")
        t = tiers([verified(), unverified, no_cycle, reviewed, catalogue], TODAY, discovered_leads=40)
        self.assertEqual(t, {"discovered_leads": 40, "recognized_programmes": 4, "verified_identity": 3,
                             "verified_eligibility": 3, "verified_current_cycle": 2, "verified_funding": 2,
                             "application_ready": 1, "verified_but_not_reviewed": 1})


class TestSetKScorer(unittest.TestCase):
    def test_extra_fields_are_scored_against_labels(self):
        import score_k
        lab = {"residency": ["KE"], "funding_class": "fully_funded", "cycle_status": "open"}
        o = Opportunity(id="x", title="t", provider_name="p",
                        nationality=NationalityRule(mode="unknown", residency_required=["KE"]),
                        funding=[FundingComponent("tuition", full=True), FundingComponent("stipend")],
                        deadlines=[Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=DeadlineCertainty.CONFIRMED,
                                            date="2027-01-15")])
        got = score_k.extra_fields(o, lab, TODAY)
        self.assertEqual(got, {"residency": (True, ["KE"]), "funding_class": (True, "fully_funded"),
                               "cycle_status": (True, "open")})


if __name__ == "__main__":
    unittest.main()
