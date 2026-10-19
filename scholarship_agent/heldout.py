"""Held-out accuracy evaluation on real pages (tests/heldout).

Separate from the development fixtures in quality.py: these pages were labelled from the page text and
were not used to tune the rules. Snapshots live in tests/heldout/pages (gitignored - third-party
content); `heldout-fetch` re-downloads them, and labels.json records what each page actually states.

Metrics:
  per field group      precision / recall / F1 (sets of values)
  deadline_exact       gold closing dates found exactly / gold closing dates
  deadline_status      correct current-vs-historical among matched dates
  nationality          exact rule match (mode + countries) among labelled pages, incl. "not stated"
  funding_amount       stipend/award amount AND currency correct among labelled pages
  age                  min/max interpretation correct (incl. "not stated") among labelled values
  page_kind            opportunity vs listing/news/unreadable classification
  attribution          share of evidence snippets that are verbatim on the page they cite
  unsupported_rate     extracted values where the label says the page does not state it, or the
                       value is not among the accepted ones / all scored extracted values
  missing_rate         labelled values the extractor left empty / all labelled values
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from .extract import Page, extract_opportunity, page_kind
from .models import DeadlineCertainty, DeadlineKind, ProviderType, SourceType
from .pdf import pdf_text

ROOT = Path(__file__).resolve().parent.parent / "tests" / "heldout"


def _fold(s: str) -> str:
    return " ".join((s or "").lower().split())


def load_page(pid: str, url: str, root: Path) -> Optional[Page]:
    files = list((root / "pages").glob(f"{pid}.*"))
    if not files:
        return None
    f = files[0]
    if f.suffix == ".pdf":
        text, status = pdf_text(f.read_bytes())
        p = Page.from_text(url, text)
        p.pdf_status = status
        return p
    return Page(url, f.read_text(encoding="utf-8"))


class Tally:
    def __init__(self):
        self.c: dict[str, list[int]] = {}

    def add(self, key: str, ok: bool):
        t = self.c.setdefault(key, [0, 0])
        t[0] += int(ok)
        t[1] += 1

    def rate(self, key: str):
        ok, n = self.c.get(key, [0, 0])
        return {"correct": ok, "total": n, "accuracy": round(ok / n, 3) if n else None}


def evaluate(root: Optional[Path] = None, llm=None, today: Optional[date] = None, split: Optional[str] = None,
             ai_mode: str = "full") -> dict:
    root = Path(root or ROOT)
    labels = json.loads((root / "labels.json").read_text(encoding="utf-8"))
    url_rows = json.loads((root / "urls.json").read_text(encoding="utf-8"))["pages"]
    urls = {p["id"]: p["url"] for p in url_rows}
    if split:
        keep = {p["id"] for p in url_rows if p.get("split") == split}
        labels = dict(labels, pages={k: v for k, v in labels["pages"].items() if k in keep})
    today = today or date.fromisoformat(labels.get("today", "2026-10-17"))
    T = Tally()
    sets: dict[str, list[int]] = {}           # field -> [tp, fp, fn]
    unsupported = scored_values = missing = labelled_values = 0
    attr_ok = attr_n = 0
    per_page = {}
    skipped = []
    ai = {"pages": 0, "proposed": 0, "accepted": 0, "rejected_by_reason": {}, "needs_review_by_reason": {}, "disagreements_with_rules": 0,
          "errors": {}, "evidence_verbatim": 0, "evidence_total": 0}

    def setcmp(field, got: set, exp: set):
        t = sets.setdefault(field, [0, 0, 0])
        t[0] += len(got & exp)
        t[1] += len(got - exp)
        t[2] += len(exp - got)

    for pid, lab in labels["pages"].items():
        page = load_page(pid, urls.get(pid, ""), root)
        if page is None:
            skipped.append(pid)
            continue
        misses: list[str] = []
        kind_pred = "unreadable" if page.pdf_status and not page.text else page_kind(page)[0]
        kind_ok = (kind_pred == "opportunity") == (lab["kind"] == "opportunity") if lab["kind"] != "unreadable" \
            else kind_pred == "unreadable"
        T.add("page_kind", kind_ok)
        if not kind_ok:
            misses.append(f"page_kind: predicted {kind_pred}, label {lab['kind']}")
        if lab["kind"] != "opportunity":
            per_page[pid] = misses
            continue
        opp, _ = extract_opportunity(page, provider_name="heldout", provider_type=ProviderType.OTHER,
                                     source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="2026-10-17T00:00:00+00:00",
                                     today=today)
        if llm is not None:
            from .ai_extract import enrich
            st = enrich(opp, page.text, llm, source_type=SourceType.OFFICIAL, retrieved_at="2026-10-17T00:00:00+00:00",
                        today=today, mode=ai_mode)
            ai["pages"] += 1
            ai["proposed"] += st["proposed"]
            ai["accepted"] += len(st["accepted"])
            for r in st["rejected"]:
                ai["rejected_by_reason"][r["reason"]] = ai["rejected_by_reason"].get(r["reason"], 0) + 1
            for r in st.get("needs_review", []):
                ai["needs_review_by_reason"][r["reason"]] = ai["needs_review_by_reason"].get(r["reason"], 0) + 1
            ai["disagreements_with_rules"] += len(st["disagreements"])
            if st.get("error"):
                kind = st["error"].split(":", 1)[0]
                ai["errors"][kind] = ai["errors"].get(kind, 0) + 1
        body = _fold(page.text)
        for e in opp.evidence:
            if e.verdict == "needs_review":
                continue   # sent to a person, not stored as a claim
            if e.snippet and not e.snippet.startswith("JSON-LD") and e.field != "title":  # titles come from <head>
                attr_n += 1
                found = _fold(e.snippet)[:100] in body
                attr_ok += found
                if e.note.startswith("ai-assisted"):
                    ai["evidence_total"] += 1
                    ai["evidence_verbatim"] += found
        F = lab.get("fields", {})

        # deadlines and openings
        if "deadlines" in F:
            gold = {d["date"]: d for d in F["deadlines"]}
            # applicant deadlines only: a date correctly typed as an institution's or an event's is not a deadline
            pred = {d.date: d for d in opp.deadlines if d.date and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)}
            setcmp("deadlines", set(pred), set(gold))
            for g in gold:
                T.add("deadline_exact", g in pred)
                labelled_values += 1
                if g not in pred:
                    missing += 1
                    misses.append(f"deadline missed {g}")
                else:
                    want_hist = gold[g]["status"] == "historical"
                    T.add("deadline_status", (pred[g].certainty == DeadlineCertainty.HISTORICAL) == want_hist)
            for p in set(pred) - set(gold):
                unsupported += 1
                misses.append(f"deadline spurious {p}")
            scored_values += len(pred)
        if "openings" in F:
            pred_o = {d.date for d in opp.deadlines if d.date and d.kind == DeadlineKind.OPENING}
            setcmp("openings", pred_o, set(F["openings"]))
        # nationality
        if "nationality" in F:
            g = F["nationality"]
            pm, pc = opp.nationality.mode, set(opp.nationality.countries)
            if g == "not_stated":
                ok = pm == "unknown"
                if not ok:
                    unsupported += 1
                    scored_values += 1
            else:
                labelled_values += 1
                ok = pm == g["mode"] and (g["mode"] == "any" or pc == set(g["countries"]))
                if pm == "unknown":
                    missing += 1
                else:
                    scored_values += 1
                    if not ok:
                        unsupported += 1
                if g["mode"] in ("include", "exclude"):
                    setcmp("nationality_countries", pc if pm == g["mode"] else set(), set(g["countries"]))
            T.add("nationality", ok)
            if not ok:
                misses.append(f"nationality: predicted {pm} {sorted(pc)[:6]}, label {g if g == 'not_stated' else (g['mode'], g['countries'][:6])}")
        # ages
        for k in ("min_age", "max_age"):
            if k in F:
                g, p = F[k], getattr(opp, k)
                if g == "not_stated":
                    ok = p is None
                    if not ok:
                        unsupported += 1
                        scored_values += 1
                else:
                    acc = g if isinstance(g, list) else [g]
                    labelled_values += 1
                    ok = p in acc
                    if p is None:
                        missing += 1
                    else:
                        scored_values += 1
                        unsupported += not ok
                T.add("age", ok)
                if not ok:
                    misses.append(f"{k}: predicted {p}, label {g}")
        if "provider" in F:
            # funder / provider identity (Claude's provider_name answer; rules do not extract it)
            prov = F["provider"]
            want = _fold(prov["name"] if isinstance(prov, dict) else prov)   # set C labels give the name only
            got = _fold(opp.institution or "")
            labelled_values += 1
            ok = bool(got) and (want in got or got in want)
            T.add("funder_identity", ok)
            # the same with sourced aliases (acronym the page defines, org_aliases.json); unsupported stays strict
            from .org_names import same_org
            T.add("funder_identity_alias", ok or same_org(prov["name"] if isinstance(prov, dict) else prov,
                                                          opp.institution or "", page.text))
            if not got:
                missing += 1
            else:
                scored_values += 1
                unsupported += not ok
                if not ok:
                    misses.append(f"funder: predicted {opp.institution!r}, label {prov['name'] if isinstance(prov, dict) else prov!r}")
        if "cycle" in F and F["cycle"] != "not_stated":
            want_y = set(re.findall(r"20\d{2}", F["cycle"]))
            got_c = opp.current_cycle or ""
            got_y = set(re.findall(r"20\d{2}", got_c))
            m = re.search(r"(20\d{2})\s?[/–-]\s?(\d{2,4})", got_c)
            if m:
                got_y = {m.group(1), m.group(2) if len(m.group(2)) == 4 else m.group(1)[:2] + m.group(2)}
            labelled_values += 1
            ok = bool(got_y) and got_y == want_y
            T.add("cycle", ok)
            if not got_c:
                missing += 1
            else:
                scored_values += 1
                unsupported += not ok
                if not ok:
                    misses.append(f"cycle: predicted {got_c!r}, label {F['cycle']!r}")
        if "stipend_by_level" in F:
            # amounts differ by level: one stored amount is a collapse
            collapsed = any(c.amount is not None for c in opp.funding if c.kind in ("stipend", "living_allowance"))
            T.add("per_level_amount_not_collapsed", not collapsed)
            if collapsed:
                unsupported += 1
                scored_values += 1
                misses.append("stipend amounts differ by level but one amount was stored")
        if "components" in F:
            # each benefit separately: a separate covered component only when the page says it is provided
            covered = {("living_allowance" if c.kind == "stipend" else c.kind) for c in opp.funding if c.covered}
            for kind, want in F["components"].items():
                provided = want in ("covered", "full")
                got = kind in covered
                T.add("funding_components", got == provided)
                if provided:
                    labelled_values += 1
                    missing += not got
                if got:
                    scored_values += 1
                    unsupported += not provided
                if got != provided:
                    misses.append(f"component {kind}: predicted {'covered' if got else 'not covered'}, label {want}")
        if "age_by_level" in F:
            # level-specific limits must be kept per level; one number for all levels is a collapse
            got = {d["level"]: {k: d[k] for k in ("max", "min") if k in d} for d in opp.age_limits}
            want = F["age_by_level"]
            labelled_values += 1
            ok = got == want
            T.add("age_by_level", ok)
            if not got:
                missing += 1
                if opp.max_age is not None or opp.min_age is not None:
                    unsupported += 1
                    scored_values += 1
                    misses.append(f"age collapsed to one number: max {opp.max_age} min {opp.min_age}")
            else:
                scored_values += 1
                unsupported += not ok
            if not ok and got:
                misses.append(f"age by level: predicted {got}, label {want}")
        # funding
        # a living allowance paid to the scholar is the stipend for scoring purposes
        cands = [c for c in opp.funding if c.kind in ("stipend", "living_allowance")]
        st = next((c for c in cands if c.amount is not None), cands[0] if cands else None)
        if "stipend" in F:
            g = F["stipend"]
            if g == "not_stated":
                ok = st is None or st.amount is None
                if st is not None and st.amount is not None:
                    unsupported += 1
                    scored_values += 1
                T.add("funding_amount", ok)
            else:
                labelled_values += 1
                present = st is not None
                if not present:
                    missing += 1
                T.add("stipend_present", present)
                if g["amount"]:
                    ok = present and st.amount in g["amount"] and (st.currency == g["currency"])
                    T.add("funding_amount", ok)
                    if present and st.amount is not None:
                        scored_values += 1
                        unsupported += not ok
                    if not ok:
                        misses.append(f"stipend: predicted {st.amount if st else None} {st.currency if st else ''}, label {g}")
                    if ok and g.get("period"):
                        T.add("funding_period", st.period == g["period"])
        if "award_amount" in F:
            g = F["award_amount"]
            amounts = {(c.amount, c.currency) for c in opp.funding if c.amount is not None}
            ok = any(a in g["amount"] and (cur == g["currency"] or cur is None) for a, cur in amounts)
            labelled_values += 1
            if not amounts:
                missing += 1
            T.add("funding_amount", ok)
            if not ok:
                misses.append(f"award amount: predicted {sorted(amounts, key=str)[:3]}, label {g}")
        if "tuition" in F:
            g = F["tuition"]
            t = next((c for c in opp.funding if c.kind == "tuition" and c.covered is not False), None)
            if g == "not_stated":
                ok = t is None
                if t:
                    unsupported += 1
                    scored_values += 1
            else:
                labelled_values += 1
                ok = t is not None and (g != "full" or bool(t.full))
                if t is None:
                    missing += 1
                else:
                    scored_values += 1
            T.add("tuition", ok)
            if not ok:
                misses.append(f"tuition: predicted {(t.full if t else None)}, label {g}")
        if "travel" in F:
            T.add("travel", any(c.kind == "travel" and c.covered for c in opp.funding) == F["travel"])
        # language
        if "language" in F:
            g = F["language"]
            pred = {r.test: r.minimum for r in opp.language_requirements}
            if g == "not_stated":
                T.add("language", not pred)
                if pred:
                    unsupported += len(pred)
                    scored_values += len(pred)
            else:
                for test, acc in g.items():
                    labelled_values += 1
                    ok = test in pred and pred[test] in acc
                    T.add("language", ok)
                    if test not in pred:
                        missing += 1
                    if not ok:
                        misses.append(f"language {test}: predicted {pred.get(test)}, label {acc}")
                for test in set(pred) - set(g):
                    unsupported += 1
                scored_values += len(pred)
        if "levels" in F:
            setcmp("levels", set(opp.study_levels), set(F["levels"]))
        if "documents" in F:
            got = {d.name for d in opp.required_documents} - {"Language test certificate", "MOI letter"}
            setcmp("documents", got, set(F["documents"]))
        if "duration_months_max" in F:
            m = re.findall(r"\d+", opp.funding_duration or "")
            unit = 12 if "year" in (opp.funding_duration or "") else 1
            got = max((int(x) * unit for x in m), default=None)
            T.add("duration", got == F["duration_months_max"])
            if got != F["duration_months_max"]:
                misses.append(f"duration: predicted {opp.funding_duration!r}, label {F['duration_months_max']} months")
        per_page[pid] = misses

    fields = {}
    for f, (tp, fp, fn) in sorted(sets.items()):
        p = tp / (tp + fp) if tp + fp else None
        r = tp / (tp + fn) if tp + fn else None
        fields[f] = {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3) if p is not None else None,
                     "recall": round(r, 3) if r is not None else None,
                     "f1": round(2 * p * r / (p + r), 3) if p and r else (0.0 if (p == 0 or r == 0) else None)}
    labels_sha = hashlib.sha256((root / "labels.json").read_bytes()).hexdigest()[:12]
    return {"set": "held-out real pages", "pages": len(labels["pages"]), "evaluated": len(per_page),
            "missing_snapshots": skipped, "labels_sha": labels_sha,
            "mode": f"deterministic + {llm.name}" if llm else "deterministic",
            "fields": fields, "rates": {k: T.rate(k) for k in sorted(T.c)},
            "attribution": {"correct": attr_ok, "total": attr_n, "accuracy": round(attr_ok / attr_n, 3) if attr_n else None},
            "unsupported_rate": round(unsupported / scored_values, 3) if scored_values else None,
            "unsupported_values": unsupported, "scored_values": scored_values,
            "missing_rate": round(missing / labelled_values, 3) if labelled_values else None,
            "missing_values": missing, "labelled_values": labelled_values,
            "ai": ai if llm is not None else None,
            "misses": {k: v for k, v in per_page.items() if v}}


def fetch(root: Optional[Path] = None, fetcher=None) -> dict:
    """Re-download the snapshots listed in urls.json (robots-respecting)."""
    from .net import Fetcher, FetchError
    root = Path(root or ROOT)
    f = fetcher or Fetcher(min_interval=1.5)
    (root / "pages").mkdir(parents=True, exist_ok=True)
    out = {}
    for p in json.loads((root / "urls.json").read_text(encoding="utf-8"))["pages"]:
        try:
            r = f.get(p["url"])
        except FetchError as e:
            out[p["id"]] = {"error": e.reason}
            continue
        data = r.data if r.is_pdf else r.text.encode("utf-8")
        (root / "pages" / f"{p['id']}.{'pdf' if r.is_pdf else 'html'}").write_bytes(data)
        out[p["id"]] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return out
