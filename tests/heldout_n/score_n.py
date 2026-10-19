"""Score set N (round 29 frozen test set): applicant decisions (tests/decisions.py) plus the per-field metrics of
scholarship_agent.heldout.evaluate. Refuses to run if the frozen pages, labels, scorer or code changed
(--any-code scores another code version, e.g. the round-26 baseline, on the same frozen data).
Usage: score_n.py [--any-code] [--clear-only] [--json]
"""
import hashlib, json, sys
from datetime import date
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
L = REPO / "tests" / "heldout_n"
sys.path.append(str(REPO))
sys.path.append(str(REPO / "tests"))
CODE = ["extract.py", "identity.py", "evidence.py", "countries.py", "languages.py", "languages.json", "retrieval.py",
        "audit.py", "funding.py", "parties.py", "heldout.py", "models.py"]
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def main():
    m = json.loads((L / "manifest.json").read_text())
    assert m["labels_sha256"] == sha((L / "labels.json").read_bytes()), "labels changed since freezing"
    assert all(sha((L / "pages" / p["file"]).read_bytes()) == p["sha256"] for p in m["pages"]), "a page changed"
    assert all(m["scorer_sha256"][f] == sha((REPO / "tests" / f).read_bytes()) for f in m["scorer_sha256"]), "scorer changed"
    if "--any-code" not in sys.argv:
        assert all(m["code_sha256"][c] == sha((REPO / "scholarship_agent" / c).read_bytes()) for c in m["code_sha256"]), \
            "code changed since freezing"
    from decisions import score
    from scholarship_agent.heldout import evaluate
    labels = json.loads((L / "labels.json").read_text())
    dec = score(L, skip_ambiguous="--clear-only" in sys.argv)
    fields = evaluate(L, today=date.fromisoformat(labels["today"]))
    out = {"set": "N", "decisions": {k: v for k, v in dec.items() if k != "rows"},
           "fields": {k: fields[k] for k in ("rates", "unsupported_values", "scored_values", "missing_values", "labelled_values")}}
    if "--json" in sys.argv:
        out["rows"], out["field_misses"] = dec["rows"], fields["misses"]
    print(json.dumps(out, indent=1, ensure_ascii=False, default=list))


if __name__ == "__main__":
    main()
