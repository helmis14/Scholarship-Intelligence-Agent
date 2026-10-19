"""Query generation and replaceable web-search providers.

Providers (pick with SEARCH_PROVIDER or SCHOLAR_SEARCH_PROVIDER, default: first configured):
  brave    Brave Search API. Needs BRAVE_SEARCH_API_KEY. Paid tiers; a free
           tier with a monthly cap has existed - check current terms.
  searxng  A SearXNG instance you run or are allowed to use. Needs SEARXNG_URL
           with the JSON format enabled. No per-query cost when self-hosted.
  none     No web search; discovery runs from the source registry only.

Search results are discovery leads, never evidence: every hit is fetched and
treated as an unverified page, and official-source checks happen in verify.py.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from . import countries

# "scholarship" and friends in the languages official pages are written in.
TERMS = {
    "en": ["scholarship", "fully funded scholarship", "graduate fellowship", "funded PhD position", "studentship"],
    "de": ["Stipendium", "Stipendien für internationale Studierende", "Promotionsstipendium"],
    "fr": ["bourse d'études", "bourses pour étudiants internationaux", "allocation doctorale"],
    "es": ["beca", "becas para estudiantes internacionales", "beca de doctorado"],
    "pt": ["bolsa de estudo", "bolsas para estudantes internacionais", "bolsa de doutorado"],
    "it": ["borsa di studio", "borse di studio per studenti internazionali", "dottorato con borsa"],
    "nl": ["beurs", "studiebeurs internationale studenten"],
    "sv": ["stipendium", "stipendier för internationella studenter"],
    "no": ["stipend", "stipend internasjonale studenter"],
    "da": ["stipendium", "legat internationale studerende"],
    "fi": ["apuraha", "stipendi kansainväliset opiskelijat"],
    "pl": ["stypendium", "stypendia dla cudzoziemców"],
    "cs": ["stipendium", "stipendia pro zahraniční studenty"],
    "hu": ["ösztöndíj", "ösztöndíj külföldi hallgatóknak"],
    "ro": ["bursă", "burse pentru studenți străini"],
    "tr": ["burs", "uluslararası öğrenci bursu"],
    "ru": ["стипендия", "стипендия для иностранных студентов"],
    "ar": ["منحة دراسية", "منح للطلاب الدوليين"],
    "fa": ["بورسیه تحصیلی"],
    "zh": ["奖学金", "国际学生奖学金"],
    "ja": ["奨学金", "留学生 奨学金"],
    "ko": ["장학금", "외국인 유학생 장학금"],
    "id": ["beasiswa", "beasiswa luar negeri", "beasiswa S2 penuh"],
    "ms": ["biasiswa", "biasiswa pelajar antarabangsa"],
    "th": ["ทุนการศึกษา"],
    "vi": ["học bổng", "học bổng du học"],
    "hi": ["छात्रवृत्ति"],
    "el": ["υποτροφία"],
    "he": ["מלגה"],
    "uk": ["стипендія"],
}
COUNTRY_LANGS = {
    "DE": ["de"], "AT": ["de"], "CH": ["de", "fr", "it"], "FR": ["fr"], "BE": ["nl", "fr"], "LU": ["fr", "de"],
    "ES": ["es"], "MX": ["es"], "AR": ["es"], "CL": ["es"], "CO": ["es"], "PE": ["es"], "UY": ["es"], "EC": ["es"],
    "BR": ["pt"], "PT": ["pt"], "IT": ["it"], "NL": ["nl"], "SE": ["sv"], "NO": ["no"], "DK": ["da"], "FI": ["fi"],
    "PL": ["pl"], "CZ": ["cs"], "HU": ["hu"], "RO": ["ro"], "TR": ["tr"], "RU": ["ru"], "UA": ["uk"], "GR": ["el"],
    "IL": ["he"], "SA": ["ar"], "AE": ["ar"], "QA": ["ar"], "EG": ["ar"], "MA": ["ar", "fr"], "TN": ["ar", "fr"],
    "JO": ["ar"], "KW": ["ar"], "OM": ["ar"], "IR": ["fa"], "CN": ["zh"], "TW": ["zh"], "HK": ["zh"], "JP": ["ja"],
    "KR": ["ko"], "ID": ["id"], "MY": ["ms"], "BN": ["ms"], "TH": ["th"], "VN": ["vi"], "IN": ["hi"], "SN": ["fr"],
    "CI": ["fr"], "CM": ["fr"], "CA": ["fr"],
}
LEVEL_WORDS = {"bachelor": "undergraduate", "master": "master's", "phd": "PhD", "postdoc": "postdoctoral",
               "short_course": "short course", "exchange": "exchange"}


def generate_queries(destinations: list[str], levels: list[str], disciplines: list[str],
                     nationality: Optional[str] = None, max_per_country: int = 6) -> list[dict]:
    """Queries per destination: English + each local language, with level/discipline/nationality variants."""
    out = []
    dests = destinations or [""]
    for c in dests:
        cname = countries.name(c) if c else ""
        langs = ["en"] + [l for l in COUNTRY_LANGS.get(c, []) if l != "en"]
        qs: list[tuple[str, str]] = []
        for lang in langs:
            for term in TERMS.get(lang, [])[:2]:
                qs.append((lang, f"{term} {cname}".strip()))
        for lvl in levels or []:
            qs.append(("en", f"{LEVEL_WORDS.get(lvl, lvl)} scholarship {cname} international students".strip()))
        for d in (disciplines or [])[:2]:
            qs.append(("en", f"{d} scholarship {cname}".strip()))
        if nationality:
            qs.append(("en", f"scholarship {cname} for {countries.name(nationality)} students".strip()))
        seen = set()
        for lang, q in qs:
            if q.lower() not in seen and len([x for x in out if x["country"] == c]) < max_per_country:
                seen.add(q.lower())
                out.append({"country": c, "language": lang, "query": q})
    return out


@dataclass
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""
    provider: str = ""
    engines: tuple = ()   # SearXNG: upstream engines that returned this URL


# Words that mark a result as about funding, in the languages the strategy searches. A hit needs one of them in
# its title, snippet or URL to be fetched (results for scholarship queries without any are almost always noise).
FUNDING_WORDS = ("scholar", "fellowship", "grant", "bursar", "funding", "funded", "stipend", "award", "studentship",
                 "financial aid", "tuition", "beasiswa", "beca", "bolsa", "bourse", "allocation", "stipendi", "borsa",
                 "burs", "studiebeurs", "stypendium", "stipendij", "ösztöndíj", "ösztöndij", "học bổng", "hoc bong",
                 "biasiswa", "iskolarship", "scholarship", "ทุน", "奨学", "奖学", "獎學", "장학", "منح", "بورس",
                 "стипенд", "грант", "υποτροφ", "מלגה", "छात्रवृत्ति", "வித்தியா", "ስኮላርሺፕ", "bursa", "udhamini",
                 "phd position", "doctoral", "postdoc")
SPAM_TOKENS = {"porn", "xxx", "sex", "casino", "slot", "slots", "gambling", "betting", "viagra", "escort", "dating",
               "adult", "hentai", "togel", "judi", "gacor", "bokep", "loan", "loans", "crypto"}
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".rar", ".mp4", ".mp3", ".exe", ".apk")


def filter_reason(hit: "SearchHit") -> Optional[str]:
    """Why a search hit should not be fetched, or None to fetch it. Leads only: nothing here marks a page valid."""
    try:
        u = urllib.parse.urlsplit(hit.url)
    except ValueError:
        return "unparseable url"
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or not host:
        return "not a web url"
    if host.replace(".", "").isdigit() or ":" in host:
        return "ip address host"
    import re
    tokens = set(re.split(r"[^a-z0-9]+", host + " " + u.path.lower()))
    if tokens & SPAM_TOKENS:
        return "spam or adult domain"
    if u.path.lower().endswith(SKIP_EXT):
        return "not a page"
    text = f"{hit.title} {hit.snippet} {urllib.parse.unquote(hit.url)}".lower()
    if not any(w in text for w in FUNDING_WORDS):
        return "no funding term in title, snippet or url"
    return None


class SearchProvider(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...

    def search(self, query: str, limit: int = 10, lang: str = "en", page: int = 0) -> list[SearchHit]: ...


JsonGet = Callable[[str, dict], dict]


def _json_get(url: str, headers: dict) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.loads(r.read(2_000_000).decode("utf-8", "replace"))


class SearchError(Exception):
    """Provider failure with a message safe to log (no keys, no auth headers)."""


def _safe_get(get: JsonGet, url: str, headers: dict) -> dict:
    import urllib.error
    try:
        return get(url, headers)
    except urllib.error.HTTPError as e:
        raise SearchError(f"HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SearchError(f"{type(e).__name__}: {getattr(e, 'reason', e)}") from None
    except ValueError:
        raise SearchError("response was not JSON") from None


class BraveSearch:
    name = "brave"
    min_interval = 1.1   # the free plan has allowed 1 query/second; check your plan
    limits = ("Brave Search API: paid per-query plans; a free tier with ~1 query/s and a monthly cap has "
              "existed - check the current plan. Max 20 results per request, offset 0-9 pages.")

    def __init__(self, api_key: Optional[str] = None, get: JsonGet = _json_get):
        self.key = api_key if api_key is not None else os.environ.get("BRAVE_SEARCH_API_KEY", "")
        self.get = get

    def available(self):
        return (bool(self.key), "ok" if self.key else "BRAVE_SEARCH_API_KEY not set")

    def search(self, query, limit=10, lang="en", page=0):
        params = {"q": query, "count": min(limit, 20), "offset": min(max(page, 0), 9)}
        if lang and lang != "en":
            params["search_lang"] = lang
        qs = urllib.parse.urlencode(params)
        doc = _safe_get(self.get, f"https://api.search.brave.com/res/v1/web/search?{qs}",
                        {"Accept": "application/json", "X-Subscription-Token": self.key})
        return [SearchHit(r.get("url", ""), r.get("title", ""), r.get("description", ""), self.name)
                for r in (doc.get("web") or {}).get("results", [])[:limit] if r.get("url")]


class SearxngSearch:
    name = "searxng"   # self-hosted: the upstream engines it queries rate-limit, not SearXNG itself
    limits = ("SearXNG: free, self-hosted metasearch; results depend on the upstream engines it queries, which "
              "may throttle or block an instance that sends many queries. JSON output must be enabled.")

    def __init__(self, base: Optional[str] = None, get: JsonGet = _json_get, pool=None):
        self.base = (base if base is not None else os.environ.get("SEARXNG_URL", "")).rstrip("/")
        self.get = get
        self.unresponsive: list = []   # [engine, reason] pairs from the last response
        self.pool = pool               # search_health.EnginePool: picks engines per query, paces, records health

    @property
    def min_interval(self) -> float:
        return self.pool.interval if self.pool is not None else 2.0

    def available(self):
        return (bool(self.base), "ok" if self.base else "SEARXNG_URL not set")

    def search(self, query, limit=10, lang="en", page=0):
        params = {"q": query, "format": "json", "language": lang or "all", "pageno": page + 1}
        used = self.pool.pick(lang) if self.pool is not None else []   # raises EnginesUnavailable when none is ready
        if used:
            params["engines"] = ",".join(used)
        doc = _safe_get(self.get, f"{self.base}/search?{urllib.parse.urlencode(params)}", {"Accept": "application/json"})
        self.unresponsive = [list(x)[:2] for x in doc.get("unresponsive_engines", []) if isinstance(x, (list, tuple))]
        if self.pool is not None:
            answered = {e for r in doc.get("results", []) for e in (r.get("engines") or [r.get("engine")]) if e}
            self.pool.record(used, answered, self.unresponsive)
        return [SearchHit(r.get("url", ""), r.get("title", ""), r.get("content", ""), self.name,
                          tuple(r.get("engines") or ([r["engine"]] if r.get("engine") else [])))
                for r in doc.get("results", [])[:limit] if r.get("url")]


class FixtureSearch:
    """Deterministic provider for tests and offline demos."""
    name = "fixture"
    min_interval = 0
    limits = "fixture provider (offline)"

    def __init__(self, results: dict[str, list[SearchHit]]):
        self.results = results
        self.queries: list[str] = []

    def available(self):
        return True, "ok"

    def search(self, query, limit=10, lang="en", page=0):
        self.queries.append(query)
        hits = self.results.get(query, self.results.get("*", []))
        return hits[page * limit:(page + 1) * limit]


def default_provider() -> Optional[SearchProvider]:
    choice = (os.environ.get("SEARCH_PROVIDER") or os.environ.get("SCHOLAR_SEARCH_PROVIDER", "")).lower()
    candidates = {"brave": BraveSearch, "searxng": SearxngSearch}
    if choice == "none":
        return None
    order = [choice] if choice in candidates else list(candidates)
    for n in order:
        p = candidates[n]()
        if p.available()[0]:
            return p
    return None
