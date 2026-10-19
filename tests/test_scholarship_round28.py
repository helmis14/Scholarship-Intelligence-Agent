"""Round 28 regression examples: the role of each date (opening, nomination, application, other step, old reference)
and nationality negation. Sentences are modelled on the development pages (sets K and L), never on the frozen set M.
Run on every rule change: python3 -m unittest tests.test_scholarship_round28"""

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent import countries  # noqa: E402
from scholarship_agent.audit import cycle_status  # noqa: E402
from scholarship_agent.extract import extract_deadlines, extract_nationality  # noqa: E402
from scholarship_agent.models import DeadlineKind, Opportunity  # noqa: E402

TODAY = date(2026, 10, 18)
URL = "https://www.example.ac.uk/scholarships/x"
APPLY = (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)


def roles(text):
    """{kind: sorted dates} for every dated entry"""
    out = {}
    for d in extract_deadlines(text, URL, TODAY):
        if d.date:
            out.setdefault(str(d.kind), set()).add(d.date)
    return {k: sorted(v) for k, v in out.items()}


def applicant(text):
    return sorted({d.date for d in extract_deadlines(text, URL, TODAY) if d.date and d.kind in APPLY})


def status(text):
    o = Opportunity(id="x", title="X", provider_name="P", info_url=URL, deadlines=extract_deadlines(text, URL, TODAY))
    return cycle_status(o, TODAY)["state"]


class TestDateRoles(unittest.TestCase):
    def test_opening_line_is_not_a_deadline(self):
        t = "Application deadlines for the KTH Scholarship\n1 December 2026: Application opens\n" \
            "15 January 2027: Application closes\n1 April 2027: Scholarship results announced"
        self.assertEqual(applicant(t), ["2027-01-15"])
        self.assertEqual(roles(t).get("opening"), ["2026-12-01"])

    def test_next_call_opening_is_upcoming(self):
        t = "We have received the maximum number of applications for the current call. The next call will open on " \
            "November 15, 2026."
        self.assertEqual(applicant(t), [])
        self.assertEqual(roles(t).get("opening"), ["2026-11-15"])
        self.assertEqual(status(t), "upcoming")

    def test_nomination_deadline_is_its_own_role(self):
        t = "Important dates and deadlines\nSchool nomination deadline: October 9, 2026\n" \
            "Student scholarship application deadline and documentation submission deadline: November 6, 2026"
        self.assertEqual(applicant(t), ["2026-11-06"])
        self.assertEqual(roles(t).get("nomination"), ["2026-10-09"])

    def test_coordinator_selection_is_a_nomination(self):
        t = "Candidate selection deadline by master's program coordinators: Wednesday 25 March 2026, 11:59pm\n" \
            "After being selected, deadline to apply for the scholarship: Tuesday 31 March 2026, 11:59pm"
        self.assertEqual(applicant(t), ["2026-03-31"])
        self.assertEqual(roles(t).get("nomination"), ["2026-03-25"])

    def test_old_faq_dates_are_references(self):
        t = "Student scholarship application deadline: November 6, 2026\nFrequently asked questions\n" \
            "When can I nominate a student?\nNominations will be accepted beginning July 1, 2025. This year's deadline " \
            "to nominate a Pearson Scholar is October 10, 2025."
        self.assertEqual(applicant(t), ["2026-11-06"])
        self.assertNotIn("2025-10-10", applicant(t))

    def test_proof_of_degree_date_is_not_the_application_deadline(self):
        t = "Applicants who have not fulfilled all requirements for their degree at the time of application must " \
            "submit proof no later than October 15, 2025."
        self.assertEqual(applicant(t), [])

    def test_expired_deadline_stays_an_application_deadline(self):
        t = "Application deadline: Tuesday 1 September 2026, 11.59pm BST\nThe application deadline has now passed."
        self.assertEqual(applicant(t), ["2026-09-01"])
        self.assertEqual(status(t), "closed")

    def test_open_until_is_a_deadline(self):
        self.assertEqual(applicant("Applications are open until 15 March 2027."), ["2027-03-15"])
        t = "The portal opens on 1 February 2027 and closes on 1 March 2027."
        self.assertEqual(applicant(t), ["2027-03-01"])
        self.assertEqual(roles(t).get("opening"), ["2027-02-01"])

    def test_fee_payment_date_is_not_the_application_deadline(self):
        self.assertEqual(applicant("The deadline for tuition fee payment for the first academic year is 31 August 2026."), [])

    def test_school_form_access_date_is_not_the_applicants(self):
        t = "Schools that have previously participated will receive access to the nomination form beginning July 6, " \
            "2026. The deadline to nominate a student is October 9, 2026."
        self.assertEqual(applicant(t), [])


