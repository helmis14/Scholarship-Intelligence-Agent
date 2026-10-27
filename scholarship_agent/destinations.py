"""Destination countries: where the funded study or research takes place, read from the page's own wording.

Only destination wording counts: "study in Japan", "universities in Canada", "hosted in Germany", "tenable at any UK
university", "studieren in Deutschland", "étudier en France", "estudiar en España", "kuliah di Jepang". A country
named as nationality, residence, a previous degree, an enrolment condition or an office's seat ("citizens of Kenya",
"a degree from a university in India", "enrolled at a university in Denmark", "Fulbright Commission in Egypt") is not
a destination. Precision first: when the wording is not clearly about where the award is held, nothing is returned.
"""

from __future__ import annotations

import re
from functools import lru_cache

from . import countries
from .languages import registry

# Country names pages write in their own language that countries.py does not resolve (read only after a place
# preposition here, so "Inggris" or "Jerman" as a language name never counts).
_EXTRA = """US: EUA, EE. UU., EE.UU., EEUU, Etats-Unis, Estados Unidos de América | CA: Canadá | JP: Japón, Japão, Giappone
IE: Irlanda, Irland, Irlande, Irlandia | HU: Hungría, Ungarn, Hongrie, Hungria, Hongaria, Ungheria
CZ: Tschechien, Tchéquie, République tchèque, República Checa, Chéquia, Ceko, České republice, Česku
TR: Turki, Turquia, Turchia | CN: Tiongkok, Cina | SG: Singapura, Singapur, Singapour | BE: Belgia, Belgio
PL: Polandia, Polônia, Polsce | NL: Holanda, Paesi Bassi | KR: Coreia do Sul, Corea del Sud, Zuid-Korea
GB: Großbritannien, Grande-Bretagne, Gran Bretaña, Inggris, Regno Unito, Northern Ireland | AU: Austrália, Australië
NZ: Nova Zelândia | IT: Itália, Italië | CH: Suíça | AT: Áustria, Oostenrijk | SE: Suécia, Svezia, Zweden
DE: Duitsland, Germania | FR: Frankrijk | ES: Spanje, Spagna | MY: Malásia | TW: Taiwán, Taïwan | IN: Índia
RU: Rússia | AE: Emirados Árabes Unidos, Emiratos Árabes Unidos, Émirats arabes unis, Uni Emirat Arab
TH: Tailândia | GR: Grécia | FI: Finlândia | NO: Noorwegen | DK: Denemarken | MR: Mauritanie | LY: Libye | SD: Soudan
TD: Tchad | KM: Comores | UG: Ouganda | KW: Koweït | RO: Roumanie | BG: Bulgarie | CY: Chypre | MT: Malte | IS: Islande
SK: Slovaquie | HR: Croatie | RS: Serbie"""
# "study in Georgia" is the US state on most pages; "America" is also a continent and a name ("Kent in America")
_NOT_A_DESTINATION = {"georgia", "america"}

# Activity words: the place after them is where the award is held ("to study ... in Japan", "research stay in").
STUDY = (r"stud(?:y|ies|ying)|pursu(?:e|ing)|attend(?:ing)?|hosted|tenable|held at|arriv(?:e|al|ing)|admitted|"
         r"admission|accepted|carried out|take[sn]? place|taking place|fieldwork|forskningsopphold\w*|"
         r"(?:international|foreign|overseas) (?:students?|scholars?|researchers?)|research (?:stays?|visits?|"
         r"periods?|placements?|attachments?|residenc(?:y|ies))|(?:conduct|conducting|carry out|carrying out|"
         r"undertake|undertaking) (?:\w+ ){0,2}research|placements?|internships?|exchange|semester|academic year|"
         r"summer (?:schools?|courses?|programmes?|programs?)|"
         r"studier\w*|studium|studien\w*|forschungsaufenthalt\w*|forschungsvorhaben|promotion|promovier\w*|"
         r"aufenthalt\w*|praktikum|étudi\w*|études?|séjours?|stages?|mobilité|poursuivre|venir|estudi\w*|cursar|"
         r"estancias?|movilidad|pasantías?|estud(?:ar|os)|intercâmbio|sanduíche|estágio|studiare|studeren|studere|"
         r"studera|uddannelse|utdanning|utbildning|opphold|ophold|vistelse|studia|studiów|studovat|studiować|"
         r"pobyt|kuliah|studi|belajar|melanjutkan (?:studi|pendidikan|kuliah)|menempuh (?:studi|pendidikan)|"
         r"pelatihan|diselenggarakan")
