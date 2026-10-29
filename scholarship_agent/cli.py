"""Command-line front end. Every command prints one JSON document on stdout.

    python3 -m scholarship_agent <command> [options]

Exit 0 on success, 1 on a usage/lookup/state error (JSON {"error": ...} on stdout),
2 on bad arguments.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .service import NotFound, ScholarshipService
from .store import data_dir
from .tracker import ICSNotifier, TransitionError

ESSAY_KINDS = ["essay", "personal_statement", "motivation_letter", "sop", "leadership_essay", "career_goals"]


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="scholarship_agent", description="Scholarship Intelligence Agent")
    ap.add_argument("--profile", default="default", help="applicant profile id (one per user)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="create or update the applicant profile")
    s.add_argument("--file", help="JSON file with profile fields (merged into the stored profile)")
    s.add_argument("--set", action="append", default=[], metavar="FIELD=JSON",
                   help='e.g. --set citizenships=\'["ID"]\' --set target_levels=\'["master"]\'')
    sub.add_parser("profile", help="show the stored profile")
    r = sub.add_parser("report-issue", help="report a value that is wrong on an opportunity (kept without personal details)")
    r.add_argument("opportunity")
    r.add_argument("--field", required=True, help="eligibility | funding | cycle | deadline | levels | provider | page | other")
    r.add_argument("--note", required=True, help="what is wrong and what the page says")
    r.add_argument("--shown", default="", help="the value that was shown")
    i = sub.add_parser("issues", help="operator: list reports, or resolve one with --resolve ID --status fixed|not_an_error|duplicate")
    i.add_argument("--status", default="open")
    i.add_argument("--opportunity", default="")
    i.add_argument("--resolve", type=int, default=0)
    i.add_argument("--resolution", default="")
    sub.add_parser("export-data", help="export all private data for this profile")
    d = sub.add_parser("delete-data", help="delete the profile and its private data")
    d.add_argument("--yes", action="store_true", help="required: confirms permanent deletion")

    s = sub.add_parser("discover", help="discover opportunities from sources and search")
    s.add_argument("--countries", help="destination ISO codes, comma-separated (default: all)")
    s.add_argument("--levels", help="bachelor,master,phd,postdoc,short_course,exchange")
    s.add_argument("--disciplines")
    s.add_argument("--nationality", help="ISO code; adds nationality-specific queries")
    s.add_argument("--sources", help="only these source ids")
    s.add_argument("--no-search", action="store_true", help="registry sources only")
    s.add_argument("--max-links", type=int, default=15)
    s.add_argument("--no-sitemaps", action="store_true", help="do not read the sources' published sitemaps")
    s.add_argument("--resume", type=int, metavar="JOB", help="continue an interrupted discover job; finished sources are skipped")

    s = sub.add_parser("scrape", help="ingest specific permitted URLs")
    s.add_argument("urls", nargs="+")
    s.add_argument("--provider", default="")
    s.add_argument("--countries")

    s = sub.add_parser("adapter", help="run a dedicated source adapter: daad | erasmus_mundus | euraxess | campusfrance | grants_at | nsp_india")
    s.add_argument("name", choices=["daad", "erasmus_mundus", "euraxess", "campusfrance", "grants_at", "nsp_india"])
    s.add_argument("--limit", type=int)
    s.add_argument("--details", action="store_true",
                   help="daad, campusfrance, grants_at: fetch programme details; nsp_india: read guidelines PDFs; erasmus_mundus: read consortium websites")
    s = sub.add_parser("euraxess-import", help="import a EURAXESS offer page you saved from your browser")
    s.add_argument("file")
    s.add_argument("--url", required=True, help="the offer's EURAXESS address")

    sub.add_parser("search-health", help="SearXNG upstream engines: ready or cooling down, and why")
    s = sub.add_parser("search-check", help="one real query to test the configured search provider")
    s.add_argument("--query", default="scholarship for international students")
    for name, hlp in (("strategy-plan", "show the country-by-country query plan"),
                      ("strategy-run", "run the country-by-country search strategy (uses search quota)")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("--countries", help="ISO codes, comma-separated (default: all)")
        s.add_argument("--regions", help="Africa,Americas,Asia,Europe,Oceania")
        s.add_argument("--categories", help="government,university,foundation,research,company,exchange,domestic,...")
        s.add_argument("--levels")
        s.add_argument("--queries-per-country", type=int)
        s.add_argument("--pages-per-query", type=int)
        s.add_argument("--fetch-per-query", type=int)
        s.add_argument("--max-countries", type=int)
        s.add_argument("--requery-days", type=int)
        s.add_argument("--concepts", help="localised concept queries (default: all; see languages.json)")
        s.add_argument("--concurrency", type=int, help="pages fetched in parallel (default 4; one at a time per host)")
        if name == "strategy-run":
            s.add_argument("--resume", type=int, metavar="JOB", help="continue an interrupted job from its checkpoint")
    sub.add_parser("coverage", help="countries configured vs searched, URLs by status")
    sub.add_parser("coverage-quality", help="coverage by country, language, category, domain and method; gaps")
    s = sub.add_parser("ai-plan", help="dry run: Claude requests full-page vs targeted on a labelled set (no paid call)")
    s.add_argument("--set", choices=["a", "b", "c", "d", "e", "f"], default="d")
    s.add_argument("--exact-tokens", action="store_true", help="count input tokens with the free counting endpoint")
    s = sub.add_parser("provider-candidates", help="domains that yielded opportunities but are not in the registry")
    s.add_argument("--status", default="candidate", choices=["candidate", "accepted", "rejected"])
    s = sub.add_parser("provider-review", help="accept or reject a provider candidate after checking it yourself")
    s.add_argument("domain")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--accept", action="store_true")
    g.add_argument("--reject", action="store_true")
    s.add_argument("--provider", default="", help="organisation the domain belongs to (needed to accept)")
    s.add_argument("--note", default="")
    s = sub.add_parser("run-report", help="found / retrieved / verified report across discovery runs")
    s.add_argument("--since-job", type=int, default=0)

    s = sub.add_parser("verify", help="verify an opportunity against its official source")
    s.add_argument("ref")
    s.add_argument("--official-url")
    s = sub.add_parser("refresh", help="re-verify stale opportunities (schedule this)")
    s.add_argument("--max-age-days", type=int, default=None, help="stale interval (default from schedule)")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--plan", action="store_true", help="show the prioritised refresh plan without fetching")
    s.add_argument("--undated", action="store_true",
                   help="re-read the official pages of listed programmes with no coming date (round 52)")

    s = sub.add_parser("show", help="full stored record for one opportunity")
    s.add_argument("ref")
    s = sub.add_parser("search", help="search the local catalog")
    s.add_argument("--country", default="")
    s.add_argument("--level", default="")
    s.add_argument("--text", default="")
    s.add_argument("--status", default="")

    s = sub.add_parser("rank", help="rank opportunities for the profile")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--weights", help='JSON, e.g. \'{"funding":0.3}\'')
    s.add_argument("--include-expired", action="store_true")
    s = sub.add_parser("match", help="explain eligibility and fit")
    s.add_argument("ref")
    s = sub.add_parser("funding", help="funding classification and coverage estimate")
    s.add_argument("ref")
    s.add_argument("--tuition", type=float)
    s.add_argument("--living", type=float, help="living cost per month")
    s.add_argument("--currency")
    s.add_argument("--fx", help='JSON like \'{"EUR->USD": 1.08}\'')

    s = sub.add_parser("plan", help="requirements matrix, checklist and timeline")
    s.add_argument("ref")
    s = sub.add_parser("prepare", help="document plan and drafts")
    s.add_argument("ref")
    s.add_argument("--kinds", help="comma-separated document kinds")
    s.add_argument("--no-save", action="store_true")
    s = sub.add_parser("essay", help="essay briefs, drafts and review")
    s.add_argument("ref")
    s.add_argument("--kind", default="essay", choices=ESSAY_KINDS)
    s = sub.add_parser("cv", help="tailored academic CV")
    s.add_argument("ref")
    s = sub.add_parser("brief", help="drafting brief for one document kind")
    s.add_argument("ref")
    s.add_argument("kind")
    s = sub.add_parser("save-draft", help="review and store a draft written elsewhere")
    s.add_argument("ref")
    s.add_argument("kind")
    s.add_argument("--file", required=True)
    s = sub.add_parser("documents", help="document readiness audit")
    s.add_argument("ref")
    s = sub.add_parser("export", help="export a saved document")
    s.add_argument("ref")
    s.add_argument("kind")
    s.add_argument("--format", default="docx", choices=["md", "docx", "pdf"])
    s.add_argument("--out", default=None)

    s = sub.add_parser("deadlines", help="upcoming deadlines and urgent tasks")
    s.add_argument("--days", type=int, default=90)
    s.add_argument("--tracked", action="store_true")
    s = sub.add_parser("reminders", help="plan reminders (console or .ics file; nothing is sent)")
    s.add_argument("--ics", help="write reminders to this .ics file")
    s = sub.add_parser("track", help="list or update applications")
    s.add_argument("ref", nargs="?")
    s.add_argument("--status")
    s.add_argument("--note", default="")
    s.add_argument("--item", help="checklist item name")
    s.add_argument("--item-status", default="done")
    s = sub.add_parser("review", help="pre-submission audit")
    s.add_argument("ref")
    s = sub.add_parser("outcome", help="record a result")
    s.add_argument("ref")
    s.add_argument("result", choices=["accepted", "rejected", "withdrawn", "expired", "interview", "waitlisted"])
    s.add_argument("--lessons", default="")
    sub.add_parser("report", help="structured status report")
    s = sub.add_parser("quality", help="score extraction against the labelled fixtures")
    s.add_argument("--fixtures", default=None)
    s.add_argument("--ai", action="store_true", help="also run the configured AI extractor")
    s.add_argument("--ai-only", action="store_true", help="score the AI extractor alone")
    sub.add_parser("catalog-audit", help="per field: present, not stated, not published or not applicable")
    s = sub.add_parser("discovery-yield", help="official programmes per country and level: new and verified")
    s.add_argument("--baseline", help="data directory of an earlier catalog; records found there are not new")
    s = sub.add_parser("stats", help="field completeness of the stored catalog")
    s = sub.add_parser("heldout", help="score extraction on the held-out real pages (tests/heldout, tests/heldout_b)")
    s.add_argument("--set", default="a", choices=["a", "b", "c", "d", "e", "f"])
    s.add_argument("--split", choices=["dev", "test"], help="set C only: development or test half")
    s.add_argument("--ai", action="store_true")
    s.add_argument("--ai-mode", default="full", choices=["full", "targeted"],
                   help="full: whole page, every field (evaluated path); targeted: only missing fields and passages")
    s.add_argument("--fetch", action="store_true", help="re-download the snapshots first (network)")
    s = sub.add_parser("compare", help="rules vs cloud providers on one held-out set (cloud modes run only when "
                                       "their key and <PREFIX>_ALLOW_PAID=1 are set; otherwise a cost estimate)")
    s.add_argument("--set", default="b", choices=["a", "b", "c", "d", "e", "f"])
    s.add_argument("--split", choices=["dev", "test"], help="set C only")
    s.add_argument("--providers", default="rules,anthropic",
                   help="comma list: rules,anthropic (gemini and ollama remain available but are inactive)")
    s = sub.add_parser("serve", help="HTTP JSON API with accounts (run behind an HTTPS reverse proxy; see web.py)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    sub.add_parser("security-status", help="encryption at rest, keys in use, accounts and sessions (no secrets shown)")
    sub.add_parser("encrypt-private", help="encrypt private data written before encryption, rewrap old keys")
    sub.add_parser("new-key", help="print a new random key for SCHOLAR_DATA_KEY or SCHOLAR_LOOKUP_KEY")
    s = sub.add_parser("ai-usage", help="AI provider, paid/dry-run requests, tokens and estimated cost (no keys)")
    s = sub.add_parser("translate", help="English translations of titles and quotations from pages in other languages "
                                        "(paid model calls only with AI_PROVIDER and <PREFIX>_ALLOW_PAID=1; else a cost estimate)")
    s.add_argument("--limit", type=int, default=0, help="translate at most this many texts")
    s = sub.add_parser("check", help="second reading of stored records by an independent model; disagreements are "
                                    "held for review (paid only with AI_PROVIDER and <PREFIX>_ALLOW_PAID=1)")
    s.add_argument("--limit", type=int, default=0, help="check at most this many records")
    s.add_argument("--refresh", action="store_true", help="read again records that already have a second reading")
    s.add_argument("--listed", action="store_true", help="only the programmes the site lists")
    s = sub.add_parser("backup", help="back up the catalogue, the private data and its keys into one archive")
    s.add_argument("--out", help="folder for the archives (default SCHOLAR_BACKUP_DIR or ~/ScholarshipBackups)")
    s.add_argument("--keep", type=int, default=7, help="keep this many newest backups (0 keeps all)")
    s = sub.add_parser("backups", help="list the backups with their date, size and record counts")
    s.add_argument("--out", help="folder of the archives")
    s = sub.add_parser("restore", help="restore a backup archive (the current data is saved first as pre-restore)")
    s.add_argument("archive", help="path of a scholarship-backup-*.tar.gz file")
    s.add_argument("--yes", action="store_true", help="confirm: the current data is replaced")
    s = sub.add_parser("describe", help="fill in programme descriptions from the pages already stored (no fetching)")
    s.add_argument("--limit", type=int, default=0, help="describe at most this many records")
    s.add_argument("--refresh", action="store_true", help="read again records that already have a description")
    s.add_argument("--fetch", action="store_true", help="read the official page again when it is not stored (free, slow)")
    s.add_argument("--listed", action="store_true", help="only the programmes the site lists")
    s = sub.add_parser("sources", help="source registry, coverage, freshness, failures")
    s.add_argument("--check", action="store_true", help="fetch every source now (network)")
    s.add_argument("--add", help="JSON object for a new local source")
    return ap


def run(args, svc: ScholarshipService) -> dict:
    pid = args.profile
    c = args.cmd
    if c == "setup":
        patch = json.loads(Path(args.file).read_text(encoding="utf-8")) if args.file else {}
        for kv in args.set:
            k, _, v = kv.partition("=")
            try:
                patch[k] = json.loads(v)
            except json.JSONDecodeError:
                patch[k] = v
        return svc.setup_profile(patch, pid)
    if c == "profile":
        return svc.get_profile(pid)
    if c == "report-issue":
        return svc.report_issue(args.opportunity, args.field, args.note, args.shown)
    if c == "issues":
        if args.resolve:
            return svc.resolve_issue_report(args.resolve, args.status, args.resolution)
        return svc.list_issue_reports(args.status, args.opportunity)
    if c == "export-data":
        return svc.export_private_data(pid)
    if c == "delete-data":
        if not args.yes:
            raise ValueError("refusing to delete without --yes")
        return svc.delete_private_data(pid)
    if c == "discover":
        return svc.discover(_csv(args.countries), _csv(args.levels), _csv(args.disciplines), args.nationality,
                            _csv(args.sources) or None, use_search=not args.no_search, max_links_per_source=args.max_links,
                            use_sitemaps=not args.no_sitemaps, resume_job=args.resume)
    if c == "scrape":
        return svc.scrape(args.urls, args.provider, _csv(args.countries))
    if c == "adapter":
        return svc.run_adapter(args.name, args.limit, args.details)
    if c == "euraxess-import":
        return svc.import_euraxess(Path(args.file).read_text(encoding="utf-8"), args.url)
    if c == "search-health":
        pool = getattr(svc.search, "pool", None)
        return {"provider": getattr(svc.search, "name", "none"), "interval_seconds": getattr(pool, "interval", None),
                "engines": pool.snapshot() if pool else {}}
    if c == "search-check":
        return svc.search_check(args.query)
    if c in ("strategy-plan", "strategy-run"):
        ov = {"countries": _csv(args.countries), "regions": _csv(args.regions), "categories": _csv(args.categories),
              "levels": _csv(args.levels), "queries_per_country": args.queries_per_country,
              "pages_per_query": args.pages_per_query, "fetch_per_query": args.fetch_per_query,
              "max_countries": args.max_countries, "requery_days": args.requery_days,
              "concepts": _csv(args.concepts), "concurrency": args.concurrency}
        if c == "strategy-plan":
            return svc.strategy_plan(**ov)
        return svc.strategy_run(resume_job=args.resume, **ov)
    if c == "coverage":
        return svc.coverage()
    if c == "coverage-quality":
        return svc.coverage_quality()
    if c == "ai-plan":
        from . import heldout
        from .ai_targeted import plan_set
        root = heldout.ROOT if args.set == "a" else heldout.ROOT.parent / f"heldout_{args.set}"
        llm = svc.extractor_llm if args.exact_tokens else None
        return plan_set(root, llm, exact=args.exact_tokens)
    if c == "provider-candidates":
        return svc.provider_candidates(args.status)
    if c == "provider-review":
        return svc.provider_review(args.domain, args.accept, args.provider, args.note)
    if c == "run-report":
        return svc.discovery_report(args.since_job)
    if c == "verify":
        return svc.verify(args.ref, args.official_url)
    if c == "refresh":
        return svc.refresh(args.max_age_days, args.limit, plan_only=args.plan, undated=args.undated)
    if c == "show":
        return svc.get_opportunity(args.ref)
    if c == "search":
        return svc.search_opportunities(args.country, args.level, args.text, args.status)
    if c == "rank":
        return svc.rank(pid, json.loads(args.weights) if args.weights else None, args.top, args.include_expired)
    if c == "match":
        return svc.match(args.ref, pid)
    if c == "funding":
        return svc.funding_estimate(args.ref, args.tuition, args.living, args.currency,
                                    json.loads(args.fx) if args.fx else None)
    if c == "plan":
        return svc.plan(args.ref, pid)
    if c == "prepare":
        return svc.prepare(args.ref, _csv(args.kinds) or None, pid, save=not args.no_save)
    if c == "essay":
        return svc.prepare(args.ref, [args.kind], pid)
    if c == "cv":
        return svc.prepare(args.ref, ["scholarship_cv"], pid)
    if c == "brief":
        return svc.brief(args.ref, args.kind, pid)
    if c == "save-draft":
        return svc.save_draft(args.ref, args.kind, Path(args.file).read_text(encoding="utf-8"), pid)
    if c == "documents":
        return svc.documents_audit(args.ref, pid)
    if c == "export":
        return svc.export_document(args.ref, args.kind, args.format,
                                   Path(args.out) if args.out else data_dir() / "private" / "exports", pid)
    if c == "deadlines":
        return svc.deadlines(args.days, pid, args.tracked)
    if c == "reminders":
        return svc.reminders(pid, ICSNotifier(Path(args.ics)) if args.ics else None)
    if c == "track":
        return svc.track(args.ref, args.status, args.note, args.item, args.item_status, pid)
    if c == "review":
        return svc.pre_submission_review(args.ref, pid)
    if c == "outcome":
        return svc.outcome(args.ref, args.result, args.lessons, pid)
    if c == "report":
        return svc.report(pid)
    if c == "quality":
        from .quality import evaluate
        llm = svc.extractor_llm if (args.ai or args.ai_only) else None
        if (args.ai or args.ai_only) and llm is None:
            raise ValueError("no AI extractor configured (set AI_PROVIDER=ollama|anthropic, see .env.example)")
        return _with_usage(evaluate(Path(args.fixtures) if args.fixtures else None, llm, ai_only=args.ai_only), llm)
    if c == "discovery-yield":
        return svc.discovery_yield(args.baseline)
    if c == "catalog-audit":
        return svc.catalog_audit()
    if c == "stats":
        return svc.catalog_stats()
    if c == "heldout":
        from . import heldout
        root = heldout.ROOT if args.set == "a" else heldout.ROOT.parent / f"heldout_{args.set}"
        if args.fetch:
            heldout.fetch(root, svc.fetcher)
        llm = svc.extractor_llm if args.ai else None
        if args.ai and llm is None:
            raise ValueError("no AI extractor configured (set AI_PROVIDER=ollama|anthropic, see .env.example)")
        out = _with_usage(heldout.evaluate(root, llm, split=args.split, ai_mode=args.ai_mode), llm)
        if args.set in ("c", "d"):
            from .claims_eval import evaluate_claims
            out["validator"] = evaluate_claims(root, args.split)
        return out
    if c == "compare":
        from . import heldout
        from .compare import compare
        root = heldout.ROOT if args.set == "a" else heldout.ROOT.parent / f"heldout_{args.set}"
        return compare(root, [x.strip() for x in args.providers.split(",") if x.strip()], svc.store, split=args.split)
    if c == "security-status":
        st = svc.store
        return {"crypto": st.cipher.describe(),
                "accounts": st.q("SELECT COUNT(*) n FROM users")[0]["n"],
                "active_sessions": st.q("SELECT COUNT(*) n FROM auth_tokens")[0]["n"],
                "private_db_mode": oct((st.dir / "private" / "private.db").stat().st_mode & 0o777),
                "plaintext_private_values": _plaintext_count(st)}
    if c == "encrypt-private":
        return svc.store.encrypt_private()
    if c == "ai-usage":
        return svc.ai_usage()
    if c == "translate":
        from .translate import translate_catalog
        if svc.extractor_llm is None:
            raise ValueError("no AI provider configured (set AI_PROVIDER=anthropic, see .env.example)")
        return _with_usage(translate_catalog(svc.store, svc.extractor_llm, args.limit), svc.extractor_llm)
    if c == "check":
        from .ai_check import check_catalog
        if svc.extractor_llm is None:
            raise ValueError("no AI provider configured (set AI_PROVIDER=anthropic, see .env.example)")
        return _with_usage(check_catalog(svc.store, svc.fetcher, svc.extractor_llm, svc.today, args.limit, args.refresh,
                                         args.listed), svc.extractor_llm)
    if c in ("backup", "backups", "restore"):   # round 51
        from . import backup as bk
        from .store import data_dir
        out = Path(args.out) if getattr(args, "out", None) else None
        if c == "backup":
            return bk.create(data_dir(), out, args.keep)
        if c == "backups":
            return {"backups": bk.listing(out)}
        return bk.restore(Path(args.archive), data_dir(), args.yes)
    if c == "describe":
        return svc.describe_catalog(args.limit, args.refresh, args.fetch, args.listed)
    if c == "sources":
        if args.add:
            return svc.add_source(json.loads(args.add))
        return svc.sources_status(check=args.check)
    raise ValueError(f"unknown command {c}")


def _plaintext_count(store) -> int:
    from .store import SENSITIVE
    if not store.cipher.enabled:
        return -1
    n = 0
    for table, cols in SENSITIVE.items():
        for col in cols:
            n += store.q(f"SELECT COUNT(*) n FROM {table} WHERE {col} IS NOT NULL AND {col} != '' "
                         f"AND {col} NOT LIKE 'enc1:%'")[0]["n"]
    return n


def _with_usage(result, llm):
    if llm is not None and hasattr(llm, "usage"):
        result["ai_usage"] = llm.usage()
    return result


def main(argv=None, svc: ScholarshipService | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.cmd == "new-key":
        from .crypto import new_key
        print(json.dumps({"key": new_key(), "note": "store it in your secret manager; never commit it"}))
        return 0
    if args.cmd == "serve":
        from .web import serve
        try:
            httpd = serve(args.host, args.port)
        except Exception as e:
            print(json.dumps({"error": str(e), "type": type(e).__name__}))
            return 1
        sys.stderr.write(f"serving the API on http://{args.host}:{args.port}/api/v1 (Ctrl+C to stop)\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0
    try:
        out = run(args, svc or ScholarshipService())
        rc = 0
    except (NotFound, TransitionError, ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        out, rc = {"error": str(e), "type": type(e).__name__}, 1
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
