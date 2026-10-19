"""Upstream-engine health for SearXNG: which engines answer, which are cooling down and until when, and how fast
the agent may send the next query.

The agent never works around a block. An engine that reports "too many requests", "access denied", a CAPTCHA or a
network-level failure is left alone for a cooldown period (at least as long as SearXNG's own suspension), each
query goes to only a few healthy engines (so no single engine sees every query), the interval between queries
grows after every throttle signal and shrinks slowly after clean answers, and when no engine is available the run
stops at a checkpoint instead of retrying.
"""

from __future__ import annotations

import re
import time
from typing import Callable, Optional

# general web engines worth asking for scholarship queries, in order of preference
GENERAL = ["google cse", "bing", "brave", "google", "yahoo", "yep", "mwmbl", "qwant", "duckduckgo"]
# engines with their own index for a language: tried first for queries in it
LANGUAGE_ENGINES = {"ko": ["naver"], "cs": ["seznam"], "ru": ["yandex"]}
# (reason pattern, cooldown seconds, kind)
COOLDOWNS = [(r"too many requests|429|rate.?limit", 3600, "rate_limited"),
             (r"captcha", 86400, "captcha"),
             (r"access denied|forbidden|403", 86400, "access_denied"),
             (r"ssl|certificate", 86400, "network_blocked"),
             (r"connection error|timeout|timed out|unreachable", 1800, "unreachable")]


class EnginesUnavailable(Exception):
    """Every usable engine is cooling down; `ready_at` is the earliest time one becomes available again."""

    def __init__(self, ready_at: Optional[float], states: dict):
        self.ready_at, self.states = ready_at, states
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(ready_at)) if ready_at else "unknown"
        super().__init__(f"all search engines are cooling down (earliest ready {when})")


def classify(reason: str) -> tuple[int, str]:
    for rx, secs, kind in COOLDOWNS:
        if re.search(rx, reason or "", re.I):
            return secs, kind
    return 900, "failing"


class EnginePool:
    def __init__(self, available: Optional[list[str]] = None, per_query: int = 2, store=None,
                 clock: Callable[[], float] = time.time, base_interval: float = 3.0, max_interval: float = 60.0):
        self.available = [e for e in GENERAL + sum(LANGUAGE_ENGINES.values(), []) if available is None or e in available]
        self.per_query, self.store, self.clock = per_query, store, clock
        self.base, self.max = base_interval, max_interval
        self.interval = base_interval
        self.state: dict[str, dict] = {}
        self._turn = 0
        if store is not None:
            for r in store.catalog.execute("SELECT * FROM engine_health"):
                self.state[r["engine"]] = {"kind": r["kind"], "reason": r["reason"], "until": r["until"] or 0,
                                           "ok": r["ok"] or 0, "failed": r["failed"] or 0, "last_ok": r["last_ok"]}

    def _s(self, e: str) -> dict:
        return self.state.setdefault(e, {"kind": "ok", "reason": "", "until": 0, "ok": 0, "failed": 0, "last_ok": None})

    def healthy(self) -> list[str]:
        now = self.clock()
        return [e for e in self.available if self._s(e)["until"] <= now]

    def pick(self, lang: str = "en") -> list[str]:
        """Healthy engines for one query: the language's own engines first, then general ones in rotation."""
        ok = self.healthy()
        if not ok:
            ready = min((self._s(e)["until"] for e in self.available), default=None)
            raise EnginesUnavailable(ready, self.snapshot())
        own = [e for e in LANGUAGE_ENGINES.get(lang, []) if e in ok]
        general = [e for e in ok if e not in sum(LANGUAGE_ENGINES.values(), [])]
        if general:
            k = self._turn % len(general)
            general = general[k:] + general[:k]
            self._turn += 1
        return (own + general)[:max(self.per_query, len(own) + 1)]

    def record(self, used: list[str], answered: set, unresponsive: list) -> None:
        """Update health from one SearXNG answer and adapt the interval."""
        now = self.clock()
        throttled = False
        for name, reason in unresponsive:
            if name not in self.available:
                continue
            secs, kind = classify(reason)
            s = self._s(name)
            s.update(kind=kind, reason=str(reason)[:120], until=max(s["until"], now + secs))
            s["failed"] += 1
            throttled = throttled or kind in ("rate_limited", "captcha", "access_denied")
            self._save(name)
        for name in used:
            if name in answered:
                s = self._s(name)
                s["ok"] += 1
                s["last_ok"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
                if s["until"] <= now:
                    s.update(kind="ok", reason="")
                self._save(name)
        # adaptive pacing: back off fast on throttling, recover slowly on clean answers
        self.interval = min(self.max, self.interval * 2) if throttled else max(self.base, self.interval / 1.25)

    def _save(self, e: str) -> None:
        if self.store is None:
            return
        s = self.state[e]
        with self.store.catalog as c:
            c.execute("INSERT OR REPLACE INTO engine_health VALUES (?,?,?,?,?,?,?)",
                      (e, s["kind"], s["reason"], s["until"], s["ok"], s["failed"], s["last_ok"]))

    def snapshot(self) -> dict:
        now = self.clock()
        return {e: {"status": "ready" if self._s(e)["until"] <= now else self._s(e)["kind"],
                    "reason": self._s(e)["reason"],
                    "ready_in_minutes": max(0, round((self._s(e)["until"] - now) / 60)),
                    "answers": self._s(e)["ok"], "failures": self._s(e)["failed"]} for e in self.available}


def searxng_engines(base: str, get=None) -> Optional[list[str]]:
    """Engines the instance has enabled (from /config), or None when it cannot be read."""
    from .search import _json_get
    try:
        doc = (get or _json_get)(f"{base.rstrip('/')}/config", {"Accept": "application/json"})
        return [e["name"] for e in doc.get("engines", []) if e.get("enabled")]
    except Exception:
        return None

