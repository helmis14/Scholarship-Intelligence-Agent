"""Round 42: patterns found on set U (now development data)."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent import countries  # noqa: E402
from scholarship_agent.extract import extract_deadlines  # noqa: E402


class TestRound42(unittest.TestCase):
    def test_bosnia_herzegovina_spelling(self):
        self.assertEqual(countries.mentions("a citizen of Bosnia-Herzegovina or Serbia"), ["BA", "RS"])

    def test_programme_start_window_is_not_a_deadline(self):
        d = extract_deadlines("Next Gilman Deadline: October 1, 2026 (for study abroad programs beginning between "
                              "December 1, 2026, to October 31, 2027)", "https://example.org/", date(2026, 10, 21))
        self.assertNotIn("2026-12-01", [x.date for x in d if x.kind.value == "scholarship"])
        self.assertNotIn("2027-10-31", [x.date for x in d if x.kind.value == "scholarship"])


if __name__ == "__main__":
    unittest.main()


class TestRound43(unittest.TestCase):
    def rule(self, text):
        from scholarship_agent.extract import extract_nationality
        r, _ = extract_nationality(text)
        return r.mode, r.countries

    def test_applicants_from_countries_outside_x(self):
        self.assertNotEqual(self.rule("scholarships to outstanding applicants from countries outside the UK")[0], "include")

    def test_latin_america_is_not_the_united_states(self):
        self.assertNotIn("US", self.rule("open to citizens of countries from Eastern Europe, Asia, Africa and Latin America.")[1])

    def test_british_protected_person_is_a_status(self):
        self.assertNotIn("GB", self.rule("Be a citizen of an eligible Commonwealth country, or be a British Protected Person")[1])

    def test_family_members_are_not_the_applicant(self):
        self.assertEqual(self.rule("Be a citizen of the United States. Note, if family members are not United States Citizens, "
                                   "some agencies may be unable to process the applicant."), ("include", ["US"]))

    def test_current_students_of_an_institution_named_after_a_country(self):
        self.assertNotIn("QA", self.rule("Current VCUarts Qatar students are not eligible to apply.")[1])


class TestRound44(unittest.TestCase):
    def rule(self, text):
        from scholarship_agent.extract import extract_nationality
        r, _ = extract_nationality(text)
        return r.mode, r.countries

    def test_from_any_country_outside_x(self):
        self.assertEqual(self.rule("Candidates can be from any country outside the UK but must fulfill all of the "
                                   "following criteria"), ("exclude", ["GB"]))

    def test_education_completed_outside_x(self):
        self.assertNotIn("AE", self.rule("The scholarships are open to those who completed their secondary education "
                                         "outside the UAE.")[1])
