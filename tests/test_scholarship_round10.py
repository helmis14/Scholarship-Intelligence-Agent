"""Round 10: validator and extraction fixes from set C, one test per failure mode. Inline page texts (adapted from
the set C pages), so nothing depends on the gitignored snapshots. No model or network calls."""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.ai_extract import enrich, validate  # noqa: E402
from scholarship_agent.claims_eval import evaluate_claims  # noqa: E402
from scholarship_agent.eligibility import evaluate as eligibility  # noqa: E402
from scholarship_agent.extract import Page, extract_age, extract_funding, extract_opportunity  # noqa: E402
from scholarship_agent.models import Opportunity, Profile, SourceType  # noqa: E402

TODAY = date(2026, 10, 17)
VLIR_AGE = ("Age: Candidates for a bachelor or initial master programme cannot be older than 35 as of 1 January of the "
            "intake year, while candidates for an advanced master cannot be older than 45. Additionally, candidates for a "
            "bachelor programme must be at least 19 years old by 1 January of the intake year.")
ASEA_AGE = "Maximum Age: Undergraduates, Graduates, and Postgraduates: 35 years; Postdocs: 45 years"


def ok(field, value, quote, page=None):
    return validate(field, value, quote, page or quote)


class TestTwoDigitYears(unittest.TestCase):
    PAGE = "Applications open: 15/10/26 | Application deadline: 01/02/27 | Programme duration: Sept 2027 - Sept 2029"

    def test_page_settles_day_month_order(self):
        self.assertIsNone(ok("deadline_scholarship", "2027-02-01", self.PAGE))
        self.assertIsNone(ok("opening_date", "2026-10-15", self.PAGE))

    def test_ambiguous_order_stays_unread(self):
        page = "Applications open: 12/10/26 | Application deadline: 01/02/27"
        self.assertEqual(ok("deadline_scholarship", "2027-02-01", page), "date not stated in quote")


class TestDurations(unittest.TestCase):
    def test_written_numbers(self):
        self.assertIsNone(ok("funding_duration_months", 36, "The MA and PhD scholarships support two and three years of "
                                                            "graduate study respectively at a US university."))
        self.assertIsNone(ok("funding_duration_months", 24, "all JJ/WBGSP scholarships cover the duration of the graduate "
                                                            "program or two years, whichever is less."))
        self.assertIsNone(ok("funding_duration_months", 12, "The student can benefit from this scholarship for 1 academic year."))

    def test_programme_length_is_not_a_funding_period(self):
        self.assertEqual(ok("funding_duration_months", 24, "The Master of Epidemiology is a two-year programme (120 ECTS)"),
                         "quote describes the study programme's length, not a funding period")


class TestFunders(unittest.TestCase):
    def test_by_statements(self):
        self.assertIsNone(ok("provider_name", "VLIRUOS", "Master of Epidemiology, an ICP Connect Scholarship by VLIRUOS"))
        self.assertIsNone(ok("provider_name", "Dutch Ministry of Education, Culture and Science",
                             "The NL Scholarship is financed by the Dutch Ministry of Education, Culture and Science together "
                             "with Dutch research universities."))

    def test_organisers_and_decision_makers_are_not_funders(self):
        self.assertIn("organises", ok("provider_name", "UGent", "Organised by UGent"))
        self.assertIsNotNone(ok("provider_name", "Austrian Federal Ministry of Women, Science and Research",
                                "Final decisions are made by the Austrian Federal Ministry of Women, Science and Research (BMFWF)."))


