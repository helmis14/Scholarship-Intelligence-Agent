"""National Scholarship Portal of India, scholarships.gov.in (round 51).

Access method (inspected 2026-10-28): the portal's public scheme pages are server-rendered HTML, one accordion per
ministry or state with every scheme's title, its dates and a link to its guidelines (PDF):

  GET  https://scholarships.gov.in/All-Scholarships                Central Sector schemes
  POST https://scholarships.gov.in/centralsOrsponsoredOrstate      the page's own filter form,
       central_sponsored_state=sponserscheme | statescheme          Centrally Sponsored and State schemes

robots.txt answers HTTP 404 (no restriction). No log-in or token is used. Guidelines PDFs are read only when
`details=True`, one request per scheme, rate-limited.

Lifecycle: a record is a scheme for the current academic year as the portal lists it. "Student Application Open till"
is the applicant deadline; the verification dates after it are for institutions and officers, not applicants. The
schemes fund study in India for Indian students; the portal does not repeat that on each scheme, so the study country
is marked as inferred and the nationality rule comes only from a scheme's own guidelines.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import date
from urllib.parse import quote
from typing import Optional

from ..extract import clean_snippet, extract_levels, extract_opportunity, page_from_response
from ..models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, Opportunity, ProviderType, SourceType,
                      VerificationStatus, stable_id)
from ..net import Fetcher, FetchError
from ..store import now
from .base import AdapterResult

BASE = "https://scholarships.gov.in/"
LISTS = [("All-Scholarships", None, "Central Sector"),
         ("centralsOrsponsoredOrstate", {"central_sponsored_state": "sponserscheme"}, "Centrally Sponsored"),
         ("centralsOrsponsoredOrstate", {"central_sponsored_state": "statescheme"}, "State")]
GROUP_RX = re.compile(r'<button class="accordion-button[^"]*"[^>]*>\s*(.*?)\s*</button>', re.S)
SCHEME_RX = re.compile(r'<div class="col-md-10">(.*?)(?=<div class="row mb-4 border-1 border-bottom">|<div class="accordion-item">|$)',
                       re.S)
DATE_RX = re.compile(r">\s*([^<>]*?(?:Open from|Open till)\s*:\s*(\d{2})-(\d{2})-(\d{4}))\s*<", re.S)


def _clean(h: str) -> str:
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", h or "")).split())


def parse_schemes(page_html: str) -> list[dict]:
    """[{group, title, dates: [(label, iso)], links: {name: url}}] from one scheme page."""
    page_html = re.sub(r"<!--.*?-->", "", page_html or "", flags=re.S)   # "<h6>by Ministry ...</h6>" is commented out
    out = []
    parts = re.split(r'(<button class="accordion-button[^"]*"[^>]*>.*?</button>)', page_html, flags=re.S)
    group = ""
    for part in parts:
        g = GROUP_RX.match(part)
        if g:
            group = _clean(g.group(1))
            continue
        for block in SCHEME_RX.findall(part):
            title = re.search(r"<h6[^>]*>(.*?)</h6>", block, re.S)
            if not title or not _clean(title.group(1)):
                continue
            dates = []
            for m in DATE_RX.finditer(block):
                try:
                    dates.append((_clean(m.group(1)), date(int(m.group(4)), int(m.group(3)), int(m.group(2))).isoformat()))
                except ValueError:
                    continue
            links = {_clean(t): quote(htmllib.unescape(u).strip(), safe=":/?&=%#+~@,;")   # file names with spaces
                     for u, t in re.findall(r'<a href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.S)}
            out.append({"group": group, "title": _clean(title.group(1)), "dates": dates, "links": links})
    return out


class NSPIndiaAdapter:
    name = "nsp_india"

    def __init__(self, fetcher: Fetcher, today: Optional[date] = None, details: bool = False,
                 detail_limit: Optional[int] = None):
        self.fetcher, self.today, self.details, self.detail_limit = fetcher, today or date.today(), details, detail_limit

    def run(self, limit: Optional[int] = None) -> AdapterResult:
        res = AdapterResult(self.name, access_method="the portal's public scheme pages and filter form")
        seen: set[str] = set()
        ts = now()
        for path, form, category in LISTS:
            url = BASE + path
            try:
                res.requests += 1
                text = (self.fetcher.post_form(url, form) if form else self.fetcher.get(url)).text
            except FetchError as e:
                res.failures.append({"url": url, "error": e.reason})
                continue
            for s in parse_schemes(text):
                key = (s["group"] + "|" + s["title"]).lower()
                if key in seen:
                    continue
                seen.add(key)
                res.records.append(self.normalize(s, category, url, ts))
        if limit:
            res.records = res.records[:limit]
        if self.details:
            for opp in res.records[:self.detail_limit]:
                self.enrich_from_guidelines(opp, res)
        return res

    def normalize(self, s: dict, category: str, src: str, ts: str) -> Opportunity:
        title = s["title"][:200]
        guide = next((u for n, u in s["links"].items() if re.search(r"specification|guideline", n, re.I)), "")
        opp = Opportunity(id=stable_id("nsp_india", s["group"], s["title"], prefix="sch"), title=title,
                          provider_name=s["group"] or "National Scholarship Portal (India)",
                          provider_type=ProviderType.GOVERNMENT, info_url=guide or src, destination_countries=["IN"],
                          study_levels=[lvl for lvl in extract_levels(title)], opportunity_type="scholarship_programme",
                          discovered_via="adapter:nsp_india", created_at=ts)
        opp.tags.append("destination:host")   # inferred from the portal, not stated on the scheme

        def add(field, value, snippet):
            opp.evidence.append(Evidence(field=field, value=value, source_url=src, source_type=SourceType.OFFICIAL,
                                         snippet=clean_snippet(snippet), retrieved_at=ts, verified_at=ts, confidence=0.95,
                                         status=VerificationStatus.CONFIRMED, note="structured official dataset",
                                         method="structured", authority="4_official_catalogue_feed"))
        add("title", title, f"National Scholarship Portal: {title}")
        for label, iso in s["dates"]:
            if re.search(r"scheme\s+open from", label, re.I):
                kind = DeadlineKind.OPENING
            elif re.search(r"student application", label, re.I):
                kind = DeadlineKind.SCHOLARSHIP
            else:
                continue   # defective-application, institute and officer verification: not the applicant's dates
            opp.deadlines.append(Deadline(kind=kind, date=iso, source_url=src, label=label,
                                          certainty=DeadlineCertainty.HISTORICAL if iso < self.today.isoformat()
                                          else DeadlineCertainty.CONFIRMED))
            add(f"deadline.{kind}", iso, label)
        opp.provider_metadata = {"category": category, "ministry_or_state": s["group"], "links": s["links"],
                                 "portal_dates": s["dates"]}
        opp.verification_status = VerificationStatus.EXTRACTED
        return opp

    def enrich_from_guidelines(self, opp: Opportunity, res: AdapterResult) -> None:
        if not opp.info_url.lower().endswith(".pdf"):
            return
        res.requests += 1
        try:
            page = page_from_response(self.fetcher.get(opp.info_url))
        except FetchError as e:
            res.failures.append({"url": opp.info_url, "error": e.reason})
            return
        if not page.text:
            return
        det, _ = extract_opportunity(page, provider_name=opp.provider_name, provider_type=opp.provider_type,
                                     source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at=now(), today=self.today)
        opp.funding, opp.required_documents = det.funding, det.required_documents
        opp.nationality = det.nationality
        opp.study_levels = sorted(set(opp.study_levels) | set(det.study_levels))
        for k in ("min_gpa", "max_age", "min_age"):
            setattr(opp, k, getattr(det, k))
        # the guidelines' own dates are often of a past year; the portal's dates stay the applicant's deadlines
        opp.evidence += [e for e in det.evidence if not e.field.startswith(("deadline", "title", "destination"))]
