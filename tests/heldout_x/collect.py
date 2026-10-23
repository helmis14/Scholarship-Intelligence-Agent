"""Collect set X (round 45, decision benchmark; frozen test set, never used for development): programme pages reached country by
country. For each country in the language registry a few searches (in English and in the country's own languages) give
official-looking list or home pages on hosts no earlier set used; the links on them that name a scholarship, fellowship, grant,
bursary or award are followed, a few per page. Robots-respecting (sites that refuse automated clients are skipped, never
bypassed). A page is fetched only if neither its address nor its host belongs to a page labelled in an earlier set. No
extractor runs here.
Usage: collect.py [--hosts H] [--per-list K] [--round2 [--shard I/N]]
--round2: a second pass with other queries (government and doctoral scholarship terms), hosts of the first pass left out;
writes urls_search2[_I].json, merged into urls.json before freezing.
"""
import html.parser, json, re, sys, urllib.parse, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.net import Fetcher, FetchError
from scholarship_agent.normalize import normalize_url

S = REPO / "tests" / "heldout_x"
EARLIER = ["heldout", "heldout_b", "heldout_c", "heldout_d", "heldout_e", "heldout_f", "heldout_g", "heldout_h", "heldout_i", "heldout_j",
           "heldout_k", "heldout_l", "heldout_m", "heldout_n", "heldout_o", "heldout_p", "heldout_q", "heldout_r", "heldout_s", "heldout_t", "heldout_u", "heldout_v", "heldout_w", "dev_r21", "dev_r22", "dev_r23"]
SEED_SETS = ["heldout_p", "heldout_q", "heldout_r"]
LISTISH = re.compile(r"list|several|overview|home page|ministry|portal|guidance|index|catalog|programmes? on|fees|admissions page|awards|scholarships", re.I)
TERMS = re.compile(r"scholar|fellow|grant|bursar|award|beca|bolsa|bourse|stipend|beasiswa|stipendi|borse|funding|financial-aid|aid", re.I)
NAMED = re.compile(r"scholarship|fellowship|bursary|bursaries|award|grant\\b|beca\\b|becas|bolsa|bourse|beasiswa|stipend|borsa|stipendium", re.I)
GENERIC = re.compile(r"(?:apply|financial|cost|view|find|learn|types|about|how|what|why|current|past|prospective|information|overview|search|browse|"
                     r"explore|see|read|more|all|list|faq|contact|deadlines?|important|tuition|aid|scholarships? (?:and|&|for|at|office|database|search|"
                     r"opportunities|programs?|programmes?|information|overview|list)\\b|scholarships?$|awards?$|fellowships?$|grants?$)", re.I)
BAD = re.compile(r"\.(?:jpg|jpeg|png|gif|svg|zip|docx?|xlsx?|pptx?|mp4)(?:$|\?)|mailto:|tel:|javascript:|login|signin|sign-in|privacy|cookie|"
                 r"facebook|twitter|linkedin|instagram|youtube|/news|/blog|/events?/|/tag/|/category/|/page/\d|#", re.I)
# the first run of this script (country searches without a host filter) returned mostly scholarship-blog and agent pages; this run
# keeps only hosts that look like a government, an education body or a university
OFFICIAL = re.compile(r"(?:^|\.)(?:gov|gob|gouv|go|govt|gv|edu|ac|univ|uni|universit|college|ministry|minister|min-|mes|mec|moe|mohe|hec|nuffic|daad|campus|fulbright|foundation|fund|fundacion|stiftung|trust)(?:[.-]|$)|universit|unversit|universidad|universite|hochschule|politecnico|fondation|fundacio|stiftung|foundation", re.I)
host = lambda u: re.sub(r"^www\d?\.", "", (urllib.parse.urlsplit(u).hostname or "").lower())  # noqa: E731


class Anchors(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self._href = None; self._text = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href"); self._text = []
    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split()))); self._href = None


def search(q):
    try:
        res = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/search?" + urllib.parse.urlencode({"q": q, "format": "json"}), timeout=40).read())["results"]
    except Exception:
        return []
    return [r["url"] for r in res]


