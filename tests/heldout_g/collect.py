"""Collect set G (round 20): pages reachable from the 13 registry sources added in round 20 (Indonesia, Vietnam,
Pakistan, Nigeria, Colombia, Chile), before anyone looks at what the classifier says about them.

Per source: its landing page plus up to 4 scholarship-looking links on its official domains, chosen at random
(seed 20). Excluded: URLs and hosts of sets A-F, the round-20 dev pages and the round-19 catalogs. Robots-respecting
fetch; nothing is classified here.
"""
import json, random, re, sqlite3, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.extract import candidate_links, page_from_response
from scholarship_agent.net import Fetcher, FetchError
from scholarship_agent.normalize import normalize_url
from scholarship_agent.registry import load_sources

G = REPO / "tests" / "heldout_g"
NEW = ["id-kemenag-beasiswa", "id-beasiswa-unggulan", "id-kip-kuliah", "vn-vnu-hoc-bong", "vn-vnu-is-hoc-bong",
       "pk-nust-scholarships", "pk-lums-financial-aid", "ng-tetfund", "ng-nddc", "co-icetex-becas",
       "co-minciencias-convocatorias", "cl-agcid-becas", "cl-chileatiende-becas"]
host = lambda u: re.sub(r"^www\d?\.", "", re.match(r"https?://([^/]+)", u).group(1).lower())  # noqa: E731
excl_urls, excl_hosts = set(), set()
for d in ["heldout", "heldout_b", "heldout_c", "heldout_d", "heldout_e", "heldout_f"]:
    for p in json.loads((REPO / "tests" / d / "urls.json").read_text())["pages"]:
        excl_urls.add(normalize_url(p["url"])); excl_hosts.add(host(p["url"]))
for extra in sys.argv[1:]:          # dev page lists and round-19 catalogs
    if extra.endswith(".json"):
        excl_urls |= {normalize_url(u) for u, _ in json.loads(Path(extra).read_text())}
    else:
        excl_urls |= {normalize_url(r[0]) for r in sqlite3.connect(extra).execute("SELECT json_extract(data, '$.info_url') FROM opportunities")}
src = {s.id: s for s in load_sources()}
f, rnd, out, skipped = Fetcher(min_interval=2.0, retries=1), random.Random(20), [], []
for sid in NEW:
    s = src[sid]
    try:
        r = f.get(s.url)
    except FetchError as e:
        skipped.append({"source": sid, "url": s.url, "why": e.reason}); continue
    pg = page_from_response(r)
    cands = [h for h, _ in candidate_links(pg) if any(host(h) == d or host(h).endswith("." + d) for d in s.official_domains)]
    rnd.shuffle(cands)
    picks = [s.url] + cands
    n = 0
    for u in picks:
        if n >= 5:
            break
        if normalize_url(u) in excl_urls or host(u) in excl_hosts or any(normalize_url(u) == normalize_url(o["url"]) for o in out):
            skipped.append({"source": sid, "url": u, "why": "overlaps an earlier set or the dev pages"}); continue
        try:
            resp = r if u == s.url else f.get(u)
        except FetchError as e:
            skipped.append({"source": sid, "url": u, "why": e.reason}); continue
        pid = f"{sid}-{n}"
        (G / "pages" / (pid + (".pdf" if resp.is_pdf else ".html"))).write_bytes(resp.data if resp.is_pdf else resp.text.encode("utf-8"))
        out.append({"id": pid, "url": resp.url, "source": sid})
        n += 1
(G / "urls.json").write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "pages": out, "skipped": skipped},
                                        indent=1, ensure_ascii=False) + "\n")
print(len(out), "pages;", len(skipped), "skipped")
