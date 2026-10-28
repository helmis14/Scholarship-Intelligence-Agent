"""Round 49: yearly deadlines without a year, DAAD detail pages read section by section, Erasmus Mundus consortium
sites read beyond their home page, and a few funding and eligibility phrases."""
import unittest
from datetime import date

from scholarship_agent.adapters.base import AdapterResult
from scholarship_agent.adapters.daad import DAADAdapter, programme_page
from scholarship_agent.adapters.erasmus_mundus import ErasmusMundusAdapter, consortium_countries, section_pages
from scholarship_agent.audit import cycle_status, field_status
from scholarship_agent.extract import Page, extract_deadlines, extract_funding, extract_nationality
from scholarship_agent.models import DeadlineCertainty, DeadlineKind, Opportunity, ProviderType
from scholarship_agent.net import Fetcher, Response
from scholarship_agent.site import _deadline_key, next_recurring

TODAY = date(2026, 10, 26)


def dl(text):
    return [(str(d.kind), d.certainty, d.date, d.recurs) for d in extract_deadlines(text, "https://x.example/p", TODAY)]


class TestYearlyDeadlines(unittest.TestCase):
    def test_a_yearly_date_is_expected_with_its_day_and_never_a_dated_deadline(self):
        got = dl("Application Deadline\n1 March and 1 September of each year")
        self.assertEqual(got, [("scholarship", DeadlineCertainty.EXPECTED, None, "03-01"),
                               ("scholarship", DeadlineCertainty.EXPECTED, None, "09-01")])
        self.assertEqual(dl("The deadline to apply for the Foundation Fellowship is November 1 of each year."),
                         [("scholarship", DeadlineCertainty.EXPECTED, None, "11-01")])

    def test_windows_semesters_and_other_dates(self):
        self.assertEqual([(k, r) for k, _, _, r in dl("Application deadline: 1 October to 15 January (midnight) for a "
                                                       "scholarship for the following winter semester")],
                         [("opening", "10-01"), ("scholarship", "01-15")])
        # the start of the programme is not a deadline
        self.assertEqual([(k, r) for k, _, _, r in dl("Application deadline: 1 September for the following summer "
                                                       "semester (programme start 1 April)")],
                         [("scholarship", "09-01"), ("event", "04-01")])
        self.assertEqual(dl("Form 1042-S will be mailed no later than February 28th of each year."), [])
        self.assertEqual(dl("Results are announced on 1 June each year."), [])
        self.assertEqual(dl("Deadline for the winter semester 2026/27: 15 July"), [])   # one cycle's date, not a rule

    def test_decisions_are_unchanged_and_the_site_shows_the_next_day(self):
        o = Opportunity(id="o1", title="Fellowship", provider_name="p", provider_type=ProviderType.FOUNDATION,
                        info_url="https://x.example/p")
        o.deadlines = extract_deadlines("Applications due by 5 September and 5 March every year", o.info_url, TODAY)
        self.assertEqual(cycle_status(o, TODAY)["state"], "not_stated")
        self.assertEqual(field_status(o, TODAY)["deadline"]["state"], "approximate")
        self.assertEqual(next_recurring(o, TODAY), "2027-03-05")
        expected = {"cycle": "", "next_deadline": None, "last_deadline": None, "expected_deadline": "2027-03-05"}
        unknown = dict(expected, expected_deadline=None)
        self.assertLess(_deadline_key(expected), _deadline_key(unknown))


DAAD_PAGE = """<html><head><title>Example Foundation: Scholarship - DAAD</title></head><body>
<h3 class="print-only">Overview</h3>
<h3>Scholarship Value</h3><p>1,500 EUR per month<br>contribution to statutory health insurance</p>
<h3>Duration</h3><p>Funding generally covers the standard period of study.</p>
<h3>Application Deadline</h3><p>15 December of each year<br>After the application deadline has expired, the portal closes.</p>
<h3>Contact</h3><p>Example Foundation, Berlin</p>
<h3>Please select your status and your country to enable you to submit an application</h3>
<p>Afghanistan<br>Albania<br>Algeria</p>
</div><!--! end of #ueberblick --></body></html>"""


