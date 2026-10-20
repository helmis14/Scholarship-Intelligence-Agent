"""SQLite persistence with forward-only migrations.

Two files, on purpose:
  catalog.db  public scholarship information (shareable, could seed a website)
  private.db  applicant profile, applications, generated documents (never shared)

The location defaults to <repo>/data and is overridable with SCHOLAR_DATA_DIR.
Both are gitignored. private.db is created 0600 inside a 0700 directory.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import Opportunity, Profile

ROOT = Path(__file__).resolve().parent.parent


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def data_dir() -> Path:
    return Path(os.environ.get("SCHOLAR_DATA_DIR") or ROOT / "data")


CATALOG_MIGRATIONS = [
    """
    CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT, country TEXT, data TEXT);
    CREATE TABLE institutions (id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT, data TEXT);
    CREATE TABLE opportunities (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, provider_name TEXT, dedup_key TEXT, info_url_norm TEXT,
        countries TEXT, verification_status TEXT, last_verified_at TEXT, data TEXT NOT NULL,
        created_at TEXT, updated_at TEXT);
    CREATE INDEX opp_dedup ON opportunities(dedup_key);
    CREATE INDEX opp_url ON opportunities(info_url_norm);
    CREATE TABLE deadlines (
        opportunity_id TEXT NOT NULL, kind TEXT, certainty TEXT, date TEXT, cycle TEXT, data TEXT);
    CREATE INDEX dl_date ON deadlines(date);
    CREATE TABLE deadline_history (
        opportunity_id TEXT NOT NULL, kind TEXT, date TEXT, cycle TEXT, recorded_at TEXT, data TEXT);
    CREATE TABLE verification_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL, run_at TEXT, outcome TEXT, data TEXT);
    CREATE TABLE source_state (
        source_id TEXT PRIMARY KEY, last_checked TEXT, last_ok TEXT, last_status TEXT,
        consecutive_failures INTEGER DEFAULT 0, last_error TEXT);
    CREATE TABLE pages (
        url TEXT PRIMARY KEY, fetched_at TEXT, http_status INTEGER, sha256 TEXT, content_type TEXT, text TEXT);
    CREATE TABLE search_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, started_at TEXT, finished_at TEXT, params TEXT,
        status TEXT, stats TEXT);
    CREATE TABLE ingestion_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, url TEXT, outcome TEXT, error TEXT,
        opportunity_id TEXT, at TEXT);
    """,
    """
    CREATE TABLE search_queries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT, query TEXT, country TEXT, category TEXT, lang TEXT,
        page INTEGER, run_at TEXT, n_results INTEGER, error TEXT, job_id INTEGER);
    CREATE INDEX sq_lookup ON search_queries(provider, query, page);
    CREATE TABLE search_results (
        query_id INTEGER, rank INTEGER, url TEXT, title TEXT, snippet TEXT);
    CREATE TABLE discovered_urls (
        url_norm TEXT PRIMARY KEY, url TEXT, first_seen TEXT, last_seen TEXT, times_seen INTEGER, country TEXT,
        category TEXT, via TEXT, status TEXT, opportunity_id TEXT, error TEXT);
    CREATE TABLE provider_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT, query TEXT, run_at TEXT, ok INTEGER, n_results INTEGER,
        urls TEXT, error TEXT);
    """,
    """
    CREATE TABLE llm_cache (key TEXT PRIMARY KEY, model TEXT, response TEXT, at TEXT);
    CREATE TABLE llm_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT, model TEXT, at TEXT, status TEXT,
        input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cost_usd REAL, request_id TEXT);
    """,
    """
    ALTER TABLE llm_usage ADD COLUMN latency_ms REAL;
    """,
    """
    ALTER TABLE discovered_urls ADD COLUMN lang TEXT;
    ALTER TABLE discovered_urls ADD COLUMN method TEXT;
    ALTER TABLE discovered_urls ADD COLUMN page_lang TEXT;
    ALTER TABLE discovered_urls ADD COLUMN retrieval TEXT;
    ALTER TABLE llm_usage ADD COLUMN purpose TEXT;
    ALTER TABLE llm_usage ADD COLUMN fields TEXT;
    ALTER TABLE llm_usage ADD COLUMN source_url TEXT;
    ALTER TABLE pages ADD COLUMN final_url TEXT;
    ALTER TABLE pages ADD COLUMN method TEXT;
    CREATE TABLE provider_candidates (
        domain TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT, times_seen INTEGER, countries TEXT, sample_urls TEXT,
        signals TEXT, status TEXT, reviewed_at TEXT, note TEXT);
    CREATE TABLE job_checkpoints (job_id INTEGER PRIMARY KEY, position INTEGER, updated_at TEXT, data TEXT);
    """,
    """
    CREATE TABLE engine_health (engine TEXT PRIMARY KEY, kind TEXT, reason TEXT, until REAL, ok INTEGER, failed INTEGER,
        last_ok TEXT);
    """,
    # round 38: "report a mistake". Public data only: no profile id, no contact details.
    """
    CREATE TABLE issue_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL, field TEXT NOT NULL, shown_value TEXT,
        note TEXT, at TEXT, status TEXT NOT NULL DEFAULT 'open', resolution TEXT);
    CREATE INDEX issue_reports_opp ON issue_reports (opportunity_id, status);
    """,
]

PRIVATE_MIGRATIONS = [
    """
    CREATE TABLE profiles (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT);
    CREATE TABLE profile_history (id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT, data TEXT, at TEXT);
    CREATE TABLE applications (
        id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, opportunity_id TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT, updated_at TEXT, notes TEXT, UNIQUE(profile_id, opportunity_id));
    CREATE TABLE status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT, from_status TEXT, to_status TEXT, at TEXT, note TEXT);
    CREATE TABLE checklist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT, name TEXT, status TEXT, data TEXT,
        UNIQUE(application_id, name));
    CREATE TABLE documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT, kind TEXT, title TEXT, current_version INTEGER,
        UNIQUE(application_id, kind, title));
    CREATE TABLE document_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER, version INTEGER, content TEXT, review TEXT,
        created_at TEXT);
    CREATE TABLE reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT, due TEXT, message TEXT, channel TEXT,
        sent_at TEXT);
    CREATE TABLE outcomes (application_id TEXT PRIMARY KEY, result TEXT, lessons TEXT, at TEXT);
    """,
]


def _migrate(conn: sqlite3.Connection, migrations: list[str]) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] or 0
    for version, sql in enumerate(migrations, start=1):
        if version <= current:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


def _connect(path: Path, private: bool) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if private:
        os.chmod(path.parent, 0o700)
        if not path.exists():
            path.touch(mode=0o600)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


class Store:
    def __init__(self, directory: Optional[Path] = None):
        d = Path(directory) if directory else data_dir()
        self.dir = d
        self.catalog = _connect(d / "catalog.db", private=False)
        self.private = _connect(d / "private" / "private.db", private=True)
        _migrate(self.catalog, CATALOG_MIGRATIONS)
        _migrate(self.private, PRIVATE_MIGRATIONS)

    def close(self) -> None:
        self.catalog.close()
        self.private.close()

    # ----------------------------------------------------------------- issue reports

    def add_issue_report(self, opportunity_id: str, field: str, shown_value: str, note: str) -> int:
        with self.catalog as c:
            cur = c.execute("INSERT INTO issue_reports (opportunity_id, field, shown_value, note, at) VALUES (?,?,?,?,?)",
                            (opportunity_id, field, shown_value, note, now()))
            return int(cur.lastrowid)

    def issue_reports(self, status: str = "open", opportunity_id: str = "") -> list[dict]:
        q, args = "SELECT * FROM issue_reports WHERE 1=1", []
        if status:
            q += " AND status = ?"; args.append(status)
        if opportunity_id:
            q += " AND opportunity_id = ?"; args.append(opportunity_id)
        return [dict(r) for r in self.catalog.execute(q + " ORDER BY id", args)]

    def resolve_issue_report(self, report_id: int, status: str, resolution: str) -> bool:
        with self.catalog as c:
            return c.execute("UPDATE issue_reports SET status = ?, resolution = ? WHERE id = ?",
                             (status, resolution[:500], report_id)).rowcount > 0

    # ---------------------------------------------------------- opportunities

    def save_opportunity(self, opp: Opportunity, dedup_key: str, url_norm: str) -> None:
        ts = now()
        opp.updated_at = ts
        opp.created_at = opp.created_at or ts
        from .audit import field_status
        opp.field_status = field_status(opp)
        previous = self.get_opportunity(opp.id)
        with self.catalog as c:
            c.execute(
                """INSERT INTO opportunities (id, title, provider_name, dedup_key, info_url_norm, countries,
                       verification_status, last_verified_at, data, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, provider_name=excluded.provider_name,
                       dedup_key=excluded.dedup_key, info_url_norm=excluded.info_url_norm,
                       countries=excluded.countries, verification_status=excluded.verification_status,
                       last_verified_at=excluded.last_verified_at, data=excluded.data,
                       updated_at=excluded.updated_at""",
                (opp.id, opp.title, opp.provider_name, dedup_key, url_norm, json.dumps(opp.destination_countries),
                 str(opp.verification_status), opp.last_verified_at, json.dumps(opp.to_dict()),
                 opp.created_at, opp.updated_at))
            # Deadlines that disappear or change are kept as history, never dropped.
            if previous:
                new = {(str(d.kind), d.date, d.cycle) for d in opp.deadlines}
                for d in previous.deadlines:
                    if d.date and (str(d.kind), d.date, d.cycle) not in new:
                        c.execute("INSERT INTO deadline_history VALUES (?,?,?,?,?,?)",
                                  (opp.id, str(d.kind), d.date, d.cycle, ts, json.dumps(d.to_dict())))
            c.execute("DELETE FROM deadlines WHERE opportunity_id = ?", (opp.id,))
            c.executemany("INSERT INTO deadlines VALUES (?,?,?,?,?,?)",
                          [(opp.id, str(d.kind), str(d.certainty), d.date, d.cycle, json.dumps(d.to_dict()))
                           for d in opp.deadlines])
            c.execute("INSERT INTO providers (id, name, type, data) VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING",
                      (opp.provider_name.strip().lower(), opp.provider_name, str(opp.provider_type), "{}"))
            if opp.institution:
                c.execute("INSERT INTO institutions (id, name, country, data) VALUES (?,?,?,?) "
                          "ON CONFLICT(id) DO NOTHING",
                          (opp.institution.strip().lower(), opp.institution,
                           (opp.destination_countries or [""])[0], "{}"))

    def get_opportunity(self, opp_id: str) -> Optional[Opportunity]:
        row = self.catalog.execute("SELECT data FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        return Opportunity.from_dict(json.loads(row["data"])) if row else None

    def find_opportunity(self, ref: str) -> Optional[Opportunity]:
        """Lookup by id, id prefix, or a unique case-insensitive title fragment."""
        opp = self.get_opportunity(ref)
        if opp:
            return opp
        rows = self.catalog.execute(
            "SELECT data FROM opportunities WHERE id LIKE ? OR lower(title) LIKE ?",
            (ref + "%", "%" + ref.lower() + "%")).fetchall()
        return Opportunity.from_dict(json.loads(rows[0]["data"])) if len(rows) == 1 else None

    def find_by_dedup(self, dedup_key: str, url_norm: str) -> Optional[Opportunity]:
        row = self.catalog.execute(
            "SELECT data FROM opportunities WHERE dedup_key = ? OR (info_url_norm = ? AND ? != '') LIMIT 1",
            (dedup_key, url_norm, url_norm)).fetchone()
        return Opportunity.from_dict(json.loads(row["data"])) if row else None

    def list_opportunities(self) -> list[Opportunity]:
        return [Opportunity.from_dict(json.loads(r["data"]))
                for r in self.catalog.execute("SELECT data FROM opportunities ORDER BY title")]

    def deadline_history(self, opp_id: str) -> list[dict]:
        return [json.loads(r["data"]) | {"recorded_at": r["recorded_at"]} for r in self.catalog.execute(
            "SELECT data, recorded_at FROM deadline_history WHERE opportunity_id = ? ORDER BY recorded_at", (opp_id,))]

    def add_verification(self, opp_id: str, outcome: str, data: dict) -> None:
        with self.catalog as c:
            c.execute("INSERT INTO verification_records (opportunity_id, run_at, outcome, data) VALUES (?,?,?,?)",
                      (opp_id, now(), outcome, json.dumps(data)))

    def verifications(self, opp_id: str) -> list[dict]:
        return [dict(r) | {"data": json.loads(r["data"])} for r in self.catalog.execute(
            "SELECT run_at, outcome, data FROM verification_records WHERE opportunity_id = ? ORDER BY id", (opp_id,))]

    # ---------------------------------------------------------- pages / sources / jobs

    def cache_page(self, url: str, status: int, sha: str, ctype: str, text: str, final_url: str = "",
                   method: str = "") -> None:
        with self.catalog as c:
            c.execute("INSERT OR REPLACE INTO pages (url, fetched_at, http_status, sha256, content_type, text, final_url, "
                      "method) VALUES (?,?,?,?,?,?,?,?)", (url, now(), status, sha, ctype, text, final_url or None,
                                                          method or None))

    def cached_page(self, url: str) -> Optional[sqlite3.Row]:
        return self.catalog.execute("SELECT * FROM pages WHERE url = ?", (url,)).fetchone()

    def record_source(self, source_id: str, ok: bool, status: str, error: str = "") -> None:
        ts = now()
        with self.catalog as c:
            c.execute("""INSERT INTO source_state VALUES (?,?,?,?,?,?)
                         ON CONFLICT(source_id) DO UPDATE SET last_checked=excluded.last_checked,
                           last_ok=COALESCE(excluded.last_ok, source_state.last_ok), last_status=excluded.last_status,
                           consecutive_failures=CASE WHEN ? THEN 0 ELSE source_state.consecutive_failures + 1 END,
                           last_error=excluded.last_error""",
                      (source_id, ts, ts if ok else None, status, 0 if ok else 1, error, ok))

    def source_states(self) -> dict[str, dict]:
        return {r["source_id"]: dict(r) for r in self.catalog.execute("SELECT * FROM source_state")}

    def start_job(self, kind: str, params: dict) -> int:
        with self.catalog as c:
            cur = c.execute("INSERT INTO search_jobs (kind, started_at, params, status) VALUES (?,?,?,?)",
                            (kind, now(), json.dumps(params), "running"))
            return cur.lastrowid

    def finish_job(self, job_id: int, status: str, stats: dict) -> None:
        with self.catalog as c:
            c.execute("UPDATE search_jobs SET finished_at=?, status=?, stats=? WHERE id=?",
                      (now(), status, json.dumps(stats), job_id))

    def record_ingestion(self, job_id: int, url: str, outcome: str, error: str = "", opp_id: str = "") -> None:
        with self.catalog as c:
            c.execute("INSERT INTO ingestion_results (job_id, url, outcome, error, opportunity_id, at) "
                      "VALUES (?,?,?,?,?,?)", (job_id, url, outcome, error, opp_id, now()))

    def jobs(self, limit: int = 10) -> list[dict]:
        return [dict(r) for r in self.catalog.execute("SELECT * FROM search_jobs ORDER BY id DESC LIMIT ?", (limit,))]

    def ingestion(self, job_id: int) -> list[dict]:
        return [dict(r) for r in self.catalog.execute("SELECT * FROM ingestion_results WHERE job_id=?", (job_id,))]

    # ---------------------------------------------------------- search log

    def last_query_run(self, provider: str, query: str, page: int) -> Optional[sqlite3.Row]:
        # an empty answer is not reused: with metasearch it usually means the upstream engines were throttled
        return self.catalog.execute("SELECT * FROM search_queries WHERE provider=? AND query=? AND page=? AND error IS NULL "
                                    "AND n_results > 0 ORDER BY id DESC LIMIT 1", (provider, query, page)).fetchone()

    def log_query(self, provider: str, q: dict, page: int, hits: list, error: str = "", job_id: int = 0) -> int:
        with self.catalog as c:
            cur = c.execute("INSERT INTO search_queries (provider, query, country, category, lang, page, run_at, n_results, "
                            "error, job_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (provider, q["query"], q.get("country"), q.get("category"), q.get("language"), page, now(),
                             len(hits), error or None, job_id))
            qid = cur.lastrowid
            c.executemany("INSERT INTO search_results VALUES (?,?,?,?,?)",
                          [(qid, i, h.url, h.title[:300], h.snippet[:500]) for i, h in enumerate(hits)])
            return qid

    def cached_results(self, query_id: int) -> list[sqlite3.Row]:
        return self.catalog.execute("SELECT * FROM search_results WHERE query_id=? ORDER BY rank", (query_id,)).fetchall()

    def see_url(self, url_norm: str, url: str, country: str, category: str, via: str, lang: str = "",
                method: str = "") -> bool:
        """Record a discovered URL with the query language and discovery method; True when it is new."""
        ts = now()
        row = self.catalog.execute("SELECT times_seen FROM discovered_urls WHERE url_norm=?", (url_norm,)).fetchone()
        with self.catalog as c:
            if row:
                c.execute("UPDATE discovered_urls SET last_seen=?, times_seen=times_seen+1 WHERE url_norm=?", (ts, url_norm))
                return False
            c.execute("INSERT INTO discovered_urls (url_norm, url, first_seen, last_seen, times_seen, country, category, via, "
                      "status, opportunity_id, error, lang, method) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (url_norm, url, ts, ts, 1, country, category, via, "new", None, None, lang or None, method or None))
            return True

    def pending_urls(self, limit: int) -> list[sqlite3.Row]:
        """URLs discovered but never fetched (an interrupted run leaves them "new"), oldest first."""
        return self.catalog.execute("SELECT * FROM discovered_urls WHERE status='new' ORDER BY first_seen LIMIT ?",
                                    (limit,)).fetchall()

    def note_retrieval(self, url_norm: str, page_lang: str, retrieval: str) -> None:
        with self.catalog as c:
            c.execute("UPDATE discovered_urls SET page_lang=?, retrieval=? WHERE url_norm=?",
                      (page_lang or None, retrieval or None, url_norm))

    def checkpoint(self, job_id: int, position: int, data: Optional[dict] = None) -> None:
        with self.catalog as c:
            c.execute("INSERT OR REPLACE INTO job_checkpoints VALUES (?,?,?,?)",
                      (job_id, position, now(), json.dumps(data or {})))

    def get_checkpoint(self, job_id: int) -> Optional[sqlite3.Row]:
        return self.catalog.execute("SELECT * FROM job_checkpoints WHERE job_id=?", (job_id,)).fetchone()

    def job(self, job_id: int) -> Optional[dict]:
        r = self.catalog.execute("SELECT * FROM search_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    def mark_url(self, url_norm: str, status: str, opp_id: str = "", error: str = "") -> None:
        with self.catalog as c:
            c.execute("UPDATE discovered_urls SET status=?, opportunity_id=?, error=? WHERE url_norm=?",
                      (status, opp_id or None, error or None, url_norm))

    def log_provider_check(self, provider: str, query: str, ok: bool, urls: list[str], error: str = "") -> None:
        import json as _j
        with self.catalog as c:
            c.execute("INSERT INTO provider_checks (provider, query, run_at, ok, n_results, urls, error) VALUES (?,?,?,?,?,?,?)",
                      (provider, query, now(), int(ok), len(urls), _j.dumps(urls), error or None))

    def provider_checks(self, limit: int = 5) -> list[dict]:
        return [dict(r) for r in self.catalog.execute("SELECT * FROM provider_checks ORDER BY id DESC LIMIT ?", (limit,))]

    # ---------------------------------------------------------- profiles

    def save_profile(self, profile: Profile) -> None:
        profile.updated_at = now()
        data = json.dumps(profile.to_dict())
        with self.private as c:
            c.execute("INSERT INTO profiles VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, "
                      "updated_at=excluded.updated_at", (profile.id, data, profile.updated_at))
            c.execute("INSERT INTO profile_history (profile_id, data, at) VALUES (?,?,?)",
                      (profile.id, data, profile.updated_at))

    def get_profile(self, profile_id: str = "default") -> Optional[Profile]:
        row = self.private.execute("SELECT data FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return Profile.from_dict(json.loads(row["data"])) if row else None

    # ---------------------------------------------------------- generic private helpers

    def q(self, sql: str, args: Iterable = ()) -> list[sqlite3.Row]:
        return self.private.execute(sql, tuple(args)).fetchall()

    def x(self, sql: str, args: Iterable = ()) -> int:
        with self.private as c:
            return c.execute(sql, tuple(args)).lastrowid
