"""The catalogue as the web site shows it (round 47): search with relevance, filters, sorting and facets, one summary
per programme, and the sections of the detail page.

English first: titles and quotations from pages in other languages are shown in English (translate.py) with the
original kept beside them as the evidence; every other value is sent as a code that the page shows in its own language.

The search index is built once per catalogue version (size and time of the database files) and day, and shared by
requests.
"""
from __future__ import annotations

import bisect
import re
import threading
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import countries
from .audit import APPLICANT_KINDS, cycle_status, field_status, funding_type
from .translate import english

LEVEL_WORDS = {
    "bachelor": "s1 bachelor bachelors undergraduate sarjana licenciatura licence bsc",
    "master": "s2 master masters msc mba magister maestria mestrado postgraduate",
    "phd": "s3 phd doctoral doctorate doktor doctorado doctorat",
    "postdoc": "postdoc postdoctoral pascadoktoral",
    "short_course": "summer",
    "exchange": "exchange pertukaran",
}
LEVEL_SYNONYMS = {w: lvl for lvl, ws in LEVEL_WORDS.items() for w in ws.split()}
FUNDING_SYNONYMS = {"penuh": "fully_funded", "fully": "fully_funded", "full": "fully_funded"}
# words every programme here shares, or that only glue a query together
STOP = set("scholarship scholarships beasiswa program programme programs programmes funded funding the for in of and "
           "to a an di untuk dan ke yang beca becas bourse bourses stipendium study studi kuliah luar negeri bidang "
           "jurusan dengan atau tentang".split())
# Round 51: what people study and look for, typed in Indonesian, found through the English words the pages use. The
# Indonesian word itself still counts, but only as a whole word ("seni" is art, not the start of "senior").
WORD_SYNONYMS = {k: v.split() for k, v in {
    "kedokteran": "medicine medical", "dokter": "medicine medical doctor", "kesehatan": "health", "masyarakat": "public community",
    "keperawatan": "nursing", "farmasi": "pharmacy pharmaceutical", "gizi": "nutrition", "psikologi": "psychology",
    "teknik": "engineering", "informatika": "informatics computer computing", "komputer": "computer computing",
    "ilmu": "science sciences", "sains": "science sciences", "matematika": "mathematics", "fisika": "physics",
    "kimia": "chemistry", "biologi": "biology", "pertanian": "agriculture agricultural", "kehutanan": "forestry",
    "perikanan": "fisheries", "kelautan": "marine ocean", "pangan": "food", "lingkungan": "environment environmental",
    "iklim": "climate", "energi": "energy", "hukum": "law laws legal", "ekonomi": "economics economic economy",
    "bisnis": "business", "manajemen": "management", "akuntansi": "accounting", "keuangan": "finance financial",
    "pendidikan": "education", "guru": "teacher teachers teaching", "seni": "art arts", "musik": "music", "desain": "design",
    "arsitektur": "architecture", "sastra": "literature", "bahasa": "language languages linguistics",
    "budaya": "culture cultural", "sejarah": "history", "filsafat": "philosophy", "agama": "religion religious theology",
    "politik": "politics political", "pemerintahan": "government governance", "sosial": "social",
    "internasional": "international", "hubungan": "relations", "pariwisata": "tourism", "jurnalistik": "journalism",
    "komunikasi": "communication communications", "riset": "research", "penelitian": "research", "kanker": "cancer",
    "perempuan": "women female", "wanita": "women female", "disabilitas": "disability disabled",
    "pengungsi": "refugee refugees", "pemuda": "youth young", "pascasarjana": "postgraduate graduate",
    "magang": "internship internships", "pelatihan": "training", "kursus": "course courses",
}.items()}
OPEN_STATES = ("open", "upcoming", "rolling")
SORTS = ("relevance", "deadline", "recent", "title")


def norm(s: str) -> str:
    """Lower case without accents; every script kept ("Líderes" -> "lideres", "奖学金" stays)."""
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(ch))
    return re.sub(r"[\W_]+", " ", s.casefold()).strip()


@dataclass
class Entry:
    summary: dict
    fields: list            # (weight, sorted unique words)
    mentioned: dict         # country code -> weight of the best field that names it
    opp: object = None      # round 51: the record itself, so matching reads no catalogue per request


def _words(text: str) -> list[str]:
    return sorted(set(norm(text).split()))