# Institution and degree words: the place may also be the applicant's own university or earlier degree, so these
# count only right before the place and only when nothing in the clause points to the applicant's past or home.
PLACE = (r"universit(?:y|ies)|institutions?|colleges?|HEIs?|graduate schools?|research (?:institutions?|"
         r"organi[sz]ations?|cent(?:re|er)s?)|degrees?|master'?s|ph\.?d\.?|doctora(?:l|te)|post-?graduate|"
         r"undergraduate|"
         r"hochschul\w*|universität\w*|einrichtung(?:en)?|universités?|établissements?|doctorat|thèse|formations?|"
         r"universidad(?:es)?|instituci(?:ón|ones)|posgrados?|maestrías?|doctorados?|universidades|instituições|"
         r"doutorado|mestrado|pós-graduação|università|universiteit|universitet|perguruan tinggi|universitas")
# Award words count only in the title ("Becas de Doctorado en Alemania", "Bourses d'études en France").
AWARD = (r"scholarships?|fellowships?|grants?|bursar(?:y|ies)|awards?|stipendi\w*|becas?|bourses?|bolsas?|"
         r"beasiswa|borse?|beurs(?:en)?|stipend(?:ier|ium)?")
STUDY_RX = re.compile(rf"(?<!\w)(?:{STUDY})(?!\w)", re.I)
PLACE_RX = re.compile(rf"(?<!\w)(?:{PLACE})(?!\w)", re.I)
AWARD_RX = re.compile(rf"(?<!\w)(?:{AWARD})(?!\w)", re.I)
# German puts the verb after the place: "die in Deutschland studieren möchten"
STUDY_AFTER = re.compile(r"\s*(?:zu\s+)?(?:studier\w*|forsch\w*|promovier\w*)", re.I)
BREAK = re.compile(r"[;:!?|–—]| - ")   # not ".": inside a sentence it is "U.S." or "Ph.D."

# Between an activity word and the place: the place belongs to the applicant, a job or an office.
BLOCK_GAP = re.compile(
    r"\b(?:from|citizens?|citizenship|nationals?|nationality|residen\w*|resid(?:e|ing)|living|lives?|born|origin|"
    r"passports?|permits?|tillatelse|permanent|domicil\w*|enrol\w*|registered|matricul\w*|inscri\w*|"
    r"eingeschrieben|immatrikul\w*|optaget|terdaftar|graduated|graduates?|obtained|completed|earned|received|"
    r"previous\w*|prior|former|alumni|careers?|jobs?|work(?:ing)?|employ\w*|who|whose|which|was|were|embass\w*|"
    r"consulat\w*|commission|office|delegation|ambassade|embajada|embaixada|botschaft|konsulat|kedutaan|kommission|"
    r"comisión|council|headquarter\w*|fulbright|campus france|"
    r"not(?!-)|nor|never|except|other than|outside|instead|wohnsitz|wohnhaft|warga|ciudadan\w*|cidad\w*|nacional\w*|"
    r"nationalité|ressortissant\w*|graduad\w*|egresad\w*|titulad\w*|diplôm\w*|secundaria|high school|secondary)\b",
    re.I)
