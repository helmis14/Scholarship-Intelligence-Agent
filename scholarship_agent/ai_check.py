"""Second reading (round 43): an independent model reads the page and gives its own four decisions; every decision the
rules answered and the model reads differently is held for review. The model never replaces a value, it can only
withhold one, so a wrong model answer costs an answer, never adds a wrong claim.

Usage: attach_second_reading(opp, page_text, llm, today) before audit.field_status(); field_status() then holds the
fields that disagree. Paid calls follow the provider's own switches and budgets (ANTHROPIC_ALLOW_PAID and the
per-run caps in anthropic_llm.py); without them the call is a dry run and nothing is held.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

CHECK_FIELDS = {
    "nationality": "who may apply by citizenship: 'any', 'include: <ISO alpha-2 codes, comma separated>', "
                   "'exclude: <codes>', or 'not_stated'. Fee status, residence, enrolment, refugee status, region names "
                   "without a list of countries and preferences are not_stated.",
    "funding_class": "one of: fully_funded (tuition AND living costs covered), partially_funded (a share, discount, cap "
                     "or fixed amount towards costs), tuition_funded (tuition only), stipend_only (a regular living "
                     "allowance only), not_stated (an amount whose use is not stated, or nothing said)",
    "deadline": "the applicant's application deadline(s) for this programme as YYYY-MM-DD, comma separated, only dates "
                "with a year written on the page; not_stated when there is none. Not openings, events, webinars, "
                "programme start dates, results or nomination steps.",
}
SYSTEM = ("You check scholarship facts. Read only the page text given. For each field give the value the page states and "
          "a short exact quotation from the page that shows it (empty quotation for not_stated). Do not guess.")
MAX_CHARS = 14000


def _codes(v: str) -> set[str]:
    from .countries import mentions
    alias = {"UK": "GB", "EL": "GR"}   # common non-ISO short forms
    codes = {alias.get(c.strip().upper(), c.strip().upper()) for c in re.split(r"[,;\s]+", v)
             if re.fullmatch(r"[A-Za-z]{2}", c.strip())}
    return codes or set(mentions(v))   # a model may answer with country names instead of codes


def _norm(v: str) -> str:
    return re.sub(r"[\s-]+", "_", (v or "").strip().lower())


def second_reading(page_text: str, url: str, llm, today: date) -> Optional[dict]:
    """The model's four values, or None when there is no answer (dry run, budget, error)."""
    user = (f"TODAY: {today.isoformat()}\nURL: {url}\n\nPAGE TEXT:\n{page_text[:MAX_CHARS]}\n\n"
            "Fields:\n" + "\n".join(f"- {k}: {v}" for k, v in CHECK_FIELDS.items())
            + '\n\nAnswer as JSON: {"fields": [{"field": "<name>", "value": "<value>", "quote": "<exact quotation>"}]}')
    try:
        try:
            data = llm.complete_json(SYSTEM, user, fields=CHECK_FIELDS, meta={"purpose": "second_reading", "source_url": url})
        except TypeError:   # local providers (Ollama, OpenAI-compatible) take only the two prompts
            data = llm.complete_json(SYSTEM, user)
    except Exception:   # dry run, budget, refusal, network: the rules' answer stands
        return None
    items = (data or {}).get("fields")
    if not isinstance(items, list):   # {"nationality": ..., "funding_class": ...} from a model without a schema
        items = [{"field": k, "value": v} for k, v in (data or {}).items()]
    out = {}
    for item in items:
        if isinstance(item, dict) and item.get("field") in CHECK_FIELDS:
            v = item.get("value")
            f = item["field"]
            out[f] = ", ".join(map(str, v)) if isinstance(v, list) else str(v).strip()
            # round 45: a value whose quotation is not on the page is a guess; it may not hold the rules' answer
            out[f + "_quote_ok"] = _silent(out[f]) or quote_on_page(str(item.get("quote") or ""), page_text)
    return out or None


def _flat(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\u2018\u2019\u201c\u201d\"'`]", "", t or "")).strip().lower()