class TestDAADDetail(unittest.TestCase):
    def test_programme_sections_only(self):
        page = programme_page("https://www2.daad.de/x?detail=1", DAAD_PAGE)
        self.assertNotIn("Afghanistan", page.text)
        self.assertNotIn("Berlin", page.text)
        self.assertIn("Scholarship value: 1,500 EUR per month", page.text)
        self.assertIn("Application deadline: 15 December of each year", page.text)
        self.assertIn("\nAfter the application deadline has expired", page.text)   # no date, so no label

    def test_detail_adds_deadline_and_funding(self):
        o = Opportunity(id="d1", title="Example", provider_name="Example Foundation", provider_type=ProviderType.FOUNDATION,
                        info_url="https://www2.daad.de/x?detail=1")
        o.uncertainties = ["no deadline entry in the DAAD dataset for this programme"]
        DAADAdapter(Fetcher(lambda u, h: None), today=TODAY).apply_detail(o, programme_page(o.info_url, DAAD_PAGE))
        self.assertEqual([(d.recurs, d.certainty) for d in o.deadlines], [("12-15", DeadlineCertainty.EXPECTED)])
        self.assertFalse(any("no deadline" in u for u in o.uncertainties))
        st = next(c for c in o.funding if c.kind == "stipend")
        self.assertEqual((st.amount, st.currency, st.period), (1500.0, "EUR", "month"))
        self.assertTrue(any(e.field.startswith("deadline") for e in o.evidence))
        self.assertEqual(cycle_status(o, TODAY)["state"], "not_stated")   # no "closed" from the conditional sentence


HOME = """<html><head><title>EXAMPLE Joint Master</title></head><body><nav>
<a href="/scholarships">Scholarships &amp; Fees</a><a href="/apply">How to apply</a><a href="/consortium">Consortium</a>
<a href="/news">News</a><a href="https://other.example/scholarships">Elsewhere</a><a href="/files/guide.pdf">Guide</a>
</nav><p>An Erasmus Mundus Joint Master.</p></body></html>"""
PAGES = {
    "https://em.example/": HOME,
    "https://em.example/scholarships": "<html><head><title>Scholarships</title></head><body><p>Erasmus Mundus "
                                       "scholarship holders receive a monthly allowance of EUR 1,400 for 24 months. "
                                       "The scholarship also covers the participation costs (tuition fees).</p></body></html>",
    "https://em.example/apply": "<html><head><title>How to apply</title></head><body><p>The application deadline for "
                                "the 2027 intake is 15 January 2027.</p></body></html>",
    "https://em.example/consortium": "<html><head><title>Consortium</title></head><body><ul>"
                                     "<li>University of Granada (Spain)</li><li>Université de Lille, France</li>"
                                     "<li>Universität Konstanz (Germany)</li></ul><h4>Associated partners</h4>"
                                     "<ul><li>University of Tokyo (Japan)</li></ul></body></html>",
}


def transport(url, headers):
    if url.endswith("/robots.txt"):
        return Response(url, 404, "text/plain", "")
    body = PAGES.get(url.rstrip("/") + ("/" if url.rstrip("/") == "https://em.example" else ""))
    return Response(url, 200, "text/html", body) if body else Response(url, 404, "text/html", "")