# Just before an activity word: it is the applicant's past, or negated ("who pursued their studies in", "cannot be
# used for studying in").
BLOCK_STUDY_BEFORE = re.compile(r"(?:\b(?:have|has|had|having|whose|previously|already|completed|commenced|started|"
                                r"began|begun|pursued|undertook|undertaken|did|finished|former)\W+(?:\w+\W+){0,3}|"
                                r"\b(?:ministr\w*|minist[eè]r\w*|kementerian|department)\W+(?:\w+\W+){0,1}|"
                                r"\b(?:not|cannot|can't|never|no longer|other than|except|excluding|instead of|enrolled|"
                                r"registered|matriculad\w*|inscrit\w*|eingeschrieben|immatrikuliert|optaget|"
                                r"terdaftar)\W+(?:\w+\W+){0,4})$", re.I)
# Anywhere in the clause before an institution or degree word: the applicant's past degree, current enrolment, job,
# or a partnership; or the institution is only eligible to send applicants ("Eligible institutions in Brazil").
BLOCK_PLACE_CLAUSE = re.compile(
    r"\b(?:from|complet\w*|graduat\w*|obtained|earned|achieved|received|hold(?:s|ing)?|holders?|whose|was|were|have|"
    r"has|had|previous\w*|prior|former|alumni|enrol\w*|registered|matricul\w*|inscri\w*|eingeschrieben|immatrikul\w*|"
    r"optaget|terdaftar|in good standing|employ\w*|work(?:s|ing|ed)?|affiliat\w*|faculty|staff|lecturers?|eligible|"
    r"nominat\w*|equivalent|support(?:s|ing)?|partner\w*|collaborat\w*|cooperat\w*|agreements?|between|return\w*|"
    r"not(?!-)|cannot|other than|except|outside|citizens?|nationals?|residen\w*|resid(?:e|ing)|living)\b", re.I)
# Anywhere in the sentence: an institution named with an earlier degree ("UK university based in China (where at least
# 50% of the programme was completed in China)")
PRIOR = re.compile(r"\b(?:complet\w*|graduat\w*|obtained|earned|awarded|achieved|alumni|previous\w*|prior)\b", re.I)
# What may stand between an institution or degree word and the place ("institutions of higher education in").
PLACE_GAP = re.compile(r"(?:\W*\b(?:of|higher|education|learning|your|their|choice|or|and|other|located|based|"
                       r"situated|across|throughout|all|over|any|the|a|an|recogni[sz]ed|accredited|public|private|state|"
                       r"research|non-profit|top|leading|best|selected|participating|host|organi[sz]ations?|"
                       r"programmes?|programs?|courses?|studies|institut\w*|universit\w*|colleges?|cent(?:re|er)s?|"
                       r"schools?|de|del|des|du|la|las|los|el|le|"
                       r"les|die|der|den|y|e|et|und|o|ou|oder|educación|superior|enseignement|supérieur|ensino|"
                       r"educação|wissenschaftlich\w*|staatlich\w*|anerkannt\w*)\b){0,6}\W*$", re.I)
# The place is one of "home or abroad" ("studies, both in Guatemala and abroad"): no particular destination
HOME_OR_ABROAD = re.compile(r"\s*,?\s*(?:and|or|y|o|et|ou|und|oder|dan|atau|e)\s+(?:en el |à l['’]|im |no )?"
                            r"(?:abroad|overseas|extranjero|exterior|étranger|ausland|luar negeri)\b", re.I)
# A heading that opens a list of who or what is excluded ("You're not eligible if you", "Who can't apply?")
NEG_HEAD = re.compile(r"not eligible|ineligible|can['’]?t apply|cannot apply|who (?:can|may)not|"
                      r"exclusions?\b|nicht förderfähig|no (?:son|es) elegible|ne sont pas éligibles", re.I)
