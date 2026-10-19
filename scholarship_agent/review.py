"""Pre-submission review of a draft against the brief and the applicant's facts.

Checks: word/character limits, required topics, unsupported claims (numbers,
years, scores, named organisations, accomplishment verbs) not backed by the
fact pack, consistency with the applicant's other documents for the same
application, unfilled placeholders, formatting requirements, and the AI-use
reminder. Deterministic: it flags, it does not rewrite.
"""

from __future__ import annotations

import re
from typing import Optional

from .documents import fact_pack, fact_text

PLACEHOLDER = re.compile(r"\[(?:YOU WRITE|TODO|PLACEHOLDER|INSERT)[^\]]*\]|lorem ipsum|\bXX+\b|\[[A-Z _]{4,}\]", re.I)
NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(%|\b)")
YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
ORG = re.compile(r"\b((?:[A-Z][a-z]+|[A-Z]{2,})(?:[ \t]+(?:of|for|and|de|the)?[ \t]*(?:[A-Z][a-z]+|[A-Z]{2,})){1,6})\b")
CLAIM_VERBS = re.compile(r"\b(published|awarded|won|founded|led|managed|ranked (?:first|top)|graduated (?:first|top)|"
                         r"received (?:the|a|an) [A-Z][\w ]+(?:award|prize|scholarship|medal))\b", re.I)
# words that say nothing about which fact a claim rests on (the subject-area words of the profile are dropped too)
CLAIM_STOP = {"published", "awarded", "managed", "founded", "received", "national", "international", "award", "prize",
              "papers", "paper", "journal", "first", "scholarship", "medal", "competition", "programme", "program",
              "project", "projects", "student", "students", "team", "university", "faculty", "department"}
COMMON_CAPS = {"I", "My", "The", "This", "In", "As", "At", "During", "Dear", "Kind", "Sincerely", "Thank", "When", "After",
               "Before", "Since", "Through", "With", "Our", "We", "It", "Its", "These", "That", "There", "Their",
               "Statement", "Purpose", "Scholarship", "University", "Programme", "Program", "Master", "PhD", "Bachelor"}


def words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", re.sub(r"<!--.*?-->", "", text, flags=re.S)))


def review(text: str, brief: dict, profile, other_docs: Optional[dict[str, str]] = None) -> dict:
    issues: list[dict] = []
    o = brief.get("OPPORTUNITY_TEXT", {})
    # naming the scholarship itself is not a claim about the applicant
    facts = fact_text(profile) + "\n" + o.get("title", "") + "\n" + o.get("provider", "")
    facts_low = facts.lower()
    body = re.sub(r"^>.*$", "", text, flags=re.M)  # quoted prompt lines are not claims

    n = words(body)
    wl, cl = brief.get("word_limit"), brief.get("char_limit")
    if wl and n > wl:
        issues.append({"type": "word_limit", "severity": "error", "detail": f"{n} words > limit {wl}"})
    elif wl and n < 0.6 * wl:
        issues.append({"type": "word_limit", "severity": "info", "detail": f"{n} words, well under the {wl} limit"})
    if cl and len(body) > cl:
        issues.append({"type": "char_limit", "severity": "error", "detail": f"{len(body)} characters > limit {cl}"})

    low = body.lower()
    missing_topics = [t for t in brief.get("required_topics", []) if t not in low and t.rstrip("s") not in low]
    soft = set(brief.get("criteria_topics", []))
    for t in missing_topics:
        # round 31: a word from the selection criteria ("excellence", "feasibility") is advice, not a required part of
        # the prompt; only the prompt's own content words are warnings
        issues.append({"type": "required_topic", "severity": "info" if t in soft else "warning",
                       "detail": f"prompt/criteria term not addressed: '{t}'"})

    for m in PLACEHOLDER.finditer(body):
        issues.append({"type": "placeholder", "severity": "error", "detail": f"unfilled: {m.group(0)[:80]}"})

    unsupported = set()
    for m in NUM.finditer(body):
        v = m.group(1)
        if len(v) == 1 and "." not in v and not m.group(2):
            continue  # "one", "2 years" style small counts are too noisy to flag
        if YEAR.fullmatch(v) or "." in v or m.group(2) == "%" or len(v) >= 2:
            if v not in facts and v.rstrip("0").rstrip(".") not in facts:
                unsupported.add(v + (m.group(2) or ""))
    for m in ORG.finditer(body):
        name = m.group(1).strip()
        first = name.split()[0]
        if first in COMMON_CAPS and len(name.split()) <= 2:
            continue
        if name.lower() not in facts_low and not all(w.lower() in facts_low for w in name.split() if len(w) > 3):
            if name.lower() not in (brief.get("OPPORTUNITY_TEXT", {}).get("title", "").lower(),
                                    brief.get("OPPORTUNITY_TEXT", {}).get("provider", "").lower()):
                unsupported.add(name)
    fp = fact_pack(profile)
    domain = {w.lower() for k in ("research_interests", "disciplines") for x in fp[k] for w in re.findall(r"[A-Za-z]{4,}", x)}
    category_text = {   # round 31: a claim is checked against the facts of its own kind, not the whole profile
        "publication": " ".join(fp["publications"]).lower(),
        "award": " ".join(fp["achievements"]).lower(),
        "role": " ".join(str(v) for x in fp["experience"] for v in x.values() if v).lower() + " " + " ".join(fp["projects"]).lower(),
    }
    for m in CLAIM_VERBS.finditer(body):
        verb = m.group(0).lower()
        cat = "publication" if verb.startswith("publish") else "role" if verb in ("founded", "led", "managed") else "award"
        sent = next((s for s in re.split(r"(?<=[.!?])\s+", body) if m.group(0) in s), m.group(0))
        after = sent[sent.lower().find(verb) + len(verb):]
        key = [w for w in re.findall(r"[A-Za-z]{5,}", after) if w.lower() not in CLAIM_STOP and w.lower() not in domain]
        if not category_text[cat].strip() or not any(k.lower() in category_text[cat] for k in key):
            issues.append({"type": "missing_evidence", "severity": "warning",
                           "detail": f"accomplishment claim with no matching profile fact: '{sent[:120]}'"})
    for u in sorted(unsupported):
        issues.append({"type": "unsupported_claim", "severity": "error",
                       "detail": f"'{u}' does not appear in your confirmed profile facts"})

    gpas_here = set(re.findall(r"GPA (?:of )?(\d\.\d{1,2})", body))
    for name, other in (other_docs or {}).items():
        gpas_there = set(re.findall(r"GPA (?:of )?(\d\.\d{1,2})", other))
        if gpas_here and gpas_there and gpas_here != gpas_there:
            issues.append({"type": "consistency", "severity": "error",
                           "detail": f"GPA {sorted(gpas_here)} here vs {sorted(gpas_there)} in {name}"})

    fmt = (brief.get("format") or "").lower()
    if fmt:
        issues.append({"type": "format", "severity": "info", "detail": f"source format requirement: '{brief['format']}' - check the exported file"})
    if brief.get("kind") in ("academic_cv", "scholarship_cv") and "## Education" not in text:
        issues.append({"type": "format", "severity": "warning", "detail": "CV has no Education section"})

    issues.append({"type": "ai_policy", "severity": "info",
                   "detail": "Check the provider's rules on AI assistance; you must review, edit and own this text."})
    errors = [i for i in issues if i["severity"] == "error"]
    return {"words": n, "characters": len(body), "passed": not errors, "errors": len(errors),
            "warnings": sum(i["severity"] == "warning" for i in issues), "issues": issues}
