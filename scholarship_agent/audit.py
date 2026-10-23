"""Catalog audit: for each record and each key field, is the value there, and if not, why not.

States (one per field):
  present         the official page states it
  approximate     only an approximate date ("usually in November")
  outdated        only a past cycle's value is known
  needs_review    stated but ambiguous; a person decides
  not_published   the page says it is not announced yet ("to be announced")
  not_applicable  the field does not apply (rolling admission has no closing date; an admission programme
                  carries no funding)
  not_stated      the page is silent: unknown, never assumed
  unofficial      (official_source only) the record rests on a non-official page
"""

from __future__ import annotations

import re

from datetime import date
from typing import Optional

from .models import DeadlineCertainty, DeadlineKind, Opportunity

FIELDS = ("page_type", "programme_identity", "official_source", "eligible_countries", "cycle", "funding_type", "study_levels", "funding_components", "application_period",
          "deadline", "verification")
APPLICANT_KINDS = {DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION, DeadlineKind.OTHER}
NO_FUNDING_TYPES = {"admission_programme"}


def _s(state: str, detail: str = "") -> dict:
    return {"state": state, "detail": detail} if detail else {"state": state}


def field_status(o: Opportunity, today: Optional[date] = None) -> dict[str, dict]:
    from .freshness import record_authority
    from .evidence import is_official
    today = today or date.today()
    out: dict[str, dict] = {}

    auth = record_authority(o)
    out["official_source"] = (_s("present", o.info_url) if o.info_url and is_official(auth)
                              else _s("unofficial", auth) if o.info_url else _s("not_stated"))

    n = o.nationality
    if n.mode in ("any", "include", "exclude"):
        out["eligible_countries"] = _s("present", n.mode + (":" + ",".join(n.countries) if n.countries else ""))
    elif (n.note or "").startswith("needs review"):
        out["eligible_countries"] = _s("needs_review", n.note)
    else:
        out["eligible_countries"] = _s("not_stated")

    out["study_levels"] = _s("present", ",".join(o.study_levels)) if o.study_levels else _s("not_stated")

    if any(c.covered for c in o.funding):
        out["funding_components"] = _s("present", ",".join(c.kind for c in o.funding if c.covered))
    elif o.funding:
        out["funding_components"] = _s("needs_review", "mentioned without saying what is covered")
    elif o.opportunity_type in NO_FUNDING_TYPES:
        out["funding_components"] = _s("not_applicable", o.opportunity_type)
    else:
        out["funding_components"] = _s("not_stated")

    rolling = any(d.kind == DeadlineKind.ROLLING for d in o.deadlines)
    opening = [d for d in o.deadlines if d.kind == DeadlineKind.OPENING]
    if any(d.date for d in opening):
        out["application_period"] = _s("present", max(d.date for d in opening if d.date))
    elif rolling:
        out["application_period"] = _s("not_applicable", "rolling admission")
    elif any(d.approximate == "not yet published" for d in opening):
        out["application_period"] = _s("not_published")
    else:
        out["application_period"] = _s("not_stated")

    appl = [d for d in o.deadlines if d.kind in APPLICANT_KINDS]
    current = [d for d in appl if d.date and d.certainty == DeadlineCertainty.CONFIRMED
               and date.fromisoformat(d.date) >= today]
    if current:
        out["deadline"] = _s("present", min(d.date for d in current))
    elif rolling:
        out["deadline"] = _s("not_applicable", "rolling admission")
    elif any(d.date for d in appl):
        out["deadline"] = _s("outdated", max(d.date for d in appl if d.date))
    elif any(d.approximate == CLOSED_NOTE for d in appl):
        out["deadline"] = _s("outdated", "the page says the call is closed; no date stated")
    elif any(d.approximate == UNAVAILABLE_NOTE for d in appl):
        out["deadline"] = _s("not_published", "the page says the programme is currently unavailable")
    elif any(d.certainty == DeadlineCertainty.EXPECTED or (d.approximate and d.approximate != "not yet published")
             for d in appl):
        out["deadline"] = _s("approximate", next(d.approximate for d in appl if d.approximate))
    elif any(d.approximate == "not yet published" for d in appl):
        out["deadline"] = _s("not_published")
    elif any(d.kind == DeadlineKind.INSTITUTIONAL for d in o.deadlines):
        out["deadline"] = _s("not_stated", "only a date for institutions, none for applicants")
    else:
        out["deadline"] = _s("not_stated")

    out["verification"] = _s(str(o.verification_status), o.verification_reason)
    out["cycle"] = cycle_status(o, today)
    out["funding_type"] = funding_type(o)
    _programme_specific(o, out)
    _require_evidence(o, out)
    _decision_evidence_gate(o, out)
    _risk_gate(o, out)
    from .ai_check import apply as _second_reading
    _second_reading(o, out, today)   # round 43: hold what an independent reading disagrees with
    # what the page is, and whether the record stands for one named programme (identity.py); domain trust alone
    # (official_source) never makes a record a verified programme
    from .identity import record_identity
    out["page_type"] = _s(o.page_type or "unknown")
    idn = record_identity(o)
    out["programme_identity"] = _s(idn["state"], "; ".join(idn["reasons"]))
    return out


