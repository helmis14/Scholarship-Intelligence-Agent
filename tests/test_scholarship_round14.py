"""Round 14: language registry, localised discovery plan, coverage accounting, resumable runs, layered retrieval,
provider candidates, targeted Claude extraction and field-level evidence. Offline; every model call is faked."""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent import ai_targeted, coverage, languages, providers  # noqa: E402
from scholarship_agent.ai_extract import enrich, judge  # noqa: E402
from scholarship_agent.anthropic_llm import AnthropicLLM  # noqa: E402
from scholarship_agent.discovery import Discovery, DiscoveryResult  # noqa: E402
from scholarship_agent.extract import Page, extract_opportunity, page_from_response, parse_dates  # noqa: E402
from scholarship_agent.models import (Evidence, Opportunity, ProviderType, SourceType,  # noqa: E402
                                      VerificationStatus)
from scholarship_agent.net import Fetcher, Response  # noqa: E402
from scholarship_agent.normalize import normalize_url  # noqa: E402
from scholarship_agent.pdf import make_pdf  # noqa: E402
from scholarship_agent.registry import Source  # noqa: E402
from scholarship_agent.retrieval import needs_browser  # noqa: E402
from scholarship_agent.search import FixtureSearch, SearchHit  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from scholarship_agent.strategy import StrategyConfig, StrategyRunner, plan  # noqa: E402

TODAY = date(2026, 10, 18)
OPP_HTML = ("<html lang='no'><head><title>Stipend for masterstudenter</title></head><body><h1>Stipend for "
            "masterstudenter</h1><p>Stipendet dekker skolepenger og levekostnader for masterstudenter.</p>"
            "<p>Søknadsfrist: 15. mars 2027.</p><p>Stipendet tildeles av Universitetet.</p></body></html>")
JS_SHELL = ("<html><head><title>Scholarships</title>" + "<script src='a.js'></script>" * 6 +
            "</head><body><noscript>Please enable JavaScript to view this site.</noscript><div id='root'></div></body></html>")
RENDERED = ("<html><head><title>Graduate Scholarship 2027</title></head><body><h1>Graduate Scholarship 2027</h1>"
            "<p>The scholarship covers full tuition and a monthly stipend for master's students.</p>"
            "<p>Application deadline: 1 March 2027.</p></body></html>")


class Transport:
    def __init__(self, pages):
        self.pages = {normalize_url(k): v for k, v in pages.items()}
        self.calls = 0

    def __call__(self, url, headers):
        self.calls += 1
        if url.endswith("/robots.txt"):
            return Response(url, 404, "text/plain", "")
        v = self.pages.get(normalize_url(url))
        if isinstance(v, bytes):
            return Response(url, 200, "application/pdf", "", v)
        return Response(url, 200, "text/html", v) if v else Response(url, 404, "text/html", "")


class FakeBrowser:
    name = "fake"

    def __init__(self):
        self.renders = 0
        self.closed = False

    def render(self, url):
        self.renders += 1
        return url, RENDERED, 200

    def close(self):
        self.closed = True


class TmpStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
        mock.patch.stopall()


class TestLanguages(unittest.TestCase):
    def test_registry_and_detection(self):
        self.assertGreaterEqual(len(languages.languages()), 40)
        for code in ("no", "de", "fr", "es", "id", "pt", "nl", "it", "sv", "da", "pl", "ja", "ko", "zh", "ar"):
            self.assertTrue(languages.concept_terms(code, "scholarship"), code)
        self.assertEqual(languages.detect("Stipendet dekker skolepenger", "nb")[0], "no")
        self.assertEqual(languages.detect("留学生のための奨学金の募集要項です。応募締切は12月です。")[0], "ja")
        self.assertEqual(languages.detect("외국인 유학생 장학금 신청 안내입니다.")[0], "ko")
        self.assertEqual(languages.detect("منحة دراسية للطلاب الدوليين في الجامعة")[0], "ar")
        self.assertEqual(languages.detect("Die Bewerbung für das Stipendium ist bis zum 1. März möglich und ist für "
                                          "die Studierenden der Universität.")[0], "de")

    def test_digits_keep_offsets(self):
        s = "آخر موعد ١٥ مارس ٢٠٢٧"
        self.assertEqual(len(languages.ascii_digits(s)), len(s))
        self.assertEqual(languages.normalize_text("１２ 000"), "12 000")

    def test_localised_dates(self):
        cases = {"Søknadsfrist: 15. mars 2027": date(2027, 3, 15), "sista ansökningsdag 1 februari 2027": date(2027, 2, 1),
                 "do dnia 15 stycznia 2027": date(2027, 1, 15), "締切：2026年12月1日": date(2026, 12, 1),
                 "마감: 2026년 12월 1일": date(2026, 12, 1), "آخر موعد ١٥ مارس ٢٠٢٧": date(2027, 3, 15),
                 "uiterlijk 3 maart 2027": date(2027, 3, 3), "prazo: 30 de abril de 2027": date(2027, 4, 30)}
        for s, d in cases.items():
            got = parse_dates(s)
            self.assertIn(d, [x for x, _ in got], s)
            self.assertTrue(all(raw in s for _, raw in got), s)   # evidence stays in the original script

    def test_written_numbers_and_units(self):
        q = "Stipendiet betales i två år."
        self.assertEqual(judge("funding_duration_months", 24, q, q)[0], "accepted")
        q = "Stypendium jest wypłacane przez trzy lata."
        self.assertEqual(judge("funding_duration_months", 36, q, q)[0], "accepted")
        self.assertEqual(languages.unit_kind("måneder"), "month")


