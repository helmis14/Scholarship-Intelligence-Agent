"""Round 52: yearly deadline days written without a year, and the month a next round would fall in."""

import unittest
from datetime import date

from scholarship_agent import site
from scholarship_agent.extract import Page, extract_opportunity
from scholarship_agent.models import ProviderType, SourceType

TODAY = date(2026, 10, 28)


def read(text, title="Example Scholarship"):
    o, _ = extract_opportunity(Page("https://example.edu/s", f"<html><head><title>{title}</title></head><body><p>The "
                                                             f"Example Scholarship covers tuition. {text}</p></body></html>"),
                               provider_name="Ex", provider_type=ProviderType.UNIVERSITY, source_type=SourceType.OFFICIAL,
                               country_hint=[], retrieved_at="2026-10-28", today=TODAY)
    return o


class TestYearlessDeadline(unittest.TestCase):
    def test_a_deadline_day_without_a_year_recurs(self):
        o = read("The application deadline is 15 March. Students must hold a bachelor degree.")
        self.assertEqual([(d.date, d.recurs) for d in o.deadlines], [(None, "03-15")])
        self.assertEqual(site.next_recurring(o, TODAY), "2027-03-15")

    def test_a_year_in_the_sentence_keeps_the_dated_reading(self):
        o = read("Application deadline: 15 March 2026.")
        self.assertEqual([(d.date, d.recurs) for d in o.deadlines], [("2026-03-15", None)])

    def test_other_dates_without_a_year_are_not_deadlines(self):
        self.assertEqual(read("Results will be announced on 1 June.").deadlines, [])


class TestLikelyRound(unittest.TestCase):
    def test_the_month_a_year_after_the_last_round(self):
        o = read("Application deadline: 15 March 2026.")
        r = site.likely_round(o, ["2026-03-15"], TODAY)
        self.assertEqual((r["month"], r["after"], r["basis"]), ("2027-03", "2026-03-15", "last_round"))

    def test_a_round_closed_this_month_moves_a_full_year(self):
        o = read("Application deadline: 2 October 2026.")
        self.assertEqual(site.likely_round(o, ["2026-10-02"], TODAY)["month"], "2027-10")

    def test_yearly_when_the_page_or_the_record_says_so(self):
        o = read("Application deadline: 1 May 2026.", title="Example Scholarship, awarded annually")
        self.assertEqual(site.likely_round(o, ["2026-05-01"], TODAY)["basis"], "yearly")
        o = read("Application deadline: 1 May 2026.")
        self.assertEqual(site.likely_round(o, ["2025-05-03", "2026-05-01"], TODAY)["basis"], "yearly")

    def test_no_estimate_for_coming_or_old_rounds(self):
        o = read("Application deadline: 1 May 2026.")
        self.assertIsNone(site.likely_round(o, ["2027-01-10"], TODAY))
        self.assertIsNone(site.likely_round(o, ["2023-05-01"], TODAY))


if __name__ == "__main__":
    unittest.main()
