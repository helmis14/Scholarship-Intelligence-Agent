"""Decision-level scoring (round 27): for each labelled programme, the four decisions an applicant acts on.

  eligibility  who may apply by nationality (mode + countries), or "not stated"
  funding      the funding class (fully / partially / tuition-only / stipend-only ...), or "not stated"
  cycle        open / upcoming / closed / not_announced / rolling, or "not stated"
  deadline     the set of applicant deadline dates the page states, or none

Each decision lands in one outcome:
  correct          the reported value equals the label
  wrong_claim      a value reported as known that differs from the label (the error that misleads an applicant)
  flagged          a value sent to review (needs_review / unsupported) instead of being reported
  abstained        nothing reported although the label has a value
"funding_unclear" counts as abstained: it says what is documented without claiming a class. A decision reported
as known also says whether its quotation passed the round-27 evidence checks (own page, states the value, names no
other programme). The pipeline's page classification runs first, as in verification, so a page read as a
catalogue sends its decisions to review.
Usage: decisions.py <set dir> [--split dev|test] [--clear-only] [--adjudicate] [--json]
"""
import json, sys
from datetime import date
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO))

OUTCOMES = ("correct", "wrong_claim", "flagged", "abstained")


def _nat(opp):
    n = opp.nationality
    return "not_stated" if n.mode == "unknown" else (n.mode, tuple(sorted(n.countries)) if n.mode != "any" else ())


def _nat_label(g):
    return "not_stated" if g == "not_stated" else (g["mode"], tuple(sorted(g["countries"])) if g["mode"] != "any" else ())


LABEL_FIELD = {"eligibility": "nationality", "funding": "funding_class", "cycle": "cycle_status", "deadline": "deadlines"}


def _review_summary(tally: dict, rows: list) -> dict:
    tot = {o: sum(t[o] for t in tally.values()) for o in OUTCOMES}
    n = sum(tot.values())
    held_right = sum(1 for r in rows for d in tally if d in r and r[d]["flagged_value_was_right"])
    answered = tot["correct"] + tot["wrong_claim"] + tot["abstained"]
    return {"decisions": n, "answered_without_review": answered, "correct_without_review": tot["correct"],
            "wrong_claims": tot["wrong_claim"], "sent_to_review": tot["flagged"], "correct_but_held_in_review": held_right,
            "share_answered": round(answered / n, 3) if n else None,
            "share_correct_without_review": round(tot["correct"] / n, 3) if n else None,
            "wrong_claims_among_answered": round(tot["wrong_claim"] / answered, 3) if answered else None}


