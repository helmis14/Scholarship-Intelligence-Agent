"""Anthropic Claude provider for evidence-checked extraction and explanations.

Configuration (environment, never in the repository):
  AI_PROVIDER=anthropic          select this provider (AI_PROVIDER=ollama | none are the alternatives)
  ANTHROPIC_API_KEY=...          required; read ONLY from this variable
  ANTHROPIC_WORKSPACE_ID=...     needed only for user-scoped keys (sk-ant-usr-...), which name no workspace
  ANTHROPIC_MODEL=...            optional; default claude-opus-5-5 (the current Opus)
  ANTHROPIC_ALLOW_PAID=1         required for any paid request. Without it every call is a dry run that
                                 only estimates tokens and cost and returns nothing.
  ANTHROPIC_MAX_REQUESTS_PER_RUN, ANTHROPIC_MAX_INPUT_TOKENS_PER_RUN,
  ANTHROPIC_MAX_OUTPUT_TOKENS_PER_RUN, ANTHROPIC_MAX_ESTIMATED_COST_USD
                                 per-run budgets; defaults 0 (nothing may be spent until you set them)
  ANTHROPIC_MAX_TOKENS           per-request output cap (default 4000; thinking counts toward it)
  ANTHROPIC_EFFORT               low | medium | high (default low: extraction is a narrow task)
  ANTHROPIC_TIMEOUT_SECONDS      per-request timeout (default 120)
  ANTHROPIC_MAX_RETRIES          agent-side retries on 429/5xx/connection errors with backoff (default 3); SDK
                                 retries are off so every attempt is checked against the budget
  ANTHROPIC_MAX_TOTAL_COST_USD   optional cap across runs in one data directory (default 0 = off)
  ANTHROPIC_SERVER_FALLBACK=1    opt-in server-side fallback to another model when overloaded
  ANTHROPIC_MAX_CONCURRENCY      simultaneous requests (default 2)
  ANTHROPIC_PRICE_INPUT_PER_MTOK / ANTHROPIC_PRICE_OUTPUT_PER_MTOK
                                 override prices for models not in PRICES (USD per million tokens)
  SCHOLAR_ANTHROPIC_BASE_URL     optional; the generic ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN variables
                                 are deliberately ignored (they may belong to another tool on this machine)

Budgets, dry run, cache, ledger and response validation are shared with Gemini in cloud_llm.py.
Nothing here logs page text, profile data or credentials. Usage is recorded as counts only.
"""

from __future__ import annotations

import os

from .cloud_llm import (Budget, BudgetExceeded, CloudConfigError, CloudLLM, PaidCallsDisabled, Reply,
                        response_schema, validate_response)

# re-exported for callers and tests written against this module
__all__ = ["AnthropicConfigError", "AnthropicLLM", "Budget", "BudgetExceeded", "PaidCallsDisabled", "PRICES",
           "cost_of", "price", "response_schema", "validate_response"]

DEFAULT_MODEL = "claude-opus-5-5"
OFFICIAL_BASE_URL = "https://api.anthropic.com"
# USD per million tokens (input, output), Anthropic first-party list prices as documented 2026-10.
# Estimates only: check current pricing before relying on them.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00), "claude-opus-5": (5.00, 25.00), "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00), "claude-sonnet-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00), "claude-fable-5-1": (10.00, 50.00),
}


class AnthropicConfigError(CloudConfigError):
    """Missing or invalid Anthropic configuration."""


def price(model: str) -> tuple[float, float]:
    return AnthropicLLM.price(model)


