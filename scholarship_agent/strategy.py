"""Country-by-country search strategy, query log, incremental discovery and coverage.

The plan is generated from registries, not a hardcoded country list:
  * countries.COUNTRIES (every ISO country) and their UN regions,
  * search.COUNTRY_LANGS + search.TERMS (local-language vocabulary),
  * QUERY_CATEGORIES below (one per provider type the brief asks for),
  * optional data/discovery_strategy.json to narrow or extend it (countries, regions, categories,
    levels, disciplines, queries per country, pages per query, re-query interval).

Each executed query is logged (provider, text, country, category, language, page, time, result count,
error) with its results cached, so a re-run inside `requery_days` reuses the cache instead of spending
quota (incremental discovery). Discovered URLs are recorded once and tracked through
new -> fetched -> opportunity / skipped / failed. Coverage distinguishes countries configured from
countries actually searched, and URLs discovered from pages retrieved from records verified.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlsplit

from . import countries, languages
from .discovery import Discovery, DiscoveryResult, host_of, is_official_url
from .models import SourceType
from .net import FetchError
from .normalize import normalize_url
from .search import COUNTRY_LANGS, TERMS, SearchError, SearchProvider, filter_reason
from .search_health import EnginesUnavailable
from .store import Store, data_dir, now

# category -> (template, ...). {term} = local word for scholarship, {country} = English country name,
# {cc} = country-code TLD, {level} = study level word.
QUERY_CATEGORIES: dict[str, tuple[str, ...]] = {   # order = priority when the per-country budget is small
    "government": ("government scholarship {country} international students", "ministry of education scholarship {country}"),
    "university": ("{country} university scholarships for international students {level}",),
    "domestic": ("scholarship for {country} citizens", "scholarships for students from {country} study abroad"),
    "local_language": ("{term} site:.{cc}",),
    "research": ("funded PhD position {country}", "research institute fellowship {country}"),
    "foundation": ("foundation scholarship {country} students",),
    "company": ("company sponsored scholarship {country}", "industry fellowship {country} students"),
    "exchange": ("bilateral exchange scholarship {country}", "regional cooperation scholarship {country}"),
    "public_agency": ("{country} national scholarship agency funding students",),
    "international_org": ("international organization scholarship {country} nationals",),
}
CCTLD_FIX = {"GB": "uk"}
LEVEL_WORD = {"bachelor": "undergraduate", "master": "master's", "phd": "PhD", "postdoc": "postdoctoral"}


@dataclass
class StrategyConfig:
    countries: list[str] = field(default_factory=list)      # ISO codes; empty = all
    regions: list[str] = field(default_factory=list)        # Africa | Americas | Asia | Europe | Oceania
    categories: list[str] = field(default_factory=lambda: list(QUERY_CATEGORIES))
    levels: list[str] = field(default_factory=lambda: ["master", "phd"])
    disciplines: list[str] = field(default_factory=list)
    queries_per_country: int = 6
    pages_per_query: int = 1
    results_per_page: int = 10
    fetch_per_query: int = 3          # new result URLs fetched and extracted per query
    requery_days: int = 14
    max_countries: Optional[int] = None
    concepts: list[str] = field(default_factory=lambda: list(languages.concepts()))   # localised concept queries
    concurrency: int = 4              # pages fetched in parallel (different hosts; each host stays throttled)
    resume_pending: int = 20          # URLs left "new" by an interrupted run, fetched first
    @classmethod
    def load(cls, override: Optional[dict] = None) -> "StrategyConfig":
        cfg = {}
        path = data_dir() / "discovery_strategy.json"
        if path.is_file():
            cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in (override or {}).items() if v not in (None, [], "")})
        known = set(cls.__dataclass_fields__)
        bad = set(cfg) - known
        if bad:
            raise ValueError(f"unknown strategy keys: {sorted(bad)}")
        c = cls(**cfg)
        bad_cat = set(c.categories) - set(QUERY_CATEGORIES)
        if bad_cat:
            raise ValueError(f"unknown query categories: {sorted(bad_cat)}")
        bad_con = set(c.concepts) - set(languages.concepts())
        if bad_con:
            raise ValueError(f"unknown concepts: {sorted(bad_con)}")
        return c


def concept_queries(cc: str, concepts: list[str]) -> list[tuple[str, str, str]]:
    """(concept, language, query) in the country's own languages, then English: "stipend Norge",
    "Promotionsstipendium Deutschland", "beasiswa pemerintah daerah Indonesia". Local languages come first."""
    name = countries.name(cc)
    out = []
    for lang in [l for l in languages.country_languages(cc) if l != "en"] + ["en"]:
        place = languages.native_name(cc, lang) or name
        for con in concepts:
            for term in languages.concept_terms(lang, con)[:1]:
                q = term.format(country=name) if "{country}" in term else f"{term} {place}"
                out.append((con, lang, " ".join(q.split())))
    return out


def target_countries(cfg: StrategyConfig) -> list[str]:
    codes = [c.upper() for c in cfg.countries] if cfg.countries else sorted(countries.COUNTRIES)
    if cfg.regions:
        codes = [c for c in codes if countries.region(c) in cfg.regions]
    return codes[:cfg.max_countries] if cfg.max_countries else codes


def plan(cfg: StrategyConfig) -> list[dict]:
    """Queries per country, round-robin over categories so a small budget still spans provider types."""
    out = []
    for cc in target_countries(cfg):
        name = countries.name(cc)
        langs = [l for l in COUNTRY_LANGS.get(cc, []) if l != "en"]
        per: list[dict] = []
        pools = []
        for cat in cfg.categories:
            qs = []
            for tpl in QUERY_CATEGORIES[cat]:
                if cat == "local_language":
                    for lang in langs:
                        for term in TERMS.get(lang, [])[:1]:
                            qs.append((tpl.format(term=term, cc=CCTLD_FIX.get(cc, cc.lower()), country=name, level=""), lang))
                    continue
                for lvl in (cfg.levels or [""])[:1] if "{level}" in tpl else [""]:
                    qs.append((" ".join(tpl.format(country=name, level=LEVEL_WORD.get(lvl, lvl), term="", cc="").split()), "en"))
            if cfg.disciplines and cat == "university":
                qs.append((f"{cfg.disciplines[0]} scholarship {name}", "en"))
            pools.append((cat, qs))
        # localised concepts interleaved with the provider categories, so a small budget still searches in the
        # country's own language: government, concept, university, concept, ...
        local: dict[str, list] = {}
        for con, lang, text in concept_queries(cc, cfg.concepts):
            local.setdefault(f"concept:{con}", []).append((text, lang))
        mixed = []
        cpools = list(local.items())
        for i in range(max(len(pools), len(cpools))):
            if i < len(pools):
                mixed.append(pools[i])
            if i < len(cpools):
                mixed.append(cpools[i])
        pools = mixed
        seen: set[str] = set()
        i = 0
        while len(per) < cfg.queries_per_country and any(qs for _, qs in pools):
            cat, qs = pools[i % len(pools)]
            if qs:
                text, lang = qs.pop(0)
                if text.lower() not in seen:
                    seen.add(text.lower())
                    per.append({"country": cc, "category": cat, "language": lang, "query": text})
            i += 1
        out += per
    return out


@dataclass
class RunReport:
    provider: str
    provider_limits: str
    started_at: str
    config: dict
    countries_configured: int = 0
    countries_searched: list[str] = field(default_factory=list)
    countries_failed: list[str] = field(default_factory=list)
    categories_attempted: dict = field(default_factory=dict)
    queries_planned: int = 0
    queries_executed: int = 0
    queries_from_cache: int = 0
    query_errors: list[dict] = field(default_factory=list)
    urls_discovered: int = 0
    urls_new: int = 0
    urls_official_domain: int = 0
    urls_filtered: dict = field(default_factory=dict)       # reason -> count, dropped before fetching
    engines_returning: dict = field(default_factory=dict)   # SearXNG upstream engine -> hits
    engines_unresponsive: dict = field(default_factory=dict)  # engine -> reason of the last failure
    pages_attempted: int = 0
    pages_retrieved: int = 0
    pages_failed: int = 0
    pages_resumed: int = 0            # URLs an interrupted run had left unfetched
    locale_fallbacks: int = 0         # local-language queries retried in the default locale after an empty answer
    paused: dict = field(default_factory=dict)   # set when every search engine was cooling down
    engine_health: dict = field(default_factory=dict)
    languages_attempted: dict = field(default_factory=dict)   # query language -> queries
    retrieval: dict = field(default_factory=dict)              # http | browser -> pages
    network_requests: int = 0
    resumed_from: int = 0             # plan position a resumed job continued from
    candidates: dict = field(default_factory=dict)
    runtime_seconds: float = 0.0

    def to_dict(self):
        return self.__dict__.copy()


class StrategyRunner:
    def __init__(self, store: Store, discovery: Discovery, provider: SearchProvider, cfg: StrategyConfig,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 today: Optional[date] = None):
        self.store, self.discovery, self.provider, self.cfg = store, discovery, provider, cfg
        self.sleep, self.clock, self.today = sleep, clock, today or date.today()
        self._last = None

    def _throttle(self):
        gap = getattr(self.provider, "min_interval", 1.0)
        if self._last is not None and self.clock() - self._last < gap:
            self.sleep(gap - (self.clock() - self._last))
        self._last = self.clock()

    def _search(self, q: dict, page: int, job_id: int, rep: RunReport) -> list:
        prev = self.store.last_query_run(self.provider.name, q["query"], page)
        if prev:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(prev["run_at"])).days
            if age < self.cfg.requery_days:
                rep.queries_from_cache += 1
                from .search import SearchHit
                return [SearchHit(r["url"], r["title"], r["snippet"], self.provider.name)
                        for r in self.store.cached_results(prev["id"])]
        last_err = ""
        for attempt in range(3):
            self._throttle()
            try:
                hits = self.provider.search(q["query"], self.cfg.results_per_page, q["language"], page)
                if not hits and q["language"] != "en" and getattr(self.provider, "unresponsive", None):
                    # some upstream engines are suspended and the rest answer only in the default locale: same
                    # local-language text, default locale (the query language recorded stays the local one)
                    self._throttle()
                    hits = self.provider.search(q["query"], self.cfg.results_per_page, "en", page)
                    rep.locale_fallbacks += 1
                self.store.log_query(self.provider.name, q, page, hits, job_id=job_id)
                rep.queries_executed += 1
                for h in hits:
                    for e in h.engines:
                        rep.engines_returning[e] = rep.engines_returning.get(e, 0) + 1
                for e, why in getattr(self.provider, "unresponsive", []) or []:
                    rep.engines_unresponsive[e] = why
                return hits
            except SearchError as e:
                last_err = str(e)
                if "HTTP 4" in last_err and "429" not in last_err:
                    break  # auth/plan errors do not improve with retries
                self.sleep(2 ** (attempt + 1))
        self.store.log_query(self.provider.name, q, page, [], error=last_err, job_id=job_id)
        rep.query_errors.append({"query": q["query"], "country": q["country"], "error": last_err})
        return []

    def _prefetch(self, urls: list[str]) -> dict:
        """Fetch URLs in parallel (bounded); the Fetcher keeps each host serial and throttled."""
        def one(u):
            try:
                return u, self.discovery.fetcher.get(u)
            except FetchError as e:
                return u, e
        if self.cfg.concurrency <= 1 or len(urls) <= 1:
            return dict(one(u) for u in urls)
        with ThreadPoolExecutor(max_workers=self.cfg.concurrency) as pool:
            return dict(pool.map(one, urls))

    def _ingest(self, job: int, dres: DiscoveryResult, rep: RunReport, url: str, response, country: str,
                via: str) -> None:
        n = normalize_url(url)
        rep.pages_attempted += 1
        n_fail = len(dres.failures)
        opp = self.discovery.ingest_url(job, url, provider=host_of(url), provider_type="other",
                                        source_type=SourceType.SEARCH_RESULT, countries_hint=[country] if country else [],
                                        result=dres, discovered_via=via, response=response)
        if len(dres.failures) > n_fail:
            rep.pages_failed += 1
            self.store.mark_url(n, "failed", error=dres.failures[-1]["error"])
            return
        rep.pages_retrieved += 1
        method = self.discovery.last_method
        rep.retrieval[method] = rep.retrieval.get(method, 0) + 1
        status = "opportunity" if opp is not None else "not_loaded" if getattr(self.discovery, "last_not_loaded", False) \
            else "skipped"   # not_loaded: the page could not be read, so it was not judged
        self.store.mark_url(n, status, opp.id if opp is not None else "")
        self.store.note_retrieval(n, self.discovery.last_page_language, method)
        if opp is not None:
            from .providers import note_candidate
            note_candidate(self.store, url, country, opp, self.discovery.sources)

    def run(self, resume_job: Optional[int] = None) -> dict:
        """Run the plan. `resume_job` continues an interrupted job from its last checkpoint; URLs any earlier run
        discovered but never fetched are fetched first."""
        t0 = self.clock()
        cfg = self.cfg
        ok, why = self.provider.available()
        rep = RunReport(provider=self.provider.name if ok else f"{self.provider.name} (unavailable: {why})",
                        provider_limits=getattr(self.provider, "limits", ""), started_at=now(), config=cfg.__dict__.copy())
        queries = plan(cfg)
        rep.queries_planned = len(queries)
        rep.countries_configured = len({q["country"] for q in queries})
        if not ok:
            return rep.to_dict() | {"error": why}
        start = 0
        if resume_job:
            cp = self.store.get_checkpoint(resume_job)
            start = cp["position"] if cp else 0
            job = resume_job
            rep.resumed_from = start
        else:
            job = self.store.start_job("strategy", {"provider": self.provider.name, **cfg.__dict__})
        requests_before = getattr(self.discovery.fetcher, "requests", 0)
        dres = DiscoveryResult(job_id=job)
        pending = self.store.pending_urls(cfg.resume_pending) if cfg.resume_pending else []
        if pending:
            got = self._prefetch([r["url"] for r in pending])
            for r in pending:
                rep.pages_resumed += 1
                self._ingest(job, dres, rep, r["url"], got[r["url"]], r["country"] or "",
                             r["via"] or f"search:{self.provider.name}:resumed")
        searched: dict[str, bool] = {}
        for pos, q in enumerate(queries):
            if pos < start:
                continue
            rep.categories_attempted[q["category"]] = rep.categories_attempted.get(q["category"], 0) + 1
            rep.languages_attempted[q["language"]] = rep.languages_attempted.get(q["language"], 0) + 1
            any_ok = False
            to_fetch: list[str] = []
            for page in range(cfg.pages_per_query):
                before_err = len(rep.query_errors)
                try:
                    hits = self._search(q, page, job, rep)
                except EnginesUnavailable as e:
                    # nothing can answer now: stop here; `--resume JOB` continues from this query later
                    rep.paused = {"reason": str(e), "at_query": pos, "engines": e.states}
                    break
                any_ok = any_ok or len(rep.query_errors) == before_err
                for h in hits:
                    u = h.url.split("#")[0]
                    if not u.startswith("http"):
                        continue
                    rep.urls_discovered += 1
                    n = normalize_url(u)
                    if is_official_url(u):
                        rep.urls_official_domain += 1
                    if not self.store.see_url(n, u, q["country"], q["category"], f"search:{self.provider.name}",
                                              lang=q["language"], method="search"):
                        continue
                    rep.urls_new += 1
                    why = filter_reason(h)
                    if why:
                        rep.urls_filtered[why] = rep.urls_filtered.get(why, 0) + 1
                        self.store.mark_url(n, "skipped", error=f"filtered: {why}")
                        continue
                    if len(to_fetch) < cfg.fetch_per_query:
                        to_fetch.append(u)
                    else:
                        self.store.mark_url(n, "deferred")   # over this query's fetch budget; not an interrupted fetch
                if len(hits) < cfg.results_per_page:
                    break
            if rep.paused:
                break
            got = self._prefetch(to_fetch)
            for u in to_fetch:
                self._ingest(job, dres, rep, u, got[u], q["country"], f"search:{self.provider.name}:{q['category']}")
            searched[q["country"]] = searched.get(q["country"], False) or any_ok
            self.store.checkpoint(job, pos + 1, {"country": q["country"], "query": q["query"]})
        rep.countries_searched = sorted(c for c, v in searched.items() if v)
        rep.countries_failed = sorted(c for c, v in searched.items() if not v)
        rep.candidates = {"new": len(dres.opportunities_new), "merged_duplicates": dres.duplicates_merged,
                          "skipped_not_opportunity": dres.skipped_not_opportunity,
                          "skipped_by_kind": dres.skipped_by_kind, "extraction_failures": len(dres.failures),
                          "aggregator_pages": dres.aggregator_pages,
                          "aggregator_listings_skipped": dres.aggregator_listings_skipped,
                          "official_links_followed_from_aggregators": dres.official_links_followed,
                          "kept_separate_same_name": dres.kept_separate,
                          "ai_fields_accepted": dres.ai_fields_accepted, "ai_fields_review": dres.ai_fields_review,
                          "ai_fields_rejected": dres.ai_fields_rejected, "ai_skipped": dres.ai_skipped,
                          "browser": dres.browser_needed}
        rep.network_requests = getattr(self.discovery.fetcher, "requests", 0) - requests_before
        if getattr(self.provider, "pool", None) is not None:
            rep.engine_health = self.provider.pool.snapshot()
        rep.runtime_seconds = round(self.clock() - t0, 1)
        self.store.finish_job(job, "paused" if rep.paused else "ok" if not rep.query_errors else "partial", {k: v for k, v in rep.to_dict().items()
                                                                              if k not in ("config",)})
        return rep.to_dict() | {"job_id": job}


def coverage_report(store: Store) -> dict:
    """Countries configured vs searched, by category; URLs by status; records by origin of discovery."""
    rows = store.catalog.execute(
        "SELECT country, category, COUNT(*) n, SUM(error IS NULL) ok, SUM(n_results) results FROM search_queries "
        "GROUP BY country, category").fetchall()
    by_country: dict[str, dict] = {}
    for r in rows:
        d = by_country.setdefault(r["country"] or "?", {"queries": 0, "ok": 0, "results": 0, "categories": {}})
        d["queries"] += r["n"]
        d["ok"] += r["ok"] or 0
        d["results"] += r["results"] or 0
        d["categories"][r["category"]] = r["n"]
    url_status = {r["status"]: r["n"] for r in store.catalog.execute(
        "SELECT status, COUNT(*) n FROM discovered_urls GROUP BY status")}
    url_by_country = {r["country"]: r["n"] for r in store.catalog.execute(
        "SELECT country, COUNT(*) n FROM discovered_urls GROUP BY country")}
    searched = sorted(c for c, d in by_country.items() if d["ok"])
    by_region: dict[str, dict] = {}
    for c in countries.COUNTRIES:
        reg = by_region.setdefault(countries.region(c), {"countries": 0, "searched": 0})
        reg["countries"] += 1
        reg["searched"] += c in searched
    return {"countries_total": len(countries.COUNTRIES), "countries_searched": len(searched),
            "countries_searched_list": searched, "by_region": by_region, "by_country": by_country,
            "urls_by_status": url_status, "urls_by_country": url_by_country,
            "note": "A country counts as searched when at least one query for it returned without error. "
                    "Searched is not covered: results depend on the provider's index."}


def check_provider(store: Store, provider: SearchProvider, query: str = "scholarship for international students") -> dict:
    """One real query to prove connectivity. Records provider, query, URLs, error and time - never the key."""
    ok, why = provider.available()
    ts = now()
    if not ok:
        store.log_provider_check(provider.name, query, False, [], why)
        return {"provider": provider.name, "query": query, "ok": False, "error": why, "at": ts}
    try:
        hits = provider.search(query, 10, "en", 0)
    except SearchError as e:
        store.log_provider_check(provider.name, query, False, [], str(e))
        return {"provider": provider.name, "query": query, "ok": False, "error": str(e), "at": ts}
    urls = [h.url for h in hits]
    store.log_provider_check(provider.name, query, bool(urls), urls, "" if urls else "no results")
    return {"provider": provider.name, "query": query, "ok": bool(urls), "results": len(urls), "urls": urls,
            "hosts": sorted({urlsplit(u).netloc for u in urls}), "at": ts, "limits": getattr(provider, "limits", "")}