class TestTablesAndDocuments(unittest.TestCase):
    def test_tables_links_and_pdf(self):
        p = Page("https://x.example/a", "<table><tr><th>Frist</th><td>1. mars 2027</td></tr></table>"
                                        "<a href='/utlysning.pdf'>Utlysning</a>")
        self.assertEqual(p.tables, [[["Frist", "1. mars 2027"]]])
        self.assertEqual(p.document_links()[0][0], "https://x.example/utlysning.pdf")
        pdf = page_from_response(Response("https://x.example/c.pdf", 200, "application/pdf", "",
                                          make_pdf(["Batas akhir pendaftaran 31 Desember 2026"])))
        self.assertIn("31 Desember 2026", pdf.text)


class TestPlan(unittest.TestCase):
    def test_local_language_queries_come_early(self):
        qs = plan(StrategyConfig(countries=["NO", "JP"], queries_per_country=4))
        texts = [q["query"] for q in qs]
        self.assertIn("stipend Norge", texts)
        self.assertIn("奨学金 日本", texts)
        self.assertEqual({q["language"] for q in qs if q["country"] == "NO"}, {"en", "no"})
        self.assertEqual(len(texts), len({t.lower() for t in texts}))

    def test_concepts_are_validated_and_english_fallback(self):
        with self.assertRaises(ValueError):
            StrategyConfig.load({"concepts": ["lottery"]})
        qs = plan(StrategyConfig(countries=["FJ"], queries_per_country=12))
        self.assertIn("scholarship for Fiji citizens", [q["query"] for q in qs])
        self.assertTrue(all(q["language"] == "en" for q in qs))


class TestRunnerCoverageResume(TmpStore):
    URL = "https://www.uio.no/stipend"

    def runner(self, provider, fetcher=None, **cfg):
        d = Discovery(self.store, fetcher or Fetcher(Transport({self.URL: OPP_HTML}), min_interval=0,
                                                     sleep=lambda s: None), None, TODAY, [])
        c = StrategyConfig(**({"countries": ["NO"], "queries_per_country": 2, "results_per_page": 2,
                               "concurrency": 3} | cfg))
        return StrategyRunner(self.store, d, provider, c, sleep=lambda s: None, today=TODAY)

    def test_coverage_counts_what_happened(self):
        p = FixtureSearch({"*": [SearchHit(self.URL, "Stipend"), SearchHit("https://gone.example.org/x", "Stipend gone")]})
        rep = self.runner(p).run()
        self.assertEqual(rep["languages_attempted"], {"en": 1, "no": 1})
        self.assertGreater(rep["network_requests"], 0)
        cov = coverage.report(self.store, TODAY, [])
        self.assertIn(cov["by_country"]["NO"]["status"], ("yielded", "official"))
        self.assertEqual(cov["summary"]["countries_by_status"]["not_attempted"], 230)   # configured is not covered
        self.assertEqual(cov["by_language"]["no"]["queries"], 1)
        self.assertEqual(cov["summary"]["retrieval_failures"], 1)
        self.assertEqual(cov["leads_vs_verified"]["discovered_urls"], 2)
        self.assertIn("www.uio.no".removeprefix("www."), cov["top_domains"])

    def test_interrupted_fetches_are_resumed_and_checkpoints_continue(self):
        p = FixtureSearch({"*": [SearchHit(self.URL, "Stipend")]})
        r = self.runner(p)
        with mock.patch.object(StrategyRunner, "_prefetch", side_effect=RuntimeError("power cut")):
            with self.assertRaises(RuntimeError):
                r.run()
        self.assertEqual(len(self.store.pending_urls(10)), 1)      # discovered, never fetched
        rep = self.runner(p).run()
        self.assertEqual(rep["pages_resumed"], 1)
        self.assertEqual(self.store.pending_urls(10), [])
        job = rep["job_id"]
        self.assertEqual(self.store.get_checkpoint(job)["position"], rep["queries_planned"])
        again = self.runner(p).run(resume_job=job)                 # nothing left after the last checkpoint
        self.assertEqual(again["resumed_from"], rep["queries_planned"])
        self.assertEqual(again["categories_attempted"], {})


