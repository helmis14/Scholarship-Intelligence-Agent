"""Round 17: organisation names with sourced aliases (page-defined acronyms, org_aliases.json); no fuzzy matching."""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scholarship_agent.extract import Page, extract_opportunity  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402
from scholarship_agent.org_names import describe, fold, page_aliases, registry, same_org  # noqa: E402


class TestOrgNames(unittest.TestCase):
    def test_page_defined_acronyms_must_spell_the_initials(self):
        t = ("Established by the Research Grants Council (RGC) of Hong Kong. Aristotle University of Thessaloniki "
             "(Greece). Programa de Becas de la Organización de los Estados Americanos (OEA).")
        self.assertEqual(page_aliases(t), {"RGC": "Research Grants Council",
                                           "OEA": "Organización de los Estados Americanos"})

    def test_matching_is_exact_or_sourced(self):
        t = "The Japan Society for the Promotion of Science (JSPS) offers fellowships."
        self.assertTrue(same_org("JSPS", "Japan Society for the Promotion of Science", t))
        self.assertTrue(same_org("MEXT", "Ministry of Education, Culture, Sports, Science and Technology"))   # registry
        self.assertTrue(same_org("The Ministry of Education, Culture, Sports, Science and Technology (MEXT ) of Japan",
                                 "Ministry of Education, Culture, Sports, Science and Technology"))
        self.assertTrue(same_org("Thailand International Development Cooperation Agency", "TICA"))   # historical name
        self.assertFalse(same_org("Ministry of Education", "Ministry of Health"))
        self.assertFalse(same_org("Research Council of Norway", "Research Grants Council"))   # similar is not same
        self.assertFalse(same_org("JSPS", "Japan Society for the Promotion of Science"))     # no source without the page

    def test_every_registry_entry_has_a_source(self):
        self.assertTrue(registry())
        self.assertTrue(all(o["source"].startswith("https://") for o in registry()))

    def test_parties_keep_the_name_as_written_and_their_aliases(self):
        html = ("<p>The Hong Kong PhD Fellowship Scheme is funded by the Research Grants Council (RGC).</p>")
        o, _ = extract_opportunity(Page("https://x.example", html), provider_name="x", provider_type=ProviderType.OTHER,
                                   source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t",
                                   today=date(2026, 10, 18))
        p = o.funding_parties[0]
        self.assertEqual((p["role"], fold(p["name"])), ("funder", "research grants council"))
        self.assertEqual(p["aliases"]["page_aliases"], ["RGC"])
        self.assertEqual(p["aliases"]["registry"]["source"], "https://www.ugc.edu.hk/eng/rgc/")
        self.assertEqual(describe("Unknown Body")["registry"], None)


if __name__ == "__main__":
    unittest.main()