def _has(words: list[str], token: str, prefix: bool = True) -> bool:
    """A word of the field is the token, or starts with it when `prefix` and the token has five characters or more
    (round 51: was three, so "seni" found "senior" and "data" found "database")."""
    i = bisect.bisect_left(words, token)
    if i >= len(words):
        return False
    return words[i].startswith(token) if prefix and len(token) >= 5 else words[i] == token


def _alternatives(token: str) -> list[tuple[str, bool]]:
    """(word, prefix allowed) that count as the token: its English synonyms, else its singular form too."""
    if token in WORD_SYNONYMS:
        return [(token, False)] + [(w, True) for w in WORD_SYNONYMS[token]]
    out = [(token, True)]
    if len(token) > 4 and token.endswith("ies"):
        out.append((token[:-3] + "y", True))
    elif len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        out.append((token[:-1], True))
    return out


def _next_day(md: str, today: date):
    """The next date (today or later) of a day and month that recur every year; None for 29 February in other years."""
    for y in (today.year, today.year + 1):
        try:
            d = date(y, int(md[:2]), int(md[3:]))
        except ValueError:
            continue
        if d >= today:
            return d.isoformat()
    return None


def next_recurring(o, today: date):
    """Round 49: the nearest coming day of an applicant deadline the page says recurs every year ("15 July of each
    year"). An expected date: the page does not confirm the year."""
    days = [_next_day(d.recurs, today) for d in o.deadlines if d.recurs and str(d.kind) in ("scholarship", "admission")]
    return min((d for d in days if d), default=None)


def summary(store, o, today: date) -> dict:
    tr = english(store, o)
    fs = field_status(o, today)
    cyc = cycle_status(o, today)
    nat_state = fs.get("eligible_countries", {}).get("state")
    n = o.nationality
    dates = sorted({d.date for d in o.deadlines if d.date and d.kind in APPLICANT_KINDS})
    ahead = [d for d in dates if d >= today.isoformat()]
    ft = funding_type(o)["state"]
    return {
        "id": o.id, "title": tr["title"], "title_original": o.title if tr["title"] != o.title else "",
        "language": tr["language"], "translated": bool(tr.get("title_translated")),
        "provider": o.provider_name, "description": o.description[:330], "countries": list(o.destination_countries),
        "countries_inferred": "destination:host" in o.tags,
        "levels": list(o.study_levels), "disciplines": list(o.disciplines[:12]),
        "funding": ft if ft not in ("not_stated", "funding_unclear") else "",
        "nationality": {"mode": n.mode if nat_state == "present" else "check" if nat_state == "needs_review" else "",
                        "countries": list(n.countries[:60])},
        "cycle": cyc["state"] if cyc["state"] != "not_stated" else "",
        "next_deadline": ahead[0] if ahead else None, "last_deadline": dates[-1] if dates and not ahead else None,
        "expected_deadline": None if ahead else next_recurring(o, today),
        "last_checked": (o.last_verified_at or o.updated_at or "")[:10],
        "verification_status": str(o.verification_status),
        "quotes": len({e.snippet for e in o.evidence if e.snippet}), "documents": len(o.required_documents),
        # decisions read from the page but held for checking (second reading disagrees, risk gate, weak quotation)
        "held": [k for k, f in (("eligibility", "eligible_countries"), ("funding", "funding_type"), ("cycle", "cycle"),
                               ("deadline", "deadline")) if fs.get(f, {}).get("state") in ("needs_review", "unsupported")],
    }


def _entry(store, o, today: date) -> Entry:
    s = summary(store, o, today)
    tr = english(store, o)
    quotes = [e.snippet for e in o.evidence if e.snippet] + list(tr["texts"].values())
    texts = [(5, s["title"] + " " + o.title),
             (3, " ".join([o.provider_name, o.institution] + o.programs + o.disciplines
                          + [countries.name(c) for c in o.destination_countries])),
             (2, o.description),
             (1, " ".join(quotes))]
    mentioned: dict = {}
    for w, t in reversed(texts):
        mentioned.update({c: w for c in countries.mentions(t)})
    return Entry(s, [(w, _words(t)) for w, t in texts], mentioned, o)


_CACHE: dict = {}
_LOCK = threading.Lock()


def _signature(store) -> tuple:
    d = Path(store.dir)
    return tuple((f, p.stat().st_size, p.stat().st_mtime_ns) for f in ("catalog.db", "catalog.db-wal")
                 if (p := d / f).exists())


