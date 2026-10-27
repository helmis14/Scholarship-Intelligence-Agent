"""Destination countries: today's search hint vs the text extractor (scholarship_agent/destinations.py) vs both.

Labels: tests/destinations_labels.json, 80 single-programme pages from the dev sets (devpool.SETS), labelled by one
person from the page text before the extractor was run on them. "not_stated" = the page gives no destination
(portable awards, "study abroad" in any country). A note starting "institution:" means the country follows only from
the host institution (the University of Stirling is in the UK), not from destination wording.

Sample (sample()): per set, labelled opportunity pages ordered by sha256("<set>/<page id>"); the first 10 from the sets
collected by country search (T, U, W, X: the only ones with search:XX parents), the first 4 from every other set.

Methods
  hint        today's live pipeline, approximated as asked: urls.json parent "search:XX" gives XX, anything else nothing
  hint_chain  the same hint inherited through the parent chain: discovery passes the search country on to the links
              it follows (discovery.py _follow_official_links / _follow_catalogue_links), so this is closer to live
  text        extract_destinations(programme_text(page.text), page.title) alone
  text>hint   the text's countries; the hint only when the text names none
  text&hint   only countries the text and the hint agree on
  text>host   the text's countries; when it names none, host_destination: the country of a university's or
              college's own domain, unless the page speaks of study elsewhere (rules designed on these same labels and
              on the other dev pages, so these are development numbers)
Scores per page: exact (same set; not_stated = empty), wrong (a country not in the label), missing (a label country
not given); precision and recall over country codes.
Usage: python3 tests/destinations_eval.py [--rows]
"""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "tests")]
from devpool import SETS  # noqa: E402

LABELS = REPO / "tests" / "destinations_labels.json"
SEARCH_SETS = {"heldout_t", "heldout_u", "heldout_w", "heldout_x"}


def _urls(s: str) -> dict:
    return {p["id"]: p for p in json.loads((REPO / "tests" / s / "urls.json").read_text())["pages"]}


def sample() -> dict:
    """{page id: set}: the deterministic page sample the labels were written for."""
    out: dict = {}
    for s in SETS:
        pages = json.loads((REPO / "tests" / s / "labels.json").read_text())["pages"]
        ids = sorted((k for k, v in pages.items() if v["kind"] == "opportunity"),
                     key=lambda k: hashlib.sha256(f"{s}/{k}".encode()).hexdigest())
        quota = 10 if s in SEARCH_SETS else 4
        for k in [k for k in ids if k not in out][:quota]:
            out[k] = s
    return out


def hint(parent: str) -> list:
    return [parent.split(":", 1)[1]] if parent.startswith("search:") else []


def chain_hint(s: str, parent: str) -> list:
    for _ in range(5):
        if not parent or parent.startswith("search:"):
            break
        if "/" in parent:
            s, parent = parent.split("/", 1)
        parent = _urls(s).get(parent, {}).get("parent", "")
    return hint(parent or "")


def score(rows: list) -> dict:
    """rows: (predicted codes, label codes) per page; a not_stated label is []."""
    tp = sum(len(set(p) & set(g)) for p, g in rows)
    npred, ngold = sum(len(set(p)) for p, _ in rows), sum(len(set(g)) for _, g in rows)
    return {"n": len(rows), "exact": sum(set(p) == set(g) for p, g in rows),
            "wrong": sum(bool(set(p) - set(g)) for p, g in rows),
            "missing": sum(bool(set(g) - set(p)) for p, g in rows),
            "answered": sum(bool(p) for p, _ in rows),
            "precision": round(tp / npred, 3) if npred else None, "recall": round(tp / ngold, 3) if ngold else None}


def line(name: str, r: dict) -> str:
    f = lambda v: "-" if v is None else f"{v:.3f}"   # noqa: E731
    return (f"{name:12} n={r['n']:3} exact={r['exact']:3} wrong={r['wrong']:3} missing={r['missing']:3} "
            f"answered={r['answered']:3} precision={f(r['precision']):>5} recall={f(r['recall']):>5}")


def main():
    from scholarship_agent.destinations import extract_destinations, host_destination
    from scholarship_agent.extract import extract_nationality, programme_text
    from scholarship_agent.heldout import load_page
    labels = json.loads(LABELS.read_text())
    assert {k: v["set"] for k, v in labels.items()} == sample(), "labels no longer match the deterministic sample"
    pages = []
    for pid, lab in labels.items():
        s = lab["set"]
        u = _urls(s)[pid]
        pg = load_page(pid, u["url"], REPO / "tests" / s)
        body = programme_text(pg.text)
        text, snips = extract_destinations(body, pg.title or "")
        nat, _ = extract_nationality(body)
        host, why = host_destination(u["url"], body, pg.title or "", nat.mode, nat.countries)
        gold = [] if lab["destinations"] == "not_stated" else lab["destinations"]
        h, hc = hint(u.get("parent", "")), chain_hint(s, u.get("parent", ""))
        pages.append({"id": pid, "set": s, "gold": gold, "basis": lab["note"].split(":", 1)[0], "snips": snips,
                      "hint": h, "hint_chain": hc, "text": text, "text>hint": text or h, "text>chain": text or hc,
                      "text&hint": [c for c in text if c in h], "text&chain": [c for c in text if c in hc],
                      "text>host": text or host, "host_why": "" if text else why})
    print(__doc__.split("\n\n")[0] + "\nOne labeller's labels on development pages, not a frozen test set.\n")
    for m in ("hint", "text", "text>hint", "text>host"):
        print(f"== {m}")
        for s in SETS:
            rows = [(p[m], p["gold"]) for p in pages if p["set"] == s]
            if rows:
                print(line(s, score(rows)))
        print(line("pooled", score([(p[m], p["gold"]) for p in pages])) + "\n")
    print("== pooled, all methods")
    for m in ("hint", "hint_chain", "text", "text>hint", "text>chain", "text&hint", "text&chain", "text>host"):
        print(line(m, score([(p[m], p["gold"]) for p in pages])))
    fell = [p for p in pages if not p["text"] and p["text>host"]]
    print(f"\n== host fallback: answered {len(fell)} pages the text left empty; where it gives a wrong country:")
    for p in fell:
        if set(p["text>host"]) - set(p["gold"]):
            print(f"{p['id']:28} host={p['text>host']} gold={p['gold'] or 'not_stated'}  {p['host_why']}")
    print("\n== text by label basis (stated: country named as the place; institution: implied by the host only)")
    for b in ("stated", "institution", "none"):
        print(line(b, score([(p["text"], p["gold"]) for p in pages if p["basis"] == b])))
    if "--rows" in sys.argv:
        print("\n== pages where text or hint differ from the label")
        for p in pages:
            if set(p["text"]) != set(p["gold"]) or set(p["hint_chain"]) != set(p["gold"]):
                print(f"{p['id']:28} gold={p['gold'] or 'not_stated'} hint={p['hint_chain']} text={p['text']} "
                      f"[{p['basis']}]" + "".join(f"\n      {c}: {s[:150]}" for c, s in zip(p["text"], p["snips"])))


if __name__ == "__main__":
    main()
