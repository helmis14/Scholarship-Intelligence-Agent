"""Side-by-side evaluation of extraction modes on one held-out set: rules, rules + Claude, rules + Gemini
(and rules + Ollama on request). Same pages, same labels, same scoring (heldout.evaluate) for every mode.

A cloud mode is scored only when it really ran: its key is set and `<PREFIX>_ALLOW_PAID=1` with budgets above 0.
Otherwise the mode is reported as "not_run" with the dry-run estimate of what it would cost, and no scores, so
rules-only numbers can never be mistaken for a provider's. A run that stops at a budget is "partial".
"""

from __future__ import annotations

import time
from pathlib import Path

from .cloud_llm import BudgetExceeded, CloudConfigError, PaidCallsDisabled

KEYS = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
NOT_LABELLED = ["scholarship name and provider", "field of study", "academic (GPA) requirements", "academic cycle",
                "residency restrictions", "conflict handling"]


class _Recorder:
    """Wraps a provider to count which requests were sent, refused by budget, or dry-run."""

    def __init__(self, llm):
        self.llm, self.name = llm, llm.name
        self.outcomes: dict[str, int] = {}

    def complete_json(self, system, user):
        try:
            out = self.llm.complete_json(system, user)
            self._n("answered")
            return out
        except (BudgetExceeded, PaidCallsDisabled) as e:
            self._n(type(e).__name__)
            raise
        except Exception as e:
            self._n(f"error:{type(e).__name__}")
            raise

    def _n(self, k):
        self.outcomes[k] = self.outcomes.get(k, 0) + 1


def _summary(res: dict) -> dict:
    r, f = res["rates"], res["fields"]
    pick = lambda k: (r[k]["correct"], r[k]["total"]) if k in r else None  # noqa: E731
    return {
        "exact_match": {k: pick(k) for k in ("deadline_exact", "deadline_status", "nationality", "funding_amount",
                                             "funding_period", "stipend_present", "travel", "tuition", "age",
                                             "language", "duration", "page_kind") if k in r},
        "precision_recall_f1": {k: (v["precision"], v["recall"], v["f1"]) for k, v in f.items()},
        "unsupported": (res["unsupported_values"], res["scored_values"], res["unsupported_rate"]),
        "missing": (res["missing_values"], res["labelled_values"], res["missing_rate"]),
        "evidence_verbatim": (res["attribution"]["correct"], res["attribution"]["total"]),
    }


def _provider(name: str, store):
    import os
    if name == "anthropic":
        from .anthropic_llm import AnthropicLLM
        return AnthropicLLM(store=store)
    if name == "gemini":
        from .gemini_llm import GeminiLLM
        return GeminiLLM(store=store)
    if name == "ollama":
        from .ai_extract import OllamaLLM
        model = os.environ.get("OLLAMA_MODEL") or os.environ.get("SCHOLAR_LLM_MODEL")
        if not model:
            raise CloudConfigError("ollama needs OLLAMA_MODEL")
        return OllamaLLM(model)
    raise ValueError(f"unknown provider {name!r}: use rules, anthropic, gemini or ollama")


def compare(root: Path, providers: list[str], store=None, clock=time.monotonic, split=None) -> dict:
    from . import heldout
    out = {"set": str(root.name), "providers": {}, "not_labelled_in_this_set": NOT_LABELLED,
           "note": "every mode is scored by heldout.evaluate on the same pages and labels; cloud modes are scored "
                   "only when they actually ran"}
    for name in providers:
        t0 = clock()
        if name == "rules":
            res = heldout.evaluate(root, None, split=split)
            out["providers"]["rules"] = {"status": "run", "runtime_s": round(clock() - t0, 1), **_summary(res)}
            continue
        try:
            llm = _provider(name, store)
        except (CloudConfigError, ValueError) as e:
            out["providers"][name] = {"status": "not_run", "reason": f"configuration: {e}"}
            continue
        import os
        key_env = KEYS.get(name)
        paid_ready = key_env is None or (bool(os.environ.get(key_env)) and getattr(llm, "allow_paid", False))
        rec = _Recorder(llm)
        res = heldout.evaluate(root, rec, split=split)
        entry = {"runtime_s": round(clock() - t0, 1), "model": llm.name, "requests": rec.outcomes}
        if hasattr(llm, "usage"):
            entry["usage"] = llm.usage()
        if not paid_ready or rec.outcomes.get("PaidCallsDisabled"):
            why = []
            if key_env and not os.environ.get(key_env):
                why.append(f"{key_env} not set")
            if not getattr(llm, "allow_paid", True):
                why.append(f"{llm.prefix}_ALLOW_PAID is not 1")
            entry.update(status="not_run", reason="; ".join(why) or "paid calls disabled",
                         estimate=entry.get("usage", {}).get("dry_run"))
            entry.pop("usage", None)
        elif not rec.outcomes.get("answered"):
            entry.update(status="failed", reason="no request was answered", ai=res.get("ai"))
        else:
            stopped = rec.outcomes.get("BudgetExceeded", 0)
            entry.update(status="partial" if stopped else "run", ai=res.get("ai"), **_summary(res))
            if stopped:
                entry["reason"] = f"budget reached: {stopped} page(s) were scored with rules only"
        out["providers"][name] = entry
    return out
