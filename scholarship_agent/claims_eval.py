"""Validator evaluation on labelled candidate answers (set C).

Each labelled page carries `claims`: answers a model could give (field, value, verbatim quote) with the verdict a
careful reviewer expects (accept / reject) and why. Running them through ai_extract.validate measures the quote
validator by itself, without calling any model:

- false rejection rate = expected-accept claims that were rejected / expected-accept claims
- false acceptance rate = expected-reject claims that were accepted / expected-reject claims
- review rate = claims sent to a person (needs_review) instead of being accepted or rejected; a review is neither a
  false acceptance nor a false rejection, but it is counted, so deferring everything cannot look accurate

Claims were written from the pages, not from model output; see tests/heldout_c/labels.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .ai_extract import judge
from .heldout import load_page

AREAS = {"deadline_scholarship": "deadline", "deadline_admission": "deadline", "opening_date": "deadline",
         "academic_cycle": "cycle", "provider_name": "funding source", "residency_required": "residency",
         "eligible_nationalities": "nationality", "nationality_mode": "nationality",
         "funding_duration_months": "funding duration", "max_age": "age", "min_age": "age",
         "age_limits_by_level": "age", "covers_living_allowance": "funding components",
         "covers_accommodation": "funding components", "covers_health_insurance": "funding components",
         "covers_travel": "funding components", "tuition_coverage": "funding components",
         "stipend_amount": "funding amount", "page_conflicts": "conflicts"}


def evaluate_claims(root: Path, split: Optional[str] = None) -> dict:
    labels = json.loads((root / "labels.json").read_text(encoding="utf-8"))
    urls = {p["id"]: p for p in json.loads((root / "urls.json").read_text(encoding="utf-8"))["pages"]}
    tot = {"pos": 0, "pos_rejected": 0, "pos_review": 0, "neg": 0, "neg_accepted": 0, "neg_review": 0}
    by_area: dict = {}
    wrong = []
    for pid, lab in labels["pages"].items():
        if split and urls[pid].get("split") != split:
            continue
        page = load_page(pid, urls[pid]["url"], root)
        if page is None:
            continue
        for c in lab.get("claims", []):
            status, why = judge(c["field"], c["value"], c["quote"], page.text)
            a = by_area.setdefault(AREAS.get(c["field"], c["field"]),
                                   {"pos": 0, "pos_rejected": 0, "pos_review": 0, "neg": 0, "neg_accepted": 0, "neg_review": 0})
            for t in (tot, a):
                if c["accept"]:
                    t["pos"] += 1
                    t["pos_rejected"] += status == "rejected"
                    t["pos_review"] += status == "needs_review"
                else:
                    t["neg"] += 1
                    t["neg_accepted"] += status == "accepted"
                    t["neg_review"] += status == "needs_review"
            if status == "needs_review" or (status == "accepted") != c["accept"]:
                wrong.append({"page": pid, "field": c["field"], "value": c["value"], "expected": "accept" if c["accept"] else "reject",
                              "got": status if status == "accepted" else f"{status}: {why}", "why_expected": c["why"]})

    def rates(t):
        return {"positives": t["pos"], "false_rejections": t["pos_rejected"],
                "false_rejection_rate": round(t["pos_rejected"] / t["pos"], 3) if t["pos"] else None,
                "positives_sent_to_review": t["pos_review"],
                "negatives": t["neg"], "false_acceptances": t["neg_accepted"],
                "false_acceptance_rate": round(t["neg_accepted"] / t["neg"], 3) if t["neg"] else None,
                "negatives_sent_to_review": t["neg_review"],
                "review_rate": round((t["pos_review"] + t["neg_review"]) / (t["pos"] + t["neg"]), 3) if t["pos"] + t["neg"] else None}
    return {"set": root.name, "split": split or "all", **rates(tot),
            "by_area": {k: rates(v) for k, v in sorted(by_area.items())}, "wrong_verdicts": wrong}