class TestAgeByLevel(unittest.TestCase):
    def test_rules_keep_limits_per_level(self):
        got = extract_age(VLIR_AGE)
        self.assertNotIn("max_age", got)
        self.assertNotIn("min_age", got)   # 'cannot be older than 35' used to be read as a minimum of 35
        self.assertEqual(got["age_limits"], [{"level": "bachelor", "max": 35, "min": 19}, {"level": "master", "max": 35},
                                             {"level": "advanced_master", "max": 45}])
        self.assertEqual([d["max"] for d in extract_age(ASEA_AGE)["age_limits"]], [35, 35, 35, 45])

    def test_single_level_statements_are_unchanged(self):
        self.assertEqual(extract_age("The maximum age is 35 years.")["max_age"], 35)
        self.assertEqual(extract_age("Applicants cannot be older than 35 years.")["max_age"], 35)

    def test_validator_refuses_a_collapsed_number(self):
        self.assertIn("differ by study level", ok("max_age", 45, ASEA_AGE))
        self.assertIsNone(ok("age_limits_by_level", ["bachelor<=35", "master<=35", "phd<=35", "postdoc<=45"], ASEA_AGE))
        self.assertIsNotNone(ok("age_limits_by_level", ["bachelor<=45"], ASEA_AGE))
        self.assertIsNone(ok("max_age", 35, "Applicants must not be older than 35 years when they start their research stay."))

    def test_model_answer_stored_per_level_and_never_collapsed(self):
        class LLM:
            name = "anthropic:test"

            def complete_json(self, s, u):
                return {"fields": [{"field": "max_age", "value": 45, "quote": ASEA_AGE},
                                   {"field": "age_limits_by_level", "value": ["bachelor<=35", "postdoc<=45"], "quote": ASEA_AGE}]}
        opp = Opportunity(id="x", title="X", provider_name="p", info_url="https://x.example/s")
        enrich(opp, ASEA_AGE, LLM(), source_type=SourceType.OFFICIAL, retrieved_at="t", today=TODAY)
        self.assertIsNone(opp.max_age)
        self.assertEqual(opp.age_limits, [{"level": "bachelor", "max": 35}, {"level": "postdoc", "max": 45}])

    def test_eligibility_uses_the_target_level(self):
        opp = Opportunity(id="x", title="X", provider_name="p")
        opp.age_limits = extract_age(VLIR_AGE)["age_limits"]
        age = lambda p: next(c for c in eligibility(opp, p, TODAY)["checks"] if c["name"] == "age")  # noqa: E731
        self.assertEqual(age(Profile(date_of_birth="1988-01-01", target_levels=["bachelor"]))["outcome"], "fail")
        self.assertEqual(age(Profile(date_of_birth="1998-01-01", target_levels=["bachelor"]))["outcome"], "pass")
        # 40-year-old master's applicant: fine for an advanced master (45), not an initial one (35): unknown
        self.assertEqual(age(Profile(date_of_birth="1986-01-01", target_levels=["master"]))["outcome"], "unknown")


class TestFundingComponents(unittest.TestCase):
    def test_allowance_spent_on_housing_is_not_accommodation(self):
        q = ("€1,400 per month for up to 24 months, which you can use for housing, food, travel, visas, and any other "
             "costs related to studying and living in Europe")
        self.assertIn("living allowance", ok("covers_accommodation", True, q))
        self.assertIn("living allowance", ok("covers_travel", True, q))
        self.assertIsNone(ok("covers_living_allowance", True, q))
        comps = {c.kind: c for c in extract_funding(q)[0]}
        self.assertEqual((comps["living_allowance"].amount, comps["living_allowance"].period), (1400.0, "month"))
        self.assertNotIn("accommodation", comps)
        self.assertNotIn("travel", comps)

    def test_board_and_lodging_is_part_of_living_expenses(self):
        q = "VLIRUOS ICP Connect scholarships cover tuition fees, travel, insurance and living expenses (board and lodging)."
        self.assertIsNotNone(ok("covers_accommodation", True, q))
        self.assertIsNone(ok("covers_travel", True, q))
        self.assertIsNone(ok("covers_health_insurance", True, q))

    def test_own_expenses_and_list_fragments(self):
        page = ("The scholarship may not cover all expenses for your research stay. You may already have various expenses:\n"
                "compulsory health insurance;\naccommodation;\ntravel costs to Austria;")
        self.assertIsNotNone(ok("covers_health_insurance", True, "compulsory health insurance;", page))
        self.assertIsNotNone(ok("covers_accommodation", True, "accommodation;", page))
        self.assertEqual({c.kind for c in extract_funding(page)[0] if c.covered}, set())

    def test_separate_accommodation_benefit(self):
        self.assertIsNone(ok("covers_accommodation", True, "Provides accommodation for students arriving in a new country."))
        comps = {c.kind: c for c in extract_funding("The program covers monthly stipend, accommodation and round trip "
                                                    "airfare tickets.")[0]}
        self.assertTrue(comps["accommodation"].covered)

    def test_benefit_list_under_a_heading(self):
        page = ("The scholarship will provide the following benefits\nRound-trip economy class air travel to the US\n"
                "Funding for tuition and fees, living and related costs")
        covered = {c.kind for c in extract_funding(page)[0] if c.covered}
        self.assertTrue({"travel", "tuition", "living_allowance"} <= covered)


