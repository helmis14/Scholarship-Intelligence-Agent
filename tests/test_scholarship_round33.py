"""Round 33 regression examples (pool K to P): nationality definitions and procedural sentences, sentences about other
scholarships, cycle states, and funding sentences that are questions or budget instructions. Each rule was kept only
when tests/devpool.py rose without any set falling. Run: python3 -m unittest tests.test_scholarship_round33"""
import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.audit import cycle_status  # noqa: E402
from scholarship_agent.extract import extract_deadlines, extract_funding, extract_nationality  # noqa: E402
from scholarship_agent.funding import classify  # noqa: E402
from scholarship_agent.models import Opportunity  # noqa: E402

TODAY = date(2026, 10, 19)
URL = "https://www.example.org/scholarship"


def nat(text):
    r = extract_nationality(text)[0]
    return r.mode, sorted(r.countries)


def cycle(text):
    return cycle_status(Opportunity(id="x", title="X", provider_name="P", info_url=URL,
                                    deadlines=extract_deadlines(text, URL, TODAY)), TODAY)["state"]


def fclass(text):
    return classify(Opportunity(id="x", title="X", provider_name="P", info_url=URL, funding=extract_funding(text)[0]))[
        "classification"]


class TestNationality(unittest.TestCase):
    def test_a_definition_of_international_is_not_a_rule(self):
        self.assertEqual(nat("You are considered an international applicant if you are not a U.S. citizen or permanent "
                             "resident."), ("unknown", []))

    def test_a_procedural_sentence_is_not_a_rule(self):
        self.assertEqual(nat("U.S. citizens or permanent residents who have completed coursework outside the United States "
                             "should follow the international admissions requirements for that country."), ("unknown", []))

    def test_a_sentence_about_other_scholarships_is_not_a_rule(self):
        self.assertEqual(nat("Kent State offers other scholarship opportunities; please read the eligibility criteria "
                             "carefully as some are for U.S. citizens only."), ("unknown", []))

    def test_a_real_rule_still_counts(self):
        self.assertEqual(nat("To qualify, you must hold citizenship in a country outside the United States and also not "
                             "possess United States citizenship or permanent residency."), ("exclude", ["US"]))
        self.assertEqual(nat("Applicants must be a U.S. citizen or permanent resident."), ("include", ["US"]))


class TestCycle(unittest.TestCase):
    def test_an_approximate_date_is_not_a_cycle_state(self):
        self.assertEqual(cycle("The application deadline for the award is typically in early October."), "not_stated")

    def test_rolling_awards_are_not_a_rolling_application_cycle(self):
        self.assertEqual(cycle("Scholarships are awarded on a rolling basis to students while funds are available."),
                         "not_stated")
        self.assertEqual(cycle("Applications are accepted on a rolling basis throughout the year."), "rolling")

    def test_a_confirmed_future_deadline_is_open(self):
        self.assertEqual(cycle("The application deadline will be November 5, 2026."), "open")


class TestFunding(unittest.TestCase):
    def test_a_question_about_support_is_not_a_benefit(self):
        self.assertNotEqual(fclass("How long do scholarship holders receive financial support?"), "stipend_only")

    def test_a_budget_instruction_is_not_a_benefit(self):
        self.assertNotEqual(fclass("Below the budget justification, include a table showing the source and amount of any "
                                   "Rice-internal funding you will be receiving (including graduate stipends)."),
                            "stipend_only")

    def test_a_stated_stipend_still_counts(self):
        self.assertEqual(fclass("Fellows receive a monthly stipend of EUR 1,200 for living costs."), "stipend_only")


if __name__ == "__main__":
    unittest.main()
