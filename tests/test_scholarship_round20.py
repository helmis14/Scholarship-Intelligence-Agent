"""Round 20 (part 1): five kinds of source page and programme identity. Offline.

The cases are modelled on pages that round 19 stored as programmes although they were not: news posts,
home pages, catalogues, guidance pages and calls for organisations."""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent.extract import PAGE_KIND_NAMES, Page, page_kind  # noqa: E402
from scholarship_agent.identity import identity, programme_lines, title_specificity  # noqa: E402
from scholarship_agent.models import Evidence, Opportunity  # noqa: E402

PROGRAMME_BODY = ("<h2>Who can apply</h2><p>Applicants must be citizens of an eligible country and hold a bachelor's "
                  "degree.</p><h2>Benefits</h2><p>The scholarship covers tuition fees and a monthly stipend.</p>"
                  "<h2>How to apply</h2><p>Submit your application online. Deadline: 15 January 2027.</p>")


def page(url, title, body, extra_head=""):
    return Page(url, f"<html><head><title>{title}</title>{extra_head}</head><body><h1>{title}</h1>{body}</body></html>")


def kind(url, title, body=PROGRAMME_BODY, extra_head=""):
    return page_kind(page(url, title, body, extra_head))[0]


class TestTitleSpecificity(unittest.TestCase):
    def test_programme_names_are_specific(self):
        for title, provider in [
            ("Chevening SIDS Scholarship | Chevening", "UK Foreign, Commonwealth & Development Office"),
            ("Commonwealth PhD Scholarships - Commonwealth Scholarship Commission in the UK",
             "Commonwealth Scholarship Commission in the UK"),
            ("Commonwealth Fellowships – information for candidates - Commonwealth Scholarship Commission in the UK",
             "Commonwealth Scholarship Commission in the UK"),
            ("Türkiye Bursları", ""), ("Global Korea Scholarship", ""), ("NL Scholarship", "Nuffic"),
            ("Singapore International Graduate Award (SINGA)", "A*STAR"), ("Ernst Mach Grant - worldwide", "OeAD"),
            ("Swiss Government Excellence Scholarships 2027 – 2028", ""), ("Beasiswa Pendidikan Indonesia (BPI)", ""),
        ]:
            self.assertTrue(title_specificity(title, provider)[0], title)

    def test_categories_portals_and_registry_names_are_generic(self):
        for title, provider in [
            ("Homepage | Gates Cambridge", "Gates Cambridge Trust"),
            ("Scholarships Archive - Commonwealth Scholarship Commission in the UK",
             "Commonwealth Scholarship Commission in the UK"),
            ("DAAD Scholarship Database", "DAAD"), ("Erasmus Mundus Joint Masters catalogue", ""),
            ("International scholarships", ""), ("Bourses internationales", ""), ("Information for scholarship applicants", ""),
            ("Scholarships for foreign students in France", "Campus France"), ("Overview: grants and scholarships", "OeAD"),
            ("OeAD scholarships (Austria)", "OeAD"), ("NAWA programmes (Poland)", "NAWA"), ("VLIR-UOS scholarships", ""),
            ("Funding your studies | Postgraduate study | The University of Edinburgh", "University of Edinburgh"),
            ("Scholarships | Plan your studies | Study in Korea | Run by Korean Government", ""),
            ("Becas SEP: Encuentra tu beca", ""), ("Para estudiar en Chile - Chile en el Exterior", ""),
        ]:
            self.assertFalse(title_specificity(title, provider)[0], title)


