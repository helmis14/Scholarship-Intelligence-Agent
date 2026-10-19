"""Application requirements matrix and dependency-aware timeline.

Built only from what the opportunity's evidence lists, plus requirements the
evidence implies (a stated IELTS minimum implies a test certificate). Nothing
is added just because "scholarships usually want it"; items the source does
not settle are marked as such.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .models import DeadlineCertainty, DeadlineKind, Opportunity, Profile, RequiredDocument

PREP_DAYS = {"Passport": 30, "Academic transcripts": 14, "Degree certificate": 14, "CV": 3, "Motivation letter": 7,
             "Statement of purpose": 10, "Personal statement": 7, "Scholarship essay": 7, "Recommendation letters": 21,
             "Research proposal": 21, "Study plan": 5, "Language test certificate": 35, "MOI letter": 14,
             "Admission or acceptance letter": 60, "Financial statement": 7, "Medical certificate": 10,
             "Police clearance": 21, "Portfolio or writing sample": 14, "Supervisor acceptance": 30,
             "Recommender briefing pack": 2}
DEPENDS = {"Recommendation letters": ["Recommender briefing pack", "CV"],
           "Recommender briefing pack": ["CV"],
           "Motivation letter": ["CV"], "Statement of purpose": ["CV"], "Scholarship essay": ["CV"],
           "Research proposal": ["Supervisor acceptance"] , "Admission or acceptance letter": ["Academic transcripts"],
           "Supervisor acceptance": ["CV", "Research proposal draft"]}
BUFFER_DAYS = 3


def _deadline_for(opp: Opportunity, doc: RequiredDocument, today: date):
    kind = {"admission": DeadlineKind.ADMISSION}.get(doc.category, DeadlineKind.SCHOLARSHIP)
    if doc.name == "Recommendation letters":
        kind = DeadlineKind.RECOMMENDATION
    cands = [d for d in opp.deadlines if d.date and d.certainty != DeadlineCertainty.HISTORICAL
             and date.fromisoformat(d.date) >= today]
    exact = [d for d in cands if d.kind == kind] or [d for d in cands if d.kind == DeadlineKind.SCHOLARSHIP] or cands
    return min(exact, key=lambda d: d.date) if exact else None


def requirements_matrix(opp: Opportunity, p: Profile, generated: set[str] | None = None,
                        today: Optional[date] = None) -> dict:
    today = today or date.today()
    generated = {g.lower() for g in (generated or set())}
    held = {d.lower() for d in p.documents_ready}
    docs = list(opp.required_documents)
    names = {d.name for d in docs}
    implied = []
    if opp.language_requirements and "Language test certificate" not in names:
        tests = ", ".join(f"{r.test} {r.minimum}" for r in opp.language_requirements)
        implied.append(RequiredDocument(name="Language test certificate", category="admission", mandatory=True,
                                        format=tests, source_url=opp.info_url))
    if opp.requires_supervisor and "Supervisor acceptance" not in names:
        implied.append(RequiredDocument(name="Supervisor acceptance", category="scholarship", mandatory=True,
                                        source_url=opp.info_url))
    if "Recommendation letters" in names:
        implied.append(RequiredDocument(name="Recommender briefing pack", category="scholarship", mandatory=False,
                                        format="internal - for your referees"))
    rows = []
    for d in docs + implied:
        dl = _deadline_for(opp, d, today)
        prep = PREP_DAYS.get(d.name, 7) + (10 if d.translation else 0) + (7 if d.certification else 0)
        lname = d.name.lower()
        if lname in held:
            readiness = "held"
        elif lname in generated:
            readiness = "draft exists"
        elif d.name == "Language test certificate" and any(
                t.test.upper() == r.test.upper() and (r.minimum is None or t.score >= r.minimum)
                for t in p.tests for r in opp.language_requirements):
            readiness = "held"
        else:
            readiness = "missing"
        start_by = (date.fromisoformat(dl.date) - timedelta(days=prep + BUFFER_DAYS)) if dl else None
        missing_info = []
        if d.mandatory is None:
            missing_info.append("whether mandatory")
        if not dl:
            missing_info.append("deadline not confirmed")
        if d.name in ("Scholarship essay", "Personal statement", "Motivation letter", "Statement of purpose") \
                and not d.prompt:
            missing_info.append("exact prompt")
        if readiness == "held":
            action = "Check it is current and in the required format"
        elif d.name == "Recommendation letters":
            action = "Ask referees now and send them the briefing pack"
        elif d.name in PREP_DAYS and d.name in ("Passport", "Academic transcripts", "Degree certificate",
                                                "MOI letter", "Police clearance", "Medical certificate"):
            action = "Request from the issuing office"
        else:
            action = f"Draft with /prepare {opp.id}" if d.name in ("CV", "Motivation letter", "Statement of purpose",
                                                                   "Personal statement", "Scholarship essay",
                                                                   "Research proposal", "Study plan",
                                                                   "Recommender briefing pack") else "Obtain"
        urgent = bool(start_by and start_by <= today and readiness != "held")
        rows.append({
            "name": d.name, "category": d.category,
            "mandatory": {True: "mandatory", False: "optional", None: "unclear"}[d.mandatory],
            "source": d.source_url or opp.info_url, "readiness": readiness, "format": d.format,
            "word_limit": d.word_limit, "translation": d.translation, "certification": d.certification,
            "prep_days": prep, "deadline": dl.date if dl else None,
            "deadline_certainty": str(dl.certainty) if dl else "unknown",
            "start_by": start_by.isoformat() if start_by else None,
            "dependencies": DEPENDS.get(d.name, []), "missing_information": missing_info,
            "next_action": action, "status": "done" if readiness == "held" else "todo", "urgent": urgent,
        })
    rows.sort(key=lambda r: (r["status"] == "done", r["start_by"] or "9999", r["name"]))
    notes = []
    if not opp.required_documents:
        notes.append("The source lists no required documents. Check the application form; this matrix is incomplete.")
    cats = {r["category"] for r in rows}
    for c in ("admission", "scholarship", "visa", "enrollment"):
        if c not in cats:
            notes.append(f"No {c} requirements found in the evidence (not the same as none existing).")
    return {"opportunity_id": opp.id, "as_of": today.isoformat(), "matrix": rows, "notes": notes,
            "timeline": timeline(rows, today)}


def timeline(rows: list[dict], today: date) -> list[dict]:
    """Order work so dependencies come first, then by start-by date."""
    by = {r["name"]: r for r in rows}
    order, seen = [], set()

    def visit(n, stack=()):
        if n in seen or n in stack or n not in by:
            return
        for dep in by[n]["dependencies"]:
            visit(dep, stack + (n,))
        seen.add(n)
        order.append(by[n])

    for r in sorted(rows, key=lambda r: r["start_by"] or "9999"):
        visit(r["name"])
    return [{"step": i + 1, "task": r["name"], "start_by": r["start_by"], "deadline": r["deadline"],
             "urgent": r["urgent"], "status": r["status"], "after": [d for d in r["dependencies"] if d in by]}
            for i, r in enumerate(order) if r["status"] != "done"]
