"""Application state, checklist, document versions, deadlines and reminders."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol

from .models import ALLOWED_TRANSITIONS, AppStatus, DeadlineCertainty, stable_id
from .store import Store, now


class TransitionError(ValueError):
    pass


def application_id(profile_id: str, opp_id: str) -> str:
    return stable_id(profile_id, opp_id, prefix="app")


def ensure_application(store: Store, profile_id: str, opp_id: str) -> dict:
    aid = application_id(profile_id, opp_id)
    if not store.q("SELECT 1 FROM applications WHERE id = ?", (aid,)):
        ts = now()
        store.x("INSERT INTO applications VALUES (?,?,?,?,?,?,?)",
                (aid, profile_id, opp_id, str(AppStatus.DISCOVERED), ts, ts, ""))
        store.x("INSERT INTO status_history (application_id, from_status, to_status, at, note) VALUES (?,?,?,?,?)",
                (aid, None, str(AppStatus.DISCOVERED), ts, store.enc("created", "status_history", "note")))
    return get_application(store, aid)


def get_application(store: Store, aid: str) -> Optional[dict]:
    rows = store.q("SELECT * FROM applications WHERE id = ?", (aid,))
    if not rows:
        return None
    app = store.dec_row(rows[0], "applications")
    app["history"] = [store.dec_row(r, "status_history") for r in store.q(
        "SELECT from_status, to_status, at, note FROM status_history WHERE application_id = ? ORDER BY id", (aid,))]
    return app


def list_applications(store: Store, profile_id: str = "default") -> list[dict]:
    return [store.dec_row(r, "applications") for r in store.q(
        "SELECT * FROM applications WHERE profile_id = ? ORDER BY updated_at DESC", (profile_id,))]


def transition(store: Store, aid: str, to: str, note: str = "") -> dict:
    app = get_application(store, aid)
    if not app:
        raise TransitionError(f"no application {aid}")
    cur, new = AppStatus(app["status"]), AppStatus(to)
    if new == cur:
        return app
    if new not in ALLOWED_TRANSITIONS[cur]:
        allowed = ", ".join(sorted(str(s) for s in ALLOWED_TRANSITIONS[cur])) or "none (final state)"
        raise TransitionError(f"cannot go from {cur} to {new}; allowed: {allowed}")
    ts = now()
    store.x("UPDATE applications SET status = ?, updated_at = ? WHERE id = ?", (str(new), ts, aid))
    store.x("INSERT INTO status_history (application_id, from_status, to_status, at, note) VALUES (?,?,?,?,?)",
            (aid, str(cur), str(new), ts, store.enc(note, "status_history", "note")))
    return get_application(store, aid)


def save_checklist(store: Store, aid: str, matrix: list[dict]) -> int:
    """Upsert checklist rows; a row the user already marked done stays done."""
    n = 0
    for r in matrix:
        prev = store.q("SELECT status FROM checklist_items WHERE application_id = ? AND name = ?", (aid, r["name"]))
        status = prev[0]["status"] if prev and prev[0]["status"] == "done" else r["status"]
        store.x("INSERT INTO checklist_items (application_id, name, status, data) VALUES (?,?,?,?) "
                "ON CONFLICT(application_id, name) DO UPDATE SET status = excluded.status, data = excluded.data",
                (aid, r["name"], status, store.enc(json.dumps(r), "checklist_items", "data")))
        n += 1
    return n


def checklist(store: Store, aid: str) -> list[dict]:
    return [json.loads(store.dec(r["data"], "checklist_items", "data")) | {"status": r["status"]}
            for r in store.q("SELECT status, data FROM checklist_items WHERE application_id = ? ORDER BY id", (aid,))]


def mark_item(store: Store, aid: str, name: str, status: str) -> None:
    if status not in ("todo", "in_progress", "done", "not_applicable"):
        raise ValueError("status must be todo | in_progress | done | not_applicable")
    if not store.q("SELECT 1 FROM checklist_items WHERE application_id = ? AND name = ?", (aid, name)):
        raise ValueError(f"no checklist item '{name}' - run /plan first")
    store.x("UPDATE checklist_items SET status = ? WHERE application_id = ? AND name = ?", (status, aid, name))


# ----------------------------------------------------------------- documents

def save_document(store: Store, aid: str, kind: str, title: str, content: str, review: Optional[dict] = None) -> dict:
    rows = store.q("SELECT id, current_version FROM documents WHERE application_id = ? AND kind = ? AND title = ?",
                   (aid, kind, title))
    if rows:
        doc_id, version = rows[0]["id"], rows[0]["current_version"] + 1
        store.x("UPDATE documents SET current_version = ? WHERE id = ?", (version, doc_id))
    else:
        doc_id = store.x("INSERT INTO documents (application_id, kind, title, current_version) VALUES (?,?,?,1)",
                         (aid, kind, title))
        version = 1
    store.x("INSERT INTO document_versions (document_id, version, content, review, created_at) VALUES (?,?,?,?,?)",
            (doc_id, version, store.enc(content, "document_versions", "content"),
             store.enc(json.dumps(review), "document_versions", "review") if review else None, now()))
    return {"document_id": doc_id, "version": version, "kind": kind, "title": title}


def documents(store: Store, aid: str, latest_only: bool = True) -> list[dict]:
    sql = ("SELECT d.id, d.kind, d.title, v.version, v.content, v.review, v.created_at FROM documents d "
           "JOIN document_versions v ON v.document_id = d.id WHERE d.application_id = ?")
    if latest_only:
        sql += " AND v.version = d.current_version"
    out = []
    for r in store.q(sql + " ORDER BY d.id, v.version", (aid,)):
        d = store.dec_row(r, "document_versions")
        d["review"] = json.loads(d["review"]) if d["review"] else None
        out.append(d)
    return out


# ----------------------------------------------------------------- deadlines and reminders

def deadlines(store: Store, profile_id: str = "default", within_days: int = 90, today: Optional[date] = None,
              tracked_only: bool = False) -> dict:
    """Upcoming deadlines grouped by certainty. Expected deadlines carry their wording, never a made-up date."""
    today = today or date.today()
    tracked = {a["opportunity_id"]: a for a in list_applications(store, profile_id)}
    out = {"confirmed": [], "expected_unconfirmed": [], "unknown": [], "historical_recent": [], "urgent_tasks": []}
    for opp in store.list_opportunities():
        app = tracked.get(opp.id)
        if tracked_only and not app:
            continue
        if app and AppStatus(app["status"]) in (AppStatus.REJECTED, AppStatus.WITHDRAWN, AppStatus.EXPIRED,
                                                AppStatus.ACCEPTED):
            continue
        base = {"opportunity_id": opp.id, "title": opp.title, "application_status": app["status"] if app else None}
        if not opp.deadlines:
            out["unknown"].append(base | {"note": "no deadline on record"})
        for d in opp.deadlines:
            row = base | {"kind": str(d.kind), "date": d.date, "time": d.time, "timezone": d.timezone,
                          "cycle": d.cycle, "source": d.source_url}
            if d.certainty == DeadlineCertainty.HISTORICAL:
                if d.date and (today - date.fromisoformat(d.date)).days <= 730:
                    out["historical_recent"].append(row)
                continue
            if d.certainty == DeadlineCertainty.EXPECTED:
                out["expected_unconfirmed"].append(row | {"approximate": d.approximate})
                continue
            if not d.date:
                out["unknown"].append(row | {"note": d.approximate})
                continue
            days = (date.fromisoformat(d.date) - today).days
            if 0 <= days <= within_days:
                out["confirmed"].append(row | {"days_left": days})
        if app:
            for item in checklist(store, app["id"]):
                if item["status"] != "done" and item.get("start_by") and item["start_by"] <= (today + timedelta(days=7)).isoformat():
                    out["urgent_tasks"].append({"opportunity_id": opp.id, "title": opp.title, "task": item["name"],
                                                "start_by": item["start_by"], "deadline": item.get("deadline")})
    out["confirmed"].sort(key=lambda r: r["date"])
    out["urgent_tasks"].sort(key=lambda r: r["start_by"])
    out["as_of"] = today.isoformat()
    return out


class Notifier(Protocol):
    """Integration point for email/calendar. Implementations must not send anything without the user's approval."""
    name: str

    def deliver(self, reminders: list[dict]) -> dict: ...


