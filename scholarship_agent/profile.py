"""Applicant profile: create, update (merge), import from JSON, export, delete."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from . import countries
from .models import Fact, Profile
from .store import Store

LIST_REPLACE = True  # a list given in an update replaces the stored list (explicit, predictable)


def _codes(values: list[str]) -> list[str]:
    out = []
    for v in values or []:
        c = countries.code(v)
        if not c:
            raise ValueError(f"unknown country: {v!r} (use a name or ISO code)")
        out.append(c)
    return out


def phone_number(v: str) -> str:
    """'+62 812-3456-7890' -> '+6281234567890'. The international form only (country code first, up to 15 digits)."""
    digits = re.sub(r"[\s().-]", "", v or "")
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not re.fullmatch(r"\+[1-9]\d{6,14}", digits):
        raise ValueError("phone: use the international form with the country code, e.g. +62 812 3456 7890")
    return digits


def linkedin_url(v: str) -> str:
    """A LinkedIn profile address or name -> 'https://www.linkedin.com/in/<name>'."""
    v = (v or "").strip()
    if not v:
        return ""
    m = re.fullmatch(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([\w%-]{3,100})/?(?:\?.*)?", v, re.I) \
        or re.fullmatch(r"@?([A-Za-z0-9][\w-]{2,99})", v)
    if not m:
        raise ValueError("linkedin: use your profile address, e.g. linkedin.com/in/your-name")
    return f"https://www.linkedin.com/in/{m.group(1)}"


EXPERIENCE_KINDS = ("work", "research", "teaching", "volunteer", "leadership")
MONTH_RX = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")


def experience_rows(rows) -> list:
    """Round 51: entries from the profile form, checked; rows without a title are dropped."""
    out = []
    for e in rows:
        e.kind = (e.kind or "work").strip().lower()
        if e.kind not in EXPERIENCE_KINDS:
            raise ValueError(f"experience: kind must be one of {', '.join(EXPERIENCE_KINDS)}")
        e.title, e.organization = e.title.strip()[:200], e.organization.strip()[:200]
        e.description = " ".join(e.description.split())[:1000]
        for k in ("start", "end"):
            v = (getattr(e, k) or "").strip()
            if v and not MONTH_RX.fullmatch(v):
                raise ValueError(f"experience: {k} must be a month, YYYY-MM")
            setattr(e, k, v)
        if e.start and e.end and e.end[:7] < e.start[:7]:
            raise ValueError("experience: the end comes before the start")
        if e.title:
            out.append(e)
    return out


def normalize(p: Profile) -> Profile:
    p.phone = phone_number(p.phone)
    p.linkedin = linkedin_url(p.linkedin)
    p.citizenships = _codes(p.citizenships)
    p.preferred_countries = _codes(p.preferred_countries)
    if p.residence_country:
        p.residence_country = _codes([p.residence_country])[0]
    for e in p.education:
        if e.country:
            e.country = countries.code(e.country) or e.country
    p.target_levels = [lvl.lower() for lvl in p.target_levels]
    p.experience = experience_rows(p.experience)
    for k in ("achievements", "publications", "projects", "research_interests"):
        setattr(p, k, [" ".join(x.split())[:300] for x in getattr(p, k) if isinstance(x, str) and x.strip()][:40])
    return p


def upsert(store: Store, patch: dict, profile_id: str = "default") -> Profile:
    """Merge `patch` into the stored profile. Applications are keyed by profile id and untouched."""
    current = store.get_profile(profile_id)
    base = current.to_dict() if current else Profile(id=profile_id).to_dict()
    for k, v in patch.items():
        if k not in base:
            raise ValueError(f"unknown profile field: {k}")
        if k == "inferred" and isinstance(v, dict):
            base[k] = base.get(k, {}) | v
        elif isinstance(base[k], dict) and isinstance(v, dict):
            base[k] = base[k] | v
        else:
            base[k] = v
    base["id"] = profile_id
    p = normalize(Profile.from_dict(base))
    store.save_profile(p)
    return p


def load_file(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def age_on(p: Profile, on: date) -> Optional[int]:
    if not p.date_of_birth:
        return None
    b = date.fromisoformat(p.date_of_birth)
    return on.year - b.year - ((on.month, on.day) < (b.month, b.day))


def work_years(p: Profile, kinds=("work",), today: Optional[date] = None) -> float:
    today = today or date.today()
    total = 0.0
    for e in p.experience:
        if e.kind not in kinds or not e.start:
            continue
        s = date.fromisoformat(e.start if len(e.start) == 10 else e.start + "-01")
        en = date.fromisoformat(e.end if len(e.end) == 10 else e.end + "-01") if e.end else today
        total += max(0, (en - s).days) / 365.25
    return round(total, 1)


def highest_degree(p: Profile):
    order = {"phd": 4, "doctorate": 4, "master": 3, "bachelor": 2, "diploma": 1, "high_school": 0}
    eds = sorted(p.education, key=lambda e: order.get(e.degree.lower(), 0), reverse=True)
    return eds[0] if eds else None


def missing_core(p: Profile) -> list[str]:
    gaps = []
    for f, label in (("citizenships", "citizenship"), ("target_levels", "target study level"),
                     ("education", "education history"), ("residence_country", "country of residence")):
        if not getattr(p, f):
            gaps.append(label)
    if p.education and all(e.gpa is None for e in p.education):
        gaps.append("grades / GPA")
    if not p.tests:
        gaps.append("language test results (or a note that none are taken yet)")
    return gaps


def export(store: Store, profile_id: str = "default") -> dict:
    """Everything private stored for this profile, for the user's own copy."""
    p = store.get_profile(profile_id)
    apps = [store.dec_row(r, "applications") for r in store.q("SELECT * FROM applications WHERE profile_id = ?", (profile_id,))]
    ids = [a["id"] for a in apps]
    marks = ",".join("?" * len(ids)) or "''"
    return {
        "profile": p.to_dict() if p else None,
        "applications": apps,
        "status_history": [store.dec_row(r, "status_history") for r in store.q(
            f"SELECT * FROM status_history WHERE application_id IN ({marks})", ids)],
        "checklist": [store.dec_row(r, "checklist_items") for r in store.q(
            f"SELECT * FROM checklist_items WHERE application_id IN ({marks})", ids)],
        "documents": [store.dec_row(r, "document_versions") for r in store.q(
            f"SELECT d.kind, d.title, d.application_id, v.version, v.content, v.created_at FROM documents d "
            f"JOIN document_versions v ON v.document_id = d.id WHERE d.application_id IN ({marks})", ids)],
        "outcomes": [store.dec_row(r, "outcomes") for r in store.q(
            f"SELECT * FROM outcomes WHERE application_id IN ({marks})", ids)],
    }


