"""CampusBourses, Campus France's database of scholarships for study and research in France (round 49).

Access method (inspected 2026-10-26): the public search page https://campusbourses.campusfrance.org/ is an
Angular application that loads its data from the JSON interface it names in its own script:

  https://bourses-api.campusfrance.org/sgetgrants/<lang>       every programme: title, summary, type, level,
                                                                subject, country of the applicant ("Location"),
                                                                funder ids, last update and "Apply before" date
  https://bourses-api.campusfrance.org/sgetgrant/<id>/<lang>   one programme: description, value, duration, age,
                                                                language, other criteria, documents, dates,
                                                                selection, how to apply and links
  js/ilangular.<hash>.js on the site                           the lists the ids stand for (countries with their
                                                                ISO codes, levels, types, subjects, funders)

Neither host publishes a robots.txt (HTTP 404, no restriction). These are the files a visitor's browser loads; no
key, log-in or query interface beyond them is used. Details are fetched only when `details=True`, one request per
programme, rate-limited.

Lifecycle: a record is a funding programme for study in France as Campus France lists it. "Location" is where the
applicant comes from: its countries are the nationality rule when listed; an empty list states none, and the
programme's own text decides. "Apply before" is the applicant deadline the catalogue shows.
"""

from __future__ import annotations

import html as htmllib
import json
import re
from datetime import date
from typing import Optional

from ..extract import Page, clean_snippet, extract_opportunity
from ..models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, FundingComponent, NationalityRule, Opportunity,
                      ProviderType, SourceType, VerificationStatus, stable_id)
from ..net import Fetcher, FetchError
from ..store import now
from .base import AdapterResult

API = "https://bourses-api.campusfrance.org/"
SITE = "https://campusbourses.campusfrance.org/"
LEVELS = {"1": "bachelor", "2": "master", "3": "phd", "4": "postdoc"}
TYPE_KIND = {"1": "scholarship_programme", "2": "fellowship", "3": "grant", "4": "grant", "5": "scholarship_programme",
             "6": "scholarship_programme"}   # study, research, internship, travel, tuition and other fee reductions
# a detail field, the heading the site shows for it
DETAIL_FIELDS = [("description", "Program description"), ("montant", "Value/Benefits"), ("duree", "Duration"),
                 ("age", "Age"), ("countryNote", "Location"), ("levelNote", "Level"), ("domainNote", "Subject area"),
                 ("maitriseLangue", "Language skills"), ("conditionsSupplementaires", "Additional criteria"),
                 ("inscription", "Application process"), ("pieces", "Required documents"), ("dates", "Deadlines"),
                 ("selection", "Selection process")]


def lookup_tables(script: str) -> dict[str, dict[str, dict]]:
    """{"IwCountry": {id: {"en":..., "iso":...}}, "IwLevel": ..., ...} from the site's script. Only the literal arrays
    of the named factories are read; nothing is executed."""
    out: dict[str, dict[str, dict]] = {}
    for name in ("IwCountry", "IwLevel", "IwType", "IwFunding", "IwDomain"):
        i = script.find(f'factory("{name}"')
        j = script.find("=[{", i) if i >= 0 else -1
        k = script.find("}]", j) if j >= 0 else -1
        if k < 0:
            continue
        rows = {}
        for obj in re.findall(r"\{([^{}]*)\}", script[j + 1:k + 2]):
            d = {key: (json.loads(v) if v.startswith('"') else v)
                 for key, v in re.findall(r'(\w+):("(?:[^"\\]|\\.)*"|[\d.]+)', obj)}
            if "id" in d:
                rows[str(d["id"])] = d
        out[name] = rows
    return out


def _ids(v) -> list[str]:
    return [x.strip() for x in str(v or "").split(",") if x.strip()]


def _text(h: str) -> str:
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", h or "")).split())


def _value_lines(h: str) -> str:
    """A value line that starts with an amount says what it is ("€1,400 or €1,500 per month + travel" is the grant,
    not the travel)."""
    lines = [_text(x) for x in re.split(r"<(?:br|/?p|/?li|/?div)\b[^>]*>", h or "")]
    return "".join(f"<p>{'Scholarship value: ' if re.match(r'(?:€|\$|£|EUR\b|USD\b|[0-9])', x) else ''}"
                   f"{htmllib.escape(x)}</p>" for x in lines if x)


