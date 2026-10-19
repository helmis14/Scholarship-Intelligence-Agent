"""Score page classification on a labelled page set (tests/dev_r21, tests/heldout_h ...).

Two error kinds, reported apart and never merged:
  false accept  a page that is not a programme is accepted as a programme
  false reject  a real programme page is rejected
Pages the rules are unsure of go to review, and pages that did not load are "not loaded"; both are counted per class,
never as an error of either kind.
Usage: score_pages.py SET_DIR [--json]   (set dir holds urls.json, labels.json, pages/)
"""
import json, sys, urllib.parse
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO))   # after PYTHONPATH, so a baseline can point PYTHONPATH at an older package copy
from datetime import date  # noqa: E402
from scholarship_agent.evidence import classify_authority  # noqa: E402
from scholarship_agent.extract import extract_opportunity, page_kind  # noqa: E402
from scholarship_agent.heldout import load_page  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402
try:
    from scholarship_agent.extract import classify_page
except ImportError:            # code before round 21: no confidence
    classify_page = lambda p: dict(zip(("kind", "reason"), page_kind(p)), confidence="high")  # noqa: E731
try:
    from scholarship_agent.identity import identity
except ImportError:            # code before round 20: no identity check
    identity = None


def run(root: Path) -> list[dict]:
    labels = json.loads((root / "labels.json").read_text())["pages"]
    rows = []
    for p in json.loads((root / "urls.json").read_text())["pages"]:
        lab = labels[p["id"]]
        pg = load_page(p["id"], p["url"], root)
        c = classify_page(pg)
        host = (urllib.parse.urlsplit(p["url"]).hostname or "").removeprefix("www.")
        opp, _ = extract_opportunity(pg, provider_name=p.get("provider") or host, provider_type=ProviderType.OTHER,
                                     source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=date(2026, 10, 18))
        opp.source_authority = str(classify_authority(p["url"], official_domains=[host], page_kind=c["kind"],
                                                      source_type=SourceType.OFFICIAL, title=pg.title))
        if identity:
            kw = {"kind_confidence": c["confidence"], "kind_reason": c["reason"]} if "kind_confidence" in identity.__code__.co_varnames else {}
            idn = identity(opp, page_title=getattr(pg, "html_title", "") or pg.title, h1=getattr(pg, "h1", ""),
                           text=pg.text, page_kind=c["kind"], **kw)
        else:
            idn = {"state": "confirmed" if c["kind"] == "opportunity" else "rejected", "reasons": []}
        # page type alone (classify_page), then the full pipeline (page type + programme identity)
        page_decision = "not_loaded" if c["kind"] == "not_loaded" else "review" if c["confidence"] == "low" \
            else "accepted" if c["kind"] == "opportunity" else "rejected"
        if c["kind"] == "not_loaded":
            decision = "not_loaded"   # not assessed: counted apart, never as a rejection
        elif c["confidence"] == "low" or idn["state"] == "needs_review":
            decision = "review"
        else:
            decision = "accepted" if c["kind"] == "opportunity" and idn["state"] == "confirmed" else "rejected"
        rows.append({"id": p["id"], "lang": p.get("lang", ""), "label": lab["kind"], "programme": lab["programme"],
                     "ambiguous": lab.get("ambiguous", False), "kind": c["kind"], "confidence": c["confidence"],
                     "identity": idn["state"], "page_decision": page_decision, "decision": decision, "reason": c["reason"][:160],
                     "identity_reasons": idn["reasons"][:3]})
    return rows


def score(rs: list[dict], key: str = "decision") -> dict:
    prog = [r for r in rs if r["programme"]]
    non = [r for r in rs if not r["programme"]]
    return {"pages": len(rs), "programme_pages": len(prog), "other_pages": len(non),
            "page_kind_correct": sum(r["kind"] == r["label"] for r in rs),
            **({"page_type": score(rs, "page_decision")} if key == "decision" else {}),
            "false_accept": sum(r[key] == "accepted" for r in non),
            "false_reject": sum(r[key] == "rejected" for r in prog),
            "programmes_accepted": sum(r[key] == "accepted" for r in prog),
            "programmes_to_review": sum(r[key] == "review" for r in prog),
            "programmes_not_loaded": sum(r[key] == "not_loaded" for r in prog),
            "others_not_loaded": sum(r[key] == "not_loaded" for r in non),
            "others_rejected": sum(r[key] == "rejected" for r in non),
            "others_to_review": sum(r[key] == "review" for r in non)}


if __name__ == "__main__":
    root = Path(sys.argv[1])
    rows = run(root)
    by_lang = {}
    for r in rows:
        by_lang.setdefault(r["lang"] or "-", []).append(r)
    out = {"set": root.name, "all": score(rows), "unambiguous": score([r for r in rows if not r["ambiguous"]]),
           "by_language": {k: score(v) for k, v in sorted(by_lang.items())}, "pages": rows}
    print(json.dumps(out, indent=1, ensure_ascii=False) if "--json" in sys.argv else
          json.dumps({k: out[k] for k in ("all", "unambiguous")}, ensure_ascii=False) + "\n" +
          "\n".join(f"{k:6} {v}" for k, v in out["by_language"].items()))
