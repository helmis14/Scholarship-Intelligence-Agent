"""Round 34 regression examples (pool K to Q): timeline pages and the host country in nationality. Each rule was kept
only when tests/devpool.py rose without any set falling. Run: python3 -m unittest tests.test_scholarship_round34"""
import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.extract import extract_deadlines, extract_nationality  # noqa: E402
from scholarship_agent.models import DeadlineKind  # noqa: E402

TODAY = date(2026, 10, 20)
URL = "https://www.example.org/scholarship"
APPLY = (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)


def applicant(text):
    return sorted({d.date for d in extract_deadlines(text, URL, TODAY) if d.date and d.kind in APPLY})


def nat(text):
    r = extract_nationality(text)[0]
    return r.mode, sorted(r.countries)


class TestTimelines(unittest.TestCase):
    def test_open_and_close_lines(self):
        self.assertEqual(applicant("The next window\nOpen: 1 December 2026\nClose: 12 February 2027. No applications after this date."),
                         ["2027-02-12"])

    def test_opening_and_closing_call_and_feedback(self):
        t = ("03 December 2026: opening call\n01 March 2027 at 5pm CET: closing call (last application date)\n"
             "17 November 2027: deadline for sending feedback")
        self.assertEqual(applicant(t), ["2027-03-01"])

    def test_application_window_with_a_colon(self):
        self.assertEqual(applicant("Application: September 1, 2026 to October 30, 2026\nApplication: March 1, 2027 to April 30, 2027"),
                         ["2026-10-30", "2027-04-30"])

    def test_spanish_window(self):
        self.assertEqual(applicant("El llamado estará abierto desde el 4 de febrero hasta el 14 de mayo de 2026 a las 23:59."),
                         ["2026-05-14"])

    def test_as_of_and_degree_dates_are_conditions(self):
        self.assertEqual(applicant("Applicants must be residing in Japan as of July 1, 2026."), [])
        self.assertEqual(applicant("Solo se considerará a aplicantes que obtendrán su título hasta el 1 de agosto de 2026."), [])


class TestNationalityHostCountry(unittest.TestCase):
    def test_dual_citizenship_exclusion_names_no_second_country(self):
        self.assertEqual(nat("Applicants must be citizens of Japan. Persons holding dual Japan-U.S. citizenship are NOT eligible."),
                         ("include", ["JP"]))

    def test_study_destination_is_not_a_nationality(self):
        self.assertEqual(nat("The programme awards grants to Malaysian students to study for a Master's in the United States."),
                         ("include", ["MY"]))

    def test_spanish_destination(self):
        self.assertEqual(nat("Las becas están restringidas a ciudadanos argentinos. No están disponibles para ciudadanos argentinos "
                             "que hayan empezado un programa para graduados en los Estados Unidos."), ("include", ["AR"]))

    def test_us_law_is_a_thing(self):
        self.assertEqual(nat("Applicants must be citizens of Japan. This U.S. law is under section 212(e) of the Act."),
                         ("include", ["JP"]))

    def test_open_to_international_graduate_students(self):
        self.assertEqual(nat("This program is open to Canadian, permanent resident, and international graduate students."),
                         ("unknown", []))

    def test_a_real_us_rule_still_counts(self):
        self.assertEqual(nat("Applicants must be citizens or nationals of the United States."), ("include", ["US"]))


if __name__ == "__main__":
    unittest.main()