def detail_page(url: str, title: str, d: dict) -> Page:
    """The programme's detail fields as one page under the site's own headings."""
    body = "".join(f"<h3>{head}</h3>{_value_lines(d[f]) if f == 'montant' else d[f]}"
                   for f, head in DETAIL_FIELDS if _text(d.get(f, "")))
    return Page(url, f"<html><head><title>{htmllib.escape(title)}</title></head><body>{body}</body></html>")


class CampusFranceAdapter:
    name = "campusfrance"

    def __init__(self, fetcher: Fetcher, today: Optional[date] = None, details: bool = False,
                 detail_limit: Optional[int] = None, lang: str = "en"):
        self.fetcher, self.today, self.details, self.detail_limit = fetcher, today or date.today(), details, detail_limit
        self.lang = lang if lang in ("en", "fr", "es") else "en"

    def _tables(self, res: AdapterResult) -> dict:
        try:
            res.requests += 1
            home = self.fetcher.get(SITE).text
            m = re.search(r'src="(js/ilangular\.[0-9a-f]+\.js)"', home)
            if not m:
                raise ValueError("lookup script not named on the search page")
            res.requests += 1
            return lookup_tables(self.fetcher.get(SITE + m.group(1)).text)
        except (FetchError, ValueError) as e:
            res.failures.append({"url": SITE, "error": getattr(e, "reason", str(e))})
            res.notes.append("lookup lists unavailable: countries, levels and subjects are left out")
            return {}

    def run(self, limit: Optional[int] = None) -> AdapterResult:
        res = AdapterResult(self.name, access_method="the search page's own JSON interface (sgetgrants, sgetgrant)")
        url = f"{API}sgetgrants/{self.lang}"
        try:
            res.requests += 1
            data = json.loads(self.fetcher.get(url).text)
        except (FetchError, ValueError) as e:
            res.failures.append({"url": url, "error": getattr(e, "reason", str(e))})
            return res
        tables = self._tables(res)
        ts = now()
        for row in (data.get("programs") or [])[:limit]:
            res.records.append(self.normalize(row, tables, ts))
        if self.details:
            for opp in res.records[:self.detail_limit]:
                self.enrich_from_detail(opp, res)
        return res

    def normalize(self, row: dict, tables: dict, ts: str) -> Opportunity:
        pid = str(row.get("bourseId"))
        title = (row.get("title") or f"CampusBourses programme {pid}").strip()
        src = f"{API}sgetgrants/{self.lang}"
        countries_ = tables.get("IwCountry", {})
        codes = sorted({countries_[i]["iso"] for i in _ids(row.get("countryListId")) if countries_.get(i, {}).get("iso")})
        levels = sorted({LEVELS[i] for i in _ids(row.get("levelListId")) if i in LEVELS})
        domains = tables.get("IwDomain", {})
        subjects = [domains.get(str(int(i) // 10000) if i.isdigit() and int(i) >= 10000 else i, {}).get("en", "")
                    for i in _ids(row.get("domainListId"))]
        types = _ids(row.get("typeListId"))
        names = tables.get("IwType", {})
        funders = [tables.get("IwFunding", {}).get(i, {}).get("en", i) for i in _ids(row.get("fundingByListId"))]
        opp = Opportunity(id=stable_id("campusfrance", pid, prefix="sch"), title=title[:200],
                          provider_name="Campus France (CampusBourses)", provider_type=ProviderType.PUBLIC_AGENCY,
                          info_url=f"{SITE}#/program/{pid}", destination_countries=["FR"], study_levels=levels,
                          disciplines=[s for s in subjects if s],
                          opportunity_type=next((TYPE_KIND[t] for t in types if t in TYPE_KIND), "scholarship_programme"),
                          discovered_via="adapter:campusfrance", created_at=ts)

        def add(field, value, snippet):
            opp.evidence.append(Evidence(field=field, value=value, source_url=src, source_type=SourceType.OFFICIAL,
                                         snippet=clean_snippet(snippet), retrieved_at=ts, verified_at=ts, confidence=0.95,
                                         status=VerificationStatus.CONFIRMED, note="structured official dataset",
                                         method="structured", authority="4_official_catalogue_feed"))
        add("title", title, f"title: {title}")
        add("destination", "FR", "Campus France scholarship database: study and research in France")
        if codes:
            opp.nationality = NationalityRule(mode="include", countries=codes,
                                              note=f"CampusBourses location list ({len(codes)} countries)")
            add("nationality", opp.nationality.to_dict(), "Location: " + ", ".join(
                countries_[i].get("en", i) for i in _ids(row.get("countryListId")) if i in countries_)[:280])
        if levels:
            add("study_levels", levels, "Level: " + ", ".join(levels))
        end = str(row.get("endAt") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
            cert = DeadlineCertainty.HISTORICAL if end < self.today.isoformat() else DeadlineCertainty.CONFIRMED
            opp.deadlines.append(Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=cert, date=end, source_url=src,
                                          label=f"Apply before: {end}"))
            add("deadline.scholarship", end, f"Apply before: {end}")
        opp.provider_metadata = {"campusbourses_id": pid, "institution_id": row.get("etabId"),
                                 "types": [names.get(t, {}).get("en", t) for t in types], "funded_by": funders,
                                 "managed_by_campus_france": bool(row.get("tcampus")),
                                 "updated": row.get("updatedAt", ""), "summary": row.get("synthese", "")}
        opp.verification_status = VerificationStatus.EXTRACTED   # programme terms come from the detail page
        if len((row.get("synthese") or "").split()) >= 8:   # round 51: the database's own summary describes the programme
            from ..extract import short_description
            opp.description = short_description(row["synthese"])
        return opp

    def enrich_from_detail(self, opp: Opportunity, res: AdapterResult) -> None:
        pid = opp.provider_metadata["campusbourses_id"]
        url = f"{API}sgetgrant/{pid}/{self.lang}"
        res.requests += 1
        try:
            d = json.loads(self.fetcher.get(url).text)
        except (FetchError, ValueError) as e:
            res.failures.append({"url": url, "error": getattr(e, "reason", str(e))})
            return
        if d.get("op") != 1:
            res.failures.append({"url": url, "error": d.get("errmsg") or "not available in this language"})
            return
        self.apply_detail(opp, d, url)

    def apply_detail(self, opp: Opportunity, d: dict, url: str) -> None:
        det, _ = extract_opportunity(detail_page(url, opp.title, d), provider_name=opp.provider_name,
                                     provider_type=opp.provider_type, source_type=SourceType.OFFICIAL, country_hint=[],
                                     retrieved_at=now(), today=self.today)
        opp.funding = det.funding
        opp.funding_duration = det.funding_duration
        opp.language_requirements = det.language_requirements
        opp.required_documents = det.required_documents
        opp.selection_criteria = det.selection_criteria
        for k in ("min_gpa", "max_age", "min_age", "min_work_years"):
            setattr(opp, k, getattr(det, k))
        if opp.nationality.mode == "unknown" and det.nationality.mode != "unknown":
            opp.nationality = det.nationality   # no location list: the programme's own words decide
            keep_nat = True
        else:
            keep_nat = False
        known = {d_.date for d_ in opp.deadlines}
        opp.deadlines += [x for x in det.deadlines if not (x.date and x.date in known)]
        if "5" in d.get("typeListId", "").split(",") and not any(c.kind == "tuition" for c in opp.funding):
            opp.funding.append(FundingComponent(kind="tuition", covered=True, full=False,
                                                note="partial tuition fee waiver (CampusBourses grant type)"))
        apply_url = (d.get("inscriptionUrl") or "").strip()
        opp.application_url = apply_url if apply_url.startswith("http") else det.application_url
        opp.provider_metadata["links"] = [{"name": d.get(f"web{i}", ""), "url": d.get(f"url{i}", "")}
                                          for i in (1, 2, 3) if d.get(f"url{i}")]
        if (d.get("web1") or "").strip():   # the embassy, school or foundation that offers it, as Campus France names it
            opp.provider_name = d["web1"].strip()[:120]
        drop = {"title", "study_levels", "destination"} | (set() if keep_nat else {"nationality"})
        opp.evidence += [e for e in det.evidence if e.field not in drop]
