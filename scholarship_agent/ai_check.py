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
    # round 46: the cycle, the decision most often wrong after the first three were checked. Asked only with
    # SCHOLAR_SECOND_READING_STATUS=1: on sets K to X it cut wrong claims from 2.64% to 2.18% of answered decisions but
    # held 29 right answers for review, a lower utility, so it is a stricter option rather than the default.
    "application_status": "whether applicants can apply as of TODAY: open (the page says applications are open, or an "
                          "applicant deadline with a year is on or after TODAY and no later opening date is given), closed "
                          "(the page says applications are closed, or every applicant deadline with a year is before TODAY), "
                          "upcoming (the page gives an opening date after TODAY), not_announced (the page says the next round "
                          "or its dates will be announced later), rolling (applications are accepted at any time), or "
                          "not_stated",
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


def asked_fields() -> dict:
    import os
    if os.environ.get("SCHOLAR_SECOND_READING_STATUS") == "1":
        return CHECK_FIELDS
    return {k: v for k, v in CHECK_FIELDS.items() if k != "application_status"}


def second_reading(page_text: str, url: str, llm, today: date) -> Optional[dict]:
    """The model's values, or None when there is no answer (dry run, budget, error)."""
    fields = asked_fields()
    user = (f"TODAY: {today.isoformat()}\nURL: {url}\n\nPAGE TEXT:\n{page_text[:MAX_CHARS]}\n\n"
            "Fields:\n" + "\n".join(f"- {k}: {v}" for k, v in fields.items())
            + '\n\nAnswer as JSON: {"fields": [{"field": "<name>", "value": "<value>", "quote": "<exact quotation>"}]}')
    try:
        try:
            data = llm.complete_json(SYSTEM, user, fields=fields, meta={"purpose": "second_reading", "source_url": url})
        except TypeError:   # local providers (Ollama, OpenAI-compatible) take only the two prompts
            data = llm.complete_json(SYSTEM, user)
    except Exception:   # dry run, budget, refusal, network: the rules' answer stands
        return None
    items = (data or {}).get("fields")
    if not isinstance(items, list):   # {"nationality": ..., "funding_class": ...} from a model without a schema
        items = [{"field": k, "value": v} for k, v in (data or {}).items()]
    out = {}
    for item in items:
        if isinstance(item, dict) and item.get("field") in fields:
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
# class, a date or a cycle into text that does not state one. The reader is given today's date and told that a past
# deadline means closed (round 46), so its silence on the status also holds a cycle.
SILENCE_HOLDS = {"eligible_countries": True, "funding_type": True, "deadline": True, "cycle": True}
CYCLE_STATES = ("open", "closed", "upcoming", "not_announced", "rolling")


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
    # round 46: the cycle. A reading of the status that differs from the rules' cycle holds it; the reader is told
    # today's date, so a past deadline reads as closed for both.
    if out["cycle"]["state"] in CYCLE_STATES and "application_status" in reading \
            and reading.get("application_status_quote_ok", True):
        theirs = _norm(reading["application_status"])
        theirs = "not_stated" if _silent(theirs) else theirs
        if theirs != out["cycle"]["state"] and (theirs in CYCLE_STATES or SILENCE_HOLDS["cycle"]):
            held["cycle"] = reading["application_status"]
    mine = {d.date for d in o.deadlines if d.date and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)}
    if mine and out["deadline"]["state"] not in ("needs_review", "unsupported") and "deadline" in reading \
            and reading.get("deadline_quote_ok", True):
        theirs = set(re.findall(r"\d{4}-\d{2}-\d{2}", reading["deadline"]))
        if not (not theirs and not SILENCE_HOLDS["deadline"]) and theirs != mine:
            held["deadline"] = reading["deadline"]
            # the cycle is read from these dates (audit.cycle_status), so it is held with them; a reader is not asked
            # for the cycle itself because comparing dates with today is where small models slip
            if out["cycle"]["state"] in ("open", "closed", "upcoming") and "cycle" not in held and \
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


def check_catalog(store, fetcher, llm, today: date, limit: int = 0, refresh: bool = False) -> dict:
    """Round 49: the second reading for stored records, so the site holds what an independent reading disagrees with.
    The catalogue keeps no page text, so each record's own page is fetched again (robots and rate limits apply) and
    read once. Records of a structured dataset (adapter:...) are left out: their decisions come from the dataset, not
    from one page. A failed request is skipped; three in a row (a dry run, a budget stop) end the run, keeping what was stored."""
    from .extract import page_from_response
    from .net import FetchError
    from .normalize import dedup_key, normalize_url
    todo = [o for o in store.list_opportunities()
            if not o.discovered_via.startswith("adapter:") and (refresh or not o.second_reading)]
    if limit:
        todo = todo[:limit]
    done, unreadable, failed, stopped = 0, 0, 0, ""
    misses = 0   # answers missing in a row: one failed request is skipped, a budget stop ends the run
    for o in todo:
        try:
            page = page_from_response(fetcher.get(o.info_url))
        except FetchError:
            unreadable += 1
            continue
        if len(page.text) < 300:   # an empty shell or a script-only page: nothing to read
            unreadable += 1
            continue
        if attach_second_reading(o, page.text, llm, today) is None:
            failed, misses = failed + 1, misses + 1
            if misses >= 3:
                stopped = "no answer from the model three times in a row (dry run, budget reached or requests failing)"
                break
            continue
        misses = 0
        store.save_opportunity(o, dedup_key(o.title, o.provider_name), normalize_url(o.info_url))
        done += 1
    return {"records_to_check": len(todo), "checked": done, "page_unreadable": unreadable, "no_answer": failed,
            "stopped": stopped or None}
