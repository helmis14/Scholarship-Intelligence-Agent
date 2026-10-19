"""Round 32: the writing standard carried in every brief, laid out by the skeleton and checked by the reviewer."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent import documents as D, review as R  # noqa: E402
from scholarship_agent.extract import extract_funding  # noqa: E402
from scholarship_agent.funding import classify  # noqa: E402
from scholarship_agent.models import Education, Opportunity, Profile, RequiredDocument  # noqa: E402

P = Profile(id="t", name="Ayu Lestari", citizenships=["ID"], residence_country="ID", target_levels=["master"],
            disciplines=["public health"], research_interests=["maternal health"],
            education=[Education(degree="bachelor", field="Public Health", institution="Universitas Gadjah Mada", country="ID",
                                 start="2019-08", end="2023-07", gpa=3.62, gpa_scale=4.0)])
O = Opportunity(id="o", title="Health Scholarship", provider_name="Example University", info_url="https://x.org/h",
                study_levels=["master"], selection_criteria=["leadership"],
                required_documents=[RequiredDocument(name="Statement of purpose", word_limit=800,
                                                     prompt="Describe your research interests and goals.")])


class TestStandard(unittest.TestCase):
    def test_every_voice_kind_has_a_structure_and_the_brief_carries_it(self):
        for kind in D.VOICE_KINDS:
            self.assertTrue(D.standard(kind)["structure"], kind)
        b = D.brief("sop", O, P)
        self.assertIn("Fit:", " ".join(b["standard"]["structure"]))
        self.assertTrue(any("quotation" in d for d in b["standard"]["do"]))
        self.assertTrue(D.standard("academic_cv")["structure"])

    def test_skeleton_lays_the_structure_out_as_slots(self):
        sk = D.skeleton("sop", D.brief("sop", O, P))
        for part in D.standard("sop")["structure"]:
            self.assertIn(part, sk)
        self.assertNotIn("3.9", sk)

    def test_reviewer_flags_filler_and_a_quotation_opener(self):
        b = D.brief("sop", O, P)
        text = ('"Be the change you wish to see." Ever since I was a child I have been passionate about maternal health. '
                "I studied Public Health at Universitas Gadjah Mada. My research interests are maternal health and my goals follow.")
        types = [i["type"] for i in R.review(text, b, P)["issues"]]
        self.assertIn("generic_phrase", types)
        self.assertIn("generic_opening", types)
        self.assertNotIn("generic_phrase", [i["type"] for i in R.review(
            "At Universitas Gadjah Mada I studied Public Health; my research interests are maternal health, and my goals follow.",
            b, P)["issues"]])

    def test_one_block_of_prose_is_a_structure_warning_only_for_voice_documents(self):
        b = D.brief("sop", O, P)
        one_block = ("I studied Public Health at Universitas Gadjah Mada and my research interests are maternal health. " * 20)
        self.assertIn("structure", [i["type"] for i in R.review(one_block, b, P)["issues"]])
        cv = D.academic_cv(P, O)
        self.assertNotIn("structure", [i["type"] for i in R.review(cv, D.brief("scholarship_cv", O, P), P)["issues"]])


def fclass(text):
    return classify(Opportunity(id="x", title="X", provider_name="P", info_url="https://x.org", funding=extract_funding(text)[0]))[
        "classification"]


class TestFundingClassRound32(unittest.TestCase):
    """Set P showed the funding class as the weak decision; each case is a kept devpool change."""

    def test_meals_are_not_a_partial_tuition_cap(self):
        t = ("The Presidential Scholarship is a renewable, merit-based award covering undergraduate tuition (fall and spring "
             "semesters), on-campus housing, a meal plan that includes up to 21 meals per week, and fees.")
        self.assertNotEqual(fclass(t), "partially_funded")

    def test_full_or_partial_written_with_a_slash_is_mixed(self):
        self.assertEqual(fclass("Award: Full tuition fees / Partial tuition fees"), "partially_funded")

    def test_a_scholarship_page_that_mentions_assistantships_is_not_an_assistantship(self):
        t = ("The International Competitive Scholarship offers a discount to pay in-state tuition instead of out-of-state "
             "tuition. Graduate assistantships are working positions in one's field of study.")
        self.assertEqual(fclass(t), "partially_funded")
        self.assertEqual(fclass("Graduate assistantships are offered to admitted doctoral students."), "assistantship")

    def test_a_stated_partial_extent_beats_a_bare_waiver(self):
        self.assertEqual(fclass("ICSP recipients receive a scholarship covering approximately half their tuition. Selected "
                                "students are granted a partial tuition-waiver scholarship."), "partially_funded")

    def test_a_minimum_award_amount_per_year_is_not_a_stipend(self):
        self.assertNotEqual(fclass("The minimum award amount is $2,500 per year."), "stipend_only")

    def test_model_stipend_quote_without_living_words_goes_to_review(self):
        from scholarship_agent.ai_extract import validate
        q = "First-Year Regents Scholars receive a $20,000 scholarship paid at $5,000 per year."
        self.assertIsNotNone(validate("stipend_amount", 5000, q, q))


if __name__ == "__main__":
    unittest.main()
