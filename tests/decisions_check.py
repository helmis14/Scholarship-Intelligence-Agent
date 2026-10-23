"""Decision scores (tests/decisions.py) with the second reading of round 43: an independent model reads each page and
every answered decision it reads differently is held for review (scholarship_agent/ai_check.py). decisions.py is not
changed (its hash is frozen in the set manifests); this module wraps extract_opportunity.

Paid calls are off unless ANTHROPIC_ALLOW_PAID=1 and the per-run budgets are set; without them every request is a dry
run that is estimated and skipped, and the scores equal the rules-only scores.
Usage: decisions_check.py <set dir> [<set dir> ...] [--cache FILE] [--cache-only] [--clear-only] [--adjudicate] [--json]
  --cache FILE   keep each page's second reading in FILE (keyed by model and page text) and reuse it
  --cache-only   never call the model; pages without a cached reading keep the rules' answers
"""
import hashlib, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO))
sys.path.append(str(REPO / "tests"))


def main():
    from scholarship_agent import extract as X
    from scholarship_agent.ai_check import attach_second_reading
    from scholarship_agent.ai_extract import default_llm
    from scholarship_agent.store import Store
    import decisions
    llm = default_llm(Store())
    if llm is None:
        sys.exit("AI_PROVIDER is not set: nothing to compare (use decisions.py for rules only)")
    stats = {"pages": 0, "read": 0}
    original = X.extract_opportunity

    cache_file = Path(sys.argv[sys.argv.index("--cache") + 1]) if "--cache" in sys.argv else None
    cache = json.loads(cache_file.read_text()) if cache_file and cache_file.exists() else {}
    model = getattr(llm, "model", getattr(llm, "name", ""))

    def with_check(page, **kw):
        opp, warnings = original(page, **kw)
        stats["pages"] += 1
        key = hashlib.sha256(f"{model}\n{page.url}\n{page.text}".encode()).hexdigest()
        if key in cache:
            opp.second_reading = cache[key]
        elif "--cache-only" not in sys.argv:
            attach_second_reading(opp, page.text, llm, kw["today"])
            if cache_file is not None and opp.second_reading:
                cache[key] = opp.second_reading
                cache_file.write_text(json.dumps(cache, ensure_ascii=False))
        if getattr(opp, "second_reading", None):
            stats["read"] += 1
        return opp, warnings

    X.extract_opportunity = with_check
    out = {}
    try:
        skip = {sys.argv[sys.argv.index("--cache") + 1]} if "--cache" in sys.argv else set()
        for root in [Path(a) for a in sys.argv[1:] if not a.startswith("--") and a not in skip]:
            r = decisions.score(root, skip_ambiguous="--clear-only" in sys.argv, adjudicate="--adjudicate" in sys.argv)
            out[root.name] = r if "--json" in sys.argv else r["review"]
    finally:
        X.extract_opportunity = original
    out["check"] = {"model": getattr(llm, "model", ""), **stats, "usage": llm.usage() if hasattr(llm, "usage") else None}
    print(json.dumps(out, indent=1, ensure_ascii=False, default=list))


if __name__ == "__main__":
    main()