def main():
    argv = sys.argv[1:]
    per_country = int(argv[argv.index("--hosts") + 1]) if "--hosts" in argv else 4
    per_list = int(argv[argv.index("--per-list") + 1]) if "--per-list" in argv else 3
    used_urls, labelled_hosts = set(), set()
    for s in EARLIER:
        f = REPO / "tests" / s / "urls.json"
        if not f.exists():
            continue
        for p in json.loads(f.read_text())["pages"]:
            used_urls.add(normalize_url(p["url"]))
            if p.get("split") != "excluded" or s in ("heldout_t", "heldout_u", "heldout_v", "heldout_w"):
                labelled_hosts.add(host(p["url"]))
    lang = json.loads((REPO / "scholarship_agent" / "languages.json").read_text())
    from scholarship_agent.countries import COUNTRIES
    round2 = "--round2" in argv
    shard = tuple(map(int, argv[argv.index("--shard") + 1].split("/"))) if "--shard" in argv else None
    out = S / ("urls.json" if not round2 else f"urls_search2_{shard[0]}.json" if shard else "urls_search2.json")
    prev = json.loads(out.read_text()) if out.exists() else {"pages": [], "skipped": [], "countries_done": []}
    pages, skipped, done = prev["pages"], prev["skipped"], set(prev.get("countries_done", []))
    have_urls = {normalize_url(p["url"]) for p in pages}
    seen_hosts = {host(p["url"]) for p in pages}
    if round2:   # the first pass (and the registry part merged into urls.json): no page or host again
        for p in json.loads((S / "urls.json").read_text())["pages"]:
            used_urls.add(normalize_url(p["url"])); seen_hosts.add(host(p["url"]))
    fetcher = Fetcher(min_interval=2.0, retries=1)
    for ci, (cc, info) in enumerate(lang["countries"].items()):
        if cc in done or cc not in COUNTRIES or (shard and ci % shard[1] != shard[0]):
            continue
        name_en = COUNTRIES[cc][0]
        queries = [f"{name_en} scholarship 2027 international students eligibility deadline official" if not round2 else
                   f"{name_en} government scholarship for citizens 2026 2027 application"]
        for lg in info.get("languages", [])[:2]:
            L = lang["languages"].get(lg, {})
            con = L.get("concepts", {})
            term = ((con.get("government_scholarship") or con.get("doctoral_funding") or con.get("scholarship")) if round2
                    else con.get("scholarship") or [""])[0]
            nm = info.get("names", {}).get(lg, name_en)
            if term and lg != "en":
                queries.append(f"{term} {nm} {2026 if round2 else 2027}")
        first_url = {}
        for q in queries:
            for u in search(q):
                h = host(u)
                if h and OFFICIAL.search(h) and h not in first_url and h not in labelled_hosts and h not in seen_hosts and normalize_url(u) not in used_urls:
                    first_url[h] = u
        hosts = list(first_url)[:per_country]
        for hi, q_h in enumerate(hosts):
            seed = first_url[q_h]
            if not seed:
                continue
            seen_hosts.add(q_h)
            try:
                resp = fetcher.get(seed)
            except FetchError as e:
                skipped.append({"id": f"x{'2' if round2 else ''}-{cc}-{hi + 1}", "url": seed, "why": e.reason}); continue
            if resp.is_pdf:
                continue
            pid0 = f"x{'2' if round2 else ''}-{cc.lower()}-{hi + 1}"
            (S / "pages" / (pid0 + ".html")).write_text(resp.text, encoding="utf-8")
            pages.append({"id": pid0, "url": resp.url, "domain": q_h, "parent": f"search:{cc}", "anchor": "seed"})
            a = Anchors(); a.feed(resp.text); cands = {}
            for href, text in a.links:
                if not href or BAD.search(href):
                    continue
                u = urllib.parse.urljoin(resp.url, href).split("#")[0]
                if host(u) != host(resp.url) or normalize_url(u) in used_urls or normalize_url(u) in have_urls or normalize_url(u) == normalize_url(resp.url):
                    continue
                if not NAMED.search(text) or GENERIC.match(text) or not 12 <= len(text) <= 140 or len(urllib.parse.urlsplit(u).path.strip("/")) < 6:
                    continue
                cands.setdefault(normalize_url(u), (len(text), u, text))
            for k, (_, u, text) in enumerate(sorted(cands.values(), key=lambda t: -t[0])[:per_list]):
                pid = f"{pid0}-{k + 1}"
                try:
                    r2 = fetcher.get(u)
                except FetchError as e:
                    skipped.append({"id": pid, "url": u, "why": e.reason}); continue
                (S / "pages" / (pid + (".pdf" if r2.is_pdf else ".html"))).write_bytes(r2.data if r2.is_pdf else r2.text.encode("utf-8"))
                pages.append({"id": pid, "url": r2.url, "domain": q_h, "parent": pid0, "anchor": text[:100]})
                have_urls.add(normalize_url(r2.url))
        done.add(cc)
        out.write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "pages": pages, "skipped": skipped,
                                                 "countries_done": sorted(done)}, indent=1, ensure_ascii=False) + "\n")
    print(len(done), "countries;", len(pages), "pages;", len(skipped), "skipped")


if __name__ == "__main__":
    main()
