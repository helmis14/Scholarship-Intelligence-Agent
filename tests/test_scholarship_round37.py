"""Round 37: the risk gate. Claim kinds whose measured precision was too low (assistantship and fee-waiver funding classes,
"not_announced" cycles, applicant deadlines with several dates; with SCHOLAR_RISK_GATE=strict also tuition-only and
stipend-only funding, "any nationality" and "upcoming" cycles) are sent to review instead of reported as known."""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.audit import field_status  # noqa: E402
from scholarship_agent.extract import extract_opportunity  # noqa: E402
from scholarship_agent.heldout import load_page  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402
from scholarship_agent.extract import Page  # noqa: E402

TODAY = date(2026, 10, 20)


def states(text, mode):
    old = os.environ.get("SCHOLAR_RISK_GATE")
    os.environ["SCHOLAR_RISK_GATE"] = mode
    try:
        o, _ = extract_opportunity(Page("https://www.example.org/s", "<html><body><h1>Example Scholarship</h1><p>" + text + "</p></body></html>"),
                                   provider_name="Example", provider_type=ProviderType.OTHER, source_type=SourceType.OFFICIAL,
                                   country_hint=[], retrieved_at="t", today=TODAY)
        fs = field_status(o, TODAY)
        return {k: fs[k]["state"] for k in ("funding_type", "cycle", "deadline", "eligible_countries")}
    finally:
        if old is None:
            os.environ.pop("SCHOLAR_RISK_GATE", None)
        else:
            os.environ["SCHOLAR_RISK_GATE"] = old


class TestRiskGate(unittest.TestCase):
    def test_several_applicant_dates_go_to_review(self):
        t = "Application deadline: 1 December 2026. Applications close on 15 January 2027 for the second round."
        self.assertEqual(states(t, "standard")["deadline"], "needs_review")
        self.assertNotEqual(states(t, "off")["deadline"], "needs_review")

    def test_one_date_stays_known(self):
        self.assertNotEqual(states("Application deadline: 1 December 2026.", "strict")["deadline"], "needs_review")

    def test_assistantship_class_goes_to_review(self):
        t = "The funding is tied to a graduate research assistantship with a monthly salary of 2,000 euros."
        self.assertEqual(states(t, "standard")["funding_type"], "needs_review")
        self.assertNotEqual(states(t, "off")["funding_type"], "needs_review")

    def test_strict_also_holds_stipend_only(self):
        t = "Fellows receive a monthly stipend of 1,200 euros. Tuition is not covered."
        self.assertNotEqual(states(t, "standard")["funding_type"], "needs_review")
        self.assertEqual(states(t, "strict")["funding_type"], "needs_review")


if __name__ == "__main__":
    unittest.main()
