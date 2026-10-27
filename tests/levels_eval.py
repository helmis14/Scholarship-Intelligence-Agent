"""Study-level scoring: the levels a record says an award is *for* (opp.study_levels) against the labelled levels.

Every page of the development sets in tests/devpool.py SETS whose label has fields.levels ([] = no level stated) is
loaded and extracted as tests/decisions.py does (adjudication.json applied; none changes levels so far; page
classification is left out because it never changes study_levels). Each page lands in one outcome:
  exact         the reported levels equal the label
  extra         a level is reported that the label does not have (the error that misleads an applicant)
  only_missing  no extra level, but a labelled level is not reported
utility = exact - 2 x pages_with_extra - 0.5 x pages_with_only_missing
A rule change is kept only when pooled utility improves and utility falls on no set (--compare prints KEEP / REJECT).
These sets are development data: a gain here is a development-set result, not a fresh-set one.
Usage: levels_eval.py [--save FILE] [--compare FILE] [--clear-only] [--errors]
  --clear-only  leave out pages whose levels the label marks as a close call ("ambiguous_fields")
  --errors      print each page with an extra level and the sentence that produced it
"""
import json, sys
from datetime import date
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO))
sys.path.append(str(REPO / "tests"))
from devpool import SETS  # noqa: E402

KEYS = ("pages", "exact", "extra", "only_missing", "utility")


def score(root: Path, clear_only=False, errors=False) -> dict:
    from scholarship_agent.extract import extract_opportunity
    from scholarship_agent.heldout import load_page
    from scholarship_agent.models import ProviderType, SourceType
    labels = json.loads((root / "labels.json").read_text())
    if (root / "adjudication.json").exists():
        for pid, case in json.loads((root / "adjudication.json").read_text())["cases"].items():
            labels["pages"][pid]["fields"].update(case["fields"])
    urls = {p["id"]: p for p in json.loads((root / "urls.json").read_text())["pages"]}
    today = date.fromisoformat(labels["today"])
    r = dict.fromkeys(KEYS, 0)
    for pid, lab in labels["pages"].items():
        if lab["kind"] != "opportunity" or "levels" not in lab.get("fields", {}) \
                or clear_only and "levels" in lab.get("ambiguous_fields", []):
            continue
        pg = load_page(pid, urls[pid]["url"], root)
        opp, _ = extract_opportunity(pg, provider_name="heldout", provider_type=ProviderType.OTHER,
                                     source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=today)
        got, want = set(opp.study_levels), set(lab["fields"]["levels"])
        r["pages"] += 1
        out = "exact" if got == want else "extra" if got - want else "only_missing"
        r[out] += 1
        if errors and out == "extra":
            print(f"{root.name} {pid}: got {sorted(got)} label {sorted(want)}")
            for e in opp.evidence:
                if e.field == "study_levels" and e.value[0] in got - want:
                    print(f"   {e.value[0]}: {e.snippet}")
    r["utility"] = r["exact"] - 2 * r["extra"] - 0.5 * r["only_missing"]
    return r


def main():
    out = {s: score(REPO / "tests" / s, "--clear-only" in sys.argv, "--errors" in sys.argv) for s in SETS}
    out["total"] = {k: sum(out[s][k] for s in SETS) for k in KEYS}
    for s in SETS + ["total"]:
        print(f"{s:10} " + json.dumps(out[s]))
    if "--save" in sys.argv:
        Path(sys.argv[sys.argv.index("--save") + 1]).write_text(json.dumps(out))
    if "--compare" in sys.argv:
        base = json.loads(Path(sys.argv[sys.argv.index("--compare") + 1]).read_text())
        print("difference against", sys.argv[sys.argv.index("--compare") + 1])
        for s in SETS + ["total"]:
            print(f"{s:10} " + json.dumps({k: out[s][k] - base[s][k] for k in KEYS}))
        ok = out["total"]["utility"] > base["total"]["utility"] \
            and all(out[s]["utility"] >= base[s]["utility"] for s in SETS)
        print("KEEP" if ok else "REJECT")


if __name__ == "__main__":
    main()
