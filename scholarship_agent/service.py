"""ScholarshipService: the integration boundary.

Every public method takes plain arguments and returns a JSON-serialisable dict
stamped with `schema_version`. The CLI is one caller; a future web backend is
another (wrap each method in an HTTP handler - see docs/scholarship-agent/API.md).
Multi-user: pass a distinct `profile_id` per user and a per-tenant data
directory or database. Nothing here prints, prompts, or sends anything.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from . import documents as docs_mod
from . import eligibility, funding, planning, profile as profile_mod, ranking, registry, review, tracker
from .discovery import Discovery
from .models import SCHEMA_VERSION, AppStatus, Opportunity, VerificationStatus
from .net import Fetcher
from .search import SearchProvider, default_provider
from .store import Store
from .verify import verify as verify_opp


class NotFound(LookupError):
    pass


def _out(**kw) -> dict:
    return {"schema_version": SCHEMA_VERSION, **kw}


class ScholarshipService:
    def __init__(self, store: Optional[Store] = None, fetcher: Optional[Fetcher] = None,
                 search: Optional[SearchProvider] = "default", today: Optional[date] = None,
                 sources: Optional[list[registry.Source]] = None, llm: Optional[docs_mod.LLMProvider] = None,
                 extractor_llm="default"):
        self.store = store or Store()
        self.fetcher = fetcher or Fetcher()
        self.search = default_provider() if search == "default" else search
        from .search import SearxngSearch
        if isinstance(self.search, SearxngSearch) and self.search.pool is None and search == "default":
            from .search_health import EnginePool, searxng_engines
            self.search.pool = EnginePool(searxng_engines(self.search.base), store=self.store)
        self._today = today
        self.sources = sources if sources is not None else registry.load_sources()
        self.llm = llm
        from .ai_extract import default_llm
        self.extractor_llm = default_llm(self.store) if extractor_llm == "default" else extractor_llm

    @property
    def today(self) -> date:
        return self._today or date.today()

    # ------------------------------------------------------------- lookups

    def _opp(self, ref: str) -> Opportunity:
        o = self.store.find_opportunity(ref)
        if not o:
            raise NotFound(f"no unique opportunity matches '{ref}' - use the id from /report or /rank")
        return o

    def _profile(self, profile_id: str):
        p = self.store.get_profile(profile_id)
        if not p:
            raise NotFound("no applicant profile yet - run /setup first")
        return p

    # ------------------------------------------------------------- profile

    def setup_profile(self, patch: dict, profile_id: str = "default") -> dict:
        p = profile_mod.upsert(self.store, patch, profile_id)
        return _out(profile=p.to_dict(), missing=profile_mod.missing_core(p))

    def get_profile(self, profile_id: str = "default") -> dict:
        p = self._profile(profile_id)
        return _out(profile=p.to_dict(), missing=profile_mod.missing_core(p))

    def export_private_data(self, profile_id: str = "default") -> dict:
        return _out(**profile_mod.export(self.store, profile_id))

    def delete_private_data(self, profile_id: str = "default") -> dict:
        return _out(deleted=profile_mod.delete(self.store, profile_id))

    # ------------------------------------------------------------- discovery

    def discover(self, destinations=None, levels=None, disciplines=None, nationality=None, source_ids=None,
                 use_search: bool = True, max_links_per_source: int = 15, use_sitemaps: bool = True,
                 resume_job: Optional[int] = None) -> dict:
        d = Discovery(self.store, self.fetcher, self.search, self.today, self.sources, self.extractor_llm)
        r = d.run(destinations, levels, disciplines, nationality, source_ids, use_search=use_search,
                  max_links_per_source=max_links_per_source, use_sitemaps=use_sitemaps, resume_job=resume_job)
        return _out(**r.to_dict())

    def run_adapter(self, name: str, limit: Optional[int] = None, details: bool = False, persist: bool = True) -> dict:
        """Run a dedicated source adapter (daad, erasmus_mundus, euraxess, campusfrance) and store its records."""
        from .adapters import ADAPTERS
        from .discovery import DiscoveryResult
        if name not in ADAPTERS:
            raise ValueError(f"unknown adapter {name!r}; one of {sorted(ADAPTERS)}")
        cls = ADAPTERS[name]
        kw = {"daad": {"details": details}, "campusfrance": {"details": details},
              "erasmus_mundus": {"follow_programme_sites": details}}.get(name, {})
        adapter = cls(self.fetcher, today=self.today, **kw)
        job = self.store.start_job(f"adapter:{name}", {"limit": limit, "details": details})
        res = adapter.run(limit=limit)
        dres = DiscoveryResult(job_id=job)
        if persist:
            d = Discovery(self.store, self.fetcher, None, self.today, self.sources)
            for opp in res.records:
                d.persist(job, opp, opp.info_url, dres)
        for f in res.failures:
            self.store.record_ingestion(job, f.get("url", ""), "failed", f.get("error", ""))
        refreshed = len(dres.opportunities_updated) - dres.duplicates_merged   # its own records read again
        self.store.finish_job(job, "ok" if not res.failures else "partial",
                              res.summary() | {"new": len(dres.opportunities_new), "merged": dres.duplicates_merged,
                                               "refreshed": refreshed})
        types: dict[str, int] = {}
        for r in res.records:
            types[r.opportunity_type] = types.get(r.opportunity_type, 0) + 1
        return _out(**res.summary(), job_id=job, new=len(dres.opportunities_new), merged=dres.duplicates_merged,
                    refreshed=refreshed, by_type=types, leads_sample=res.leads[:20],
                    records_sample=[{"id": r.id, "title": r.title, "type": r.opportunity_type,
                                     "deadlines": len(r.deadlines), "nationality": r.nationality.mode}
                                    for r in res.records[:10]])

    def import_euraxess(self, html: str, offer_url: str) -> dict:
        from .adapters import EuraxessAdapter
        from .discovery import DiscoveryResult
        opp = EuraxessAdapter(self.fetcher, today=self.today).import_saved(html, offer_url)
        job = self.store.start_job("adapter:euraxess:import", {"url": offer_url})
        dres = DiscoveryResult(job_id=job)
        saved, is_new = Discovery(self.store, self.fetcher, None, self.today, self.sources).persist(job, opp, offer_url, dres)
        self.store.finish_job(job, "ok", {"new": int(is_new)})
        return _out(opportunity_id=saved.id, new=is_new, type=saved.opportunity_type, title=saved.title)

    def search_check(self, query: str = "scholarship for international students") -> dict:
        from .strategy import check_provider
        if self.search is None:
            return _out(ok=False, provider=None, error="no search provider configured: set BRAVE_SEARCH_API_KEY or "
                                                       "SEARXNG_URL (see docs/scholarship-agent/SEARCH.md)")
        return _out(**check_provider(self.store, self.search, query), history=self.store.provider_checks(5))

    def strategy_plan(self, **override) -> dict:
        from .strategy import StrategyConfig, plan, target_countries
        cfg = StrategyConfig.load(override)
        qs = plan(cfg)
        by_cat: dict[str, int] = {}
        for q in qs:
            by_cat[q["category"]] = by_cat.get(q["category"], 0) + 1
        return _out(config=cfg.__dict__, countries=len(target_countries(cfg)), queries=len(qs), by_category=by_cat,
                    sample=qs[:40])

    def strategy_run(self, resume_job: Optional[int] = None, **override) -> dict:
        from .strategy import StrategyConfig, StrategyRunner
        if self.search is None:
            raise ValueError("no search provider configured: set BRAVE_SEARCH_API_KEY or SEARXNG_URL")
        cfg = StrategyConfig.load(override)
        from .retrieval import default_browser
        browser, browser_note = default_browser()
        d = Discovery(self.store, self.fetcher, None, self.today, self.sources, self.extractor_llm, browser=browser)
        try:
            out = StrategyRunner(self.store, d, self.search, cfg, today=self.today).run(resume_job=resume_job)
        finally:
            d.close()
        return _out(**out, browser=browser_note)

    def coverage_quality(self) -> dict:
        from .coverage import report
        return _out(**report(self.store, self.today, self.sources))

    def provider_candidates(self, status: str = "candidate") -> dict:
        from .providers import candidates
        return _out(candidates=candidates(self.store, status))

    def provider_review(self, domain: str, accept: bool, provider: str = "", note: str = "") -> dict:
        from .providers import review
        out = review(self.store, domain, accept, provider, note)
        self.sources = registry.load_sources()
        return _out(**out)

    def coverage(self) -> dict:
        from .strategy import coverage_report
        return _out(search=coverage_report(self.store),
                    registry=registry.coverage(self.sources, self.store.source_states()))

    def scrape(self, urls: list[str], provider: str = "", countries=None) -> dict:
        d = Discovery(self.store, self.fetcher, self.search, self.today, self.sources, self.extractor_llm)
        return _out(**d.scrape(urls, provider, countries).to_dict())

    def verify(self, ref: str, official_url: Optional[str] = None) -> dict:
        return _out(**verify_opp(self.store, self._opp(ref), self.fetcher, self.sources, official_url=official_url,
                                 today=self.today))

    def refresh(self, max_age_days: Optional[int] = None, limit: int = 20, plan_only: bool = False) -> dict:
        """Re-verify due records in priority order (upcoming deadlines, conflicts, past-cycle-only, stale,
        incomplete). Schedule this; it only re-reads official pages and never invents a new cycle."""
        from . import freshness
        cfg = freshness.schedule({"stale_days": max_age_days} if max_age_days is not None else None)
        order = freshness.plan(self.store, self.today, cfg)
        due = [r for r in order if r["due"]]
        if plan_only:
            return _out(schedule=cfg, due=len(due), plan=order[:max(limit, 50)])
        done = []
        for r in due[:limit]:
            o = self.store.get_opportunity(r["opportunity_id"])
            if o:
                res = verify_opp(self.store, o, self.fetcher, self.sources, today=self.today)
                done.append(res | {"priority": r["priority"], "reasons": r["reasons"]})
        return _out(schedule=cfg, due=len(due), refreshed=len(done), results=done)

    def discovery_report(self, since_job: int = 0) -> dict:
        """What a set of runs found, retrieved and verified - record level and field level kept apart."""
        from . import freshness
        from .strategy import coverage_report
        c = self.store.catalog
        jobs = [dict(r) for r in c.execute("SELECT * FROM search_jobs WHERE id > ? ORDER BY id", (since_job,))]
        ids = [j["id"] for j in jobs] or [-1]
        marks = ",".join("?" * len(ids))
        outcomes = {r["outcome"]: r["n"] for r in c.execute(
            f"SELECT outcome, COUNT(*) n FROM ingestion_results WHERE job_id IN ({marks}) GROUP BY outcome", ids)}
        errors = [dict(r) for r in c.execute(
            f"SELECT url, error FROM ingestion_results WHERE job_id IN ({marks}) AND outcome='failed' LIMIT 50", ids)]
        opp_ids = {r["opportunity_id"] for r in c.execute(
            f"SELECT DISTINCT opportunity_id FROM ingestion_results WHERE job_id IN ({marks}) AND opportunity_id != ''", ids)}
        opps = [o for o in self.store.list_opportunities() if o.id in opp_ids]
        verified_src = [o for o in opps if o.last_verified_at]
        fv = [freshness.field_verification(o, self.today) for o in opps]
        runtime = 0.0
        for j in jobs:
            if j["finished_at"] and j["started_at"]:
                runtime += (datetime.fromisoformat(j["finished_at"]) - datetime.fromisoformat(j["started_at"])).total_seconds()
        sources = sorted({s for j in jobs for s in (json.loads(j["params"] or "{}").get("source_ids") or [])})
        adapters = sorted({j["kind"].split(":", 1)[1] for j in jobs if j["kind"].startswith("adapter:")})
        q = c.execute(f"SELECT COUNT(*) n, COUNT(DISTINCT country) countries, SUM(error IS NOT NULL) errors "
                      f"FROM search_queries WHERE job_id IN ({marks})", ids).fetchone()
        cats = {r["category"]: r["n"] for r in c.execute(
            f"SELECT category, COUNT(*) n FROM search_queries WHERE job_id IN ({marks}) GROUP BY category", ids)}
        stats = self.catalog_stats()
        n = len(opps)
        return _out(
            jobs=[{k: j[k] for k in ("id", "kind", "started_at", "finished_at", "status")} for j in jobs],
            configuration={"search_provider": self.search.name if self.search else "none configured",
                           "search_limits": getattr(self.search, "limits", "") if self.search else "",
                           "ai_extraction": self.extractor_llm.name if self.extractor_llm else "off",
                           "adapters_run": adapters},
            search={"queries": q["n"] or 0, "countries_attempted": q["countries"] or 0, "query_errors": q["errors"] or 0,
                    "categories": cats, "coverage": coverage_report(self.store)["countries_searched"]},
            sources_queried=sources,
            urls={"ingested": sum(outcomes.values()), "discovered_from_search": c.execute(
                "SELECT COUNT(*) FROM discovered_urls").fetchone()[0]},
            pages={"retrieved": sum(v for k, v in outcomes.items() if k != "failed"), "failed": outcomes.get("failed", 0),
                   "skipped_not_opportunity": sum(v for k, v in outcomes.items() if k.startswith("skipped") or k == "not_an_opportunity"),
                   "by_outcome": outcomes},
            candidates={"unique_records": n, "duplicates_merged": outcomes.get("merged", 0)},
            verification={"record_level_verified_against_official_source": len(verified_src),
                          "record_status": {s: sum(1 for o in opps if str(o.verification_status) == s)
                                            for s in sorted({str(o.verification_status) for o in opps})},
                          "field_level": {"confirmed_current_deadline": sum(f["current_deadline"] for f in fv),
                                          "confirmed_nationality": sum(f["nationality"] for f in fv),
                                          "confirmed_funding": sum(f["funding"] for f in fv),
                                          "all_three_confirmed": sum(all(f.values()) for f in fv)}},
            trust=freshness.trust_counts(opps, c.execute("SELECT COUNT(*) FROM discovered_urls").fetchone()[0], self.today),
            extraction_errors=errors[:20],
            missing_field_rates=stats["missing_rate"] if n else {},
            runtime_seconds=round(runtime, 1),
            notes=["A discovered URL is not an opportunity; a record verified against its official source is not "
                   "verified on every field - see field_level."])

    def get_opportunity(self, ref: str) -> dict:
        o = self._opp(ref)
        reports = self.store.issue_reports("open", o.id)
        held = {"eligibility": "eligible_countries", "funding": "funding_type", "cycle": "cycle", "deadline": "deadline"}
        for field, key in held.items():
            n = sum(1 for r in reports if r["field"] == field)
            if n >= 2 and o.field_status.get(key, {}).get("state") not in (None, "not_stated", "needs_review"):
                o.field_status[key] = {"state": "needs_review", "detail": f"{n} open user reports say this value is wrong"}
        return _out(opportunity=o.to_dict(), deadline_history=self.store.deadline_history(o.id),
                    verifications=self.store.verifications(o.id), open_issue_reports=len(reports))

    FUNDING_LABELS = {"fully_funded": "Fully funded (tuition and living costs)", "partially_funded": "Partly funded",
                      "tuition_funded": "Tuition only", "stipend_only": "Living allowance only",
                      "fee_waiver": "Fee waiver", "assistantship": "Assistantship"}
    CYCLE_LABELS = {"open": "Open", "closed": "Closed", "upcoming": "Opens later", "not_announced": "Next round not announced",
                    "rolling": "Rolling (any time)"}

    def decision_card(self, ref: str) -> dict:
        """The four decisions an applicant acts on, as a reader-facing card (round 46, for the web front end): each with
        a state (answered | check | not_stated), a plain value, the quotations and the official page. A value held for
        review is shown with state "check": it is what the page seems to say, unconfirmed. Next to each English value
        are its codes (mode/countries, code, dates), so a client can show the value in its own language."""
        from .audit import cycle_status, decision_evidence, field_status, funding_type
        from .countries import COUNTRIES
        from .models import DeadlineKind
        from . import site
        from .translate import english
        o = self._opp(ref)
        fs, ev = field_status(o, self.today), decision_evidence(o, self.today)
        name = lambda c: COUNTRIES.get(c, (c, ""))[0]   # noqa: E731
        tr = english(self.store, o)
        in_english = {k[:300]: v for k, v in tr["texts"].items()}
        with_english = lambda qs: [q | {"translation": in_english.get(q.get("quote", ""), "")} for q in qs]   # noqa: E731

        def state(key: str, value_present: bool) -> str:
            st = fs.get(key, {}).get("state")
            if not value_present or st in ("not_stated", None):
                return "not_stated"
            return "check" if st in ("needs_review", "unsupported") else "answered"

        n = o.nationality
        nat_value = {"any": "Open to every nationality",
                     "include": "Only citizens of: " + ", ".join(name(c) for c in n.countries[:60]),
                     "exclude": "Everyone except citizens of: " + ", ".join(name(c) for c in n.countries[:60])}.get(n.mode, "")
        ft = funding_type(o)["state"]
        cyc = cycle_status(o, self.today)
        dates = sorted({d.date for d in o.deadlines if d.date and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)})
        dl_quotes = [{"quote": d.label[:300], "url": d.source_url} for d in o.deadlines
                     if d.date in dates and d.label][:3]
        for k in ("eligibility", "funding", "cycle"):
            if k in ev:
                ev[k]["quotes"] = with_english(ev[k].get("quotes", []))
        dl_quotes = with_english(dl_quotes)
        card = {
            "eligibility": {"state": state("eligible_countries", bool(nat_value)), "value": nat_value or "Not stated on the page",
                            "mode": n.mode if nat_value else "", "countries": list(n.countries[:60]),
                            "quotes": ev.get("eligibility", {}).get("quotes", [])},
            "funding": {"state": state("funding_type", ft in self.FUNDING_LABELS), "value": self.FUNDING_LABELS.get(ft, "Not stated on the page"),
                        "code": ft if ft in self.FUNDING_LABELS else "", "quotes": ev.get("funding", {}).get("quotes", [])},
            "deadline": {"state": state("deadline", bool(dates)), "value": ", ".join(dates) or "No dated deadline on the page",
                         "dates": dates, "quotes": dl_quotes},
            "cycle": {"state": state("cycle", cyc["state"] in self.CYCLE_LABELS), "value": self.CYCLE_LABELS.get(cyc["state"], "Not stated"),
                      "code": cyc["state"] if cyc["state"] in self.CYCLE_LABELS else "",
                      "detail": cyc.get("detail", ""), "quotes": ev.get("cycle", {}).get("quotes", [])},
        }
        return _out(id=o.id, title=tr["title"], title_original=o.title if tr["title"] != o.title else "",
                    language=tr["language"], provider=o.provider_name, official_url=o.info_url,
                    application_url=o.application_url, details=site.details(self.store, o, self.today),
                    destination_countries=[name(c) for c in o.destination_countries],
                    destination_country_codes=list(o.destination_countries),
                    destination_inferred="destination:host" in o.tags, levels=o.study_levels,
                    last_checked=o.last_verified_at or o.updated_at, decisions=card, as_of=self.today.isoformat(),
                    note="Confirm every value on the official page before you apply. Values marked 'check' could not "
                         "be confirmed automatically.")

    ISSUE_FIELDS = ("eligibility", "funding", "cycle", "deadline", "levels", "provider", "page", "other")

    def report_issue(self, ref: str, field: str, note: str, shown_value: str = "") -> dict:
        """A user says that a value shown for this opportunity is wrong. Stored without any profile or contact
        detail; e-mail addresses and phone numbers in the note are removed. Reports are reviewed by the operator
        (list_issue_reports / resolve_issue_report); a record with two or more open reports on one field is
        shown as needs_review for that field until they are resolved."""
        import re
        o = self._opp(ref)
        if field not in self.ISSUE_FIELDS:
            raise ValueError(f"field must be one of {', '.join(self.ISSUE_FIELDS)}")
        text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email removed]", (note or "").strip())
        text = re.sub(r"(?<!\d)\+?\d[\d ()-]{7,}\d(?!\d)", "[number removed]", text)[:1000]
        if len(text) < 5:
            raise ValueError("say what is wrong in at least a few words")
        rid = self.store.add_issue_report(o.id, field, (shown_value or "")[:200], text)
        return _out(report_id=rid, opportunity_id=o.id, field=field, status="open",
                    message="Thank you. The report is kept without any personal detail and is reviewed by the operator.")

    def list_issue_reports(self, status: str = "open", ref: str = "") -> dict:
        oid = self._opp(ref).id if ref else ""
        rows = self.store.issue_reports(status, oid)
        return _out(reports=rows, count=len(rows))

    def resolve_issue_report(self, report_id: int, status: str, resolution: str = "") -> dict:
        if status not in ("fixed", "not_an_error", "duplicate"):
            raise ValueError("status must be fixed, not_an_error or duplicate")
        if not self.store.resolve_issue_report(report_id, status, resolution):
            raise NotFound(f"no issue report {report_id}")
        return _out(report_id=report_id, status=status)

    def search_opportunities(self, country: str = "", level: str = "", text: str = "", status: str = "",
                             funding: str = "", open_only: bool = False, citizenship: str = "", sort: str = "",
                             limit: int = 60, offset: int = 0, within_days: int = 0, discipline: str = "") -> dict:
        """Catalogue search for the site and the CLI (round 47, site.py): every word must match (title, provider,
        quotations, in the original and in English; S2/master, Jepang/Japan and other synonyms), filters by destination,
        level, funding, open applications and the applicant's citizenship, sorted by relevance or nearest deadline,
        with counts per filter value."""
        from . import site
        return _out(**site.search(self.store, self.today, text=text, country=country, level=level, funding=funding,
                                  open_only=open_only, citizenship=citizenship, status=status, sort=sort,
                                  limit=limit, offset=offset, within_days=within_days, discipline=discipline))

    def sources_status(self, check: bool = False) -> dict:
        states = self.store.source_states()
        checks = []
        if check:
            for s in self.sources:
                if not s.enabled:
                    continue
                ok, why = self.fetcher.robots_ok(s.url)
                if ok:
                    try:
                        r = self.fetcher.get(s.url)
                        self.store.record_source(s.id, True, f"HTTP {r.status}")
                        checks.append({"id": s.id, "ok": True, "status": r.status, "final_url": r.url})
                    except Exception as e:
                        self.store.record_source(s.id, False, "failed", getattr(e, "reason", str(e)))
                        checks.append({"id": s.id, "ok": False, "error": getattr(e, "reason", str(e))})
                else:
                    self.store.record_source(s.id, False, "robots", why)
                    checks.append({"id": s.id, "ok": False, "error": why})
            states = self.store.source_states()
        rows = []
        for s in self.sources:
            st = states.get(s.id, {})
            fresh = None
            if st.get("last_ok"):
                age = (self.today - date.fromisoformat(st["last_ok"][:10])).days
                fresh = "fresh" if age <= s.refresh_days else f"stale ({age}d > {s.refresh_days}d)"
            rows.append({"id": s.id, "name": s.name, "type": s.source_type, "countries": s.countries, "url": s.url,
                         "enabled": s.enabled, "last_checked": st.get("last_checked"), "last_ok": st.get("last_ok"),
                         "freshness": fresh or "never fetched", "consecutive_failures": st.get("consecutive_failures", 0),
                         "last_error": st.get("last_error")})
        prov = self.search.name if self.search else None
        ai = self.extractor_llm.name if self.extractor_llm else "none configured (deterministic extraction only)"
        return _out(sources=rows, checks=checks, coverage=registry.coverage(self.sources, states),
                    search_provider=prov or "none configured (registry-only discovery)", ai_extraction=ai,
                    recent_jobs=self.store.jobs(5))

    def add_source(self, entry: dict) -> dict:
        path = registry.add_local_source(entry)
        self.sources = registry.load_sources()
        return _out(added=entry["id"], file=str(path))

    # ------------------------------------------------------------- evaluation

    def match(self, ref: str, profile_id: str = "default") -> dict:
        o, p = self._opp(ref), self._profile(profile_id)
        e = eligibility.evaluate(o, p, self.today)
        return _out(eligibility=e, funding=funding.classify(o), verification_status=str(o.verification_status),
                    last_verified_at=o.last_verified_at)

    def funding_estimate(self, ref: str, tuition_per_year=None, living_per_month=None, currency=None, fx=None) -> dict:
        o = self._opp(ref)
        return _out(classification=funding.classify(o),
                    estimate=funding.estimate(o, tuition_per_year, living_per_month, currency, fx))

    def rank(self, profile_id: str = "default", weights: Optional[dict] = None, top: int = 20,
             include_expired: bool = False) -> dict:
        from . import site
        r = ranking.rank(self.store.list_opportunities(), self._profile(profile_id), weights, self.today,
                         include_expired)
        r["ranked"] = r["ranked"][:top]
        by_id = {e.summary["id"]: e.summary for e in site.index(self.store, self.today)}
        for x in r["ranked"]:   # the card the site shows: English title, codes, deadline
            x["summary"] = by_id.get(x["opportunity_id"], {})
        return _out(**r)

    # ------------------------------------------------------------- planning and documents

    def plan(self, ref: str, profile_id: str = "default") -> dict:
        o, p = self._opp(ref), self._profile(profile_id)
        app = tracker.ensure_application(self.store, profile_id, o.id)
        have = {d["title"] for d in tracker.documents(self.store, app["id"])}
        m = planning.requirements_matrix(o, p, have, self.today)
        tracker.save_checklist(self.store, app["id"], m["matrix"])
        return _out(application_id=app["id"], **m)

    def prepare(self, ref: str, kinds: Optional[list[str]] = None, profile_id: str = "default", save: bool = True) -> dict:
        """Document plan + drafts. Voice documents come back as briefs + factual skeletons unless an LLM is set."""
        o, p = self._opp(ref), self._profile(profile_id)
        app = tracker.ensure_application(self.store, profile_id, o.id)
        tasks = docs_mod.writing_tasks(o)
        kinds = kinds or (["scholarship_cv"] + [t["kind"] for t in tasks] + ["application_summary"])
        out = []
        others = {d["title"]: d["content"] for d in tracker.documents(self.store, app["id"])}
        for k in dict.fromkeys(kinds):
            if k == "application_summary":
                e = eligibility.evaluate(o, p, self.today)
                text = docs_mod.application_summary(o, e, funding.classify(o),
                                                    planning.requirements_matrix(o, p, today=self.today))
                g = {"kind": k, "title": docs_mod.KINDS[k], "content": text, "method": "assembled", "brief": {}}
            else:
                g = docs_mod.generate(k, o, p, self.llm)
            rv = review.review(g["content"], g["brief"], p, others) if g["brief"] else None
            saved = tracker.save_document(self.store, app["id"], k, g["title"], g["content"], rv) if save else None
            out.append({"kind": k, "title": g["title"], "method": g["method"], "review": rv, "saved": saved,
                        "brief": g["brief"], "content": g["content"]})
        if save and AppStatus(tracker.get_application(self.store, app["id"])["status"]) in (
                AppStatus.DISCOVERED, AppStatus.AWAITING_VERIFICATION, AppStatus.ELIGIBILITY_REVIEW, AppStatus.SHORTLISTED):
            self._advance(app["id"], AppStatus.PREPARING, "documents drafted")
        return _out(application_id=app["id"], writing_tasks=tasks, documents=out)

    def _advance(self, aid: str, target: AppStatus, note: str) -> None:
        """Walk forward through allowed states to target (e.g. discovered -> ... -> preparing)."""
        order = [AppStatus.DISCOVERED, AppStatus.AWAITING_VERIFICATION, AppStatus.ELIGIBILITY_REVIEW,
                 AppStatus.SHORTLISTED, AppStatus.PREPARING]
        cur = AppStatus(tracker.get_application(self.store, aid)["status"])
        if cur in order and target in order:
            for s in order[order.index(cur) + 1: order.index(target) + 1]:
                tracker.transition(self.store, aid, str(s), note)

    def brief(self, ref: str, kind: str, profile_id: str = "default") -> dict:
        return _out(brief=docs_mod.brief(kind, self._opp(ref), self._profile(profile_id)))

    def save_draft(self, ref: str, kind: str, content: str, profile_id: str = "default") -> dict:
        """Store a draft written by the orchestrating model or the user, after review."""
        o, p = self._opp(ref), self._profile(profile_id)
        app = tracker.ensure_application(self.store, profile_id, o.id)
        b = docs_mod.brief(kind, o, p)
        others = {d["title"]: d["content"] for d in tracker.documents(self.store, app["id"]) if d["kind"] != kind}
        rv = review.review(content, b, p, others)
        saved = tracker.save_document(self.store, app["id"], kind, docs_mod.KINDS[kind], content, rv)
        return _out(saved=saved, review=rv)

    def review_draft(self, ref: str, kind: str, content: str, profile_id: str = "default") -> dict:
        o, p = self._opp(ref), self._profile(profile_id)
        return _out(review=review.review(content, docs_mod.brief(kind, o, p), p))

    def documents_audit(self, ref: str, profile_id: str = "default") -> dict:
        o, p = self._opp(ref), self._profile(profile_id)
        app = tracker.ensure_application(self.store, profile_id, o.id)
        drafts = tracker.documents(self.store, app["id"])
        m = planning.requirements_matrix(o, p, {d["title"] for d in drafts}, self.today)
        saved = {r["name"]: r["status"] for r in tracker.checklist(self.store, app["id"])}
        for r in m["matrix"]:
            if saved.get(r["name"]) == "done":
                r["status"] = "done"
        return _out(application_id=app["id"], matrix=m["matrix"], notes=m["notes"],
                    drafts=[{"kind": d["kind"], "title": d["title"], "version": d["version"],
                             "review_passed": (d["review"] or {}).get("passed")} for d in drafts],
                    missing=[r["name"] for r in m["matrix"] if r["status"] != "done" and r["readiness"] == "missing"])

    def pre_submission_review(self, ref: str, profile_id: str = "default") -> dict:
        o, p = self._opp(ref), self._profile(profile_id)
        app = tracker.ensure_application(self.store, profile_id, o.id)
        audit = self.documents_audit(ref, profile_id)
        e = eligibility.evaluate(o, p, self.today)
        drafts = tracker.documents(self.store, app["id"])
        blockers = []
        if e["decision"] in ("INELIGIBLE", "UNCERTAIN", "INSUFFICIENT_INFORMATION"):
            blockers.append(f"eligibility is {e['decision']}: {e['next_action']}")
        if o.verification_status != VerificationStatus.CONFIRMED:
            blockers.append(f"opportunity not verified against the official source ({o.verification_status})")
        for d in drafts:
            if d["review"] and not d["review"]["passed"]:
                blockers.append(f"{d['title']} v{d['version']} has {d['review']['errors']} review error(s)")
        mand_missing = [r["name"] for r in audit["matrix"] if r["mandatory"] == "mandatory" and r["status"] != "done"]
        if mand_missing:
            blockers.append("mandatory items not marked done: " + ", ".join(mand_missing))
        nd = ranking.next_deadline(o, self.today)
        if not nd:
            blockers.append("no confirmed upcoming deadline")
        return _out(application_id=app["id"], ready=not blockers, blockers=blockers,
                    next_deadline=nd.to_dict() if nd else None, eligibility=e["decision"],
                    reminder="This agent never submits applications or sends messages; you submit on the official portal.")

    def export_document(self, ref: str, kind: str, fmt: str, out_dir: Path, profile_id: str = "default") -> dict:
        o = self._opp(ref)
        aid = tracker.application_id(profile_id, o.id)
        d = next((x for x in tracker.documents(self.store, aid) if x["kind"] == kind), None)
        if not d:
            raise NotFound(f"no saved {kind} for this application - run /prepare first")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = f"{o.id}_{kind}_v{d['version']}"
        if fmt == "md":
            path = out_dir / f"{safe}.md"
            path.write_text(d["content"], encoding="utf-8")
        elif fmt == "docx":
            path = out_dir / f"{safe}.docx"
            path.write_bytes(docs_mod.to_docx(d["content"]))
        else:
            raise ValueError("format must be md or docx (PDF: open the .docx and export it)")
        return _out(file=str(path))

    # ------------------------------------------------------------- tracking

    def track(self, ref: Optional[str] = None, status: Optional[str] = None, note: str = "",
              item: Optional[str] = None, item_status: Optional[str] = None, profile_id: str = "default") -> dict:
        from .models import ALLOWED_TRANSITIONS
        nxt = lambda st: sorted(str(x) for x in ALLOWED_TRANSITIONS.get(AppStatus(st), set()))   # noqa: E731
        if ref is None:
            from . import site
            apps = tracker.list_applications(self.store, profile_id)
            for a in apps:
                o = self.store.get_opportunity(a["opportunity_id"])
                a["summary"] = site.summary(self.store, o, self.today) if o else {}
                a["title"] = a["summary"].get("title") or "(missing opportunity)"
                a["allowed_next"] = nxt(a["status"])
                items = tracker.checklist(self.store, a["id"])
                a["checklist"] = {"done": sum(1 for i in items if i["status"] in ("done", "not_applicable")),
                                  "total": len(items)}
                a["documents"] = len(tracker.documents(self.store, a["id"]))
            return _out(applications=apps)
        o = self._opp(ref)
        app = tracker.ensure_application(self.store, profile_id, o.id)
        if status:
            app = tracker.transition(self.store, app["id"], status, note)
        if item:
            tracker.mark_item(self.store, app["id"], item, item_status or "done")
        app = tracker.get_application(self.store, app["id"])
        return _out(application=app | {"allowed_next": nxt(app["status"])},
                    checklist=tracker.checklist(self.store, app["id"]), title=o.title)

    def deadlines(self, within_days: int = 90, profile_id: str = "default", tracked_only: bool = False) -> dict:
        return _out(**tracker.deadlines(self.store, profile_id, within_days, self.today, tracked_only))

    def reminders(self, profile_id: str = "default", notifier: Optional[tracker.Notifier] = None) -> dict:
        rem = tracker.plan_reminders(self.store, profile_id, today=self.today)
        delivered = (notifier or tracker.ConsoleNotifier()).deliver(rem)
        return _out(reminders=rem, delivery=delivered)

    def outcome(self, ref: str, result: str, lessons: str = "", profile_id: str = "default") -> dict:
        o = self._opp(ref)
        aid = tracker.application_id(profile_id, o.id)
        if not tracker.get_application(self.store, aid):
            raise NotFound("this opportunity is not tracked yet - run /track first")
        return _out(application=tracker.record_outcome(self.store, aid, result, lessons))

    # ------------------------------------------------------------- reporting

    def ai_usage(self) -> dict:
        """Provider in use and the recorded AI request ledger (counts and estimated USD only)."""
        llm = self.extractor_llm
        rows = self.store.catalog.execute(
            "SELECT provider, model, status, COUNT(*) n, SUM(input_tokens) tin, SUM(output_tokens) tout, "
            "SUM(cost_usd) cost FROM llm_usage GROUP BY provider, model, status").fetchall()
        out = {"provider": llm.name if llm else "none", "ledger": [dict(r) for r in rows],
               "note": "costs are estimates from list prices and reported token counts; the Anthropic Console is authoritative"}
        if llm is not None and hasattr(llm, "usage"):
            out["this_process"] = llm.usage()
        return out

    def catalog_audit(self) -> dict:
        from .audit import audit
        out = audit(self.store.list_opportunities(), self.today)
        out["tiers"]["discovered_leads"] = self.store.catalog.execute("SELECT COUNT(*) FROM discovered_urls").fetchone()[0]
        return _out(**out)

    def discovery_yield(self, baseline_dir: Optional[str] = None) -> dict:
        from pathlib import Path
        from .audit import discovery_yield, known_keys
        known: set[str] = set()
        if baseline_dir:
            base = Store(Path(baseline_dir))
            known = known_keys(base.list_opportunities())
            base.close()
        return _out(baseline=baseline_dir or "", **discovery_yield(self.store.list_opportunities(), known))

    def catalog_stats(self) -> dict:
        """How complete the stored records are: share of opportunities missing each key field."""
        opps = self.store.list_opportunities()
        checks = {
            "deadline_any": lambda o: bool(o.deadlines),
            "deadline_current_dated": lambda o: any(d.date and d.certainty != "historical" for d in o.deadlines),
            "nationality_rule": lambda o: o.nationality.mode != "unknown",
            "funding_any": lambda o: bool(o.funding),
            "funding_amount": lambda o: any(c.amount is not None for c in o.funding),
            "tuition_coverage": lambda o: any(c.kind == "tuition" for c in o.funding),
            "language_requirement": lambda o: bool(o.language_requirements),
            "required_documents": lambda o: bool(o.required_documents),
            "study_levels": lambda o: bool(o.study_levels),
            "application_url": lambda o: bool(o.application_url),
        }
        n = len(opps)
        present = {k: sum(1 for o in opps if f(o)) for k, f in checks.items()}
        by_status: dict[str, int] = {}
        for o in opps:
            by_status[str(o.verification_status)] = by_status.get(str(o.verification_status), 0) + 1
        return _out(opportunities=n, verification=by_status,
                    present={k: v for k, v in present.items()},
                    missing_rate={k: round(1 - v / n, 3) if n else None for k, v in present.items()},
                    with_conflicts=sum(1 for o in opps if o.conflicts),
                    evidence_items=sum(len(o.evidence) for o in opps),
                    ai_evidence_items=sum(1 for o in opps for e in o.evidence if e.note.startswith("ai-assisted")))

    def report(self, profile_id: str = "default") -> dict:
        opps = self.store.list_opportunities()
        by_status: dict[str, int] = {}
        for o in opps:
            by_status[str(o.verification_status)] = by_status.get(str(o.verification_status), 0) + 1
        p = self.store.get_profile(profile_id)
        decisions: dict[str, int] = {}
        ranked = None
        if p:
            for o in opps:
                d = eligibility.evaluate(o, p, self.today)["decision"]
                decisions[d] = decisions.get(d, 0) + 1
            ranked = ranking.rank(opps, p, today=self.today)["ranked"][:10]
        apps = tracker.list_applications(self.store, profile_id)
        app_status: dict[str, int] = {}
        for a in apps:
            app_status[a["status"]] = app_status.get(a["status"], 0) + 1
        dl = tracker.deadlines(self.store, profile_id, 60, self.today)
        cov = registry.coverage(self.sources, self.store.source_states())
        return _out(as_of=self.today.isoformat(), opportunities_total=len(opps), verification=by_status,
                    eligibility=decisions, top_ranked=[{k: r[k] for k in ("opportunity_id", "title", "score",
                                                                          "eligibility", "funding")} for r in ranked or []],
                    applications=app_status, shortlisted=[a for a in apps if a["status"] == str(AppStatus.SHORTLISTED)],
                    upcoming_deadlines=dl["confirmed"][:15], expected_deadlines=dl["expected_unconfirmed"][:15],
                    urgent_tasks=dl["urgent_tasks"],
                    coverage={k: cov[k] for k in ("countries_total", "countries_with_official_source",
                                                  "countries_with_verified_healthy_source", "by_region")},
                    recent_jobs=self.store.jobs(5), lessons=tracker.lessons(self.store, profile_id)[:5],
                    disclaimer=ranking.DISCLAIMER)