# A sentence about coming back home, a testimonial or a biography, an exclusion, or a menu line
SKIP = re.compile(r"\b(?:return\w*|come back|go back|back home|regres\w*|retorn\w*|volver|rückkehr\w*|"
                  r"zurückkehr\w*|retour|rentrer|kembali|pulang|home country|hjemland\w*|heimatland\w*|not eligible|"
                  r"ineligible|no son elegibles|ne sont pas éligibles|nicht förderfähig|my|me|he|she|his|her|him)\b|"
                  r"(?-i:\bI\b)|\||^\W*«|»\W*$", re.I)


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    out = {k: v for k, v in countries._BY_NAME.items() if k not in _NOT_A_DESTINATION}
    for cc, row in registry()["countries"].items():
        for n in row.get("names", {}).values():
            out.setdefault(n.lower(), cc)
    for part in re.split(r"[|\n]", _EXTRA):
        cc, _, names = part.partition(":")
        for n in names.split(","):
            out.setdefault(n.strip().lower(), cc.strip())
    return out


def _alt(words) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


@lru_cache(maxsize=1)
def _rx() -> dict:
    name = rf"(?:{_alt(_names())})(?![\w-])"
    art = r"(?:(?:the|la|le|les|el|los|las|der|den|dem)\s+|l['’])?"
    join = r"\s*(?:,|/|&|\band\b|\bor\b|\bund\b|\boder\b|\bet\b|\bou\b|\by\b|\be\b|\bdan\b|\batau\b|\bog\b|\beller\b)\s*"
    names = rf"(?P<names>{name}(?:{join}{art}{name})*)"
    adj = rf"(?:(?-i:UK|U\.\s?S\.|US|USA)|{_alt(countries.DEMONYMS)})(?![\w-])"
    return {
        "name": re.compile(name, re.I),
        # a place: preposition, optional article, one country name or a list ("in the U.S. or Canada")
        "loc": re.compile(rf"(?<![\w-])(?:in|en|au|aux|à|nach|di|ke|em|no|na|nos|nas|i|v|ve|w)\s+{art}{names}", re.I),
        # going there: "travel to Panama", "come to Japan", "move to Finland"
        "motion": re.compile(rf"(?<!\w)(?:com(?:e|ing)|mov(?:e|ing)|travel(?:l?ing)?|relocat(?:e|ing))\s+to\s+"
                             rf"{art}{names}", re.I),
        # a label: "Host country: Germany", "cílový stát: Česko"
        "label": re.compile(rf"(?:(?:host|destination|target) countr(?:y|ies)|cílový stát|zielland|gastland|"
                            rf"pays d['’]accueil|país (?:de destino|anfitrión)|negara tujuan)\s*[:\-–]\s*{art}{names}",
                            re.I),
        # "at a German university", "UK universities", "U.S. institutions"; not a name ("American University of
        # Beirut", "German University in Cairo") and not the applicant ("Japanese university faculty")
        "adj": re.compile(rf"(?<![\w-])(?P<adj>{adj})\s+(?:(?:public|private|state|partner|host|research)\s+)?"
                          r"(?P<noun>universit(?:y|ies)|institutions?|higher education institutions?|HEIs?|colleges?|"
                          r"graduate schools?|research (?:institutions?|organi[sz]ations?|cent(?:re|er)s?))\b"
                          r"(?!\s+(?:faculty|staff|students?|graduates?|alumni|lecturers?|professors?|"
                          r"researchers?|members?|degrees?|diplomas?|qualifications?)\b)", re.I),
    }


def _codes(span: str) -> list[str]:
    out = []
    for m in _rx()["name"].finditer(span):
        if len(m.group(0)) <= 3 and not m.group(0).isupper():
            continue    # "in us": a pronoun, not the United States
        out.append(_names()[m.group(0).lower()])
    return list(dict.fromkeys(out))


def _clause(before: str) -> str:
    """The part of the sentence before a place that belongs to the same clause."""
    parts = BREAK.split(before)
    return parts[-1] if parts else ""