class TestErasmusSites(unittest.TestCase):
    def test_section_pages(self):
        got = section_pages(Page("https://em.example/", HOME))
        self.assertEqual(got, ["https://em.example/scholarships", "https://em.example/apply",
                               "https://em.example/consortium"])

    def test_consortium_countries_leave_out_associated_partners(self):
        text = Page("https://em.example/consortium", PAGES["https://em.example/consortium"]).text
        self.assertEqual([c for c, _ in consortium_countries(text)], ["ES", "FR", "DE"])

    def test_programme_site_read_beyond_home(self):
        o = Opportunity(id="e1", title="EXAMPLE", provider_name="EXAMPLE consortium", provider_type=ProviderType.UNIVERSITY,
                        info_url="https://em.example/", study_levels=["master"])
        o.uncertainties = ["scholarship terms, eligibility and deadlines are set by the consortium; read the programme website"]
        res = AdapterResult("erasmus_mundus")
        ErasmusMundusAdapter(Fetcher(transport, min_interval=0, sleep=lambda s: None), today=TODAY).read_programme_site(o, res)
        self.assertEqual(res.requests, 4)
        self.assertEqual(o.destination_countries, ["ES", "FR", "DE"])
        self.assertIn("2027-01-15", {d.date for d in o.deadlines if d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)})
        self.assertTrue(any(c.kind in ("stipend", "living_allowance") and c.amount == 1400.0 for c in o.funding))
        self.assertEqual(o.uncertainties, [])
        dest_ev = [e for e in o.evidence if e.field == "destination"]
        self.assertTrue(all(e.source_url == "https://em.example/consortium" for e in dest_ev))


class TestPhrases(unittest.TestCase):
    def test_funding_phrases(self):
        for text, amount in (("The fellowship is worth 3,600 EUR per month.", 3600.0), ("grant: 1,500 EUR per month", 1500.0),
                             ("base amount of up to 855 EUR per month", 855.0)):
            st = next(c for c in extract_funding(text)[0] if c.kind == "stipend")
            self.assertEqual((st.amount, st.period), (amount, "month"), text)
        acc = extract_funding("If no guest room is available, a flat-rate accommodation allowance of 500 EUR per month "
                              "will be paid.")[0]
        self.assertTrue(next(c for c in acc if c.kind == "accommodation").covered)

    def test_a_document_for_some_countries_is_not_an_eligibility_rule(self):
        rule, _ = extract_nationality("Applicants from China, India and Vietnam: APS certificate (original) issued by "
                                      "the German Embassy of your home country.")
        self.assertEqual(rule.mode, "unknown")
        self.assertEqual(extract_nationality("The scholarship is open to citizens of Indonesia only.")[0].countries, ["ID"])


if __name__ == "__main__":
    unittest.main()


class TestAdapterRerun(unittest.TestCase):
    def test_a_second_run_replaces_the_adapters_own_records(self):
        import tempfile
        from pathlib import Path
        from scholarship_agent.service import ScholarshipService
        from scholarship_agent.store import Store
        from tests.test_scholarship_adapters import daad_pages, fetcher
        svc = ScholarshipService(Store(Path(tempfile.mkdtemp())), fetcher(daad_pages(True)), search=None, today=TODAY,
                                 sources=[], extractor_llm=None)
        first = svc.run_adapter("daad", details=True)
        second = svc.run_adapter("daad", details=True)
        self.assertEqual((first["new"], second["new"], second["refreshed"], second["merged"]), (3, 0, 3, 0))
        self.assertEqual(len(svc.store.list_opportunities()), 3)
        self.assertFalse(any(o.conflicts for o in svc.store.list_opportunities()))


