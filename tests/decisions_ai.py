"""Decision scores (tests/decisions.py) with Claude-assisted extraction on top of the rules.

The rules read each page as usual; then ai_extract.enrich() asks the configured model for the fields the rules left
empty (mode "targeted") or for every field (mode "full"), quote-checks every answer and keeps only evidence-backed
values. The four decisions are then scored exactly as in decisions.py. decisions.py itself is not changed (its hash
is frozen in the set manifests); this module wraps extract_opportunity.

Paid calls are off unless ANTHROPIC_ALLOW_PAID=1 and budgets are set; without them every request is a dry run that
is estimated and skipped, and the scores equal the rules-only scores.
Usage: decisions_ai.py <set dir> [--mode targeted|full] [--clear-only] [--adjudicate] [--json]
"""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO))
sys.path.append(str(REPO / "tests"))


def main():
    from scholarship_agent import extract as X
    from scholarship_agent.ai_extract import default_llm, enrich
    from scholarship_agent.models import SourceType
    from scholarship_agent.store import Store
    import decisions
    root = Path(sys.argv[1])
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "targeted"
    store = Store()   # the page cache and usage ledger live in SCHOLAR_DATA_DIR
    llm = default_llm(store)
    if llm is None:
        sys.exit("AI_PROVIDER is not set: nothing to compare (use decisions.py for rules only)")
    stats = {"pages": 0, "proposed": 0, "accepted": 0, "rejected": {}, "needs_review": {}, "errors": {}, "skipped": 0}
    original = X.extract_opportunity

    def with_ai(page, **kw):
        opp, warnings = original(page, **kw)
        st = enrich(opp, page.text, llm, source_type=SourceType.OFFICIAL, retrieved_at=kw["retrieved_at"],
                    today=kw["today"], mode=mode)
        stats["pages"] += 1
        stats["proposed"] += st.get("proposed", 0)
        stats["accepted"] += len(st.get("accepted", []))
        for r in st.get("rejected", []):
            stats["rejected"][r["reason"]] = stats["rejected"].get(r["reason"], 0) + 1
        for r in st.get("needs_review", []):
            stats["needs_review"][r["reason"]] = stats["needs_review"].get(r["reason"], 0) + 1
        if st.get("error"):
            k = st["error"].split(":", 1)[0]
            stats["errors"][k] = stats["errors"].get(k, 0) + 1
        if st.get("skipped"):
            stats["skipped"] += 1
        return opp, warnings

    X.extract_opportunity = with_ai
    try:
        r = decisions.score(root, skip_ambiguous="--clear-only" in sys.argv, adjudicate="--adjudicate" in sys.argv)
    finally:
        X.extract_opportunity = original
    r["ai"] = {"model": llm.name, "mode": mode, **stats, "usage": llm.usage() if hasattr(llm, "usage") else None}
    print(json.dumps(r if "--json" in sys.argv else {k: v for k, v in r.items() if k != "rows"}, indent=1,
                     ensure_ascii=False, default=list))


if __name__ == "__main__":
    main()