GUESS_RX = re.compile(r"best guess: (\w+)")
# pages about a programme office, a process or a past round rather than a programme ("Contact SFA", "Financial Aid
# Glossary", "Announcement of Successful Applications for ...")
NOT_PROGRAMME_TITLE = re.compile(r"^(?:contact|about|staff|faqs?|frequently asked|glossary|forms?|policies|getting started)\b|"
                                 # a site's home page named after an office, not a programme ("Home - X Scholarships Authority")
                                 r"^home(?:page)?\s*(?:$|[|\u2013-]\s*(?:.*\b(?:authority|office|unit|administration|ministry|"
                                 r"department|financial aid)\b))|"
                                 r"\b(?:contact us|staff|glossary|terminology|faqs?|frequently asked questions|"
                                 r"announcement of successful|successful applic\w+|recipients?|winners?|says|"
                                 r"inspired|resultados|results of|writing your|proposal preparation|projects funded)\b|"
                                 # round 50: a page named only by its office or topic ("Financial Aid | FAU", "Login")
                                 r"^(?:financial aid|financial support|funding|scholarships?|grants?|assistantships|"
                                 r"login|log in|sign in|apply(?: now)?)\s*(?:$|\|)", re.I)   # "Scholarship - X" names X: kept


def listed(o) -> bool:
    """Round 49: the site lists programmes an applicant can apply to. Kept in the catalogue but not listed: pages the
    classifier could not place whose best guess is not an opportunity (news, events, glossaries, research papers,
    hubs that list many programmes, guidance), aggregator and catalogue pages, past mobility projects, and uncertain
    pages that state no term at all."""
    from urllib.parse import urlsplit
    from .extract import NEWS_PATH, NEWS_TITLE
    if o.discovered_via.startswith("adapter:"):
        return o.opportunity_type != "funded_project"
    pi = o.programme_identity or {}
    if pi.get("state") == "rejected" or NOT_PROGRAMME_TITLE.search(o.title):
        return False
    if o.page_type == "scholarship_program":
        return True
    if o.page_type != "unknown":
        return False
    guess = pi.get("page_kind") or (GUESS_RX.search(" ".join(pi.get("reasons") or [])) or [None, ""])[1]
    if (pi and guess != "opportunity") or NEWS_TITLE.search(o.title) \
            or NEWS_PATH.search(urlsplit(o.info_url).path):   # a record never assessed is judged by its terms
        return False
    return bool(o.deadlines or o.funding or o.nationality.mode != "unknown" or o.required_documents)


REBUILD_AFTER = 300   # seconds: while crawls write all day, rebuild at most this often (a rebuild reads every record)


_BUILDING: set = set()


class Built(list):
    """The index entries, with room for what is computed from them once (the vocabulary for spelling)."""
    vocab = None


def _build(store, today: date, where: str, key: tuple) -> list[Entry]:
    entries = Built(_entry(store, o, today) for o in store.list_opportunities() if listed(o))
    with _LOCK:
        _CACHE[where] = (key, entries, time.monotonic())
    return entries


def _build_behind(store, today: date, where: str) -> None:
    """Round 51: a changed catalogue is read again in a thread of its own; requests keep the index they have meanwhile
    (a rebuild reads every record and took seconds, which the visitor who happened to ask paid)."""
    with _LOCK:
        if where in _BUILDING:
            return
        _BUILDING.add(where)

    def run():
        st = None
        try:
            st = type(store)(Path(store.dir))   # a connection of its own: sqlite connections stay in their thread
            _build(st, today, where, (_signature(st), today.isoformat()))
        except Exception:   # the old index stays; the next request after REBUILD_AFTER tries again
            pass
        finally:
            if st is not None:
                st.close()
            with _LOCK:
                _BUILDING.discard(where)

    threading.Thread(target=run, name="site-index", daemon=True).start()


def index(store, today: date) -> list[Entry]:
    where = str(Path(store.dir).resolve())
    key = (_signature(store), today.isoformat())
    with _LOCK:
        hit = _CACHE.get(where)
    if hit is None or hit[0][1] != key[1]:   # nothing yet, or a new day (cycles move with the date): build now
        return _build(store, today, where, key)
    if hit[0] != key and time.monotonic() - hit[2] >= REBUILD_AFTER:
        _build_behind(store, today, where)
    return hit[1]


def warm(store, today: date) -> None:
    """Build the index before the first visitor asks for it (round 51: called when the server starts)."""
    _build_behind(store, today, str(Path(store.dir).resolve()))


