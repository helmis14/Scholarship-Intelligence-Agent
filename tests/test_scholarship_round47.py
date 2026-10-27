"""Round 47: English first (translations kept beside the originals), the site's search and detail sections, and the
site's string files."""
import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scholarship_agent import site
from scholarship_agent.extract import Page, extract_opportunity
from scholarship_agent.models import ProviderType, SourceType
from scholarship_agent.store import Store
from scholarship_agent.translate import clean_title, english, pending, translate_catalog

TODAY = date(2026, 10, 20)
UI = Path(__file__).resolve().parents[1] / "scholarship_agent" / "webui" / "i18n"


def record(store, oid, url, html, hint=()):
    o, _ = extract_opportunity(Page(url, html), provider_name="Example", provider_type=ProviderType.OTHER,
                               source_type=SourceType.OFFICIAL, country_hint=list(hint), retrieved_at="2026-10-20", today=TODAY)
    o.id = oid
    store.save_opportunity(o, oid, url)
    return o


class FakeTranslator:
    """Answers like the model would: one item per numbered text, here the text with "EN:" in front."""
    name = "fake:translator"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, fields=None, meta=None):
        self.calls += 1
        items = re.findall(r"\[(t\d+)\](?: TITLE)?\n(.*?)(?=\n\n\[t\d+\]|\n\nAnswer as JSON)", user, re.S)
        return {"fields": [{"field": f, "value": "EN: " + text, "quote": ""} for f, text in items]}


class DryRun:
    name = "fake:dry"

    def complete_json(self, *a, **kw):
        raise RuntimeError("dry run: paid calls are off")


GERMAN_EN = ("<html><head><title>Master's Scholarships in Germany | Example University</title></head><body>"
             "<h1>Master's Scholarships in Germany</h1><p>The scholarship is open to citizens of all countries. "
             "It covers full tuition fees and a monthly stipend of 934 euros. The application deadline is 15 December 2026.</p>"
             "</body></html>")
FRENCH = ("<html><head><title>752 - Programme de bourses de recherche doctorale - Répertoire des bourses</title></head><body>"
          "<h1>Programme de bourses de recherche doctorale</h1><p>Les candidatures sont ouvertes aux étudiants inscrits au "
          "doctorat. Cette bourse permet aux lauréats d'étudier en France pendant trois ans. La bourse couvre les frais de "
          "scolarité et une allocation mensuelle de "
          "1 500 euros. La date limite de "
          "dépôt des candidatures est le 30 novembre 2026.</p></body></html>")
INDONESIA_ONLY = ("<html><head><title>PhD Fellowship for Indonesian Researchers</title></head><body>"
                  "<h1>PhD Fellowship for Indonesian Researchers</h1><p>Only citizens of Indonesia may apply. The fellowship "
                  "pays a monthly stipend for doctoral research. Applicants must have a master's degree. MBA applicants "
                  "only require 2 years of work experience, except for recent graduates. The application deadline was "
                  "1 March 2026.</p></body></html>")


class TestTitles(unittest.TestCase):
    def test_site_names_and_catalogue_numbers_are_dropped(self):
        self.assertEqual(clean_title("Academic Merit Scholarship - Griffith College", "https://www.griffith.ie/x"),
                         "Academic Merit Scholarship")
        self.assertEqual(clean_title("752 - Programme de bourses doctorales - Répertoire des bourses de l'Université Laval",
                                     "https://repertoire.bbaf.ulaval.ca/b/1"), "Programme de bourses doctorales")
        self.assertEqual(clean_title("Becas Líderes UNIBE | Programa y requisitos", "https://unibe.edu.do/x"), "Becas Líderes UNIBE")

    def test_a_generic_title_keeps_the_name_after_it(self):
        self.assertEqual(clean_title("Scholarship | Bakala Foundation", "https://bakalafoundation.org/s"), "Scholarship - Bakala Foundation")
        self.assertEqual(clean_title("Visiting Fellowships | ANU Philippines Institute", "https://philippinesinstitute.anu.edu.au/v"),
                         "Visiting Fellowships - ANU Philippines Institute")

    def test_titles_without_a_site_part_are_unchanged(self):
        t = "2026 Fulbright Student (Master's and PhD) Program"
        self.assertEqual(clean_title(t, "https://example.org/f"), t)


