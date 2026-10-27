"""English first (round 47): text read from a page in another language gets an English translation, kept next to the
original. The original stays the evidence (quote checks, reports, "show original"); the translation is for reading and
for translating the site into other languages later. Each text is translated once: translations are stored by a hash of
the text (and its role), so a text that appears on many records or runs is paid once and a changed text is translated
again.

Translating needs a model. Production uses Claude through the same switches as every paid call (AI_PROVIDER=anthropic,
ANTHROPIC_ALLOW_PAID=1, ANTHROPIC_MODEL, the per-run caps in cloud_llm.py); without them the run is a dry run that
estimates the cost and translates nothing.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional

from .languages import detect

SYSTEM = ("You translate text from scholarship web pages into English for students. Translate each numbered text "
          "faithfully and completely. Keep the names of programmes, organisations, places and people as written (add a "
          "well-known English name in brackets only when there is one). Keep numbers, dates, amounts and currencies "
          "exactly. Do not add, explain, shorten or summarise. A text that is already English is returned unchanged.")
TITLE_NOTE = ("Texts marked TITLE are page titles: translate the programme's name and leave out the website's name and "
              "navigation words (Home, News, Directory, page numbers) that are not part of it.")
PROMPT_VERSION = "translate-v1"
BATCH_CHARS = 5000
BATCH_ITEMS = 30


def key(text: str, role: str = "text", target: str = "en") -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}\n{target}\n{role}\n{text}".encode()).hexdigest()


def record_language(o) -> str:
    """The language of a record's page: as read from the whole page at extraction, else from its title and quotations
    together (short texts alone mislead)."""
    if getattr(o, "page_language", ""):
        return o.page_language
    sample = " ".join([o.title] + [e.snippet for e in o.evidence[:40] if e.snippet] + [d.label for d in o.deadlines if d.label])
    return detect(sample)[0]


def texts_of(o) -> list[tuple[str, str]]:
    """(role, text) pairs a reader sees for a record: the title and every quotation."""
    out = [("title", o.title)] if o.title and not o.title.startswith("(") else []
    seen = set()
    for t in [e.snippet for e in o.evidence] + [d.label for d in o.deadlines] + list(o.selection_criteria):
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(("text", t))
    return out


def needs_translation(o) -> bool:
    return record_language(o) not in ("en", "")


def pending(store, opps: Iterable) -> list[tuple[str, str]]:
    """(role, text) pairs of non-English records that have no stored translation yet, without repeats."""
    want, seen = [], set()
    for o in opps:
        if not needs_translation(o):
            continue
        for role, t in texts_of(o):
            k = key(t, role)
            if k not in seen:
                seen.add(k)
                want.append((role, t))
    have = store.translations([key(t, r) for r, t in want])
    return [(r, t) for r, t in want if key(t, r) not in have]


def batches(items: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    out, cur, size = [], [], 0
    for it in items:
        n = len(it[1])
        if cur and (size + n > BATCH_CHARS or len(cur) >= BATCH_ITEMS):
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    return out + [cur] if cur else out


def translate_batch(items: list[tuple[str, str]], llm) -> dict[str, str]:
    """key -> English for one request. Items the model leaves out or answers empty stay untranslated."""
    fields = {f"t{i}": "English translation of text " + str(i) for i in range(len(items))}
    user = (TITLE_NOTE + "\n\n" + "\n\n".join(f"[t{i}]{' TITLE' if r == 'title' else ''}\n{t[:2000]}"
                                              for i, (r, t) in enumerate(items))
            + '\n\nAnswer as JSON: {"fields": [{"field": "t0", "value": "<English>", "quote": ""}, ...]}, one item per text.')
    data = llm.complete_json(SYSTEM, user, fields=fields, meta={"purpose": "translate"})
    out = {}
    for item in (data or {}).get("fields") or []:
        f, v = item.get("field", ""), item.get("value")
        if f in fields and isinstance(v, str) and v.strip():
            r, t = items[int(f[1:])]
            out[key(t, r)] = re.sub(r"\s+", " ", v).strip()[:4000]
    return out


def translate_catalog(store, llm, limit: int = 0) -> dict:
    """Translate what is missing for every non-English record. A dry run, a budget stop or a failed request ends the
    run early and keeps what was already stored."""
    opps = store.list_opportunities()
    todo = pending(store, opps)
    if limit:
        todo = todo[:limit]
    done, stopped = 0, ""
    for b in batches(todo):
        try:
            got = translate_batch(b, llm)
        except Exception as e:   # dry run, budget, refusal, network: stop, keep what is stored
            stopped = f"{type(e).__name__}: {e}"[:300]
            break
        store.save_translations([(k, r, t, got[k]) for r, t in b if (k := key(t, r)) in got], getattr(llm, "name", ""))
        done += sum(1 for r, t in b if key(t, r) in got)
    return {"records_in_other_languages": sum(1 for o in opps if needs_translation(o)), "texts_pending": len(todo),
            "translated": done, "stopped": stopped or None}


def english(store, o) -> dict:
    """{"language", "title", "texts": {original: English}} for a record; English records map to themselves. A page
    without a title is named by its provider."""
    if (o.title or "").startswith("(untitled"):
        o = type(o).from_dict(o.to_dict() | {"title": o.provider_name or o.title})
    lang = record_language(o)
    if lang in ("en", ""):
        return {"language": lang or "en", "title": clean_title(o.title, o.info_url), "texts": {}}
    pairs = texts_of(o)
    have = store.translations([key(t, r) for r, t in pairs])
    title = have.get(key(o.title, "title"))
    return {"language": lang, "title": clean_title(title or o.title, o.info_url),   # the model may keep the site's name
            "title_translated": bool(title),
            "texts": {t: have[key(t, r)] for r, t in pairs if r == "text" and key(t, r) in have}}


GENERIC = set("scholarship scholarships fellowship fellowships grant grants award awards bursary bursaries studentship "
              "studentships programme program programmes programs applications application call for international visiting "
              "research graduate doctoral phd master masters short term long the and of introduction home".split())
SITE_WORDS = re.compile(r"^(?:home(?:page)?|official (?:web)?site|news|directory|r[ée]pertoire|portal|page \d+|"
                        r"programa y requisitos|program(?:me)? and requirements|inicio|accueil|startseite|beranda)$", re.I)


def clean_title(title: str, url: str = "") -> str:
    """The programme's name without the website's name or navigation words around it ("X | University Y" -> "X").
    Only a trailing part that names the site, a known navigation word or a leading catalogue number is dropped."""
    t = re.sub(r"\s+", " ", title or "").strip()
    host = re.sub(r"^www\d?\.", "", re.sub(r"^https?://", "", url or "").split("/")[0]).lower()
    labels = {_fold(p).replace("-", "") for p in host.split(".") if len(p) >= 4 and p not in ("info", "html", "www")}
    parts = re.split(r"\s+[|–—»·]\s+|\s+-\s+|\s+::\s+", t)
    if len(parts) > 1 and re.fullmatch(r"\d{2,6}[A-Z]?", parts[0]):
        parts = parts[1:]
    while len(parts) > 1:
        last = parts[-1].strip()
        words = re.findall(r"[a-z0-9]+", _fold(last))
        joined = "".join(words)
        site = any(lb in joined or (len(joined) >= 4 and joined in lb) or any(len(w) >= 5 and w in lb for w in words)
                   for lb in labels)
        rest = set(re.findall(r"[a-z]+", _fold(" ".join(parts[:-1]))))
        if (SITE_WORDS.match(last) or site) and not rest <= GENERIC:   # "Scholarship | Bakala Foundation" keeps the name
            parts = parts[:-1]
        else:
            break
    return " - ".join(p.strip() for p in parts) or t


def _fold(s: str) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(ch))
