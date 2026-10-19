"""Explainable eligibility evaluation.

Rules of evidence:
  * A requirement the source does not mention is UNKNOWN, never "not required".
  * A mismatch backed only by unverified evidence makes the decision UNCERTAIN,
    not INELIGIBLE - a partial page must not reject anyone.
  * Inferred applicant facts are never proof of eligibility.
  * No language-test waiver is assumed. An MOI route is surfaced only when the
    source documents one, and still needs confirming with the admissions office.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

from . import countries
from .models import (DeadlineCertainty, DeadlineKind, EligibilityStatus, Evidence, Opportunity, Profile,
                     VerificationStatus)
from .profile import age_on, highest_degree, work_years

PASS, FAIL, UNKNOWN, WARN, NA = "pass", "fail", "unknown", "warn", "not_applicable"


@dataclass
class Check:
    name: str
    mandatory: bool
    outcome: str
    requirement: str
    applicant_fact: str = ""
    evidence_url: str = ""
    evidence_status: str = ""
    note: str = ""
    missing: str = ""         # what the applicant needs to supply, if anything


def _ev(opp: Opportunity, prefix: str) -> Optional[Evidence]:
    best = None
    for e in opp.evidence:
        if e.field == prefix or e.field.startswith(prefix + "."):
            if best is None or (e.status == VerificationStatus.CONFIRMED and best.status != VerificationStatus.CONFIRMED):
                best = e
    return best


def _confirmed(e: Optional[Evidence]) -> bool:
    return e is not None and e.status == VerificationStatus.CONFIRMED


def _check(name, mandatory, outcome, requirement, opp, field_prefix, **kw) -> Check:
    e = _ev(opp, field_prefix) if field_prefix else None
    return Check(name, mandatory, outcome, requirement, evidence_url=e.source_url if e else "",
                 evidence_status=str(e.status) if e else "no_evidence", **kw)


def _gpa_fraction(v: Optional[float], scale: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    s = scale or (4.0 if v <= 4.0 else 5.0 if v <= 5 else 10.0 if v <= 10 else 100.0)
    return v / s


def evaluate(opp: Opportunity, p: Profile, today: Optional[date] = None) -> dict:
    today = today or date.today()
    checks: list[Check] = []
    cits = set(p.citizenships)

    # 1. Nationality / residency
    rule = opp.nationality
    if not cits:
        checks.append(_check("nationality", True, UNKNOWN, f"{rule.mode} {rule.countries}", opp, "nationality",
                             missing="citizenship"))
    elif rule.mode == "any":
        checks.append(_check("nationality", True, PASS, "open to all nationalities", opp, "nationality",
                             applicant_fact=",".join(sorted(cits))))
    elif rule.mode == "include":
        ok = bool(cits & set(rule.countries))
        checks.append(_check("nationality", True, PASS if ok else FAIL,
                             "citizens of " + ", ".join(countries.name(c) for c in rule.countries), opp, "nationality",
                             applicant_fact=",".join(sorted(cits))))
    elif rule.mode == "exclude":
        bad = cits & set(rule.countries)
        checks.append(_check("nationality", True, FAIL if bad and bad == cits else PASS,
                             "not open to citizens of " + ", ".join(countries.name(c) for c in rule.countries), opp,
                             "nationality", applicant_fact=",".join(sorted(cits)),
                             note="dual citizenship: confirm which passport may be used" if bad and bad != cits else ""))
    else:
        checks.append(_check("nationality", True, UNKNOWN, "nationality rules not stated in the evidence", opp,
                             "nationality", applicant_fact=",".join(sorted(cits)),
                             note="check the official eligibility page"))
    if rule.residency_required:
        if not p.residence_country:
            checks.append(_check("residency", True, UNKNOWN, "residents of " + ", ".join(rule.residency_required), opp,
                                 "nationality", missing="country of residence"))
        else:
            checks.append(_check("residency", True, PASS if p.residence_country in rule.residency_required else FAIL,
                                 "residents of " + ", ".join(rule.residency_required), opp, "nationality",
                                 applicant_fact=p.residence_country))
    domestic = bool(cits & set(opp.destination_countries))

    # 2. Study level
    if not p.target_levels:
        checks.append(_check("study_level", True, UNKNOWN, ",".join(opp.study_levels) or "not stated", opp,
                             "study_levels", missing="target study level"))
    elif not opp.study_levels:
        checks.append(_check("study_level", True, UNKNOWN, "study levels not stated", opp, "study_levels",
                             applicant_fact=",".join(p.target_levels)))
    else:
        ok = bool(set(p.target_levels) & set(opp.study_levels))
        checks.append(_check("study_level", True, PASS if ok else FAIL, ",".join(opp.study_levels), opp, "study_levels",
                             applicant_fact=",".join(p.target_levels),
                             note="" if ok else "levels were read from page wording; confirm on the official page"))

    # 3. Prior degree for the target level
    hd = highest_degree(p)
    need = {"master": {"bachelor", "master", "phd"}, "phd": {"master", "phd"}, "postdoc": {"phd"}}
    for lvl in p.target_levels:
        if lvl in need:
            if not hd:
                checks.append(Check("prior_degree", True, UNKNOWN, f"degree required before {lvl}",
                                    missing="education history"))
            elif hd.degree.lower() in need[lvl]:
                done = hd.completed is not False
                checks.append(Check("prior_degree", True, PASS if done else WARN, f"degree required before {lvl}",
                                    applicant_fact=f"{hd.degree} {hd.field} ({'completed' if done else 'in progress'})",
                                    note="" if done else "check whether final-year applicants may apply"))
            elif lvl == "phd" and hd.degree.lower() == "bachelor":
                checks.append(Check("prior_degree", True, WARN, "PhD entry usually needs a master's",
                                    applicant_fact="bachelor", note="some systems admit directly from a bachelor's; confirm"))
            break

    # 4. GPA
    if opp.min_gpa is not None:
        if not hd or hd.gpa is None:
            checks.append(_check("gpa", True, UNKNOWN, f"minimum GPA {opp.min_gpa}" + (f"/{opp.gpa_scale}" if opp.gpa_scale else ""),
                                 opp, "min_gpa", missing="GPA and grading scale"))
        else:
            need_f, have_f = _gpa_fraction(opp.min_gpa, opp.gpa_scale), _gpa_fraction(hd.gpa, hd.gpa_scale)
            same_scale = (opp.gpa_scale or 0) == (hd.gpa_scale or 0) or (opp.gpa_scale and hd.gpa_scale)
            out = PASS if have_f >= need_f else FAIL
            checks.append(_check("gpa", True, out if same_scale else WARN,
                                 f"minimum GPA {opp.min_gpa}" + (f"/{opp.gpa_scale}" if opp.gpa_scale else ""), opp,
                                 "min_gpa", applicant_fact=f"{hd.gpa}/{hd.gpa_scale or '?'}",
                                 note="" if same_scale else "grading scales differ or are unstated; conversion needs the provider's own rule"))

    # 5. Age
    if opp.age_limits:
        # limits differ by study level: use the applicant's target level, never a single collapsed number
        rows = {d["level"]: d for d in opp.age_limits}
        targets = [lvl for lvl in p.target_levels if lvl in rows]
        if "master" in p.target_levels and "master" in rows and "advanced_master" in rows \
                and rows["master"] != rows["advanced_master"]:
            checks.append(_check("age", True, UNKNOWN, "age limit differs for initial and advanced master's programmes",
                                 opp, "age_limits", missing="initial or advanced master's"))
        elif not targets:
            checks.append(_check("age", True, UNKNOWN, "age limits stated per study level: " +
                                 ", ".join(f"{d['level']} {d.get('min', '')}-{d.get('max', '')}" for d in opp.age_limits),
                                 opp, "age_limits", missing="target study level"))
        else:
            ref = next((date.fromisoformat(d.date) for d in opp.deadlines if d.date and d.kind == DeadlineKind.SCHOLARSHIP
                        and d.certainty == DeadlineCertainty.CONFIRMED), today)
            a = age_on(p, ref)
            lim = rows[targets[0]]
            desc = f"{targets[0]}: " + " ".join(x for x in (f"min {lim['min']}" if "min" in lim else "",
                                                           f"max {lim['max']}" if "max" in lim else "") if x)
            if a is None:
                checks.append(_check("age", True, UNKNOWN, desc, opp, "age_limits", missing="date of birth"))
            else:
                ok_age = a <= lim.get("max", 200) and a >= lim.get("min", 0)
                checks.append(_check("age", True, PASS if ok_age else FAIL, desc, opp, "age_limits",
                                     applicant_fact=f"{a} on {ref.isoformat()}",
                                     note="the exact cut-off date and whether the limit is inclusive must be checked"))
    if opp.max_age is not None and not opp.age_limits:
        ref = next((date.fromisoformat(d.date) for d in opp.deadlines if d.date and d.kind == DeadlineKind.SCHOLARSHIP
                    and d.certainty == DeadlineCertainty.CONFIRMED), today)
        a = age_on(p, ref)
        if a is None:
            checks.append(_check("age", True, UNKNOWN, f"maximum age {opp.max_age}", opp, "max_age", missing="date of birth"))
        else:
            checks.append(_check("age", True, PASS if a <= opp.max_age else FAIL, f"maximum age {opp.max_age}", opp,
                                 "max_age", applicant_fact=f"{a} on {ref.isoformat()}",
                                 note="the exact cut-off date and whether the limit is inclusive must be checked"))
    if opp.min_age is not None and not opp.age_limits:
        ref = next((date.fromisoformat(d.date) for d in opp.deadlines if d.date and d.kind == DeadlineKind.SCHOLARSHIP
                    and d.certainty == DeadlineCertainty.CONFIRMED), today)
        a = age_on(p, ref)
        if a is None:
            checks.append(_check("min_age", True, UNKNOWN, f"minimum age {opp.min_age}", opp, "min_age",
                                 missing="date of birth"))
        else:
            checks.append(_check("min_age", True, PASS if a >= opp.min_age else FAIL, f"minimum age {opp.min_age}", opp,
                                 "min_age", applicant_fact=f"{a} on {ref.isoformat()}",
                                 note="the reference date for the minimum age must be checked"))

    # 6. Language
    if not opp.language_requirements:
        checks.append(Check("language", True, UNKNOWN, "no language test stated in the evidence",
                            note="absence is not a waiver; check the university's admission language rules"))
    for r in opp.language_requirements:
        mine = [t for t in p.tests if t.test.upper() == r.test.upper()]
        if mine:
            best = max(mine, key=lambda t: t.score)
            out = PASS if r.minimum is None or best.score >= r.minimum else FAIL
            note = "" if best.confirmed else "score not confirmed by the applicant"
            checks.append(_check(f"language.{r.test}", r.mandatory, out if best.confirmed or out == FAIL else WARN,
                                 f"{r.test} >= {r.minimum}", opp, f"language.{r.test}",
                                 applicant_fact=f"{best.test} {best.score}", note=note))
        else:
            alt = [f"{t.test} {t.score}" for t in p.tests]
            note = ("applicant holds " + ", ".join(alt) + "; equivalence is not assumed - check accepted tests") if alt else ""
            if opp.moi_policy and any((e.language_of_instruction or "").lower() == "english" for e in p.education):
                note += ("; the source mentions a medium-of-instruction route: '" + opp.moi_policy[:140] +
                         "' - confirm it applies to you before relying on it")
            checks.append(_check(f"language.{r.test}", r.mandatory, UNKNOWN,
                                 f"{r.test} >= {r.minimum}", opp, f"language.{r.test}", note=note.strip("; "),
                                 missing=f"{r.test} result" if not alt else ""))

    # 7. Work experience
    if opp.min_work_years:
        wy = work_years(p, today=today)
        checks.append(_check("work_experience", True, PASS if wy >= opp.min_work_years else FAIL,
                             f"{opp.min_work_years}+ years work experience", opp, "min_work_years",
                             applicant_fact=f"{wy} years", note="only roles with start dates are counted"))

    # 8. Discipline (soft unless the source restricts it - recorded as a preference here)
    if opp.disciplines and p.disciplines:
        ok = any(d.lower() in o.lower() or o.lower() in d.lower() for d in p.disciplines for o in opp.disciplines)
        checks.append(Check("discipline", False, PASS if ok else WARN, ",".join(opp.disciplines),
                            applicant_fact=",".join(p.disciplines)))

    # 9. Supervisor / proposal (things to prepare, not eligibility gates)
    if opp.requires_supervisor:
        checks.append(_check("supervisor", True, UNKNOWN, "supervisor contact or acceptance needed", opp,
                             "requires_supervisor", missing="supervisor contact / acceptance letter"))

    # 10. Preferences (never disqualifying)
    if p.preferred_countries and opp.destination_countries:
        ok = bool(set(p.preferred_countries) & set(opp.destination_countries))
        checks.append(Check("destination_preference", False, PASS if ok else WARN, ",".join(opp.destination_countries),
                            applicant_fact=",".join(p.preferred_countries)))

    return _decide(opp, p, checks, domestic)


def _decide(opp: Opportunity, p: Profile, checks: list[Check], domestic: bool) -> dict:
    mand = [c for c in checks if c.mandatory]
    fails = [c for c in mand if c.outcome == FAIL]
    hard_fails = [c for c in fails if c.evidence_status == str(VerificationStatus.CONFIRMED) or not c.evidence_url
                  and c.name in ("prior_degree",)]
    missing = sorted({c.missing for c in checks if c.missing})
    unknown = [c for c in mand if c.outcome == UNKNOWN]
    core_missing = {"citizenship", "target study level"} & set(missing)

    if hard_fails:
        decision = EligibilityStatus.INELIGIBLE
    elif fails:
        decision = EligibilityStatus.UNCERTAIN
    elif core_missing:
        decision = EligibilityStatus.INSUFFICIENT_INFORMATION
    elif not unknown and all(c.evidence_status in (str(VerificationStatus.CONFIRMED), "") for c in mand if c.outcome == PASS):
        decision = EligibilityStatus.ELIGIBLE
    elif any(c.name == "nationality" and c.outcome == PASS for c in mand) and \
            any(c.name == "study_level" and c.outcome == PASS for c in mand) and len(unknown) <= 2:
        decision = EligibilityStatus.LIKELY_ELIGIBLE
    elif missing and len(missing) >= len(unknown):
        decision = EligibilityStatus.INSUFFICIENT_INFORMATION
    else:
        decision = EligibilityStatus.UNCERTAIN

    uncertainties = [f"{c.name}: {c.note or 'requirement not confirmed'}" for c in checks
                     if c.outcome in (UNKNOWN, WARN) or (c.outcome == FAIL and c not in hard_fails)]
    uncertainties += opp.uncertainties + [f"conflict: {x}" for x in opp.conflicts]
    if p.inferred:
        uncertainties.append("inferred profile facts were not used as proof: " + ", ".join(p.inferred))

    if decision == EligibilityStatus.INELIGIBLE:
        action = "Skip, unless the provider confirms an exception for: " + ", ".join(c.name for c in hard_fails)
    elif decision == EligibilityStatus.INSUFFICIENT_INFORMATION:
        action = "Complete your profile: " + ", ".join(missing)
    elif fails:
        action = "Verify on the official page: " + ", ".join(c.name for c in fails)
    elif opp.verification_status != VerificationStatus.CONFIRMED:
        action = f"Run /verify {opp.id} against the official page before investing effort"
    elif unknown:
        action = "Confirm with the provider: " + ", ".join(c.name for c in unknown)
    else:
        action = f"Shortlist and run /plan {opp.id}"

    return {
        "opportunity_id": opp.id,
        "title": opp.title,
        "decision": str(decision),
        "track": "domestic" if domestic else "international",
        "supporting_requirements": [{"requirement": c.requirement, "source": c.evidence_url, "status": c.evidence_status}
                                    for c in checks if c.evidence_url],
        "applicant_facts_used": {c.name: c.applicant_fact for c in checks if c.applicant_fact},
        "matches": [c.name for c in checks if c.outcome == PASS],
        "mismatches": [{"check": c.name, "mandatory": c.mandatory, "requirement": c.requirement,
                        "applicant": c.applicant_fact, "hard": c in hard_fails} for c in checks
                       if c.outcome == FAIL or (c.outcome == WARN and not c.mandatory)],
        "missing_information": missing,
        "uncertainties": uncertainties,
        "next_action": action,
        "checks": [asdict(c) for c in checks],
    }