from .extract import CLOSED_NOTE, UNAVAILABLE_NOTE  # noqa: E402


def cycle_status(o: Opportunity, today: date) -> dict:
    """Where the application cycle stands, from the applicant dates the official pages state:
    open (a confirmed deadline ahead, the window started or no opening date), upcoming (the window opens later),
    closed (only past applicant deadlines: the next cycle is not published yet), not_announced (the page says the
    dates will be announced), rolling, or not_stated (also when the page gives only an approximate date)."""
    appl = [d for d in o.deadlines if d.kind in APPLICANT_KINDS]
    opening = [d for d in o.deadlines if d.kind == DeadlineKind.OPENING and d.date]
    ahead = sorted(d.date for d in appl if d.date and d.certainty == DeadlineCertainty.CONFIRMED
                   and date.fromisoformat(d.date) >= today)
    if ahead:
        opens = sorted(d.date for d in opening if d.date <= ahead[0])
        if opens and date.fromisoformat(opens[-1]) > today:
            return _s("upcoming", f"opens {opens[-1]}, closes {ahead[0]}")
        return _s("open", f"closes {ahead[0]}")
    if any(date.fromisoformat(d.date) > today for d in opening):
        return _s("upcoming", "opens " + min(d.date for d in opening if date.fromisoformat(d.date) > today))
    # round 27: what the page says about the call outranks a guess from dates
    if any(d.approximate == UNAVAILABLE_NOTE for d in appl):
        return _s("not_announced", "the page says the programme is currently unavailable")
    if any(d.approximate == CLOSED_NOTE for d in appl):
        return _s("closed", "the page says the call is closed" + (f" (cycle {c})" if (c := next(
            (d.cycle for d in appl if d.approximate == CLOSED_NOTE and d.cycle), "")) else "; no date stated"))
    if any(d.kind == DeadlineKind.ROLLING for d in o.deadlines) and not any(d.date for d in appl):
        return _s("rolling")   # "rolling" beside dated deadlines describes the review order, not the cycle
    if any(d.approximate == "not yet published" for d in o.deadlines):
        return _s("not_announced")
    past = [d.date for d in appl if d.date]
    if past:
        return _s("closed", f"last deadline {max(past)}; next cycle not published")
    # round 33: "typically in early October" says nothing about the current cycle; the applicant checks the page
    return _s("not_stated")


def funding_type(o: Opportunity) -> dict:
    """fully_funded | partially_funded | tuition_funded | fee_waiver | stipend_only | assistantship from the documented
    components (funding.classify); funding_unclear when components are named but what they pay is not; not_stated when
    the page names none. Never inferred from words like "scholarship" alone."""
    if not o.funding:
        return _s("not_stated")
    from .funding import classify
    c = classify(o)
    return _s(c["classification"], "; ".join(c["reasons"])[:160])