class TestCheckCatalog(unittest.TestCase):
    def test_second_reading_of_stored_records(self):
        import tempfile
        from pathlib import Path
        from scholarship_agent.ai_check import check_catalog
        from scholarship_agent.store import Store
        st = Store(Path(tempfile.mkdtemp()))
        text = "<html><head><title>Example Scholarship</title></head><body><p>" + ("The scholarship is open to citizens "
                "of Kenya only. It covers full tuition fees and a monthly stipend. " * 6) + "</p></body></html>"
        for i, via in enumerate(("source:x", "adapter:daad", "source:y")):
            o = Opportunity(id=f"c{i}", title=f"Example {i}", provider_name="p", provider_type=ProviderType.FOUNDATION,
                            info_url=f"https://x.example/{i}", discovered_via=via)
            st.save_opportunity(o, f"k{i}", o.info_url)

        class LLM:
            calls = 0

            def complete_json(self, system, user, **kw):
                LLM.calls += 1
                if LLM.calls > 1:
                    raise RuntimeError("budget reached")
                return {"fields": [{"field": "nationality", "value": "include: KE", "quote": "citizens of Kenya only"}]}

        f = Fetcher(lambda u, h: Response(u, 404, "text/plain", "") if u.endswith("robots.txt")
                    else Response(u, 200, "text/html", text), min_interval=0, sleep=lambda s: None)
        out = check_catalog(st, f, LLM(), TODAY)
        self.assertEqual((out["records_to_check"], out["checked"], out["no_answer"]), (2, 1, 1))   # adapter record left out
        self.assertIsNone(out["stopped"])   # one failed request is skipped, not the end of the run
        self.assertEqual(st.get_opportunity("c0").second_reading["nationality"], "include: KE")
        self.assertFalse(st.get_opportunity("c2").second_reading)


class TestListed(unittest.TestCase):
    def rec(self, title, page_type="unknown", identity=None, via="source:x", otype="unknown", terms=True):
        from scholarship_agent.models import FundingComponent
        o = Opportunity(id="l", title=title, provider_name="p", provider_type=ProviderType.FOUNDATION,
                        info_url="https://x.example/scholarship", discovered_via=via, opportunity_type=otype)
        o.page_type, o.programme_identity = page_type, identity or {}
        o.funding = [FundingComponent(kind="stipend")] if terms else []
        return o

    def test_the_site_lists_programmes_not_news_hubs_or_guides(self):
        from scholarship_agent.site import listed
        unsure = lambda kind: {"state": "needs_review", "reasons": [f"page type uncertain (best guess: {kind}): ..."]}  # noqa: E731
        self.assertTrue(listed(self.rec("Example Scholarship", "scholarship_program", {"state": "confirmed"})))
        self.assertTrue(listed(self.rec("DAAD programme", via="adapter:daad")))
        self.assertFalse(listed(self.rec("Legacy project", via="adapter:erasmus_mundus", otype="funded_project")))
        self.assertTrue(listed(self.rec("LPDP scholarship", identity=unsure("opportunity"))))
        self.assertFalse(listed(self.rec("LPDP scholarship", identity=unsure("opportunity"), terms=False)))
        self.assertFalse(listed(self.rec("Financial Aid Glossary", identity=unsure("opportunity"))))
        self.assertFalse(listed(self.rec("Announcement of Successful Applications for the Fellowships",
                                         identity=unsure("opportunity"))))
        self.assertFalse(listed(self.rec("Malaysia higher education scholarships", identity=unsure("listing"))))
        self.assertFalse(listed(self.rec("A Simple Introduction to PhD Funding", "aggregator")))
        self.assertTrue(listed(self.rec("Example Fellowship")))   # never assessed: judged by its terms
        # round 50: a page named only by its office or topic is not a programme; "Scholarship - X" names X
        self.assertFalse(listed(self.rec("Financial Aid | Example University", "scholarship_program")))
        self.assertTrue(listed(self.rec("Scholarship - Vietnam High Achievers", "scholarship_program")))


CF_JS = ('angular.module("x").factory("IwCountry",[function(){var l={fr:"Tous"},c=[{id:9,fr:"Cameroun",en:"Cameroon",'
         'continent_id:1,iso:"CM"},{id:21,fr:"Gabon",en:"Gabon",continent_id:1,iso:"GA"}];return{}}])'
         '.factory("IwLevel",[function(){var l=[{id:1,fr:"Licence",en:"Bachelor"},{id:2,fr:"Master",en:"Master"}];return{}}])'
         '.factory("IwType",[function(){var l=[{id:1,fr:"Bourse d\'études",en:"Study"},{id:5,fr:"Réduction",en:"Partial '
         'tuition fee waivers"}];return{}}]).factory("IwFunding",[function(){var l=[{id:1,fr:"Gouvernement français",'
         'en:"French government"}];return{}}]).factory("IwDomain",[function(){var l=[{id:9,fr:"Informatique",'
         'en:"Computer Science"}];return{}}])')
