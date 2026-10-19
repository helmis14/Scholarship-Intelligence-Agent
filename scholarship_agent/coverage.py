"""Coverage and quality data for a future dashboard: what was attempted, what worked, what is still missing.

A country or language counts only by what happened, never because it is configured:
  not_attempted   no query was run
  attempted       queries ran, all failed
  searched        at least one query answered
  retrieved       at least one page from its results was fetched
  yielded         at least one opportunity record came from it
  official        at least one of those records rests on an official source (authority levels 1-4)
Discovered URLs are leads; records are candidates; only official-source confirmation makes a field verified.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from . import countries, freshness, languages
from .discovery import host_of
from .evidence import is_official
from .store import Store

LEVELS = ["not_attempted", "attempted", "searched", "retrieved", "yielded", "official"]
KEY_FIELDS = {"deadline": lambda o: any((d.date or d.approximate) and d.kind in ("scholarship", "admission", "rolling")
                                        for d in o.deadlines),
              "nationality": lambda o: o.nationality.mode != "unknown",
              "study_levels": lambda o: bool(o.study_levels),
              "funding": lambda o: any(c.covered for c in o.funding)}


def _missing_rate(opps) -> Optional[float]:
    if not opps:
        return None
    return round(sum(sum(not f(o) for f in KEY_FIELDS.values()) for o in opps) / (len(opps) * len(KEY_FIELDS)), 3)


def report(store: Store, today: Optional[date] = None, sources=None, top_domains: int = 30) -> dict:
    today = today or date.today()
    c = store.catalog
    opps = {o.id: o for o in store.list_opportunities()}
    q_rows = c.execute("SELECT country, lang, category, error, run_at, n_results FROM search_queries").fetchall()
    u_rows = c.execute("SELECT * FROM discovered_urls").fetchall()

    def blank():
        return {"queries": 0, "queries_ok": 0, "last_success": None, "last_failure": None, "results": 0,
                "urls_discovered": 0, "pages_retrieved": 0, "pages_failed": 0, "opportunities": set()}
    by: dict[str, dict] = {"country": {}, "language": {}, "category": {}}
    for r in q_rows:
        for dim, key in (("country", r["country"] or "?"), ("language", r["lang"] or "?"), ("category", r["category"] or "?")):
            d = by[dim].setdefault(key, blank())
            d["queries"] += 1
            if r["error"] is None:
                d["queries_ok"] += 1
                d["results"] += r["n_results"] or 0
                d["last_success"] = max(d["last_success"] or "", r["run_at"])
            else:
                d["last_failure"] = max(d["last_failure"] or "", r["run_at"])
    domains: dict[str, dict] = {}
    methods: dict[str, int] = {}
    retrieval: dict[str, int] = {}
    page_langs: dict[str, int] = {}
    for r in u_rows:
        keys = (("country", r["country"] or "?"), ("language", r["lang"] or "?"), ("category", r["category"] or "?"))
        fetched = r["status"] in ("opportunity", "skipped") and not (r["error"] or "").startswith("filtered")
        for dim, key in keys:
            d = by[dim].setdefault(key, blank())
            d["urls_discovered"] += 1
            d["pages_retrieved"] += fetched
            d["pages_failed"] += r["status"] == "failed"
            if r["opportunity_id"]:
                d["opportunities"].add(r["opportunity_id"])
        dom = domains.setdefault(host_of(r["url"]), {"urls": 0, "pages_retrieved": 0, "failed": 0, "opportunities": set()})
        dom["urls"] += 1
        dom["pages_retrieved"] += fetched
        dom["failed"] += r["status"] == "failed"
        if r["opportunity_id"]:
            dom["opportunities"].add(r["opportunity_id"])
        methods[r["method"] or (r["via"] or "?").split(":")[0]] = methods.get(r["method"] or (r["via"] or "?").split(":")[0], 0) + 1
        if fetched:
            retrieval[r["retrieval"] or "http"] = retrieval.get(r["retrieval"] or "http", 0) + 1
            if r["page_lang"]:
                page_langs[r["page_lang"]] = page_langs.get(r["page_lang"], 0) + 1

    def finish(d: dict) -> dict:
        recs = [opps[i] for i in d.pop("opportunities") if i in opps]
        d["unique_opportunities"] = len(recs)
        d["official_records"] = sum(is_official(freshness.record_authority(o)) for o in recs)
        d["official_rate"] = round(d["official_records"] / len(recs), 3) if recs else None
        d["missing_field_rate"] = _missing_rate(recs)
        d["status"] = ("official" if d["official_records"] else "yielded" if recs else
                       "retrieved" if d["pages_retrieved"] else "searched" if d["queries_ok"] else
                       "attempted" if d["queries"] else "not_attempted")
        return d
    for dim in by:
        by[dim] = {k: finish(v) for k, v in sorted(by[dim].items())}
    dom_out = {}
    for k, v in sorted(domains.items(), key=lambda kv: -kv[1]["urls"])[:top_domains]:
        v["unique_opportunities"] = len(v.pop("opportunities"))
        dom_out[k] = v
    if sources is not None:
        from .providers import classify_domain
        for k, v in dom_out.items():
            v["trust"] = classify_domain("https://" + k, sources, store)[0]

    status_count = {lvl: 0 for lvl in LEVELS}
    for cc in countries.COUNTRIES:
        status_count[by["country"].get(cc, {}).get("status", "not_attempted")] += 1
    lang_status = {}
    for code in languages.languages():
        lang_status[code] = by["language"].get(code, {}).get("status", "not_attempted")
    outcomes = {r["outcome"]: r["n"] for r in c.execute("SELECT outcome, COUNT(*) n FROM ingestion_results GROUP BY outcome")}
    new, merged = outcomes.get("new", 0), outcomes.get("merged", 0)
    ai = {r["purpose"] or "extract-full": {"requests": r["n"], "paid": r["paid"] or 0, "input_tokens": r["tin"] or 0,
                                           "output_tokens": r["tout"] or 0, "cost_usd": round(r["cost"] or 0, 4),
                                           "mean_latency_ms": round(r["lat"], 1) if r["lat"] else None}
          for r in c.execute("SELECT purpose, COUNT(*) n, SUM(status='ok') paid, SUM(input_tokens) tin, "
                             "SUM(output_tokens) tout, SUM(cost_usd) cost, AVG(CASE WHEN status='ok' THEN latency_ms END) lat "
                             "FROM llm_usage GROUP BY purpose")}
    trust = freshness.trust_counts(list(opps.values()), len(u_rows), today)

    gaps, tasks = [], []
    never = [cc for cc in countries.COUNTRIES if by["country"].get(cc, {}).get("status", "not_attempted") == "not_attempted"]
    if never:
        gaps.append({"kind": "countries_not_attempted", "count": len(never), "sample": sorted(never)[:20]})
        tasks.append(f"strategy-run --countries {','.join(sorted(never)[:10])} (first {min(10, len(never))} of {len(never)})")
    dry = sorted(k for k, v in by["country"].items() if v["status"] in ("attempted", "searched") and k != "?")
    if dry:
        gaps.append({"kind": "countries_searched_without_a_retrieved_page", "countries": dry})
        tasks.append("add official sources or local-language queries for: " + ",".join(dry[:15]))
    unused = sorted(l for l, s in lang_status.items() if s == "not_attempted" and l != "en")
    if unused:
        gaps.append({"kind": "registered_languages_never_queried", "languages": unused})
    noisy = sorted((k for k, v in dom_out.items() if v["failed"] >= 3 and not v["pages_retrieved"]))
    if noisy:
        gaps.append({"kind": "domains_always_failing", "domains": noisy})
        tasks.append("check robots/terms or an official feed for: " + ",".join(noisy[:10]))
    pending = sum(1 for r in u_rows if r["status"] == "new")
    if pending:
        tasks.append(f"{pending} discovered URLs were never fetched (interrupted run): strategy-run resumes them first")
    not_loaded = [r["url"] for r in u_rows if r["status"] == "not_loaded"]
    if not_loaded:
        # these were never judged: a programme behind JavaScript or a login is not "not a programme"
        gaps.append({"kind": "pages_not_loaded_not_assessed", "count": len(not_loaded), "sample": not_loaded[:10]})
        tasks.append(f"{len(not_loaded)} pages did not load (JavaScript, login wall, empty or unreadable): not assessed; "
                     "retry with SCHOLAR_BROWSER=playwright or check them by hand")
    cands = c.execute("SELECT COUNT(*) FROM provider_candidates WHERE status='candidate'").fetchone()[0]
    if cands:
        tasks.append(f"review {cands} provider candidates: provider-candidates / provider-review")

    return {
        "summary": {"countries_total": len(countries.COUNTRIES), "countries_by_status": status_count,
                    "languages_registered": len(languages.languages()),
                    "languages_by_status": {lvl: sum(1 for s in lang_status.values() if s == lvl) for lvl in LEVELS},
                    "page_languages_retrieved": dict(sorted(page_langs.items(), key=lambda kv: -kv[1])),
                    "queries": len(q_rows), "queries_failed": sum(1 for r in q_rows if r["error"] is not None),
                    "unique_source_domains": len(domains), "urls_discovered": len(u_rows),
                    "pages_retrieved": sum(retrieval.values()), "retrieval_by_method": retrieval,
                    "retrieval_failures": sum(1 for r in u_rows if r["status"] == "failed"),
                    "urls_by_discovery_method": methods,
                    "new_records": new, "duplicates_merged": merged,
                    "duplicate_rate": round(merged / (new + merged), 3) if new + merged else None,
                    "provider_candidates_pending": cands},
        "leads_vs_verified": {"discovered_urls": len(u_rows), "retrieved_pages": sum(retrieval.values()),
                              "opportunity_records": len(opps),
                              "official_source_records": trust["official_source_candidates"],
                              "officially_verified_programmes": trust["officially_verified_programmes"]},
        "quality": trust | {"missing_field_rate": _missing_rate(list(opps.values())),
                            "unsupported_note": "unsupported-value rates need labels; see `heldout --set a|b|c|d`"},
        "ai": ai,
        "by_country": by["country"], "by_language": by["language"], "by_category": by["category"],
        "top_domains": dom_out, "gaps": gaps, "next_tasks": tasks,
        "note": "Counts come from runs recorded in this catalog. Configured is not covered: see the status levels.",
    }