def parse_query(text: str) -> list[tuple[str, str]]:
    """(kind, value) terms: country, level, funding or word. Two-word country names are read first. Words every
    programme shares are skipped, unless the query has nothing else."""
    toks = [t for t in norm(text).split() if t]
    stop = STOP if any(t not in STOP for t in toks) else set()
    out, i = [], 0
    while i < len(toks):
        pair = " ".join(toks[i:i + 2]) if i + 1 < len(toks) else ""
        if pair and countries.code(pair):
            out.append(("country", countries.code(pair)))
            i += 2
            continue
        t = toks[i]
        i += 1
        if t in stop:
            continue
        if t in LEVEL_SYNONYMS:
            out.append(("level", LEVEL_SYNONYMS[t]))
        elif t in FUNDING_SYNONYMS:
            out.append(("funding", FUNDING_SYNONYMS[t]))
        elif len(t) > 2 and countries.code(t) and not t.isdigit():
            out.append(("country", countries.code(t)))
        else:
            out.append(("word", t))
    return out


def _term_score(e: Entry, kind: str, value: str) -> int:
    s = e.summary
    if kind == "level" and value in s["levels"]:
        return 4
    if kind == "funding" and s["funding"] == value:
        return 4
    if kind == "country":
        return 4 if value in s["countries"] else e.mentioned.get(value, 0)
    if kind in ("level", "funding"):
        return 0
    alts = _alternatives(value)
    return max((w for w, words in e.fields if any(_has(words, t, pre) for t, pre in alts)), default=0)


def fit(s: dict, citizenship: str) -> str:
    """open | excluded | check | not_stated for a citizen of one country."""
    n = s["nationality"]
    if n["mode"] == "any":
        return "open"
    if n["mode"] in ("include", "exclude"):
        inside = citizenship in n["countries"]
        return "open" if inside == (n["mode"] == "include") else "excluded"
    return "check" if n["mode"] == "check" else "not_stated"


def _ord(iso) -> int:
    try:
        return date.fromisoformat((iso or "")[:10]).toordinal()
    except ValueError:
        return 0


def _deadline_key(s: dict) -> tuple:
    """Open programmes by nearest deadline, then open ones without a date, then unknown, then closed (latest first)."""
    if s["cycle"] in OPEN_STATES and s["next_deadline"]:
        return (0, _ord(s["next_deadline"]))
    if s["cycle"] in OPEN_STATES:
        return (1, 0)
    if s.get("expected_deadline"):   # round 49: the next day of a yearly deadline, expected rather than confirmed
        return (2, _ord(s["expected_deadline"]))
    if s["cycle"] != "closed":
        return (2, 10 ** 7)
    return (3, -_ord(s["last_deadline"]))


LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _edits1(w: str) -> set:
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    return ({a + b[1:] for a, b in splits if b} | {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1}
            | {a + c + b[1:] for a, b in splits if b for c in LETTERS} | {a + c + b for a, b in splits for c in LETTERS})


def _vocabulary(entries) -> tuple[Counter, list]:
    """How many programmes use each word, and the words in order (built once per index)."""
    v = getattr(entries, "vocab", None)
    if v is None:
        counts = Counter(w for e in entries for w in {x for _, words in e.fields for x in words})
        v = (counts, sorted(counts))
        try:
            entries.vocab = v
        except AttributeError:   # a plain list (tests): computed each time
            pass
    return v


def _correct(terms: list, entries) -> tuple[list, list]:
    """Round 51: a word of five letters or more that no programme has is replaced by the closest word that many
    programmes have ("enginering" -> "engineering"); returns the new terms and what was changed."""
    (vocab, known), changed, out = _vocabulary(entries), [], []
    for kind, value in terms:
        if kind == "word" and len(value) >= 5 and value not in WORD_SYNONYMS:
            i, uses = bisect.bisect_left(known, value), 0   # programmes with a word that starts with it (a few at most)
            while i < len(known) and known[i].startswith(value) and uses < 3:
                uses += vocab[known[i]]
                i += 1
            uses += sum(vocab.get(t, 0) for t, _ in _alternatives(value)[1:])
            if uses < 3:   # a typo that a page happens to share ("scholarhsip") still counts as unknown
                best = max((w for w in _edits1(value) if vocab.get(w, 0) >= max(2, 10 * uses)), key=lambda w: vocab[w],
                           default=None)
                if best:
                    changed.append({"from": value, "to": best})
                    value = best
        out.append((kind, value))
    return out, changed