CF_LIST = {"count": 2, "op": 1, "programs": [
    {"bourseId": 321, "title": "French Government grants - Embassy in Gabon", "typeListId": "1", "levelListId": "2",
     "domainListId": "90000", "countryListId": "21,9", "fundingByListId": "1", "tcampus": 1, "updatedAt": "2026-05-12",
     "endAt": "2027-01-25", "synthese": "Grants for students from Gabon and Cameroon."},
    {"bourseId": 1641, "title": "Excellence Scholarship - Example School", "typeListId": "5", "levelListId": "2",
     "domainListId": "", "countryListId": "", "fundingByListId": "1", "tcampus": 0, "updatedAt": "2026-05-12",
     "endAt": "2026-08-31", "synthese": "A tuition reduction."}]}
CF_DETAIL = {"op": 1, "bourseId": 1641, "typeListId": "5", "title": "Excellence Scholarship - Example School",
             "description": "<div>For international students admitted to the MSc.</div>",
             "montant": "<div>€3,000 reduction of the tuition fees</div>", "duree": "<div>1 year</div>",
             "countryNote": "<div>The scholarship is open to citizens of Japan only.</div>",
             "pieces": "<div>CV and motivation letter</div>", "inscriptionUrl": "https://apply.example.fr/",
             "web1": "Example School", "url1": "https://www.example.fr", "dates": "", "selection": ""}


class TestCampusFrance(unittest.TestCase):
    def fetcher(self, with_detail=True):
        import json
        from scholarship_agent.adapters.campusfrance import API, SITE
        pages = {SITE: '<script src="js/ilangular.0a1b2c3d.js"></script>', SITE + "js/ilangular.0a1b2c3d.js": CF_JS,
                 API + "sgetgrants/en": json.dumps(CF_LIST)}
        if with_detail:
            pages[API + "sgetgrant/1641/en"] = json.dumps(CF_DETAIL)

        def t(url, headers):
            if url.endswith("/robots.txt"):
                return Response(url, 404, "text/plain", "")
            v = pages.get(url)
            return Response(url, 200, "application/json" if "api" in url else "text/html", v) if v else \
                Response(url, 404, "text/html", "")
        return Fetcher(t, min_interval=0, sleep=lambda s: None)

    def test_dataset_and_details(self):
        from scholarship_agent.adapters.campusfrance import CampusFranceAdapter
        res = CampusFranceAdapter(self.fetcher(), today=TODAY, details=True).run()
        self.assertEqual(len(res.records), 2)
        gabon, school = res.records
        self.assertEqual((gabon.nationality.mode, gabon.nationality.countries), ("include", ["CM", "GA"]))
        self.assertEqual((gabon.study_levels, gabon.disciplines, gabon.destination_countries),
                         (["master"], ["Computer Science"], ["FR"]))
        self.assertEqual([(d.date, d.certainty) for d in gabon.deadlines], [("2027-01-25", DeadlineCertainty.CONFIRMED)])
        self.assertEqual(len(res.failures), 1)   # the first programme's detail is not in the fixture
        # no location list: the programme's own words decide; the grant type adds a partial tuition waiver
        self.assertEqual((school.nationality.mode, school.nationality.countries), ("include", ["JP"]))
        self.assertEqual(school.deadlines[0].certainty, DeadlineCertainty.HISTORICAL)
        self.assertEqual(school.application_url, "https://apply.example.fr/")
        self.assertEqual((school.provider_name, gabon.provider_name), ("Example School", "Campus France (CampusBourses)"))
        self.assertTrue(any(d.name == "CV" for d in school.required_documents))
        tuition = next(c for c in school.funding if c.kind == "tuition")
        self.assertIs(tuition.full, False)

    def test_lists_unavailable(self):
        from scholarship_agent.adapters.campusfrance import CampusFranceAdapter, lookup_tables
        self.assertEqual(lookup_tables("alert(1)"), {})
        self.assertEqual(lookup_tables(CF_JS)["IwCountry"]["21"]["iso"], "GA")
        f = self.fetcher(with_detail=False)
        f.transport = lambda url, h: Response(url, 404, "text/html", "") if "ilangular" in url or url.endswith(
            "robots.txt") else (Response(url, 200, "text/html", '<script src="js/ilangular.0a1b2c3d.js">') if "campusbourses"
                                in url else Response(url, 200, "application/json", __import__("json").dumps(CF_LIST)))
        res = CampusFranceAdapter(f, today=TODAY).run()
        self.assertEqual(len(res.records), 2)
        self.assertEqual(res.records[0].nationality.mode, "unknown")   # no list to read the ids with
        self.assertTrue(res.notes)


