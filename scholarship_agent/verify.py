"""Primary-source verification.

Official sources are the authority. For one opportunity this:
  1. picks its official page (or an official URL the user supplies),
  2. re-fetches it fresh,
  3. confirms each claim whose evidence is still on that page,
  4. re-extracts the page and marks claims that now disagree as conflicting
     (both values kept, never silently overwritten),
  5. leaves aggregator/search claims unverified unless the official page
     states the same value,
  6. moves past-dated deadlines to historical,
  7. writes a verification record.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .discovery import is_official_url
from .evidence import classify_authority, is_official, substantiates, validate_deadline
from .extract import clean_snippet, extract_opportunity, page_from_response, page_kind
from .models import (DeadlineCertainty, DeadlineKind, Evidence, Opportunity, SourceAuthority, SourceType,
                     VerificationStatus)

APPLICANT_KINDS = (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION, DeadlineKind.OPENING)
from .net import Fetcher, FetchError
from .normalize import normalize_url
from .registry import Source
from .store import Store, now

MAX_PAGES = 6
STRUCTURED_NOTES = {"structured official dataset", "official catalogue entry"}
SINGLE_FIELDS = {"nationality", "max_age", "min_age", "min_gpa"}
MULTI_FIELDS = {"study_levels", "selection_criteria", "required_documents", "application_url"}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


ADAPTER_DOMAINS = {"adapter:daad": ["daad.de"], "adapter:erasmus_mundus": ["europa.eu"],
                   "adapter:euraxess:import": ["europa.eu"], "adapter:campusfrance": ["campusfrance.org"]}


def official_domains_for(opp: Opportunity, sources: list[Source]) -> list[str]:
    if opp.discovered_via in ADAPTER_DOMAINS:
        doms = list(ADAPTER_DOMAINS[opp.discovered_via])
        if opp.discovered_via == "adapter:erasmus_mundus" and opp.info_url:
            # the catalogue (an official EU source) names the consortium site as the programme's own page
            from urllib.parse import urlsplit
            host = (urlsplit(opp.info_url).hostname or "").removeprefix("www.")
            if host:
                doms.append(host)
        return doms
    src_id = opp.discovered_via.removeprefix("source:") if opp.discovered_via.startswith("source:") else ""
    for s in sources:
        if s.id == src_id:
            return s.official_domains
    return []


def verify(store: Store, opp: Opportunity, fetcher: Fetcher, sources: list[Source], *,
           official_url: Optional[str] = None, today: Optional[date] = None) -> dict:
    today = today or date.today()
    domains = official_domains_for(opp, sources)
    target = official_url or opp.info_url
    if not domains:
        from .evidence import host, registry_domains
        h = host(target)
        domains = [d for d in registry_domains() if h == d or h.endswith("." + d)]
    report: dict = {"opportunity_id": opp.id, "official_url": target, "confirmed": [], "conflicting": [],
                    "unverified": [], "historical_deadlines": [], "notes": []}

    if not is_official_url(target, domains) and not official_url:
        report["notes"].append("no official source known for this opportunity; supply one with --official-url")
        opp.source_authority = str(classify_authority(target, page_kind="opportunity", title=opp.title))
        opp.verification_reason = (f"source is {opp.source_authority.split('_', 1)[1].replace('_', ' ')}, not an official "
                                   "page; values stay unverified until an official page states them")
        for e in opp.evidence:
            if e.status not in (VerificationStatus.CONFIRMED, VerificationStatus.HISTORICAL):
                report["unverified"].append(e.field)
        opp.verification_status = VerificationStatus.CONFLICTING if opp.conflicts else VerificationStatus.EXTRACTED
        return _finish(store, opp, report, "no_official_source")

    # Every official page this record's evidence came from is re-checked (programme landing page plus its
    # eligibility/benefits/deadline sections), not only the first one.
    # Structured sources (an adapter's dataset or feed) are re-checked by re-running the adapter, not by reading
    # them as web pages; their evidence keeps its status here.
    structured = {normalize_url(e.source_url) for e in opp.evidence if e.note in STRUCTURED_NOTES}
    pages = [u for u in dict.fromkeys([target] + [e.source_url for e in opp.evidence])
             if u and normalize_url(u) not in structured and (normalize_url(u) == normalize_url(target)
                                                             or is_official_url(u, domains))][:MAX_PAGES]
    ts = now()
    # conflicts found by an earlier verification are re-derived now, not carried forward
    opp.conflicts = [c for c in opp.conflicts if "vs official now" not in c]
    fresh_all: list[Opportunity] = []
    fresh_values: set = set()
    reachable = 0
    for url in pages:
        url_n = normalize_url(url)
        try:
            resp = fetcher.get(url)
        except FetchError as e:
            for ev in opp.evidence:
                if normalize_url(ev.source_url) == url_n:
                    ev.status, ev.note = VerificationStatus.SOURCE_UNAVAILABLE, e.reason
            report["notes"].append(f"official source unavailable: {url} ({e.reason})")
            continue
        reachable += 1
        page = page_from_response(resp)
        body = _norm(page.text)
        fresh, flags = extract_opportunity(page, provider_name=opp.provider_name, provider_type=opp.provider_type,
                                           source_type=SourceType.OFFICIAL, country_hint=opp.destination_countries,
                                           retrieved_at=ts, today=today)
        if flags:
            report["notes"].append(f"official page contains text addressed to AI systems; ignored ({url})")
        from .extract import classify_page
        cls_now = classify_page(page)
        kind_now = cls_now["kind"]
        authority = classify_authority(url, official_domains=domains or None, page_kind=kind_now,
                                       source_type=SourceType.OFFICIAL if is_official_url(url, domains) else "",
                                       title=page.title)
        if normalize_url(url) == normalize_url(opp.info_url):
            opp.source_authority = str(authority)
            from .identity import identity, page_type
            opp.page_type = "unknown" if cls_now["confidence"] == "low" else page_type(kind_now)
            report["programme_identity"] = opp.programme_identity = identity(
                opp, page_title=page.html_title or page.title, h1=page.h1, text=page.text, page_kind=kind_now,
                kind_confidence=cls_now["confidence"], kind_reason=cls_now["reason"])
        # several applicant dates on one page usually means several programmes or rounds
        applicant_dates = {d.date for d in fresh.deadlines if d.date and d.kind == DeadlineKind.SCHOLARSHIP
                           and d.scope == "general"}
        n_programmes = 2 if len(applicant_dates) > 2 or kind_now == "listing" else 1
        for f in fresh.evidence:
            f.authority = str(authority)
        fresh_all.append(fresh)
        fresh_by_field: dict[str, Evidence] = {e.field: e for e in fresh.evidence}
        fresh_multi: dict[str, set] = {}
        for e in fresh.evidence:
            fresh_multi.setdefault(e.field, set()).add(repr(e.value))
        fresh_values |= {(e.field, repr(e.value)) for e in fresh.evidence}
        for ev in opp.evidence:
            if ev.status == VerificationStatus.HISTORICAL or normalize_url(ev.source_url) != url_n \
                    or ev.verdict == "needs_review":   # a person decides those; verification never confirms them
                continue
            f = fresh_by_field.get(ev.field)
            same_value = repr(ev.value) in fresh_multi.get(ev.field, set())
            if ev.field == "title":
                continue  # page titles differ between a catalogue and a programme site; never a conflict
            if ev.note.startswith("ai-assisted") and not same_value:
                # The quote can be re-found, but the reading of it is the model's: never promoted to confirmed.
                found = bool(ev.snippet) and _norm(ev.snippet)[:120] in body
                ev.status = VerificationStatus.EXTRACTED
                ev.note = (ev.note.split(";")[0] + ("; quote still on the official page, interpretation not "
                                                    "confirmed by rules" if found else "; quote no longer on the page"))
                report["unverified"].append(ev.field)
                continue
            ev.authority = str(authority)
            quote_here = bool(ev.snippet) and _norm(ev.snippet)[:120] in body
            if same_value and not quote_here:
                # same reading from today's text: carry today's quotation forward
                twin = next((x for x in fresh.evidence if x.field == ev.field and repr(x.value) == repr(ev.value)), None)
                if twin is not None:
                    ev.snippet, quote_here = twin.snippet, True
            if same_value or quote_here:
                why = _cannot_confirm(ev, opp, authority, quote_here, today, n_programmes)
                if ev.field.startswith("deadline.") and not same_value:
                    # the quote is still there, but today's rules no longer read it as this kind of date
                    why.append(f"page no longer read as a {ev.field.split('.', 1)[1]} date")
                if why:
                    ev.status = VerificationStatus.EXTRACTED
                    ev.warnings = sorted(set(ev.warnings) | set(why))
                    report["unverified"].append(ev.field)
                    report.setdefault("not_confirmed_because", {}).setdefault(ev.field, why)
                    continue
                ev.status, ev.verified_at, ev.confidence = VerificationStatus.CONFIRMED, ts, max(ev.confidence, 0.9)
                report["confirmed"].append(ev.field)
            elif f is not None and ev.field.startswith("deadline"):
                # pages list several dates (rounds, levels); a date that is gone is a change, not a contradiction
                ev.status, ev.note = VerificationStatus.EXTRACTED, f"no longer stated; page now lists {sorted(fresh_multi[ev.field])[:4]}"
                report.setdefault("changed", []).append(ev.field)
            elif f is not None and ev.field not in MULTI_FIELDS:
                ev.status, ev.note = VerificationStatus.CONFLICTING, f"official page now states: {clean_snippet(f.snippet, 160)}"
                report["conflicting"].append(ev.field)
                opp.conflicts.append(f"{ev.field}: stored '{ev.value}' vs official now '{f.value}' ({url})")
            else:
                ev.status, ev.note = VerificationStatus.EXTRACTED, "no longer found on its official page"
                report["unverified"].append(ev.field)

    # Two official pages that each state a different value for a single-valued field: keep both, flag it.
    seen_vals: dict = {}
    for ev in opp.evidence:
        if ev.status == VerificationStatus.CONFIRMED and (ev.field in SINGLE_FIELDS or ev.field.startswith("language.")):
            seen_vals.setdefault(ev.field, {}).setdefault(repr(ev.value), ev.source_url)
    for fld, vals in seen_vals.items():
        if len(vals) > 1 and len(set(vals.values())) > 1:
            (va, ua), (vb, ub) = list(vals.items())[:2]
            opp.conflicts.append(f"{fld}: official pages disagree, {va} ({ua}) vs {vb} ({ub}) - vs official now")
            report["conflicting"].append(fld)

    if not reachable:
        opp.verification_status = VerificationStatus.SOURCE_UNAVAILABLE
        opp.verification_reason = ("official page could not be re-read; values are kept as last verified"
                                   + (f" on {opp.last_verified_at[:10]}" if opp.last_verified_at else "") + " and may be out of date")
        return _finish(store, opp, report, "source_unavailable")

    # Claims from non-official pages: confirmed only if an official page states the same value.
    official_n = {normalize_url(u) for u in pages}
    for ev in opp.evidence:
        if normalize_url(ev.source_url) in official_n or ev.status == VerificationStatus.HISTORICAL \
                or ev.note in STRUCTURED_NOTES:
            continue
        if (ev.field, repr(ev.value)) in fresh_values:
            ev.note = "same value found on an official page"
            report["confirmed"].append(ev.field)
        else:
            ev.status, ev.note = VerificationStatus.EXTRACTED, "not found on the official pages"
            report["unverified"].append(ev.field)

    # Official claims that were not on file before become confirmed evidence now.
    have = {(e.field, repr(e.value), normalize_url(e.source_url)) for e in opp.evidence}
    for fresh in fresh_all:
        multi = len({d.date for d in fresh.deadlines if d.date and d.kind == DeadlineKind.SCHOLARSHIP
                     and d.scope == "general"}) > 2
        for f in fresh.evidence:
            if (f.field, repr(f.value), normalize_url(f.source_url)) not in have:
                why = _cannot_confirm(f, fresh, SourceAuthority(f.authority) if f.authority else SourceAuthority.LEAD,
                                      True, today, 2 if multi else 1, title=opp.title)
                if why:
                    f.warnings = why
                else:
                    f.status, f.verified_at, f.confidence = VerificationStatus.CONFIRMED, ts, 0.9
                    report["confirmed"].append(f.field)
                opp.evidence.append(f)

    # Deadlines: official pages win for certainty; nothing is invented.
    for fresh in fresh_all:
        have_d = {(d.kind, d.date, d.approximate) for d in opp.deadlines}
        opp.deadlines += [d for d in fresh.deadlines if (d.kind, d.date, d.approximate) not in have_d]
    # A confirmed current deadline that its own official page no longer states, while that page now gives another
    # date of the same kind and cycle, was changed by the provider: it leaves the record (store keeps it in
    # deadline_history) and the change is reported, instead of lingering as a second date.
    fresh_dl = [(d.kind, d.date, d.cycle, normalize_url(d.source_url)) for f in fresh_all for d in f.deadlines if d.date]
    for d in list(opp.deadlines):
        u = normalize_url(d.source_url)
        if not (d.date and d.kind in APPLICANT_KINDS and d.certainty == DeadlineCertainty.CONFIRMED
                and date.fromisoformat(d.date) >= today and u in official_n) \
                or any(k == d.kind and x == d.date and s == u for k, x, _, s in fresh_dl):
            continue
        new = sorted(x for k, x, c, s in fresh_dl
                     if k == d.kind and s == u and x != d.date and date.fromisoformat(x) >= today
                     and (not c or not d.cycle or c == d.cycle))
        if new:
            opp.deadlines.remove(d)
            for ev in opp.evidence:
                if ev.field == f"deadline.{d.kind}" and ev.value == d.date:
                    ev.status, ev.note = VerificationStatus.HISTORICAL, f"superseded by {new[0]} on the official page"
            report.setdefault("deadline_changes", []).append({"kind": str(d.kind), "from": d.date, "to": new[0],
                                                              "cycle": d.cycle, "source_url": d.source_url})
    # A deadline is confirmed only by confirmed evidence for that exact kind and date (official page, verbatim
    # quote stating the date, applicant-facing, current cycle, this programme). Past dates never roll forward.
    confirmed_dates = {(e.field, e.value) for e in opp.evidence if e.status == VerificationStatus.CONFIRMED
                       and e.field.startswith("deadline.")}
    for d in opp.deadlines:
        if d.date and date.fromisoformat(d.date) < today:
            if d.certainty != DeadlineCertainty.HISTORICAL:
                report["historical_deadlines"].append(d.date)
            d.certainty = DeadlineCertainty.HISTORICAL
            continue
        d.warnings = validate_deadline(d, today, record_title=opp.title,
                                       page_programmes=1)
        if d.date and (f"deadline.{d.kind}", d.date) in confirmed_dates and not d.warnings:
            d.certainty = DeadlineCertainty.CONFIRMED
        elif d.certainty == DeadlineCertainty.CONFIRMED and d.date:
            d.certainty = DeadlineCertainty.EXPECTED if d.kind in APPLICANT_KINDS else DeadlineCertainty.UNKNOWN
            if "not confirmed by verification" not in d.warnings:
                d.warnings.append("not confirmed by verification")
        for attr in ("funding", "language_requirements", "required_documents"):
            if not getattr(opp, attr) and getattr(fresh, attr):
                setattr(opp, attr, getattr(fresh, attr))
        if opp.nationality.mode == "unknown":
            opp.nationality = fresh.nationality

    confirmed = set(report["confirmed"]) | {e.field for e in opp.evidence if e.status == VerificationStatus.CONFIRMED}
    core = {"deadline": any(d.date and d.certainty == DeadlineCertainty.CONFIRMED and d.kind in
                            (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION) for d in opp.deadlines),
            "eligibility": bool({"nationality", "min_gpa", "max_age"} & confirmed or any(f.startswith("language.") for f in confirmed)),
            "funding": any(f.startswith("funding.") for f in confirmed)}
    report["core_fields_confirmed"] = sorted(k for k, v in core.items() if v)
    report["core_fields_missing"] = sorted(k for k, v in core.items() if not v)
    report["pages_checked"] = reachable
    opp.conflicts = sorted(set(opp.conflicts))
    opp.last_verified_at = ts
    if opp.conflicts:
        opp.verification_status = VerificationStatus.CONFLICTING
        opp.verification_reason = f"official sources disagree: {opp.conflicts[0][:160]}"
    elif any(core.values()) and report.get("programme_identity", {}).get("state", "confirmed") != "confirmed":
        # official quotes alone do not make a verified programme: the page must be one named programme
        idn = report["programme_identity"]
        opp.verification_status = VerificationStatus.EXTRACTED
        opp.verification_reason = (f"programme identity {idn['state'].replace('_', ' ')}: " + "; ".join(idn["reasons"])[:200]
                                   + "; official quotes found for " + ", ".join(report["core_fields_confirmed"]))
        report["notes"].append("moved to review: " + opp.verification_reason)
    elif any(core.values()):
        opp.verification_status = VerificationStatus.CONFIRMED
        opp.verification_reason = ("official page quotes confirm: " + ", ".join(report["core_fields_confirmed"]) +
                                   (f"; not confirmed: {', '.join(report['core_fields_missing'])}"
                                    if report["core_fields_missing"] else ""))
    else:
        # The page is official and was re-read, but it states none of the terms that matter.
        opp.verification_status = VerificationStatus.EXTRACTED
        report["notes"].append("official page re-checked, but it states no current deadline, eligibility or funding "
                               "terms; record stays unverified")
        why = report.get("not_confirmed_because")
        opp.verification_reason = ("official page re-read; no deadline, eligibility or funding value could be confirmed"
                                   + (f" ({'; '.join(sorted({w for v in why.values() for w in v}))[:200]})" if why else ""))
    return _finish(store, opp, report, str(opp.verification_status))


def _cannot_confirm(ev: Evidence, opp: Opportunity, authority: SourceAuthority, quote_here: bool, today: date,
                    n_programmes: int, title: str = "") -> list[str]:
    """Why this evidence may not be confirmed (empty = it may)."""
    why = []
    if not is_official(str(authority)):
        why.append(f"source authority {authority.value} cannot confirm")
    if not quote_here:
        why.append("quotation not found verbatim on the official page")
    bad = substantiates(ev.field, ev.value, ev.snippet)
    if bad:
        why.append(bad)
    if ev.field.startswith("deadline.") and isinstance(ev.value, str):
        kind = ev.field.split(".", 1)[1]
        d = next((x for x in opp.deadlines if str(x.kind) == kind and x.date == ev.value), None)
        if d is not None:
            why += validate_deadline(d, today, record_title=title or opp.title, page_programmes=n_programmes)
        if kind in ("institutional", "event"):
            why.append(f"{kind} date, not an applicant deadline")
    return sorted(set(why))


def _finish(store: Store, opp: Opportunity, report: dict, outcome: str) -> dict:
    from .normalize import dedup_key
    report["status"] = str(opp.verification_status)
    report["conflicts"] = list(opp.conflicts)
    for k in ("confirmed", "unverified", "conflicting"):
        report[k] = sorted(set(report[k]))
    store.save_opportunity(opp, dedup_key(opp.title, opp.provider_name), normalize_url(opp.info_url))
    store.add_verification(opp.id, outcome, report)
    return report
