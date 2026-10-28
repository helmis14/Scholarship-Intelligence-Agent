"""grants.at, OeAD's Austrian database for scholarships and research grants (round 50).

Access method (inspected 2026-10-27): the search page https://grants.at/en/ loads
https://ajs.scholarships.at/JS_1.0/STIMAQuery.min.js, which calls a public JSON interface at
https://ajs.scholarships.at/ (POST, JSON body, no key or log-in):

  GetMetadata                          lookup lists: grant types, target groups, subjects, 243 countries with ISO codes
  STIMAEntrySearchForTextParameters    every programme for the given grant types (one row per programme and type)
  GetDetailHtml                        one programme: country of origin, target country, subjects, target group,
                                       funding organisation, amount, closing date, advice, a link to the provider

grants.at disallows only /typo3/ in robots.txt; ajs.scholarships.at publishes none (HTTP 404, no restriction). Details
are fetched only when `details=True`, one request per programme, rate-limited.

Lifecycle: a record is a funding programme as OeAD lists it, into or out of Austria. "Country of origin" is the
applicants' nationality rule ("All" = any), "Target country" is where the grant is used. The provider's own page
("Further information") is the record's official page when OeAD names one.
"""

from __future__ import annotations

import html as htmllib
import json
import re
from datetime import date
from typing import Optional

from ..extract import Page, clean_snippet, extract_opportunity
from ..models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, NationalityRule, Opportunity, ProviderType,
                      SourceType, VerificationStatus, stable_id)
from ..net import Fetcher, FetchError
from ..store import now
from .base import AdapterResult

API = "https://ajs.scholarships.at/"
SITE = "https://grants.at/en/"
TEMPLATE, LANG = "44", "0"   # the English template of grants.at
TYPE_KIND = {11: "scholarship_programme", 2: "scholarship_programme", 1: "scholarship_programme", 4: "grant", 5: "grant",
             7: "award", 3: "grant", 6: "grant"}
LEVELS = [(r"undergraduate", "bachelor"), (r"^graduates$", "master"), (r"postgraduate|phd students", "phd"),
          (r"post ?docs?|phd holders", "postdoc")]
ROW_RX = re.compile(r'<label>([^<]+?):?</label></div>\s*<div class="grain-data[^"]*">(.*?)</div>\s*</div>(?=\s*<div class="(?:row|linerow)")',
                    re.S)


def _text(h: str) -> list[str]:
    """The lines of an HTML fragment."""
    t = re.sub(r"<(?:br|/?div|/?p|/?li)\b[^>]*>", "\n", h or "")
    return [" ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", x)).split()) for x in t.split("\n") if re.sub(r"<[^>]+>", "", x).strip()]


def _valid(url: str) -> bool:
    from urllib.parse import urlsplit
    try:
        return bool(urlsplit(url).hostname)
    except ValueError:
        return False


def detail_rows(page_html: str) -> dict[str, str]:
    """{label: inner HTML} of the labelled rows of a GetDetailHtml answer."""
    return {htmllib.unescape(k).strip(): v for k, v in ROW_RX.findall(page_html or "")}


def closing_dates(text: str, today: date, src: str) -> list[Deadline]:
    """'15.01.2027' is a dated deadline; 'Annually (15.11.)' a yearly one (expected, no year)."""
    out = []
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        out.append(Deadline(kind=DeadlineKind.SCHOLARSHIP, date=d.isoformat(), source_url=src,
                            certainty=DeadlineCertainty.HISTORICAL if d < today else DeadlineCertainty.CONFIRMED,
                            label=f"Closing date for applications: {clean_snippet(text, 160)}"))
    if re.search(r"annually|every year|each year|jährlich", text, re.I):
        for m in re.finditer(r"\((\d{1,2})\.(\d{1,2})\.\)", text):
            try:
                date(2027, int(m.group(2)), int(m.group(1)))
            except ValueError:
                continue
            md = f"{int(m.group(2)):02d}-{int(m.group(1)):02d}"
            out.append(Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=DeadlineCertainty.EXPECTED, recurs=md, source_url=src,
                                approximate=f"every year on {int(m.group(1))}.{int(m.group(2))}.",
                                label=f"Closing date for applications: {clean_snippet(text, 160)}"))
    return out


