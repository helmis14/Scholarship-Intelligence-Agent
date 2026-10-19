"""Who is who in a scholarship: the funder (pays), the provider (offers or runs it), the host (where the scholar
studies), the administrator (handles applications for someone else) and partners. Each party comes from one
sentence that states the role; nothing is inferred from a programme's name ("Khalifa University Scholarship" does
not say who pays). The funder and provider roles are re-checked with evidence.organisation_role.
"""

from __future__ import annotations

import re

from .evidence import organisation_role

_CONN = r"(?:of|for|and|the|on|in|de|del|la|las|los|le|du|des|da|do|dos|für|und|van|di|e|y|&)"
_WORD = r"[A-ZÀ-Ý][\w'’.&-]*"
# a name: capitalised words joined by short connectors, optionally followed by an acronym in brackets
_ACR = r"\([A-Z][\w .-]{1,24}\)"   # "(MOE)", "(Taiwan)", "(CSC)"
# a name: capitalised words joined by short connectors or ", " (Ministry of Education, Culture and Science), with
# bracketed acronyms anywhere, and an optional trailing organisation noun ("the Japanese government")
ORG = (rf"((?:{_WORD})(?:\s*{_ACR}|\s+(?:{_WORD}|{_CONN}(?=(?:\s+{_CONN})*\s+[A-ZÀ-Ý]))|,\s+(?={_WORD}\s+(?:and|und|y|e|et)\s+[A-ZÀ-Ý])"
       rf"{_WORD}){{0,12}}(?:\s+(?:government|ministry|foundation|council|agency))?)")
ORG_HINT = re.compile(r"ministr|ministère|ministerio|ministerium|kementerian|government|gouvernement|gobierno|"
                      r"regierung|pemerintah|confederation|foundation|fondation|fundación|fundação|stiftung|yayasan|"
                      r"council|agency|agence|agencia|agência|institut|university|universit|college|academy|bureau|"
                      r"organi[sz]ation|organización|organização|commission|department|directorate|\bfund\b|trust|"
                      r"society|association|\bbank\b|lånekassen|forum|alliance|network|union|consortium|partnership", re.I)
ACRONYM = re.compile(r"^[A-Z][A-Z0-9&-]{1,9}$")
SCHEME_ONLY = re.compile(r"^(?:the\s+)?(?:scholarships?|fellowships?|programmes?|programs?|grants?|awards?|scheme)$", re.I)
PATTERNS = [   # (role, regex); the name is group 1
    ("funder", rf"\b(?:funded|financed|sponsored|paid)\s+(?:\w+\s+){{0,2}}?by\s+(?:the\s+)?{ORG}"),
    ("funder", rf"\b(?:funding source|funded by|funder|sponsor)\s*:\s*(?:the\s+)?{ORG}"),
    ("funder", rf"\b(?:dibiayai|didanai|financiad[oa]s?|financé(?:e|s)?|gefördert)\s+(?:\w+\s+){{0,2}}?(?:oleh|por|par|von|vom)\s+"
               rf"(?:la |el |le |der |dem |the )?{ORG}"),
    ("provider", rf"(?:^|[.;:]\s+|\bthe\s+){ORG}\s+(?:also\s+|annually\s+)?(?:offers|awards|provides|grants|runs)\b"
                 rf"[^.]{{0,80}}?\b(?:scholarships?|fellowships?|grants?|bursar(?:y|ies)|stipends?|awards?)"),
    ("provider", rf"\b(?:scholarships?|fellowships?|grants?|becas?|bolsas?|bourses?|beasiswa)\s+(?:is|are|will be|were)\s+"
                 rf"(?:offered|awarded|provided|granted|funded)\s+by\s+(?:the\s+)?{ORG}"),
    ("administrator", rf"\b(?:administered|administrated|managed|coordinated)\s+by\s+(?:the\s+)?{ORG}"),
    ("administrator", rf"\b{ORG},?\s+(?:como|as)\s+(?:la\s+|the\s+)?(?:Oficina Nacional de Enlace|national (?:liaison|focal) "
                      rf"(?:office|point))"),
    ("partner", rf"\b(?:in (?:collaboration|cooperation|partnership) with|with the support of|em (?:cooperação|colaboração) "
                rf"com|en (?:colaboración|cooperación) con|in Zusammenarbeit mit|en partenariat avec|kerja sama dengan)\s+"
                rf"(?:the\s+|la\s+|el\s+|a\s+|o\s+)?{ORG}"),
    ("host", rf"\b(?:study|studies|studying|enrol(?:led)?|admitted|pursue \w+ (?:degree|studies))\s+(?:at|in)\s+(?:the\s+)?"
             rf"{ORG}"),
]
_RX = [(role, re.compile(rx)) for role, rx in PATTERNS]


def _clean(name: str) -> str:
    name = re.sub(rf"(?:\s+{_CONN})+$", "", " ".join(name.split()))
    name = re.sub(r"^(?:The|El|La|Le|Les|Los|Las|Der|Die|Das|O|A|Il)\s+", "", name.strip(" ,.;:"))
    return name.strip(" ,.;:")


def _is_org(name: str) -> bool:
    if SCHEME_ONLY.match(name):
        return False
    return bool(ORG_HINT.search(name) or ACRONYM.match(name))


def extract_parties(text: str, limit: int = 8) -> list[dict]:
    """[{name, role, quote}] in page order; one entry per (name, role)."""
    out, seen = [], set()
    for line in (text or "").split("\n"):
        if len(line) > 1200:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", line):
            for role, rx in _RX:
                for m in rx.finditer(sent):
                    name = _clean(m.group(1))
                    if len(name) < 3 or len(name.split()) > 14 or not _is_org(name):
                        continue
                    if role in ("funder", "provider"):
                        checked, _why = organisation_role(name, sent)
                        if checked not in ("funder", "provider"):
                            continue   # the sentence does not bear the role out
                        role = checked
                    key = (name.lower(), role)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"name": name, "role": role, "quote": " ".join(sent.split())[:300]})
                    if len(out) >= limit:
                        return out
    return out


def payer(parties: list[dict]) -> dict | None:
    """The party the page says funds the award, else the one it says offers it; never a host or partner."""
    return next((p for p in parties if p["role"] == "funder"), None) or \
        next((p for p in parties if p["role"] == "provider"), None)