def cost_of(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
    return AnthropicLLM.cost(model, Reply("", input_tokens, output_tokens, cache_read, cache_write))


class AnthropicLLM(CloudLLM):
    provider = "anthropic"
    prefix = "ANTHROPIC"
    key_env = ("ANTHROPIC_API_KEY",)   # never ANTHROPIC_AUTH_TOKEN: that is another tool's login, not an API key
    prices = PRICES
    default_model = DEFAULT_MODEL
    ConfigError = AnthropicConfigError

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
        if self._key and not self._key.startswith(("sk-ant-api", "sk-ant-usr")):
            # e.g. sk-ant-oat-: a Claude login (OAuth) token, not a billed API key; never send it
            raise AnthropicConfigError("ANTHROPIC_API_KEY does not look like an Anthropic API key "
                                       "(sk-ant-api... or sk-ant-usr...); create one at console.anthropic.com")
        if self._key.startswith("sk-ant-usr") and not self.workspace_id:
            # user-scoped Console keys are not tied to a workspace; the API needs the workspace in a header
            raise AnthropicConfigError("this API key is not scoped to a workspace: set ANTHROPIC_WORKSPACE_ID "
                                       "(Console > Settings > Workspaces) or use a workspace key")
        self.effort = os.environ.get("ANTHROPIC_EFFORT", "low")
        if self.effort not in ("low", "medium", "high", "xhigh", "max"):
            raise AnthropicConfigError("ANTHROPIC_EFFORT must be low, medium, high, xhigh or max")

    def _make_client(self):
        try:
            import anthropic
        except ImportError:
            raise AnthropicConfigError("the 'anthropic' package is not installed: python3 -m pip install anthropic") from None
        # Explicit key and base URL: the SDK then ignores ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL
        # from the environment, which on this machine may point at another tool's proxy.
        # max_retries=0: the SDK would otherwise retry timeouts and 5xx silently, and a timed-out request may still
        # be billed. Retries happen in _create instead, where each one is checked against the budget.
        return anthropic.Anthropic(api_key=self._key,
                                   base_url=os.environ.get("SCHOLAR_ANTHROPIC_BASE_URL") or OFFICIAL_BASE_URL,
                                   timeout=self.timeout, max_retries=0,
                                   default_headers={"anthropic-workspace-id": self.workspace_id}
                                   if self.workspace_id else None)

    def _request_args(self, system: str, user: str, fields: dict) -> dict:
        args = {"model": self.model, "system": system, "messages": [{"role": "user", "content": user}],
                "output_config": {"effort": self.effort,
                                  "format": {"type": "json_schema", "schema": response_schema(fields)}}}
        if os.environ.get("ANTHROPIC_SERVER_FALLBACK") == "1":
            # opt-in: another model may answer when this one is overloaded; its price may differ from the estimate
            args.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        return args

    def count_input_tokens(self, system: str, user: str, fields: dict):
        """Anthropic's token-counting endpoint (free, separately rate-limited) for an exact input budget check."""
        args = self._request_args(system, user, fields)
        args.pop("fallbacks", None)
        try:
            return int(self.client().beta.messages.count_tokens(**args).input_tokens)
        except Exception:  # counting is a safety improvement, never a reason to fail; the char estimate remains
            return None

    def _call(self, system: str, user: str, fields: dict) -> Reply:
        resp = self._create(system, user, fields)
        u = resp.usage
        stop = {"refusal": "refusal", "max_tokens": "truncated"}.get(resp.stop_reason, "ok")
        return Reply(text=next((b.text for b in resp.content if getattr(b, "type", "") == "text"), ""),
                     input_tokens=int(getattr(u, "input_tokens", 0) or 0),
                     output_tokens=int(getattr(u, "output_tokens", 0) or 0),
                     cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
                     cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
                     served_model=getattr(resp, "model", "") or "", request_id=getattr(resp, "_request_id", "") or "",
                     stop=stop)

    def _create(self, system: str, user: str, fields: dict):
        try:
            from anthropic import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
            retryable = (RateLimitError, InternalServerError, APIConnectionError)
        except ImportError:   # injected test clients
            APITimeoutError, RateLimitError, retryable = (), (), ()
        attempts = 0
        while True:
            try:
                return self.client().beta.messages.create(max_tokens=self.max_tokens,
                                                          **self._request_args(system, user, fields))
            except retryable as e:
                if isinstance(e, APITimeoutError) or (not isinstance(e, (RateLimitError, InternalServerError))):
                    self.charge_uncertain_attempt()   # it may have run and been billed
                attempts += 1
                if attempts > self.max_retries:
                    raise
                retry_after = 0.0
                try:
                    retry_after = float(e.response.headers.get("retry-after", "0"))
                except (AttributeError, ValueError):
                    pass
                self.sleep(max(retry_after, 2.0 * (2 ** attempts)))
                self.reserve_retry()