class TestPageKind(unittest.TestCase):
    def test_kinds_have_plain_names(self):
        self.assertEqual(set(PAGE_KIND_NAMES), {"opportunity", "listing", "guidance", "news", "not_relevant", "not_loaded"})

    def test_programme_page(self):
        self.assertEqual(kind("https://www.example.ac.uk/scholarships/global-excellence", "Global Excellence Scholarship"),
                         "opportunity")

    def test_announcements(self):
        self.assertEqual(kind("https://www.educanada.ca/scholarships-bourses/news-nouvelles/2026/2026-09-16.aspx",
                              "Apply now for the Netaji Subhas-ICAR International Fellowship"), "news")
        dated = "<p>16 September 2026</p>" + PROGRAMME_BODY
        self.assertEqual(kind("https://cscuk.fcdo.gov.uk/health-practitioners-benefit-from-fellowships/",
                              "Health practitioners benefit from development fellowships", dated), "news")
        # a date-stamped upload folder is not a news path
        self.assertEqual(kind("https://www.fundacioncarolina.es/wp-content/uploads/2026/01/convocatoria.pdf",
                              "Convocatoria de becas 2026-2027"), "opportunity")

    def test_home_pages_and_catalogues_are_portals(self):
        links = "".join(f"<li>Programme {n} scholarship</li>" for n in range(4))
        self.assertEqual(kind("https://fulbright.example.org/", "Fulbright Colombia – Intercambio educativo",
                              f"<ul>{links}</ul>" + PROGRAMME_BODY), "listing")
        # a programme's own site: its home page is the programme
        self.assertEqual(kind("https://www.multidiverse.example.eu/", "Home | MultiDiverse"), "opportunity")
        self.assertEqual(kind("https://www.gatescambridge.example.org/", "Homepage | Gates Cambridge"), "listing")
        self.assertEqual(kind("https://www.daad.example.de/de/programme", "DAAD Scholarship Database"), "listing")
        self.assertEqual(kind("https://www.eacea.example.eu/scholarships/erasmus-mundus-catalogue_de",
                              "Erasmus-Mundus-Katalog"), "listing")
        self.assertEqual(kind("https://www.campusfrance.example.org/en/bursaries-foreign-students",
                              "Scholarships for foreign students in France"), "listing")
        self.assertEqual(kind("https://www.educanada.example.ca/scholarships-bourses/index.aspx",
                              "International scholarships"), "listing")

    def test_guidance_pages(self):
        for title in ("Information for scholarship applicants", "Finding a scholarship step-by-step",
                      "Prepare to Apply | Funding Guidance | Wellcome", "Organising your stay as a scholarship holder",
                      "Para estudiar en Chile - Chile en el Exterior", "Students from Nigeria"):
            self.assertEqual(kind("https://www.example.org/students/funding", title), "guidance", title)
        general = "<p>There are no governmental scholarship programmes. Start at the university you apply to.</p>"
        self.assertEqual(kind("https://www.example.fi/en/doctoral-funding", "Doctoral funding in Finland",
                              general + PROGRAMME_BODY), "guidance")
        # a programme's own page for candidates stays a programme page
        self.assertEqual(kind("https://cscuk.example.uk/scholarships/commonwealth-fellowships-information",
                              "Commonwealth Fellowships – information for candidates"), "opportunity")

    def test_calls_for_organisations_are_not_for_applicants(self):
        self.assertEqual(kind("https://erasmus-plus.example.eu/opportunities/organisations/emjm",
                              "Erasmus Mundus Joint Masters (organisations)"), "not_relevant")
        body = ("<p>Universities are invited to apply for project funding. The grant supports partnerships between "
                "higher education institutions. Deadline: 15 January 2027. Funding covers staff costs.</p>")
        self.assertEqual(kind("https://www.example.org/calls/partnerships", "Partnership grant", body), "not_relevant")
        body_students = body + "<p>Students can apply for the mobility scholarships offered by the partners.</p>"
        self.assertNotEqual(kind("https://www.example.org/calls/partnerships", "Partnership grant", body_students),
                            "not_relevant")

    def test_programme_lines_counts_listed_awards(self):
        self.assertEqual(programme_lines("Chevening Scholarships\nCommonwealth Scholarships\nA sentence about a grant."), 2)


def opp(**kw):
    base = dict(id="sch_x", title="Ernst Mach Grant - worldwide", provider_name="OeAD",
                info_url="https://oead.at/en/ernst-mach", source_authority="1_official_programme_page")
    return Opportunity(**(base | kw))


class TestIdentity(unittest.TestCase):
    def test_specific_official_named_programme_is_confirmed(self):
        r = identity(opp(), page_title="Ernst Mach Grant - worldwide", h1="Ernst Mach Grant",
                     text="Ernst Mach Grant for postdocs", page_kind="opportunity")
        self.assertEqual(r["state"], "confirmed", r)

    def test_page_that_is_not_a_programme_is_rejected(self):
        r = identity(opp(title="Scholarships Archive"), page_kind="listing")
        self.assertEqual(r["state"], "rejected")
        self.assertIn("listing", r["reasons"][0])

    def test_record_named_after_its_source_needs_review(self):
        o = opp(title="OeAD scholarships (Austria)",
                evidence=[Evidence(field="title", value="Ernst Mach Grant - worldwide", source_url="u")])
        r = identity(o)
        self.assertEqual(r["state"], "needs_review")
        self.assertIn("named after its source", r["reasons"][0])

    def test_generic_title_programme_needs_a_name(self):
        r = identity(opp(title="PhD Fellowships", provider_name="TWAS"), page_kind="opportunity")
        self.assertEqual(r["state"], "needs_review")

    def test_missing_provider_and_unofficial_source_need_review(self):
        self.assertEqual(identity(opp(provider_name="studyin.gov.cz"))["state"], "needs_review")
        r = identity(opp(source_authority="6_aggregator_or_search_result"))
        self.assertEqual(r["state"], "needs_review")
        self.assertIn("not on an official page", r["reasons"][-1])


if __name__ == "__main__":
    unittest.main()
