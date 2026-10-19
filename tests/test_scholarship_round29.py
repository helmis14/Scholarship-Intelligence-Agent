"""Round 29 regression examples: nationality negation (stage 2) and which programme a date belongs to.
Sentences are modelled on the development sets (K, L, M). Passing them is not evidence that the rules generalise; the
frozen set N measures that. Run on every rule change: python3 -m unittest tests.test_scholarship_round29"""

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.extract import extract_deadlines, extract_nationality  # noqa: E402
from scholarship_agent.models import DeadlineKind  # noqa: E402

TODAY = date(2026, 10, 19)
URL = "https://www.example.org/scholarship"
APPLY = (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)


def nat(text):
    r = extract_nationality(text)[0]
    return r.mode, sorted(r.countries)


def applicant(text, title="Churchill Scholarship"):
    return sorted({d.date for d in extract_deadlines(text, URL, TODAY, title=title) if d.date and d.kind in APPLY})


class TestNegationStage2(unittest.TestCase):
    # excluded by negation
    def test_not_a_citizen_without_a_verb(self):
        self.assertEqual(nat("Be an offshore international student (ie not an Australian citizen, New Zealand citizen or "
                             "permanent resident)."), ("exclude", ["AU", "NZ"]))

    def test_who_are_not_citizens_as_a_requirement(self):
        self.assertEqual(nat("International students who are required to pay international tuition fees and who are not "
                             "Canadian citizens or Permanent Residents of Canada."), ("exclude", ["CA"]))

    def test_non_us_citizens_variants(self):
        for s in ("Fellowship recipients must be non-U.S. citizens.", "Open to non-US citizens only.",
                  "Applicants must be non-United States citizens."):
            self.assertEqual(nat(s), ("exclude", ["US"]), s)

    def test_must_not_hold_citizenship(self):
        self.assertEqual(nat("Applicants must not hold Swiss citizenship."), ("exclude", ["CH"]))

    # eligible: the same words without negation must not flip
    def test_us_citizens_is_the_united_states(self):
        self.assertEqual(nat("Eligible applicants are US Citizens or permanent residents."), ("include", ["US"]))
        self.assertEqual(nat("Applicants must be U.S. citizens."), ("include", ["US"]))

    def test_us_pronoun_is_not_a_country(self):
        self.assertEqual(nat("Tell us about your goals; citizens of Kenya are eligible."), ("include", ["KE"]))

    def test_double_negation_is_not_an_exclusion(self):
        self.assertEqual(nat("Applicants who are not Kenyan citizens are not eligible."), ("include", ["KE"]))

    def test_not_only_is_not_negation(self):
        self.assertEqual(nat("The award is open not only to citizens of Ghana but also to citizens of Togo."),
                         ("include", ["GH", "TG"]))

    def test_condition_on_where_to_hold_stays_neutral(self):
        self.assertEqual(nat("Applicants who are not Canadian citizens may only hold their fellowship at a Canadian "
                             "institution."), ("unknown", []))

    def test_eligible_and_excluded_together(self):
        self.assertEqual(nat("Citizens of Kenya and Uganda are eligible; citizens of Tanzania are not eligible."),
                         ("include", ["KE", "UG"]))

    def test_all_nationalities_except_by_negation(self):
        self.assertEqual(nat("Open to all nationalities. Applicants must not be citizens of Japan."), ("exclude", ["JP"]))

    def test_conditional_branch_and_relatives_are_not_exclusions(self):
        self.assertEqual(nat("If you were born abroad as a non-US citizen then one of the following must be true."),
                         ("unknown", []))
        self.assertEqual(nat("Your birth parents must have both been born outside of the US as non-US citizens."),
                         ("unknown", []))
        self.assertEqual(nat("We require a non-binding moral commitment to the United States in times of national "
                             "emergency."), ("unknown", []))

    def test_national_university_is_not_a_nationality(self):
        self.assertEqual(nat("ANU Chancellor's International Scholarship | The Australian National University"),
                         ("unknown", []))

    def test_unknown_stays_unknown(self):
        self.assertEqual(nat("Applicants must be citizens of an eligible country."), ("unknown", []))


