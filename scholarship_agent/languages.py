"""Language registry (languages.json): one place for the words the agent reads and searches with.

Discovery takes concept terms (scholarship, tuition waiver, doctoral funding ...) and native country names from
here; parsing takes month names, deadline words, number words and duration units. Nothing is translated: values
are read in the page's own language and evidence stays in the original text.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

PATH = Path(__file__).with_name("languages.json")
# number words that are also everyday words in another registered language ("to" = 2 in Danish, "en" = 1 in Swedish)
AMBIGUOUS_NUMBER_WORDS = {"to", "en", "et", "een", "ett", "sei", "bir"}
SCRIPTS = [("ja", r"[぀-ヿ]"), ("ko", r"[가-힯]"), ("zh", r"[一-鿿]"), ("th", r"[฀-๿]"),
           ("hi", r"[ऀ-ॿ]"), ("bn", r"[ঀ-৿]"), ("he", r"[֐-׿]"), ("el", r"[Ͱ-Ͽ]"),
           ("ar", r"[؀-ۿ]"), ("ru", r"[Ѐ-ӿ]")]


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def languages() -> dict:
    return registry()["languages"]


def concepts() -> list[str]:
    return registry()["concepts"]


def country_languages(cc: str) -> list[str]:
    """Languages (besides English) to search a country in: the registry first, then search.COUNTRY_LANGS."""
    row = registry()["countries"].get((cc or "").upper())
    if row:
        return [l for l in row["languages"] if l in languages()]
    from .search import COUNTRY_LANGS
    return [l for l in COUNTRY_LANGS.get((cc or "").upper(), []) if l in languages()]


def native_name(cc: str, lang: str) -> str:
    return registry()["countries"].get((cc or "").upper(), {}).get("names", {}).get(lang, "")


def concept_terms(lang: str, concept: str) -> list[str]:
    return list(languages().get(lang, {}).get("concepts", {}).get(concept, []))


def _merged(key: str) -> dict:
    out: dict = {}
    for lang in languages().values():
        for k, v in lang.get(key, {}).items():
            out.setdefault(k.lower(), v)
    return out


@lru_cache(maxsize=1)
def month_names() -> dict[str, int]:
    return _merged("months")


@lru_cache(maxsize=1)
def number_words() -> dict[str, int]:
    return {k: v for k, v in _merged("numbers").items() if k not in AMBIGUOUS_NUMBER_WORDS}


@lru_cache(maxsize=1)
def unit_words() -> dict[str, str]:
    """duration unit word -> 'year' | 'month' | 'semester'"""
    out: dict[str, str] = {}
    for lang in languages().values():
        for kind, words in lang.get("units", {}).items():
            for w in words:
                out.setdefault(w.lower(), kind)
    return out


def unit_kind(word: str) -> Optional[str]:
    w = (word or "").lower()
    if w in unit_words():
        return unit_words()[w]
    for prefix, kind in (("year", "year"), ("jahr", "year"), ("año", "year"), ("ano", "year"), ("tahun", "year"),
                         ("month", "month"), ("monat", "month"), ("mes", "month"), ("bulan", "month"), ("mois", "month"),
                         ("semester", "semester")):
        if w.startswith(prefix):
            return kind
    if w in ("an", "ans"):
        return "year"
    return None


@lru_cache(maxsize=1)
def deadline_words() -> list[str]:
    seen, out = set(), []
    for lang in languages().values():
        for w in lang.get("deadline", []):
            if w.lower() not in seen:
                seen.add(w.lower())
                out.append(w)
    return out


def words_rx(words) -> str:
    """Alternation for a word list; Latin words get word boundaries, CJK and other scripts do not need them."""
    parts = []
    for w in sorted(set(words), key=len, reverse=True):
        e = re.escape(w).replace(r"\ ", r"\s+")
        parts.append(rf"\b{e}\b" if re.match(r"[A-Za-zÀ-ɏ]", w) else e)
    return "|".join(parts)


# ------------------------------------------------------------------ normalisation

_DIGITS = {**{chr(0x0660 + i): str(i) for i in range(10)}, **{chr(0x06F0 + i): str(i) for i in range(10)},
           **{chr(0xFF10 + i): str(i) for i in range(10)}, "٫": ".", "٬": ","}


def ascii_digits(s: str) -> str:
    """Arabic-Indic, Persian and full-width digits as ASCII, character for character (offsets are unchanged, so
    a match found in the result can be cut from the original text)."""
    return "".join(_DIGITS.get(ch, ch) for ch in s or "")


def normalize_text(s: str) -> str:
    """For matching only (never stored as evidence): NFC, ASCII digits, no-break spaces as spaces, one space."""
    s = unicodedata.normalize("NFC", ascii_digits(s or ""))
    return " ".join(s.replace(" ", " ").replace(" ", " ").split())


# ------------------------------------------------------------------ detection

def detect(text: str, declared: str = "") -> tuple[str, float]:
    """(language code, confidence 0-1) of a page. The page's own <html lang> wins when it names a registered
    language; otherwise the script decides, and for Latin script the share of each language's stopwords."""
    d = (declared or "").lower().split("-")[0].split("_")[0]
    if d == "nb" or d == "nn":
        d = "no"
    if d in languages():
        return d, 1.0
    sample = (text or "")[:6000]
    if not sample.strip():
        return "", 0.0
    letters = [ch for ch in sample if ch.isalpha()]
    if not letters:
        return "", 0.0
    for code, rx in SCRIPTS:
        n = len(re.findall(rx, sample))
        if n / len(letters) > 0.2:
            if code == "zh" and re.search(r"[぀-ヿ]", sample):
                return "ja", 0.9
            if code == "ar" and re.search(r"[ٹڈڑںےۓ]", sample):
                return "ur", 0.8          # letters Urdu has and Persian does not
            if code == "ar" and re.search(r"[پچژگ]", sample):
                return "fa", 0.8
            if code == "ru" and re.search(r"[іїєґ]", sample, re.I):
                return "uk", 0.8
            return code, 0.9
    words = re.findall(r"[a-zà-ɏḀ-ỿ']+", sample.lower())   # Ḁ-ỿ: Vietnamese letters with two diacritics
    if not words:
        return "", 0.0
    total = len(words)
    best, score = "", 0.0
    for code, lang in languages().items():
        stop = set(lang.get("stopwords", []))
        if not stop:
            continue
        s = sum(1 for w in words if w in stop) / total
        if s > score:
            best, score = code, s
    return (best, round(min(1.0, score * 3), 2)) if score >= 0.05 else ("", 0.0)


# Languages whose programme-page words are written into extract.py's own patterns (before round 21).
BUILTIN_PAGE_LANGS = {"en", "de", "fr", "es", "pt", "it", "nl", "no", "sv", "da", "pl", "id", "ja", "ko", "zh", "ar",
                      "fi", "el", "ru", "tr"}
PAGE_GROUPS = ("scholarship", "eligibility", "deadline", "application", "benefit", "requirement", "listing",
               "guidance", "news")


def page_vocabulary(lang: str) -> dict:
    """The words a programme page uses in `lang`, per group (languages.json "page"; each block lists the official
    pages its words were read from under "sources")."""
    return languages().get(lang, {}).get("page", {})


def has_page_vocabulary(lang: str) -> bool:
    return lang in BUILTIN_PAGE_LANGS or bool(page_vocabulary(lang))


def page_terms(group: str) -> str:
    """"|w1|w2..." for appending to a regex alternation; "" when no language lists words for `group`."""
    words = sorted({w for lang in languages() for w in page_vocabulary(lang).get(group, [])}, key=len, reverse=True)
    return "".join("|" + re.escape(w) for w in words)
