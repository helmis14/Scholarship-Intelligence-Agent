"""Round 16: nationality basis (citizenship / origin / residence / unknown) and funder roles (funder, provider,
host, administrator, partner), each from the sentence that states it. Offline."""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent.ai_extract import judge  # noqa: E402
from scholarship_agent.extract import Page, extract_nationality, extract_opportunity  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402
from scholarship_agent.parties import extract_parties, payer  # noqa: E402


def opp_of(html):
    o, _ = extract_opportunity(Page("https://x.example/s", html), provider_name="x", provider_type=ProviderType.OTHER,
                               source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=date(2026, 10, 18))
    return o


class TestNationality(unittest.TestCase):
    def test_one_country_per_line_lists(self):
        t = ("Citizens of the following countries are eligible\nAustria\nCanada\nThe Czech Republic\n*The United States\n"
             "How to apply")
        rule, _ = extract_nationality(t)
        self.assertEqual((rule.mode, rule.countries, rule.basis), ("include", ["AT", "CA", "CZ", "US"], "citizenship"))

    def test_basis_origin_unstated_and_residence(self):
        self.assertEqual(extract_nationality("Applicants from Kenya and Ghana may apply.")[0].basis, "origin")
        r = extract_nationality("The programme is open to the following countries\nPeru\nChile\nNext section")[0]
        self.assertEqual((r.mode, r.basis), ("include", "unstated"))
        r = extract_nationality("Applicants must be permanently resident in Peru or Chile.")[0]
        self.assertEqual((r.mode, r.residency_required), ("unknown", ["CL", "PE"]))   # residence is not nationality

    def test_nothing_stated_stays_unknown(self):
        self.assertEqual(extract_nationality("The scholarship covers tuition and a monthly stipend.")[0].mode, "unknown")

    def test_model_any_needs_explicit_wording(self):
        q = "The fellowship is available to all foreign nationals and all fields of study."
        self.assertEqual(judge("nationality_mode", "any", q, q)[0], "needs_review")
        q = "Students from all over the world, irrespective of nationality, can apply."
        self.assertEqual(judge("nationality_mode", "any", q, q)[0], "accepted")


class TestParties(unittest.TestCase):
    def test_roles_from_their_sentences(self):
        t = ("The scholarship is funded by the Dutch Ministry of Education, Culture and Science. "
             "It is administered by the National Agency for Education. "
             "The programme runs in collaboration with the Pacific Islands Forum. You will study at the University of Twente.")
        roles = {(p["role"], p["name"]) for p in extract_parties(t)}
        self.assertIn(("funder", "Dutch Ministry of Education, Culture and Science"), roles)
        self.assertIn(("administrator", "National Agency for Education"), roles)
        self.assertIn(("partner", "Pacific Islands Forum"), roles)
        self.assertIn(("host", "University of Twente"), roles)
        self.assertEqual(payer(extract_parties(t))["name"], "Dutch Ministry of Education, Culture and Science")

    def test_programme_names_hosts_and_unrelated_services_are_not_funders(self):
        o = opp_of("<h1>Khalifa University Scholarship</h1><p>Students study at Khalifa University.</p>"
                   "<p>Health care for scholarship holders is provided by the Ministry of Health.</p>")
        self.assertEqual(o.institution, "")                 # the title alone does not say who pays
        self.assertFalse([p for p in o.funding_parties if p["role"] in ("funder", "provider")])

    def test_provider_with_acronyms_inside_the_name(self):
        t = "the Ministry of Education (MOE) of the Republic of China (Taiwan) offers two kinds of scholarships."
        self.assertEqual(extract_parties(t)[0]["name"], "Ministry of Education (MOE) of the Republic of China (Taiwan)")

    def test_institution_carries_its_evidence(self):
        o = opp_of("<p>The Heinrich Böll Foundation awards scholarships to graduate students.</p>")
        self.assertEqual(o.institution, "Heinrich Böll Foundation")
        ev = [e for e in o.evidence if e.field == "provider"]
        self.assertTrue(ev and "awards scholarships" in ev[0].snippet)


if __name__ == "__main__":
    unittest.main()