def _programme_specific(o: Opportunity, out: dict) -> None:
    """Eligibility counts only when it was read on the programme's own page (or one of its sections), not on a
    portal, catalogue or guidance page that speaks about many programmes."""
    from .normalize import normalize_url
    if out["eligible_countries"]["state"] != "present":
        return
    if o.page_type not in ("scholarship_program", "unknown"):
        out["eligible_countries"] = _s("needs_review", f"stated on a {o.page_type} page, not the programme's own page")
        return
    own = {normalize_url(o.info_url)}
    nat = [e for e in o.evidence if e.field == "nationality"]
    sections = any(t.startswith("section:") for t in o.tags)
    if nat and not sections and not any(normalize_url(e.source_url) in own for e in nat):
        out["eligible_countries"] = _s("needs_review", "stated only on another page: " + nat[0].source_url[:100])


EVIDENCE_PREFIX = {"eligible_countries": ("nationality",), "study_levels": ("study_levels",),
                   "funding_components": ("funding.",), "deadline": ("deadline.",), "application_period": ("deadline.",)}


# Round 27: each decision an applicant acts on must rest on a quotation from the programme's own page.
_NAME_RX = re.compile(r"\b((?:[A-Z][\w'’&-]+\s+){1,6}(?:Scholarships?|Fellowships?|Programm?es?|Awards?|Grants?|"
                      r"Bursar(?:y|ies)|Studentships?))\b")
_NAME_GENERIC = {"the", "a", "an", "of", "for", "and", "in", "at", "to", "university", "college", "scholarship",
                 "scholarships", "fellowship", "fellowships", "programme", "programmes", "program", "programs", "award",
                 "awards", "grant", "grants", "bursary", "bursaries", "studentship", "studentships"}


def _name_tokens(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _NAME_GENERIC}


def _other_programme(quote: str, o: Opportunity) -> str:
    """A programme named in the quotation that shares no distinctive word with the record's title or provider
    ("China Scholarship Council - University of Melbourne PhD Scholarship" on the Graduate Research Scholarships page)."""
    if o.own_programme_words:
        # round 29: the page's own award name (title plus the award it repeats), shared with deadline ownership
        from .extract import AWARD_NAME_RX, _foreign
        own_words = set(o.own_programme_words)
        for m in AWARD_NAME_RX.finditer(quote or ""):
            name = m.group(1) or m.group(2)
            if _foreign(name, own_words):
                return name.strip()
        return ""
    own = _name_tokens(f"{o.title} {o.provider_name} {o.programme_identity.get('name', '') if isinstance(o.programme_identity, dict) else ''}")
    if not own:
        return ""
    for m in _NAME_RX.finditer(quote or ""):
        toks = _name_tokens(m.group(1))
        if toks and not toks & own:
            return m.group(1).strip()
    return ""


def decision_evidence(o: Opportunity, today: Optional[date] = None) -> dict:
    """For eligibility, funding and cycle: the quotations the decision rests on and what is wrong with them.
    state: supported (every quotation is from this programme's own page, states the value and names no other
    programme), needs_review (a problem below), no_evidence (a value without a quotation), not_stated (no value)."""
    from .normalize import normalize_url
    today = today or date.today()
    own = normalize_url(o.info_url) if o.info_url else ""
    sections = any(t.startswith("section:") for t in o.tags)
    kinds_used = {"tuition", "stipend", "living_allowance", "assistantship"}
    decisions = {
        "eligibility": (o.nationality.mode in ("any", "include", "exclude"), ("nationality",)),
        "funding": (funding_type(o)["state"] not in ("not_stated",),
                    tuple(f"funding.{k}" for k in kinds_used if any(c.kind == k for c in o.funding))),
        "cycle": (cycle_status(o, today)["state"] != "not_stated", ("deadline.",)),
    }
    out = {}
    for name, (has_value, prefixes) in decisions.items():
        if not has_value:
            out[name] = {"state": "not_stated", "quotes": [], "problems": []}
            continue
        ev = [e for e in o.evidence if prefixes and e.field.startswith(prefixes)]
        problems = []
        if not ev or not any(e.snippet for e in ev):
            out[name] = {"state": "no_evidence", "quotes": [], "problems": ["a value without a quotation"]}
            continue
        # round 29: "irrelevant" from the page classifier conflicts with a page that keeps naming its own award; the
        # quotation checks below still apply. Catalogue, guidance and announcement pages are still sent to review.
        if o.page_type not in ("scholarship_program", "unknown", "", None) \
                and not (o.page_type == "irrelevant" and o.own_programme_words):
            problems.append(f"read on a {o.page_type} page, not the programme's own page")
        for e in ev:
            if own and e.source_url and normalize_url(e.source_url) != own and not sections:
                problems.append(f"quoted from another page: {e.source_url[:100]}")
            problems += [w for w in e.warnings if w]
            other = _other_programme(e.snippet, o)
            if other:
                problems.append(f"the quotation names another programme: {other[:80]}")
        out[name] = {"state": "needs_review" if problems else "supported",
                     "quotes": [{"field": e.field, "url": e.source_url, "quote": e.snippet[:300]} for e in ev[:4]],
                     "problems": list(dict.fromkeys(problems))[:6]}
    return out


