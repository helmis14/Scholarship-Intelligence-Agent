"""Round 27: fewer wrong claims on nationality, funding, cycle and evidence. Offline; sentences modelled on the
development pages (set K), never on the frozen test set L."""

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent import countries  # noqa: E402
from scholarship_agent.audit import cycle_status, decision_evidence, funding_type  # noqa: E402
from scholarship_agent.extract import extract_deadlines, extract_funding, extract_nationality, programme_text  # noqa: E402
from scholarship_agent.models import Evidence, NationalityRule, Opportunity  # noqa: E402

TODAY = date(2026, 10, 18)
URL = "https://www.example.ac.uk/scholarships/x"


def nat(text):
    return extract_nationality(text)[0]


class TestNationality(unittest.TestCase):
    def test_invitation_is_not_open_to_all(self):
        self.assertEqual(nat("We encourage applications from talented students around the world.").mode, "unknown")
        self.assertEqual(nat("The ministry awards scholarships to outstanding students from around the world.").mode,
                         "unknown")

    def test_explicit_open_to_all(self):
        self.assertEqual(nat("There are no restrictions on nationality.").mode, "any")
        self.assertEqual(nat("Researchers of any nationality can apply.").mode, "any")

    def test_international_students_is_a_scope_not_a_nationality_rule(self):
        r = nat("The scholarship is offered to high-achieving international students.")
        self.assertEqual((r.mode, r.applicant_scope), ("unknown", "international"))

    def test_outside_the_eu_eea_and_switzerland_expands(self):
        r = nat("You must be a citizen of a country from outside the EU/EEA (and Switzerland) and be required to pay "
                "tuition fees.")
        self.assertEqual(r.mode, "exclude")
        self.assertEqual(set(r.countries), set(countries.EEA) | {"CH"})
        r = nat("Students who hold a non-EU/EEA passport are eligible.")
        self.assertEqual(set(r.countries), set(countries.EEA))
        self.assertEqual(nat("Candidates can be from any country outside the UK but must fulfil the criteria.").countries,
                         ["GB"])

    def test_a_region_minus_one_country_is_not_an_exclusion_list(self):
        self.assertNotEqual(nat("I am a citizen of an African country outside of South Africa.").mode, "exclude")

    def test_quota_is_not_a_restriction(self):
        r = nat("Candidates can be from any country outside the UK. There are up to 85 scholarships with five "
                "ring-fenced for students from India.")
        self.assertEqual((r.mode, r.countries), ("exclude", ["GB"]))

    def test_menu_item_and_other_track_dates_are_not_eligibility(self):
        r = nat("Japanese Nationals\nDates of the 2027 application window for Japanese nationals have been announced.")
        self.assertEqual(r.mode, "unknown")

    def test_exclusion_by_demonym_and_from(self):
        self.assertEqual(nat("Russian and Belarusian nationals are not eligible to apply.").countries, ["BY", "RU"])
        self.assertEqual(nat("Students from China are not eligible to apply.").countries, ["CN"])

    def test_residency_list_under_the_sentence(self):
        r = nat("To be eligible, you must be living in one of the countries listed below.\nCheck your country profile.\n"
                "Bangladesh\nGhana\nIndonesia\nThe Next Heading Here")
        self.assertEqual(r.residency_required, ["BD", "GH", "ID"])

    def test_funder_country_is_not_the_applicants(self):
        r = nat("The Government of the Czech Republic offers scholarships to citizens of the following countries\n"
                "Ethiopia, Gabon, Mauritania, Zambia,\nBangladesh, Cambodia.")
        self.assertNotIn("CZ", r.countries)
        self.assertIn("ET", r.countries)

    def test_do_is_not_south_africa(self):
        self.assertEqual(countries.mentions("You do not have dual nationality."), [])

    def test_related_scholarships_section_is_cut(self):
        body = "\n".join(["Graduate Research Scholarships"] + ["Text about this award."] * 10 +
                         ["Related scholarships", "China Scholarship Council PhD Scholarship",
                          "Offered to citizens of the People's Republic of China."])
        self.assertNotIn("China", programme_text(body))


