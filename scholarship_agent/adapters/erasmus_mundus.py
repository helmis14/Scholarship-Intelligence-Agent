"""Erasmus Mundus catalogue (EACEA).

Access method (inspected 2026-10-17):
  * Official RSS feed of the catalogue: https://www.eacea.ec.europa.eu/node/253/rss_en - the 30 most
    recent entries, each with structured <category> fields (EACEA catalogue, Studies, ECTS Duration,
    Years for EMJMD, EMJMD Universities, intra-Africa universities, thematic areas). The feed does not page.
  * The catalogue listing pages https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en
    ?page=N (20 cards per page; title, programme website, project-overview link). EACEA's robots.txt does
    not restrict these paths. Pages are walked until one returns no cards.

Lifecycle: a catalogue entry is a *joint master programme* (an admission programme run by a university
consortium). Erasmus Mundus scholarships, their amounts, eligibility and deadlines are set and published
by each consortium on its own website, not in the catalogue - so records start with those fields unknown,
and `follow_programme_sites=True` reads the consortium site as the official source for them: its home page
and up to four of its own pages on scholarships and fees, admission and dates, and the consortium (round 49).
The study countries are the consortium's: the countries named beside its universities on those pages.
"Intra-Africa Scholarships Legacy" entries are past mobility projects and are stored as historical
funded projects, not as open opportunities.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Optional

from .. import countries
from ..extract import Page, clean_snippet, extract_opportunity, page_from_response
from ..models import Evidence, Opportunity, ProviderType, SourceType, VerificationStatus, stable_id
from ..net import Fetcher, FetchError
from ..normalize import normalize_url
from ..store import now
from .base import AdapterResult

RSS = "https://www.eacea.ec.europa.eu/node/253/rss_en"
CATALOGUE = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
CARD_RX = re.compile(r"<article\s+class=\"ecl-card\"[^>]*>(.*?)</article>", re.S)
# a consortium site's own pages worth reading, in order: what the scholarship pays, how and when to apply, who the
# partner universities are
SECTION_KINDS = [re.compile(r"scholarships?|funding|fees|tuition|costs", re.I),
                 re.compile(r"admissions?|apply|applications?|eligib|key dates|deadlines?|requirements", re.I),
                 re.compile(r"consortium|partners?|universities", re.I)]
NOT_SECTION = re.compile(r"news|events?|blog|alumni|login|call for partners|\.(?:pdf|docx?|jpe?g|png)(?:$|[?#])", re.I)
UNI_LINE = re.compile(r"universit|universidad|universidade|uniwersytet|univerzit|hochschule|[ée]cole|institut|polytechn|"
                      r"politecnic|college|academy|akadem|school of", re.I)
ASSOCIATED = re.compile(r"^(?:associated|associate) (?:partners?|members?|institutions?)\b", re.I | re.M)


def section_pages(page: Page, limit: int = 4) -> list[str]:
    """Up to `limit` links to the site's own pages on scholarships, admission and the consortium, in that order."""
    from urllib.parse import urlsplit
    host = (urlsplit(page.url).hostname or "").removeprefix("www.")
    home = normalize_url(page.url)
    found: list[list[str]] = [[] for _ in SECTION_KINDS]
    for href, label in page.links:
        if (urlsplit(href).hostname or "").removeprefix("www.") != host or NOT_SECTION.search(href + " " + label):
            continue
        u = normalize_url(href.split("#")[0])
        if u == home:
            continue
        for i, rx in enumerate(SECTION_KINDS):
            if rx.search(label) or rx.search(urlsplit(href).path):
                if u not in found[i]:
                    found[i].append(u)
                break
    firsts = [group[0] for group in found if group]   # the first link of each kind, then the others
    return (firsts + [u for group in found for u in group[1:]])[:limit]


def consortium_countries(text: str) -> list[tuple[str, str]]:
    """(country, line) for each country named beside a university on a consortium page; associated partners, which
    award no degree, are left out."""
    m = ASSOCIATED.search(text or "")
    out: list[tuple[str, str]] = []
    for line in (text[:m.start()] if m else text or "").splitlines():
        if len(line) > 220 or not UNI_LINE.search(line):
            continue
        for c in countries.mentions(line):
            if c not in {x for x, _ in out}:
                out.append((c, line))
    return out


def parse_rss(xml: str) -> list[dict]:
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml or "", re.S):
        def tag(t):
            m = re.search(rf"<{t}>(.*?)</{t}>", it, re.S)
            return htmllib.unescape(m.group(1).strip()) if m else ""
        cats: dict[str, list[str]] = {}
        for dom, val in re.findall(r'<category domain="([^"]*)">([^<]*)</category>', it):
            cats.setdefault(htmllib.unescape(dom), []).append(htmllib.unescape(val).strip())
        desc = re.sub(r"<[^>]+>", " ", tag("description"))
        out.append({"title": tag("title"), "link": tag("link"), "node": tag("atom:id"), "pub_date": tag("pubDate"),
                    "description": " ".join(desc.split()), "categories": cats})
    return out