def quote_on_page(quote: str, page_text: str) -> bool:
    """Every part of the quotation (split at ellipses) of 12 or more characters appears in the page text."""
    page = _flat(page_text)
    parts = [p for p in (_flat(x) for x in re.split(r"\.\.\.|\u2026", quote)) if len(p) >= 12]
    return bool(parts) and all(p in page for p in parts)


NOT_A_CLAIM = ("not_stated", "needs_review", "unsupported", "funding_unclear")
# a second reading that finds nothing ("not_stated") holds these answers: the rules may have read a country, a funding
# class or a date into text that does not state one. A past deadline makes a cycle "closed" even when the page never says
# so, which a reader that only quotes statements will not repeat, so silence does not hold a cycle.
SILENCE_HOLDS = {"eligible_countries": True, "funding_type": True, "deadline": True}


def _silent(v: str) -> bool:
    return _norm(v) in ("", "not_stated", "none", "unknown", "n/a", "null")


def _confirms(ours: set, theirs: set) -> bool:
    # every country the rules name is in the second reading's list (a reader may also list the countries a rule
    # leaves open, or copy a long list with a slip)
    missing = ours - theirs
    return not missing or (len(ours) >= 10 and len(missing) <= len(ours) // 10)


def disagreements(o, out: dict, reading: dict, today: date) -> dict[str, str]:
    """field_status key -> what the second reading says, for every answered decision it reads differently."""
    from .models import DeadlineKind
    held = {}
    n = o.nationality
    if out["eligible_countries"]["state"] == "present" and "nationality" in reading and reading.get("nationality_quote_ok", True):
        r = reading["nationality"].lower()
        mode = "any" if r.startswith("any") else "include" if r.startswith("include") else \
            "exclude" if r.startswith("exclude") else "not_stated"
        if mode == "not_stated" and (not SILENCE_HOLDS["eligible_countries"] or n.mode == "exclude"):
            pass   # exclusions are often worded as fee rules ("EU citizens pay no fees"), which the reader is told to skip
        elif mode != n.mode or (mode in ("include", "exclude")
                                and not _confirms(set(n.countries), _codes(r.split(":", 1)[-1]))):
            held["eligible_countries"] = reading["nationality"]
    if out["funding_type"]["state"] not in NOT_A_CLAIM and "funding_class" in reading and reading.get("funding_class_quote_ok", True):
        theirs = reading["funding_class"]
        if not (_silent(theirs) and not SILENCE_HOLDS["funding_type"]) and _norm(theirs) != out["funding_type"]["state"]:
            held["funding_type"] = theirs
    mine = {d.date for d in o.deadlines if d.date and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)}
    if mine and out["deadline"]["state"] not in ("needs_review", "unsupported") and "deadline" in reading \
            and reading.get("deadline_quote_ok", True):
        theirs = set(re.findall(r"\d{4}-\d{2}-\d{2}", reading["deadline"]))
        if not (not theirs and not SILENCE_HOLDS["deadline"]) and theirs != mine:
            held["deadline"] = reading["deadline"]
            # the cycle is read from these dates (audit.cycle_status), so it is held with them; a reader is not asked
            # for the cycle itself because comparing dates with today is where small models slip
            if out["cycle"]["state"] in ("open", "closed", "upcoming") and \
                    re.match(r"(closes|opens|last deadline)", out["cycle"].get("detail", "")):
                held["cycle"] = "depends on the held deadline"
    return held


def attach_second_reading(o, page_text: str, llm, today: date) -> Optional[dict]:
    o.second_reading = second_reading(page_text, o.info_url or "", llm, today)
    return o.second_reading


def apply(o, out: dict, today: date) -> None:
    """Called by audit.field_status: hold the decisions the second reading disagrees with."""
    reading = getattr(o, "second_reading", None)
    if not reading:
        return
    for f, theirs in disagreements(o, out, reading, today).items():
        out[f] = {"state": "needs_review",
                  "detail": f"{out[f]['state']}, but a second reading of the page says {theirs[:120]!r}; check the quotation"}