class TestDeadlineOwnership(unittest.TestCase):
    def test_other_programme_deadline_is_not_inherited(self):
        t = ("The deadline for the Churchill Scholarship is Monday, November 2, 2026, at 5pm Eastern Time.\n"
             "Because of Cambridge's rolling admissions, we strongly suggest that you apply by the deadline for the "
             "Gates Cambridge Scholarship, which is Wednesday, October 14, 2026.")
        self.assertEqual(applicant(t), ["2026-11-02"])

    def test_coincides_with_another_programme(self):
        t = ("Churchill Scholarship application deadline: November 2, 2026.\n"
             "The next deadline coincides with the Gates Cambridge deadline, Wednesday, October 14, 2026.")
        self.assertEqual(applicant(t), ["2026-11-02"])

    def test_partner_institution_window_is_not_the_programme_deadline(self):
        t = ("Globalink Research Internship applications close September 24, 2026.\n"
             "Application period at Tec: August 3 – September 3, 2027. Successful ITESM applicants will contribute $2,500.")
        self.assertEqual(applicant(t, title="Globalink Research Internship"), ["2026-09-24"])

    def test_track_of_the_same_call_keeps_its_deadline(self):
        t = "Ernst Mach Grant ASEA-UNINET call 2027/28.\nClosing Date (Music Practice Grant): 15 December 2026"
        self.assertEqual(applicant(t, title="Ernst Mach Grant - ASEA-UNINET: Scholarship Call 2027/28"), ["2026-12-15"])

    def test_own_programme_named_in_the_sentence_keeps_its_deadline(self):
        t = "The Churchill Scholarship deadline is Monday, November 2, 2026."
        self.assertEqual(applicant(t), ["2026-11-02"])

    def test_page_without_a_title_keeps_its_deadline(self):
        self.assertEqual(applicant("Application deadline: 15 January 2027.", title=""), ["2027-01-15"])

    def test_sibling_track_deadline_on_the_same_page(self):
        t = ("Vingroup Science and Technology Scholarship: applications close 30 November 2026.\n"
             "Vingroup Young Talent Scholarship at SMU: applications close 15 January 2027.")
        self.assertEqual(applicant(t, title="Vingroup Science and Technology Scholarship Programs"), ["2026-11-30"])


if __name__ == "__main__":
    unittest.main()


class TestReviewChecks(unittest.TestCase):
    """Round 29: review checks that held right answers; the quotation checks themselves stay."""

    def _opp(self, quote, page_type="scholarship_program", words=("churchill",)):
        from scholarship_agent.models import Evidence, NationalityRule, Opportunity
        return Opportunity(id="x", title="The Scholarship", provider_name="P", info_url=URL, page_type=page_type,
                           own_programme_words=list(words), nationality=NationalityRule(mode="include", countries=["US"]),
                           evidence=[Evidence(field="nationality", value={}, source_url=URL, snippet=quote)])

    def test_own_award_named_in_the_quotation_is_not_another_programme(self):
        from scholarship_agent.audit import decision_evidence
        o = self._opp("An applicant for the Churchill Scholarship must be a citizen of the United States.")
        self.assertEqual(decision_evidence(o, TODAY)["eligibility"]["state"], "supported")

    def test_other_award_in_the_quotation_still_needs_review(self):
        from scholarship_agent.audit import decision_evidence
        o = self._opp("An applicant for the Gates Cambridge Scholarship must be a citizen of the United States.")
        self.assertEqual(decision_evidence(o, TODAY)["eligibility"]["state"], "needs_review")

    def test_irrelevant_label_does_not_block_a_page_that_names_its_award(self):
        from scholarship_agent.audit import decision_evidence
        o = self._opp("Applicants must be citizens of the United States.", page_type="irrelevant")
        self.assertEqual(decision_evidence(o, TODAY)["eligibility"]["state"], "supported")
        o = self._opp("Applicants must be citizens of the United States.", page_type="scholarship_catalog")
        self.assertEqual(decision_evidence(o, TODAY)["eligibility"]["state"], "needs_review")
        o = self._opp("Applicants must be citizens of the United States.", page_type="irrelevant", words=())
        self.assertEqual(decision_evidence(o, TODAY)["eligibility"]["state"], "needs_review")
