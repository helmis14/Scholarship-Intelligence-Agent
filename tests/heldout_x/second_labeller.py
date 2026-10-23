"""Agreement between the first labels of set X and a second labeller's answers (round 46).

The second labeller fills the "Lembar Pelabel Kedua" form (24 pages of set X, read on the live official pages) without
seeing the first labels. Export the answers as JSON (the form's copy button, or the form's store) and run:

    python3 tests/heldout_x/second_labeller.py answers.json [--adjudicated]

Per decision it prints the share of pages where both labellers agree and Cohen's kappa (agreement beyond chance), and
lists the disagreements to adjudicate. Pages the second labeller marked as changed or unavailable are left out.
Nationality agrees when the mode and the country set are the same; deadlines when the sets of dates are the same.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))


def _codes(text: str) -> tuple:
    from scholarship_agent.countries import code, mentions
    out = set()
    for part in re.split(r"[,;\n]+", text or ""):
        p = part.strip()
        if not p:
            continue
        c = code(p) if len(p) > 2 else p.upper()
        out |= {c} if c else set(mentions(p))
    return tuple(sorted(out))


def second(a: dict) -> dict:
    nat = a.get("nat") or "not_stated"
    return {"nationality": (nat, _codes(a.get("nat_countries", ""))) if nat in ("include", "exclude") else (nat, ()),
            "funding": a.get("funding") or "not_stated",
            "deadline": () if a.get("no_deadline") else tuple(sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", a.get("deadlines", ""))))),
            "cycle": a.get("cycle") or "not_stated"}


def first(fields: dict) -> dict:
    n = fields["nationality"]
    return {"nationality": ("not_stated", ()) if n == "not_stated" else
            (n["mode"], tuple(sorted(n["countries"])) if n["mode"] != "any" else ()),
            "funding": fields["funding_class"], "deadline": tuple(sorted(d["date"] for d in fields["deadlines"])),
            "cycle": fields["cycle_status"]}


def kappa(pairs: list) -> float:
    n = len(pairs)
    if not n:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def main():
    answers = json.loads(Path(sys.argv[1]).read_text())
    pages = answers.get("pages", answers)
    labels = json.loads((ROOT / "labels.json").read_text())["pages"]
    if "--adjudicated" in sys.argv and (ROOT / "adjudication.json").exists():
        for pid, case in json.loads((ROOT / "adjudication.json").read_text())["cases"].items():
            labels[pid]["fields"].update(case["fields"])
    pairs = {d: [] for d in ("nationality", "funding", "deadline", "cycle")}
    diffs = []
    for pid, a in sorted(pages.items()):
        if pid not in labels or a.get("unavailable"):
            continue
        s, f = second(a), first(labels[pid]["fields"])
        for d in pairs:
            pairs[d].append((f[d], s[d]))
            if f[d] != s[d]:
                diffs.append({"page": pid, "decision": d, "first": f[d], "second": s[d], "note": a.get("note", ""),
                              "close_call": d.replace("funding", "funding_class").replace("deadline", "deadlines")
                              .replace("cycle", "cycle_status") in labels[pid].get("ambiguous_fields", [])})
    out = {"pages_compared": len(pairs["funding"]),
           "agreement": {d: round(sum(a == b for a, b in p) / len(p), 3) if p else None for d, p in pairs.items()},
           "kappa": {d: round(kappa([(str(a), str(b)) for a, b in p]), 3) if p else None for d, p in pairs.items()},
           "overall_agreement": round(sum(a == b for p in pairs.values() for a, b in p) / max(1, sum(len(p) for p in pairs.values())), 3),
           "disagreements": diffs}
    print(json.dumps(out, indent=1, ensure_ascii=False, default=list))


if __name__ == "__main__":
    main()
