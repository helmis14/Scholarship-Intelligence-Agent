"""Shared machinery for paid cloud LLM providers (Anthropic, Gemini).

Each provider subclass only builds its SDK client and sends one request (`_call`). Everything that protects the
user's money and the evidence rules lives here, identically for every provider:

- dry run unless `<PREFIX>_ALLOW_PAID=1`: requests are estimated (tokens, USD) and not sent;
- per-run budgets `<PREFIX>_MAX_REQUESTS_PER_RUN`, `_MAX_INPUT_TOKENS_PER_RUN`, `_MAX_OUTPUT_TOKENS_PER_RUN`,
  `_MAX_ESTIMATED_COST_USD`, default 0; a request whose worst case would cross one is refused before sending;
- a cache keyed by provider + model + prompt version + prompt + page text, so unchanged pages are never paid twice;
- a usage ledger (counts, latency and estimated USD only; never page text, profile data or keys);
- the response is validated against the field schema here, whatever the API promised.

The model's answer is only a proposal: ai_extract.enrich() quote-checks every value and verify.py decides what an
official page confirms.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

PROMPT_VERSION = "extract-v2"   # bump whenever SYSTEM or FIELDS change, so cached answers are not reused
CHARS_PER_TOKEN = 3.5   # rough, for dry-run estimates; real counts come from the provider's usage report


class CloudConfigError(ValueError):
    """Missing or invalid configuration (no key, no budget, unknown price, bad number)."""


class BudgetExceeded(RuntimeError):
    pass


class PaidCallsDisabled(RuntimeError):
    pass


def int_env(name: str, default: int, err=CloudConfigError) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except ValueError:
        raise err(f"{name} must be a number") from None


def float_env(name: str, default: float, err=CloudConfigError) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        raise err(f"{name} must be a number") from None


@dataclass
class Budget:
    max_requests: int = 0
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_cost_usd: float = 0.0
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    dry_run_requests: int = 0
    dry_run_input_tokens: int = 0
    dry_run_cost_usd: float = 0.0
    dry_run_worst_cost_usd: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_env(cls, prefix: str = "ANTHROPIC", err=CloudConfigError) -> "Budget":
        return cls(int_env(f"{prefix}_MAX_REQUESTS_PER_RUN", 0, err), int_env(f"{prefix}_MAX_INPUT_TOKENS_PER_RUN", 0, err),
                   int_env(f"{prefix}_MAX_OUTPUT_TOKENS_PER_RUN", 0, err),
                   float_env(f"{prefix}_MAX_ESTIMATED_COST_USD", 0, err))

    def reserve(self, est_in: int, max_out: int, est_cost: float) -> None:
        """Refuse a request whose worst case would cross any limit."""
        with self.lock:
            if self.requests + 1 > self.max_requests:
                raise BudgetExceeded(f"request budget reached ({self.requests}/{self.max_requests})")
            if self.input_tokens + est_in > self.max_input_tokens:
                raise BudgetExceeded(f"input-token budget would be exceeded ({self.input_tokens}+{est_in} > {self.max_input_tokens})")
            if self.output_tokens + max_out > self.max_output_tokens:
                raise BudgetExceeded(f"output-token budget would be exceeded ({self.output_tokens}+{max_out} > {self.max_output_tokens})")
            if self.cost_usd + est_cost > self.max_cost_usd:
                raise BudgetExceeded(f"cost budget would be exceeded (${self.cost_usd:.4f}+${est_cost:.4f} > ${self.max_cost_usd:.2f})")
            self.requests += 1

    def record(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        with self.lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.cost_usd += cost

    def summary(self) -> dict:
        return {"paid": {"requests": self.requests, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                         "estimated_cost_usd": round(self.cost_usd, 6)},
                "dry_run": {"requests": self.dry_run_requests, "estimated_input_tokens": self.dry_run_input_tokens,
                            "estimated_cost_usd": round(self.dry_run_cost_usd, 6),
                            "worst_case_cost_usd": round(self.dry_run_worst_cost_usd, 6),
                            "note": "dry-run input tokens estimated at ~3.5 characters per token and 800 output "
                                    "tokens per request (worst case: the full output cap); actual counts differ"},
                "limits": {"requests": self.max_requests, "input_tokens": self.max_input_tokens,
                           "output_tokens": self.max_output_tokens, "cost_usd": self.max_cost_usd}}


def response_schema(fields: dict) -> dict:
    value = {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"},
                       {"type": "array", "items": {"type": "string"}}]}
    return {"type": "object", "additionalProperties": False, "required": ["fields"],
            "properties": {"fields": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["field", "value", "quote"],
                "properties": {"field": {"type": "string", "enum": sorted(fields)}, "value": value,
                               "quote": {"type": "string"}}}}}}


def validate_response(data: Any, fields: dict) -> list[dict]:
    """Shape check on what came back (the API schema guarantee is not trusted blindly)."""
    if not isinstance(data, dict) or not isinstance(data.get("fields"), list):
        raise ValueError("response is not an object with a 'fields' list")
    out = []
    for item in data["fields"]:
        if not isinstance(item, dict) or set(item) - {"field", "value", "quote"}:
            continue
        if item.get("field") not in fields or not isinstance(item.get("quote"), str):
            continue
        out.append(item)
    return out


@dataclass
class Reply:
    """One provider response, reduced to what the shared code needs."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0          # includes thinking tokens where the provider bills them as output
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    served_model: str = ""
    request_id: str = ""
    stop: str = "ok"                # ok | refusal | truncated | blocked


