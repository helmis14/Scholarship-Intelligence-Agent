"""Round 6: Gemini provider (official google-genai SDK), shared cloud budgets/cache/ledger, provider selection,
side-by-side comparison. Every cloud call is mocked; nothing here touches the network or spends money."""

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

from scholarship_agent import compare as compare_mod  # noqa: E402
from scholarship_agent.ai_extract import default_llm, enrich  # noqa: E402
from scholarship_agent.anthropic_llm import AnthropicLLM  # noqa: E402
from scholarship_agent.cloud_llm import Budget, BudgetExceeded, PaidCallsDisabled  # noqa: E402
from scholarship_agent.gemini_llm import GeminiConfigError, GeminiLLM  # noqa: E402
from scholarship_agent.heldout import ROOT as HELDOUT_A  # noqa: E402
from scholarship_agent.models import Opportunity, SourceType, VerificationStatus  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402

TODAY = date(2026, 10, 17)
TEXT = ("Applicants must be citizens of Ghana or Kenya. The scholarship deadline is 1 March 2027. "
        "A monthly stipend of USD 1,000 per month is paid.")
GOOD = [{"field": "deadline_scholarship", "value": "2027-03-01", "quote": "The scholarship deadline is 1 March 2027."}]
VARS = ("AI_PROVIDER", "SCHOLAR_LLM_PROVIDER", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "GEMINI_ALLOW_PAID",
        "GEMINI_MAX_REQUESTS_PER_RUN", "GEMINI_MAX_INPUT_TOKENS_PER_RUN", "GEMINI_MAX_OUTPUT_TOKENS_PER_RUN",
        "GEMINI_MAX_ESTIMATED_COST_USD", "GEMINI_PRICE_INPUT_PER_MTOK", "GEMINI_PRICE_OUTPUT_PER_MTOK",
        "ANTHROPIC_API_KEY", "ANTHROPIC_ALLOW_PAID", "ANTHROPIC_MAX_REQUESTS_PER_RUN",
        "ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN", "ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN", "ANTHROPIC_MAX_ESTIMATED_COST_USD")
BUDGET = dict(GEMINI_MAX_REQUESTS_PER_RUN=5, GEMINI_MAX_INPUT_TOKENS_PER_RUN=100000,
              GEMINI_MAX_OUTPUT_TOKENS_PER_RUN=50000, GEMINI_MAX_ESTIMATED_COST_USD=1)


def env(**kw):
    p = mock.patch.dict(os.environ, {k: str(v) for k, v in kw.items()})
    p.start()
    for k in VARS:
        if k not in kw:
            os.environ.pop(k, None)


def gresp(fields=None, text=None, finish="STOP", prompt=1000, cached=0, cand=150, thoughts=50, blocked=None):
    body = text if text is not None else json.dumps({"fields": fields or []})
    parts = [SimpleNamespace(text="thinking...", thought=True), SimpleNamespace(text=body, thought=False)]
    return SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=prompt, cached_content_token_count=cached,
                                       candidates_token_count=cand, thoughts_token_count=thoughts),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish), content=SimpleNamespace(parts=parts))],
        prompt_feedback=SimpleNamespace(block_reason=blocked) if blocked else None, response_id="resp-1")


class FakeGemini:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Case(unittest.TestCase):
    def tearDown(self):
        mock.patch.stopall()


class TestGeminiConfig(Case):
    def test_defaults_are_dry_run_with_current_model(self):
        env(GEMINI_API_KEY="g-test")
        factory = mock.Mock()
        g = GeminiLLM(client_factory=factory)
        self.assertEqual((g.model, g.allow_paid, g.name), ("gemini-3.8-flash", False, "gemini:gemini-3.8-flash"))
        with self.assertRaises(PaidCallsDisabled):
            g.complete_json("s", "u")
        factory.assert_not_called()
        self.assertEqual(g.usage()["paid"]["requests"], 0)
        self.assertGreater(g.usage()["dry_run"]["worst_case_cost_usd"], g.usage()["dry_run"]["estimated_cost_usd"])

    def test_missing_key_is_a_configuration_error(self):
        env(GEMINI_ALLOW_PAID=1, GOOGLE_API_KEY="other-google-credential")
        with self.assertRaises(GeminiConfigError):
            GeminiLLM()

    def test_unknown_model_and_bad_numbers(self):
        env(GEMINI_MODEL="gemini-9-ultra")
        with self.assertRaises(GeminiConfigError):
            GeminiLLM()
        env(GEMINI_MODEL="gemini-9-ultra", GEMINI_PRICE_INPUT_PER_MTOK=1, GEMINI_PRICE_OUTPUT_PER_MTOK=2)
        self.assertEqual(GeminiLLM.price("gemini-9-ultra"), (1.0, 2.0))
        env(GEMINI_MAX_REQUESTS_PER_RUN="many")
        with self.assertRaises(GeminiConfigError):
            GeminiLLM()

    def test_dated_list_prices(self):
        with mock.patch.object(GeminiLLM, "today", staticmethod(lambda: date(2026, 12, 31))):
            self.assertEqual(GeminiLLM.price("gemini-3.8-flash"), (0.75, 3.75))
        with mock.patch.object(GeminiLLM, "today", staticmethod(lambda: date(2027, 1, 1))):
            self.assertEqual(GeminiLLM.price("gemini-3.8-flash"), (1.50, 7.50))

    def test_client_uses_explicit_key_developer_api_and_official_url(self):
        env(GEMINI_API_KEY="g-test", GOOGLE_API_KEY="must-not-be-used", GEMINI_ALLOW_PAID=1, **BUDGET)
        with mock.patch("google.genai.Client") as client:
            GeminiLLM().client()
        kw = client.call_args.kwargs
        self.assertEqual((kw["api_key"], kw["vertexai"]), ("g-test", False))
        self.assertEqual(kw["http_options"].base_url, "https://generativelanguage.googleapis.com/")
        self.assertEqual(kw["http_options"].timeout, 120000)
        self.assertIn(429, kw["http_options"].retry_options.http_status_codes)

    def test_structured_config_is_accepted_by_the_sdk(self):
        from google.genai import types
        from scholarship_agent.ai_extract import FIELDS, SYSTEM
        env()
        cfg = GeminiLLM()._config(SYSTEM, FIELDS)
        built = types.GenerateContentConfig(**cfg)
        self.assertEqual(built.response_mime_type, "application/json")
        self.assertIn("deadline_scholarship",
                      cfg["response_json_schema"]["properties"]["fields"]["items"]["properties"]["field"]["enum"])
        self.assertEqual(str(built.thinking_config.thinking_level.value).lower(), "low")
        env(GEMINI_MODEL="gemini-2.5-flash")
        self.assertNotIn("thinking_config", GeminiLLM()._config(SYSTEM, FIELDS))


