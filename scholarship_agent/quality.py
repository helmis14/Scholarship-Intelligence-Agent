"""Extraction quality against hand-labelled fixtures (tests/fixtures/scholarship/gold.json).

Per field group: true positives, false positives, false negatives -> precision,
recall, F1, plus the exact misses per fixture so regressions are readable.

    python3 -m scholarship_agent quality [--fixtures DIR] [--ai]
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from .extract import Page, extract_opportunity
from .models import ProviderType, SourceType
from .pdf import make_pdf, pdf_text

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "tests" / "fixtures" / "scholarship"
TODAY = date(2026, 10, 17)


def _items(opp, gold: dict) -> dict[str, tuple[set, set]]:
    """(predicted, expected) sets per field group."""
    got, exp = {}, {}
    got["nationality"] = {(opp.nationality.mode, c) for c in (opp.nationality.countries or ["*"])} \
        if opp.nationality.mode != "unknown" else set()
    g = gold.get("nationality") or {}
    exp["nationality"] = {(g["mode"], c) for c in (g.get("countries") or ["*"])} if g else set()
    got["deadlines"] = {(str(d.kind), d.date) for d in opp.deadlines if d.date}
    exp["deadlines"] = {tuple(x) for x in gold.get("deadlines", [])}
    got["funding_kinds"] = {c.kind for c in opp.funding if c.covered is not False}
    exp["funding_kinds"] = set(gold.get("funding", {}))
    got["funding_amounts"] = {(c.kind, c.amount, c.currency, c.period) for c in opp.funding if c.amount is not None}
    exp["funding_amounts"] = {(k, float(v["amount"]), v.get("currency"), v.get("period"))
                              for k, v in gold.get("funding", {}).items() if "amount" in v}
    got["tuition_full"] = {"full"} if any(c.kind == "tuition" and c.full for c in opp.funding) else set()
    exp["tuition_full"] = {"full"} if gold.get("funding", {}).get("tuition", {}).get("full") else set()
    got["language"] = {(r.test, float(r.minimum)) for r in opp.language_requirements if r.minimum is not None}
    exp["language"] = {(k, float(v)) for k, v in gold.get("language", {}).items()}
    # implied certificate is not a separate fact on the page; compare named documents only
    got["documents"] = {d.name for d in opp.required_documents if d.name not in ("Language test certificate", "MOI letter")}
    exp["documents"] = set(gold.get("documents", []))
    got["levels"] = set(opp.study_levels)
    exp["levels"] = set(gold.get("levels", []))
    for k in ("min_gpa", "max_age", "min_age"):
        if k in gold or getattr(opp, k) is not None:
            got[k] = {getattr(opp, k)} - {None}
            exp[k] = {gold[k]} if k in gold else set()
    return {k: (got[k], exp[k]) for k in got}


def load_page(name: str, spec: dict, directory: Path) -> Page:
    if "pdf_lines" in spec:
        text, _status = pdf_text(make_pdf(spec["pdf_lines"]))
        return Page.from_text(spec["url"], text)
    return Page(spec["url"], (directory / name).read_text(encoding="utf-8"))


def evaluate(directory: Optional[Path] = None, llm=None, ai_only: bool = False) -> dict:
    """ai_only=True scores the model alone (empty deterministic record, then enrich) - its own precision/recall."""
    directory = Path(directory or DEFAULT_DIR)
    gold = json.loads((directory / "gold.json").read_text(encoding="utf-8"))["fixtures"]
    totals: dict[str, list[int]] = {}
    per_fixture = {}
    for name, spec in gold.items():
        page = load_page(name, spec, directory)
        st = SourceType(spec.get("source_type", "official"))
        opp, _ = extract_opportunity(page, provider_name="fixture", provider_type=ProviderType.OTHER, source_type=st,
                                     country_hint=[], retrieved_at="2026-10-17T00:00:00+00:00", today=TODAY)
        ai_stats = None
        if llm is not None:
            from .ai_extract import enrich
            if ai_only:
                from .models import Opportunity
                opp = Opportunity(id=opp.id, title=opp.title, provider_name="fixture", info_url=spec["url"])
            ai_stats = enrich(opp, page.text, llm, source_type=st, retrieved_at="2026-10-17T00:00:00+00:00",
                              today=TODAY)
            totals.setdefault("_ai_rejected", [0, 0, 0])[0] += len(ai_stats["rejected"])
            totals.setdefault("_ai_errors", [0, 0, 0])[0] += 1 if ai_stats.get("error") else 0
        misses = {}
        for field, (got, exp) in _items(opp, spec).items():
            tp, fp, fn = len(got & exp), len(got - exp), len(exp - got)
            t = totals.setdefault(field, [0, 0, 0])
            t[0] += tp
            t[1] += fp
            t[2] += fn
            if fp or fn:
                misses[field] = {"missed": sorted(map(str, exp - got)), "spurious": sorted(map(str, got - exp))}
        if spec.get("expect_conflict") is not None:
            ok = bool(opp.conflicts) == spec["expect_conflict"]
            t = totals.setdefault("conflict_detection", [0, 0, 0])
            t[0 if ok else 2] += 1
            if not ok:
                misses["conflict_detection"] = {"missed": ["conflict"], "spurious": []}
        per_fixture[name] = misses
    fields = {}
    all_tp = all_fp = all_fn = 0
    ai = {"rejected_by_quote_check": totals.pop("_ai_rejected", [0])[0], "calls_failed": totals.pop("_ai_errors", [0])[0]}
    for f, (tp, fp, fn) in sorted(totals.items()):
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        fields[f] = {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3),
                     "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}
        all_tp, all_fp, all_fn = all_tp + tp, all_fp + fp, all_fn + fn
    P = all_tp / (all_tp + all_fp) if all_tp + all_fp else 1.0
    R = all_tp / (all_tp + all_fn) if all_tp + all_fn else 1.0
    mode = (f"{llm.name} only" if ai_only else f"deterministic + {llm.name}") if llm else "deterministic"
    return {"fixtures": len(gold), "mode": mode, "ai": ai if llm else None,
            "overall": {"precision": round(P, 3), "recall": round(R, 3), "f1": round(2 * P * R / (P + R), 3) if P + R else 0},
            "fields": fields, "misses": {k: v for k, v in per_fixture.items() if v}}