def _decision_evidence_gate(o: Opportunity, out: dict) -> None:
    """A decision whose quotation is not clean goes to review instead of being reported as known."""
    de = decision_evidence(o)
    for name, field in (("eligibility", "eligible_countries"), ("funding", "funding_type"), ("cycle", "cycle")):
        d = de[name]
        if d["state"] in ("needs_review", "no_evidence") and out[field]["state"] not in ("needs_review", "unsupported",
                                                                                          "not_stated"):
            out[field] = _s("needs_review", f"{out[field]['state']}, but " + "; ".join(d["problems"])[:180])


# Round 37: claim kinds whose measured precision on 1,336 decisions (sets K to S) was too low to report as known. Each is
# sent to review with its reason; the value stays visible as "unverified". SCHOLAR_RISK_GATE=off|standard|strict
# (default standard). standard: assistantship and fee waiver readings (0 right of 6), "announcement pending" cycles
# (1 right of 7) and applicant deadlines with two or more dates (52% right). strict adds tuition-only (58%) and
# stipend-only (76%) readings, "open to any nationality" (67%) and "upcoming" cycles (77%).
RISK_FUNDING = {"standard": {"assistantship", "fee_waiver"}, "strict": {"assistantship", "fee_waiver", "tuition_funded", "stipend_only"}}
RISK_CYCLE = {"standard": {"not_announced"}, "strict": {"not_announced", "upcoming"}}


def _risk_gate(o: Opportunity, out: dict) -> None:
    import os
    mode = os.environ.get("SCHOLAR_RISK_GATE", "standard").strip().lower()
    if mode not in ("standard", "strict"):
        return

    def hold(field: str, why: str) -> None:
        if out[field]["state"] not in ("needs_review", "unsupported", "not_stated"):
            out[field] = _s("needs_review", f"{out[field]['state']}, but {why}")

    if out["funding_type"]["state"] in RISK_FUNDING[mode]:
        hold("funding_type", "this reading of the funding class is often wrong on university and funder pages; check the quotation")
    if out["cycle"]["state"] in RISK_CYCLE[mode]:
        hold("cycle", "this cycle state is often wrong when the page does not say it outright; check the quotation")
    if mode == "strict" and o.nationality.mode == "any":
        hold("eligible_countries", "'open to any nationality' is often a reading of a sentence about another group")
    dated = [d for d in o.deadlines if d.date and d.kind in APPLICANT_KINDS]
    # dates of earlier cycles that the record already knows are past do not make the current deadline ambiguous
    live = [d for d in dated if d.certainty != DeadlineCertainty.HISTORICAL]
    dates = {d.date for d in (live or dated)}
    if len(dates) >= 2:
        hold("deadline", "the page gives several dates (opening, closing, interview, earlier cycles); pick the applicant deadline from the page")


def _require_evidence(o: Opportunity, out: dict) -> None:
    """A value is only "present" when an evidence item (source URL and quotation) backs it."""
    for f, prefixes in EVIDENCE_PREFIX.items():
        if out.get(f, {}).get("state") != "present":
            continue
        if not any(e.field.startswith(prefixes) and e.source_url and e.snippet for e in o.evidence):
            out[f] = _s("unsupported", "a value without a source quotation")


DECISION_FIELDS = ("eligible_countries", "study_levels", "funding_type", "cycle")


