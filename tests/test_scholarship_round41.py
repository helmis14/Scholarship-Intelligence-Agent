"""Round 41: nationality words that only look like a nationality rule (found on set T)."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent.extract import extract_deadlines, extract_nationality  # noqa: E402


class TestRound41(unittest.TestCase):
    def rule(self, text):
        r, _ = extract_nationality(text)
        return r.mode, r.countries

    def test_any_country_outside_x_excludes_x(self):
        self.assertEqual(self.rule("Citizen of any country outside the United Kingdom"), ("exclude", ["GB"]))

    def test_outside_x_in_brackets_is_a_place_of_study(self):
        mode, countries = self.rule("Open to students who have completed secondary school overseas (outside of New Zealand).")
        self.assertNotIn("NZ", countries)

    def test_degree_of_a_country_is_not_a_nationality(self):
        _, countries = self.rule("Applicants must hold the equivalent of a UK first class honours degree.")
        self.assertNotIn("GB", countries)

    def test_same_conditions_as_citizens_and_agreements_with_x(self):
        _, countries = self.rule("Open to citizens of countries that have agreements with Ukraine. "
                                 "Accommodation in a dormitory under the same conditions as Ukrainian citizens.")
        self.assertNotIn("UA", countries)

    def test_renewal_dates_are_not_application_dates(self):
        d = extract_deadlines("Las renovaciones del programa serán Inicio: 17 de noviembre de 2026 Finalización: 12 de febrero de 2027.",
                              "https://example.org/", date(2026, 10, 21))
        self.assertEqual([x.date for x in d if x.kind.value in ("scholarship", "admission")], [])


if __name__ == "__main__":
    unittest.main()