def _strength(sentence: str, start: int, end: int, title: bool) -> str:
    """'strong' (an activity word governs the place), 'weak' (an institution or degree word right before it), or ''."""
    clause = _clause(sentence[:start])
    for m in reversed(list(STUDY_RX.finditer(clause)) + (list(AWARD_RX.finditer(clause)) if title else [])):
        if len(clause) - m.end() <= 70 and not BLOCK_GAP.search(clause[m.start():]) \
                and not BLOCK_STUDY_BEFORE.search(clause[:m.start()]):
            return "strong"
    if STUDY_AFTER.match(sentence, end) and not BLOCK_PLACE_CLAUSE.search(clause):
        return "strong"
    places = list(PLACE_RX.finditer(clause))
    if places and PLACE_GAP.fullmatch(clause[places[-1].end():]) \
            and not BLOCK_PLACE_CLAUSE.search(clause[:places[-1].end()]) and not PRIOR.search(sentence):
        return "weak"
    return ""


def _found(sentence: str, title: bool) -> list[tuple[str, str]]:
    """(code, strength) pairs for the places this sentence names as where the award is held."""
    if not title and SKIP.search(re.sub(r"\b(?:his/her|him/her|he/she|her/his|s/he)\b", "", sentence, flags=re.I)):
        return []
    rx = _rx()
    out = [(c, "strong") for m in rx["label"].finditer(sentence) for c in _codes(m.group("names"))]
    for m in rx["motion"].finditer(sentence):
        clause = _clause(sentence[:m.start()])
        # not "visa requirements for non-U.S. citizens ... coming to the U.S.", "without traveling to Japan"
        if not BLOCK_STUDY_BEFORE.search(clause) and not re.search(r"\b(?:visas?|citizens?|nationals?|without)\b",
                                                                  clause, re.I):
            out += [(c, "strong") for c in _codes(m.group("names"))]
    for m in rx["loc"].finditer(sentence):
        if HOME_OR_ABROAD.match(sentence, m.end()):
            continue
        s = _strength(sentence, m.start(), m.end(), title)
        if s:
            out += [(c, s) for c in _codes(m.group("names"))]
    for m in rx["adj"].finditer(sentence):
        if m.group("noun")[0].isupper() and not m.group("noun").lower().endswith(("ies", "s")):
            continue    # "the American College of Greece": a name, not a place
        clause = _clause(sentence[:m.start()])
        if re.search(r"(?:\bnon-?\s*|\b(?:latin|south|central|north|native|african|asian)\s+)$", clause, re.I) \
                or re.search(r"\b(?:abroad|overseas)\b", sentence, re.I):
            continue
        s = _strength(sentence, m.start(), m.end(), False)
        a = re.sub(r"\s", "", m.group("adj")).lower()
        c = {"uk": "GB", "u.s.": "US", "us": "US", "usa": "US"}.get(a) or countries.DEMONYMS.get(a)
        if c and s == "strong":
            out.append((c, s))
    return out


def _sentences(text: str) -> list[str]:
    from .extract import _sentences as split     # lazy: extract.py imports this module
    return split(text)


def extract_destinations(text: str, title: str = "") -> tuple[list[str], list[str]]:
    """(ISO alpha-2 codes, one supporting sentence per code) for where the funded study or research takes place.

    A country stated only beside an institution or degree word is dropped when another country is stated with an
    activity word ("support universities in Ukraine" beside "a research stay ... in Germany"); a country the body
    states once is dropped when the title states a different one (an advertisement in a sidebar)."""
    from .extract import clean_snippet
    found: dict[str, dict] = {}
    units = [(title, True)] if title else []
    excluded = False
    for line in (text or "").splitlines():
        # the list items under "You're not eligible if you" name what does not qualify ("Plan to study at an
        # Australian university"); the list ends at a long line or at the next heading ("Who can apply?")
        if NEG_HEAD.search(line) and len(line.split()) <= 10:
            excluded = True
            continue
        if excluded and len(line.split()) <= 25 and not line.rstrip().endswith(("?", ":")):
            continue
        excluded = False
        # a short line is a menu item or a link ("Study in Japan"), unless it is a label ("Host country: Norway")
        units += [(s, False) for s in _sentences(line) if len(s.split()) >= 4 or _rx()["label"].search(s)]
    for s, is_title in units:
        for c, strength in _found(s, is_title):
            f = found.setdefault(c, {"snip": clean_snippet(s), "strong": False, "title": False, "n": 0})
            f["strong"] |= strength == "strong"
            f["title"] |= is_title
            f["n"] += 1
    if any(f["strong"] for f in found.values()):
        found = {c: f for c, f in found.items() if f["strong"]}
    if any(f["title"] for f in found.values()):
        found = {c: f for c, f in found.items() if f["title"] or f["n"] >= 2}
    return list(found), [f["snip"] for f in found.values()]


