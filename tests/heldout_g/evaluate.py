"""Score set G: (1) page kind, (2) the pipeline decision a record would get (accepted programme / review /
rejected). Two error kinds, never merged: non-programme pages accepted as programmes, and real programme pages
rejected. Refuses to run if the frozen pages, labels or classifier files changed (python3 evaluate.py --any-code to
score an older or newer code version on the same frozen pages and labels, e.g. for a baseline)."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
G = REPO / "tests" / "heldout_g"
sys.path.insert(0, str(REPO / "tests" / "heldout_g"))
sys.path.append(str(REPO))   # after PYTHONPATH, so a baseline can point PYTHONPATH at an older package copy
import freeze  # noqa: E402
from scholarship_agent.evidence import classify_authority  # noqa: E402
from scholarship_agent.extract import extract_opportunity, page_kind  # noqa: E402
from scholarship_agent.heldout import load_page  # noqa: E402
from scholarship_agent.models import ProviderType, SourceType  # noqa: E402
from scholarship_agent.registry import load_sources  # noqa: E402

frozen, now = json.loads((G / "manifest.json").read_text()), freeze.current()
assert frozen["pages"] == now["pages"] and frozen["labels_sha256"] == now["labels_sha256"], "set G pages or labels changed"
any_code = "--any-code" in sys.argv
if not any_code:
    assert frozen["code_sha256"] == now["code_sha256"], "classifier files changed since set G was frozen"
labels = json.loads((G / "labels.json").read_text())["pages"]
src = {s.id: s for s in load_sources()}
try:
    from scholarship_agent.identity import identity
except ImportError:
    identity = None   # code before round 20 has no identity check
rows = []
for p in json.loads((G / "urls.json").read_text())["pages"]:
    s, lab = src[p["source"]], labels[p["id"]]
    pg = load_page(p["id"], p["url"], G)
    kind, why = page_kind(pg)
    opp, _ = extract_opportunity(pg, provider_name=s.provider, provider_type=ProviderType(s.provider_type),
                                 source_type=SourceType.OFFICIAL, country_hint=s.countries, retrieved_at="t",
                                 today=__import__("datetime").date(2026, 10, 18))
    opp.source_authority = str(classify_authority(p["url"], official_domains=s.official_domains, page_kind=kind,
                                                  source_type=SourceType.OFFICIAL, title=pg.title))
    if identity:
        idn = identity(opp, page_title=getattr(pg, "html_title", "") or pg.title, h1=getattr(pg, "h1", ""),
                       text=pg.text, page_kind=kind)
    else:
        idn = {"state": "confirmed" if kind == "opportunity" else "rejected", "reasons": []}
    decision = "accepted" if kind == "opportunity" and idn["state"] == "confirmed" else \
        "review" if kind == "opportunity" or idn["state"] == "needs_review" else "rejected"
    rows.append({"id": p["id"], "label": lab["kind"], "programme": lab["programme"], "ambiguous": lab["ambiguous"],
                 "kind": kind, "identity": idn["state"], "decision": decision, "title": opp.title[:70],
                 "why": why, "identity_reasons": idn["reasons"]})


def score(rs):
    prog = [r for r in rs if r["programme"]]
    non = [r for r in rs if not r["programme"]]
    return {"pages": len(rs), "programme_pages": len(prog), "other_pages": len(non),
            "page_kind_correct": sum(r["kind"] == r["label"] for r in rs),
            "kind_false_accept": sum(r["kind"] == "opportunity" for r in non),
            "kind_false_reject": sum(r["kind"] != "opportunity" for r in prog),
            "pipeline_false_accept": sum(r["decision"] == "accepted" for r in non),
            "pipeline_false_reject": sum(r["decision"] == "rejected" for r in prog),
            "programmes_accepted": sum(r["decision"] == "accepted" for r in prog),
            "programmes_to_review": sum(r["decision"] == "review" for r in prog),
            "others_to_review": sum(r["decision"] == "review" for r in non)}


print(json.dumps({"code": "frozen" if not any_code else "any", "all": score(rows),
                  "unambiguous": score([r for r in rows if not r["ambiguous"]]), "pages": rows}, indent=1, ensure_ascii=False))