class TestGeminiCalls(Case):
    def setUp(self):
        env(GEMINI_API_KEY="g-test-key", GEMINI_ALLOW_PAID=1, **BUDGET)
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        super().tearDown()
        self.store.close()
        self.tmp.cleanup()

    def llm(self, *responses, **kw):
        self.fake = FakeGemini(*responses)
        return GeminiLLM(client_factory=lambda: self.fake, store=self.store, **kw)

    def test_parse_usage_cost_latency_and_ledger(self):
        ticks = iter([10.0, 10.25])
        g = self.llm(gresp(GOOD, prompt=1000, cached=200, cand=150, thoughts=50), clock=lambda: next(ticks))
        with mock.patch.object(GeminiLLM, "today", staticmethod(lambda: TODAY)):
            out = g.complete_json("sys", "page")
        self.assertEqual(out["fields"][0]["value"], "2027-03-01")      # thought parts are not parsed as the answer
        u = g.usage()
        self.assertEqual((u["paid"]["input_tokens"], u["paid"]["output_tokens"]), (1000, 200))
        self.assertAlmostEqual(u["paid"]["estimated_cost_usd"], (800 * 0.75 + 200 * 0.075 + 200 * 3.75) / 1e6)
        self.assertEqual(u["latency_ms"]["mean"], 250.0)
        row = self.store.catalog.execute("SELECT provider, status, latency_ms, request_id FROM llm_usage").fetchone()
        self.assertEqual(tuple(row), ("gemini", "ok", 250.0, "resp-1"))
        self.assertEqual(self.fake.calls[0]["model"], "gemini-3.8-flash")
        self.assertEqual(self.fake.calls[0]["contents"], "page")

    def test_truncated_blocked_and_invalid_answers(self):
        for r, msg in ((gresp(finish="MAX_TOKENS"), "MAX_TOKENS"), (gresp(finish="SAFETY"), "blocked"),
                       (gresp(blocked="PROHIBITED_CONTENT"), "blocked"), (gresp(text="not json"), "validation")):
            with self.assertRaisesRegex(ValueError, msg):
                self.llm(r).complete_json("s", f"u-{msg}")

    def test_extra_and_unknown_fields_are_dropped(self):
        bad = [{"field": "salary", "value": 1, "quote": "xxxxxxx"},
               {"field": "max_age", "value": 35, "quote": "under 35", "note": "extra"}] + GOOD
        out = self.llm(gresp(bad)).complete_json("s", "u")
        self.assertEqual([f["field"] for f in out["fields"]], ["deadline_scholarship"])

    def test_rate_limit_error_is_safe_and_counted(self):
        from google.genai import errors
        err = errors.ClientError(429, {"error": {"code": 429, "message": "quota for g-test-key exhausted",
                                                 "status": "RESOURCE_EXHAUSTED"}})
        g = self.llm(err)
        with self.assertRaises(RuntimeError) as cm:
            g.complete_json("s", "u")
        self.assertIn("rate limit", str(cm.exception))
        self.assertNotIn("g-test-key", str(cm.exception))
        self.assertEqual(g.budget.requests, 1)        # the attempt counts against the request budget

    def test_server_error_is_reported_without_key(self):
        from google.genai import errors
        g = self.llm(errors.ServerError(503, {"error": {"message": "overloaded g-test-key"}}))
        with self.assertRaisesRegex(RuntimeError, "Gemini API error 503") as cm:
            g.complete_json("s", "u")
        self.assertNotIn("g-test-key", str(cm.exception))

    def test_budget_stops_before_sending(self):
        os.environ["GEMINI_MAX_REQUESTS_PER_RUN"] = "1"
        g = self.llm(gresp(GOOD), gresp(GOOD))
        g.complete_json("s", "one")
        with self.assertRaises(BudgetExceeded):
            g.complete_json("s", "two")
        self.assertEqual(len(self.fake.calls), 1)
        os.environ["GEMINI_MAX_ESTIMATED_COST_USD"] = "0.00001"
        os.environ["GEMINI_MAX_REQUESTS_PER_RUN"] = "5"
        g = self.llm(gresp(GOOD))
        with self.assertRaises(BudgetExceeded):
            g.complete_json("s", "x" * 4000)
        self.assertEqual(self.fake.calls, [])

    def test_cache_is_per_provider_and_skips_repeat_pages(self):
        g = self.llm(gresp(GOOD))
        g.complete_json("sys", "page")
        g2 = GeminiLLM(client_factory=lambda: self.fake, store=self.store)
        self.assertEqual(g2.complete_json("sys", "page")["fields"], g.complete_json("sys", "page")["fields"])
        self.assertEqual(len(self.fake.calls), 1)
        a = AnthropicLLM(store=self.store)                     # Claude dry run: not served from Gemini's cache
        with self.assertRaises(PaidCallsDisabled):
            a.complete_json("sys", "page")

    def test_model_claims_are_quote_checked_and_never_confirmed(self):
        claims = GOOD + [{"field": "max_age", "value": 30, "quote": "Applicants must be under 30."},
                         {"field": "stipend_amount", "value": 2000, "quote": "A monthly stipend of USD 1,000 per month is paid."}]
        opp = Opportunity(id="x", title="X", provider_name="p", info_url="https://www.example.gov/x")
        st = enrich(opp, TEXT, self.llm(gresp(claims)), source_type=SourceType.OFFICIAL, retrieved_at="t", today=TODAY)
        self.assertEqual(st["accepted"], ["deadline.scholarship"])
        reasons = {r["reason"] for r in st["rejected"]}
        self.assertIn("quote not found on page", reasons)
        self.assertIn("number not stated in quote", reasons)
        e = next(x for x in opp.evidence if x.note.startswith("ai-assisted"))
        self.assertEqual((e.method, e.status), ("gemini", VerificationStatus.EXTRACTED))