def delete(store: Store, profile_id: str = "default") -> dict:
    """Remove the profile and everything private attached to it. Public catalog data stays."""
    ids = [r["id"] for r in store.q("SELECT id FROM applications WHERE profile_id = ?", (profile_id,))]
    marks = ",".join("?" * len(ids)) or "''"
    doc_ids = [r["id"] for r in store.q(f"SELECT id FROM documents WHERE application_id IN ({marks})", ids)]
    dmarks = ",".join("?" * len(doc_ids)) or "''"
    counts = {}
    with store.private as c:
        counts["document_versions"] = c.execute(f"DELETE FROM document_versions WHERE document_id IN ({dmarks})", doc_ids).rowcount
        for t in ("documents", "checklist_items", "status_history", "reminders", "outcomes"):
            counts[t] = c.execute(f"DELETE FROM {t} WHERE application_id IN ({marks})", ids).rowcount
        counts["applications"] = c.execute("DELETE FROM applications WHERE profile_id = ?", (profile_id,)).rowcount
        counts["profile_history"] = c.execute("DELETE FROM profile_history WHERE profile_id = ?", (profile_id,)).rowcount
        counts["profiles"] = c.execute("DELETE FROM profiles WHERE id = ?", (profile_id,)).rowcount
    store.private.execute("VACUUM")
    return counts


def infer(p: Profile, key: str, value, source: str = "inferred") -> None:
    p.inferred[key] = Fact(value=value, confirmed=False, source=source)