class TestDeadlinesAndCycles(unittest.TestCase):
    def test_start_date_is_not_a_deadline_but_a_window_end_is(self):
        self.assertIsNotNone(ok("deadline_scholarship", "2027-09-01", "Project Start Date 01 September 2027"))
        self.assertIsNone(ok("deadline_scholarship", "2027-05-21", "Application Window #2 from March 29 to May 21, 2027"))

    def test_closed_cycle_is_not_current(self):
        self.assertIn("closed", ok("academic_cycle", "2026/2027",
                                   "The ICP Connect scholarship call for the 2026–2027 academic year is now closed."))
        self.assertIsNone(ok("academic_cycle", "2027/2028", "for the Austrian academic year 2027/28"))

    def test_rules_age_on_full_page(self):
        page = Page("https://www.vliruos.be/x", f"<html><head><title>Master X, an ICP Connect Scholarship by VLIRUOS</title>"
                                                f"</head><body><p>{VLIR_AGE}</p></body></html>")
        o, _ = extract_opportunity(page, provider_name="VLIRUOS", provider_type="other", source_type=SourceType.OFFICIAL,
                                   country_hint=[], retrieved_at="t", today=TODAY)
        self.assertEqual((o.max_age, o.min_age), (None, None))
        self.assertEqual(len(o.age_limits), 3)
        self.assertTrue(any(e.field == "age_limits" for e in o.evidence))


class TestClaimsEvaluator(unittest.TestCase):
    def test_counts_false_rejections_and_acceptances(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pages").mkdir()
            (root / "pages" / "p1.html").write_text("<html><body><p>The scholarship deadline is 1 March 2027.</p></body></html>")
            (root / "urls.json").write_text(json.dumps({"pages": [{"id": "p1", "url": "https://x.example/p1", "split": "test"}]}))
            (root / "labels.json").write_text(json.dumps({"pages": {"p1": {"kind": "opportunity", "fields": {}, "claims": [
                {"field": "deadline_scholarship", "value": "2027-03-01", "quote": "The scholarship deadline is 1 March 2027.",
                 "accept": True, "why": ""},
                {"field": "deadline_scholarship", "value": "2027-03-02", "quote": "The scholarship deadline is 1 March 2027.",
                 "accept": False, "why": ""}]}}}))
            r = evaluate_claims(root, "test")
        self.assertEqual((r["positives"], r["false_rejections"], r["negatives"], r["false_acceptances"]), (1, 0, 1, 0))
        self.assertEqual(evaluate_claims.__module__, "scholarship_agent.claims_eval")


@unittest.skipUnless((REPO / "tests" / "heldout_c" / "pages").exists(), "set C snapshots not downloaded")
class TestSetCIntegrity(unittest.TestCase):
    def test_every_labelled_quote_is_on_its_page(self):
        from scholarship_agent.heldout import load_page
        root = REPO / "tests" / "heldout_c"
        labels = json.loads((root / "labels.json").read_text())["pages"]
        urls = {p["id"]: p for p in json.loads((root / "urls.json").read_text())["pages"]}
        self.assertEqual({p["split"] for p in urls.values()}, {"dev", "test"})
        for pid, lab in labels.items():
            body = " ".join(load_page(pid, urls[pid]["url"], root).text.lower().split())
            for c in lab["claims"]:
                self.assertIn(" ".join(c["quote"].lower().split()), body, pid)


if __name__ == "__main__":
    unittest.main()