def search(store, today: date, text: str = "", country: str = "", level: str = "", funding: str = "",
           open_only: bool = False, citizenship: str = "", status: str = "", sort: str = "", limit: int = 60,
           offset: int = 0, within_days: int = 0, discipline: str = "") -> dict:
    entries = index(store, today)
    terms, corrected = _correct(parse_query(text), entries)
    country, citizenship = country.upper(), citizenship.upper()
    pool = []
    for e in entries:
        s = e.summary
        if country and country not in s["countries"]:
            continue
        if level and level not in s["levels"]:
            continue
        if discipline and discipline.lower() not in (d.lower() for d in s["disciplines"]):
            continue
        if funding and s["funding"] != funding:
            continue
        if open_only and s["cycle"] not in OPEN_STATES:
            continue
        if within_days and not (s["next_deadline"] and _ord(s["next_deadline"]) - today.toordinal() <= within_days):
            continue
        if status and s["verification_status"] != status:
            continue
        if citizenship and fit(s, citizenship) == "excluded":
            continue
        pool.append(e)
    scored, match = [], "all"
    if terms:
        for e in pool:
            parts = [_term_score(e, k, v) for k, v in terms]
            if all(parts):
                scored.append((sum(parts), e))
        if not scored:   # nothing has every word: the programmes that have most of them, marked as partial matches
            match = "some"
            for e in pool:
                parts = [_term_score(e, k, v) for k, v in terms]
                if sum(1 for p in parts if p) * 2 >= len(parts):
                    scored.append((sum(parts), e))
    else:
        scored = [(0, e) for e in pool]
    sort = sort if sort in SORTS else ("relevance" if terms else "deadline")
    keys = {"relevance": lambda x: (-x[0], _deadline_key(x[1].summary), x[1].summary["title"].lower()),
            "deadline": lambda x: (_deadline_key(x[1].summary), x[1].summary["title"].lower()),
            "recent": lambda x: (-_ord(x[1].summary["last_checked"]), x[1].summary["title"].lower()),
            "title": lambda x: x[1].summary["title"].lower()}
    scored.sort(key=keys[sort])
    if citizenship:   # stable: within the chosen order, programmes that name the applicant's country as eligible first
        scored.sort(key=lambda x: fit(x[1].summary, citizenship) != "open")
    found = [e.summary for _, e in scored]
    facets = {"countries": Counter(c for s in found for c in s["countries"]),
              "levels": Counter(lv for s in found for lv in s["levels"]),
              "disciplines": Counter(d for s in found for d in s["disciplines"]),
              "funding": Counter(s["funding"] for s in found if s["funding"]),
              "cycle": Counter(s["cycle"] for s in found if s["cycle"])}
    limit = max(1, min(int(limit or 60), 200))
    page = found[max(0, int(offset or 0)):][:limit]
    if citizenship:
        page = [s | {"fit": fit(s, citizenship)} for s in page]
    return {"results": page, "count": len(found), "match": match if terms else "", "sort": sort,
            "query": [{"kind": k, "value": v} for k, v in terms], "corrected": corrected,
            "facets": {k: dict(v.most_common(40)) for k, v in facets.items()}}


APPLICANT_DATE_KINDS = ("scholarship", "admission", "opening", "rolling", "test", "recommendation", "document", "event",
                        "other")


# a requirement stated for one group of applicants only ("except for MBA applicants, who require 2 years of work
# experience"): shown, but marked for checking, never as a rule for everyone
SCOPED = re.compile(r"\b(?:except|unless|only for|apart from|in the case of|with the exception)\b|"
                    r"\bfor (?:MBA|LLM|MD|medical|law|engineering|business|PhD|doctoral|master'?s?) (?:\w+ )?(?:applicants|candidates|students)\b",
                    re.I)


# a sentence that gives advice about a document ("contact the advising centre for information about essays") rather
# than asking for it: the document is shown, marked for checking
ADVICE = re.compile(r"\b(?:contact|information about|resources?|guide|tips?|workshops?|webinars?|advis(?:e|ing|ors?))\b", re.I)
ASKS = re.compile(r"\b(?:submit|required?|must|include|upload|attach|provide|send|need(?:ed|s)?|applicants? (?:should|will))\b", re.I)


