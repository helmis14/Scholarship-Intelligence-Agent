"""Collect set R (round 34, decision benchmark; frozen test set, never used for development): one official programme page per named programme, from funders that are not universities (governments, foundations, companies, international organisations).

Each SPEC is "id|official-domain|search words" (the local SearXNG is asked for the words restricted to the
programme's own official domain, and the first result on that domain is fetched) or "id|-|https://..." (the
programme's official page, fetched directly). Robots-respecting. Pages of
hosts and URLs used by any earlier evaluation or development set are reported as overlaps and not fetched.
No classifier or extractor runs here; which programmes to include was decided by hand before fetching.
Usage: collect.py SPEC...
"""
import json, re, sys, urllib.parse, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.net import Fetcher, FetchError
from scholarship_agent.normalize import normalize_url

K = REPO / "tests" / "heldout_r"
SETS = ["heldout", "heldout_b", "heldout_c", "heldout_d", "heldout_e", "heldout_f", "heldout_g", "heldout_h", "heldout_i",
        "heldout_j", "heldout_k", "heldout_l", "heldout_m", "heldout_n", "heldout_o", "heldout_p", "heldout_q", "dev_r21", "dev_r22", "dev_r23"]
host = lambda u: re.sub(r"^www\d?\.", "", (urllib.parse.urlsplit(u).hostname or "").lower())  # noqa: E731
used_urls, used_hosts = {}, {}
for s in SETS:
    for p in json.loads((REPO / "tests" / s / "urls.json").read_text())["pages"]:
        used_urls[normalize_url(p["url"])] = s
        used_hosts.setdefault(host(p["url"]), s)
prev = json.loads((K / "urls.json").read_text()) if (K / "urls.json").exists() else {"pages": [], "skipped": []}
pages, skipped = prev["pages"], prev["skipped"]
have = {p["id"] for p in pages}
f = Fetcher(min_interval=2.0, retries=1)
for spec in sys.argv[1:]:
    pid, dom, words = spec.split("|", 2)
    if pid in have:
        continue
    if words.startswith("http"):
        hit, dom = words, host(words)
    else:
        q = urllib.parse.urlencode({"q": f"{words} site:{dom}", "format": "json"})
        try:
            res = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/search?" + q, timeout=40).read())["results"]
        except Exception as e:
            skipped.append({"id": pid, "why": f"search failed: {type(e).__name__}"}); continue
        own = [r["url"] for r in res if host(r["url"]) == dom or host(r["url"]).endswith("." + dom)]
        # a home page or a one-word path is rarely the programme page; prefer the first result whose path says so
        deep = [u for u in own if len(urllib.parse.urlsplit(u).path.strip("/")) > 1
                and re.search(r"scholar|fellow|grant|bours|beca|bolsa|stipend|award|apply|eligib|program|funding|beasiswa", u, re.I)]
        hit = (deep or own or [None])[0]
    if not hit:
        skipped.append({"id": pid, "why": "no result on the official domain"}); continue
    if normalize_url(hit) in used_urls or host(hit) in used_hosts:
        skipped.append({"id": pid, "url": hit, "why": f"overlap with set {used_urls.get(normalize_url(hit)) or used_hosts[host(hit)]}"})
        continue
    try:
        resp = f.get(hit)
    except FetchError as e:
        skipped.append({"id": pid, "url": hit, "why": e.reason}); continue
    (K / "pages" / (pid + (".pdf" if resp.is_pdf else ".html"))).write_bytes(resp.data if resp.is_pdf else resp.text.encode("utf-8"))
    pages.append({"id": pid, "url": resp.url, "domain": dom, "query": words})
(K / "urls.json").write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "pages": pages, "skipped": skipped},
                                        indent=1, ensure_ascii=False) + "\n")
print(len(pages), "pages;", len(skipped), "skipped")