# ------------------------------------------------------------------ fallback: the publishing institution's country

# The domain of a university or college: "ac"/"edu" under a country code, US ".edu", or an institution word in a label
ACADEMIC_ZONE = {"ac", "edu"}
INSTITUTION_LABEL = re.compile(r"univ|universit|college|polytechn|politecn|hochschule|institut|academ|akadem|ecole|"
                               r"escuela|^uni-|^fh-|^tu-", re.I)
VANITY_TLD = {"io", "co", "me", "tv", "ai", "ly", "fm", "cc", "ws", "nu", "to", "la", "sh", "gg", "im", "ac", "so", "is"}
# Wording about going elsewhere: the institution sends its own people abroad
OUTBOUND = re.compile(
    r"\b(?:stud(?:y|ying|ies)|stays?|semesters?|years?|terms?|period|exchanges?|internships?|go(?:ing)?|"
    r"travel(?:l?ing)?|mobility|experience)\s+abroad\b|\bstudy[- ]abroad\b|\babroad\s+(?:study|studies|programs?|"
    r"programmes?|experience|stays?|semester|term)\b|\boverseas\s+(?:study|studies|universit\w*|institution\w*|"
    r"degrees?|training|postgraduate|academic)|\b(?:study|studying|training|universities)\s+overseas\b|"
    r"\bforeign\s+(?:universit\w*|educational institutions?|institutions? of higher|higher education institutions?)|"
    r"\buniversities\s+in\s+other\s+countries|\bfaculty[- ]led\b|\beducation abroad\b|\b(?:research|fieldwork|"
    r"internships?|experiences?)\s+(?:in|to|across)\s+(?:Africa|Asia|Latin America|Europe|the Middle East|Oceania|"
    r"South America|the Caribbean|other countries)\b|\bauslands\w*|\bins ausland|\bim ausland|\bà l['’]étranger|"
    r"\ben el extranjero|\bno exterior|\ball['’]estero|\bluar negeri|\bi u[dt]landet|\byurt ?dışı|海外|해외|εξωτερικό",
    re.I)
# A university office that advises on other bodies' awards (Gates Cambridge, Rhodes), or money to travel somewhere
RELAY_TITLE = re.compile(r"\bnational (?:and international )?(?:scholarships?|fellowships?)|\bnationally competitive|"
                         r"\bfellowships? (?:advising|office)|\bdistinguished (?:scholarships|fellowships)|"
                         r"\bexternal (?:scholarships|awards|funding)|\bprestigious (?:scholarships|awards)|"
                         r"\bconference\b|\btravel (?:grants?|awards?|funds?|scholarships?)\b", re.I)
# right after a country name: it names the applicants ("China Merit Scholarship"), not a place
APPLICANT_WORD = re.compile(r"\W*(?:merit|students?|applicants?|scholars?|citizens?|nationals?|alumni|graduates?|"
                            r"women|refugees?|undergraduates?|postgraduates?|candidates?)\b", re.I)