def nat(text):
    return extract_nationality(text)[0]


class TestNationalityNegation(unittest.TestCase):
    def test_non_us_citizens(self):
        r = nat("Fellowship recipients must be non-U.S. citizens and must not hold U.S. permanent resident status.")
        self.assertEqual((r.mode, r.countries), ("exclude", ["US"]))

    def test_non_canadian(self):
        r = nat("To be eligible you must be an international student (i.e. a non-Canadian requiring a study permit).")
        self.assertEqual((r.mode, r.countries), ("exclude", ["CA"]))

    def test_us_citizens_are_not_eligible(self):
        self.assertEqual(nat("U.S. citizens are not eligible for this award.").countries, ["US"])
        self.assertEqual(nat("U.S. citizens are not eligible for this award.").mode, "exclude")

    def test_not_a_national_of(self):
        self.assertEqual((nat("You are not a German national.").mode, nat("You are not a German national.").countries),
                         ("exclude", ["DE"]))
        r = nat("Applicants must not be citizens of Japan.")
        self.assertEqual((r.mode, r.countries), ("exclude", ["JP"]))

    def test_never_held_nationality(self):
        r = nat("Applicants and their parents must all hold foreign nationality and have never held Taiwan Nationality.")
        self.assertEqual((r.mode, r.countries), ("exclude", ["TW"]))

    def test_citizens_and_foreign_citizens_means_everyone(self):
        r = nat("Canadian citizens, permanent residents of Canada and foreign citizens are eligible to apply.")
        self.assertEqual(r.mode, "any")

    def test_all_except(self):
        r = nat("The programme is open to all nationalities except Russian and Belarusian citizens.")
        self.assertEqual((r.mode, r.countries), ("exclude", ["BY", "RU"]))

    def test_several_eligible_nationalities(self):
        r = nat("Citizens of Kenya, Uganda and Tanzania are eligible to apply.")
        self.assertEqual((r.mode, r.countries), ("include", ["KE", "TZ", "UG"]))

    def test_eligible_and_excluded_in_one_sentence(self):
        r = nat("Citizens of Kenya and Uganda are eligible; citizens of Tanzania are not eligible.")
        self.assertEqual((r.mode, r.countries), ("include", ["KE", "UG"]))

    def test_positive_control(self):
        r = nat("Applicants must be citizens of the United States of America.")
        self.assertEqual((r.mode, r.countries), ("include", ["US"]))

    def test_list_elsewhere_is_unknown(self):
        self.assertEqual(nat("Be a citizen of an eligible country (the list is on another page).").mode, "unknown")

    def test_efta_exclusion_includes_switzerland(self):
        r = nat("Applicants must have a non-EEA/non-EFTA passport.")
        self.assertEqual(set(r.countries), set(countries.EEA) | {"CH"})

    def test_domicile_is_residency_not_nationality(self):
        r = nat("To apply for this scholarship, you must be domiciled in India or Pakistan.")
        self.assertEqual((r.mode, r.residency_required), ("unknown", ["IN", "PK"]))

    def test_condition_on_where_to_hold_is_not_a_ban(self):
        r = nat("Canadian citizens, permanent residents of Canada and foreign citizens are eligible to apply.\n"
                "Applicants who are not Canadian citizens or permanent residents of Canada may only hold their "
                "fellowship at a Canadian institution.")
        self.assertEqual((r.mode, r.residency_required), ("any", []))

    def test_negated_country_is_never_made_eligible_by_another_sentence(self):
        r = nat("Applicants will be pursuing graduate studies in the U.S. as citizens of their home country.\n"
                "Fellowship recipients must be non-U.S. citizens.")
        self.assertEqual((r.mode, r.countries), ("exclude", ["US"]))

    def test_fee_liability_sentence_is_not_the_scholarship_rule(self):
        r = nat("You must pay tuition fee if you are citizen of a country outside the European Union (EU) or the "
                "European Economic Area (EEA) or Switzerland.")
        self.assertNotEqual((r.mode, r.countries), ("include", ["CH"]))


if __name__ == "__main__":
    unittest.main()
