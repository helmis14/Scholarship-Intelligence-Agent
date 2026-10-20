"""Round 38: "report a mistake" - stored without personal details, reviewed by the operator, and two open reports on one field
hold that field as needs_review."""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from datetime import date  # noqa: E402
from scholarship_agent.extract import Page, extract_opportunity  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402
from scholarship_agent.service import NotFound, ScholarshipService  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402


class TestIssueReports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.svc = ScholarshipService(store=self.store, search=None)
        page = Page("https://example.org/s", "<html><body><h1>Example Fellowship</h1><p>Fellows receive a monthly stipend of 1,200 euros. "
                    "Tuition is not covered. The application deadline is 1 December 2026.</p></body></html>")
        o, _ = extract_opportunity(page, provider_name="Example", provider_type=ProviderType.OTHER, source_type=SourceType.OFFICIAL,
                                   country_hint=[], retrieved_at="t", today=date(2026, 10, 20))
        o.id = "opp1"
        self.store.save_opportunity(o, "k", "https://example.org/s")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_report_is_stored_without_contact_details(self):
        r = self.svc.report_issue("opp1", "deadline", "Wrong, mail me at ayu@example.com or call +62 812 3456 7890", "2026-12-01")
        self.assertEqual(r["status"], "open")
        row = self.svc.list_issue_reports()["reports"][0]
        self.assertNotIn("ayu@example.com", row["note"])
        self.assertNotIn("812 3456", row["note"])
        self.assertEqual(row["field"], "deadline")

    def test_bad_field_and_empty_note_are_refused(self):
        with self.assertRaises(ValueError):
            self.svc.report_issue("opp1", "colour", "something is wrong here")
        with self.assertRaises(ValueError):
            self.svc.report_issue("opp1", "deadline", "x")

    def test_two_open_reports_hold_the_field_until_resolved(self):
        before = self.svc.get_opportunity("opp1")["opportunity"]["field_status"]["funding_type"]["state"]
        self.assertNotIn(before, ("not_stated", "needs_review"))
        self.svc.report_issue("opp1", "funding", "It is not a stipend, the page says a loan")
        self.assertEqual(self.svc.get_opportunity("opp1")["opportunity"]["field_status"]["funding_type"]["state"], before)
        self.svc.report_issue("opp1", "funding", "The funding class is wrong, see the quotation")
        self.assertEqual(self.svc.get_opportunity("opp1")["opportunity"]["field_status"]["funding_type"]["state"], "needs_review")
        for rep in self.svc.list_issue_reports()["reports"]:
            self.svc.resolve_issue_report(rep["id"], "fixed", "checked against the official page")
        self.assertEqual(self.svc.get_opportunity("opp1")["opportunity"]["field_status"]["funding_type"]["state"], before)

    def test_resolve_unknown_report(self):
        with self.assertRaises(NotFound):
            self.svc.resolve_issue_report(999, "fixed")


if __name__ == "__main__":
    unittest.main()