def _host(url: str) -> tuple[str, bool, str]:
    """(country of the domain, whether the domain is a university's or college's, host name)."""
    from urllib.parse import urlparse
    host = (urlparse(url or "").hostname or "").lower().rstrip(".")
    labels = host.split(".")
    if len(labels) < 2:
        return "", False, host
    tld = labels[-1]
    if tld == "edu":
        return "US", True, host
    cc = "GB" if tld == "uk" else tld.upper() if tld.upper() in countries.COUNTRIES else ""
    academic = len(labels) >= 3 and labels[-2] in ACADEMIC_ZONE or (
        tld not in VANITY_TLD and any(INSTITUTION_LABEL.search(lab) for lab in labels[:-1]))
    return cc, academic, host


@lru_cache(maxsize=1)
def _place_rx():
    """Country names (not demonyms) as whole words; "New Mexico" is a US state."""
    return re.compile(rf"(?<![\w-])(?<![Nn]ew )({_alt([n for n in _names() if len(n) > 3])})(?![\w-])", re.I)


def _foreign_place(line: str, cc: str, applicants: set) -> str:
    """A country other than `cc` that the line names as a place, not as the applicants' ("for students from X")."""
    for m in _place_rx().finditer(line):
        c = _names().get(m.group(1).lower())
        if c and c != cc and c not in applicants and not APPLICANT_WORD.match(line, m.end()) \
                and not re.search(r"\b(?:for|from)\s+(?:\w+\s+)?$", line[:m.start()], re.I):
            return c
    return ""


def host_destination(url: str, text: str, title: str = "", nationality_mode: str = "",
                     nationality_countries: list[str] | None = None) -> tuple[list[str], str]:
    """Fallback for when extract_destinations finds nothing: a university's or college's own page is about study at
    that institution, so the country of its domain (www.stir.ac.uk -> GB, wayne.edu -> US, uni-trier.de -> DE).

    Returns ([code], reason) or ([], why not). Nothing for other publishers (foundations, ministries, embassies:
    as often outbound as inbound), and nothing when the page sends people elsewhere: study-abroad wording, an award for
    the country's own citizens only, another country in the host name or in the page's opening lines (a university
    relaying another country's scholarship), a fellowships-advising office, a travel or conference grant."""
    cc, academic, host = _host(url)
    if not cc or not academic:
        return [], f"{host or 'no host'} is not a university or college domain with a country"
    applicants = set(nationality_countries or []) if nationality_mode == "include" else set()
    if applicants == {cc}:
        return [], f"only citizens of {cc} may apply: usually study elsewhere"
    for label in host.split(".")[:-1]:
        # "aucegypt.edu", "qatar.vcu.edu": a campus in another country (Indiana is a US state, not India)
        c = next((c for n, c in _names().items() if len(n) >= 5 and " " not in n and n in label and c != cc
                  and not re.search(r"indiana|newmexico|newjersey", label)), "")
        if c:
            return [], f"the host name {host} names {c}"
    if RELAY_TITLE.search(title or ""):
        return [], "an advising office or a travel grant: " + title[:100]
    names = "|".join(re.escape(n) for n, c in _names().items() if c == cc and len(n) > 3) or "$^"
    inbound = re.compile(rf"\s+(?:in|to|at)\s+(?:the\s+)?(?:{names})\b", re.I)
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in [title or ""] + lines:
        if len(ln.split()) < 3 or ln[0] in "\"“”'‘’«" or re.search(r"\b(?:my|me)\b|(?-i:\bI\b)", ln, re.I):
            continue    # a menu link ("Study abroad"), or a testimonial ("studying abroad - let alone in the Netherlands")
        for m in OUTBOUND.finditer(ln):
            if not inbound.match(ln, m.end()):    # "study abroad in Germany" on a German page is coming here
                return [], "study elsewhere: " + ln[:150]
    lead = [ln for ln in lines if len(ln.split()) >= 8][:3]
    if any(RELAY_TITLE.search(ln) for ln in lead):
        return [], "an advising office: " + next(ln for ln in lead if RELAY_TITLE.search(ln))[:100]
    for ln in lead:
        c = _foreign_place(ln, cc, applicants)
        if c:
            return [], f"the opening lines name {c}: " + ln[:120]
    return [cc], f"published by {host}, a university or college in {cc}"
