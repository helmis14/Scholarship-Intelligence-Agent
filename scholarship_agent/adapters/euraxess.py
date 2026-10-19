"""EURAXESS (European Commission research careers portal).

Access constraints (inspected 2026-10-17, https://euraxess.ec.europa.eu/robots.txt):
  * `Disallow: /jobs/*` - every individual job, funding and hosting offer page;
  * `Disallow: /*?` - every search or filter URL, so search result pages and RSS queries;
  * `Disallow: */api/*` - the API paths, including /api/xmlguidelines (which, from its listing in the
    sitemap, documents the XML interface organisations use to *publish* offers);
  * the published sitemaps list only basic pages, events and news - no offers.
The portal therefore offers no automated read access to offers that respects its policy, and this adapter
does not crawl them. What it does instead:
  1. `run()` reads the allowed EURAXESS Worldwide pages (country funding guides, "careers and funding"
     pages) from the basic-pages sitemap and returns the external funding-scheme links on them as
     discovery *leads* (never as opportunities).
  2. `import_saved()` parses an offer page the user opened and saved in their own browser, keeping the
     original offer URL as the source. Offers are research positions, fellowships (funding offers) or
     hosting offers - not scholarship programmes - and are typed accordingly.
If EURAXESS publishes a read API or open dataset in future, it belongs here.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional
from urllib.parse import urlsplit

from ..extract import Page, extract_opportunity, parse_dates
from ..models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, Opportunity, ProviderType, SourceType,
                      VerificationStatus, stable_id)
from ..net import Fetcher, FetchError
from ..store import now
from .base import AdapterResult

ROOT = "https://euraxess.ec.europa.eu"
SITEMAP = ROOT + "/sitemaps/euraxess-domain-basic-pages/sitemap.xml"
LEAD_PATH = re.compile(r"/worldwide/[^/]+/(?:careers-and-funding|funding[\w-]*|jobs-funding|[\w-]*fellowship[\w-]*)$")
OFFER_TYPE = {"job": "research_position", "job offer": "research_position", "funding": "fellowship",
              "funding offer": "fellowship", "hosting": "funded_project", "hosting offer": "funded_project"}
PROFILE_LEVEL = {"r1": "phd", "first stage researcher": "phd", "r2": "postdoc", "recognised researcher": "postdoc",
                 "r3": "postdoc", "established researcher": "postdoc", "r4": "postdoc", "leading researcher": "postdoc"}
LABELS = ("application deadline", "deadline", "organisation/company", "organisation", "department", "country",
          "city", "research field", "researcher profile", "offer type", "type of offer", "funding programme",
          "type of contract", "job status", "offer starting date", "reference number", "positions",
          "is the job funded through the eu research framework programme?", "eu research framework programme",
          "marie curie grant agreement number")


def label_values(html: str) -> dict[str, str]:
    """Label -> value from dt/dd, th/td and 'Label: value' lines."""
    out: dict[str, str] = {}
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    for a, b in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", text, re.S | re.I) + \
            re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", text, re.S | re.I):
        k = " ".join(re.sub(r"<[^>]+>", " ", a).split()).strip(" :").lower()
        v = " ".join(re.sub(r"<[^>]+>", " ", b).split())
        if k and v:
            out.setdefault(k, v)
    plain = Page("about:blank", html).text
    for line in plain.splitlines():
        m = re.match(r"\s*([A-Za-z/ ?]{4,70}?)\s*[:|]\s+(.+)$", line)
        if m and m.group(1).strip().lower() in LABELS:
            out.setdefault(m.group(1).strip().lower(), m.group(2).strip())
    return out


class EuraxessAdapter:
    name = "euraxess"

    def __init__(self, fetcher: Fetcher, today: Optional[date] = None, max_pages: int = 25):
        self.fetcher, self.today, self.max_pages = fetcher, today or date.today(), max_pages

    def run(self, limit: Optional[int] = None) -> AdapterResult:
        res = AdapterResult(self.name, access_method="allowed Worldwide pages only (offers are robots-disallowed)")
        res.notes.append("EURAXESS robots.txt disallows /jobs/*, query URLs and */api/*; offers are not crawled. "
                         "Use `euraxess-import` on offer pages saved from your browser.")
        try:
            res.requests += 1
            xml = self.fetcher.get(SITEMAP).text
        except FetchError as e:
            res.failures.append({"url": SITEMAP, "error": e.reason})
            return res
        pages = []
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
            u = loc if loc.startswith("http") else ROOT + loc
            if LEAD_PATH.search(urlsplit(u).path):
                pages.append(u)
        for u in pages[:self.max_pages]:
            try:
                res.requests += 1
                p = Page(u, self.fetcher.get(u).text)
            except FetchError as e:
                res.failures.append({"url": u, "error": e.reason})
                continue
            for href, text in p.links:
                host = urlsplit(href).netloc
                if host and "euraxess" not in host and "europa.eu" not in host and \
                        re.search(r"fellow|grant|fund|scholar|award|programme|program", text + " " + href, re.I):
                    res.leads.append({"url": href.split("#")[0], "text": text[:120], "found_on": u})
        uniq = {}
        for l in res.leads:
            uniq.setdefault(l["url"], l)
        res.leads = list(uniq.values())[:limit] if limit else list(uniq.values())
        return res

    def import_saved(self, html: str, offer_url: str) -> Opportunity:
        if not re.match(r"https://euraxess\.ec\.europa\.eu/jobs/(?:funding/)?\d+", offer_url or ""):
            raise ValueError("offer_url must be the EURAXESS offer address, e.g. https://euraxess.ec.europa.eu/jobs/123456")
        page = Page(offer_url, html)
        lv = label_values(html)
        opp, _ = extract_opportunity(page, provider_name=lv.get("organisation/company") or lv.get("organisation") or
                                     "EURAXESS-listed organisation", provider_type=ProviderType.RESEARCH_INSTITUTE,
                                     source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at=now(), today=self.today)
        ts = now()
        opp.id = stable_id("euraxess", offer_url, prefix="sch")
        opp.discovered_via = "adapter:euraxess:import"
        otype = (lv.get("offer type") or lv.get("type of offer") or "").lower()
        opp.opportunity_type = OFFER_TYPE.get(otype, "research_position" if "/jobs/" in offer_url else "unknown")
        prof = (lv.get("researcher profile") or "").lower()
        levels = sorted({v for k, v in PROFILE_LEVEL.items() if k in prof})
        if levels:
            opp.study_levels = levels
        from .. import countries
        if lv.get("country"):
            c = countries.code(lv["country"].split(",")[0].strip())
            if c:
                opp.destination_countries = [c]
        raw_dl = lv.get("application deadline") or lv.get("deadline") or ""
        if raw_dl:
            d = next((x for x, _ in parse_dates(raw_dl) if x), None)
            tm = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", raw_dl)
            tz = re.search(r"\(([A-Za-z]+/[A-Za-z_]+)\)|\b(UTC[+-]?\d*|CET|CEST|GMT)\b", raw_dl)
            if d:
                opp.deadlines = [x for x in opp.deadlines if x.date != d.isoformat()] + [Deadline(
                    kind=DeadlineKind.SCHOLARSHIP if opp.opportunity_type == "fellowship" else DeadlineKind.ADMISSION,
                    certainty=DeadlineCertainty.HISTORICAL if d < self.today else DeadlineCertainty.CONFIRMED,
                    date=d.isoformat(), time=f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None,
                    timezone=(tz.group(1) or tz.group(2)) if tz else None, label=f"Application Deadline: {raw_dl}",
                    source_url=offer_url)]
                opp.evidence.append(Evidence(field="deadline.application", value=d.isoformat(), source_url=offer_url,
                                             source_type=SourceType.OFFICIAL, snippet=f"Application Deadline: {raw_dl}",
                                             retrieved_at=ts, status=VerificationStatus.EXTRACTED, confidence=0.8,
                                             note="from a page saved by the user"))
        opp.provider_metadata = {"labels": lv, "saved_by_user": True}
        opp.uncertainties.append("imported from a saved page; re-check the live offer before relying on it")
        return opp