class ConsoleNotifier:
    name = "console"

    def deliver(self, reminders):
        return {"delivered": len(reminders), "channel": "console", "items": reminders}


class ICSNotifier:
    """Writes an .ics calendar file the user can import. Nothing is sent anywhere."""
    name = "ics"

    def __init__(self, path: Path):
        self.path = Path(path)

    def deliver(self, reminders):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Scholarship Intelligence Agent//EN"]
        for i, r in enumerate(reminders):
            d = r["due"].replace("-", "")
            msg = r["message"].replace(",", "\\,").replace(";", "\\;")[:200]
            L += ["BEGIN:VEVENT", f"UID:sia-{d}-{i}@local", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d}",
                  f"SUMMARY:{msg}", "END:VEVENT"]
        L.append("END:VCALENDAR")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\r\n".join(L) + "\r\n", encoding="utf-8")
        return {"delivered": len(reminders), "channel": "ics", "file": str(self.path)}


def plan_reminders(store: Store, profile_id: str = "default", offsets=(30, 14, 7, 2), today: Optional[date] = None) -> list[dict]:
    """Reminders for confirmed deadlines and checklist start-by dates of tracked applications. Persisted, idempotent."""
    today = today or date.today()
    made = []
    dl = deadlines(store, profile_id, within_days=365, today=today, tracked_only=True)
    for r in dl["confirmed"]:
        aid = application_id(profile_id, r["opportunity_id"])
        for off in offsets:
            due = date.fromisoformat(r["date"]) - timedelta(days=off)
            if due >= today:
                made.append({"application_id": aid, "due": due.isoformat(),
                             "message": f"{r['title']}: {r['kind']} deadline in {off} days ({r['date']})"})
    for t in dl["urgent_tasks"]:
        made.append({"application_id": application_id(profile_id, t["opportunity_id"]),
                     "due": max(t["start_by"], today.isoformat()), "message": f"{t['title']}: start '{t['task']}'"})
    for m in made:
        if not store.q("SELECT 1 FROM reminders WHERE application_id = ? AND due = ? AND message = ?",
                       (m["application_id"], m["due"], m["message"])):
            store.x("INSERT INTO reminders (application_id, due, message, channel) VALUES (?,?,?,?)",
                    (m["application_id"], m["due"], m["message"], "pending"))
    return sorted(made, key=lambda m: m["due"])