class CloudLLM:
    """LLM for ai_extract.enrich(): complete_json(system, user) -> {"fields": [...]}. Subclasses set the class
    attributes and implement _make_client() and _call()."""
    provider = ""
    prefix = ""                     # environment prefix: ANTHROPIC, GEMINI
    key_env: tuple = ()             # variables the key may come from, first wins
    prices: dict = {}
    default_model = ""
    ConfigError = CloudConfigError

    def __init__(self, client_factory: Optional[Callable[..., Any]] = None, model: Optional[str] = None,
                 budget: Optional[Budget] = None, allow_paid: Optional[bool] = None, store=None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        p = self.prefix
        self._key = next((os.environ[k] for k in self.key_env if os.environ.get(k)), "")
        self.model = model or os.environ.get(f"{p}_MODEL") or self.default_model
        self.name = f"{self.provider}:{self.model}"
        self.allow_paid = (os.environ.get(f"{p}_ALLOW_PAID", "") == "1") if allow_paid is None else allow_paid
        self.budget = budget or Budget.from_env(p, self.ConfigError)
        self.max_tokens = int_env(f"{p}_MAX_TOKENS", 4000, self.ConfigError)
        self.timeout = float_env(f"{p}_TIMEOUT_SECONDS", 120, self.ConfigError)
        self.max_retries = int_env(f"{p}_MAX_RETRIES", 3, self.ConfigError)
        self.sem = threading.Semaphore(max(1, int_env(f"{p}_MAX_CONCURRENCY", 2, self.ConfigError)))
        self.store = store
        self.sleep = sleep
        self.clock = clock
        self.price(self.model)  # fail early when the cost of this model cannot be estimated
        self._client = None
        self._factory = client_factory
        if self.allow_paid and not self._key:
            raise self.ConfigError(f"AI_PROVIDER={self.provider} with {p}_ALLOW_PAID=1 needs "
                                   f"{' or '.join(self.key_env)}")
        self.calls: list[dict] = []   # per-request ledger (counts only)
        self._meta: dict = {}

    # -- pricing --------------------------------------------------------------------------------------------
    @classmethod
    def price(cls, model: str) -> tuple[float, float]:
        p, self = cls.prefix, cls
        if os.environ.get(f"{p}_PRICE_INPUT_PER_MTOK") and os.environ.get(f"{p}_PRICE_OUTPUT_PER_MTOK"):
            return (float_env(f"{p}_PRICE_INPUT_PER_MTOK", 0, self.ConfigError),
                    float_env(f"{p}_PRICE_OUTPUT_PER_MTOK", 0, self.ConfigError))
        if model not in self.prices:
            raise self.ConfigError(f"no price known for {model!r}: set {p}_PRICE_INPUT_PER_MTOK and "
                                   f"{p}_PRICE_OUTPUT_PER_MTOK so the cost budget can be enforced")
        return self.prices[model]

    @classmethod
    def cost(cls, model: str, r: Reply) -> float:
        pin, pout = cls.price(model)
        return (r.input_tokens * pin + r.cache_read_tokens * pin * 0.1 + r.cache_write_tokens * pin * 1.25
                + r.output_tokens * pout) / 1e6

    def estimate(self, system: str, user: str) -> dict:
        return self._estimate_with_input(int((len(system) + len(user)) / CHARS_PER_TOKEN) + 400)  # + schema/framing

    def _estimate_with_input(self, est_in: int) -> dict:
        pin, pout = self.price(self.model)
        typical = min(self.max_tokens, 800)
        return {"input_tokens": est_in, "max_output_tokens": self.max_tokens,
                "worst_case_cost_usd": round((est_in * pin + self.max_tokens * pout) / 1e6, 6),
                "typical_cost_usd": round((est_in * pin + typical * pout) / 1e6, 6)}

    # -- client ---------------------------------------------------------------------------------------------
    def client(self):
        if self._client is None:
            self._client = self._factory() if self._factory is not None else self._make_client()
        return self._client

    def _make_client(self):
        raise NotImplementedError

    def count_input_tokens(self, system: str, user: str, fields: dict) -> Optional[int]:
        """The provider's exact input-token count, when it offers a free counting endpoint; else None."""
        return None

    def charge_uncertain_attempt(self) -> None:
        """A request that may have been processed but returned no usage (timeout, dropped connection): book its
        worst case so the budget can only be overestimated, never exceeded."""
        est = getattr(self, "_current_est", None)
        if est:
            self.budget.record(est["input_tokens"], self.max_tokens, est["worst_case_cost_usd"])
            self._ledger({"status": "uncertain_charged_worst_case", "input_tokens": est["input_tokens"],
                          "output_tokens": self.max_tokens, "cost_usd": est["worst_case_cost_usd"]})

    def reserve_retry(self) -> None:
        """Every retry is a new request: it counts against the request budget and is checked like the first."""
        est = self._current_est
        self._check_total(est["worst_case_cost_usd"])
        self.budget.reserve(est["input_tokens"], self.max_tokens, est["worst_case_cost_usd"])

    def _check_total(self, worst: float) -> None:
        """Optional cap across runs: <PREFIX>_MAX_TOTAL_COST_USD against everything in this data directory's ledger."""
        cap = float_env(f"{self.prefix}_MAX_TOTAL_COST_USD", 0, self.ConfigError)
        if cap <= 0 or self.store is None:
            return
        spent_before = self.store.catalog.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE provider = ?", (self.provider,)).fetchone()[0]
        # this run's own rows are in the ledger already; budget.cost_usd covers rows not yet written
        if spent_before + worst > cap:
            raise BudgetExceeded(f"total cost cap would be exceeded (${spent_before:.4f} spent + ${worst:.4f} > ${cap:.2f})")

    def _call(self, system: str, user: str, fields: dict) -> Reply:
        raise NotImplementedError

    # -- cache and ledger -----------------------------------------------------------------------------------
    def _cache_key(self, system: str, user: str) -> str:
        return hashlib.sha256("\x1f".join([self.provider, self.model, PROMPT_VERSION, system, user]).encode()).hexdigest()

    def _cached(self, key: str):
        if self.store is None:
            return None
        row = self.store.catalog.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row["response"]) if row else None

    def _cache_put(self, key: str, data: dict) -> None:
        if self.store is not None:
            with self.store.catalog as c:
                c.execute("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?)", (key, self.name, json.dumps(data),
                                                                             time.strftime("%Y-%m-%dT%H:%M:%SZ")))

    def _ledger(self, entry: dict) -> None:
        entry = entry | {k: v for k, v in (self._meta or {}).items() if k not in entry}
        self.calls.append(entry)
        if self.store is not None:
            with self.store.catalog as c:
                c.execute("INSERT INTO llm_usage (provider, model, at, status, input_tokens, output_tokens, "
                          "cache_read_tokens, cost_usd, request_id, latency_ms, purpose, fields, source_url) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (self.provider, self.model, time.strftime("%Y-%m-%dT%H:%M:%SZ"), entry["status"],
                           entry.get("input_tokens", 0), entry.get("output_tokens", 0), entry.get("cache_read_tokens", 0),
                           entry.get("cost_usd", 0.0), entry.get("request_id", ""), entry.get("latency_ms"),
                           entry.get("purpose"), json.dumps(entry["fields"]) if entry.get("fields") else None,
                           entry.get("source_url")))

    # -- request --------------------------------------------------------------------------------------------
    def complete_json(self, system: str, user: str, fields: Optional[dict] = None, cache_key: Optional[str] = None,
                      meta: Optional[dict] = None) -> dict:
        """`cache_key` replaces the prompt-hash key (targeted requests build theirs from URL, content hash, schema
        version and fields); `meta` (purpose, fields, source_url) is written to the usage ledger: why it was sent."""
        from .ai_extract import FIELDS
        fields = fields or FIELDS
        self._meta = meta or {}
        key = cache_key or self._cache_key(system, user)
        hit = self._cached(key)
        if hit is not None:
            self._ledger({"status": "cache_hit"})
            return hit
        est = self.estimate(system, user)
        if self.allow_paid:
            counted = self.count_input_tokens(system, user, fields)
            if counted:
                # the provider's own count (+5%) replaces the character estimate when it is larger
                est = self._estimate_with_input(max(est["input_tokens"], int(counted * 1.05) + 50))
        if not self.allow_paid:
            with self.budget.lock:
                self.budget.dry_run_requests += 1
                self.budget.dry_run_input_tokens += est["input_tokens"]
                self.budget.dry_run_cost_usd += est["typical_cost_usd"]
                self.budget.dry_run_worst_cost_usd += est["worst_case_cost_usd"]
            self._ledger({"status": "dry_run", "input_tokens": est["input_tokens"]})
            raise PaidCallsDisabled(f"dry run: paid {self.provider} calls are off (set {self.prefix}_ALLOW_PAID=1); "
                                    f"this request would use ~{est['input_tokens']} input tokens, "
                                    f"up to ${est['worst_case_cost_usd']:.4f}")
        self._check_total(est["worst_case_cost_usd"])
        self.budget.reserve(est["input_tokens"], self.max_tokens, est["worst_case_cost_usd"])
        self._current_est = est
        t0 = self.clock()
        with self.sem:
            r = self._call(system, user, fields)
        latency = round((self.clock() - t0) * 1000, 1)
        served = r.served_model or self.model
        try:
            cost = self.cost(served, r)
        except CloudConfigError:
            # served by a fallback model without a known price: charge it at the dearest known price
            cost = max(self.cost(m, r) for m in self.prices)
        self.budget.record(r.input_tokens + r.cache_read_tokens + r.cache_write_tokens, r.output_tokens, cost)
        entry = {"status": "ok", "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                 "cache_read_tokens": r.cache_read_tokens, "cost_usd": round(cost, 6), "request_id": r.request_id,
                 "stop_reason": r.stop, "served_by": served, "latency_ms": latency}
        if r.stop in ("refusal", "blocked"):
            entry["status"] = r.stop
            self._ledger(entry)
            raise ValueError(f"model declined the request ({r.stop})")
        if r.stop == "truncated":
            entry["status"] = "truncated"
            self._ledger(entry)
            raise ValueError(f"response hit {self.prefix}_MAX_TOKENS before finishing; raise it")
        try:
            data = {"fields": validate_response(json.loads(r.text), fields)}
        except (ValueError, TypeError) as e:
            entry["status"] = "invalid_json"
            self._ledger(entry)
            raise ValueError(f"response failed validation: {e}") from None
        self._ledger(entry)
        self._cache_put(key, data)
        return data

    def usage(self) -> dict:
        s = self.budget.summary()
        s["provider"] = self.provider
        s["model"] = self.model
        s["paid_calls_enabled"] = self.allow_paid
        s["cache_hits"] = sum(1 for c in self.calls if c["status"] == "cache_hit")
        lat = [c["latency_ms"] for c in self.calls if c.get("latency_ms") is not None]
        s["latency_ms"] = {"requests": len(lat), "total": round(sum(lat), 1),
                           "mean": round(sum(lat) / len(lat), 1) if lat else None, "max": max(lat) if lat else None}
        return s
