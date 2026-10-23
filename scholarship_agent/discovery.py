"""Discovery and ingestion pipeline.

source selection -> query generation -> discovery (registry pages, one hop of
links, optional web search) -> URL normalization -> polite retrieval ->
extraction -> duplicate detection / merge -> cycle identification ->
persistence -> per-URL ingestion records and source health.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

from .extract import (RULES_VERSION, SCHOLARSHIP_TERMS, SECTION_TITLE, candidate_links, classify_page, section_links, extract_opportunity, looks_like_opportunity, page_from_response,
                      page_kind)
from .evidence import AGGREGATOR_DOMAINS, classify_authority, host as _host, is_aggregator
from .models import Opportunity, ProviderType, SourceAuthority, SourceType, VerificationStatus, stable_id
from .net import Fetcher, FetchError
from .normalize import dedup_key, normalize_url, similar
from .registry import Source, load_sources
from .search import SearchProvider, generate_queries
from .store import Store, now

OFFICIAL_TLD = re.compile(r"(\.gov|\.gov\.[a-z]{2}|\.govt\.[a-z]{2}|\.go\.[a-z]{2}|\.gob\.[a-z]{2}|\.gouv\.[a-z]{2}|"
                          r"\.edu|\.edu\.[a-z]{2}|\.ac\.[a-z]{2}|\.europa\.eu|\.int|\.admin\.ch)$")


def host_of(url: str) -> str:
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def domain_matches(url: str, domains: list[str]) -> bool:
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in domains if d)


def is_official_url(url: str, domains: list[str] | None = None) -> bool:
    return domain_matches(url, domains or []) or bool(OFFICIAL_TLD.search(host_of(url)))


@dataclass
class DiscoveryResult:
    job_id: int
    pages_fetched: int = 0
    opportunities_new: list[str] = field(default_factory=list)
    opportunities_updated: list[str] = field(default_factory=list)
    duplicates_merged: int = 0
    skipped_not_opportunity: int = 0
    skipped_by_kind: dict = field(default_factory=dict)
    failures: list[dict] = field(default_factory=list)
    injection_flags: list[dict] = field(default_factory=list)
    search_provider: Optional[str] = None
    queries: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    sitemap_urls: int = 0
    section_pages: int = 0
    ai_model: Optional[str] = None
    ai_fields_accepted: int = 0
    ai_fields_rejected: int = 0
    ai_disagreements: int = 0
    ai_errors: list[dict] = field(default_factory=list)
    aggregator_pages: int = 0
    aggregator_listings_skipped: int = 0
    official_links_followed: int = 0
    catalogue_links_followed: int = 0     # programme pages read from official catalogues met in search
    kept_separate: int = 0          # same programme name but different cycle / eligibility / institution
    retrieval: dict = field(default_factory=dict)   # retrieval method (http | browser | browser-cache) -> pages
    browser_needed: dict = field(default_factory=dict)   # why a page needed a browser, or what the browser did
    ai_fields_review: int = 0
    ai_skipped: dict = field(default_factory=dict)    # why no Claude request was needed -> pages

    def to_dict(self):
        return self.__dict__.copy()


LOC_RX = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


YEAR_IN_PATH = re.compile(r"/(20\d\d)/")


def newest_first(urls: list[str], today: date) -> list[str]:
    """Calls filed under a year (/utlysninger/2026/...): this year and later first, past years dropped."""
    def year(u):
        m = YEAR_IN_PATH.search(urlsplit(u).path)
        return int(m.group(1)) if m else None
    keep = [u for u in urls if year(u) is None or year(u) >= today.year]
    return sorted(keep, key=lambda u: -(year(u) or 0))


def feed_links(text: str) -> list[str]:
    """Item links of an RSS or Atom feed."""
    out = re.findall(r"<item\b.*?<link>\s*([^<\s]+)\s*</link>", text or "", re.S | re.I)
    out += re.findall(r"<entry\b.*?<link[^>]*href=[\"']([^\"']+)", text or "", re.S | re.I)
    return list(dict.fromkeys(out))


def sitemap_links(fetcher: Fetcher, base_url: str, domains: list[str], limit: int = 40, max_maps: int = 4,
                  pattern: str = "", sitemap: str = "") -> list[str]:
    """Scholarship-looking URLs from the site's published sitemaps (robots.txt Sitemap: lines, else /sitemap.xml).
    Keyless discovery that uses only what the site itself publishes for crawlers. `pattern` (a source's
    url_pattern) replaces the scholarship-word test; `sitemap` names the sitemap explicitly."""
    parts = urlsplit(base_url)
    root = f"{parts.scheme}://{parts.netloc}"
    maps: list[str] = []
    try:
        fetcher.robots_ok(base_url)
        body = fetcher._robots.get(root) or ""
        maps = [l.split(":", 1)[1].strip() for l in body.splitlines() if l.lower().startswith("sitemap:")]
    except Exception:
        pass
    maps = [sitemap] if sitemap else (maps or [root + "/sitemap.xml"])
    want = re.compile(pattern, re.I) if pattern else None
    out: list[str] = []
    seen_maps = 0
    queue = [m for m in maps if not m.endswith(".gz")]
    while queue and seen_maps < max_maps and len(out) < limit:
        m = queue.pop(0)
        seen_maps += 1
        try:
            r = fetcher.get(m)
        except FetchError:
            continue
        locs = LOC_RX.findall(r.text or "")
        if "<sitemapindex" in (r.text or "")[:2000].lower():
            # prefer child sitemaps that look relevant, then the rest
            locs.sort(key=lambda u: not SCHOLARSHIP_TERMS.search(u))
            queue += [u for u in locs if not u.endswith(".gz")][:max_maps]
            continue
        for u in locs:
            path = urlsplit(u).path
            if domain_matches(u, domains) and (want.search(path) if want else SCHOLARSHIP_TERMS.search(path)) \
                    and u not in out:
                out.append(u)
                if len(out) >= limit and not want:
                    break   # with a pattern, collect all, then keep the newest calls
    return out


def select_sources(sources: list[Source], destinations: list[str], levels: list[str],
                   ids: list[str] | None = None) -> list[Source]:
    out = []
    for s in sources:
        if not s.enabled:
            continue
        if ids:
            if s.id in ids:
                out.append(s)
            continue
        if destinations and not (s.destination_codes() & set(destinations)):
            continue
        if levels and s.levels and not set(levels) & set(s.levels):
            continue
        out.append(s)
    return out


LISTING_HINT = re.compile(r"\b(?:top|best|list of|latest|\d+\+?)\s.{0,40}scholarships?\b|"
                          r"scholarships? (?:for|in) [A-Z]\w+\b|\bkalender\b|\bdirectory\b", re.I)


def distinct_reason(a: Opportunity, b: Opportunity) -> str:
    """Why two records with the same name are different opportunities ("" = they may be merged)."""
    if a.current_cycle and b.current_cycle and a.current_cycle != b.current_cycle:
        return f"cycle {a.current_cycle} vs {b.current_cycle}"
    na, nb = a.nationality, b.nationality
    if na.mode == nb.mode == "include" and na.countries and nb.countries and not set(na.countries) & set(nb.countries):
        return "different eligible nationalities"
    if a.study_levels and b.study_levels and not set(a.study_levels) & set(b.study_levels):
        return "different study levels"
    from .normalize import _fold
    if a.institution and b.institution and _fold(a.institution) != _fold(b.institution):
        return "different institutions"
    searched = a.discovered_via.startswith("search:") or b.discovered_via.startswith("search:")
    if not searched and a.destination_countries and b.destination_countries \
            and not set(a.destination_countries) & set(b.destination_countries):
        return "different host countries"
    return ""


def merge(old: Opportunity, new: Opportunity) -> Opportunity:
    """Keep what we had, add new evidence, and record (not resolve) disagreements."""
    known = {(e.field, e.source_url, repr(e.value)) for e in old.evidence}
    for e in new.evidence:
        if (e.field, e.source_url, repr(e.value)) not in known:
            old.evidence.append(e)
    simple = ("min_gpa", "max_age", "min_age", "min_work_years", "application_url", "moi_policy", "current_cycle",
              "funding_duration")
    for f in simple:
        a, b = getattr(old, f), getattr(new, f)
        if a in (None, "") and b not in (None, ""):
            setattr(old, f, b)
        elif a not in (None, "") and b not in (None, "") and a != b:
            msg = f"{f}: '{a}' vs '{b}' ({new.info_url})"
            if msg not in old.conflicts:
                old.conflicts.append(msg)
    have = {(d.kind, d.date, d.approximate) for d in old.deadlines}
    for d in new.deadlines:
        if (d.kind, d.date, d.approximate) not in have:
            same_kind_cycle = [x for x in old.deadlines if x.kind == d.kind and x.cycle == d.cycle and x.date and d.date
                               and x.certainty == d.certainty]
            if same_kind_cycle:
                old.conflicts.append(f"deadline.{d.kind} ({d.cycle}): {same_kind_cycle[0].date} vs {d.date} ({d.source_url})")
            old.deadlines.append(d)
    for listname in ("study_levels", "disciplines", "destination_countries", "programs"):
        cur = getattr(old, listname)
        for v in getattr(new, listname):
            if v not in cur:
                cur.append(v)
    have_f = {c.kind for c in old.funding}
    old.funding += [c for c in new.funding if c.kind not in have_f]
    have_l = {r.test for r in old.language_requirements}
    for r in new.language_requirements:
        old_r = next((x for x in old.language_requirements if x.test == r.test), None)
        if old_r and old_r.minimum != r.minimum:
            old.conflicts.append(f"language.{r.test}: {old_r.minimum} vs {r.minimum} ({new.info_url})")
        elif r.test not in have_l:
            old.language_requirements.append(r)
    have_d = {d.name for d in old.required_documents}
    old.required_documents += [d for d in new.required_documents if d.name not in have_d]
    if old.nationality.mode == "unknown" and new.nationality.mode != "unknown":
        old.nationality = new.nationality
    elif new.nationality.mode != "unknown" and (new.nationality.mode, sorted(new.nationality.countries)) != \
            (old.nationality.mode, sorted(old.nationality.countries)):
        old.conflicts.append(f"nationality: {old.nationality.mode}{old.nationality.countries} vs "
                             f"{new.nationality.mode}{new.nationality.countries} ({new.info_url})")
    if old.opportunity_type == "unknown" and new.opportunity_type != "unknown":
        old.opportunity_type = new.opportunity_type
    for k, v in new.provider_metadata.items():
        old.provider_metadata.setdefault(k, v)
    for t in new.tags:
        if t not in old.tags:
            old.tags.append(t)
    if old.conflicts:
        old.verification_status = VerificationStatus.CONFLICTING
    return old


class Discovery:
    def __init__(self, store: Store, fetcher: Optional[Fetcher] = None, search: Optional[SearchProvider] = None,
                 today: Optional[date] = None, sources: Optional[list[Source]] = None, llm=None, browser=None):
        self.store = store
        self.fetcher = fetcher or Fetcher()
        self.search = search
        self.today = today or date.today()
        self.sources = sources if sources is not None else load_sources()
        self.llm = llm
        self.section_depth = 1      # programme section pages are followed one level deep
        self.official_links_per_aggregator = 2   # aggregator pages are leads: follow their links to the provider
        self.links_per_catalogue = 4             # an official catalogue is a lead too: read the programmes it links
        self._seen_urls: set[str] = set()
        self.last_page_language = ""
        self.last_method = "http"
        self.browser = browser      # retrieval.Browser, used only when the HTTP page needs one
        # discovery asks Claude only for what the rules missed; SCHOLAR_AI_MODE=full restores whole-page requests
        self.ai_mode = os.environ.get("SCHOLAR_AI_MODE", "targeted")

    def ingest_url(self, job_id: int, url: str, *, provider: str, provider_type: str, source_type: SourceType,
                   countries_hint: list[str], result: DiscoveryResult, discovered_via: str,
                   require_opportunity: bool = True, official_domains: list[str] | None = None,
                   parent_title: str = "", force_parent: bool = False, response=None) -> Optional[Opportunity]:
        """Fetch (or take the prefetched `response`, a Response or FetchError) and extract one page. With
        require_opportunity=False (registry programme sources, user-supplied URLs) a page that is not a programme is
        still stored, with its page_type, and its programme identity is rejected: never verified, listed by the audit."""
        self._seen_urls.add(normalize_url(url))
        try:
            if isinstance(response, FetchError):
                raise response
            resp = response if response is not None else self.fetcher.get(url)
        except FetchError as e:
            result.failures.append({"url": url, "error": e.reason})
            self.store.record_ingestion(job_id, url, "failed", e.reason)
            return None
        result.pages_fetched += 1
        page = page_from_response(resp)
        from .retrieval import needs_browser, rendered
        need, why = needs_browser(resp, page)
        if need:
            if self.browser is None:
                result.browser_needed[why] = result.browser_needed.get(why, 0) + 1
            else:
                r2, how = rendered(self.store, self.browser, resp)
                result.browser_needed[how] = result.browser_needed.get(how, 0) + 1
                if r2 is not None:
                    resp, page = r2, page_from_response(r2)
        method = getattr(resp, "method", "http")
        result.retrieval[method] = result.retrieval.get(method, 0) + 1
        prev = self.store.cached_page(normalize_url(resp.url))
        unchanged = prev is not None and prev["sha256"] == resp.sha256
        self.store.cache_page(normalize_url(resp.url), resp.status, resp.sha256, resp.content_type, "",
                              final_url=resp.url, method=method)
        self.last_page_language, self.last_method = page.language, method
        if page.pdf_status and not page.text:
            result.failures.append({"url": url, "error": f"PDF unreadable: {page.pdf_status}"})
            self.store.record_ingestion(job_id, url, "failed", f"PDF unreadable: {page.pdf_status}")
            return None
        cls = classify_page(page)
        kind, why, uncertain = cls["kind"], cls["reason"], cls["confidence"] == "low"
        aggregator = is_aggregator(resp.url, page.title) and not is_official_url(resp.url, official_domains)
        if aggregator:
            result.aggregator_pages += 1
            self._follow_official_links(job_id, page, result, discovered_via, countries_hint)
            if kind == "listing" or LISTING_HINT.search(page.title or ""):
                result.aggregator_listings_skipped += 1
                self.store.record_ingestion(job_id, url, "skipped_aggregator_listing", "lists several programmes")
                return None
            source_type = SourceType.AGGREGATOR
        self.last_not_loaded = kind == "not_loaded"
        if kind == "not_loaded" and require_opportunity:
            # not assessed, not "not a programme": logged apart so a browser, a retry or a person can look again
            result.skipped_by_kind["not_loaded"] = result.skipped_by_kind.get("not_loaded", 0) + 1
            self.store.record_ingestion(job_id, url, "not_loaded", why)
            return None
        if require_opportunity and kind == "listing" and not aggregator:
            # a catalogue is not a programme, but the programmes it lists must not be lost: read a few of them
            self._follow_catalogue_links(job_id, page, result, discovered_via, countries_hint)
        if require_opportunity and kind != "opportunity" and not uncertain:   # uncertain pages go to review
            result.skipped_not_opportunity += 1
            result.skipped_by_kind[kind] = result.skipped_by_kind.get(kind, 0) + 1
            self.store.record_ingestion(job_id, url, f"skipped_{kind}", why)
            return None
        if source_type != SourceType.AGGREGATOR:
            source_type = SourceType.OFFICIAL if is_official_url(resp.url, official_domains) else SourceType.SEARCH_RESULT
        try:
            ptype = ProviderType(provider_type)
        except ValueError:
            ptype = ProviderType.OTHER
        opp, flags = extract_opportunity(page, provider_name=provider, provider_type=ptype, source_type=source_type,
                                         country_hint=countries_hint, retrieved_at=now(), today=self.today)
        opp.discovered_via = discovered_via
        authority = classify_authority(resp.url, official_domains=official_domains or None, page_kind=kind,
                                       source_type=source_type if official_domains else
                                       (SourceType.AGGREGATOR if aggregator else ""), title=page.title)
        opp.source_authority = str(authority)
        from .identity import page_type
        # a third-party page describing a programme is an aggregator page, whatever its domain list says
        third_party = aggregator or (kind == "opportunity" and authority == SourceAuthority.AGGREGATOR)
        # who published the page is known even when what it is is not
        opp.page_type = "aggregator" if third_party and kind != "not_loaded" else "unknown" if uncertain else page_type(kind)
        opp.discovered_authority = (str(SourceAuthority.AGGREGATOR) if ":via-aggregator" in discovered_via
                                    else str(authority))
        for e in opp.evidence:
            e.authority = str(authority)
            e.cycle = e.cycle or opp.current_cycle
        known = unchanged and self.store.find_by_dedup("", normalize_url(opp.info_url)) is not None
        if self.llm is not None and known:
            # same content as last time and already a record: nothing new for the model to read
            result.ai_skipped["page unchanged since last extraction"] = \
                result.ai_skipped.get("page unchanged since last extraction", 0) + 1
        elif self.llm is not None:
            from .ai_extract import enrich
            st = enrich(opp, page.text, self.llm, source_type=source_type, retrieved_at=now(), today=self.today,
                        mode=self.ai_mode)
            result.ai_model = st["model"]
            result.ai_fields_accepted += len(st["accepted"])
            result.ai_fields_rejected += len(st["rejected"])
            result.ai_fields_review += len(st.get("needs_review", []))
            if st.get("skipped"):
                result.ai_skipped[st["skipped"]] = result.ai_skipped.get(st["skipped"], 0) + 1
            result.ai_disagreements += len(st["disagreements"])
            if st.get("error"):
                result.ai_errors.append({"url": url, "error": st["error"]})
            for e in opp.evidence:
                e.authority = e.authority or str(authority)
            if os.environ.get("SCHOLAR_SECOND_READING") == "1":
                # round 43: an independent reading of the four decisions; disagreements are held for review
                from .ai_check import attach_second_reading
                attach_second_reading(opp, page.text, self.llm, self.today)
        for e in opp.evidence:   # where and how each claim was read
            e.final_url = e.final_url or resp.url
            e.programme = e.programme or opp.title
            e.method_version = e.method_version or (RULES_VERSION if e.method in ("rules", "structured") else "")
        from .identity import title_specificity
        # renamed only to a parent that names a programme: "OeAD scholarships (Austria)" is a collection, and the
        # Ernst Mach grant page keeps its own name
        if parent_title and (force_parent or title_specificity(parent_title, opp.provider_name)[0]) and (
                force_parent or not SCHOLARSHIP_TERMS.search(page.title or "") or SECTION_TITLE.search(page.title or "")):
            # "Who can apply?", "Application timeline": a section of the programme, not a separate award
            opp.tags.append(f"section:{page.title[:80]}")
            opp.title = parent_title
            opp.id = stable_id(dedup_key(parent_title, opp.provider_name), prefix="sch")
        from .identity import identity
        # the same check verification makes, on the page as fetched now, with the record's final name
        opp.programme_identity = identity(opp, page_title=page.html_title or page.title, h1=page.h1, text=page.text,
                                          page_kind=kind, kind_confidence=cls["confidence"], kind_reason=why)
        if flags:
            result.injection_flags.append({"url": url, "flags": flags})
        opp, is_new = self.persist(job_id, opp, url, result)
        if is_new:
            self._follow_sections(job_id, page, opp, result, discovered_via, official_domains, countries_hint)
        return opp

    def persist(self, job_id: int, opp: Opportunity, url: str, result: "DiscoveryResult") -> tuple[Opportunity, bool]:
        """Save a record, merging it into an existing one when it is the same opportunity."""
        key, url_norm = dedup_key(opp.title, opp.provider_name), normalize_url(opp.info_url)
        existing = self.store.get_opportunity(opp.id) or self.store.find_by_dedup(key, url_norm)
        if existing and existing.id != opp.id and opp.discovered_via.startswith("adapter:") \
                and existing.discovered_via == opp.discovered_via:
            existing = None  # distinct ids from one structured source are distinct programmes
        if not existing:
            for o in self.store.list_opportunities():
                # two records from the same structured source with different ids are different programmes
                same_adapter = opp.discovered_via.startswith("adapter:") and o.discovered_via == opp.discovered_via
                if not same_adapter and similar(o.title, o.provider_name, opp.title, opp.provider_name):
                    existing = o
                    break
        if existing and not any(t.startswith("section:") for t in opp.tags):  # sections always join their programme
            reason = distinct_reason(existing, opp)
            if reason:
                # same name, genuinely different terms: keep both, each with its own evidence
                opp.id = stable_id(opp.id, reason, prefix="sch")
                opp.tags.append(f"kept separate from {existing.id}: {reason}")
                result.kept_separate += 1
                existing = None
        if existing:
            merged = merge(existing, opp)
            self.store.save_opportunity(merged, dedup_key(merged.title, merged.provider_name),
                                        normalize_url(merged.info_url))
            result.duplicates_merged += 1
            result.opportunities_updated.append(merged.id)
            self.store.record_ingestion(job_id, url, "merged", opp_id=merged.id)
            return merged, False
        self.store.save_opportunity(opp, key, url_norm)
        result.opportunities_new.append(opp.id)
        self.store.record_ingestion(job_id, url, "new", opp_id=opp.id)
        return opp, True

    def _follow_official_links(self, job_id, page, result, discovered_via, countries_hint) -> None:
        """An aggregator names the provider's page: read that instead of trusting the aggregator."""
        if self.official_links_per_aggregator <= 0 or ":via-aggregator" in discovered_via:
            return
        here = _host(page.url)
        picked = []
        for href, label in page.links:
            h = _host(href)
            if not h or h == here or any(h == d or h.endswith("." + d) for d in AGGREGATOR_DOMAINS):
                continue
            if normalize_url(href) in self._seen_urls or not href.startswith("http"):
                continue
            official_link = bool(re.search(r"official (?:web)?site|official page|apply (?:here|now|online)|"
                                           r"more (?:info|information|details)|situs resmi|sitio oficial|site officiel",
                                           label or "", re.I))
            if official_link or (is_official_url(href) and SCHOLARSHIP_TERMS.search(f"{label} {href}")):
                picked.append(href)
            if len(picked) >= self.official_links_per_aggregator:
                break
        for href in picked:
            self._seen_urls.add(normalize_url(href))
            result.official_links_followed += 1
            self.ingest_url(job_id, href, provider=_host(href), provider_type="other",
                            source_type=SourceType.SEARCH_RESULT, countries_hint=countries_hint, result=result,
                            discovered_via=f"{discovered_via}:via-aggregator")

    def _follow_catalogue_links(self, job_id, page, result, discovered_via, countries_hint) -> None:
        """Same-site links of an official catalogue whose text or address names funding, one level deep."""
        if self.links_per_catalogue <= 0 or ":via-catalogue" in discovered_via or ":via-aggregator" in discovered_via:
            return
        picked = [h for h, _ in candidate_links(page, same_site_only=True)
                  if normalize_url(h) not in self._seen_urls][:self.links_per_catalogue]
        for href in picked:
            self._seen_urls.add(normalize_url(href))
            result.catalogue_links_followed += 1
            self.ingest_url(job_id, href, provider=_host(href), provider_type="other",
                            source_type=SourceType.SEARCH_RESULT, countries_hint=countries_hint, result=result,
                            discovered_via=f"{discovered_via}:via-catalogue")

    def _follow_sections(self, job_id, page, opp, result, discovered_via, official_domains, countries_hint) -> None:
        """Read the programme's own eligibility/benefits/deadline pages into the same record."""
        if self.section_depth <= 0 or not is_official_url(page.url, official_domains):
            return
        for u in section_links(page):
            if normalize_url(u) in self._seen_urls:
                continue
            self._seen_urls.add(normalize_url(u))
            self.section_depth -= 1
            try:
                self.ingest_url(job_id, u, provider=opp.provider_name, provider_type=str(opp.provider_type),
                                source_type=SourceType.OFFICIAL, countries_hint=countries_hint, result=result,
                                discovered_via=discovered_via, require_opportunity=False,
                                official_domains=official_domains, parent_title=opp.title, force_parent=True)
                result.section_pages += 1
            finally:
                self.section_depth += 1

    def run(self, destinations: list[str] | None = None, levels: list[str] | None = None,
            disciplines: list[str] | None = None, nationality: Optional[str] = None,
            source_ids: list[str] | None = None, max_links_per_source: int = 15, max_search_results: int = 5,
            use_search: bool = True, use_sitemaps: bool = True, resume_job: Optional[int] = None) -> DiscoveryResult:
        """`resume_job` continues an interrupted run: the sources it finished are skipped, using its parameters."""
        destinations, levels = [c.upper() for c in destinations or []], levels or []
        params = {"destinations": destinations, "levels": levels, "disciplines": disciplines or [],
                  "nationality": nationality, "source_ids": source_ids or []}
        start = 0
        if resume_job:
            prev = self.store.job(resume_job)
            if not prev or prev["kind"] != "discover":
                raise ValueError(f"no discover job {resume_job} to resume")
            params = json.loads(prev["params"])
            destinations, levels, source_ids = params["destinations"], params["levels"], params["source_ids"] or None
            disciplines, nationality = params["disciplines"], params["nationality"]
            cp = self.store.get_checkpoint(resume_job)
            start, job = (cp["position"] if cp else 0), resume_job
        else:
            job = self.store.start_job("discover", params)
        res = DiscoveryResult(job_id=job)
        chosen = select_sources(self.sources, destinations, levels, source_ids)
        for pos, s in enumerate(chosen):
            if pos < start:
                continue
            if pos:
                self.store.checkpoint(job, pos, {"next_source": s.id})
            res.sources_used.append(s.id)
            st = SourceType.AGGREGATOR if s.source_type == "aggregator" else SourceType.OFFICIAL
            hint = [] if s.is_global() or any(c.startswith("*") for c in s.countries) else list(s.countries)
            if s.kind == "opportunity":
                opp = self.ingest_url(job, s.url, provider=s.provider or s.name, provider_type=s.provider_type,
                                      source_type=st, countries_hint=hint, result=res, discovered_via=f"source:{s.id}",
                                      require_opportunity=False, official_domains=s.official_domains)
                self.store.record_source(s.id, opp is not None, "ok" if opp else "failed",
                                         "" if opp else (res.failures[-1]["error"] if res.failures else ""))
                continue
            try:
                resp = self.fetcher.get(s.url)
            except FetchError as e:
                res.failures.append({"url": s.url, "error": e.reason, "source": s.id})
                self.store.record_source(s.id, False, "failed", e.reason)
                self.store.record_ingestion(job, s.url, "failed", e.reason)
                continue
            res.pages_fetched += 1
            self.store.record_source(s.id, True, "ok")
            page = page_from_response(resp)
            if s.kind == "feed":
                links = [(u, "") for u in feed_links(resp.text)]
            elif s.url_pattern:
                rx = re.compile(s.url_pattern, re.I)
                links = [(h, t) for h, t in page.links if rx.search(urlsplit(h).path)]
            else:
                links = candidate_links(page)
            if use_sitemaps and s.official_domains and s.kind != "feed":
                have = {normalize_url(h) for h, _ in links}
                sm = sitemap_links(self.fetcher, s.url, s.official_domains, pattern=s.url_pattern, sitemap=s.sitemap)
                res.sitemap_urls += len(sm)
                links += [(h, "") for h in sm if normalize_url(h) not in have]
            if s.url_pattern:
                order = newest_first([h for h, _ in links], self.today)
                text = dict(links)
                links = [(h, text.get(h, "")) for h in dict.fromkeys(order)]
            # official pages whose own path names a scholarship first; navigation chrome last
            if not s.url_pattern:
                links.sort(key=lambda hl: (not domain_matches(hl[0], s.official_domains),
                                           not SCHOLARSHIP_TERMS.search(urlsplit(hl[0]).path)))
            if looks_like_opportunity(page) and s.kind != "listing":
                links.insert(0, (resp.url, page.title))
            for href, _text in links[:max_links_per_source]:
                official = domain_matches(href, s.official_domains)
                provider = s.provider if official else host_of(href)
                self.ingest_url(job, href, provider=provider or s.name,
                                provider_type=s.provider_type if official else "other",
                                source_type=st, countries_hint=hint, result=res,
                                discovered_via=f"source:{s.id}", official_domains=s.official_domains,
                                # pages matched by a source's url_pattern are separate programmes, not its sections
                                parent_title=s.name if official and not s.url_pattern else "")
        if use_search and self.search is not None:
            ok, why = self.search.available()
            res.search_provider = self.search.name if ok else f"{self.search.name} unavailable: {why}"
            if ok:
                for q in generate_queries(destinations, levels, disciplines or [], nationality):
                    res.queries.append(q["query"])
                    try:
                        hits = self.search.search(q["query"], max_search_results, q["language"])
                    except Exception as e:  # provider outage must not kill the run
                        res.failures.append({"query": q["query"], "error": f"search failed: {type(e).__name__}"})
                        continue
                    for h in hits:
                        self.ingest_url(job, h.url, provider=host_of(h.url), provider_type="other",
                                        source_type=SourceType.SEARCH_RESULT,
                                        countries_hint=[q["country"]] if q["country"] else [], result=res,
                                        discovered_via=f"search:{self.search.name}")
        self.store.checkpoint(job, len(chosen), {"next_source": None})
        status = "ok" if not res.failures else ("partial" if res.pages_fetched else "failed")
        self.store.finish_job(job, status, {k: (len(v) if isinstance(v, list) else v)
                                            for k, v in res.to_dict().items() if k != "job_id"})
        return res

    def close(self) -> None:
        if self.browser is not None:
            self.browser.close()

    def scrape(self, urls: list[str], provider: str = "", countries_hint: list[str] | None = None) -> DiscoveryResult:
        """Ingest specific permitted URLs (the /scholar-scrape command)."""
        job = self.store.start_job("scrape", {"urls": urls})
        res = DiscoveryResult(job_id=job)
        for u in urls:
            self.ingest_url(job, u, provider=provider or host_of(u), provider_type="other",
                            source_type=SourceType.SEARCH_RESULT, countries_hint=countries_hint or [], result=res,
                            discovered_via="scrape", require_opportunity=False)
        self.store.finish_job(job, "ok" if not res.failures else "partial", {"fetched": res.pages_fetched})
        return res


def stale(opp: Opportunity, max_age_days: int, today: Optional[date] = None) -> bool:
    if not opp.last_verified_at:
        return True
    t = today or date.today()
    v = datetime.fromisoformat(opp.last_verified_at).astimezone(timezone.utc).date()
    return (t - v).days > max_age_days
