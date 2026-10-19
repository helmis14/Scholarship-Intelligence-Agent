"""Google Gemini provider (Gemini Developer API via Google's official `google-genai` SDK).

Configuration (environment, never in the repository):
  AI_PROVIDER=gemini             select this provider
  GEMINI_API_KEY=...             required; read ONLY from this variable (GOOGLE_API_KEY, Vertex AI and
                                 application-default credentials are deliberately not used)
  GEMINI_MODEL=...               optional; default gemini-3.8-flash (stable, 2026-10)
  GEMINI_ALLOW_PAID=1            required for any request. Without it every call is a dry run that only
                                 estimates tokens and cost. Required on the free tier too: the agent cannot tell
                                 which tier a key is on, and free-tier prompts may be used by Google to improve
                                 its products (public scholarship pages only are sent; never profile data).
  GEMINI_MAX_REQUESTS_PER_RUN, GEMINI_MAX_INPUT_TOKENS_PER_RUN,
  GEMINI_MAX_OUTPUT_TOKENS_PER_RUN, GEMINI_MAX_ESTIMATED_COST_USD
                                 per-run budgets; defaults 0
  GEMINI_MAX_TOKENS              per-request output cap (default 4000; thinking tokens count toward it)
  GEMINI_THINKING_LEVEL          low | medium | high for Gemini 3+ models (default low)
  GEMINI_TIMEOUT_SECONDS, GEMINI_MAX_RETRIES, GEMINI_MAX_CONCURRENCY
                                 timeout (120 s), SDK retries on 408/429/5xx with backoff (3), parallel requests (2)
  GEMINI_PRICE_INPUT_PER_MTOK / GEMINI_PRICE_OUTPUT_PER_MTOK
                                 prices for models not in PRICES (USD per million tokens)

Shares budgets, dry run, cache, ledger and response validation with the Anthropic provider (cloud_llm.py).
"""

from __future__ import annotations

import os
from datetime import date

from .cloud_llm import CloudConfigError, CloudLLM, Reply, response_schema

DEFAULT_MODEL = "gemini-3.8-flash"
OFFICIAL_BASE_URL = "https://generativelanguage.googleapis.com/"
# USD per million tokens, standard paid tier, text prompts <= 200k tokens, from ai.google.dev/gemini-api/docs/pricing
# (page last updated 2026-10-16). Some list prices change on a date: (last day of the price or None, in, out).
PRICES = {
    "gemini-3.8-flash": [("2026-12-31", 0.75, 3.75), (None, 1.50, 7.50)],
    "gemini-3.6-flash": [("2026-12-31", 0.75, 3.75), (None, 1.50, 7.50)],
    "gemini-4-argon": [("2026-11-30", 2.00, 10.00), (None, 4.00, 20.00)],
    "gemini-3.5-flash-lite": [(None, 0.30, 2.50)],
    "gemini-3.1-pro-preview": [(None, 2.00, 12.00)],
    "gemini-2.5-flash": [(None, 0.30, 2.50)],
    "gemini-2.5-pro": [(None, 1.25, 10.00)],
}
BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY", "LANGUAGE", "OTHER"}


class GeminiConfigError(CloudConfigError):
    """Missing or invalid Gemini configuration."""


class GeminiLLM(CloudLLM):
    provider = "gemini"
    prefix = "GEMINI"
    key_env = ("GEMINI_API_KEY",)
    prices = PRICES
    default_model = DEFAULT_MODEL
    ConfigError = GeminiConfigError
    today = staticmethod(date.today)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.thinking_level = os.environ.get("GEMINI_THINKING_LEVEL", "low")
        if self.thinking_level not in ("minimal", "low", "medium", "high"):
            raise GeminiConfigError("GEMINI_THINKING_LEVEL must be minimal, low, medium or high")

    @classmethod
    def price(cls, model: str) -> tuple[float, float]:
        if os.environ.get("GEMINI_PRICE_INPUT_PER_MTOK") and os.environ.get("GEMINI_PRICE_OUTPUT_PER_MTOK"):
            return CloudLLM.price.__func__(cls, model)
        if model not in PRICES:
            raise GeminiConfigError(f"no price known for {model!r}: set GEMINI_PRICE_INPUT_PER_MTOK and "
                                    "GEMINI_PRICE_OUTPUT_PER_MTOK so the cost budget can be enforced")
        today = cls.today().isoformat()
        for until, pin, pout in PRICES[model]:
            if until is None or today <= until:
                return pin, pout
        return PRICES[model][-1][1:]

    def _make_client(self):
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise GeminiConfigError("the 'google-genai' package is not installed: python3 -m pip install google-genai") from None
        # Explicit key, Developer API (not Vertex AI) and base URL, so no other Google credential on this machine
        # is picked up from the environment.
        return genai.Client(api_key=self._key, vertexai=False, http_options=types.HttpOptions(
            base_url=OFFICIAL_BASE_URL, timeout=int(self.timeout * 1000),
            retry_options=types.HttpRetryOptions(attempts=self.max_retries + 1, initial_delay=2.0, max_delay=60.0,
                                                 http_status_codes=[408, 429, 500, 502, 503, 504])))

    def _config(self, system: str, fields: dict) -> dict:
        cfg = {"system_instruction": system, "temperature": 0, "max_output_tokens": self.max_tokens,
               "response_mime_type": "application/json", "response_json_schema": response_schema(fields)}
        if not self.model.startswith(("gemini-2.", "gemini-1.")):
            cfg["thinking_config"] = {"thinking_level": self.thinking_level}
        return cfg

    def _call(self, system: str, user: str, fields: dict) -> Reply:
        try:
            resp = self.client().models.generate_content(model=self.model, contents=user,
                                                         config=self._config(system, fields))
        except Exception as e:  # SDK errors carry the API's message; make sure the key never travels with it
            code = getattr(e, "code", None)
            msg = str(e).replace(self._key, "[redacted]") if self._key else str(e)
            if code == 429:
                raise RuntimeError(f"Gemini rate limit or quota reached after retries: {msg[:200]}") from None
            if type(e).__module__.startswith("google"):
                raise RuntimeError(f"Gemini API error {code}: {msg[:200]}") from None
            raise
        u = getattr(resp, "usage_metadata", None)
        prompt = int(getattr(u, "prompt_token_count", 0) or 0)
        cached = int(getattr(u, "cached_content_token_count", 0) or 0)
        out = int(getattr(u, "candidates_token_count", 0) or 0) + int(getattr(u, "thoughts_token_count", 0) or 0)
        stop = "ok"
        feedback = getattr(resp, "prompt_feedback", None)
        cands = getattr(resp, "candidates", None) or []
        reason = str(getattr(getattr(cands[0], "finish_reason", None), "name", getattr(cands[0], "finish_reason", ""))
                     if cands else "")
        if feedback is not None and getattr(feedback, "block_reason", None):
            stop = "blocked"
        elif reason.endswith("MAX_TOKENS"):
            stop = "truncated"
        elif reason.split(".")[-1] in BLOCKED or not cands:
            stop = "blocked"
        text = ""
        if stop == "ok":
            parts = getattr(getattr(cands[0], "content", None), "parts", None) or []
            text = "".join(getattr(p, "text", "") or "" for p in parts if not getattr(p, "thought", False))
        return Reply(text=text, input_tokens=max(prompt - cached, 0), output_tokens=out, cache_read_tokens=cached,
                     served_model=self.model, request_id=getattr(resp, "response_id", "") or "", stop=stop)