class TestSelection(Case):
    def test_each_provider_is_selected_independently_and_never_falls_back(self):
        env(AI_PROVIDER="gemini")
        self.assertIsInstance(default_llm(), GeminiLLM)
        env(AI_PROVIDER="anthropic")
        self.assertIsInstance(default_llm(), AnthropicLLM)
        env(AI_PROVIDER="gemini", GEMINI_ALLOW_PAID=1, ANTHROPIC_API_KEY="sk-ant-api03-test")   # Claude key present: no fallback
        with self.assertRaises(GeminiConfigError):
            default_llm()
        env(AI_PROVIDER="none", GEMINI_API_KEY="g", ANTHROPIC_API_KEY="sk-ant-api03-test")
        self.assertIsNone(default_llm())
        env(AI_PROVIDER="ollama", OLLAMA_MODEL="m")
        self.assertEqual(default_llm().name, "ollama:m")

    def test_budgets_are_separate_per_provider(self):
        env(ANTHROPIC_MAX_REQUESTS_PER_RUN=3)
        self.assertEqual(Budget.from_env("ANTHROPIC").max_requests, 3)
        self.assertEqual(Budget.from_env("GEMINI").max_requests, 0)


class TestCompare(Case):
    def test_cloud_modes_without_keys_are_not_run_and_have_no_scores(self):
        env()
        out = compare_mod.compare(HELDOUT_A.parent / "heldout_b", ["rules", "anthropic", "gemini"])
        self.assertEqual(out["providers"]["rules"]["status"], "run")
        for p in ("anthropic", "gemini"):
            r = out["providers"][p]
            self.assertEqual(r["status"], "not_run")
            self.assertNotIn("exact_match", r)
            self.assertIn("not set", r["reason"])
            self.assertGreater(r["estimate"]["estimated_cost_usd"], 0)

    def test_authorised_mocked_run_is_scored_and_budget_stop_is_partial(self):
        env(GEMINI_API_KEY="g", GEMINI_ALLOW_PAID=1, **(BUDGET | {"GEMINI_MAX_REQUESTS_PER_RUN": 3}))
        fake = FakeGemini(*[gresp([]) for _ in range(20)])
        with mock.patch.object(compare_mod, "_provider", lambda name, store: GeminiLLM(client_factory=lambda: fake)):
            out = compare_mod.compare(HELDOUT_A.parent / "heldout_b", ["gemini"])
        r = out["providers"]["gemini"]
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["requests"]["answered"], 3)
        self.assertIn("exact_match", r)
        self.assertEqual(r["usage"]["paid"]["requests"], 3)
        self.assertEqual(len(fake.calls), 3)


if __name__ == "__main__":
    unittest.main()
