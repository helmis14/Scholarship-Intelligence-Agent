"""DAAD scholarship database (funding for study and research in Germany).

Access method (inspected 2026-10-17): the public database page
https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/
loads its complete dataset as static JavaScript files (TaffyDB):

  .../data/a/js/scholarships.js   programmes: names, isDaad, applicant status ids, origin-country ids,
                                  subject groups, intentions, introduction
  .../data/a/js/deadlines.js      per programme: general note + deadline text per origin country
  .../data/a/js/origin.js         origin country ids -> names (de/en/es)
  .../data/a/js/status.js         applicant groups (undergraduates, graduates, doctoral, postdoc, faculty)
  .../data/a/js/intentions.js     study, research, teaching, internship, language course

www2.daad.de serves no robots.txt (HTTP 404 = no published restriction). These are the files any
visitor's browser downloads; no API key, login or query interface is used. Detail pages
(`?detail=<sapProgid>`) carry funding value, duration and requirements and are fetched only
when `details=True`, one request per programme, rate-limited.

Lifecycle: a DAAD record is a *funding programme*. Deadlines differ by the applicant's country
of origin and are stored per country in provider_metadata; dated ones also become Deadline rows.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

from .. import countries
from ..extract import Page, clean_snippet, extract_opportunity, page_from_response, parse_dates
from ..models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, NationalityRule, Opportunity,
                      ProviderType, SourceType, VerificationStatus, stable_id)
from ..net import Fetcher, FetchError
from ..store import now
from .base import AdapterResult

BASE = "https://www2.daad.de/bundles/daadstipendiendatenbanklsh/data/a/js/"
DB_URL = "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/"
FILES = ("scholarships", "deadlines", "origin", "status", "intentions", "subjectgroups")
STATUS_LEVEL = {1: "bachelor", 3: "master", 4: "phd", 2: "postdoc"}
INTENTION_TYPE = {1: "scholarship_programme", 2: "fellowship", 3: "scholarship_programme", 4: "fellowship",
                  5: "fellowship"}
# DAAD names that countries.code() does not know
NAME_FIX = {"Korea, Republic": "KR", "Korea, Democratic People's Republic": "KP", "Congo, Democratic Republic": "CD",
            "Palestinian Territories": "PS", "Russian Federation": "RU", "Hong Kong (CN)": "HK", "Macau (CN)": "MO",
            "Brunei Darussalam": "BN", "Moldova, Republic": "MD", "Syrian Arab Republic": "SY", "Viet Nam": "VN",
            "Tanzania, United Republic": "TZ", "Iran, Islamic Republic": "IR", "Lao People's Democratic Republic": "LA",
            "Czech Republic": "CZ", "Turkey": "TR", "Türkiye": "TR", "Cape Verde": "CV", "Swaziland": "SZ",
            "Eswatini": "SZ", "North Macedonia": "MK", "Bosnia and Herzegovina": "BA", "Ivory Coast": "CI",
            "Côte d'Ivoire": "CI", "Timor-Leste": "TL", "East Timor": "TL", "Micronesia": "FM", "Myanmar": "MM",
            "Eswatani": "SZ", "French Guayana": "GF", "Macao (CN)": "MO", "Syrian Arab Republic (Syria)": "SY",
            "Bermudas": "BM", "Réunion": "RE", "Vatican City": "VA", "Tahiti": "PF"}


def parse_taffy(js: str) -> list:
    """`var x = TAFFY([...]);` -> list. Only the JSON literal is read; nothing is executed."""
    i, j = js.find("TAFFY("), js.rfind(")")
    if i < 0 or j <= i:
        raise ValueError("not a TAFFY data file")
    return json.loads(js[i + 6:j])


def origin_code(name: str) -> Optional[str]:
    n = re.sub(r"\s*\((?:brit|frz|usa|cn)\.?\)", "", name or "").strip()
    head = n.split(",")[0].strip()  # "Moldova, Republic of" -> "Moldova"
    return NAME_FIX.get(name) or NAME_FIX.get(n) or countries.code(n) or countries.code(head)


def detail_url(prog_id) -> str:
    return f"{DB_URL}?status=&origin=&subjectGrps=&daad=&intention=&q=&page=1&detail={prog_id}"


def _first_date(text: str) -> Optional[date]:
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text or "")
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    d = [x for x, _ in parse_dates(text or "") if x]
    return d[0] if d else None


class DAADAdapter:
    name = "daad"

    def __init__(self, fetcher: Fetcher, today: Optional[date] = None, details: bool = False, detail_limit: int = 25,
                 lang: str = "en"):
        self.fetcher, self.today, self.details, self.detail_limit = fetcher, today or date.today(), details, detail_limit
        self.lang = "En" if lang == "en" else "De"

    def _load(self, res: AdapterResult) -> dict[str, list]:
        data = {}
        for f in FILES:
            url = BASE + f + ".js"
            res.requests += 1
            r = self.fetcher.get(url)
            data[f] = parse_taffy(r.text)
        return data

    def run(self, limit: Optional[int] = None) -> AdapterResult:
        res = AdapterResult(self.name, access_method="published static dataset (scholarships.js et al.)")
        try:
            data = self._load(res)
        except (FetchError, ValueError) as e:
            res.failures.append({"url": BASE, "error": getattr(e, "reason", str(e))})
            return res
        origins = {o["id"]: o for o in data["origin"]}
        deadlines = {d["id"]: d for d in data["deadlines"]}
        status = {s["id"]: s for s in data["status"]}
        intents = {i["id"]: i for i in data["intentions"]}
        subjects = {s["code"]: s for s in data["subjectgroups"]}
        ts = now()
        unmapped: set[str] = set()
        for row in data["scholarships"][:limit]:
            opp = self.normalize(row, origins, deadlines.get(row.get("sapProgid")), status, intents, subjects, ts,
                                 unmapped)
            res.records.append(opp)
        if unmapped:
            res.notes.append("origin names not mapped to ISO codes (kept in metadata): " + ", ".join(sorted(unmapped)))
        if self.details:
            for opp in res.records[:self.detail_limit]:
                self.enrich_from_detail(opp, res)
        res.notes.append("Deadlines depend on the applicant's country of origin; see provider_metadata.deadlines_by_origin.")
        return res

    def normalize(self, row, origins, dl, status, intents, subjects, ts, unmapped) -> Opportunity:
        L = self.lang
        prog = row.get("sapProgid") or row.get("id")
        title = row.get(f"programmname{L}") or row.get(f"name{L}") or row.get("nameEn") or f"DAAD programme {prog}"
        is_daad = bool(row.get("isDaad"))
        provider = "German Academic Exchange Service (DAAD)"
        if not is_daad and ":" in title:
            provider = title.split(":", 1)[0].strip()
        url = detail_url(prog)
        src = BASE + "scholarships.js"
        ev = []

        def add(field, value, snippet, source=src):
            ev.append(Evidence(field=field, value=value, source_url=source, source_type=SourceType.OFFICIAL,
                               snippet=clean_snippet(snippet), retrieved_at=ts, verified_at=ts, confidence=0.95,
                               status=VerificationStatus.CONFIRMED, note="structured official dataset", method="structured", authority="4_official_catalogue_feed"))

        names = [origins.get(i, {}).get("nameEn", f"#{i}") for i in row.get("origin", [])]
        codes = []
        for n in names:
            c = origin_code(n)
            if c:
                codes.append(c)
            else:
                unmapped.add(n)
        nat = NationalityRule(mode="include", countries=sorted(set(codes)),
                              note=f"DAAD origin list ({len(names)} entries)") if names else NationalityRule()
        levels = sorted({STATUS_LEVEL[s] for s in row.get("status", []) if s in STATUS_LEVEL})
        groups = [status.get(s, {}).get("nameEn", str(s)) for s in row.get("status", [])]
        intentions = [intents.get(i, {}).get("nameEn", str(i)) for i in row.get("intentions", [])]
        otype = next((INTENTION_TYPE[i] for i in row.get("intentions", []) if i in INTENTION_TYPE), "scholarship_programme")
        opp = Opportunity(id=stable_id("daad", str(prog), prefix="sch"), title=title[:200], provider_name=provider,
                          provider_type=ProviderType.PUBLIC_AGENCY if is_daad else ProviderType.FOUNDATION,
                          info_url=url, destination_countries=["DE"], study_levels=levels, nationality=nat,
                          disciplines=[subjects.get(c, {}).get("nameEn", c) for c in row.get("subjectGrps", [])],
                          opportunity_type=otype, discovered_via="adapter:daad", created_at=ts)
        add("title", title, f"programmname{L}: {title}")
        if names:
            add("nationality", nat.to_dict(), f"origin ids {len(names)}: " + ", ".join(names[:12]) + ("..." if len(names) > 12 else ""))
        if levels:
            add("study_levels", levels, "status: " + ", ".join(groups))
        by_origin: dict[str, list[str]] = {}
        if dl:
            general = (dl.get("general") or {}).get(L.lower()) or ""
            if general.strip():
                opp.uncertainties.append("DAAD deadline note: " + clean_snippet(re.sub(r"<[^>]+>", " ", general), 240))
            for oid, entries in (dl.get("countries") or {}).items():
                cname = origins.get(int(oid), {}).get("nameEn", oid) if str(oid).isdigit() else oid
                code = origin_code(cname) or cname
                for e in entries:
                    txt = re.sub(r"<[^>]+>", " ", (e or {}).get(L.lower()) or "")
                    by_origin.setdefault(code, []).append(clean_snippet(txt, 200))
            seen: dict[str, list[str]] = {}
            for code, texts in by_origin.items():
                for t in texts:
                    d = _first_date(t)
                    if d:
                        seen.setdefault(d.isoformat(), []).append(code)
            for iso, codes_ in sorted(seen.items()):
                d = date.fromisoformat(iso)
                cert = DeadlineCertainty.HISTORICAL if d < self.today else DeadlineCertainty.CONFIRMED
                opp.deadlines.append(Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=cert, date=iso,
                                              label=f"for applicants from {', '.join(sorted(codes_)[:8])}"
                                                    + ("..." if len(codes_) > 8 else ""),
                                              source_url=BASE + "deadlines.js"))
                add("deadline.scholarship", iso, f"deadlines.js origin {', '.join(sorted(codes_)[:6])}: {iso}",
                    source=BASE + "deadlines.js")
            if not seen and not general.strip():
                opp.uncertainties.append("no deadline published in the DAAD dataset for this programme")
        else:
            opp.uncertainties.append("no deadline entry in the DAAD dataset for this programme")
        opp.provider_metadata = {"daad_prog_id": prog, "daad_obj_id": row.get("sapObjid"), "is_daad": is_daad,
                                 "programme_type_id": row.get("programmtypId"), "applicant_groups": groups,
                                 "intentions": intentions, "origin_names": names, "deadlines_by_origin": by_origin,
                                 "introduction": (row.get("introduction") or {}).get(L.lower(), "")}
        opp.evidence = ev
        opp.verification_status = VerificationStatus.EXTRACTED  # programme-level terms come from the detail page
        return opp

    def enrich_from_detail(self, opp: Opportunity, res: AdapterResult) -> None:
        res.requests += 1
        try:
            resp = self.fetcher.get(opp.info_url)
        except FetchError as e:
            res.failures.append({"url": opp.info_url, "error": e.reason})
            return
        self.apply_detail(opp, page_from_response(resp))

    def apply_detail(self, opp: Opportunity, page: Page) -> None:
        det, _ = extract_opportunity(page, provider_name=opp.provider_name, provider_type=opp.provider_type,
                                     source_type=SourceType.OFFICIAL, country_hint=["DE"], retrieved_at=now(),
                                     today=self.today)
        opp.funding = det.funding or opp.funding
        opp.funding_duration = det.funding_duration or opp.funding_duration
        opp.language_requirements = det.language_requirements or opp.language_requirements
        opp.required_documents = det.required_documents or opp.required_documents
        for k in ("min_gpa", "max_age", "min_age", "min_work_years"):
            if getattr(opp, k) is None and getattr(det, k) is not None:
                setattr(opp, k, getattr(det, k))
        keep = {"title", "nationality", "study_levels"}  # the dataset is authoritative for these
        opp.evidence += [e for e in det.evidence if e.field not in keep and not e.field.startswith("deadline")]
        opp.selection_criteria = det.selection_criteria or opp.selection_criteria
        opp.uncertainties += [u for u in det.uncertainties if "deadline" not in u and "nationality" not in u]