class TestTranslation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        record(self.st, "de1", "https://example.org/de", GERMAN_EN, ["DE"])
        record(self.st, "fr1", "https://example.org/fr", FRENCH, ["FR"])

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_only_records_in_other_languages_are_translated_and_paid_once(self):
        llm = FakeTranslator()
        out = translate_catalog(self.st, llm)
        self.assertEqual(out["records_in_other_languages"], 1)
        self.assertGreater(out["translated"], 1)
        self.assertIsNone(out["stopped"])
        fr = english(self.st, self.st.get_opportunity("fr1"))
        self.assertEqual(fr["language"], "fr")
        self.assertTrue(fr["title"].startswith("EN: "))
        self.assertTrue(fr["texts"] and all(v.startswith("EN: ") for v in fr["texts"].values()))
        de = english(self.st, self.st.get_opportunity("de1"))
        self.assertEqual((de["language"], de["texts"]), ("en", {}))
        self.assertEqual(de["title"], "Master's Scholarships in Germany")   # the site name is dropped, nothing translated
        calls = llm.calls
        self.assertEqual(translate_catalog(self.st, llm)["texts_pending"], 0)   # stored: nothing is asked twice
        self.assertEqual(llm.calls, calls)

    def test_a_dry_run_stops_without_storing_anything(self):
        out = translate_catalog(self.st, DryRun())
        self.assertIn("dry run", out["stopped"])
        self.assertEqual(out["translated"], 0)
        self.assertTrue(pending(self.st, self.st.list_opportunities()))

    def test_the_card_shows_english_beside_the_original(self):
        from scholarship_agent.service import ScholarshipService
        translate_catalog(self.st, FakeTranslator())
        svc = ScholarshipService(store=self.st, search=None, today=TODAY, extractor_llm=None)
        c = svc.decision_card("fr1")
        self.assertTrue(c["title"].startswith("EN: "))
        self.assertIn("Programme de bourses", c["title_original"])
        quotes = c["decisions"]["funding"]["quotes"]
        self.assertTrue(quotes and quotes[0]["translation"].startswith("EN: "))
        self.assertNotIn("EN: ", quotes[0]["quote"])   # the evidence stays the page's own words


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name))
        record(self.st, "de1", "https://example.org/de", GERMAN_EN, ["DE"])
        record(self.st, "fr1", "https://example.org/fr", FRENCH, ["FR"])
        record(self.st, "id1", "https://example.org/id", INDONESIA_ONLY, ["NL"])

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def find(self, **kw):
        return site.search(self.st, TODAY, **kw)

    def test_synonyms_in_indonesian_and_degree_shorthands(self):
        r = self.find(text="beasiswa S2 Jerman")
        self.assertEqual([x["id"] for x in r["results"]], ["de1"])
        self.assertEqual({q["kind"] for q in r["query"]}, {"level", "country"})
        r = self.find(text="doctorat")   # a level word: the French title ranks first, other PhD programmes follow
        self.assertEqual([x["id"] for x in r["results"]], ["fr1", "id1"])
        self.assertEqual([x["id"] for x in self.find(text="allocation mensuelle")["results"]], ["fr1"])

    def test_filters_and_citizenship(self):
        self.assertEqual([x["id"] for x in self.find(country="FR")["results"]], ["fr1"])
        ids = {x["id"] for x in self.find(citizenship="MY")["results"]}
        self.assertNotIn("id1", ids)   # only Indonesians may apply
        r = self.find(citizenship="ID")
        self.assertEqual(r["results"][0]["fit"], "open")
        self.assertNotIn("id1", {x["id"] for x in self.find(open_only=True)["results"]})   # closed in March

    def test_deadline_order_facets_and_partial_matches(self):
        r = self.find()
        self.assertEqual([x["id"] for x in r["results"]][:2], ["fr1", "de1"])   # 30 November before 15 December
        self.assertEqual(r["sort"], "deadline")
        self.assertEqual(r["facets"]["countries"].get("DE"), 1)
        r = self.find(text="germany zzzunknownword")
        self.assertEqual(r["match"], "some")

    def test_details_mark_a_requirement_limited_to_some_applicants(self):
        d = site.details(self.st, self.st.get_opportunity("id1"), TODAY)
        work = [x for x in d["requirements"] if x["kind"] == "work_years"]
        self.assertEqual([x["state"] for x in work], ["check"])   # shown with its sentence, marked for checking
        self.assertTrue(d["dates"])

    def test_stats_cover_six_months(self):
        s = site.stats(self.st, TODAY)
        self.assertEqual(len(s["deadlines_by_month"]), 6)
        self.assertEqual(s["programmes"], 3)


@unittest.skipUnless(UI.exists(), "the website files are kept outside the public repository")
class TestStrings(unittest.TestCase):
    def keys(self, d, p=""):
        out = set()
        for k, v in d.items():
            if k != "_note":
                out |= self.keys(v, p + k + ".") if isinstance(v, dict) else {p + k}
        return out

    def test_every_language_has_every_english_key(self):
        index = json.loads((UI / "index.json").read_text())
        self.assertIn("en", index)
        en = self.keys(json.loads((UI / "en.json").read_text()))
        for code in index:
            other = self.keys(json.loads((UI / f"{code}.json").read_text()))
            self.assertEqual(en - other, set(), code)
            self.assertEqual(other - en, set(), code)

    def test_string_files_are_served(self):
        from scholarship_agent import web
        for code in json.loads((UI / "index.json").read_text()):
            self.assertIn(f"/static/i18n/{code}.json", web.STATIC)


if __name__ == "__main__":
    unittest.main()
