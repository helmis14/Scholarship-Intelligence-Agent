"""Collect set S (round 36, decision benchmark; frozen test set, never used for development): programme pages reached by
following the links of list pages, one list at a time.

Sets P, Q and R left hundreds of fetched pages out because they were lists of awards, home pages or several-award
pages. This script opens each such page that was saved (never labelled, never used to change a rule), takes the links
of the same site whose address or text names a scholarship, fellowship, grant, bursary or award, and fetches the best few
of them. Robots-respecting (sites that refuse automated clients are skipped, never bypassed). A page is fetched only if
neither its address nor its host belongs to a page that was labelled in any earlier set. No extractor runs here; which
list pages to follow was decided by the reason recorded when they were excluded.
Usage: collect.py [--max-fetches N] [--per-list K]
"""
import html.parser, json, re, sys, urllib.parse
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scholarship_agent.net import Fetcher, FetchError
from scholarship_agent.normalize import normalize_url

S = REPO / "tests" / "heldout_s"
EARLIER = ["heldout", "heldout_b", "heldout_c", "heldout_d", "heldout_e", "heldout_f", "heldout_g", "heldout_h", "heldout_i", "heldout_j",
           "heldout_k", "heldout_l", "heldout_m", "heldout_n", "heldout_o", "heldout_p", "heldout_q", "heldout_r", "dev_r21", "dev_r22", "dev_r23"]
SEED_SETS = ["heldout_p", "heldout_q", "heldout_r"]
LISTISH = re.compile(r"list|several|overview|home page|ministry|portal|guidance|index|catalog|programmes? on|fees|admissions page|awards|scholarships", re.I)
TERMS = re.compile(r"scholar|fellow|grant|bursar|award|beca|bolsa|bourse|stipend|beasiswa|stipendi|borse|funding|financial-aid|aid", re.I)
NAMED = re.compile(r"scholarship|fellowship|bursary|bursaries|award|grant\\b|beca\\b|becas|bolsa|bourse|beasiswa|stipend|borsa|stipendium", re.I)
GENERIC = re.compile(r"(?:apply|financial|cost|view|find|learn|types|about|how|what|why|current|past|prospective|information|overview|search|browse|"
                     r"explore|see|read|more|all|list|faq|contact|deadlines?|important|tuition|aid|scholarships? (?:and|&|for|at|office|database|search|"
                     r"opportunities|programs?|programmes?|information|overview|list)\\b|scholarships?$|awards?$|fellowships?$|grants?$)", re.I)
BAD = re.compile(r"\.(?:jpg|jpeg|png|gif|svg|zip|docx?|xlsx?|pptx?|mp4)(?:$|\?)|mailto:|tel:|javascript:|login|signin|sign-in|privacy|cookie|"
                 r"facebook|twitter|linkedin|instagram|youtube|/news|/blog|/events?/|/tag/|/category/|/page/\d|#", re.I)
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


def main():
    argv = sys.argv[1:]
    max_fetches = int(argv[argv.index("--max-fetches") + 1]) if "--max-fetches" in argv else 600
    per_list = int(argv[argv.index("--per-list") + 1]) if "--per-list" in argv else 3
    used_urls, labelled_hosts = set(), set()
    for s in EARLIER:
        f = REPO / "tests" / s / "urls.json"
        if not f.exists():
            continue
        for p in json.loads(f.read_text())["pages"]:
            used_urls.add(normalize_url(p["url"]))
            if p.get("split") != "excluded":
                labelled_hosts.add(host(p["url"]))
    seeds = []
    for s in SEED_SETS:
        for p in json.loads((REPO / "tests" / s / "urls.json").read_text())["pages"]:
            if p.get("split") == "excluded" and LISTISH.search(p.get("excluded_because", "")) and host(p["url"]) not in labelled_hosts:
                fp = next((REPO / "tests" / s / "pages").glob(p["id"] + ".html"), None)
                if fp:
                    seeds.append((s, p, fp))
    seeds.sort(key=lambda t: (t[0] == "heldout_p", t[1]["id"].startswith("us-")))   # non-US lists first
    prev = json.loads((S / "urls.json").read_text()) if (S / "urls.json").exists() else {"pages": [], "skipped": [], "lists_done": []}
    pages, skipped, done = prev["pages"], prev["skipped"], set(prev.get("lists_done", []))
    have_urls = {normalize_url(p["url"]) for p in pages}
    fetcher = Fetcher(min_interval=2.0, retries=1)
    n = 0
    for s, p, fp in seeds:
        key = f"{s}/{p['id']}"
        if key in done:
            continue
        if n >= max_fetches:
            break
        a = Anchors()
        try:
            a.feed(fp.read_text(errors="ignore"))
        except Exception:
            continue
        base = p["url"]; cands = {}
        for href, text in a.links:
            if not href or BAD.search(href):
                continue
            u = urllib.parse.urljoin(base, href).split("#")[0]
            if host(u) != host(base) or normalize_url(u) in used_urls or normalize_url(u) in have_urls or normalize_url(u) == normalize_url(base):
                continue
            if not NAMED.search(text) or GENERIC.match(text) or not 12 <= len(text) <= 140:
                continue   # the link text must name an award, and not be a generic menu entry
            path = urllib.parse.urlsplit(u).path.strip("/")
            if len(path) < 6:
                continue
            score = (2 if TERMS.search(text) else 0) + (1 if TERMS.search(path) else 0) + min(len(path.split("/")), 4) * 0.2
            cands.setdefault(normalize_url(u), (score, u, text))
        best = sorted(cands.values(), key=lambda t: -t[0])[:per_list]
        for k, (score, u, text) in enumerate(best):
            pid = f"s-{p['id']}-{k + 1}"
            try:
                resp = fetcher.get(u)
            except FetchError as e:
                skipped.append({"id": pid, "url": u, "why": e.reason}); continue
            n += 1
            (S / "pages" / (pid + (".pdf" if resp.is_pdf else ".html"))).write_bytes(resp.data if resp.is_pdf else resp.text.encode("utf-8"))
            pages.append({"id": pid, "url": resp.url, "domain": host(u), "parent": key, "anchor": text[:100]})
            have_urls.add(normalize_url(resp.url))
        done.add(key)
        (S / "urls.json").write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "pages": pages, "skipped": skipped,
                                                 "lists_done": sorted(done)}, indent=1, ensure_ascii=False) + "\n")
    print(len(seeds), "list pages;", len(pages), "pages;", len(skipped), "skipped;", len(done), "lists done")


if __name__ == "__main__":
    main()
