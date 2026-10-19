"""Overlap check against sets A-E and the freeze manifest for set F.

Writes tests/heldout_f/manifest.json: per page the URL, snapshot sha256 and size; the labels sha256; and the overlap
findings (shared domains, shared normalised URLs, identical page text, shared provider names). Run after labelling,
before any evaluation; re-running later must reproduce the same hashes.
"""
import hashlib, json, re, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.heldout import load_page
from scholarship_agent.normalize import normalize_url

E = REPO / "tests" / "heldout_f"
OTHERS = {"A": REPO / "tests" / "heldout", "B": REPO / "tests" / "heldout_b", "C": REPO / "tests" / "heldout_c",
          "D": REPO / "tests" / "heldout_d", "E": REPO / "tests" / "heldout_e"}
host = lambda u: re.sub(r"^www\d?\.", "", re.match(r"https?://([^/]+)", u).group(1).lower())  # noqa: E731
fold = lambda t: " ".join((t or "").lower().split())  # noqa: E731

e_pages = json.loads((E / "urls.json").read_text())["pages"]
other = []
for name, root in OTHERS.items():
    for p in json.loads((root / "urls.json").read_text())["pages"]:
        pg = load_page(p["id"], p["url"], root)
        other.append({"set": name, **p, "text_sha": hashlib.sha256(fold(pg.text).encode()).hexdigest() if pg else None})
other_hosts = {host(o["url"]) for o in other}
other_urls = {normalize_url(o["url"]) for o in other}
other_text = {o["text_sha"] for o in other if o["text_sha"]}
# provider names labelled or used in A/B/C (for a by-name check, beyond domains)
PROVIDERS = ["ICETEX", "Khalifa", "HBKU", "Lånekassen", "EDUFI", "TICA", "GCUB", "Camões", "Invest Your Talent", "Árni Magnússon", "DAAD", "Fulbright", "Chevening", "Commonwealth", "Erasmus Mundus", "VLIR", "OeAD", "Ernst Mach", "LPDP",
             "Türkiye", "Turkiye", "Stipendium Hungaricum", "Knight-Hennessy", "World Bank", "JJ/WBGSP", "TWAS", "NAWA",
             "Böll", "Boell", "Carolina", "Colfuturo", "Pronabec", "JSPS", "Wellcome", "Campus France", "Eiffel", "Manaaki",
             "Global Korea", "GKS", "PTDF", "Holland Scholarship", "NL Scholarship"]
rows, issues = [], []
for p in e_pages:
    f = next((E / "pages").glob(f"{p['id']}.*"), None)
    data = f.read_bytes() if f else b""
    pg = load_page(p["id"], p["url"], E)
    text = pg.text if pg else ""
    row = {"id": p["id"], "url": p["url"], "file": f.name if f else None, "bytes": len(data),
           "sha256": hashlib.sha256(data).hexdigest(), "text_sha": hashlib.sha256(fold(text).encode()).hexdigest()}
    if host(p["url"]) in other_hosts:
        issues.append({"id": p["id"], "issue": "domain also in A-E", "domain": host(p["url"])})
    if normalize_url(p["url"]) in other_urls:
        issues.append({"id": p["id"], "issue": "same URL as a page in A-E"})
    if text and row["text_sha"] in other_text:
        issues.append({"id": p["id"], "issue": "identical page text to a page in A-E"})
    named = sorted({n for n in PROVIDERS if re.search(re.escape(n), text, re.I)})
    if named:
        row["mentions_providers_from_abc"] = named
    rows.append(row)
labels = (E / "labels.json").read_bytes()
manifest = {"set": "F", "fetched": "2026-10-18", "pages": rows, "labels_sha256": hashlib.sha256(labels).hexdigest(),
            "overlap": {"compared_with": {k: len(json.loads((v / "urls.json").read_text())["pages"]) for k, v in OTHERS.items()},
                        "issues": issues}}
(E / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
print("pages", len(rows), "labels sha", manifest["labels_sha256"][:16], "overlap issues", issues)
for r in rows:
    if r.get("mentions_providers_from_abc"):
        print("  mentions:", r["id"], r["mentions_providers_from_abc"])