def _quote(e, tr: dict, scoped_check: bool = False) -> dict:
    """A quotation as the page shows it: the original, its English translation when there is one, and a state
    ("check" when the extractor attached a warning or held the value, or the sentence limits it to some applicants)."""
    if e is None or not e.snippet:
        return {}
    english_text = tr["texts"].get(e.snippet, "")
    scoped = scoped_check and bool(SCOPED.search(english_text or e.snippet))
    return {"quote": e.snippet[:500], "url": e.source_url, "translation": english_text,
            "state": "check" if (e.warnings or e.verdict != "accepted" or scoped) else "answered"}


def details(store, o, today: date) -> dict:
    """The detail page's sections beyond the four decisions: what is paid, what is asked of the applicant, the
    documents, every applicant date, and how to apply. Values are codes and numbers; quotations come with English."""
    tr = english(store, o)
    ev = {}
    for e in o.evidence:
        ev.setdefault(e.field, e)
    q = lambda f: _quote(ev.get(f), tr, scoped_check=not f.startswith(("funding.", "document.")))   # noqa: E731
    covers = [{"kind": c.kind, "covered": c.covered, "full": c.full, "amount": c.amount, "currency": c.currency,
               "period": c.period, **q("funding." + c.kind)} for c in o.funding]
    req = []
    if o.min_gpa is not None:
        req.append({"kind": "min_gpa", "value": o.min_gpa, "scale": o.gpa_scale, **q("min_gpa")})
    if o.min_age is not None or o.max_age is not None:
        req.append({"kind": "age", "min": o.min_age, "max": o.max_age, **(q("max_age") or q("min_age"))})
    if o.min_work_years is not None:
        req.append({"kind": "work_years", "value": o.min_work_years, **q("min_work_years")})
    for r in o.language_requirements:
        req.append({"kind": "language_test", "test": r.test, "minimum": r.minimum, "mandatory": r.mandatory,
                    **q("language." + r.test)})
    if o.requires_supervisor:
        req.append({"kind": "supervisor", **q("requires_supervisor")})
    if o.requires_research_proposal:
        req.append({"kind": "research_proposal", **q("requires_research_proposal")})
    docs = []
    for d in o.required_documents:
        item = {"name": d.name, "category": d.category, "mandatory": d.mandatory, "word_limit": d.word_limit,
                **q("document." + d.name)}
        text = item.get("translation") or item.get("quote", "")
        if ADVICE.search(text) and not ASKS.search(text):
            item["state"] = "check"
        docs.append(item)
    dates = [{"kind": str(d.kind), "date": d.date, "approximate": bool(d.approximate) and not d.date,
              "recurs": d.recurs, "next": _next_day(d.recurs, today) if d.recurs else None,
              "certainty": str(d.certainty), "quote": d.label[:500], "url": d.source_url,
              "translation": tr["texts"].get(d.label, "")}
             for d in sorted(o.deadlines, key=lambda d: (d.date is None, d.date or "")) if str(d.kind) in APPLICANT_DATE_KINDS]
    return {"covers": covers, "duration": {"value": o.funding_duration, **q("funding_duration")} if o.funding_duration else None,
            "requirements": req, "documents": docs, "dates": dates,
            "selection": [{"quote": c, "translation": tr["texts"].get(c, "")} for c in o.selection_criteria[:6]],
            "apply": {"official_url": o.info_url, "application_url": o.application_url},
            "about": {"description": o.description, "institution": o.institution, "programs": list(o.programs[:12]),
                      "disciplines": list(o.disciplines[:24]),
                      "renewal": o.renewal_conditions[:400], "type": o.opportunity_type if o.opportunity_type != "unknown" else ""},
            "language": tr["language"], "title_original": o.title if tr["title"] != o.title else ""}


def stats(store, today: date) -> dict:
    """Numbers for the site's overview band: programmes, open now, destinations, and applicant deadlines per month
    for the next six months."""
    found = [e.summary for e in index(store, today)]
    months = []
    y, m = today.year, today.month
    for _ in range(6):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    per = Counter(s["next_deadline"][:7] for s in found if s["next_deadline"])
    return {"programmes": len(found), "open": sum(1 for s in found if s["cycle"] in OPEN_STATES),
            "closing_30_days": sum(1 for s in found if s["next_deadline"] and _ord(s["next_deadline"]) - today.toordinal() <= 30),
            "destinations": len({c for s in found for c in s["countries"]}),
            "in_english": sum(1 for s in found if s["language"] == "en" or s["translated"]),
            "deadlines_by_month": [{"month": k, "count": per.get(k, 0)} for k in months], "as_of": today.isoformat()}
