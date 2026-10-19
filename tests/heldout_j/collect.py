"""Collect set J (round 24): programme pages as official catalogues link them.

Per SPEC (lang|tld|query): local SearXNG finds official pages on the domain; each one found is read as a possible
catalogue, and up to LINKS same-site links whose text or address names funding (extract.candidate_links) are fetched,
in a random order (seed 24). Only the linked pages enter the set; the catalogue they came from is recorded. Hosts of
every earlier set and development set are excluded. Robots-respecting; no classifier runs here.
Usage: collect.py SPEC...
"""
import json, random, re, sys, urllib.parse, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.extract import candidate_links, page_from_response
from scholarship_agent.net import Fetcher, FetchError
from scholarship_agent.normalize import normalize_url

J = REPO / "tests" / "heldout_j"
CATALOGUES_PER_SPEC, LINKS = 2, 5
host = lambda u: re.sub(r"^www\d?\.", "", (urllib.parse.urlsplit(u).hostname or "").lower())  # noqa: E731
excl = set(json.loads((J / "exclude_hosts.json").read_text()))
f, rnd = Fetcher(min_interval=2.0, retries=1), random.Random(24)
prev = json.loads((J / "urls.json").read_text()) if (J / "urls.json").exists() else {"pages": [], "skipped": []}
pages, skipped = prev["pages"], prev["skipped"]          # a second run adds to the first
seen = {normalize_url(p["url"]) for p in pages}
excl |= {host(p["catalogue"]) for p in pages}
for spec in sys.argv[1:]:
    lang, tld, q = spec.split("|", 2)
    url = "http://127.0.0.1:8080/search?" + urllib.parse.urlencode({"q": f"{q} site:{tld}", "format": "json"})
    try:
        res = json.loads(urllib.request.urlopen(url, timeout=40).read())["results"]
    except Exception as e:
        skipped.append({"spec": spec, "why": f"search failed: {type(e).__name__}"}); continue
    cats = 0
    for r in res:
        cu, ch = r["url"], host(r["url"])
        if cats >= CATALOGUES_PER_SPEC or not (ch == tld or ch.endswith("." + tld)) or ch in excl:
            continue
        try:
            cat = page_from_response(f.get(cu))
        except FetchError as e:
            skipped.append({"url": cu, "why": e.reason}); continue
        links = [h for h, _ in candidate_links(cat, same_site_only=True) if normalize_url(h) not in seen]
        if not links:
            continue
        cats += 1
        excl.add(ch)
        rnd.shuffle(links)
        n = 0
        for u in links:
            if n >= LINKS:
                break
            seen.add(normalize_url(u))
            try:
                resp = f.get(u)
            except FetchError as e:
                skipped.append({"url": u, "why": e.reason}); continue
            pid = f"{lang}-{len(pages):03d}"
            (J / "pages" / (pid + (".pdf" if resp.is_pdf else ".html"))).write_bytes(
                resp.data if resp.is_pdf else resp.text.encode("utf-8"))
            pages.append({"id": pid, "url": resp.url, "lang": lang, "catalogue": cu})
            n += 1
(J / "urls.json").write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "pages": pages, "skipped": skipped},
                                        indent=1, ensure_ascii=False) + "\n")
print(len(pages), "pages;", len(skipped), "skipped")
