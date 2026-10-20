"""Round 30: score the rules on every used set at once (K, L, M adjudicated, N, O adjudicated) so a change is judged on all of them.

utility = correct - 2 x wrong_claims - 0.5 x correct_held_in_review   (a wrong claim misleads an applicant; a right
answer held for review costs a person's time)
A rule change is kept only when total utility improves and utility falls on none of the 4 sets (a fall that is only a
held value becoming right, with no more review, fewer correct or more wrong, does not count)
(--compare FILE prints the per-set difference against a saved run).
Usage: devpool.py [--json] [--rows]
"""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO / "tests"))
SETS = ["heldout_k", "heldout_l", "heldout_m", "heldout_n", "heldout_o", "heldout_p", "heldout_q", "heldout_r"]


def utility(rev: dict) -> float:
    return rev["correct_without_review"] - 2 * rev["wrong_claims"] - 0.5 * rev["correct_but_held_in_review"]


def main():
    from decisions import score
    out = {}
    for s in SETS:
        r = score(REPO / "tests" / s, adjudicate=True)
        rev = r["review"]
        out[s] = {"utility": utility(rev), "correct": rev["correct_without_review"], "wrong": rev["wrong_claims"],
                  "review": rev["sent_to_review"], "held_right": rev["correct_but_held_in_review"],
                  "by_decision": {k: (v["correct"], v["wrong_claim"], v["flagged"], v["abstained"]) for k, v in r["decisions"].items()}}
        if "--rows" in sys.argv:
            out[s]["rows"] = r["rows"]
    out["total"] = {k: sum(out[s][k] for s in SETS) for k in ("utility", "correct", "wrong", "review", "held_right")}
    if "--save" in sys.argv:
        Path(sys.argv[sys.argv.index("--save") + 1]).write_text(json.dumps({k: v for k, v in out.items()}, default=list))
    if "--compare" in sys.argv:
        base = json.loads(Path(sys.argv[sys.argv.index("--compare") + 1]).read_text())
        for s in SETS + ["total"]:
            d = {k: round(out[s][k] - base[s][k], 1) for k in ("utility", "correct", "wrong", "review", "held_right")}
            print(f"{s:10} {d}")
        # a set whose only loss is a held value that became right (same review load, no fewer correct, no more wrong)
        # has not got worse: those decisions were in review before and still are
        def held_only(s):
            return out[s]["correct"] >= base[s]["correct"] and out[s]["wrong"] <= base[s]["wrong"] \
                and out[s]["review"] <= base[s]["review"]
        ok = all(out[s]["utility"] >= base[s]["utility"] or held_only(s) for s in SETS) \
            and out["total"]["utility"] > base["total"]["utility"]
        print("KEEP" if ok else "REJECT")
        return
    print(json.dumps(out, indent=1, default=list) if "--json" in sys.argv or "--rows" in sys.argv else
          "\n".join(f"{s:10} " + json.dumps({k: v for k, v in out[s].items() if k != "by_decision"}) for s in SETS + ["total"]))


if __name__ == "__main__":
    main()
