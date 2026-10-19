"""Organisation names: the same body written as an acronym, its full official name, or in another language.

Two kinds of alias, both with a source:
  * page aliases: the page itself writes "Research Grants Council (RGC)". The acronym must spell the initials of the
    name's words (connectors such as "of", "de", "für" may be skipped), so "Swaminathan Research Foundation (MSSRF)"
    is accepted only with its full name and "(Greece)" after a university is never an alias.
  * registry aliases: org_aliases.json, each entry with the official page that states the equivalence.
Names are compared after folding case, accents, articles and punctuation. Nothing else counts: two names that
merely look alike are different organisations.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).with_name("org_aliases.json")
CONNECTORS = {"of", "for", "and", "the", "on", "in", "at", "de", "del", "la", "las", "los", "le", "du", "des", "da",
              "do", "dos", "das", "für", "und", "van", "di", "e", "y", "et", "&", "a", "to"}
_NAME = r"(?:[A-ZÀ-Ý][\w'’.-]*|of|for|and|the|on|in|at|de|del|la|las|los|le|du|des|da|do|dos|für|und|van|di|e|y|et|&)"
PAGE_ALIAS = re.compile(rf"((?:{_NAME})(?:[ ,]+{_NAME}){{0,14}})\s*\(([A-Z][A-Za-z&-]{{1,11}})\)")


def fold(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"\([^)]*\)", " ", s)                       # bracketed acronyms are aliases, not part of the name
    s = re.sub(r"[^\w\s]", " ", s)
    words = [w for w in s.split() if w not in ("the", "el", "la", "le", "les", "los", "las", "der", "die", "das")]
    return " ".join(words)


def _initials_match(words: list[str], acronym: str) -> bool:
    """The acronym's capitals spell the initials of the significant words, in order, using every word."""
    caps = [c for c in acronym if c.isupper() or c.isdigit()]
    sig = [w for w in words if w.lower() not in CONNECTORS]
    if not sig or len(caps) < 2:
        return False
    if len(caps) == len(sig):
        return all(w[0].upper() == c for w, c in zip(sig, caps))
    # acronyms that also take a connector's initial ("Ministry of Education, Culture, Sports, Science and
    # Technology" stays strict; "Coordenação de Aperfeiçoamento de Pessoal de Nível Superior" = CAPES is not
    # guessed): only an exact one-letter-per-word match is accepted, with connectors counted
    allw = [w for w in words if w != "&"]
    return len(caps) == len(allw) and all(w[0].upper() == c for w, c in zip(allw, caps))


def page_aliases(text: str) -> dict[str, str]:
    """{ACRONYM: full name} that the page itself states."""
    out: dict[str, str] = {}
    for m in PAGE_ALIAS.finditer(text or ""):
        words = re.split(r"[ ,]+", m.group(1).strip(" ,"))
        acr = m.group(2)
        # the shortest tail of the captured words whose initials spell the acronym is the name
        for start in range(len(words) - 1, -1, -1):
            tail = words[start:]
            if tail[0].lower() in CONNECTORS:
                continue
            if _initials_match(tail, acr):
                out.setdefault(acr, " ".join(tail))
                break
    return out


@lru_cache(maxsize=1)
def registry() -> list[dict]:
    if not PATH.exists():
        return []
    return json.loads(PATH.read_text(encoding="utf-8"))["organisations"]


def aliases_of(name: str, text: str = "") -> set[str]:
    """Every folded form known for `name`: itself, what the page pairs it with, and registry equivalents."""
    forms = {fold(name)}
    # an acronym the name itself carries in brackets ("... Technology (MEXT) of Japan") is an alias as written
    forms |= {fold(x) for x in re.findall(r"\(\s*([A-Z][A-Za-z&-]{1,11})\s*\)", name or "")}
    pa = page_aliases(text) if text else {}
    for acr, full in pa.items():
        if fold(acr) in forms or fold(full) in forms:
            forms |= {fold(acr), fold(full)}
    for org in registry():
        names = {fold(n) for n in [org["name"]] + org.get("aliases", [])}
        if forms & names:
            forms |= names
    return {f for f in forms if f}


def same_org(a: str, b: str, text: str = "") -> bool:
    """True only when the names are the same after folding or linked by a sourced alias."""
    if not a or not b:
        return False
    return bool(aliases_of(a, text) & aliases_of(b, text))


def describe(name: str, text: str = "") -> dict:
    """The name as written, the aliases that apply, and where each alias comes from."""
    pa = page_aliases(text)
    page = sorted({acr if fold(full) == fold(name) else full for acr, full in pa.items()
                   if fold(name) in (fold(acr), fold(full))})
    reg = next((org for org in registry() if fold(name) in {fold(n) for n in [org["name"]] + org.get("aliases", [])}), None)
    return {"as_written": name, "page_aliases": page,
            "registry": {"name": reg["name"], "aliases": reg.get("aliases", []), "source": reg["source"]} if reg else None}