GA_DETAIL = ('<div id="GrainEntry"><div class="h3">Example Fellowship</div>'
             '<div class="row"><div class="col-sm-3"><label>Country of origin:</label></div><div class="grain-data col-sm-9">'
             'Indonesia, Viet Nam</div></div>'
             '<div class="row"><div class="col-sm-3"><label>Target country:</label></div><div class="grain-data col-sm-9">'
             'Austria</div></div>'
             '<div class="row"><div class="col-sm-3"><label>Target group:</label></div><div class="grain-data col-sm-9">'
             '  Graduates<br/>  PhD students<br/></div></div>'
             '<div class="row"><div class="col-sm-3"><label>Funding organisation:</label></div><div class="grain-data col-sm-9">'
             '<div>Example Foundation</div></div></div>'
             '<div class="row"><div class="col-sm-3"><label>Grant benefit paid:</label></div><div class="grain-data col-sm-9">'
             '<div>EUR 1,200 per month</div></div></div>'
             '<div class="row" id="subdate"><div class="col-sm-3"><label>Closing date for applications:</label></div>'
             '<div class="grain-data col-sm-9"><div class="sd"><div class="date">15.01.2027</div></div><div class="sd">'
             '<div class="date">Annually (01.03.)</div></div></div></div>'
             '<div class="row"><div class="col-sm-3"><label>Advice on how to apply:</label></div><div class="grain-data col-sm-9">'
             '<div>Send a CV and a motivation letter.</div><div><a href="https://example.org/fellowship" target="_blank">'
             'Further information</a></div></div></div><div class="linerow"> </div></div>')


