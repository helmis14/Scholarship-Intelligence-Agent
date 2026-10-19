"""Cost-cap audit for the Claude evaluation (follow-up to round 7): no hidden SDK retries, exact input counting,
worst-case booking of uncertain attempts, budget re-check on every retry, optional total cap across runs,
opt-in server fallback, conservative pricing of unknown served models, and a worst-case set-B run that cannot
cross $1. Every API call is mocked."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scholarship_agent import compare as compare_mod  # noqa: E402
from scholarship_agent.anthropic_llm import AnthropicLLM  # noqa: E402
from scholarship_agent.cloud_llm import BudgetExceeded  # noqa: E402
from scholarship_agent.heldout import ROOT as HELDOUT_A  # noqa: E402
from scholarship_agent.store import Store  # noqa: E402

GOOD = [{"field": "deadline_scholarship", "value": "2027-03-01", "quote": "The scholarship deadline is 1 March 2027."}]
VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_ALLOW_PAID", "ANTHROPIC_MAX_REQUESTS_PER_RUN", "ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN",
        "ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN", "ANTHROPIC_MAX_ESTIMATED_COST_USD", "ANTHROPIC_MAX_TOTAL_COST_USD",
        "ANTHROPIC_SERVER_FALLBACK", "ANTHROPIC_MODEL", "ANTHROPIC_MAX_TOKENS", "AI_PROVIDER", "ANTHROPIC_WORKSPACE_ID")
# the budget printed in EVALUATION.md / the round 7 report
DOC_BUDGET = dict(ANTHROPIC_API_KEY="sk-ant-api03-test", ANTHROPIC_ALLOW_PAID=1, ANTHROPIC_MAX_REQUESTS_PER_RUN=10,
                  ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN=40000, ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN=40000,
                  ANTHROPIC_MAX_ESTIMATED_COST_USD=1)


def env(**kw):
    mock.patch.dict(os.environ, {k: str(v) for k, v in kw.items()}).start()
    for k in VARS:
        if k not in kw:
            os.environ.pop(k, None)


def resp(fields=GOOD, tin=1000, tout=200, model="claude-opus-5-5"):
    return SimpleNamespace(usage=SimpleNamespace(input_tokens=tin, output_tokens=tout, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0),
                           stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"fields": fields}))],
                           model=model, _request_id="req")


class Client:
    def __init__(self, *responses, count=None):
        self.responses, self.calls, self.counts = list(responses), [], []
        self.count = count
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create, count_tokens=self.count_tokens))

    def create(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r(kw) if callable(r) else r

    def count_tokens(self, **kw):
        self.counts.append(kw)
        if self.count is None:
            raise RuntimeError("counting unavailable")
        return SimpleNamespace(input_tokens=self.count(kw))


REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class TestCostGuards(unittest.TestCase):
    def tearDown(self):
        mock.patch.stopall()

    def test_sdk_never_retries_on_its_own(self):
        env(**DOC_BUDGET)
        fake = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"anthropic": fake}):
            AnthropicLLM().client()
        self.assertEqual(fake.Anthropic.call_args.kwargs["max_retries"], 0)

    def test_exact_input_count_is_used_for_the_budget(self):
        env(**(DOC_BUDGET | {"ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN": 5000}))
        c = Client(resp(), count=lambda kw: 9000)          # far more than the character estimate
        with self.assertRaises(BudgetExceeded):
            AnthropicLLM(client_factory=lambda: c).complete_json("s", "short page")
        self.assertEqual((len(c.counts), c.calls), (1, []))
        self.assertIn("output_config", c.counts[0])         # counted with the same schema it would be sent with

    def test_counting_failure_falls_back_to_the_estimate(self):
        env(**DOC_BUDGET)
        c = Client(resp())
        out = AnthropicLLM(client_factory=lambda: c).complete_json("s", "page")
        self.assertEqual(len(out["fields"]), 1)

    def test_timeout_is_booked_at_worst_case_and_retry_is_rechecked(self):
        env(**DOC_BUDGET)
        c = Client(anthropic.APITimeoutError(request=REQ), resp(tin=1000, tout=200))
        llm = AnthropicLLM(client_factory=lambda: c, sleep=lambda s: None)
        llm.complete_json("s", "page")
        u = llm.usage()["paid"]
        self.assertEqual(u["requests"], 2)                  # the retry counted as a request
        self.assertGreater(u["estimated_cost_usd"], 0.08)   # worst case of the lost attempt + the real one
        self.assertIn("uncertain_charged_worst_case", [x["status"] for x in llm.calls])

    def test_retry_that_would_cross_the_request_budget_is_not_sent(self):
        env(**(DOC_BUDGET | {"ANTHROPIC_MAX_REQUESTS_PER_RUN": 1}))
        overloaded = anthropic.InternalServerError("overloaded", response=httpx.Response(529, request=REQ), body=None)
        c = Client(overloaded, resp())
        with self.assertRaises(BudgetExceeded):
            AnthropicLLM(client_factory=lambda: c, sleep=lambda s: None).complete_json("s", "page")
        self.assertEqual(len(c.calls), 1)

    def test_total_cap_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            with store.catalog as cx:
                cx.execute("INSERT INTO llm_usage (provider, model, at, status, input_tokens, output_tokens, "
                           "cache_read_tokens, cost_usd, request_id) VALUES ('anthropic','m','t','ok',0,0,0,0.97,'')")
            env(**(DOC_BUDGET | {"ANTHROPIC_MAX_TOTAL_COST_USD": 1}))
            c = Client(resp())
            with self.assertRaises(BudgetExceeded):
                AnthropicLLM(client_factory=lambda: c, store=store).complete_json("s", "page")
            self.assertEqual(c.calls, [])
            store.close()

    def test_server_fallback_is_opt_in(self):
        env(**DOC_BUDGET)
        c = Client(resp(), resp())
        AnthropicLLM(client_factory=lambda: c).complete_json("s", "a")
        self.assertNotIn("fallbacks", c.calls[0])
        os.environ["ANTHROPIC_SERVER_FALLBACK"] = "1"
        AnthropicLLM(client_factory=lambda: c).complete_json("s", "b")
        self.assertEqual(c.calls[1]["fallbacks"], "default")

    def test_unknown_served_model_is_charged_at_the_dearest_price(self):
        env(**DOC_BUDGET)
        llm = AnthropicLLM(client_factory=lambda: Client(resp(tin=1000, tout=1000, model="claude-mystery-9")))
        llm.complete_json("s", "page")
        self.assertAlmostEqual(llm.usage()["paid"]["estimated_cost_usd"], (1000 * 10 + 1000 * 50) / 1e6)


class TestKeyShape(unittest.TestCase):
    def tearDown(self):
        mock.patch.stopall()

    def test_login_tokens_are_refused_before_any_request(self):
        from scholarship_agent.anthropic_llm import AnthropicConfigError
        for token in ("sk-ant-oat01-xxxx", "not-a-key"):
            env(ANTHROPIC_API_KEY=token)
            with self.assertRaises(AnthropicConfigError):
                AnthropicLLM()
        env(ANTHROPIC_API_KEY="sk-ant-api03-xxxx")
        self.assertEqual(AnthropicLLM().model, "claude-opus-5-5")

    def test_user_scoped_key_needs_a_workspace_header(self):
        from scholarship_agent.anthropic_llm import AnthropicConfigError
        env(ANTHROPIC_API_KEY="sk-ant-usr-xxxx")
        with self.assertRaises(AnthropicConfigError):
            AnthropicLLM()
        env(ANTHROPIC_API_KEY="sk-ant-usr-xxxx", ANTHROPIC_WORKSPACE_ID="wrkspc_test")
        fake = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"anthropic": fake}):
            AnthropicLLM().client()
        self.assertEqual(fake.Anthropic.call_args.kwargs["default_headers"], {"anthropic-workspace-id": "wrkspc_test"})


class TestDocumentedBudgetIsSafe(unittest.TestCase):
    """Worst case for the documented set-B command: every answer uses the full output cap and the input count is
    larger than the character estimate. The run must stop before $1, never after."""

    def tearDown(self):
        mock.patch.stopall()

    def test_worst_case_set_b_run_stays_under_one_dollar(self):
        env(**DOC_BUDGET)
        n_in = lambda kw: int(len(kw["system"]) / 2.5 + len(kw["messages"][0]["content"]) / 2.5)  # noqa: E731
        c = Client(*[lambda kw: resp([], tin=n_in(kw), tout=4000) for _ in range(20)], count=n_in)
        with mock.patch.object(compare_mod, "_provider", lambda name, store: AnthropicLLM(client_factory=lambda: c)):
            out = compare_mod.compare(HELDOUT_A.parent / "heldout_b", ["anthropic"])
        r = out["providers"]["anthropic"]
        cost = r["usage"]["paid"]["estimated_cost_usd"]
        self.assertLessEqual(cost, 1.0)
        self.assertLessEqual(r["usage"]["paid"]["output_tokens"], 40000)
        self.assertLessEqual(r["usage"]["paid"]["input_tokens"], 40000)
        self.assertIn(r["status"], ("run", "partial"))


if __name__ == "__main__":
    unittest.main()


class TestClaudeAnswerAudit(unittest.TestCase):
    """Plausible wrong (and right) Claude answers built from real development-set sentences; inline so the test does
    not depend on the gitignored page snapshots. Simulated answers, not API results."""

    NZ_COSTS = ("Visa costs we will reimburse (if you show your payment receipts)\nVisa application fee and immigration levy\n"
                "Visa costs we will not reimburse\nTravel to location where medical check occurs\nPolice clearance fee")
    NSP = ("Closing dates for student application is 31-10-2026 and closing date for institute verification is : "
           "15-11-2026 and closing date for L2 verification is : 30/11/2026.")
    CASES = [
        # (field, value, quote, page or None (= quote), accept?)
        ("deadline_scholarship", "2026-10-31", NSP, None, True),
        ("deadline_scholarship", "2026-11-30", NSP, None, False),
        ("opening_date", "2026-11-28", "Masters Virtual Open Day: Saturday 28 November 2026", None, False),
        ("opening_date", "2026-06-30", "Pendaftaran dibuka pada 30 Juni 2026 - 31 Juli 2026.", None, True),
        ("academic_cycle", "2027/2028", "2027-28 Chevening scholars commence their studies in the UK", None, True),
        ("academic_cycle", "2024/2033", "International Decade of Sciences for Sustainable Development (2024–2033)", None, False),
        ("provider_name", "New Zealand Government", "The New Zealand Government offers Vocational Short Term Training "
                                                    "Scholarships", None, True),
        ("provider_name", "Study with New Zealand", "The Study with New Zealand website lists other full scholarships "
                                                    "available to international students.", None, False),
        ("residency_required", ["Japan"], "A citizen or permanent resident of Japan", None, False),
        ("funding_duration_months", 18, "you must be 18 years old at signing the scholarship letter of offer.", None, False),
        ("funding_duration_months", 36, "US $10K per year for up to 3 years (or up to graduation)", None, True),
        ("funding_duration_months", 6, "the Project may be extended for a maximum of 6 months", None, False),
        ("covers_travel", True, "Travel to location where medical check occurs", NZ_COSTS, False),
        ("covers_travel", True, "travel expenses including overseas travel", None, True),
        ("covers_accommodation", True, "your accommodation costs will be supported as well.", None, True),
        ("tuition_coverage", "full", "US $85K per year towards education costs (tuition and fees), living expenses",
         None, False),
        ("tuition_coverage", "full", "all your tuition fees will be covered", None, True),
        ("tuition_coverage", "full", "The Study with New Zealand website lists other full scholarships.", None, False),
    ]

    def test_validator_verdicts(self):
        from scholarship_agent.ai_extract import validate
        for f, v, q, pg, want in self.CASES:
            with self.subTest(field=f, value=v):
                why = validate(f, v, q, pg or q)
                self.assertEqual(why is None, want, why)
