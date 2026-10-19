"""Round 31 regression examples: date roles stage 4, exclusion lists, residence conditions, the full cost of
attendance, and European demonyms. Sentences are modelled on the development sets (K to O); each rule was kept only
when tests/devpool.py improved on the pooled sets without lowering any of them. Passing them is not evidence that the
rules generalise. Run on every rule change: python3 -m unittest tests.test_scholarship_round31"""

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent import countries  # noqa: E402
from scholarship_agent.audit import cycle_status  # noqa: E402
from scholarship_agent.extract import extract_deadlines, extract_funding, extract_nationality  # noqa: E402
from scholarship_agent.funding import classify  # noqa: E402
from scholarship_agent.models import DeadlineKind, Opportunity  # noqa: E402

TODAY = date(2026, 10, 19)
URL = "https://www.example.org/scholarship"
APPLY = (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)
EEA_CH = sorted(set(countries.EEA) | {"CH"})


def nat(text):
    r = extract_nationality(text)[0]
    return r.mode, sorted(r.countries)


def applicant(text):
    return sorted({d.date for d in extract_deadlines(text, URL, TODAY) if d.date and d.kind in APPLY})


def fclass(text):
    return classify(Opportunity(id="x", title="X", provider_name="P", info_url=URL, funding=extract_funding(text)[0]))[
        "classification"]


class TestDemonyms(unittest.TestCase):
    def test_two_nationalities_with_or(self):
        self.assertEqual(nat("Applicants must have Spanish or Portuguese nationality."), ("include", ["ES", "PT"]))

    def test_european_demonyms_are_countries(self):
        self.assertEqual(countries.mentions("Dutch, Swedish and Czech citizens"), ["NL", "SE", "CZ"])

    def test_demonym_as_an_adjective_of_a_thing_is_not_a_country(self):
        for s in ("You are eligible to meet the requirements for obtaining a Dutch student visa.",
                  "a student has the right to use Finnish Student Health Service",
                  "Full medical coverage under the Austrian national health plan",
                  "the program fee includes the Austrian students' union fee"):
            self.assertEqual(countries.mentions(s), [], s)

    def test_fee_table_column_is_not_an_exclusion(self):
        self.assertEqual(nat("Saudi | 5000 | 2500\nNon-Saudi | 7500 | 3750"), ("unknown", []))


class TestExclusionLists(unittest.TestCase):
    def test_not_open_for_students_from_a_bracketed_list(self):
        t = ("The scholarship is aimed at students coming from countries outside of EU/EEA/Switzerland and who are "
             "required to pay tuition fees. The scholarship is NOT open for students from the twelve countries with which "
             "Sweden has long-term development cooperation (Bangladesh, Bolivia, Burkina Faso, Cambodia, Ethiopia, Kenya, "
             "Mali, Mozambique, Rwanda, Tanzania, Uganda and Zambia).")
        mode, codes = nat(t)
        self.assertEqual(mode, "exclude")
        self.assertTrue({"BD", "BO", "BF", "KH", "ET", "KE", "ML", "MZ", "RW", "TZ", "UG", "ZM"} <= set(codes))
        self.assertTrue(set(EEA_CH) <= set(codes))


class TestResidenceConditions(unittest.TestCase):
    def test_residence_during_the_fellowship_is_not_an_exclusion(self):
        t = ("Applicants must be a US citizen, a permanent resident, a DACA recipient, an asylee, or a refugee. In addition, "
             "a foreign national who has been living in the United States or US territories for the three years immediately "
             "preceding the application deadline is also eligible, provided they do not establish permanent residence "
             "outside the United States during the period of the fellowship.")
        self.assertEqual(nat(t), ("unknown", []))

    def test_us_citizens_alone_stay_a_rule(self):
        self.assertEqual(nat("Applicants must be a US citizen or a permanent resident."), ("include", ["US"]))


class TestFullCostOfAttendance(unittest.TestCase):
    def test_entire_cost_of_attendance_is_fully_funded(self):
        self.assertEqual(fclass("The award is intended to cover the entire cost of attendance for four years at the "
                                "University, plus coverage of supplemental enrichment experiences."), "fully_funded")

    def test_a_cost_the_applicant_must_meet_is_not_a_benefit(self):
        self.assertNotEqual(fclass("You must show that you can meet the full cost of attendance yourself."), "fully_funded")


class TestDateRolesStage4(unittest.TestCase):
    def test_award_term_dates_are_not_deadlines(self):
        t = ("Completed applications must be submitted no later than 5:00 PM Eastern Time, September 17, 2026.\n"
             "The fellowship term must begin no earlier than July 1, 2027, and no later than July 1, 2028. It must conclude "
             "no later than December 31, 2028.")
        self.assertEqual(applicant(t), ["2026-09-17"])
        o = Opportunity(id="x", title="X", provider_name="P", info_url=URL, deadlines=extract_deadlines(t, URL, TODAY))
        self.assertEqual(cycle_status(o, TODAY)["state"], "closed")

    def test_news_date_is_not_a_deadline(self):
        t = "DAAD Scholarships for International Students (Application Deadline: January 11, 2026)\nNews from Dec 10, 2025"
        self.assertEqual(applicant(t), ["2026-01-11"])

    def test_document_and_fee_step_after_the_date(self):
        t = ("15 January 2027: application deadline on University Admissions (last day to rank your programme choices)\n"
             "1 February 2027: deadline to submit supporting documentation and pay the application fee to University "
             "Admissions.\n15 February 2027: Deadline to submit the scholarship application.")
        self.assertEqual(applicant(t), ["2027-01-15", "2027-02-15"])

    def test_german_range_opens_and_closes(self):
        t = "Der Bewerbungszeitraum für die Deutschlandstipendien findet vom 9. November bis zum 6. Dezember 2026 statt."
        self.assertEqual(applicant(t), ["2026-12-06"])
        roles = {d.date: str(d.kind) for d in extract_deadlines(t, URL, TODAY) if d.date}
        self.assertEqual(roles.get("2026-11-09"), "opening")

    def test_old_faq_date_without_a_current_deadline_is_a_reference(self):
        t = ("The programme will no longer be accepting applications.\nFrequently asked questions\n"
             "When is the deadline? Applications closed on September 1, 2019 at 5 PM.")
        self.assertEqual(applicant(t), [])


class TestModelReadings(unittest.TestCase):
    def test_award_total_is_not_a_stipend(self):
        from scholarship_agent.ai_extract import validate
        q1, q2 = "The maximum Dissertation Fieldwork Grant is $25,000.", "A monthly stipend of EUR 1,200 for living costs."
        page = q1 + "\n" + q2
        self.assertIsNotNone(validate("stipend_amount", 25000, q1, page))
        self.assertIsNone(validate("stipend_amount", 1200, q2, page))


if __name__ == "__main__":
    unittest.main()