def parse_cards(page_html: str) -> list[dict]:
    out = []
    for c in CARD_RX.findall(page_html or ""):
        a = re.search(r'ecl-content-block__title"\s*>\s*<a\s+href="([^"]+)".*?<span[^>]*ecl-link__label[^>]*>([^<]+)</span>',
                      c, re.S)
        if not a:
            continue
        desc = re.search(r'<div class="ecl-content-block__description">(.*?)</div>', c, re.S)
        dtext = " ".join(re.sub(r"<[^>]+>", " ", desc.group(1) if desc else "").split())
        proj = re.search(r'href="(https://erasmus-plus\.ec\.europa\.eu/projects/[^"]+)"', c)
        acr = re.match(r"([A-Za-z0-9+&\-]{2,20})\s*-\s*[Pp]roject overview", dtext)
        out.append({"title": htmllib.unescape(a.group(2).strip()), "link": htmllib.unescape(a.group(1)),
                    "acronym": acr.group(1) if acr else "", "project_url": proj.group(1) if proj else "",
                    "description": dtext})
    return out


class ErasmusMundusAdapter:
    name = "erasmus_mundus"

    def __init__(self, fetcher: Fetcher, today: Optional[date] = None, max_pages: int = 12,
                 follow_programme_sites: bool = False, site_limit: Optional[int] = None):
        self.fetcher, self.today, self.max_pages = fetcher, today or date.today(), max_pages
        self.follow, self.site_limit = follow_programme_sites, site_limit

    def run(self, limit: Optional[int] = None) -> AdapterResult:
        res = AdapterResult(self.name, access_method="official RSS feed + catalogue listing pages")
        rss_items: dict[str, dict] = {}
        try:
            res.requests += 1
            for it in parse_rss(self.fetcher.get(RSS).text):
                rss_items[normalize_url(it["link"])] = it
        except FetchError as e:
            res.failures.append({"url": RSS, "error": e.reason})
        cards: list[dict] = []
        for n in range(self.max_pages):
            url = CATALOGUE if n == 0 else f"{CATALOGUE}?page={n}"
            try:
                res.requests += 1
                found = parse_cards(self.fetcher.get(url).text)
            except FetchError as e:
                res.failures.append({"url": url, "error": e.reason})
                break
            if not found:
                break
            cards += found
            if limit and len(cards) >= limit:
                break
        else:
            res.notes.append(f"stopped after max_pages={self.max_pages}; catalogue may have more entries")
        ts = now()
        seen = set()
        for c in cards:
            key = normalize_url(c["link"])
            seen.add(key)
            res.records.append(self.normalize(c, rss_items.get(key), ts))
        for key, it in rss_items.items():  # feed entries not on the walked pages
            if key not in seen:
                res.records.append(self.normalize({"title": it["title"], "link": it["link"], "acronym": "",
                                                   "project_url": "", "description": it["description"]}, it, ts))
        if limit:
            res.records = res.records[:limit]
        if self.follow:
            for opp in [r for r in res.records if r.opportunity_type == "admission_programme"][:self.site_limit]:
                self.read_programme_site(opp, res)
        res.notes.append("Scholarship amounts, eligibility and deadlines are published by each consortium, not by "
                         "the catalogue; until the programme site is read they stay unknown.")
        return res

    def normalize(self, card: dict, rss: Optional[dict], ts: str) -> Opportunity:
        cats = (rss or {}).get("categories", {})
        catalogue = (cats.get("EACEA catalogue") or [""])[0]
        legacy = "legacy" in catalogue.lower() or "intra-africa" in catalogue.lower()
        acronym = card.get("acronym") or re.match(r"([A-Za-z0-9+&\-]{2,20})\s*-", (rss or {}).get("description", "") + " ")
        acronym = acronym if isinstance(acronym, str) else (acronym.group(1) if acronym else "")
        universities = cats.get("EMJMD Universities", []) + cats.get("intra-Africa universities", [])
        opp = Opportunity(
            id=stable_id("erasmus_mundus", normalize_url(card["link"]), prefix="sch"), title=card["title"][:200],
            provider_name=f"{acronym} consortium" if acronym else "Erasmus Mundus consortium",
            provider_type=ProviderType.UNIVERSITY, info_url=card["link"], study_levels=["master"],
            institution=", ".join(universities[:3]) + (" ..." if len(universities) > 3 else ""),
            disciplines=cats.get("Studies", []) + cats.get("Thematic global", []) + cats.get("Intra-Africa Thematic", []),
            opportunity_type="funded_project" if legacy else "admission_programme",
            discovered_via="adapter:erasmus_mundus", created_at=ts)
        if legacy:
            opp.tags.append("historical_mobility_project")
            opp.uncertainties.append("catalogued as a legacy Intra-Africa mobility project; not an open call")
        else:
            opp.tags.append("erasmus_mundus_joint_master")
            opp.uncertainties.append("scholarship terms, eligibility and deadlines are set by the consortium; read the "
                                     "programme website")
        src = RSS if rss else CATALOGUE
        opp.evidence = [Evidence(field="title", value=card["title"], source_url=src, source_type=SourceType.OFFICIAL,
                                 snippet=clean_snippet(f"EACEA catalogue: {card['title']}"), retrieved_at=ts,
                                 verified_at=ts, confidence=0.95, status=VerificationStatus.CONFIRMED,
                                 note="official catalogue entry", method="structured", authority="4_official_catalogue_feed")]
        years = cats.get("Years for EMJMD", [])
        pub = (rss or {}).get("pub_date", "")
        try:
            pub_iso = parsedate_to_datetime(pub).date().isoformat() if pub else ""
        except (TypeError, ValueError):
            pub_iso = ""
        opp.provider_metadata = {"acronym": acronym, "catalogue": catalogue, "universities": universities,
                                 "ects_duration": (cats.get("ECTS Duration") or [""])[0], "selection_years": years,
                                 "project_url": card.get("project_url", ""), "catalogue_published": pub_iso,
                                 "feed_node": (rss or {}).get("node", "")}
        if cats.get("ECTS Duration"):
            opp.funding_duration = cats["ECTS Duration"][0]
            opp.evidence.append(Evidence(field="programme_duration", value=opp.funding_duration, source_url=src,
                                         source_type=SourceType.OFFICIAL, snippet=f"ECTS Duration: {opp.funding_duration}",
                                         retrieved_at=ts, verified_at=ts, status=VerificationStatus.CONFIRMED,
                                         confidence=0.95, note="official catalogue entry", method="structured", authority="4_official_catalogue_feed"))
        opp.verification_status = VerificationStatus.EXTRACTED
        return opp

    def _page(self, url: str, res: AdapterResult) -> Optional[Page]:
        res.requests += 1
        try:
            return page_from_response(self.fetcher.get(url))
        except FetchError as e:
            res.failures.append({"url": url, "error": e.reason})
            return None

    def read_programme_site(self, opp: Opportunity, res: AdapterResult) -> None:
        home = self._page(opp.info_url, res)
        if home is None:
            return
        pages = [home] + [p for p in (self._page(u, res) for u in section_pages(home)) if p is not None]
        # scholarship and admission pages before the home page: they state the terms, the home page advertises
        pages = pages[1:] + pages[:1]
        ts = now()
        dests: list[str] = []
        for page in pages:
            site, _ = extract_opportunity(page, provider_name=opp.provider_name, provider_type=opp.provider_type,
                                          source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at=ts,
                                          today=self.today)
            for attr in ("funding", "selection_criteria"):   # one page's terms, never a mix of pages
                if getattr(site, attr) and not getattr(opp, attr):
                    setattr(opp, attr, getattr(site, attr))
            seen = {(d.kind, d.date, d.recurs, d.approximate) for d in opp.deadlines}
            opp.deadlines += [d for d in site.deadlines if (d.kind, d.date, d.recurs, d.approximate) not in seen]
            names = {r.test for r in opp.language_requirements}
            opp.language_requirements += [r for r in site.language_requirements if r.test not in names]
            names = {d.name for d in opp.required_documents}
            opp.required_documents += [d for d in site.required_documents if d.name not in names]
            if site.nationality.mode != "unknown" and opp.nationality.mode == "unknown":
                opp.nationality = site.nationality
            for k in ("min_gpa", "max_age", "min_age", "min_work_years"):
                if getattr(site, k) is not None and getattr(opp, k) is None:
                    setattr(opp, k, getattr(site, k))
            opp.application_url = opp.application_url or site.application_url
            if "destination:host" not in site.tags:   # the web address's country is not a consortium's
                dests += [c for c in site.destination_countries if c not in dests]
            opp.evidence += [e for e in site.evidence if e.field != "title" and not
                             (e.field == "destination" and "destination:host" in site.tags)]
            opp.conflicts += [c for c in site.conflicts if c not in opp.conflicts]
            if re.search(r"consortium|partner|universit", page.url + " " + page.title, re.I):
                named = consortium_countries(page.text)
                if len(named) >= 2:   # a joint master is run in at least three countries
                    for c, line in named:
                        if c not in dests:
                            dests.append(c)
                            opp.evidence.append(Evidence(field="destination", value=c, source_url=page.url,
                                                         source_type=SourceType.OFFICIAL, snippet=clean_snippet(line),
                                                         retrieved_at=ts, confidence=0.7,
                                                         status=VerificationStatus.EXTRACTED,
                                                         note="a consortium university's country"))
        opp.destination_countries = dests or opp.destination_countries
        if opp.deadlines or opp.funding:
            opp.uncertainties = [u for u in opp.uncertainties if "read the programme website" not in u]