class TestLocaleFallback(TmpStore):
    def test_empty_local_answer_is_retried_in_default_locale_and_not_cached(self):
        class Throttled(FixtureSearch):
            unresponsive = [["google cse", "Suspended: too many requests"]]

            def search(self, query, limit=10, lang="en", page=0):
                self.queries.append((query, lang))
                return [SearchHit("https://www.uio.no/stipend", "Stipend")] if lang == "en" else []
        p = Throttled({})
        d = Discovery(self.store, Fetcher(Transport({"https://www.uio.no/stipend": OPP_HTML}), min_interval=0,
                                          sleep=lambda s: None), None, TODAY, [])
        rep = StrategyRunner(self.store, d, p, StrategyConfig(countries=["NO"], queries_per_country=2, results_per_page=2),
                             sleep=lambda s: None, today=TODAY).run()
        self.assertEqual(rep["locale_fallbacks"], 1)
        self.assertIn(("stipend Norge", "en"), p.queries)
        self.assertIsNone(self.store.last_query_run("fixture", "nothing here", 0))
        self.store.log_query("fixture", {"query": "empty", "language": "no"}, 0, [])
        self.assertIsNone(self.store.last_query_run("fixture", "empty", 0))     # empty answers are retried later


class TestRetrieval(TmpStore):
    URL = "https://apply.example.org/scholarships"

    def test_needs_browser_only_on_evidence(self):
        self.assertTrue(needs_browser(Response(self.URL, 200, "text/html", JS_SHELL), Page(self.URL, JS_SHELL))[0])
        self.assertFalse(needs_browser(Response(self.URL, 200, "text/html", RENDERED), Page(self.URL, RENDERED))[0])
        captcha = "<html><body>Please complete the CAPTCHA to continue</body></html>"
        ok, why = needs_browser(Response(self.URL, 200, "text/html", captcha), Page(self.URL, captcha))
        self.assertFalse(ok)
        self.assertIn("not bypassed", why)

    def test_browser_fallback_is_used_once_and_cached(self):
        b = FakeBrowser()
        t = Transport({self.URL: JS_SHELL})
        d = Discovery(self.store, Fetcher(t, min_interval=0, sleep=lambda s: None), None, TODAY, [], browser=b)
        res = DiscoveryResult(job_id=1)
        opp = d.ingest_url(1, self.URL, provider="x", provider_type="other", source_type=SourceType.SEARCH_RESULT,
                           countries_hint=[], result=res, discovered_via="test")
        self.assertIsNotNone(opp)
        self.assertEqual(res.retrieval, {"browser": 1})
        d.ingest_url(1, self.URL, provider="x", provider_type="other", source_type=SourceType.SEARCH_RESULT,
                     countries_hint=[], result=res, discovered_via="test")
        self.assertEqual(b.renders, 1)                               # unchanged HTTP body: cached rendering
        self.assertEqual(res.retrieval.get("browser-cache"), 1)
        d.close()
        self.assertTrue(b.closed)

    def test_without_a_browser_the_need_is_recorded(self):
        d = Discovery(self.store, Fetcher(Transport({self.URL: JS_SHELL}), min_interval=0, sleep=lambda s: None),
                      None, TODAY, [])
        res = DiscoveryResult(job_id=1)
        d.ingest_url(1, self.URL, provider="x", provider_type="other", source_type=SourceType.SEARCH_RESULT,
                     countries_hint=[], result=res, discovered_via="test")
        self.assertEqual(res.retrieval, {"http": 1})
        self.assertTrue(res.browser_needed)


