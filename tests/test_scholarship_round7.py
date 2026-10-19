"""Round 7: Claude-only AI path. New Claude extraction fields (provider, cycle, fields of study, residency, funding
components, page conflicts) stay quote-checked and unconfirmed; model deadlines are never "confirmed"; an
institution's date inside a quote is rejected; funding classification says whether its evidence is confirmed.
Every Claude call is mocked."""

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

from scholarship_agent.ai_extract import FIELDS, default_llm, enrich, validate  # noqa: E402
from scholarship_agent.anthropic_llm import AnthropicLLM  # noqa: E402
from scholarship_agent.cli import build_parser  # noqa: E402
from scholarship_agent.funding import classify  # noqa: E402
from scholarship_agent.models import (DeadlineCertainty, FundingComponent, Opportunity, SourceType,  # noqa: E402
                                      VerificationStatus)
from scholarship_agent.net import Fetcher  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402
from scholarship_agent.verify import verify  # noqa: E402
from tests.test_scholarship_strategy import Transport  # noqa: E402

TODAY = date(2026, 10, 17)
URL = "https://www.example.gov/scholarship"
TEXT = ("The Example Foundation Scholarship 2027/2028 is funded by the Example Foundation. "
        "Applicants must be citizens of Ghana or Kenya and must reside in Ghana. "
        "Eligible fields: Public Health, Agricultural Science. "
        "The scholarship provides a monthly living allowance, free accommodation in a university residence and "
        "health insurance. Travel costs are not covered. "
        "Closing date for student application is 31-10-2026 and closing date for institute verification is 15-11-2026. "
        "Funding is provided for 24 months. The deadline is 30 November 2026 on another part of this page.")


class FakeLLM:
    name = "anthropic:claude-opus-5-5"

    def __init__(self, fields):
        self.fields = fields

    def complete_json(self, system, user):
        return {"fields": self.fields}


def run(fields, opp=None):
    opp = opp or Opportunity(id="x", title="Example Foundation Scholarship", provider_name="example.gov", info_url=URL)
    st = enrich(opp, TEXT, FakeLLM(fields), source_type=SourceType.OFFICIAL, retrieved_at="2026-10-17T00:00:00Z",
                today=TODAY)
    return opp, st


class TestNewClaudeFields(unittest.TestCase):
    def test_new_fields_are_in_the_structured_schema(self):
        for f in ("provider_name", "academic_cycle", "fields_of_study", "covers_accommodation", "covers_travel",
                  "covers_health_insurance", "covers_living_allowance", "page_conflicts", "residency_required"):
            self.assertIn(f, FIELDS)

    def test_supported_values_are_recorded_as_unverified_evidence(self):
        opp, st = run([
            {"field": "provider_name", "value": "Example Foundation", "quote": "is funded by the Example Foundation."},
            {"field": "academic_cycle", "value": "2027/2028", "quote": "The Example Foundation Scholarship 2027/2028"},
            {"field": "fields_of_study", "value": ["Public Health", "Agricultural Science"],
             "quote": "Eligible fields: Public Health, Agricultural Science."},
            {"field": "residency_required", "value": ["Ghana"], "quote": "must reside in Ghana"},
            {"field": "funding_duration_months", "value": 24, "quote": "Funding is provided for 24 months."},
            {"field": "covers_accommodation", "value": True,
             "quote": "free accommodation in a university residence and health insurance"},
            {"field": "covers_health_insurance", "value": True,
             "quote": "free accommodation in a university residence and health insurance"},
        ])
        self.assertEqual(st["rejected"], [])
        self.assertEqual((opp.institution, opp.current_cycle), ("Example Foundation", "2027/2028"))
        self.assertEqual(opp.disciplines, ["Public Health", "Agricultural Science"])
        self.assertEqual(opp.nationality.residency_required, ["GH"])
        self.assertEqual(opp.funding_duration, "24 months")
        self.assertEqual({c.kind for c in opp.funding}, {"accommodation", "insurance"})
        self.assertTrue(all(e.status == VerificationStatus.EXTRACTED and e.method == "anthropic" for e in opp.evidence))

    def test_unsupported_claims_are_rejected(self):
        _, st = run([
            {"field": "covers_travel", "value": True, "quote": "Travel costs are not covered."},
            {"field": "covers_travel", "value": False, "quote": "Travel costs are not covered."},
            {"field": "provider_name", "value": "Gates Foundation", "quote": "is funded by the Example Foundation."},
            {"field": "academic_cycle", "value": "2028/2029", "quote": "The Example Foundation Scholarship 2027/2028"},
            {"field": "fields_of_study", "value": ["Engineering"], "quote": "Eligible fields: Public Health"},
            {"field": "covers_living_allowance", "value": True, "quote": "Funding is provided for 24 months."},
        ])
        reasons = [r["reason"] for r in st["rejected"]]
        self.assertEqual(st["accepted"], [])
        for want in ("quote says the benefit is not provided", "only stated benefits are recorded",
                     "provider name not in quote", "cycle not stated in quote", "field of study not on page",
                     "quote does not mention this benefit"):
            self.assertIn(want, reasons)

    def test_institutional_date_in_quote_is_not_an_applicant_deadline(self):
        q = ("Closing date for student application is 31-10-2026 and closing date for institute verification is "
             "15-11-2026.")
        self.assertIsNone(validate("deadline_scholarship", "2026-10-31", q, TEXT))
        self.assertEqual(validate("deadline_scholarship", "2026-11-15", q, TEXT),
                         "date belongs to institutions, officials or an event, not the applicant")

    def test_model_deadline_is_never_confirmed_by_extraction(self):
        opp, _ = run([{"field": "deadline_scholarship", "value": "2026-10-31",
                       "quote": "Closing date for student application is 31-10-2026"}])
        self.assertEqual([(d.date, d.certainty) for d in opp.deadlines], [("2026-10-31", DeadlineCertainty.EXPECTED)])

    def test_page_conflicts_are_reported_not_resolved(self):
        opp, st = run([{"field": "page_conflicts", "value": "two different deadlines (31-10-2026 and 30 November 2026)",
                        "quote": "The deadline is 30 November 2026 on another part of this page."}])
        self.assertEqual(st.get("conflicts_noted"), 1)
        self.assertTrue(any("possible conflict" in u for u in opp.uncertainties))
        self.assertEqual(opp.deadlines, [])
        self.assertFalse(any(e.field == "page_conflicts" for e in opp.evidence))


