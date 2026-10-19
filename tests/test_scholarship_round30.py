"""Round 30 regression examples: funding extent, nationality groups and definitions, list-item quotations, and the
role of dates that are not application deadlines. Sentences are modelled on the development sets (K, L, M, N); each
rule was kept only when tests/devpool.py improved on all four. Passing them is not evidence that the rules generalise;
the frozen set O measures that. Run on every rule change: python3 -m unittest tests.test_scholarship_round30"""

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


def comps(text):
    return {c.kind: c for c in extract_funding(text)[0]}


def fclass(text):
    return classify(Opportunity(id="x", title="X", provider_name="P", info_url=URL, funding=extract_funding(text)[0]))[
        "classification"]


def nat(text):
    r = extract_nationality(text)[0]
    return r.mode, sorted(r.countries)


def applicant(text):
    return sorted({d.date for d in extract_deadlines(text, URL, TODAY) if d.date and d.kind in APPLY})


class TestFundingExtent(unittest.TestCase):
    def test_full_or_partial_waiver_is_not_full_tuition(self):
        self.assertIs(comps("Selected candidates receive a full or partial waiver of the tuition fee.")["tuition"].full, False)
        self.assertIs(comps("Full tuition fee discount for first year of study; £10,000 tuition fee discount for second "
                            "and third year of study")["tuition"].full, False)

    def test_repayment_is_not_a_benefit(self):
        self.assertNotIn("tuition", comps("Fellows who leave the programme early are liable for full or partial "
                                          "restitution of tuition paid."))

    def test_conditions_on_the_applicant_are_not_benefits(self):
        t = ("The students are awarded up to €20,000 for tuition costs and up to €20,000 for living costs.\n"
             "Applicants are obliged to declare additional scholarships, in which case the support would be reduced "
             "accordingly, i.e. only covering tuition costs.")
        self.assertIs(comps(t)["tuition"].full, False)
        self.assertNotIn("tuition", comps("Be liable to pay full tuition fees at the overseas rate"))
        self.assertNotIn("tuition", comps("You will be required to cover the costs of tuition fees at the regular Quebec rate."))

    def test_full_costs_of_tuition_and_a_living_bursary(self):
        self.assertEqual(fclass("A Kennedy Scholarship typically covers the full costs of tuition and health insurance, "
                                "and a means-tested bursary of up to $33,000 to cover living costs."), "fully_funded")

    def test_living_wordings(self):
        self.assertIn("living_allowance", comps("The scholarship covers: Monthly cost-of-living financial assistance."))
        self.assertEqual(fclass("The scholarships are worth over $360,000 and cover full tuition, housing, food, and other "
                                "expenses."), "fully_funded")

    def test_free_study_in_a_benefits_list(self):
        c = comps("Other benefits: Free study, No tuition fee.")["tuition"]
        self.assertEqual((c.covered, c.full), (True, True))
        self.assertIsNot(comps("There is no tuition fee at public universities.").get("tuition", None) and
                         comps("There is no tuition fee at public universities.")["tuition"].full, True)

    def test_partial_tuition_elsewhere_on_the_page_wins(self):
        t = ("All students who fulfil the requirements are eligible for a scholarship that covers 50% of the tuition fee.\n"
             "The award includes a grant of 1000€/month and a scholarship covering the tuition fee.")
        self.assertEqual(fclass(t), "partially_funded")

    def test_heading_line_introduces_benefits(self):
        t = ("Full tuition coverage for 20 incoming students\nThe scholarship covers\nThe tuition fee for one academic "
             "year\nMonthly cost-of-living financial assistance;\nHealth insurance for up to one academic year; and")
        self.assertEqual(fclass(t), "fully_funded")

    def test_contribution_towards_fees_is_tuition(self):
        self.assertEqual(fclass("The scholarship is worth up to £30,000 payable as a contribution of up to £15,000 "
                                "towards fees paid directly to your university, and a stipend of up to £15,000."),
                         "partially_funded")

    def test_assistantship_conditions_and_links_are_not_assistantships(self):
        self.assertNotIn("assistantship", comps("A Teaching Assistantship training must be completed if the fellow is "
                                                "involved in teaching assistantship duties."))
        self.assertNotIn("assistantship", comps("For details and more information about teaching assistantships, click here."))

    def test_other_financial_support_is_not_a_stipend(self):
        self.assertNotIn("stipend", comps("Proof of any other existing financial support (e.g. scholarship, state support)."))