class TestFunding(unittest.TestCase):
    def kind(self, text):
        comps, _ = extract_funding(text)
        return funding_type(Opportunity(id="x", title="X", provider_name="P", info_url=URL, funding=comps))["state"], comps

    def test_condition_is_not_a_benefit(self):
        state, comps = self.kind("You must be a citizen of a country outside the EU and be required to pay tuition fees.")
        self.assertEqual(state, "not_stated")

    def test_full_tuition_wordings(self):
        for s in ("Full fee offset for up to four years.", "Full funding for tuition fees.",
                  "The scholarship covers University of Oxford course fees.",
                  "These scholarships cover the full cost of tuition, but not living expenses."):
            comps, _ = extract_funding(s)
            t = next(c for c in comps if c.kind == "tuition")
            self.assertTrue(t.covered and t.full, s)
        state, comps = self.kind("These scholarships cover the full cost of tuition, but not living expenses.")
        self.assertEqual(state, "tuition_funded")

    def test_unstated_extent_is_not_partial(self):
        state, _ = self.kind("A scholarship provides tuition and a monthly living stipend.")
        self.assertEqual(state, "funding_unclear")
        state, _ = self.kind("A £16,000 tuition fee discount and a monthly stipend of £500.")
        self.assertEqual(state, "partially_funded")

    def test_recurring_cash_grant_is_a_stipend(self):
        state, comps = self.kind("These fellowships, worth CHF 10'000 per semester, are awarded on merit.")
        self.assertEqual(state, "stipend_only")
        s = next(c for c in comps if c.kind == "stipend")
        self.assertEqual((s.amount, s.currency, s.period), (10000.0, "CHF", "semester"))

    def test_assistantship_needs_the_word(self):
        _, comps = self.kind("Our research assistants support the lab. A stipend of €1,000 per month is paid.")
        self.assertNotIn("assistantship", [c.kind for c in comps])


class TestCycle(unittest.TestCase):
    def status(self, text):
        o = Opportunity(id="x", title="X", provider_name="P", info_url=URL, deadlines=extract_deadlines(text, URL, TODAY))
        return cycle_status(o, TODAY)["state"]

    def test_closed_without_a_date(self):
        self.assertEqual(self.status("Applications for the Rhodes Scholarship are now closed."), "closed")
        self.assertEqual(self.status("The call for the academic year 2026-2027 is now closed."), "closed")
        self.assertEqual(self.status("STATUS\nClosed"), "closed")
        self.assertEqual(self.status("If the opportunity is closed the Apply link will not be visible."), "not_stated")

    def test_currently_unavailable_is_not_announced(self):
        self.assertEqual(self.status("The scholarship is currently unavailable. Application period is open all year round."),
                         "not_announced")

    def test_rolling_assessment_is_not_a_rolling_cycle(self):
        self.assertNotEqual(self.status("Applications will be assessed and awarded on a rolling basis."), "rolling")

    def test_month_window_opening(self):
        self.assertEqual(self.status("Application Period: Apr 2027 - Sep 2027"), "upcoming")

    def test_other_step_dates_are_not_deadlines(self):
        ds = extract_deadlines("Next application deadline is 28 February 2027 (for Masters starting September 14, 2027).",
                               URL, TODAY)
        self.assertEqual([d.date for d in ds if d.kind == "scholarship"], ["2027-02-28"])


class TestDecisionEvidence(unittest.TestCase):
    def test_quotation_naming_another_programme_needs_review(self):
        o = Opportunity(id="x", title="Graduate Research Scholarships", provider_name="University of Melbourne",
                        info_url=URL, nationality=NationalityRule(mode="include", countries=["CN"]),
                        evidence=[Evidence(field="nationality", value={}, source_url=URL,
                                           snippet="The China Scholarship Council PhD Scholarship is offered to citizens "
                                                   "of the People's Republic of China.")])
        d = decision_evidence(o, TODAY)["eligibility"]
        self.assertEqual(d["state"], "needs_review")
        self.assertIn("another programme", d["problems"][0])

    def test_quotation_from_another_page_needs_review(self):
        o = Opportunity(id="x", title="X Scholarship", provider_name="P", info_url=URL,
                        nationality=NationalityRule(mode="any"),
                        evidence=[Evidence(field="nationality", value={}, source_url="https://www.example.ac.uk/funding",
                                           snippet="There are no restrictions on nationality.")])
        self.assertEqual(decision_evidence(o, TODAY)["eligibility"]["state"], "needs_review")


if __name__ == "__main__":
    unittest.main()