def complete_with_evidence(fs: dict) -> tuple[bool, list[str]]:
    """Every field an applicant needs is filled and quoted: a confirmed programme on an official page, eligibility read
    on that programme's page, its study levels, what the funding pays, and where the cycle stands (a closed or
    not-yet-announced cycle is known information). Filled and quoted is not verified, and not reviewed: see tiers().
    Returns (complete, what is missing)."""
    missing = []
    if fs["programme_identity"]["state"] != "confirmed":
        missing.append("programme_identity")
    if fs["official_source"]["state"] != "present":
        missing.append("official_source")
    if fs["eligible_countries"]["state"] != "present":
        missing.append("eligible_countries")
    if fs["study_levels"]["state"] != "present":
        missing.append("study_levels")
    if fs["funding_type"]["state"] in ("not_stated", "funding_unclear", "needs_review"):
        missing.append("funding_type")
    if fs["cycle"]["state"] in ("not_stated", "needs_review"):
        missing.append("cycle")
    return not missing, missing


REVIEWED_TAG = "human-reviewed"    # set by a person after checking the record against the official pages


def tiers(opps: list[Opportunity], today: date, discovered_leads: Optional[int] = None) -> dict:
    """Separate counts, each a subset of the one before it except the first; none is a share of another.
      discovered_leads           URLs found by search or links (when the caller knows them)
      recognized_programmes      records whose page is a programme page
      verified_identity          ... whose programme identity is confirmed and whose record an official page verified
      verified_eligibility       ... whose nationality rule an official quotation confirmed on the programme's page
      verified_current_cycle     ... with an applicant deadline ahead confirmed verbatim on an official page
      verified_funding           ... whose funding components an official quotation confirmed
      application_ready          ... all of the above, and checked by a person (tag "human-reviewed")
    Filled-in fields never count here: only official confirmation does, and "ready" needs a human review."""
    from .freshness import field_verification
    from .identity import record_identity
    from .models import VerificationStatus
    out = {"discovered_leads": discovered_leads}
    rec = [o for o in opps if o.page_type == "scholarship_program"]
    ident = [o for o in rec if record_identity(o).get("state") == "confirmed"
             and o.verification_status == VerificationStatus.CONFIRMED]
    fv = {o.id: field_verification(o, today) for o in ident}
    elig = [o for o in ident if fv[o.id]["nationality"] and field_status(o, today)["eligible_countries"]["state"] == "present"]
    cyc = [o for o in elig if fv[o.id]["current_deadline"]]
    fund = [o for o in cyc if fv[o.id]["funding"]]
    ready = [o for o in fund if REVIEWED_TAG in o.tags]
    out.update(recognized_programmes=len(rec), verified_identity=len(ident), verified_eligibility=len(elig),
               verified_current_cycle=len(cyc), verified_funding=len(fund), application_ready=len(ready),
               verified_but_not_reviewed=len(fund) - len(ready))
    return out


def audit(opps: list[Opportunity], today: Optional[date] = None) -> dict:
    """Counts per field and state, plus the records that most need work."""
    today = today or date.today()
    counts: dict[str, dict[str, int]] = {f: {} for f in FIELDS}
    gaps = []
    ready, ready_now, blocking = [], [], {}
    for o in opps:
        fs = field_status(o, today)
        for f, v in fs.items():
            counts[f][v["state"]] = counts[f].get(v["state"], 0) + 1
        ok, miss = complete_with_evidence(fs)
        if ok:
            ready.append(o.id)
            if fs["cycle"]["state"] in ("open", "upcoming", "rolling"):
                ready_now.append(o.id)
        elif fs["programme_identity"]["state"] == "confirmed":
            for m in miss:
                blocking[m] = blocking.get(m, 0) + 1
        missing = [f for f, v in fs.items() if v["state"] in ("not_stated", "unofficial", "outdated", "needs_review",
                                                               "rejected") and f != "verification"]
        if missing:
            gaps.append({"id": o.id, "title": o.title[:90], "info_url": o.info_url, "needs": missing})
    complete = len(opps) - len(gaps)
    gaps.sort(key=lambda g: -len(g["needs"]))
    return {"as_of": today.isoformat(), "records": len(opps), "complete_records": complete,
            "complete_with_evidence": len(ready), "complete_with_evidence_and_open_or_upcoming": len(ready_now),
            "tiers": tiers(opps, today),
            "confirmed_programmes_missing": dict(sorted(blocking.items(), key=lambda kv: -kv[1])),
            "by_field": counts,
            "records_needing_work": gaps, "possible_duplicates": possible_duplicates(opps),
            "states": "present | approximate | outdated | needs_review | not_published | not_applicable | not_stated "
                      "| unofficial | unsupported (a value with no source quotation); cycle: open | upcoming | closed | "
                      "not_announced | expected | rolling | not_stated; only not_applicable means the field does not apply. programme_identity: confirmed | "
                      "needs_review | rejected; page_type: scholarship_program | scholarship_catalog | general_guidance | "
                      "announcement | aggregator | irrelevant | unknown"}




