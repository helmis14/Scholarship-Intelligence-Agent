"""Refresh scheduling and run reporting.

Refresh priority (higher first), configurable in data/refresh_schedule.json:
  upcoming confirmed deadline within `upcoming_days`            +5
  conflicting information                                         +4
  only historical deadlines (a new cycle may have been published) +3, rechecked every `historical_days`
  current-cycle record not verified within `stale_days`           +3
  nationality rule unknown                                         +2
  funding terms missing or without amounts                         +2
  never verified                                                   +2
A record is due when its last verification is older than the interval its worst condition allows.
Historical cycles are never turned into a current deadline: a refresh only re-reads the official pages.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .models import DeadlineCertainty, Opportunity, VerificationStatus
from .store import Store, data_dir

DEFAULTS = {"upcoming_days": 45, "stale_days": 14, "historical_days": 30, "incomplete_days": 21, "upcoming_interval_days": 3}


def schedule(override: Optional[dict] = None) -> dict:
    cfg = dict(DEFAULTS)
    path = data_dir() / "refresh_schedule.json"
    if path.is_file():
        cfg.update({k: int(v) for k, v in json.loads(path.read_text()).items() if k in DEFAULTS})
    cfg.update({k: int(v) for k, v in (override or {}).items() if k in DEFAULTS and v is not None})
    return cfg


def _age_days(opp: Opportunity, today: date) -> Optional[int]:
    if not opp.last_verified_at:
        return None
    return (today - datetime.fromisoformat(opp.last_verified_at).astimezone(timezone.utc).date()).days


def priority(opp: Opportunity, today: date, cfg: dict) -> dict:
    reasons, score, interval = [], 0, cfg["stale_days"]
    future = [d for d in opp.deadlines if d.date and d.certainty == DeadlineCertainty.CONFIRMED
              and date.fromisoformat(d.date) >= today]
    soon = [d for d in future if (date.fromisoformat(d.date) - today).days <= cfg["upcoming_days"]]
    if soon:
        score += 5
        interval = min(interval, cfg["upcoming_interval_days"])
        reasons.append(f"confirmed deadline {min(d.date for d in soon)} within {cfg['upcoming_days']} days")
    if opp.conflicts or opp.verification_status == VerificationStatus.CONFLICTING:
        score += 4
        interval = min(interval, cfg["upcoming_interval_days"])
        reasons.append("conflicting information")
    dated = [d for d in opp.deadlines if d.date]
    if dated and all(d.certainty == DeadlineCertainty.HISTORICAL for d in dated):
        score += 3
        interval = min(interval, cfg["historical_days"])
        reasons.append("only past-cycle deadlines known: check for a newly published cycle")
    age = _age_days(opp, today)
    if age is None:
        score += 2
        reasons.append("never verified")
    elif future and age > cfg["stale_days"]:
        score += 3
        reasons.append(f"current-cycle record last verified {age} days ago")
    if opp.nationality.mode == "unknown":
        score += 2
        interval = min(interval, cfg["incomplete_days"])
        reasons.append("nationality rule not established")
    if not opp.funding or not any(c.amount is not None for c in opp.funding):
        score += 2
        interval = min(interval, cfg["incomplete_days"])
        reasons.append("funding terms incomplete")
    due = age is None or age >= interval
    nxt = (today if due else today + timedelta(days=interval - age)).isoformat()
    return {"opportunity_id": opp.id, "title": opp.title, "priority": score, "due": due, "next_check": nxt,
            "last_verified_at": opp.last_verified_at, "interval_days": interval, "reasons": reasons}


def plan(store: Store, today: date, cfg: Optional[dict] = None) -> list[dict]:
    cfg = cfg or schedule()
    rows = [priority(o, today, cfg) for o in store.list_opportunities()]
    return sorted(rows, key=lambda r: (not r["due"], -r["priority"], r["next_check"]))


def _confirmed(e) -> bool:
    from .evidence import is_official
    # structured feed evidence predates authority labels; anything else must come from an official authority
    return e.status == VerificationStatus.CONFIRMED and (is_official(e.authority) or not e.authority)


def field_verification(opp: Opportunity, today: date) -> dict:
    """Which key fields are confirmed on an official page (field level, not record level). A current deadline
    counts only when an applicant deadline's exact date is confirmed by an official quotation."""
    from .models import DeadlineKind
    conf = {e.field for e in opp.evidence if _confirmed(e)}
    conf_dates = {(e.field, e.value) for e in opp.evidence if _confirmed(e) and e.field.startswith("deadline.")}
    cur_deadline = any(d.date and d.certainty == DeadlineCertainty.CONFIRMED and date.fromisoformat(d.date) >= today
                       and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION) and not d.warnings
                       and (f"deadline.{d.kind}", d.date) in conf_dates for d in opp.deadlines)
    return {"current_deadline": cur_deadline,
            "nationality": "nationality" in conf and opp.nationality.mode != "unknown",
            "funding": any(f.startswith("funding") for f in conf)}