class TestProviders(TmpStore):
    def test_trust_levels_and_review(self):
        mock.patch.dict(os.environ, {"SCHOLAR_DATA_DIR": self.tmp.name}).start()
        srcs = [Source(id="no-hkdir", name="HK-dir", url="https://hkdir.no/", provider="HK-dir",
                       official_domains=["hkdir.no"])]
        self.assertEqual(providers.classify_domain("https://www.hkdir.no/stipend", srcs)[0], "registry_official")
        self.assertEqual(providers.classify_domain("https://scholarships.gov.example/x", srcs)[0], "candidate")
        self.assertEqual(providers.classify_domain("https://www.studie.ac.jp/x", srcs)[0], "pattern_official")
        opp = Opportunity(id="o", title="Stipend", provider_name="x")
        self.assertEqual(providers.note_candidate(self.store, "https://fondet.example.no/a", "NO", opp, srcs), "candidate")
        self.assertIsNone(providers.note_candidate(self.store, "https://hkdir.no/a", "NO", opp, srcs))
        self.assertEqual([c["domain"] for c in providers.candidates(self.store)], ["fondet.example.no"])
        with self.assertRaises(ValueError):
            providers.review(self.store, "fondet.example.no", accept=True)          # who does it belong to?
        providers.review(self.store, "fondet.example.no", accept=True, provider="Fondet", note="checked imprint")
        from scholarship_agent.registry import load_sources
        self.assertEqual(providers.classify_domain("https://fondet.example.no/b", load_sources())[0], "reviewed_official")


class FakeLLM:
    name = "anthropic:fake"

    def __init__(self, fields):
        self.fields, self.calls = fields, []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        return {"fields": self.fields}


def rules_opp(html, url="https://www.example.no/stipend"):
    page = Page(url, html)
    opp, _ = extract_opportunity(page, provider_name="x", provider_type=ProviderType.OTHER, source_type=SourceType.OFFICIAL,
                                 country_hint=[], retrieved_at="2026-10-18T00:00:00+00:00", today=TODAY)
    return opp, page