class GrantsAtAdapter:
    name = "grants_at"

    def __init__(self, fetcher: Fetcher, today: Optional[date] = None, details: bool = False,
                 detail_limit: Optional[int] = None):
        self.fetcher, self.today, self.details, self.detail_limit = fetcher, today or date.today(), details, detail_limit
        self.countries: dict[str, str] = {}

    def _post(self, method: str, payload: dict, res: AdapterResult):
        res.requests += 1
        return json.loads(self.fetcher.post_json(API + method, payload).text)

    def run(self, limit: Optional[int] = None) -> AdapterResult:
        res = AdapterResult(self.name, access_method="the search page's own JSON interface (ajs.scholarships.at)")
        try:
            meta = self._post("GetMetadata", {"TemplateID": TEMPLATE, "LanguageID": LANG}, res)
            types = ";".join(str(t["ID"]) for t in meta.get("FoerderArten", []))
            rows = self._post("STIMAEntrySearchForTextParameters", {"TemplateID": TEMPLATE, "LanguageID": LANG,
                              "SearchParameters": f"foerderart:{types},eingabetyp:4"}, res)
        except (FetchError, ValueError) as e:
            res.failures.append({"url": API, "error": getattr(e, "reason", str(e))})
            return res
        self.countries = {c["T"].lower(): c["ISO"] for c in meta.get("Laender", []) if c.get("ISO")}
        programmes: dict[int, dict] = {}
        for r in rows if isinstance(rows, list) else []:   # one row per programme and grant type
            p = programmes.setdefault(r["StipFoeID"], {"id": r["StipFoeID"], "hzg": r.get("HZGID", 0),
                                                      "name": (r.get("StipName") or "").strip(), "types": []})
            p["types"].append((r.get("FoerderArtID"), (r.get("FoerderArtText") or "").strip()))
        ts = now()
        for p in list(programmes.values())[:limit]:
            res.records.append(self.normalize(p, ts))
        if self.details:
            for opp in res.records[:self.detail_limit]:
                self.enrich_from_detail(opp, res)
        return res

    def normalize(self, p: dict, ts: str) -> Opportunity:
        title = p["name"] or f"grants.at programme {p['id']}"
        kind = next((TYPE_KIND[t] for t, _ in p["types"] if t in TYPE_KIND), "scholarship_programme")
        opp = Opportunity(id=stable_id("grants_at", str(p["id"]), prefix="sch"), title=title[:200],
                          provider_name="OeAD (grants.at)", provider_type=ProviderType.PUBLIC_AGENCY, info_url=SITE,
                          opportunity_type=kind, discovered_via="adapter:grants_at", created_at=ts)
        opp.evidence.append(Evidence(field="title", value=title, source_url=SITE, source_type=SourceType.OFFICIAL,
                                     snippet=clean_snippet(f"grants.at: {title}"), retrieved_at=ts, verified_at=ts,
                                     confidence=0.95, status=VerificationStatus.CONFIRMED, note="structured official dataset",
                                     method="structured", authority="4_official_catalogue_feed"))
        opp.provider_metadata = {"grants_at_id": p["id"], "hzg_id": p["hzg"], "grant_types": [t for _, t in p["types"]]}
        opp.verification_status = VerificationStatus.EXTRACTED
        return opp

    def enrich_from_detail(self, opp: Opportunity, res: AdapterResult) -> None:
        try:
            d = self._post("GetDetailHtml", {"StipFoeID": str(opp.provider_metadata["grants_at_id"]),
                                             "HZGID": str(opp.provider_metadata["hzg_id"]), "LangID": LANG,
                                             "TemplateID": TEMPLATE, "LabelCol": "3"}, res)
        except (FetchError, ValueError) as e:
            res.failures.append({"url": API + "GetDetailHtml", "error": getattr(e, "reason", str(e))})
            return
        try:
            self.apply_detail(opp, (d or {}).get("html", ""))
        except ValueError as e:   # one malformed entry must not end a run of a thousand
            res.failures.append({"url": API + "GetDetailHtml", "error": f"{opp.provider_metadata['grants_at_id']}: {e}"})

    def _codes(self, lines: list[str]) -> tuple[Optional[list[str]], list[str]]:
        """(ISO codes, or None for "All"; names not matched)."""
        names = [n.strip() for x in lines for n in x.split(",") if n.strip()]
        if any(n.lower() in ("all", "all countries") for n in names):
            return None, []
        codes = [self.countries[n.lower()] for n in names if n.lower() in self.countries]
        return sorted(set(codes)), [n for n in names if n.lower() not in self.countries]

    def apply_detail(self, opp: Opportunity, page_html: str) -> None:
        rows = detail_rows(page_html)
        ts, src = now(), SITE

        def add(field, value, snippet):
            opp.evidence.append(Evidence(field=field, value=value, source_url=src, source_type=SourceType.OFFICIAL,
                                         snippet=clean_snippet(snippet), retrieved_at=ts, verified_at=ts, confidence=0.9,
                                         status=VerificationStatus.CONFIRMED, note="structured official dataset",
                                         method="structured", authority="4_official_catalogue_feed"))
        origin = _text(rows.get("Country of origin", ""))
        if origin:
            codes, _ = self._codes(origin)
            opp.nationality = NationalityRule(mode="any") if codes is None else \
                NationalityRule(mode="include", countries=codes) if codes else opp.nationality
            if opp.nationality.mode != "unknown":
                add("nationality", opp.nationality.to_dict(), "Country of origin: " + ", ".join(origin)[:280])
        target = _text(rows.get("Target country", ""))
        if target:
            codes, _ = self._codes(target)
            if codes:
                opp.destination_countries = codes
                for c in codes:
                    add("destination", c, "Target country: " + ", ".join(target)[:280])
        groups = _text(rows.get("Target group", ""))
        opp.study_levels = sorted({lvl for g in groups for rx, lvl in LEVELS if re.search(rx, g, re.I)})
        if opp.study_levels:
            add("study_levels", opp.study_levels, "Target group: " + ", ".join(groups))
        opp.disciplines = [x for x in _text(rows.get("Area of study or research", ""))][:12]
        funder = _text(rows.get("Funding organisation", ""))
        if funder:
            opp.provider_name = funder[0][:120]
        link = re.search(r'<a href="(https?://[^"]+)"[^>]*>\s*Further information', rows.get("Advice on how to apply", ""))
        if link and _valid(htmllib.unescape(link.group(1))):   # some entries carry malformed links ("http://[...")
            opp.info_url = htmllib.unescape(link.group(1))
        opp.deadlines = closing_dates(" ".join(_text(rows.get("Closing date for applications", ""))), self.today, src)
        for d in opp.deadlines:
            add(f"deadline.{d.kind}", d.date or d.approximate, d.label)
        # amount and advice through the usual readers, under the database's own headings
        value = "".join(f"<p>Scholarship value: {htmllib.escape(x)}</p>" for x in _text(rows.get("Grant benefit paid", "")))
        body = (f"<h3>Grant benefit paid</h3>{value}" if value else "") + "".join(
            f"<h3>{h}</h3>{rows[h]}" for h in ("Quota", "Advice on how to apply") if h in rows)
        if body:
            det, _ = extract_opportunity(Page(src, f"<html><head><title>{htmllib.escape(opp.title)}</title></head>"
                                                   f"<body>{body}</body></html>"), provider_name=opp.provider_name,
                                         provider_type=opp.provider_type, source_type=SourceType.OFFICIAL, country_hint=[],
                                         retrieved_at=ts, today=self.today)
            opp.funding, opp.required_documents = det.funding, det.required_documents
            opp.language_requirements, opp.selection_criteria = det.language_requirements, det.selection_criteria
            for k in ("min_gpa", "max_age", "min_age", "min_work_years"):
                setattr(opp, k, getattr(det, k))
            opp.evidence += [e for e in det.evidence if e.field.startswith(("funding.", "document.", "language.", "max_age",
                                                                            "min_age", "min_gpa", "selection"))]
        update = _text(rows.get("Last update", ""))
        if update:
            opp.provider_metadata["last_update"] = update[0][:60]