def record_authority(opp: Opportunity) -> str:
    if opp.source_authority:
        return opp.source_authority
    if opp.discovered_via.startswith("adapter:"):
        return "4_official_catalogue_feed"
    from .evidence import classify_authority
    return str(classify_authority(opp.info_url, title=opp.title))


def trust_counts(opps: list[Opportunity], discovered_leads: int, today: date) -> dict:
    """Separate counts; deliberately no single verification percentage."""
    from .evidence import is_official
    fv = [field_verification(o, today) for o in opps]
    auth = [record_authority(o) for o in opps]
    by_auth: dict = {}
    for a in auth:
        by_auth[a] = by_auth.get(a, 0) + 1
    from .evidence import is_aggregator
    from_agg = [o for o in opps if ":via-aggregator" in o.discovered_via or is_aggregator(o.info_url, o.title)]
    agg_confirmed = [o for o in from_agg if o.verification_status == VerificationStatus.CONFIRMED
                     and is_official(record_authority(o))]
    unsupported = [o for o in opps if any(e.warnings for e in o.evidence)]
    key_fields = {"deadline": lambda o: any(d.date or d.kind == "rolling" for d in o.deadlines),
                  "nationality": lambda o: o.nationality.mode != "unknown",
                  "funding": lambda o: bool(o.funding), "study_levels": lambda o: bool(o.study_levels),
                  "language": lambda o: bool(o.language_requirements)}
    outdated = [o for o in opps if o.deadlines and all(d.certainty == DeadlineCertainty.HISTORICAL
                                                       for d in o.deadlines if d.date)
                and any(d.date for d in o.deadlines)]
    return {
        "discovered_leads": discovered_leads,
        "records": len(opps),
        "records_by_source_authority": dict(sorted(by_auth.items())),
        "official_source_candidates": sum(is_official(a) for a in auth),
        "officially_verified_programmes": sum(1 for o, a in zip(opps, auth) if is_official(a)
                                             and o.verification_status == VerificationStatus.CONFIRMED),
        "confirmed_current_deadlines": sum(f["current_deadline"] for f in fv),
        "confirmed_nationality_rules": sum(f["nationality"] for f in fv),
        "confirmed_funding_coverage": sum(f["funding"] for f in fv),
        "records_with_conflicting_evidence": sum(1 for o in opps if o.verification_status == VerificationStatus.CONFLICTING
                                                 or o.conflicts),
        "records_with_unsupported_or_flagged_values": len(unsupported),
        "records_missing_field": {k: sum(1 for o in opps if not f(o)) for k, f in key_fields.items()},
        "records_using_outdated_cycles": len(outdated),
        "records_from_aggregators": len(from_agg),
        "aggregator_records_confirmed_by_official_source": len(agg_confirmed),
        "note": "each count is separate; none is a share of another and they are not combined into one rate",
    }