def possible_duplicates(opps: list[Opportunity]) -> list[list[str]]:
    """Records that share a normalised URL, or a title and provider, and were not deliberately kept apart."""
    from .normalize import dedup_key, normalize_url
    groups: dict[str, list[str]] = {}
    for o in opps:
        if any(t.startswith("kept separate from") for t in o.tags):
            continue
        for k in {"url:" + normalize_url(o.info_url) if o.info_url else "", "key:" + dedup_key(o.title, o.provider_name)}:
            if k:
                groups.setdefault(k, []).append(o.id)
    return [list(g) for g in sorted({tuple(sorted(set(v))) for v in groups.values() if len(set(v)) > 1})]


def discovery_yield(opps: list[Opportunity], known: Optional[set[str]] = None) -> dict:
    """Per destination country and study level: official records whose programme identity is confirmed, how many are new against `known`
    (dedup keys and normalised URLs of an earlier catalog), and how many are verified on an official page.
    Records, not URLs: a programme is counted once however many pages mention it."""
    from .evidence import is_official
    from .freshness import record_authority
    from .models import VerificationStatus
    from .normalize import dedup_key, normalize_url
    known = known or set()
    rows: dict[tuple[str, str], dict] = {}
    countries_: dict[str, dict] = {}
    from .identity import record_identity
    totals = {"records": len(opps), "official_programmes": 0, "new": 0, "verified": 0, "identity_needs_review": 0,
              "not_a_programme": 0}
    for o in opps:
        # admission programmes carry no award
        if o.opportunity_type in NO_FUNDING_TYPES or not is_official(record_authority(o)):
            continue
        idn = record_identity(o)["state"]
        if idn != "confirmed":   # catalogues, guidance and unnamed records are not counted as programmes
            totals["not_a_programme" if idn == "rejected" else "identity_needs_review"] += 1
            continue
        new = dedup_key(o.title, o.provider_name) not in known and normalize_url(o.info_url) not in known
        # CONFIRMED already requires an official quotation for a deadline, eligibility or funding value
        verified = o.verification_status == VerificationStatus.CONFIRMED
        totals["official_programmes"] += 1
        totals["new"] += new
        totals["verified"] += verified
        for c in o.destination_countries or ["unspecified"]:
            bc = countries_.setdefault(c, {"country": c, "official_programmes": 0, "new": 0, "verified": 0})
            for k, v in (("official_programmes", True), ("new", new), ("verified", verified)):
                bc[k] += v
            for lv in o.study_levels or ["unspecified"]:
                r = rows.setdefault((c, lv), {"country": c, "level": lv, "official_programmes": 0, "new": 0,
                                              "verified": 0})
                r["official_programmes"] += 1
                r["new"] += new
                r["verified"] += verified
    return {"totals": totals, "by_country": sorted(countries_.values(), key=lambda r: -r["official_programmes"]),
            "by_country_level": sorted(rows.values(), key=lambda r: (r["country"], r["level"])),
            "note": "a programme with several levels or host countries appears in each row; totals count it once"}


def known_keys(opps: list[Opportunity]) -> set[str]:
    from .normalize import dedup_key, normalize_url
    return {dedup_key(o.title, o.provider_name) for o in opps} | {normalize_url(o.info_url) for o in opps if o.info_url}