def record_outcome(store: Store, aid: str, result: str, lessons: str = "") -> dict:
    status = {"accepted": AppStatus.ACCEPTED, "rejected": AppStatus.REJECTED, "withdrawn": AppStatus.WITHDRAWN,
              "expired": AppStatus.EXPIRED, "interview": AppStatus.ASSESSMENT, "waitlisted": AppStatus.AWAITING_DECISION}
    if result not in status:
        raise ValueError(f"result must be one of {sorted(status)}")
    app = transition(store, aid, str(status[result]), note=f"outcome: {result}")
    if status[result] in (AppStatus.ACCEPTED, AppStatus.REJECTED, AppStatus.WITHDRAWN, AppStatus.EXPIRED):
        store.x("INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?)", (aid, result, store.enc(lessons, "outcomes", "lessons"), now()))
    return app | {"lessons": lessons}


def lessons(store: Store, profile_id: Optional[str] = None) -> list[dict]:
    """Outcomes and lessons; with a profile id only that applicant's (round 46: a multi-user service must not show
    one user's lessons to another)."""
    if profile_id is None:
        rows = store.q("SELECT * FROM outcomes ORDER BY at DESC")
    else:
        rows = store.q("SELECT o.* FROM outcomes o JOIN applications a ON a.id = o.application_id WHERE a.profile_id = ? "
                       "ORDER BY o.at DESC", (profile_id,))
    return [store.dec_row(r, "outcomes") for r in rows]
