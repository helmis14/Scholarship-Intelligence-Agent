"""Score set K (round 26 field-accuracy benchmark).

The per-field metrics of scholarship_agent.heldout.evaluate (deadlines, nationality, levels, cycle, provider,
funding components, amounts, unsupported and missing values) on the frozen labels, plus three fields that
evaluator does not cover: residency requirements, the funding class (fully / partially / tuition-only / stipend-only)
and the cycle status (open / upcoming / closed / not_announced / rolling / not_stated). Refuses to run if the frozen
pages, labels or code changed (--any-code to score another code version on the same frozen data).
Usage: score_k.py [--split dev|test] [--any-code] [--json]
"""
import hashlib, json, sys
from datetime import date
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
K = REPO / "tests" / "heldout_k"
sys.path.append(str(REPO))   # after PYTHONPATH, so a baseline can point PYTHONPATH at an older package copy
CODE = ["extract.py", "identity.py", "evidence.py", "countries.py", "languages.py", "languages.json", "retrieval.py",
        "audit.py", "funding.py", "parties.py", "heldout.py"]
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def extra_fields(opp, lab: dict, today: date) -> dict:
    """{field: (correct, predicted)} for residency, funding_class and cycle_status where the label has them."""
    from scholarship_agent.audit import cycle_status, funding_type
    out = {}
    if "residency" in lab:
        got = sorted(opp.nationality.residency_required)
        out["residency"] = (got == sorted(lab["residency"]), got)
    if "funding_class" in lab:
        got = funding_type(opp)["state"]
        out["funding_class"] = (got == lab["funding_class"], got)
    if "cycle_status" in lab:
        got = cycle_status(opp, today)["state"]
        out["cycle_status"] = (got == lab["cycle_status"], got)
    return out


def main():
    m = json.loads((K / "manifest.json").read_text())
    assert m["labels_sha256"] == sha((K / "labels.json").read_bytes()), "labels changed since freezing"
    assert all(sha((K / "pages" / p["file"]).read_bytes()) == p["sha256"] for p in m["pages"]), "a page changed"
    if "--any-code" not in sys.argv:
        assert all(m["code_sha256"][c] == sha((REPO / "scholarship_agent" / c).read_bytes()) for c in m["code_sha256"]), \
            "code changed since freezing"
    split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else None
    from scholarship_agent.extract import extract_opportunity
    from scholarship_agent.heldout import evaluate, load_page
    from scholarship_agent.models import ProviderType, SourceType
    labels = json.loads((K / "labels.json").read_text())
    today = date.fromisoformat(labels["today"])
    base = evaluate(K, today=today, split=split)
    urls = {p["id"]: p for p in json.loads((K / "urls.json").read_text())["pages"]}
    extra, misses = {}, {}
    for pid, lab in labels["pages"].items():
        if split and urls[pid].get("split") != split or lab["kind"] != "opportunity":
            continue
        pg = load_page(pid, urls[pid]["url"], K)
        opp, _ = extract_opportunity(pg, provider_name="heldout", provider_type=ProviderType.OTHER,
                                     source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=today)
        for f, (ok, got) in extra_fields(opp, lab.get("fields", {}), today).items():
            t = extra.setdefault(f, [0, 0])
            t[0] += ok
            t[1] += 1
            if not ok:
                misses.setdefault(pid, []).append(f"{f}: predicted {got}, label {lab['fields'][f]}")
    base["rates"].update({k: {"correct": c, "total": n, "accuracy": round(c / n, 3) if n else None}
                          for k, (c, n) in extra.items()})
    for pid, ms in misses.items():
        base["misses"].setdefault(pid, []).extend(ms)
    base["set"], base["split"] = "K", split or "all"
    print(json.dumps(base, indent=1, ensure_ascii=False) if "--json" in sys.argv else
          json.dumps({k: base[k] for k in ("split", "fields", "rates", "unsupported_values", "scored_values",
                                           "missing_values", "labelled_values")}, indent=1))


if __name__ == "__main__":
    main()
