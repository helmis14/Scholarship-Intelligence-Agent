"""Round 18: nationality exceptions ("other than Ghana" excludes Ghana) and country lists written one per line or
separated by punctuation. Offline."""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent import countries  # noqa: E402
from scholarship_agent.ai_extract import validate  # noqa: E402
from scholarship_agent.extract import Page, extract_nationality, extract_opportunity  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402


def nat(text):
    r, _ = extract_nationality(text)
    return r.mode, r.countries


class TestExceptions(unittest.TestCase):
    def test_group_minus_country_is_needs_review_never_the_excepted_country(self):
        r, _ = extract_nationality("Applicants must be citizens of ECOWAS member states other than Ghana.")
        self.assertEqual((r.mode, r.countries), ("unknown", []))
        self.assertTrue(r.note.startswith("needs review"))

    def test_any_except_is_exclusion(self):
        self.assertEqual(nat("Open to all nationalities except Nigeria."), ("exclude", ["NG"]))

    def test_explicit_list_minus_exception_keeps_the_rest(self):
        self.assertEqual(nat("Citizens of Kenya, Uganda and Tanzania, excluding Uganda, may apply."),
                         ("include", ["KE", "TZ"]))

    def test_plain_citizenship_still_included(self):
        self.assertEqual(nat("Applicants must be citizens of Ghana."), ("include", ["GH"]))

    def test_needs_review_reaches_the_opportunity_as_evidence_not_a_value(self):
        html = "<h1>Programme</h1><p>Applicants must be citizens of ECOWAS member states other than Ghana.</p>"
        o, _ = extract_opportunity(Page("https://x.example/s", html), provider_name="x",
                                   provider_type=ProviderType.OTHER, source_type=SourceType.OFFICIAL,
                                   country_hint=[], retrieved_at="t", today=date(2026, 10, 18))
        self.assertNotIn("GH", o.nationality.countries)
        self.assertTrue(any(e.field == "nationality" and e.verdict == "needs_review" for e in o.evidence))

    def test_claude_value_contradicting_the_exception_is_rejected(self):
        q = "citizens of ECOWAS member states other than Ghana"
        self.assertIsNotNone(validate("eligible_nationalities", ["GH"], q, q))
        self.assertIsNone(validate("eligible_nationalities", ["GH"], "citizens of Ghana", "citizens of Ghana"))


class TestCountryLists(unittest.TestCase):
    def test_two_groups_one_per_line(self):
        t = ("Scholarships are available to citizens of the following countries:\nArmenia\nAzerbaijan\nGeorgia\n\n"
             "and to nationals of\nAustralia\nCanada (Quebec)\nJapan\nHow to apply")
        r, _ = extract_nationality(t)
        self.assertEqual((r.mode, r.countries, r.basis),
                         ("include", ["AM", "AU", "AZ", "CA", "GE", "JP"], "citizenship"))

    def test_cue_line_without_following_countries(self):
        self.assertEqual(nat("Who can apply\nCitizens of\nIndia\nNepal\nDeadline 1 May"), ("include", ["IN", "NP"]))

    def test_punctuation_separated(self):
        self.assertEqual(nat("Eligible are nationals of: Armenia; Belarus, Georgia; Moldova and Ukraine."),
                         ("include", ["AM", "BY", "GE", "MD", "UA"]))

    def test_bracketed_and_accented_names(self):
        self.assertEqual(countries.mentions("Congo (Democratic Republic), Congo (Republic), São Tomé and Príncipe"),
                         ["CD", "CG", "ST"])

    def test_lines_that_are_not_countries_end_the_list(self):
        r, _ = extract_nationality("Citizens of the following countries are eligible\nKenya\nGhana\n"
                                   "The orientation week takes place in Nigeria.")
        self.assertEqual(r.countries, ["GH", "KE"])


if __name__ == "__main__":
    unittest.main()