def score(root: Path, split=None, skip_ambiguous=False, adjudicate=False) -> dict:
    """skip_ambiguous: leave out the decisions a label marks as a close call ("ambiguous_fields").
    adjudicate: apply <set>/adjudication.json overrides in memory (labels.json and frozen results stay as they are)."""
    from scholarship_agent.audit import cycle_status, field_status, funding_type
    try:
        from scholarship_agent.audit import decision_evidence
    except ImportError:   # code from before round 27 (a baseline) has no evidence checks
        def decision_evidence(o, t):
            return {}
    from scholarship_agent.extract import classify_page, extract_opportunity
    from scholarship_agent.heldout import load_page
    from scholarship_agent.identity import page_type
    from scholarship_agent.models import DeadlineKind, ProviderType, SourceType
    labels = json.loads((root / "labels.json").read_text())
    if adjudicate and (root / "adjudication.json").exists():
        for pid, case in json.loads((root / "adjudication.json").read_text())["cases"].items():
            labels["pages"][pid]["fields"].update(case["fields"])
    urls = {p["id"]: p for p in json.loads((root / "urls.json").read_text())["pages"]}
    today = date.fromisoformat(labels["today"])
    tally = {d: {o: 0 for o in OUTCOMES} for d in ("eligibility", "funding", "cycle", "deadline")}
    known_supported = {d: [0, 0] for d in tally}       # [quotation passed the checks, known decisions]
    rows = []
    by_rule: dict = {}
    for pid, lab in labels["pages"].items():
        if split and urls[pid].get("split") != split or lab["kind"] != "opportunity":
            continue
        pg = load_page(pid, urls[pid]["url"], root)
        opp, _ = extract_opportunity(pg, provider_name="heldout", provider_type=ProviderType.OTHER,
                                     source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=today)
        cls = classify_page(pg)
        opp.page_type = "unknown" if cls["confidence"] == "low" else page_type(cls["kind"])
        fs = field_status(opp, today)
        de = decision_evidence(opp, today)
        F = lab.get("fields", {})
        got = {
            "eligibility": (_nat(opp), fs["eligible_countries"]["state"]),
            "funding": (funding_type(opp)["state"], fs["funding_type"]["state"]),
            "cycle": (cycle_status(opp, today)["state"], fs["cycle"]["state"]),
            "deadline": (tuple(sorted({d.date for d in opp.deadlines if d.date and d.kind in
                                       (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)})), fs["deadline"]["state"]),
        }
        want = {
            "eligibility": _nat_label(F["nationality"]) if "nationality" in F else None,
            "funding": F.get("funding_class"),
            "cycle": F.get("cycle_status"),
            "deadline": tuple(sorted(d["date"] for d in F["deadlines"])) if "deadlines" in F else None,
        }
        row = {"id": pid}
        for d in tally:
            if want[d] is None or skip_ambiguous and LABEL_FIELD[d] in lab.get("ambiguous_fields", []):
                continue
            value, state = got[d]
            empty = value in ("not_stated", "funding_unclear", ())
            label_empty = want[d] in ("not_stated", ())
            if state in ("needs_review", "unsupported"):
                out = "flagged"
            elif empty:
                out = "correct" if label_empty else "abstained"
            else:
                out = "correct" if value == want[d] else "wrong_claim"
            tally[d][out] += 1
            if d == "eligibility":   # round 29: eligibility split by the kind of rule the label states
                kind = want[d] if want[d] == "not_stated" else want[d][0]
                by_rule.setdefault(kind, {o: 0 for o in OUTCOMES})[out] += 1
            if out in ("correct", "wrong_claim") and not empty and d != "deadline":
                known_supported[d][1] += 1
                known_supported[d][0] += de.get(d, {}).get("state") == "supported"
            row[d] = {"outcome": out, "predicted": value, "label": want[d], "state": state,
                      "flagged_value_was_right": value == want[d] if out == "flagged" else None,
                      "evidence": de.get(d, {}).get("problems", [])}
        rows.append(row)
    n = {d: sum(t.values()) for d, t in tally.items()}
    return {"set": root.name, "split": split or "all", "ambiguous_left_out": skip_ambiguous, "adjudicated": adjudicate,
            "today": labels["today"],
            "decisions": tally,
            "correct_rate": {d: round(t["correct"] / n[d], 3) if n[d] else None for d, t in tally.items()},
            "wrong_claim_rate": {d: round(t["wrong_claim"] / n[d], 3) if n[d] else None for d, t in tally.items()},
            "known_with_clean_quotation": {d: f"{a}/{b}" for d, (a, b) in known_supported.items() if d != "deadline"},
            "flagged_but_right": {d: sum(1 for r in rows if d in r and r[d]["flagged_value_was_right"]) for d in tally},
            # round 28: the review trade-off. "answered" = reported without review; a held-back right value is a
            # correct decision the review gate cost; review_load is what a person must look at
            "review": _review_summary(tally, rows),
            # "exclude" rows are where negation decides: "non-U.S. citizens", "not an Australian citizen"
            "eligibility_by_label_rule": by_rule,
            "programmes": len(rows), "rows": rows}


if __name__ == "__main__":
    root = Path(sys.argv[1])
    split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else None
    r = score(root, split, skip_ambiguous="--clear-only" in sys.argv, adjudicate="--adjudicate" in sys.argv)
    print(json.dumps(r if "--json" in sys.argv else {k: v for k, v in r.items() if k != "rows"}, indent=1,
                     ensure_ascii=False, default=list))
