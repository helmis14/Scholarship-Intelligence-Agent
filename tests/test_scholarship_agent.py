"""Deterministic tests for the scholarship_agent package.

No network: every page comes from tests/fixtures/scholarship through a fake
transport, search goes through FixtureSearch, and every store lives in a
temporary directory.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent import cli, countries  # noqa: E402
from scholarship_agent.discovery import merge  # noqa: E402
from scholarship_agent.documents import brief, generate, to_docx  # noqa: E402
from scholarship_agent.eligibility import evaluate  # noqa: E402
from scholarship_agent.extract import Page, extract_deadlines, extract_funding, extract_opportunity, injection_flags  # noqa: E402
from scholarship_agent.funding import classify, estimate  # noqa: E402
from scholarship_agent.models import (DeadlineCertainty, Evidence, FundingComponent, Opportunity, Profile,  # noqa: E402
                                      ProviderType, SCHEMA_VERSION, SourceType, VerificationStatus)
from scholarship_agent.net import Fetcher, FetchError, Response  # noqa: E402
from scholarship_agent.normalize import dedup_key, normalize_url  # noqa: E402
from scholarship_agent.planning import requirements_matrix  # noqa: E402
from scholarship_agent.ranking import DISCLAIMER, load_weights, rank  # noqa: E402
from scholarship_agent.registry import Source, coverage, load_sources  # noqa: E402
from scholarship_agent.review import review  # noqa: E402
from scholarship_agent.search import FixtureSearch, SearchHit, generate_queries  # noqa: E402
from scholarship_agent.service import ScholarshipService  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from scholarship_agent.tracker import TransitionError, ensure_application, transition  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "scholarship"
TODAY = date(2026, 10, 17)
OFFICIAL = "https://www.example.ac.uk/scholarships/excellence"
RESEARCH = "https://www.example.ac.uk/scholarships/research"
LISTING = "https://www.example.ac.uk/scholarships"
AGG = "https://scholarhub.example.com/example-excellence"


class FakeTransport:
    def __init__(self, pages=None, robots=None):
        self.pages = {normalize_url(k): v for k, v in (pages or {}).items()}
        self.robots = robots or {}
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            host = url.rsplit("/robots.txt", 1)[0]
            body = self.robots.get(host)
            return Response(url, 200, "text/plain", body) if body is not None else Response(url, 404, "text/plain", "")
        v = self.pages.get(normalize_url(url))
        if v is None:
            return Response(url, 404, "text/html", "")
        if isinstance(v, list):  # sequence of responses for retry tests
            v = v.pop(0) if len(v) > 1 else v[0]
        if isinstance(v, Exception):
            raise v
        status, body = v if isinstance(v, tuple) else (200, v)
        return Response(url, status, "text/html; charset=utf-8", body)


def fx(name):
    return (FIX / name).read_text(encoding="utf-8")


def fetcher(pages, **kw):
    return Fetcher(FakeTransport(pages, kw.pop("robots", None)), min_interval=0, sleep=lambda s: None, **kw)


PROFILE = {
    "name": "Test Applicant", "email": "applicant@example.org", "citizenships": ["Indonesia"],
    "residence_country": "ID", "date_of_birth": "1996-05-01", "target_levels": ["master"],
    "preferred_countries": ["United Kingdom", "DE"], "disciplines": ["Public Health"],
    "research_interests": ["health policy"],
    "education": [{"degree": "bachelor", "field": "Public Health", "institution": "Universitas Contoh", "country": "ID",
                   "start": "2014", "end": "2018", "gpa": 3.5, "gpa_scale": 4.0, "completed": True,
                   "language_of_instruction": "English"}],
    "tests": [{"test": "IELTS", "score": 7.0, "date": "2026-03-01"}],
    "experience": [{"kind": "work", "title": "Health Programme Officer", "organization": "Contoh Health Foundation",
                    "start": "2019-01-01", "description": "Coordinated district vaccination outreach."}],
    "achievements": ["Provincial Youth Health Award 2020"],
    "documents_ready": ["Passport", "Academic transcripts"],
}

SOURCES = [Source(id="ex-uni", name="Example University funding", url=LISTING, provider="Example University",
                  provider_type="university", countries=["GB"], levels=["master", "phd"], kind="listing",
                  official_domains=["example.ac.uk"])]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.pages = {LISTING: fx("listing.html"), OFFICIAL: fx("official_page.html"), RESEARCH: fx("research.html"),
                      AGG: fx("aggregator.html")}
        self.svc = ScholarshipService(self.store, fetcher(self.pages), search=None, today=TODAY, sources=SOURCES)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def discover(self):
        return self.svc.discover(["GB"], ["master"], use_search=False)

    def official_opp(self):
        return next(o for o in self.store.list_opportunities() if "Excellence" in o.title)


# ---------------------------------------------------------------- profile

class TestProfile(Base):
    def test_create_normalises_countries_and_reports_gaps(self):
        out = self.svc.setup_profile({"name": "A", "citizenships": ["Indonesia", "ke"]})
        self.assertEqual(out["profile"]["citizenships"], ["ID", "KE"])
        self.assertIn("target study level", out["missing"])

    def test_update_merges_and_keeps_applications(self):
        self.svc.setup_profile(PROFILE)
        self.discover()
        ensure_application(self.store, "default", self.official_opp().id)
        self.svc.setup_profile({"target_intake": "2027-09"})
        p = self.store.get_profile()
        self.assertEqual(p.target_intake, "2027-09")
        self.assertEqual(p.citizenships, ["ID"])
        self.assertEqual(len(self.svc.track()["applications"]), 1)

    def test_rejects_unknown_field_and_country(self):
        with self.assertRaises(ValueError):
            self.svc.setup_profile({"salary": 1})
        with self.assertRaises(ValueError):
            self.svc.setup_profile({"citizenships": ["Atlantis"]})


# ---------------------------------------------------------------- discovery

class TestDiscovery(Base):
    def test_registry_listing_follows_links_and_persists(self):
        out = self.discover()
        titles = sorted(o.title for o in self.store.list_opportunities())
        self.assertEqual(len(titles), 2, out)
        self.assertTrue(any("Excellence" in t for t in titles))
        self.assertEqual(self.store.source_states()["ex-uni"]["consecutive_failures"], 0)
        self.assertIn("ex-uni", out["sources_used"])

    def test_duplicate_urls_merge(self):
        self.discover()
        self.svc.scrape([OFFICIAL + "?utm_source=x&utm_medium=y"])
        self.assertEqual(sum("Excellence" in o.title for o in self.store.list_opportunities()), 1)

    def test_aggregator_duplicate_merges_and_records_conflict(self):
        self.discover()
        self.svc.scrape([AGG])
        o = self.official_opp()
        self.assertEqual(sum("Excellence" in x.title for x in self.store.list_opportunities()), 1)
        agg_deadlines = [d for d in o.deadlines if d.source_url == AGG]
        self.assertTrue(all(d.certainty != DeadlineCertainty.CONFIRMED for d in agg_deadlines))

    def test_source_failure_is_recorded_not_fatal(self):
        self.pages[LISTING] = (500, "")
        svc = ScholarshipService(self.store, fetcher(self.pages, retries=2), search=None, today=TODAY, sources=SOURCES)
        out = svc.discover(["GB"], use_search=False)
        self.assertTrue(out["failures"])
        self.assertEqual(self.store.source_states()["ex-uni"]["consecutive_failures"], 1)
        svc.discover(["GB"], use_search=False)
        self.assertEqual(self.store.source_states()["ex-uni"]["consecutive_failures"], 2)

    def test_search_provider_is_pluggable(self):
        search = FixtureSearch({"*": [SearchHit(url=OFFICIAL, title="x")]})
        svc = ScholarshipService(self.store, fetcher(self.pages), search=search, today=TODAY, sources=[])
        out = svc.discover(["DE"], ["master"], nationality="ID")
        self.assertEqual(out["search_provider"], "fixture")
        self.assertTrue(any("Stipendium" in q for q in search.queries), search.queries)
        self.assertTrue(any("Indonesia" in q for q in search.queries))
        self.assertEqual(len(self.store.list_opportunities()), 1)

    def test_queries_cover_local_languages(self):
        qs = generate_queries(["JP", "ID"], ["phd"], [], None)
        self.assertTrue(any("奨学金" in q["query"] for q in qs))
        self.assertTrue(any("beasiswa" in q["query"] for q in qs))

    def test_coverage_reports_gaps_and_does_not_count_global_sources(self):
        srcs = SOURCES + [Source(id="g", name="global", url="https://agg.example.com", source_type="aggregator",
                                 countries=["*"])]
        cov = coverage(srcs)
        self.assertEqual(cov["countries_with_official_source"], 1)
        self.assertIn("FR", [g["code"] for g in cov["gaps"]])
        self.assertEqual(cov["global_sources"], ["g"])

    def test_seed_registry_loads_and_is_well_formed(self):
        srcs = load_sources(local=Path(self.tmp.name) / "none.json")
        self.assertGreater(len(srcs), 30)
        self.assertEqual(len({s.id for s in srcs}), len(srcs))
        for s in srcs:
            self.assertTrue(s.url.startswith("https://"), s.id)
            for c in s.countries:
                self.assertTrue(c.startswith("*") or c in countries.COUNTRIES, (s.id, c))


# ---------------------------------------------------------------- extraction, normalisation, provenance

class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.opp, self.flags = extract_opportunity(
            Page(OFFICIAL, fx("official_page.html")), provider_name="Example University",
            provider_type=ProviderType.UNIVERSITY, source_type=SourceType.OFFICIAL, country_hint=["GB"],
            retrieved_at="2026-10-17T00:00:00+00:00", today=TODAY)

    def test_fields(self):
        o = self.opp
        self.assertEqual(o.nationality.mode, "include")
        self.assertEqual(o.nationality.countries, ["ID", "KE", "VN"])
        self.assertEqual((o.min_gpa, o.gpa_scale, o.max_age, o.min_work_years), (3.0, 4.0, 35, 2.0))
        self.assertEqual({r.test: r.minimum for r in o.language_requirements}, {"IELTS": 6.5, "TOEFL_IBT": 90})
        self.assertEqual(o.study_levels, ["master"])
        self.assertTrue(o.moi_policy)
        self.assertEqual(o.application_url, "https://apply.example.ac.uk/portal")
        essay = next(d for d in o.required_documents if d.name == "Scholarship essay")
        self.assertEqual(essay.word_limit, 500)
        self.assertIn("home community", essay.prompt)
        self.assertEqual(next(d for d in o.required_documents if d.name == "Motivation letter").word_limit, 800)
        self.assertIsNone(next(d for d in o.required_documents if d.name == "CV").word_limit)

    def test_multiple_deadlines_and_history(self):
        got = {(str(d.kind), d.date, str(d.certainty)) for d in self.opp.deadlines}
        self.assertIn(("scholarship", "2027-01-15", "confirmed"), got)
        self.assertIn(("admission", "2026-12-01", "confirmed"), got)
        # round 28: "The previous round closed on 15 January 2025" belongs to an earlier cycle
        self.assertIn(("reference", "2025-01-15", "historical"), got)
        d = next(d for d in self.opp.deadlines if d.date == "2027-01-15")
        self.assertEqual((d.time, d.timezone, d.cycle), ("23:59", "CET", "2026/2027"))

    def test_approximate_and_ambiguous_dates_never_become_precise(self):
        ds = extract_deadlines("The deadline is usually in early November. Closing date: 03/04/2027.", OFFICIAL, TODAY)
        approx = [d for d in ds if d.certainty == DeadlineCertainty.EXPECTED]
        self.assertTrue(approx and all(d.date is None for d in approx))
        amb = [d for d in ds if d.certainty == DeadlineCertainty.UNKNOWN]
        self.assertTrue(amb and amb[0].date is None)

    def test_every_field_has_provenance(self):
        fields = {e.field for e in self.opp.evidence}
        for f in ("title", "nationality", "min_gpa", "max_age", "language.IELTS", "funding.stipend",
                  "deadline.scholarship", "document.Scholarship essay"):
            self.assertIn(f, fields)
        for e in self.opp.evidence:
            self.assertEqual(e.source_url, OFFICIAL)
            self.assertTrue(e.retrieved_at)
            self.assertEqual(e.status, VerificationStatus.EXTRACTED)

    def test_prompt_injection_is_flagged_and_inert(self):
        self.assertTrue(self.flags)
        dumped = json.dumps(self.opp.to_dict())
        self.assertNotIn("attacker@example.com", dumped)
        self.assertTrue(any("untrusted" in u for u in self.opp.uncertainties))
        self.assertEqual(injection_flags("Normal scholarship text about applications."), [])

    def test_url_normalisation_and_dedup_key(self):
        self.assertEqual(normalize_url("HTTP://WWW.Example.ac.uk:443/a/b/?utm_source=x&b=2&a=1#frag"),
                         "https://example.ac.uk/a/b?a=1&b=2")
        self.assertEqual(normalize_url("https://x.org/index.html"), "https://x.org/")
        self.assertEqual(dedup_key("Example Scholarship 2026/2027", "Example Univ"),
                         dedup_key("Example scholarship 2027/2028", "Example Univ"))

    def test_funding_negation_and_amounts(self):
        comps, _ = extract_funding("Tuition fees are not covered. A stipend of USD 2,000 per month is paid.")
        by = {c.kind: c for c in comps}
        self.assertFalse(by["tuition"].covered)
        self.assertEqual((by["stipend"].amount, by["stipend"].currency, by["stipend"].period), (2000.0, "USD", "month"))

    def test_non_official_page_cannot_confirm_a_deadline(self):
        o, _ = extract_opportunity(Page(AGG, fx("aggregator.html")), provider_name="agg", provider_type=ProviderType.AGGREGATOR,
                                   source_type=SourceType.AGGREGATOR, country_hint=[], retrieved_at="t", today=TODAY)
        self.assertTrue(o.deadlines)
        self.assertTrue(all(d.certainty == DeadlineCertainty.EXPECTED for d in o.deadlines))


# ---------------------------------------------------------------- verification

class TestVerification(Base):
    def test_confirms_against_official_page(self):
        self.discover()
        r = self.svc.verify(self.official_opp().id)
        self.assertEqual(r["status"], "officially_confirmed", r)
        o = self.official_opp()
        self.assertTrue(o.last_verified_at)
        self.assertTrue(all(e.status == VerificationStatus.CONFIRMED for e in o.evidence if e.source_url == OFFICIAL))
        self.assertEqual(len(self.store.verifications(o.id)), 1)

    def test_changed_official_page_is_conflicting_not_overwritten(self):
        self.discover()
        self.pages[OFFICIAL] = fx("official_page.html").replace("IELTS overall score of 6.5", "IELTS overall score of 7.0")
        svc = ScholarshipService(self.store, fetcher(self.pages), search=None, today=TODAY, sources=SOURCES)
        r = svc.verify(self.official_opp().id)
        self.assertEqual(r["status"], "conflicting")
        self.assertTrue(any("IELTS" in c for c in r["conflicts"]))

    def test_unavailable_source(self):
        self.discover()
        self.pages[OFFICIAL] = (404, "")
        svc = ScholarshipService(self.store, fetcher(self.pages), search=None, today=TODAY, sources=SOURCES)
        self.assertEqual(svc.verify(self.official_opp().id)["status"], "source_unavailable")

    def test_aggregator_only_record_is_not_confirmed(self):
        self.svc.scrape([AGG])
        o = self.store.list_opportunities()[0]
        r = self.svc.verify(o.id)
        self.assertEqual(r["status"], "extracted_unverified")
        self.assertIn("no official source", r["notes"][0])

    def test_past_deadlines_move_to_history_on_refresh(self):
        self.discover()
        svc = ScholarshipService(self.store, fetcher(self.pages), search=None, today=date(2027, 2, 1), sources=SOURCES)
        svc.verify(self.official_opp().id)
        o = self.official_opp()
        self.assertTrue(all(d.certainty == DeadlineCertainty.HISTORICAL for d in o.deadlines if d.date))


# ---------------------------------------------------------------- eligibility, funding, ranking

def _opp(**kw):
    base = dict(id="sch_x", title="X Scholarship", provider_name="X", study_levels=["master"])
    base.update(kw)
    return Opportunity.from_dict(base)


def _confirmed_ev(field):
    return Evidence(field=field, value=None, source_url=OFFICIAL, status=VerificationStatus.CONFIRMED).to_dict()


class TestEligibility(Base):
    def setUp(self):
        super().setUp()
        self.svc.setup_profile(PROFILE)
        self.p = self.store.get_profile()

    def test_explained_decision_on_real_extraction(self):
        self.discover()
        self.svc.verify(self.official_opp().id)
        m = self.svc.match(self.official_opp().id)["eligibility"]
        self.assertIn(m["decision"], ("ELIGIBLE", "LIKELY_ELIGIBLE"), m)
        for k in ("supporting_requirements", "applicant_facts_used", "matches", "mismatches", "missing_information",
                  "uncertainties", "next_action"):
            self.assertIn(k, m)
        self.assertIn("nationality", m["matches"])
        self.assertIn("language.IELTS", m["matches"])

    def test_confirmed_hard_mismatch_is_ineligible(self):
        o = _opp(nationality={"mode": "include", "countries": ["KE"]}, evidence=[_confirmed_ev("nationality")])
        self.assertEqual(evaluate(o, self.p, TODAY)["decision"], "INELIGIBLE")

    def test_unverified_mismatch_is_only_uncertain(self):
        o = _opp(nationality={"mode": "include", "countries": ["KE"]})
        self.assertEqual(evaluate(o, self.p, TODAY)["decision"], "UNCERTAIN")

    def test_missing_applicant_facts(self):
        o = _opp(nationality={"mode": "any"})
        self.assertEqual(evaluate(o, Profile(), TODAY)["decision"], "INSUFFICIENT_INFORMATION")

    def test_absent_language_requirement_is_not_a_waiver(self):
        e = evaluate(_opp(nationality={"mode": "any"}), self.p, TODAY)
        lang = next(c for c in e["checks"] if c["name"] == "language")
        self.assertEqual(lang["outcome"], "unknown")
        self.assertIn("not a waiver", lang["note"])

    def test_other_test_not_assumed_equivalent_and_moi_not_assumed(self):
        p = Profile.from_dict(PROFILE | {"citizenships": ["ID"], "tests": [{"test": "TOEFL_IBT", "score": 100}]})
        o = _opp(nationality={"mode": "any"}, language_requirements=[{"test": "IELTS", "minimum": 6.5}],
                 moi_policy="Applicants taught in English may submit an MOI letter")
        c = next(c for c in evaluate(o, p, TODAY)["checks"] if c["name"] == "language.IELTS")
        self.assertEqual(c["outcome"], "unknown")
        self.assertIn("equivalence is not assumed", c["note"])
        self.assertIn("confirm it applies", c["note"])

    def test_language_score_below_minimum_fails(self):
        o = _opp(nationality={"mode": "any"}, language_requirements=[{"test": "IELTS", "minimum": 7.5}])
        c = next(c for c in evaluate(o, self.p, TODAY)["checks"] if c["name"] == "language.IELTS")
        self.assertEqual(c["outcome"], "fail")

    def test_age_and_inferred_facts(self):
        p = Profile.from_dict(PROFILE | {"citizenships": ["ID"], "inferred": {"gpa_rank": {"value": "top 5%", "confirmed": False}}})
        e = evaluate(_opp(max_age=25, nationality={"mode": "any"}), p, TODAY)
        self.assertEqual(next(c for c in e["checks"] if c["name"] == "age")["outcome"], "fail")
        self.assertTrue(any("inferred" in u for u in e["uncertainties"]))


class TestFunding(unittest.TestCase):
    def cls(self, comps):
        return classify(_opp(funding=[FundingComponent(**c).to_dict() for c in comps]))["classification"]

    def test_classifications(self):
        self.assertEqual(self.cls([{"kind": "tuition", "full": True}, {"kind": "stipend"}]), "fully_funded")
        self.assertEqual(self.cls([{"kind": "tuition", "full": True}]), "tuition_funded")
        self.assertEqual(self.cls([{"kind": "tuition", "note": "fee waiver mentioned"}]), "fee_waiver")
        self.assertEqual(self.cls([{"kind": "stipend"}]), "stipend_only")
        # round 27: tuition of unstated extent is neither full nor partial
        self.assertEqual(self.cls([{"kind": "tuition"}, {"kind": "stipend"}]), "funding_unclear")
        self.assertEqual(self.cls([{"kind": "tuition", "full": False}, {"kind": "stipend"}]), "partially_funded")
        self.assertEqual(self.cls([{"kind": "assistantship"}]), "assistantship")
        self.assertEqual(self.cls([]), "funding_unclear")
        self.assertEqual(self.cls([{"kind": "tuition", "covered": False}, {"kind": "stipend"}]), "stipend_only")

    def test_estimate_is_explicit_about_currency(self):
        o = _opp(funding=[{"kind": "tuition", "full": True}, {"kind": "stipend", "amount": 1000, "currency": "EUR",
                                                             "period": "month"}])
        e = estimate(o, tuition_per_year=20000, living_per_month=1200, currency="EUR")
        self.assertEqual((e["stipend_per_year"], e["living_gap_per_year"], e["tuition_gap_per_year"]), (12000, 2400, 0))
        e2 = estimate(o, living_per_month=1200, currency="USD")
        self.assertIsNone(e2["stipend_per_year"])
        self.assertIn("exchange rate EUR->USD", e2["missing"])
        e3 = estimate(o, living_per_month=1200, currency="USD", fx={"EUR->USD": 1.1})
        self.assertAlmostEqual(e3["stipend_per_year"], 13200)


class TestRanking(Base):
    def setUp(self):
        super().setUp()
        self.svc.setup_profile(PROFILE)
        self.discover()

    def test_explainable_and_separates_hard_failures(self):
        bad = _opp(id="sch_bad", title="Kenya only", nationality={"mode": "include", "countries": ["KE"]},
                   evidence=[_confirmed_ev("nationality")])
        r = rank(self.store.list_opportunities() + [bad], self.store.get_profile(), today=TODAY)
        self.assertEqual(r["disclaimer"], DISCLAIMER)
        self.assertIn("sch_bad", [x["opportunity_id"] for x in r["excluded"]])
        top = r["ranked"][0]
        self.assertAlmostEqual(sum(c["contribution"] for c in top["components"].values()), top["score"], delta=0.6)
        self.assertTrue(all(c["reason"] for c in top["components"].values()))

    def test_weights_override_and_validation(self):
        w = load_weights({"funding": 1.0})
        self.assertAlmostEqual(sum(w.values()), 1.0)
        with self.assertRaises(ValueError):
            load_weights({"luck": 1})


# ---------------------------------------------------------------- documents, review, planning

class TestDocuments(Base):
    def setUp(self):
        super().setUp()
        self.svc.setup_profile(PROFILE)
        self.discover()
        self.o, self.p = self.official_opp(), self.store.get_profile()

    def test_cv_uses_only_profile_facts(self):
        cv = generate("scholarship_cv", self.o, self.p)["content"]
        self.assertIn("Universitas Contoh", cv)
        self.assertIn("GPA 3.5/4.0", cv)
        rv = review(cv, brief("scholarship_cv", self.o, self.p), self.p)
        self.assertFalse([i for i in rv["issues"] if i["type"] == "unsupported_claim"], rv)

    def test_essay_brief_carries_prompt_limit_and_rules(self):
        b = brief("essay", self.o, self.p)
        self.assertEqual(b["word_limit"], 500)
        self.assertIn("home community", b["prompt"])
        self.assertIn("community", b["required_topics"])
        self.assertTrue(any("untrusted" in r for r in b["rules"]))
        self.assertNotIn("gpa_rank", json.dumps(b["FACT_PACK"]["education"]))

    def test_skeleton_never_invents(self):
        g = generate("essay", self.o, self.p)
        self.assertIn("[YOU WRITE:", g["content"])
        self.assertFalse(review(g["content"], g["brief"], self.p)["passed"])  # placeholders block readiness

    def test_review_flags_limits_unsupported_claims_and_inconsistency(self):
        b = brief("essay", self.o, self.p)
        text = ("My GPA of 3.9 at Universitas Contoh and my work at the Global Vaccine Alliance shaped my home community "
                "leadership. I published three papers. ") * 40
        rv = review(text, b, self.p, other_docs={"CV": "GPA of 3.5"})
        types = {i["type"] for i in rv["issues"]}
        self.assertIn("word_limit", types)
        self.assertIn("unsupported_claim", types)
        self.assertIn("consistency", types)
        self.assertIn("missing_evidence", types)
        self.assertFalse(rv["passed"])

    def test_clean_draft_passes(self):
        b = brief("essay", self.o, self.p)
        text = ("Studying public health will let me serve my home community. As Health Programme Officer at Contoh "
                "Health Foundation I coordinated vaccination outreach, which taught me leadership and how studies "
                "translate into benefit and experience for families.")
        rv = review(text, b, self.p)
        self.assertTrue(rv["passed"], rv)

    def test_recommender_pack_is_not_a_letter(self):
        t = generate("recommender_brief", self.o, self.p)["content"]
        self.assertIn("must be written and submitted by you", t)

    def test_prepare_saves_versions_and_advances_status(self):
        out = self.svc.prepare(self.o.id)
        kinds = [d["kind"] for d in out["documents"]]
        self.assertIn("scholarship_cv", kinds)
        self.assertIn("essay", kinds)
        self.svc.prepare(self.o.id, ["scholarship_cv"])
        aid = out["application_id"]
        rows = self.store.q("SELECT current_version FROM documents WHERE application_id=? AND kind='scholarship_cv'", (aid,))
        self.assertEqual(rows[0]["current_version"], 2)
        self.assertEqual(self.svc.track(self.o.id)["application"]["status"], "preparing_documents")

    def test_docx_export_is_valid_zip(self):
        import zipfile, io
        data = to_docx("# Title\n\n- **bold** item\nplain & <text>")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn("word/document.xml", z.namelist())
            self.assertIn("plain &amp; &lt;text&gt;", z.read("word/document.xml").decode())


class TestPlanning(Base):
    def setUp(self):
        super().setUp()
        self.svc.setup_profile(PROFILE)
        self.discover()

    def test_matrix_and_timeline(self):
        o, p = self.official_opp(), self.store.get_profile()
        m = requirements_matrix(o, p, today=TODAY)
        names = {r["name"]: r for r in m["matrix"]}
        self.assertEqual(names["Passport"]["readiness"], "held")
        self.assertEqual(names["Language test certificate"]["readiness"], "held")
        self.assertIn("Recommender briefing pack", names)
        self.assertEqual(names["Recommendation letters"]["deadline"], "2027-01-15")
        self.assertEqual(names["MOI letter"]["mandatory"], "optional")
        order = [s["task"] for s in m["timeline"]]
        self.assertLess(order.index("Recommender briefing pack"), order.index("Recommendation letters"))
        self.assertTrue(any("visa" in n for n in m["notes"]))

    def test_plan_persists_checklist_and_keeps_done_items(self):
        o = self.official_opp()
        self.svc.plan(o.id)
        self.svc.track(o.id, item="CV", item_status="done")
        self.svc.plan(o.id)
        cl = {i["name"]: i["status"] for i in self.svc.track(o.id)["checklist"]}
        self.assertEqual(cl["CV"], "done")


# ---------------------------------------------------------------- tracking, deadlines, persistence

class TestTracking(Base):
    def setUp(self):
        super().setUp()
        self.svc.setup_profile(PROFILE)
        self.discover()
        self.o = self.official_opp()

    def test_valid_and_invalid_transitions(self):
        app = ensure_application(self.store, "default", self.o.id)
        with self.assertRaises(TransitionError):
            transition(self.store, app["id"], "accepted")
        for s in ("shortlisted", "preparing_documents", "ready_for_review", "submitted", "assessment_or_interview"):
            app = transition(self.store, app["id"], s)
        self.svc.outcome(self.o.id, "accepted", lessons="interview focused on community impact")
        with self.assertRaises(TransitionError):
            transition(self.store, app["id"], "withdrawn")
        hist = [h["to_status"] for h in self.svc.track(self.o.id)["application"]["history"]]
        self.assertEqual(hist[0], "discovered")
        self.assertEqual(hist[-1], "accepted")
        self.assertEqual(self.svc.report()["lessons"][0]["result"], "accepted")

    def test_deadlines_grouped_by_certainty(self):
        self.svc.scrape([RESEARCH])
        dl = self.svc.deadlines(120)
        self.assertEqual(dl["confirmed"][0]["date"], "2026-12-01")
        self.assertTrue(any(r["approximate"] and r["date"] is None for r in dl["expected_unconfirmed"]))
        self.assertTrue(any(r["date"] == "2025-01-15" for r in dl["historical_recent"]))

    def test_reminders_and_ics(self):
        self.svc.plan(self.o.id)
        from scholarship_agent.tracker import ICSNotifier
        path = Path(self.tmp.name) / "r.ics"
        out = self.svc.reminders(notifier=ICSNotifier(path))
        self.assertTrue(out["reminders"])
        self.assertIn("BEGIN:VEVENT", path.read_text())
        n = len(self.store.q("SELECT * FROM reminders"))
        self.svc.reminders()
        self.assertEqual(len(self.store.q("SELECT * FROM reminders")), n)  # idempotent

    def test_persistence_and_recovery(self):
        self.svc.plan(self.o.id)
        self.store.close()
        s2 = Store(Path(self.tmp.name))
        self.assertEqual(s2.get_profile().name, "Test Applicant")
        self.assertIsNotNone(s2.get_opportunity(self.o.id))
        from scholarship_agent.store import CATALOG_MIGRATIONS
        self.assertEqual(s2.catalog.execute("SELECT MAX(version) FROM schema_version").fetchone()[0],
                         len(CATALOG_MIGRATIONS))
        self.store = s2

    def test_changed_deadline_is_kept_in_history(self):
        o = self.store.get_opportunity(self.o.id)
        o.deadlines[0].date = "2027-01-20"
        self.store.save_opportunity(o, "k", "u")
        self.assertTrue(any(h["date"] == "2027-01-15" for h in self.store.deadline_history(o.id)))

    def test_pre_submission_review_blocks_until_ready(self):
        r = self.svc.pre_submission_review(self.o.id)
        self.assertFalse(r["ready"])
        self.assertTrue(any("not verified" in b for b in r["blockers"]))
        self.assertIn("never submits", r["reminder"])


# ---------------------------------------------------------------- network politeness

class TestFetcher(unittest.TestCase):
    def test_retries_then_succeeds(self):
        sleeps = []
        t = FakeTransport({OFFICIAL: [(503, ""), (200, "<p>ok</p>")]})
        f = Fetcher(t, min_interval=0, sleep=sleeps.append, retries=3, backoff=1)
        self.assertEqual(f.get(OFFICIAL).text, "<p>ok</p>")
        self.assertIn(1, sleeps)

    def test_403_is_not_bypassed(self):
        t = FakeTransport({OFFICIAL: (403, "")})
        f = Fetcher(t, min_interval=0, sleep=lambda s: None)
        with self.assertRaises(FetchError) as cm:
            f.get(OFFICIAL)
        self.assertIn("not bypassed", cm.exception.reason)
        self.assertEqual(sum(1 for c in t.calls if c == OFFICIAL), 1)

    def test_robots_disallow_blocks(self):
        t = FakeTransport({OFFICIAL: "<p>x</p>"}, robots={"https://www.example.ac.uk": "User-agent: *\nDisallow: /scholarships/"})
        f = Fetcher(t, min_interval=0, sleep=lambda s: None)
        with self.assertRaises(FetchError):
            f.get(OFFICIAL)
        self.assertNotIn(OFFICIAL, t.calls)

    def test_rate_limit_waits_between_same_host_requests(self):
        sleeps = []
        t = FakeTransport({OFFICIAL: "<p>x</p>", RESEARCH: "<p>y</p>"})
        f = Fetcher(t, min_interval=5, sleep=sleeps.append)
        f.clock = lambda: 100.0
        f.get(OFFICIAL)
        f.get(RESEARCH)
        self.assertTrue(sleeps and max(sleeps) == 5)

    def test_429_backs_off_and_slows_the_host(self):
        sleeps = []
        t = FakeTransport({OFFICIAL: [(429, ""), (200, "<p>ok</p>")]})
        f = Fetcher(t, min_interval=0, sleep=sleeps.append)
        self.assertEqual(f.get(OFFICIAL).text, "<p>ok</p>")
        self.assertGreaterEqual(max(sleeps), 15)
        self.assertEqual(f.host_interval["www.example.ac.uk"], 15.0)

    def test_rejects_non_http(self):
        with self.assertRaises(FetchError):
            Fetcher(FakeTransport()).get("file:///etc/passwd")


# ---------------------------------------------------------------- privacy, structured output, API boundary

class TestPrivacyAndBoundary(Base):
    def test_private_store_permissions(self):
        mode = stat.S_IMODE(os.stat(Path(self.tmp.name) / "private" / "private.db").st_mode)
        self.assertEqual(mode & 0o077, 0)

    def test_export_and_delete(self):
        self.svc.setup_profile(PROFILE)
        self.discover()
        self.svc.prepare(self.official_opp().id, ["scholarship_cv"])
        exp = self.svc.export_private_data()
        self.assertEqual(exp["profile"]["name"], "Test Applicant")
        self.assertTrue(exp["documents"])
        counts = self.svc.delete_private_data()["deleted"]
        self.assertEqual(counts["profiles"], 1)
        self.assertIsNone(self.store.get_profile())
        self.assertEqual(self.store.q("SELECT COUNT(*) c FROM document_versions")[0]["c"], 0)
        self.assertTrue(self.store.list_opportunities())  # public catalog survives

    def test_gitignore_keeps_data_out_of_git(self):
        self.assertIn("data/", (REPO / ".gitignore").read_text().splitlines())

    def test_no_secrets_in_outputs(self):
        with mock.patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "sk-test-secret-123"}):
            from scholarship_agent.search import BraveSearch
            svc = ScholarshipService(self.store, fetcher(self.pages), search=BraveSearch(), today=TODAY, sources=SOURCES)
            self.assertNotIn("sk-test-secret-123", json.dumps(svc.sources_status(), default=str))

    def test_structured_outputs_have_schema_version(self):
        self.svc.setup_profile(PROFILE)
        self.discover()
        oid = self.official_opp().id
        calls = [lambda: self.svc.get_profile(), lambda: self.svc.match(oid), lambda: self.svc.rank(),
                 lambda: self.svc.plan(oid), lambda: self.svc.documents_audit(oid), lambda: self.svc.deadlines(),
                 lambda: self.svc.report(), lambda: self.svc.sources_status(), lambda: self.svc.get_opportunity(oid),
                 lambda: self.svc.funding_estimate(oid), lambda: self.svc.search_opportunities(country="GB"),
                 lambda: self.svc.brief(oid, "essay"), lambda: self.svc.pre_submission_review(oid)]
        for c in calls:
            out = c()
            self.assertEqual(out["schema_version"], SCHEMA_VERSION)
            json.dumps(out)  # serialisable without default=

    def test_cli_round_trip_and_errors(self):
        buf = StringIO()
        with mock.patch("sys.stdout", buf):
            rc = cli.main(["setup", "--set", 'citizenships=["ID"]', "--set", 'target_levels=["master"]'], svc=self.svc)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["profile"]["citizenships"], ["ID"])
        buf = StringIO()
        with mock.patch("sys.stdout", buf):
            rc = cli.main(["match", "does-not-exist"], svc=self.svc)
        self.assertEqual(rc, 1)
        self.assertIn("error", json.loads(buf.getvalue()))
        buf = StringIO()
        with mock.patch("sys.stdout", buf):
            self.assertEqual(cli.main(["delete-data"], svc=self.svc), 1)


class TestMerge(unittest.TestCase):
    def test_conflicting_language_minimum_is_kept(self):
        a = _opp(language_requirements=[{"test": "IELTS", "minimum": 6.5}])
        b = _opp(language_requirements=[{"test": "IELTS", "minimum": 7.0}], info_url=AGG)
        m = merge(a, b)
        self.assertEqual(m.verification_status, VerificationStatus.CONFLICTING)
        self.assertEqual(m.language_requirements[0].minimum, 6.5)
        self.assertTrue(m.conflicts)


if __name__ == "__main__":
    unittest.main()