class TestTargeted(TmpStore):
    def test_only_missing_fields_and_relevant_passages(self):
        html = ("<p>Om stipendet</p><p>Søknadsfrist: 15. mars 2027.</p><p>Stipendet er for masterstudenter.</p>"
                "<p>Stipendet utgjør 12 000 NOK per måned.</p><p>Spørsmål?</p><p>Les mer om oss.</p>"
                "<p>Kontakt oss på telefon.</p>")
        opp, page = rules_opp(html)
        p = ai_targeted.plan(opp, page.text, opp.info_url)
        self.assertNotIn("deadline_scholarship", p["fields"])          # the rules already read it
        self.assertNotIn("Kontakt oss", p["user"])                      # unrelated text is not sent
        self.assertLess(p["excerpt_chars"], p["page_chars"] + 1)
        self.assertIn("deadline", p["skipped"] if "deadline" not in p["groups"] else {"deadline": ""})

    def test_nothing_missing_means_no_request(self):
        opp = Opportunity(id="o", title="t", provider_name="p", info_url="https://x.example/a")
        with mock.patch.object(ai_targeted, "missing_fields", return_value={}):
            out, p = ai_targeted.ask(opp, "Any text", FakeLLM([]))
        self.assertIsNone(out)
        st = None
        llm = FakeLLM([])
        with mock.patch.object(ai_targeted, "missing_fields", return_value={}):
            st = enrich(opp, "Any text", llm, source_type=SourceType.OFFICIAL, retrieved_at="t", today=TODAY,
                        mode="targeted")
        self.assertEqual(llm.calls, [])
        self.assertIn("skipped", st)

    def test_cache_key_changes_with_content_schema_and_fields(self):
        llm = SimpleNamespace(provider="anthropic", model="claude-opus-5-5", effort="low")
        base = {"content_sha256": "a", "fields": ["study_levels"], "system": "s", "user": "u"}
        k = ai_targeted.cache_key(llm, "https://x.example/a?utm_source=y", base)
        self.assertEqual(k, ai_targeted.cache_key(llm, "https://x.example/a", base))     # URL normalised
        self.assertNotEqual(k, ai_targeted.cache_key(llm, "https://x.example/a", base | {"content_sha256": "b"}))
        self.assertNotEqual(k, ai_targeted.cache_key(llm, "https://x.example/a", base | {"fields": ["provider_name"]}))
        with mock.patch.object(ai_targeted, "SCHEMA_VERSION", "targeted-v2"):
            self.assertNotEqual(k, ai_targeted.cache_key(llm, "https://x.example/a", base))

    def test_ledger_records_why_and_cache_avoids_repeat(self):
        from tests.test_scholarship_round8 import Client, env, resp
        env(ANTHROPIC_API_KEY="sk-ant-api03-test", ANTHROPIC_ALLOW_PAID=1, ANTHROPIC_MAX_REQUESTS_PER_RUN=3,
            ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN=40000, ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN=40000,
            ANTHROPIC_MAX_ESTIMATED_COST_USD=1)
        html = "<p>Stipend for studenter.</p><p>Stipendet er åpent for masterstudenter og ph.d.-kandidater.</p>"
        opp, page = rules_opp(html)
        quote = "Stipendet er åpent for masterstudenter og ph.d.-kandidater."
        c = Client(resp([{"field": "study_levels", "value": ["master", "phd"], "quote": quote}]))
        llm = AnthropicLLM(client_factory=lambda: c, store=self.store)
        for _ in range(2):
            o = Opportunity.from_dict(opp.to_dict())
            enrich(o, page.text, llm, source_type=SourceType.OFFICIAL, retrieved_at="t", today=TODAY, mode="targeted")
        self.assertEqual(len(c.calls), 1)                                # the second time is a cache hit
        row = self.store.catalog.execute("SELECT purpose, fields, source_url FROM llm_usage WHERE status='ok'").fetchone()
        self.assertTrue(row["purpose"].startswith("targeted-v1:"))
        self.assertIn("study_levels", json.loads(row["fields"]))
        self.assertEqual(row["source_url"], opp.info_url)
        schema = c.calls[0]["output_config"]["format"]["schema"]
        enum = schema["properties"]["fields"]["items"]["properties"]["field"]["enum"]
        self.assertLess(len(enum), 31)                                   # only the requested fields

    def test_unchanged_page_is_not_sent_again(self):
        url = "https://www.example.no/stipend"
        llm = FakeLLM([])
        d = Discovery(self.store, Fetcher(Transport({url: OPP_HTML}), min_interval=0, sleep=lambda s: None), None,
                      TODAY, [], llm=llm)
        res = DiscoveryResult(job_id=1)
        for _ in range(2):
            d.ingest_url(1, url, provider="x", provider_type="other", source_type=SourceType.OFFICIAL,
                         countries_hint=[], result=res, discovered_via="test")
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(res.ai_skipped, {"page unchanged since last extraction": 1})


class TestFieldEvidence(TmpStore):
    def test_evidence_records_method_original_and_verdicts(self):
        url = "https://www.example.no/stipend"
        page_text = "Stipend\nSøknadsfrist: 15. mars 2027.\n€ 900, -."
        llm = FakeLLM([{"field": "deadline_scholarship", "value": "2027-03-15", "quote": "Søknadsfrist: 15. mars 2027."},
                       {"field": "stipend_amount", "value": 900, "quote": "€ 900, -."}])
        opp = Opportunity(id="o", title="Stipend", provider_name="x", info_url=url)
        st = enrich(opp, page_text, llm, source_type=SourceType.OFFICIAL, retrieved_at="t", today=TODAY, mode="full")
        dl = next(e for e in opp.evidence if e.field == "deadline.scholarship")
        self.assertEqual((dl.original, dl.method_version, dl.programme, dl.decision()), ("15. mars 2027", "extract-v2",
                                                                                         "Stipend", "accepted"))
        review = next(e for e in opp.evidence if e.verdict == "needs_review")
        self.assertEqual((review.field, review.decision()), ("stipend_amount", "needs_review"))
        self.assertEqual([r["field"] for r in st["needs_review"]], ["stipend_amount"])
        dl.status = VerificationStatus.CONFIRMED
        self.assertEqual(dl.decision(), "confirmed")
        self.assertEqual(Evidence.from_dict(dl.to_dict()).original, "15. mars 2027")   # stored and read back


if __name__ == "__main__":
    unittest.main()