class TestNationalityGroups(unittest.TestCase):
    def test_group_with_international_students_is_no_nationality_rule(self):
        self.assertEqual(nat("Open To: US citizens, permanent residents, DACA recipients, and international students "
                             "eligible to study at their institution"), ("unknown", []))

    def test_definition_is_not_an_exclusion(self):
        t = ("The program is open only to applicants who are citizens or nationals of the United States. The term "
             "\"nationals\" refers to native residents of a possession of the United States such as American Samoa. "
             "It does not refer to a citizen of another country who has applied for U.S. citizenship.")
        self.assertEqual(nat(t), ("include", ["US"]))

    def test_non_us_institution_is_a_place(self):
        self.assertEqual(nat("Applicants must be U.S. citizens. The fellowship does not pay for tuition at any non-U.S. "
                             "institution."), ("include", ["US"]))

    def test_us_nationals_of_american_samoa_are_the_us_rule(self):
        self.assertEqual(nat("Eligible: US Citizens, US National residents of American Samoa, or those expecting their "
                             "citizenship."), ("include", ["US"]))

    def test_american_indian_is_not_india(self):
        self.assertEqual(nat("Applicants must be U.S. citizens. American Indian College Fund provides Native American "
                             "students with scholarships."), ("include", ["US"]))

    def test_citizen_of_a_country_outside_a_list_item(self):
        self.assertEqual(nat("are a citizen of a country outside of the EU/EEA and Switzerland;"), ("exclude", EEA_CH))

    def test_who_is_charged_fees_is_not_the_scholarship_rule(self):
        self.assertEqual(nat("Tuition fees will be charged from citizens of a country outside the European Union (EU) "
                             "and the European Economic Area (EEA) or Switzerland."), ("unknown", []))


class TestListItemQuotation(unittest.TestCase):
    """The evidence check on an eligibility quotation (its warning holds the decision for review)."""
    def _warn(self, quote, codes=("US",)):
        from scholarship_agent.evidence import substantiates
        return substantiates("nationality", {"mode": "include", "countries": list(codes)}, quote)

    def test_requirement_list_items_state_who_is_eligible(self):
        self.assertIsNone(self._warn("A United States citizen or permanent resident"))
        self.assertIsNone(self._warn("United States Citizen, Permanent Legal Resident, or DACA"))

    def test_a_list_item_supports_only_the_countries_it_names(self):
        self.assertIsNotNone(self._warn("Be a United States citizen and a non-UK resident", codes=("CA", "US")))

    def test_prose_about_the_programme_still_needs_review(self):
        self.assertIsNotNone(self._warn("Scholars immerse themselves in the culture of the US as part of a group of "
                                        "British graduates."))


class TestDateRolesStage3(unittest.TestCase):
    def test_notification_is_not_a_deadline(self):
        t = ("22 March 2026: Deadline to complete your application to the programme\n"
             "30 March 2026: Applicants are informed of acceptance\n"
             "10 April 2026: Deadline for accepted applicants to apply for the scholarship")
        self.assertEqual(applicant(t), ["2026-03-22", "2026-04-10"])

    def test_programme_stay_dates_are_not_deadlines(self):
        t = ("Die Ausschreibung für 2028-29 bezieht sich auf einen Aufenthaltsbeginn in den USA ab dem 1. August 2028 und "
             "einem Aufenthaltsende spätestens am 31. Mai 2029.")
        self.assertEqual(applicant(t), [])

    def test_fee_payment_offer_and_permit_dates(self):
        t = ("have completed your application before the application deadline on 15 January 2026; have paid the "
             "application fee by 2 February 2026; and have chosen a programme")
        self.assertEqual(applicant(t), ["2026-01-15"])
        t = ("You must apply via UCAS by the Equal Consideration Deadline of 13th January 2027. Applicants who receive an "
             "offer from the University by 31st March 2027, must accept the University as a Firm choice by 3rd May 2027.")
        self.assertEqual(applicant(t), ["2027-01-13"])
        self.assertEqual(applicant("You can only apply if your residence permit is still valid until 2 September 2027."), [])

    def test_application_and_documentation_deadline_is_the_deadline(self):
        t = ("Deadline for application and submission of documentation: November 26, 2026\n"
             "Communication of decision: From 14 to 18 of December 2026")
        self.assertEqual(applicant(t), ["2026-11-26"])

    def test_open_through_is_the_closing_date(self):
        self.assertEqual(applicant("Competition: Held annually; open now and accepting applications through October 27, "
                                   "2026"), ["2026-10-27"])
        o = Opportunity(id="x", title="X", provider_name="P", info_url=URL, deadlines=extract_deadlines(
            "The portal is open September 1, 2026 through October 27, 2026.", URL, TODAY))
        self.assertEqual(cycle_status(o, TODAY)["state"], "open")

    def test_deadline_has_passed_without_a_date_is_closed(self):
        for t in ("Die Frist zur Bewerbung im Programm 2027-28 ist verstrichen.", "The application deadline has passed."):
            o = Opportunity(id="x", title="X", provider_name="P", info_url=URL, deadlines=extract_deadlines(t, URL, TODAY))
            self.assertEqual(cycle_status(o, TODAY)["state"], "closed", t)


if __name__ == "__main__":
    unittest.main()
