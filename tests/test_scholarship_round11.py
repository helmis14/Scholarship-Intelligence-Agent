"""Round 11: funder identity and study-level evidence. Inline texts; no model or network calls."""

import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.ai_extract import validate  # noqa: E402
from scholarship_agent.evidence import organisation_role, study_levels_supported, substantiates  # noqa: E402
from scholarship_agent.extract import Page, extract_opportunity  # noqa: E402
from scholarship_agent.models import SourceType  # noqa: E402

TODAY = date(2026, 10, 17)


def ok(field, value, quote, page=None):
    return validate(field, value, quote, page or quote)


class TestFunderIdentity(unittest.TestCase):
    def test_original_failure_own_funds(self):
        q = "You do not need to provide evidence of own funds to the OeAD agency."
        self.assertEqual(organisation_role("OeAD", q)[0], "own_funds")
        self.assertEqual(ok("provider_name", "OeAD", q), "the quote is about the applicant's own funds, not a funder")

    def test_roles(self):
        cases = {
            ("Austrian Federal Ministry of Women, Science and Research",
             "The grant programme is financed by the Austrian Federal Ministry of Women, Science and Research (BMFWF)."): "funder",
            ("OeAD-GmbH", "Funding organisation: OeAD-GmbH on behalf and financed by the Austrian Federal Ministry"): "funder",
            ("VLIRUOS", "Master of Epidemiology, an ICP Connect Scholarship by VLIRUOS"): "funder",
            ("Heinrich Böll Foundation", "The Heinrich Böll Foundation grants scholarships to approximately 1,000 students"): "provider",
            ("New Zealand Government", "The New Zealand Government offers Vocational Short Term Training Scholarships"): "provider",
            ("UGent", "Organised by UGent"): "host",
            ("Global Health Institute", "Through a VLIRUOS grant programme, this Master's programme is supported by the "
                                        "Global Health Institute."): "host",
            ("Ghent University", "is organised by the Laboratory for Aquaculture & Artemia Reference Centre of Ghent University"): "host",
            ("University of Twente", "You will study at the University of Twente for two years."): "host",
            ("Aarhus University", "Aarhus University will apply for funding from the EU every academic year."): "mentioned",
            ("OeAD", "Please contact the OeAD if you have questions about the grant."): "mentioned",
            ("DAAD", "The DAAD website lists many scholarships."): "mentioned",
            ("LPDP", "Beasiswa ini dibiayai oleh LPDP untuk putra-putri terbaik bangsa."): "funder",
            ("Fundación Carolina", "Becas otorgadas por la Fundación Carolina para estudiantes"): "funder",
            ("DAAD", "Das Stipendium wird vom DAAD gefördert."): "funder",
            ("Gates Foundation", "The scholarship is funded by the Mastercard Foundation."): "absent",
        }
        for (name, quote), want in cases.items():
            with self.subTest(name=name, quote=quote[:40]):
                self.assertEqual(organisation_role(name, quote)[0], want)

    def test_validator_accepts_only_funders_and_providers(self):
        self.assertIsNone(ok("provider_name", "VLIRUOS", "an ICP Connect Scholarship by VLIRUOS"))
        self.assertIsNotNone(ok("provider_name", "Aarhus University", "Aarhus University will apply for funding from the EU."))
        self.assertIn("hosts", ok("provider_name", "UGent", "Organised by UGent"))

    def test_rules_evidence_for_a_provider_carries_a_warning(self):
        self.assertIsNotNone(substantiates("provider", "OeAD", "You do not need to show proof of own funds to the OeAD."))
        self.assertIsNone(substantiates("provider", "VLIRUOS", "an ICP Connect Scholarship by VLIRUOS"))


class TestStudyLevels(unittest.TestCase):
    def test_each_level_must_be_stated_as_offered(self):
        self.assertEqual(study_levels_supported(["master", "phd"], "The MA and PhD scholarships support two and three "
                                                                  "years of graduate study."), [])
        self.assertEqual(study_levels_supported(["bachelor", "master"], "Target group: undergraduates and graduates"), [])
        self.assertIn("bachelor not stated in the quotation",
                      study_levels_supported(["bachelor", "master"], "The Master in Aquaculture is a two-year programme"))

    def test_prerequisites_and_exclusions_are_not_levels(self):
        self.assertTrue(study_levels_supported(["phd"], "Visiting scholars holding a doctoral degree may carry out research."))
        self.assertTrue(study_levels_supported(["master"], "applicants who have already completed a master's degree of two "
                                                          "years or more are not eligible"))
        q = "Please note, these scholarships are for Master’s courses only and not for undergraduate or PhD study."
        self.assertEqual(study_levels_supported(["master"], q), [])
        self.assertTrue(study_levels_supported(["phd"], q))
        self.assertTrue(study_levels_supported(["bachelor"], q))

    def test_validator(self):
        self.assertIsNotNone(ok("study_levels", ["bachelor", "master", "phd", "postdoc"],
                                "The Ernst Mach Grant worldwide is targeted at young researchers from all disciplines."))
        self.assertIsNone(ok("study_levels", ["postdoc"], "The Follow-Up Grant is aimed at postdocs from developing countries."))
        self.assertEqual(ok("study_levels", ["astronaut"], "astronaut training"), "bad study levels")

    def test_rules_keep_one_evidence_per_level_and_drop_unsupported_ones(self):
        page = Page("https://x.example/s", "<html><head><title>Example Scholarship</title></head><body>"
                    "<p>The scholarship is for master's students.</p>"
                    "<p>Applicants must hold a bachelor's degree.</p></body></html>")
        o, _ = extract_opportunity(page, provider_name="p", provider_type="other", source_type=SourceType.OFFICIAL,
                                   country_hint=[], retrieved_at="t", today=TODAY)
        self.assertEqual(o.study_levels, ["master"])
        ev = [e for e in o.evidence if e.field == "study_levels"]
        self.assertEqual([e.value for e in ev], [["master"]])
        self.assertEqual(ev[0].warnings, [])


class TestOtherSafeguardsUnchanged(unittest.TestCase):
    def test_deadline_nationality_age_components_and_quotes(self):
        nsp = ("Closing dates for student application is 31-10-2026 and closing date for institute verification is "
               "15-11-2026.")
        self.assertIsNone(ok("deadline_scholarship", "2026-10-31", nsp))
        self.assertIsNotNone(ok("deadline_scholarship", "2026-11-15", nsp))
        self.assertEqual(ok("eligible_nationalities", ["Nigeria"], "citizens of Ghana or Kenya"), "country not named in quote")
        self.assertIn("differ by study level", ok("max_age", 45, "Maximum Age: Undergraduates: 35 years; Postdocs: 45 years"))
        self.assertIn("living allowance", ok("covers_accommodation", True, "€1,400 per month, which you can use for housing"))
        self.assertEqual(validate("max_age", 35, "Applicants must be under 35.", "A different page."), "quote not found on page")


if __name__ == "__main__":
    unittest.main()