class TestGrantsAt(unittest.TestCase):
    def test_list_and_detail_through_post(self):
        import json
        from scholarship_agent.adapters.grants_at import API, GrantsAtAdapter
        bodies = []

        def t(url, headers, data=None):
            if url.endswith("/robots.txt"):
                return Response(url, 404, "text/plain", "")
            bodies.append((url, json.loads(data)))
            answers = {"GetMetadata": {"FoerderArten": [{"ID": 11, "T": "Whole degree"}, {"ID": 7, "T": "Awards"}],
                                       "Laender": [{"T": "Indonesia", "ISO": "ID"}, {"T": "Viet Nam", "ISO": "VN"},
                                                   {"T": "Austria", "ISO": "AT"}]},
                       "STIMAEntrySearchForTextParameters": [
                           {"StipFoeID": 1, "HZGID": 0, "StipName": "Example Fellowship", "FoerderArtID": 11},
                           {"StipFoeID": 1, "HZGID": 0, "StipName": "Example Fellowship", "FoerderArtID": 7},
                           {"StipFoeID": 2, "HZGID": 0, "StipName": "Example Prize", "FoerderArtID": 7}],
                       "GetDetailHtml": {"html": GA_DETAIL}}
            return Response(url, 200, "application/json", json.dumps(answers[url[len(API):]]))
        res = GrantsAtAdapter(Fetcher(t, min_interval=0, sleep=lambda s: None), today=TODAY, details=True, detail_limit=1).run()
        self.assertEqual(len(res.records), 2)   # one record per programme, not per grant type
        o = res.records[0]
        self.assertEqual(bodies[1][1]["SearchParameters"], "foerderart:11;7,eingabetyp:4")
        self.assertEqual((o.nationality.mode, o.nationality.countries, o.destination_countries), ("include", ["ID", "VN"], ["AT"]))
        self.assertEqual((o.study_levels, o.provider_name, o.info_url), (["master", "phd"], "Example Foundation",
                                                                        "https://example.org/fellowship"))
        self.assertEqual([(d.date, d.recurs) for d in o.deadlines], [("2027-01-15", None), (None, "03-01")])
        st = next(c for c in o.funding if c.kind == "stipend")
        self.assertEqual((st.amount, st.currency, st.period), (1200.0, "EUR", "month"))
        self.assertTrue(any(d.name == "CV" for d in o.required_documents))
        self.assertEqual(res.records[1].opportunity_type, "award")
        from scholarship_agent.adapters.grants_at import _valid
        self.assertFalse(_valid("http://[malformed"))


NSP_PAGE = ('<button class="accordion-button collapsed" type="button">\n Ministry of Example Affairs\n</button>'
            '<div class="row mb-4 border-1 border-bottom"><div class="col-md-10"><h6> Example Post Matric Scholarship Scheme '
            'For Graduate Students</h6><br><!--<h6>by Ministry</h6>-->'
            '<span>Scheme  Open from : 01-06-2026 </span><span>Student Application  Open till : 31-12-2026 </span>'
            '<span>Institute Verification Open till:15-01-2027 </span>'
            '<div class="mb-4"><a href="https://scholarships.gov.in/public/schemeGuidelines/x.pdf" target="_blank">Specifications'
            '</a></div></div></div>')


class TestNSPIndia(unittest.TestCase):
    def test_schemes_dates_and_form(self):
        from scholarship_agent.adapters.nsp_india import BASE, NSPIndiaAdapter, parse_schemes
        s = parse_schemes(NSP_PAGE)[0]
        self.assertEqual((s["group"], s["title"]), ("Ministry of Example Affairs", "Example Post Matric Scholarship Scheme For Graduate Students"))
        spaced = parse_schemes(NSP_PAGE.replace("schemeGuidelines/x.pdf", "schemeGuidelines/x y.pdf"))[0]
        self.assertEqual(spaced["links"]["Specifications"], BASE + "public/schemeGuidelines/x%20y.pdf")
        calls = []

        def t(url, headers, data=None):
            if url.endswith("/robots.txt"):
                return Response(url, 404, "text/plain", "")
            calls.append(data)
            return Response(url, 200, "text/html", NSP_PAGE if data is None else NSP_PAGE.replace("Example Post", f"Example {len(calls)}"))
        res = NSPIndiaAdapter(Fetcher(t, min_interval=0, sleep=lambda s: None), today=TODAY).run()
        self.assertEqual(len(res.records), 3)   # one scheme from each of the three lists
        self.assertIn(b"central_sponsored_state=sponserscheme", calls[1])
        o = res.records[0]
        self.assertEqual([(str(d.kind), d.date) for d in o.deadlines], [("opening", "2026-06-01"), ("scholarship", "2026-12-31")])
        self.assertEqual((o.provider_name, o.destination_countries, o.info_url),
                         ("Ministry of Example Affairs", ["IN"], BASE + "public/schemeGuidelines/x.pdf"))
        self.assertIn("destination:host", o.tags)
