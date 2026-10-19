"""Evidence reliability: source authority, whether a quotation substantiates a value, deadline validation.

Used by extraction (to label each deadline), by verification (to decide what may be confirmed) and by reporting.
The rule throughout: a page being official is necessary, never sufficient. A value is confirmed only when an
official page's verbatim quotation states that value, for this programme, applicant and cycle.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional
from urllib.parse import urlsplit

from . import countries
from .models import Deadline, DeadlineKind, SourceAuthority, SourceType

# Sites that list or rewrite other providers' scholarships. Discovery aids only, never the authority.
AGGREGATOR_DOMAINS = {
    "titansabroad.org", "scholars4dev.com", "schoters.com", "scholarships.com", "fastweb.com", "mastersportal.com",
    "phdportal.com", "bachelorsportal.com", "scholarshipportal.com", "studyportals.com", "scholarshiptab.com",
    "globaladmissions.com", "gslscholarship.com", "internationalscholarships.com", "mbbsinvietnam.com",
    "opportunitydesk.org", "opportunitiesforafricans.com", "afterschoolafrica.com", "wemakescholars.com",
    "scholarshipsads.com", "scholarshipdb.net", "myscholarshipcentral.com", "scholarship-positions.com",
    "scholarshipregion.com", "youthop.com", "opportunitiescorners.com", "estudarfora.org.br", "mystipendium.de",
    "onlinestudies.com.br", "onlinestudies.com", "studying-in-germany.org", "quora.com", "reddit.com",
    "medium.com", "facebook.com", "linkedin.com", "youtube.com", "indbeasiswa.com", "beasiswa.id",
    "scholarshipscorner.website", "greatyop.com", "ilmkidunya.com", "studyabroadnations.com", "mladiinfo.eu",
}
# Not the provider, but accountable bodies that relay external awards accurately enough to cite as secondary.
TRUSTED_SECONDARY_DOMAINS = {"globalscholarships.stanford.edu", "educationusa.state.gov", "iie.org",
                             "stipendiumplus.de", "studyinjapan.go.jp"}
GOV_RX = re.compile(r"(?:^|\.)(?:gov|go|gob|gouv|govt|gc|gv|mil)\.[a-z]{2,3}$|\.gov$|\.gouv\.fr$|\.gc\.ca$|"
                    r"(?:^|\.)(?:europa\.eu|un\.org|unesco\.org|oas\.org)$|bund\.de$|\.admin\.ch$|bmbf\.de$", re.I)
EDU_RX = re.compile(r"(?:^|\.)(?:edu|ac|uni|univ)\.[a-z]{2,3}$|\.edu$|(?:^|\.)uni-[a-z-]+\.de$", re.I)
LISTING_TITLE = re.compile(r"\b(?:top|best|list of|\d+\+?)\s.{0,40}scholarships?\b|\btop \d+\+?(?=\s)|scholarships? (?:for|in) [A-Z][a-z]+n?s?\b"
                           r"|\bscholarships? directory\b|kalender beasiswa|\bbolsas com inscrições abertas\b", re.I)


_REGISTRY: Optional[set] = None


def registry_domains() -> set:
    """Official domains of every provider in the source registry (a search hit on one of them is the provider's)."""
    global _REGISTRY
    if _REGISTRY is None:
        from .registry import load_sources
        try:
            _REGISTRY = {d for s in load_sources() for d in s.official_domains if "." in d}
        except (OSError, ValueError):
            _REGISTRY = set()
    return _REGISTRY


UNI_HOST = re.compile(r"(?:^|[.-])(?:univ\w*|universit\w*|hochschule\w*|college|polytechn\w*)(?:[.-]|$)", re.I)


def host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _on(h: str, domains) -> bool:
    return any(h == d or h.endswith("." + d) for d in domains)


def is_aggregator(url: str, title: str = "") -> bool:
    h = host(url)
    return _on(h, AGGREGATOR_DOMAINS) or (not GOV_RX.search(h) and not EDU_RX.search(h)
                                          and bool(LISTING_TITLE.search(title or "")))


def classify_authority(url: str, *, official_domains: Optional[list[str]] = None, page_kind: str = "",
                       source_type: SourceType | str = "", structured: bool = False, fetched: bool = True,
                       title: str = "") -> SourceAuthority:
    """Authority of one page for facts about one opportunity. `official_domains` are the provider's own domains
    when known (registry or adapter); for search hits they are unknown and only the domain type can be judged."""
    h = host(url)
    if not fetched:
        return SourceAuthority.LEAD
    if title and LISTING_TITLE.search(title):
        page_kind = "listing"   # "Top 9 government scholarships": a list, even on an official domain
    if structured:
        return SourceAuthority.OFFICIAL_FEED
    if _on(h, TRUSTED_SECONDARY_DOMAINS):
        return SourceAuthority.TRUSTED_SECONDARY
    if is_aggregator(url, title) or str(source_type) in ("aggregator",):
        return SourceAuthority.AGGREGATOR
    own = (bool(official_domains) and _on(h, official_domains)) or _on(h, registry_domains())
    if own or (str(source_type) == "official" and not official_domains):
        if page_kind in ("", "opportunity"):
            return SourceAuthority.PROGRAMME_PAGE
        return SourceAuthority.GOVERNMENT if GOV_RX.search(h) else SourceAuthority.PROVIDER_PAGE
    if GOV_RX.search(h):
        return SourceAuthority.GOVERNMENT
    if EDU_RX.search(h) or UNI_HOST.search(h):
        # an institution's own page; whether it is the funder's page is unknown for a search hit
        return SourceAuthority.PROVIDER_PAGE
    return SourceAuthority.AGGREGATOR


def is_official(authority: str) -> bool:
    return bool(authority) and authority[0] in "1234"


# ------------------------------------------------------------------ deadline clauses

INSTITUTIONAL_RX = re.compile(
    r"\b(?:institut\w*|universit\w*|college|school|department|faculty|nodal|district|state|ministry|officer|official|"
    r"l1|l2|level[- ]?[12]|committee|nominating|endorsing|dno|ino|sno)\s+(?:level\s+)?(?:verification|approval|"
    r"nomination|endorsement|submission of nominations|forwarding|scrutiny)|\bverification\b|"
    r"\bnominations? (?:by|from) (?:the )?(?:universit|institut|embass|ministr)|for (?:institutions|universities|"
    r"officials|nominating bodies|embassies)\b|\bdefective (?:application )?verification\b", re.I)
ROLLING_RX = re.compile(r"\brolling (?:basis|admissions?|deadline)|on a rolling\b|no (?:fixed |set )?deadline|"
                        r"open (?:all|throughout the) year|applications? (?:are|is) accepted (?:at any time|year-round)|"
                        r"first[- ]come,? first[- ]served", re.I)
UNPUBLISHED_RX = re.compile(r"\b(?:to be (?:announced|confirmed|determined)|tba|tbc|will be (?:announced|published|"
                            r"updated|confirmed)|not yet (?:announced|published|open)|coming soon|segera dibuka|"
                            r"akan diumumkan|por anunciar|à venir)\b", re.I)
COUNTRY_SCOPE_RX = re.compile(r"\b(?:applicants?|candidates?|students?|nationals?|citizens?)\s+(?:from|of|in|residing in)\s+"
                              r"|\bfor\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s+(?:applicants|candidates|students|nationals)\b|"
                              r"^\s*[A-Z][A-Za-z ]{2,30}\s*[:–-]\s", re.M)


def clause_before(sentence: str, raw: str, previous_raws: list[str]) -> str:
    """The part of a sentence that belongs to one date: from the end of the previous date up to this one."""
    end = sentence.find(raw)
    if end < 0:
        return sentence
    start = 0
    for r in previous_raws:
        i = sentence.find(r)
        if 0 <= i < end:
            start = max(start, i + len(r))
    return sentence[start:end + len(raw)]


def clause_role(clause: str) -> Optional[DeadlineKind]:
    """INSTITUTIONAL / EVENT when the clause is about someone other than the applicant, else None."""
    from .extract import EVENT_WORDS
    if INSTITUTIONAL_RX.search(clause) and not re.search(r"\b(?:student|applicant|candidate)s?\b(?!\s+verification)",
                                                         clause, re.I):
        return DeadlineKind.INSTITUTIONAL
    if EVENT_WORDS.search(clause) and not re.search(r"deadline|closing|close|submit|apply|bewerbungsschluss|plazo|"
                                                    r"date limite|ditutup", clause, re.I):
        return DeadlineKind.EVENT
    return None


GROUP_SCOPE_RX = re.compile(
    r"\b(?:US|U\.S\.|UK|EU|EEA|non-EU|international|domestic|home|overseas|local|foreign)\s+(?:citizens?|nationals?|"
    r"applicants?|students?|candidates?)(?:\s+(?:resident|residing|living)\s+in\s+(?:the\s+)?[A-Z][\w.]*)?|"
    r"\b(?:new|current|continuing|returning|ongoing|existing)\s+(?:students?|applicants?|scholars?)\b|"
    r"\bmahasiswa baru\b|\byang sedang menempuh\b|\bnouve(?:aux|lles?|l) (?:étudiant|candidat)\w*|"
    r"\bestudiantes de nuevo ingreso\b|\bNeubewerber\w*", re.I)
PROGRAMME_SCOPE_RX = re.compile(
    r"\bdepend(?:s|ent|ing)? (?:up)?on (?:your|the) (?:course|programme|program|degree|department|faculty)|"
    r"\bvar(?:y|ies) (?:by|according to|depending on) (?:the |your )?(?:course|programme|program|department|faculty)|"
    r"\bselon (?:la |le |votre )?(?:formation|programme|fili[eè]re)|\bseg[uú]n (?:el |la |tu )?(?:programa|carrera)|"
    r"\bje nach (?:Studiengang|Programm|Fach)|\btergantung (?:pada )?(?:program|jurusan)", re.I)


def clause_scope(clause: str, sentence: str = "") -> tuple[str, list[str]]:
    """Who a date applies to: ('country', [ISO codes]) for applicants from named countries, ('applicant_group',
    [phrase]) for a category of applicant ("US citizens", "new students"), ('programme', [phrase]) when it depends on
    the course, else ('general', []). `sentence` is the wider sentence; only the programme test reads it."""
    found = sorted(countries.mentions(clause))
    if found and COUNTRY_SCOPE_RX.search(clause):
        return "country", found
    m = GROUP_SCOPE_RX.search(clause)
    if m:
        return "applicant_group", [" ".join(m.group(0).split())]
    m = PROGRAMME_SCOPE_RX.search(clause) or PROGRAMME_SCOPE_RX.search(sentence or "")
    if m:
        return "programme", [" ".join(m.group(0).split())]
    return "general", []


CYCLE_PAIR = re.compile(r"\b(20\d{2})\s?[/–-]\s?(20\d{2}|\d{2})\b")


def cycle_is_past(cycle: Optional[str], today: date) -> bool:
    """A cycle such as 2024/2025 or 2025 whose applications cannot still be open on `today`."""
    if not cycle:
        return False
    m = CYCLE_PAIR.search(cycle)
    years = [int(m.group(1)), int(m.group(2)) if len(m.group(2)) == 4 else 2000 + int(m.group(2))] if m else \
        [int(y) for y in re.findall(r"20\d{2}", cycle)]
    return bool(years) and max(years) < today.year


def validate_deadline(d: Deadline, today: date, *, record_title: str = "", page_programmes: int = 1) -> list[str]:
    """Reasons this deadline cannot be confirmed (empty list = it may be). Never checks officialness: callers do."""
    from .extract import parse_dates
    w: list[str] = []
    if d.kind in (DeadlineKind.INSTITUTIONAL, DeadlineKind.EVENT):
        w.append(f"{d.kind.value} date, not an applicant deadline")
    if d.kind == DeadlineKind.ROLLING:
        return w
    if not d.date:
        w.append("no exact date stated")
        return w
    stated = {x.isoformat() for x, _ in parse_dates(d.label or "") if x}
    if d.date not in stated:
        w.append("date not stated in the evidence quotation")
    if date.fromisoformat(d.date) < today:
        w.append("date has passed (previous cycle or closed)")
    if cycle_is_past(d.cycle, today):
        w.append(f"cycle {d.cycle} is a previous cycle")
    if page_programmes > 1 and record_title:
        words = [t for t in re.findall(r"[A-Za-zÀ-ÿ]{4,}", record_title)
                 if t.lower() not in {"scholarship", "scholarships", "programme", "program", "international",
                                      "students", "student", "government", "fellowship", "funding", "page", "untitled"}]
        if words and not any(t.lower() in (d.label or "").lower() for t in words):
            w.append("page lists several programmes and the quotation does not name this one")
    return w


# ------------------------------------------------------------------ substantiation of other fields

def _numbers(s: str) -> set[float]:
    out = set()
    for m in re.findall(r"\d[\d.,\s'’]*\d|\d", s or ""):
        t = m.replace(" ", "").replace("'", "").replace("’", "")
        for cand in (t.replace(",", ""), t.replace(".", "").replace(",", "."), t):
            try:
                out.add(float(cand))
            except ValueError:
                pass
    k = re.findall(r"(\d+(?:[.,]\d+)?)\s?[kK]\b", s or "")
    out |= {float(x.replace(",", ".")) * 1000 for x in k}
    return out


ELIGIBILITY_RX = re.compile(
    r"\b(?:must|eligib\w*|open to|only (?:for|to)|may apply|can apply|are invited|is available (?:to|for)|"
    r"applicants? (?:from|who|of|with)|candidates? (?:from|of)|citizens? of|nationals? of|nationality\s*:|"
    r"residents? of|holders? of|all countries|any country|countries? (?:listed|below|eligible)|"
    r"warga negara|ciudadan\w+|nacionalidad|ressortissants?|staatsangeh\w+|vatanda\w+|công dân|"
    # round 27: the wordings the nationality rules read ("an Indian passport holder", "hold a nationality in a
    # country outside the EU/EEA", "no restrictions on nationality", "any nationality can apply", "open to Indians")
    r"passport holders?|(?:hold|have) (?:a |the )?nationality|nationals?\b[^.]{0,30}\bnot eligible|"
    r"no (?:restrictions?|limitations?) (?:on|of|regarding) (?:the )?nationality|any nationality|"
    r"(?:from|outside)(?: of)? (?:the )?(?:EU|EEA|European)|non-EU|aimed at|awarded to|offered to)\b", re.I)


# round 30: an item of a requirements list ("A United States citizen or permanent resident", "Be a United States
# citizen", "a non-Canadian requiring a study permit"): the list heading carries the "must"
LIST_ITEM_ELIG = re.compile(r"^\W*(?:[Bb]e\s+)?(?:[Aa]n?\s+)?(?:[A-Z][\w.]+\s+){1,3}(?:[Cc]itizens?|[Nn]ationals?)\b|"
                            r"\ba non-[A-Z][a-z]+\b")


HOST_PHRASE = re.compile(r"\b[A-Z][\w'-]+(?:\s[A-Z][\w'-]+)?\s+(?:higher education\s+)?(?:institutions?|universit\w+|"
                         r"government|embassy|ministry|host|campus|schools?|colleges?)\b|\b(?:in|at|to study in)\s+"
                         r"[A-Z][\w'-]+\b")


def substantiates(field: str, value, quote: str) -> Optional[str]:
    """None when the quotation states this value; otherwise the warning to attach."""
    if not quote or len(quote.strip()) < 4:
        return "no supporting quotation"
    from .extract import _INJ_INSTRUCT
    if _INJ_INSTRUCT.search(quote):
        return "quotation is text addressed to AI systems, not a stated fact"
    if field.startswith("deadline."):
        from .extract import parse_dates
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            if value not in {x.isoformat() for x, _ in parse_dates(quote) if x} and not quote.startswith("JSON-LD"):
                return "date not stated in the quotation"
        return None
    if field == "nationality" and isinstance(value, dict):
        mode, codes = value.get("mode"), value.get("countries") or []
        if len(quote.split()) < 6 and not re.search(r"\b(?:must|only|open to|eligible|may apply)\b", quote, re.I):
            return "quotation is a heading or label, not an eligibility statement"
        item = LIST_ITEM_ELIG.search(quote)
        if not ELIGIBILITY_RX.search(quote) and not item:
            return "quotation does not state who is eligible"
        if item and not ELIGIBILITY_RX.search(quote) and mode in ("include", "exclude") and \
                any(c not in countries.group_members(quote) for c in codes):
            return "quotation does not name every country of the rule"   # a list item states only what it names
        if mode in ("include", "exclude") and codes:
            # "open to French higher education institutions": the country of the host, not of the applicant
            applicant_text = HOST_PHRASE.sub(" ", quote)
            named = countries.group_members(applicant_text)   # "outside the EU/EEA" names its members
            missing = [c for c in codes if c not in named]
            if len(missing) == len(codes) and not re.search(r"\b(?:list|following|eligible countries|see)\b", quote, re.I):
                return "none of the countries is named in the quotation"
        return None
    if field.startswith("funding.") and len(quote.split()) < 4:
        return "quotation is a heading or label, not a funding statement"
    if field == "study_levels" and isinstance(value, list):
        problems = study_levels_supported(value, quote)
        return "; ".join(problems) if problems else None
    if field == "provider" and isinstance(value, str):
        role, why = organisation_role(value, quote)
        return None if role in ("funder", "provider") else why
    if field.startswith(("funding.", "stipend")) and isinstance(value, dict) and value.get("amount"):
        if float(value["amount"]) not in _numbers(quote):
            return "amount not stated in the quotation"
        return None
    if field.startswith("language.") or field in ("max_age", "min_age", "min_gpa"):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if v not in _numbers(quote):
            return "number not stated in the quotation"
    return None


# ------------------------------------------------------------------ organisations and study levels

_FUND_VERB = r"(?:funds?|funded|finances?|financed|sponsors?|sponsored|awards?|awarded|grants?|granted|offers?|offered|" \
             r"provides?|provided|pays?|paid|endows?|endowed|administers?|administered|manages?|managed|runs?|" \
             r"launch(?:es|ed)?|announces?|announced|convoca\w*|ofrece\w*|otorga\w*|offre\w*|octroie\w*|accorde\w*|" \
             r"propose\w*|menawarkan|memberikan|menyediakan|vergibt|vergeben|bietet|fördert)"
_FUND_OBJ = r"(?:scholarships?|grants?|fellowships?|awards?|bursar(?:y|ies)|stipends?|funding|programme|program|" \
            r"scheme|call|beasiswa|becas?|bourses?|stipendi\w*)"
# a study programme "supported by" an institute is not a scholarship funded by it, so "programme" is not here
_FUND_NOUN = r"(?:scholarships?|grants?|fellowships?|awards?|bursar(?:y|ies)|stipends?|funding)"
_HOST = r"(?:organi[sz]ed|hosted|taught|coordinated|delivered|accredited|supported|reviewed|evaluated|selected|" \
        r"decided|made|posted|published|written)"


def organisation_role(name: str, quote: str) -> tuple[str, str]:
    """How a quote connects an organisation to the scholarship: ('funder' | 'provider', why) when it funds or runs
    it; ('linked', why) when it is tied to the scheme but not as its funder (a person should decide); otherwise
    ('host' | 'own_funds' | 'mentioned' | 'absent', why). Being named in the quote is not enough."""
    q = " ".join((quote or "").split())
    n = re.escape(" ".join((name or "").split()))
    if not n or not re.search(n, q, re.I):
        return "absent", "the organisation is not named in the quotation"
    if re.search(r"own (?:funds|money|resources|expense|cost)[^.]{0,40}" + n + r"|" + n + r"[^.]{0,40}own (?:funds|money)",
                 q, re.I):
        return "own_funds", "the quotation is about the applicant's own funds"
    if re.search(rf"\bnot\s+(?:\w+\s+){{0,2}}(?:offered|funded|awarded|provided|paid|financed|sponsored|run)\s+by\s+"
                 rf"(?:the\s+)?{n}|{n}\s+(?:does|do|will)\s+not\s+(?:pay|fund|cover|offer|provide)", q, re.I):
        return "mentioned", "the quotation says this organisation does not fund or offer it"
    funder = [
        rf"\b(?:funded|financed|sponsored|awarded|granted|paid|endowed)\s+(?:\w+\s+){{0,3}}?by\s+(?:funds\s+of\s+)?(?:the\s+)?{n}",
        rf"\b{_FUND_NOUN}\s+(?:\w+\s+){{0,3}}?(?:by|from|of)\s+(?:the\s+)?{n}",
        rf"\bfunds\s+of\s+(?:the\s+)?{n}",
        rf"\b(?:funding organi[sz]ation|funder|financed by|funded by|sponsor|donor)\s*:\s*(?:the\s+)?{n}",
        # the same in the other languages the agent reads
        rf"\b(?:otorgad|financiad|patrocinad|gefördert|finanziert|vergeben|financée?|attribuée?|dibiayai|didanai|"
        rf"disponsori|diberikan)\w*\s+(?:\w+\s+){{0,3}}?(?:por|von|vom|durch|par|oleh)\s+(?:la |el |der |die |dem |le |l'|the )?{n}",
        rf"\b(?:beasiswa|becas?|bourses?|stipendi\w*)\s+(?:\w+\s+){{0,3}}?(?:dari|oleh|de la|del|de|der|des|von)\s+{n}",
        rf"\b(?:von|vom|durch)\s+(?:der |dem |den |die )?{n}\s+(?:\w+\s+)?(?:gefördert|finanziert|vergeben)",
    ]
    if any(re.search(rx, q, re.I) for rx in funder):
        return "funder", "the quotation says this organisation funds the award"
    if re.search(rf"\b{_HOST}\s+(?:\w+\s+){{0,3}}?by\s+(?:the\s+)?(?:[\w&'-]+\s+){{0,8}}?{n}", q, re.I) or \
            re.search(rf"\b(?:study|studies|studying|enrol(?:led)?|admitted)\s+(?:at|in)\s+(?:the\s+)?{n}", q, re.I):
        return "host", "the organisation hosts, organises or decides; the quotation does not say it funds the award"
    # the organisation as the subject of a funding verb ("X offers/awards/provides ... scholarships")
    subj = re.search(rf"(?:^|[.;:]\s*|\bthe\s+|^\W*)({n})(?:\s*\([^)]*\))?\s+(?:also\s+|now\s+|annually\s+|is\s+)?"
                     rf"(?:\w+\s+)?{_FUND_VERB}\b[^.]{{0,80}}?\b{_FUND_OBJ}", q, re.I)
    if subj:
        before = q[:subj.start(1)]
        if not re.search(r"\b(?:to|with|at|for|contact|from|via|through|by)\s+(?:the\s+)?$", before, re.I):
            return "provider", "the quotation says this organisation offers or runs the award"
    # linked to the scheme, but not stated as its funder: a person should decide (needs_review, not a rejection)
    if re.search(rf"\b(?:established|set up|founded|initiated|created|introduced)\s+(?:\w+\s+){{0,2}}?by\s+(?:the\s+)?{n}|"
                 rf"\binitiative\s+(?:of|by|from)\s+(?:the\s+)?{n}|\b(?:a trav[eé]s de|par l'interm[eé]diaire d[eu]|"
                 rf"melalui|über)\s+(?:la |el |l'|le |du |der |die |dem )?{n}", q, re.I):
        return "linked", "the quotation links the organisation to the scheme (established, initiative, through) " \
                         "without saying it funds it"
    contacted = re.search(rf"\b(?:contact|email|e-mail|write to|send\w*\s+(?:\w+\s+){{0,3}}?to|submit\w*\s+(?:\w+\s+){{0,4}}?to)"
                          rf"\s+(?:the\s+)?{n}", q, re.I)
    if not contacted and re.search(rf"\b{_FUND_VERB}\b[^.]{{0,80}}?\b{_FUND_OBJ}", q, re.I):
        return "linked", "the quotation names the organisation next to a funding statement whose subject is something else"
    if contacted or re.search(rf"\b(?:to|with|at|contact|from|via|through)\s+(?:the\s+)?{n}", q, re.I):
        return "mentioned", "the organisation is only addressed or contacted in the quotation"
    return "mentioned", "the quotation names the organisation but not as funder or provider"


LEVEL_WORDS = {
    "bachelor": r"\bbachelor'?s?\b|undergraduates?|\bassociate'?s?\b|\bBA\b|\bBSc\b|licenciatura|sarjana\b|S1\b|"
                r"\bbacheli[eè]r\w*|\blicence\b|\bgrado\b|diploma IV|\bD-?IV\b|Bachelorstudi\w*",
    "master": r"\bmaster'?s?\b|\bMA\b|\bMSc\b|\bM\.Sc?\.|\bgraduates?\b(?! study)|postgraduate taught|magister|maestr[ií]a|S2\b|"
              r"ma[iî]trise|Masterstudi\w*",
    "phd": r"\bph\.?d\.?\b|doctoral|doctorate|postgraduates?\b|\bdoktor\w*|doctorado|S3\b|\bdoctorat\b|\bPromotion\b|"
           r"Promovierend\w*",
    "postdoc": r"post-?docs?\b|postdoctoral|post-doctoral|posdoctor\w*|postdoctorat\w*",
    "short_course": r"short[- ]term|short course|summer school|non-degree|training course|visiting research|"
                    r"formation continue|formaci[oó]n continua|Weiterbildung|kursus singkat",
    "exchange": r"\bexchange\b|visiting (?:student|scholar)s?|semester abroad|free movers?",
}
# a level mentioned as something the applicant already holds, or as excluded, is not a level the award funds
_PREREQ = r"(?:hold(?:s|ing)?|held|holders? of|completed|obtained|earned|earning|with|have|has|having|possess\w*|graduated)" \
          r"\s+(?:(?:a|an|the|their|your|his|her|at least one)\s+)?(?:\w+\s+){0,3}?"
_NEG = r"(?:not (?:\w+ )?(?:for|open to|eligible|available)|no |never\b|nor\b|excluding|except|ineligible|not (?:be )?(?:accepted|considered))" \
       r"[^.;]{0,40}?"


def study_levels_supported(levels: list, quote: str) -> list[str]:
    """Problems with a list of levels for one quotation (empty = every level is stated as offered)."""
    q = " ".join((quote or "").replace("\u2019", "'").replace("\u2018", "'").split())
    problems = []
    for lvl in levels or []:
        rx = LEVEL_WORDS.get(str(lvl))
        if not rx:
            problems.append(f"unknown level {lvl!r}")
            continue
        hits = list(re.finditer(rx, q, re.I))
        if not hits:
            problems.append(f"{lvl} not stated in the quotation")
            continue
        usable = []
        for m in hits:
            before = q[max(0, m.start() - 60):m.start()]
            after = q[m.end():m.end() + 40]
            if re.search(_PREREQ + r"$", before, re.I) and re.match(r"\s*(?:'s\s+)?(?:degree|diploma|qualification)", after, re.I):
                continue   # "holding a doctoral degree", "completed a master's degree"
            if re.search(_NEG + r"$", before, re.I) or re.search(r"(?:not|n't) eligible", after[:40], re.I):
                continue   # "not for undergraduate or PhD study", "... are not eligible"
            usable.append(m)
        if not usable:
            problems.append(f"{lvl} appears only as a prerequisite or an exclusion")
    return problems
