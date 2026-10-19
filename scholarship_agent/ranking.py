"""Transparent, configurable ranking.

The score is a weighted sum of named components in [0, 1], each with a one-line
reason. It orders opportunities for attention; it is NOT a probability of
winning an award. Hard eligibility failures are listed separately and never
ranked; soft preference mismatches only lower a component.

Weights: defaults below, overridable by data/ranking_weights.json or the
`weights` argument.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

from .eligibility import evaluate
from .funding import classify
from .models import DeadlineCertainty, DeadlineKind, EligibilityStatus, Opportunity, Profile, VerificationStatus
from .store import data_dir

DEFAULT_WEIGHTS = {
    "eligibility": 0.20, "academic_fit": 0.12, "research_fit": 0.06, "nationality": 0.08, "funding": 0.16,
    "language": 0.07, "complexity": 0.05, "deadline": 0.10, "documents": 0.05, "source_reliability": 0.07,
    "preferences": 0.04,
}
DISCLAIMER = "Ranking score orders opportunities for attention. It is not a probability of receiving an award."

ELIG_SCORE = {"ELIGIBLE": 1.0, "LIKELY_ELIGIBLE": 0.8, "UNCERTAIN": 0.45, "INSUFFICIENT_INFORMATION": 0.35,
              "INELIGIBLE": 0.0}
FUND_SCORE = {"fully_funded": 1.0, "assistantship": 0.8, "tuition_funded": 0.65, "partially_funded": 0.5,
              "fee_waiver": 0.45, "stipend_only": 0.45, "funding_unclear": 0.2}
NEED_MIN = {"full": {"fully_funded": 1.0, "assistantship": 0.9}, "tuition": {"tuition_funded": 1.0, "fee_waiver": 0.9}}


def load_weights(override: Optional[dict] = None) -> dict:
    w = dict(DEFAULT_WEIGHTS)
    path = data_dir() / "ranking_weights.json"
    if path.is_file():
        w.update({k: float(v) for k, v in json.loads(path.read_text()).items() if k in w})
    if override:
        unknown = set(override) - set(w)
        if unknown:
            raise ValueError(f"unknown ranking components: {sorted(unknown)}")
        w.update({k: float(v) for k, v in override.items()})
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}


def _overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.5
    A, B = {x.lower() for x in a}, " ".join(b).lower()
    return 1.0 if any(x in B or any(w in B for w in x.split() if len(w) > 3) for x in A) else 0.2


def next_deadline(opp: Opportunity, today: date):
    future = [d for d in opp.deadlines if d.date and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)
              and date.fromisoformat(d.date) >= today and d.certainty != DeadlineCertainty.HISTORICAL]
    return min(future, key=lambda d: d.date) if future else None


def score(opp: Opportunity, p: Profile, weights: dict, today: date) -> dict:
    elig = evaluate(opp, p, today)
    fund = classify(opp)
    comp: dict[str, tuple[float, str]] = {}
    comp["eligibility"] = (ELIG_SCORE[elig["decision"]], elig["decision"])
    nat = next((c for c in elig["checks"] if c["name"] == "nationality"), None)
    comp["nationality"] = ({"pass": 1.0, "unknown": 0.5, "warn": 0.5, "fail": 0.0}.get(nat["outcome"], 0.5) if nat else 0.5,
                           nat["requirement"] if nat else "not evaluated")
    comp["academic_fit"] = (_overlap(p.disciplines, opp.disciplines + [opp.title] + opp.programs),
                            "discipline overlap" if opp.disciplines else "no discipline restriction stated")
    comp["research_fit"] = (_overlap(p.research_interests, opp.disciplines + [opp.title]),
                            "research interests vs stated focus")
    fs = FUND_SCORE[fund["classification"]]
    need = NEED_MIN.get(p.funding_need)
    if need is not None and fund["classification"] not in need:
        fs *= 0.6
    comp["funding"] = (fs, f"{fund['classification']} vs need '{p.funding_need}'")
    lang = [c for c in elig["checks"] if c["name"].startswith("language")]
    lv = min(({"pass": 1.0, "warn": 0.7, "unknown": 0.5, "fail": 0.1}[c["outcome"]] for c in lang), default=0.5)
    comp["language"] = (lv, ", ".join(f"{c['name']}:{c['outcome']}" for c in lang) or "not evaluated")
    ndocs = len(opp.required_documents)
    comp["complexity"] = (max(0.2, 1 - 0.07 * ndocs) if ndocs else 0.5, f"{ndocs} documents listed" if ndocs else "requirements unknown")
    nd = next_deadline(opp, today)
    if nd:
        days = (date.fromisoformat(nd.date) - today).days
        dv = 0.25 if days < 14 else 0.6 if days < 45 else 1.0
        if nd.certainty != DeadlineCertainty.CONFIRMED:
            dv *= 0.8
        comp["deadline"] = (dv, f"{days} days to {nd.kind} deadline ({nd.certainty})")
    elif any(d.certainty == DeadlineCertainty.EXPECTED for d in opp.deadlines):
        comp["deadline"] = (0.5, "deadline expected but unconfirmed")
    else:
        comp["deadline"] = (0.35, "no upcoming deadline known")
    held = {d.lower() for d in p.documents_ready}
    if ndocs:
        ready = sum(1 for d in opp.required_documents if d.name.lower() in held)
        comp["documents"] = (ready / ndocs, f"{ready}/{ndocs} required documents already held")
    else:
        comp["documents"] = (0.5, "requirements unknown")
    rel = {VerificationStatus.CONFIRMED: 1.0, VerificationStatus.EXTRACTED: 0.5, VerificationStatus.CONFLICTING: 0.3,
           VerificationStatus.SOURCE_UNAVAILABLE: 0.2}.get(opp.verification_status, 0.4)
    if opp.discovered_via.startswith("search") and opp.verification_status != VerificationStatus.CONFIRMED:
        rel *= 0.8
    comp["source_reliability"] = (rel, str(opp.verification_status))
    if p.preferred_countries and opp.destination_countries:
        pv = 1.0 if set(p.preferred_countries) & set(opp.destination_countries) else 0.3
    else:
        pv = 0.5
    comp["preferences"] = (pv, "destination preference")
    total = round(100 * sum(weights[k] * v for k, (v, _) in comp.items()), 1)
    return {
        "opportunity_id": opp.id, "title": opp.title, "provider": opp.provider_name, "score": total,
        "eligibility": elig["decision"], "funding": fund["classification"],
        "next_deadline": nd.to_dict() if nd else None,
        "components": {k: {"value": round(v, 3), "weight": round(weights[k], 3), "contribution": round(100 * weights[k] * v, 1),
                           "reason": r} for k, (v, r) in comp.items()},
        "hard_failures": [m for m in elig["mismatches"] if m.get("hard")],
        "soft_mismatches": [m for m in elig["mismatches"] if not m.get("hard")],
        "next_action": elig["next_action"],
    }


def rank(opps: list[Opportunity], p: Profile, weights: Optional[dict] = None, today: Optional[date] = None,
         include_expired: bool = False) -> dict:
    today = today or date.today()
    w = load_weights(weights)
    ranked, excluded = [], []
    for o in opps:
        s = score(o, p, w, today)
        expired = not next_deadline(o, today) and o.deadlines and all(
            d.certainty == DeadlineCertainty.HISTORICAL for d in o.deadlines)
        if s["eligibility"] == str(EligibilityStatus.INELIGIBLE):
            excluded.append({"opportunity_id": o.id, "title": o.title, "reason": "hard eligibility failure",
                             "failures": s["hard_failures"]})
        elif expired and not include_expired:
            excluded.append({"opportunity_id": o.id, "title": o.title,
                             "reason": "only past-cycle deadlines known; current cycle unconfirmed"})
        else:
            ranked.append(s)
    ranked.sort(key=lambda r: (-r["score"], r["title"]))
    return {"weights": w, "ranked": ranked, "excluded": excluded, "disclaimer": DISCLAIMER, "as_of": today.isoformat()}
