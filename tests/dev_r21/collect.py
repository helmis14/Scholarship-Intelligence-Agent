"""Collect a multilingual development set (round 21) from official domains via the local SearXNG, robots-respecting.

Countries are split between development and set H so the two never share a country's domains:
development = Indonesia (ac.id), Vietnam (edu.vn), Pakistan (edu.pk), Nigeria (edu.ng), Mexico, Colombia (edu.co),
Brazil (gov.br), Morocco (ac.ma), Egypt (edu.eg). Hosts of sets A-G are excluded. Up to 2 pages per host.
Usage: collect.py OUT_DIR SPEC...   SPEC = lang|tld|query   (OUT_DIR/exclude_hosts.json: more hosts to skip)
"""
import json, re, sys, urllib.parse, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.net import Fetcher, FetchError
from scholarship_agent.normalize import normalize_url

host = lambda u: re.sub(r"^www\d?\.", "", (urllib.parse.urlsplit(u).hostname or "").lower())  # noqa: E731
out_dir, specs = Path(sys.argv[1]), sys.argv[2:]
excl_hosts = set()
for d in ["heldout", "heldout_b", "heldout_c", "heldout_d", "heldout_e", "heldout_f", "heldout_g"]:
    for p in json.loads((REPO / "tests" / d / "urls.json").read_text())["pages"]:
        excl_hosts.add(host(p["url"]))
for extra in (out_dir / "exclude_hosts.json",):
    if extra.exists():
        excl_hosts |= set(json.loads(extra.read_text()))
f = Fetcher(min_interval=2.0, retries=1)
pages, skipped, per_host = [], [], {}
for spec in specs:
    lang, tld, q = spec.split("|", 2)
    url = "http://127.0.0.1:8080/search?" + urllib.parse.urlencode({"q": f"{q} site:{tld}", "format": "json"})
    try:
        res = json.loads(urllib.request.urlopen(url, timeout=40).read())["results"]
    except Exception as e:
        skipped.append({"spec": spec, "why": f"search failed: {type(e).__name__}"}); continue
    n = 0
    for r in res:
        u, h = r["url"], host(r["url"])
        if n >= 6 or not (h == tld or h.endswith("." + tld)):
            continue
        if h in excl_hosts or per_host.get(h, 0) >= 2 or any(normalize_url(u) == normalize_url(p["url"]) for p in pages):
            continue
        try:
            resp = f.get(u)
        except FetchError as e:
            skipped.append({"url": u, "why": e.reason}); continue
        pid = f"{lang}-{len(pages):03d}"
        (out_dir / "pages" / (pid + (".pdf" if resp.is_pdf else ".html"))).write_bytes(
            resp.data if resp.is_pdf else resp.text.encode("utf-8"))
        pages.append({"id": pid, "url": resp.url, "lang": lang, "query": q, "tld": tld})
        per_host[h] = per_host.get(h, 0) + 1
        n += 1
(out_dir / "urls.json").write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "pages": pages,
                                               "skipped": skipped}, indent=1, ensure_ascii=False) + "\n")
print(len(pages), "pages;", len(skipped), "skipped")
