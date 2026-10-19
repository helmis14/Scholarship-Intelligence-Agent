"""Funding classification and coverage estimates.

"Fully funded" requires documented tuition coverage AND a documented living
stipend/allowance. Anything less gets a weaker label. Estimates compare like
currencies only, unless the caller supplies an exchange rate - and every
estimate lists its assumptions and what is missing.
"""

from __future__ import annotations

from typing import Optional

from .models import FundingClass, FundingComponent, Opportunity


def _get(opp: Opportunity, *kinds) -> list[FundingComponent]:
    return [c for c in opp.funding if c.kind in kinds]


def classify(opp: Opportunity) -> dict:
    tuition = _get(opp, "tuition")
    living = [c for c in _get(opp, "stipend", "living_allowance") if c.covered]
    assist = [c for c in _get(opp, "assistantship") if c.covered]
    t_cov = [c for c in tuition if c.covered]
    t_full = any(c.full for c in t_cov)
    waiver = any("waiver" in (c.note or "") for c in t_cov)
    reasons = []
    if t_full and living:
        cls = FundingClass.FULLY_FUNDED
        reasons.append("documented full tuition coverage and a living stipend/allowance")
    elif assist:
        cls = FundingClass.ASSISTANTSHIP
        reasons.append("funding is tied to an assistantship")
    elif t_cov and living and any(c.full is False for c in t_cov):
        cls = FundingClass.PARTIALLY_FUNDED
        reasons.append("a stipend and partial tuition support (an amount, share or discount) are documented")
    elif t_cov and living:
        # round 27: neither proven full nor stated as partial - never guessed either way
        cls = FundingClass.UNCLEAR
        reasons.append("tuition support and a stipend are documented, but whether tuition is covered in full is not stated")
    elif t_full and not living:
        cls = FundingClass.TUITION_FUNDED
        reasons.append("full tuition documented; no living stipend documented")
    elif waiver and not living:
        cls = FundingClass.FEE_WAIVER
        reasons.append("a tuition fee waiver is mentioned; no stipend documented")
    elif t_cov and any(c.full is False for c in t_cov):
        cls = FundingClass.PARTIALLY_FUNDED
        reasons.append("partial tuition support (an amount, share or discount) documented")
    elif t_cov:
        cls = FundingClass.UNCLEAR
        reasons.append("tuition support documented; whether in full or in part is not stated")
    elif living and not tuition:
        cls = FundingClass.STIPEND_ONLY
        reasons.append("a stipend/allowance is documented; tuition coverage is not")
    elif living and tuition and not t_cov:
        cls = FundingClass.STIPEND_ONLY
        reasons.append("stipend documented; tuition explicitly not covered")
    else:
        cls = FundingClass.UNCLEAR
        reasons.append("the evidence does not establish what is paid for")
    extras = sorted(c.kind for c in opp.funding if c.covered and c.kind in ("travel", "insurance", "relocation", "research",
                                                                              "accommodation"))
    not_covered = sorted(c.kind for c in opp.funding if c.covered is False)
    # A classification is only as good as its evidence: say whether an official page confirmed every component
    # it rests on, and flag model readings, so "fully funded" is never taken from incomplete evidence.
    from .models import VerificationStatus
    used = {c.kind for c in tuition + living + assist}
    ev = [e for e in opp.evidence if e.field.split(".", 1)[-1] in used and e.field.startswith("funding.")]
    confirmed = bool(used) and all(any(e.status == VerificationStatus.CONFIRMED for e in ev
                                       if e.field == f"funding.{k}") for k in used)
    if any(c.note == "ai-assisted" for c in tuition + living + assist):
        reasons.append("rests partly on a model reading of the page, not yet confirmed on an official page")
    return {"classification": str(cls), "reasons": reasons, "also_covers": extras, "explicitly_not_covered": not_covered,
            "confirmed_by_official_source": confirmed, "components": [c.to_dict() for c in opp.funding]}


def _annual(c: FundingComponent) -> Optional[float]:
    if c.amount is None:
        return None
    return {"month": c.amount * 12, "semester": c.amount * 2, "year": c.amount, None: None, "total": None,
            "one_off": None}.get(c.period)


def estimate(opp: Opportunity, tuition_per_year: Optional[float] = None, living_per_month: Optional[float] = None,
             currency: Optional[str] = None, fx: Optional[dict[str, float]] = None) -> dict:
    """Coverage of one year of costs. fx maps 'EUR->USD' style keys to rates supplied by the caller."""
    fx = fx or {}
    assumptions, missing = [], []
    data_dates = sorted({e.retrieved_at[:10] for e in opp.evidence if e.field.startswith("funding") and e.retrieved_at})

    def conv(amount, cur):
        if amount is None:
            return None
        if not currency or not cur or cur == currency:
            if not cur:
                assumptions.append("an amount had no stated currency; read as the comparison currency")
            return amount
        rate = fx.get(f"{cur}->{currency}")
        if rate is None:
            missing.append(f"exchange rate {cur}->{currency}")
            return None
        assumptions.append(f"{cur}->{currency} at {rate} (caller-supplied)")
        return amount * rate

    out = {"currency": currency, "data_date": data_dates[-1] if data_dates else None}
    t = _get(opp, "tuition")
    if tuition_per_year is not None:
        if any(c.full and c.covered for c in t):
            out["tuition_covered"] = tuition_per_year
            assumptions.append("full tuition coverage taken at face value from the source wording")
        elif any(c.covered and c.amount is not None for c in t):
            c = next(c for c in t if c.covered and c.amount is not None)
            out["tuition_covered"] = conv(_annual(c) or c.amount, c.currency)
            if c.period not in ("year", "month"):
                assumptions.append("tuition amount period not stated; treated as one year")
        else:
            out["tuition_covered"] = None
            missing.append("tuition coverage amount")
    else:
        missing.append("tuition cost for your programme")

    stip = [c for c in _get(opp, "stipend", "living_allowance") if c.covered]
    annual_stipend = None
    for c in stip:
        a = _annual(c)
        if a is None:
            missing.append(f"{c.kind} amount or period")
            continue
        v = conv(a, c.currency)
        if v is not None:
            annual_stipend = (annual_stipend or 0) + v
    out["stipend_per_year"] = annual_stipend
    if living_per_month is not None:
        need = living_per_month * 12
        out["living_cost_per_year"] = need
        out["living_gap_per_year"] = None if annual_stipend is None else round(need - annual_stipend, 2)
    else:
        missing.append("living cost estimate for the destination city")
    if tuition_per_year is not None and out.get("tuition_covered") is not None:
        out["tuition_gap_per_year"] = round(tuition_per_year - out["tuition_covered"], 2)
    out["assumptions"] = assumptions
    out["missing"] = sorted(set(missing))
    out["note"] = "Estimate only. Amounts come from extracted source text; confirm figures with the provider."
    return out