class TestFundingEvidence(unittest.TestCase):
    def test_full_funding_from_model_readings_is_flagged_and_unconfirmed(self):
        opp = Opportunity(id="x", title="X", provider_name="p")
        opp.funding = [FundingComponent(kind="tuition", covered=True, full=True, note="ai-assisted"),
                       FundingComponent(kind="living_allowance", covered=True, note="ai-assisted")]
        c = classify(opp)
        self.assertEqual(c["classification"], "fully_funded")
        self.assertFalse(c["confirmed_by_official_source"])
        self.assertTrue(any("model reading" in r for r in c["reasons"]))

    def test_unknown_funding_stays_unclear(self):
        c = classify(Opportunity(id="x", title="X", provider_name="p"))
        self.assertEqual((c["classification"], c["confirmed_by_official_source"]), ("funding_unclear", False))


class TestVerificationKeepsModelReadingsUnconfirmed(unittest.TestCase):
    def test_official_page_reverify_does_not_confirm_a_model_only_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            opp, _ = run([{"field": "covers_accommodation", "value": True,
                           "quote": "free accommodation in a university residence and health insurance"}])
            store.save_opportunity(opp, opp.id, URL)
            html = f"<html><head><title>Example Foundation Scholarship</title></head><body><p>{TEXT}</p></body></html>"
            verify(store, opp, Fetcher(Transport({URL: html}), min_interval=0, sleep=lambda s: None), [],
                   official_url=URL, today=TODAY)
            store.close()
        e = next(x for x in opp.evidence if x.field == "funding.accommodation" and x.method == "anthropic")
        self.assertEqual(e.status, VerificationStatus.EXTRACTED)


class TestClaudeIsTheActivePath(unittest.TestCase):
    def tearDown(self):
        mock.patch.stopall()

    def test_compare_defaults_to_rules_and_claude_only(self):
        args = build_parser().parse_args(["compare"])
        self.assertEqual(args.providers, "rules,anthropic")

    def test_env_example_selects_claude_in_dry_run(self):
        env = (REPO / ".env.example").read_text()
        self.assertIn("AI_PROVIDER=anthropic", env)
        self.assertIn("ANTHROPIC_ALLOW_PAID=0", env)
        self.assertIn("ANTHROPIC_MAX_ESTIMATED_COST_USD=0", env)

    def test_claude_without_key_is_dry_run_and_sends_nothing(self):
        mock.patch.dict(os.environ, {"AI_PROVIDER": "anthropic"}).start()
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_ALLOW_PAID"):
            os.environ.pop(k, None)
        llm = default_llm()
        self.assertIsInstance(llm, AnthropicLLM)
        factory = mock.Mock()
        llm._factory = factory
        st = enrich(Opportunity(id="y", title="Y", provider_name="p", info_url=URL), TEXT, llm,
                    source_type=SourceType.OFFICIAL, retrieved_at="t", today=TODAY)
        self.assertIn("PaidCallsDisabled", st["error"])
        factory.assert_not_called()

    def test_prompt_version_changes_invalidate_cached_answers(self):
        from scholarship_agent import cloud_llm
        self.assertEqual(cloud_llm.PROMPT_VERSION, "extract-v2")
        mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-test"}).start()
        a = AnthropicLLM()
        k2 = a._cache_key("s", "u")
        with mock.patch.object(cloud_llm, "PROMPT_VERSION", "extract-v1"):
            self.assertNotEqual(a._cache_key("s", "u"), k2)


class TestMockedClaudeRunEndToEnd(unittest.TestCase):
    def test_new_fields_through_the_real_provider_code(self):
        fields = [{"field": "covers_health_insurance", "value": True,
                   "quote": "free accommodation in a university residence and health insurance"}]
        resp = SimpleNamespace(usage=SimpleNamespace(input_tokens=900, output_tokens=120, cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0),
                               stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"fields": fields}))],
                               model="claude-opus-5-5", _request_id="req_1")
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: resp)))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-test", "ANTHROPIC_ALLOW_PAID": "1",
                                          "ANTHROPIC_MAX_REQUESTS_PER_RUN": "1", "ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN": "20000",
                                          "ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN": "8000",
                                          "ANTHROPIC_MAX_ESTIMATED_COST_USD": "0.2"}):
            llm = AnthropicLLM(client_factory=lambda: client)
            opp = Opportunity(id="z", title="Z", provider_name="p", info_url=URL)
            st = enrich(opp, TEXT, llm, source_type=SourceType.OFFICIAL, retrieved_at="t", today=TODAY)
        self.assertEqual(st["accepted"], ["funding.insurance"])
        u = llm.usage()["paid"]
        self.assertEqual((u["requests"], u["input_tokens"], u["output_tokens"]), (1, 900, 120))
        self.assertAlmostEqual(u["estimated_cost_usd"], (900 * 4 + 120 * 20) / 1e6)


if __name__ == "__main__":
    unittest.main()
