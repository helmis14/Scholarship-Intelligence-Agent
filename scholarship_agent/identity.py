"""Programme identity: does a record stand for one specific programme, offered by a named institution, on an
official page that is really about that programme?

Round 19's catalog showed what goes wrong without this check: home pages ("Homepage | Gates Cambridge"),
catalogues ("DAAD Scholarship Database"), country overviews ("Scholarships for foreign students in France") and
records named after the registry source instead of the page ("OeAD scholarships (Austria)" on the Ernst Mach
grant page). A record is only a programme when

  1. its name is specific: something beyond generic words such as "scholarships", "international", "funding",
     "overview", country names and years ("Chevening SIDS Scholarship", "Ernst Mach Grant", "Türkiye Bursları");
  2. the page it rests on states that name (title, heading or opening text), so the name is not borrowed;
  3. the page is about one programme, not a list of many;
  4. a provider is named (an organisation, not a bare web address);
  5. the page is official (source authority 1 to 4).

The result is "confirmed", "needs_review" (a person checks) or "rejected" (not a programme), with reasons.
"""

from __future__ import annotations

import re
from typing import Optional

from . import countries

# Title segments are separated like "Programme | Site", "Site - Programme", "Programme – Section".
_SEP = re.compile(r"\s+(?:\||–|—|-|::|·|•|»|/)\s+|:\s+(?=[A-Z])")
# Words that describe a kind of page or a category of funding, not one programme.
GENERIC_WORDS = set("""
scholarship scholarships fellowship fellowships grant grants grantees award awards bursary bursaries funding funded fund
funds financial aid support stipend stipends studentship studentships assistantship assistantships prize prizes
programme programmes program programs scheme schemes opportunity opportunities call calls offer offers project projects
international foreign overseas global national abroad worldwide local domestic regional
student students study studies studying applicant applicants candidate candidates scholar scholars researcher
researchers alumni graduate graduates postgraduate undergraduate doctoral doctorate phd master masters master's bachelor
bachelors bachelor's postdoctoral postdoc academic academics degree degrees course courses education higher research
early career young talent talents
overview information info guide guidance options option types type sources source list lists database catalogue catalog
archive archives search finder portal page home homepage welcome news update updates announcement announcements faq faqs
plan planning prepare preparing apply applying application applications how find finding get ready step steps start
starting organising organizing organise stay living costs cost tuition fee fees waiver waivers loan loans finances
finance money budget your our my the a an and or for of in at to with on by from about as into new current open
opening closed key dates date deadline deadlines all other more further general main detail details
university universities college colleges school schools institute institution institutions government governmental
ministry office department agency council commission foundation trust service centre center embassy
year years month months semester term short long full part time online
exchange mobility visiting visit
run managed operated official website site holder holders recipient recipients awardee awardees nouvelles actualités
actualites noticias berita aktuelles nieuws discounts discount descuentos descuento sponsorship sponsorships exterior
estudiar estudie trabaje trabajar studieren étudier etudier belajar bekerja
sur avec dans aux par une un au con por sobre una uno über ueber zum zur per tra con dla oraz untuk dan
""".split())
# Other languages: the same kinds of words in the registry's main languages.
GENERIC_WORDS |= set("""
beasiswa bantuan program pendanaan studi kuliah mahasiswa luar negeri dalam informasi panduan daftar
bourse bourses programme programmes étudiants etudiants internationales internationaux étrangers etrangers
informations aides financement études etudes pour les des de la le du et en
beca becas ayuda ayudas programa programas estudiantes extranjeros internacionales información informacion para
los las el y del en convocatoria convocatorias estudios posgrado
bolsa bolsas estudo estudos estudantes estrangeiros internacionais para os as e do da em
stipendium stipendien förderung foerderung programm programme studierende ausländische internationale studium für fur
und der die das im in
borsa borse studio studenti stranieri internazionali per gli le e di del
stypendium stypendia program programy studenci zagraniczni dla
burs burslari bursları burslar
biasiswa bantuan kewangan pelajar pelajaran penajaan pinjaman pembiayaan jabatan bahagian seksyen unit pusat yayasan
""".split())
GENERIC_PHRASE = re.compile(
    r"\b(?:study in|studying in|plan your studies|funding your studies|information for|for (?:international|foreign) "
    r"students|step[- ]by[- ]step|how to (?:apply|find)|finding (?:a|your) scholarship|overview|archive|database|"
    r"catalogue|catalog|home ?page|news|types of|list of|scholarship finder|encuentra tu beca|get ready|prepare to "
    r"apply|organising your stay|organizing your stay|information for candidates|frequently asked)\b", re.I)
# "Türkiye Bursları", "Global Korea Scholarship", "Chinese Government Scholarship": a country's own programme name.
NATIONAL_BRAND = re.compile(r"^(?:the\s+)?(?:global\s+)?(?P<c>[\w'’ .-]{3,40}?)\s+(?:government\s+)?(?:excellence\s+)?"
                            r"(?:\(\w+\)\s+)?(?:scholarships?|bursları|burslari|fellowships?|awards?)$", re.I)
ORG_WORDS = re.compile(r"\b(?:commission|ministry|university|universit[äaéy]|college|foundation|trust|council|agency|"
                       r"office|department|institute|embassy|service|government|centre|center|academy|association|"
                       r"bank|corporation|company|authority)\b", re.I)
SCHOLARSHIP_WORD = re.compile(r"scholarship|fellowship|bursar|grant|stipend|funding|bourse|beca|beasiswa|stipendi|"
                              r"borsa|bolsa|burs|award", re.I)
_TOKEN = re.compile(r"[\w'’*+]+", re.U)


def title_segments(title: str) -> list[str]:
    parts = [p.strip(" |:-–—()") for p in _SEP.split(title or "") if p and p.strip(" |:-–—()")]
    return parts or ([title.strip()] if title and title.strip() else [])


def _site_segment(seg: str, provider: str = "") -> bool:
    """A segment that names the site or organisation rather than the page ("Chevening", "Commonwealth Scholarship
    Commission in the UK", "The University of Edinburgh")."""
    low = seg.lower()
    if provider and (low == provider.lower() or low in provider.lower() or provider.lower() in low):
        return True
    if ORG_WORDS.search(seg) and not re.search(r"\bscholarships?\b|\bfellowships?\b|\bgrants?\b", seg, re.I):
        return True
    return False


def specific_tokens(segment: str) -> list[str]:
    """Words of a title segment that can name one programme: not generic, not a country, not a year."""
    s = segment
    for m in sorted(countries._NAME_RX.finditer(s), key=lambda m: -m.start()):   # drop country names and demonyms
        s = s[:m.start()] + " " + s[m.end():]
    out = []
    for t in _TOKEN.findall(s):
        low = t.lower().strip("'’")
        if not low or low in GENERIC_WORDS or low.rstrip("s") in GENERIC_WORDS:
            continue
        if re.fullmatch(r"\d+|(?:19|20)\d\d(?:[-/]\d{2,4})?", low):
            continue
        if len(low) < 3 and not (t.isupper() and len(t) >= 2):
            continue
        out.append(t)
    return out


# "OeAD scholarships (Austria)", "VLIR-UOS scholarships": an organisation's collection, written in lower case,
# unlike a programme's own name ("Chevening Scholarships", "Commonwealth PhD Scholarships").
COLLECTION = re.compile(r"^[\w*+&.'’-]+(?:\s+[\w*+&.'’-]+)?\s+(?:scholarships|programmes|programs|grants|fellowships|"
                        r"funding|awards)(?:\s*\([^)]*\)?)?$")
# A finder, catalogue, archive or home page anywhere in the title makes the whole page a portal.
PORTAL_PHRASE = re.compile(r"\b(?:database|catalogue|catalog|archive|home ?page|scholarship finder|encuentra tu beca|"
                           r"find (?:a|your) scholarship|search (?:for )?scholarships|list of)\b|katalog|cat[áa]logo|"
                           r"datenbank|base de datos|banco de dados|direktori|daftar beasiswa", re.I)


def segment_specific(segment: str) -> bool:
    if COLLECTION.match(segment.strip()):
        return False
    if NATIONAL_BRAND.match(segment.strip()):
        rest = NATIONAL_BRAND.match(segment.strip()).group("c")
        if countries.code(rest.strip()) or countries.mentions(rest):
            return True
    if GENERIC_PHRASE.search(segment):
        # "Commonwealth Fellowships information for candidates" is still named; "Information for applicants" is not
        named = [t for t in specific_tokens(GENERIC_PHRASE.sub(" ", segment))]
        return bool(named) and not re.search(r"\b(?:database|catalogue|catalog|archive|overview|home ?page|news|"
                                             r"list of|study in)\b", segment, re.I)
    return bool(specific_tokens(segment))


def title_specificity(title: str, provider: str = "") -> tuple[bool, str]:
    """(is the title a specific programme name, the segment that names it or the main segment)."""
    segs = title_segments(title)
    if not segs:
        return False, ""
    if PORTAL_PHRASE.search(title or ""):
        return False, segs[0]
    if len(segs) >= 2 and _site_segment(segs[-1], provider):
        segs = segs[:-1]
    if len(segs) >= 3:
        segs = segs[:1]     # "Page | Section | Site": the first part names the page
    if len(segs) >= 2 and _site_segment(segs[0], provider) and not SCHOLARSHIP_WORD.search(segs[0]):
        segs = segs[1:]
    for seg in segs:
        if segment_specific(seg):
            return True, seg
    return False, segs[0]


def programme_lines(text: str) -> int:
    """Short lines that each name a scholarship or grant: many of them means the page lists programmes."""
    n = 0
    for line in (text or "").splitlines():
        words = line.split()
        if 1 <= len(words) <= 12 and SCHOLARSHIP_WORD.search(line) and not line.rstrip().endswith((".", ":", "?")):
            n += 1
    return n


# A programme named in a line: a funding word with up to four capitalised words after it ("Beasiswa KIP Kuliah",
# "Biasiswa Sagong Tasi") or before it ("Rattansi Education Fund", "PRIME Scholarship").
_FUND_WORD = (r"(?:scholarships?|fellowships?|grants?|bursar(?:y|ies)|awards?|funds?|beasiswa|biasiswa|bantuan|becas?|"
              r"bolsas?|bourses?|học bổng|stipendi(?:um|en)|burs(?:u|ları)|منحة|وظیفہ)")
_CAP = r"[A-Z0-9ÀÁÂÃÉÊÍÓÔÕÚÜÇĐ][\w'’&.-]*"
_NAMED = re.compile(rf"(?i:{_FUND_WORD})(?:\s+{_CAP}){{1,4}}|(?:{_CAP}\s+){{1,4}}(?i:{_FUND_WORD})")
# capitalised words that start a sentence or a button, not a programme name ("This scholarship", "Explore ...")
NAME_STOP = set("""this that these those our your their its explore more read view see apply learn find about other
other's all any each every new open closed latest available form forms info jenis nama tahun daftar senarai lihat""".split())
CATALOG_MIN_NAMES = 5          # different programmes named on one page
CATALOG_SURE_NAMES = 8         # from this many on, a page with a generic title is a catalogue without doubt
CATALOG_MAX_TOP_SHARE = 0.4    # a programme page keeps repeating its own name; a catalogue does not


def named_programmes(text: str) -> dict:
    """{specific words of a programme name: times named} for programme names written on the page."""
    out: dict = {}
    for line in (text or "").splitlines():
        for m in _NAMED.finditer(line):
            key = tuple(sorted({t.lower() for t in specific_tokens(m.group(0))} - NAME_STOP))
            if key:
                out[key] = out.get(key, 0) + 1
    return out


def catalogue_evidence(text: str, title: str = "") -> tuple[bool, str]:
    """(True, why) when the page names several different programmes and none of them dominates it, and the title
    does not name one of the most frequent ones. Language-neutral apart from the funding words above."""
    names = named_programmes(text)
    total = sum(names.values())
    if len(names) < CATALOG_MIN_NAMES or not total:
        return False, ""
    top = sorted(names.items(), key=lambda kv: -kv[1])[:3]
    if top[0][1] / total >= CATALOG_MAX_TOP_SHARE:
        return False, ""
    why = f"names {len(names)} different programmes, none dominant ({top[0][1]} of {total} mentions)"
    specific, segment = title_specificity(title)
    if specific:
        if set(t.lower() for t in specific_tokens(segment)) & {w for k, _ in top for w in k}:
            return False, ""   # the page's own name is among the names it repeats most: the programme's page
        # the title names one programme that the page barely repeats: variants or siblings, not certain
        return True, why + "; but the title names a programme"
    if len(names) < CATALOG_SURE_NAMES:
        return True, why + "; but only a few names"
    return True, why


_HOSTLIKE = re.compile(r"^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+$", re.I)


def name_on_page(name: str, page_title: str, h1: str, text: str) -> bool:
    """The page states the record's name: its specific words appear in the title, heading or opening text."""
    toks = [t.lower() for t in specific_tokens(name)]
    if not toks:
        return False
    hay = " ".join([page_title or "", h1 or "", (text or "")[:1500]]).lower()
    found = sum(1 for t in toks if t in hay)
    return found >= max(1, (len(toks) + 1) // 2)


# Page types as stored on a record (Opportunity.page_type). Domain trust (source_authority) is kept apart: an
# official domain says who published a page, the page type says what the page is.
PAGE_TYPES = {"opportunity": "scholarship_program", "listing": "scholarship_catalog", "guidance": "general_guidance",
              "news": "announcement", "not_relevant": "irrelevant", "not_loaded": "not_loaded"}
KIND_OF_TYPE = {v: k for k, v in PAGE_TYPES.items()}


def page_type(kind: str, aggregator: bool = False) -> str:
    """scholarship_program | scholarship_catalog | general_guidance | announcement | aggregator | irrelevant | unknown"""
    if aggregator:
        return "aggregator"
    return PAGE_TYPES.get(kind, "unknown")


def record_identity(opp) -> dict:
    """The identity stored when the page was last read (discovery or verification); recomputed from the record
    only when none is stored, so discovery, verification and the audit agree."""
    if getattr(opp, "programme_identity", None):
        return opp.programme_identity
    return identity(opp, page_kind=KIND_OF_TYPE.get(getattr(opp, "page_type", ""), ""))


def identity(opp, *, page_title: Optional[str] = None, h1: str = "", text: str = "", page_kind: str = "",
             kind_confidence: str = "high", kind_reason: str = "") -> dict:
    """The record's programme identity. `page_title`, `h1`, `text` and `page_kind` describe the page as fetched
    now (verification); without them the record's own evidence is used."""
    from .evidence import is_official
    reasons: list[str] = []
    title = opp.title or ""
    specific, segment = title_specificity(title, opp.provider_name or "")
    page_titles = [e.value for e in getattr(opp, "evidence", []) if getattr(e, "field", "") == "title" and e.value]
    own_title = page_title if page_title is not None else (page_titles[0] if page_titles else title)
    state = "confirmed"
    if page_kind == "not_loaded":
        return {"state": "not_assessed", "name": segment,
                "reasons": [f"the page did not load, so it was not assessed: {kind_reason[:120]}"]}
    if kind_confidence == "low":
        # the page type itself is uncertain (extract.classify_page): a person decides, nothing is rejected or confirmed
        return {"state": "needs_review", "name": segment,
                "reasons": [f"page type uncertain (best guess: {page_kind or 'unknown'}): {kind_reason[:120]}"]}
    if page_kind and page_kind != "opportunity":
        return {"state": "rejected", "name": segment, "reasons": [f"the page is a {page_kind} page, not a programme"]}
    if not specific:
        own_specific, own_seg = title_specificity(str(own_title), opp.provider_name or "")
        if own_specific and own_title != title:
            reasons.append(f"named after its source ({title[:60]}); the page is about {own_seg[:60]}")
        else:
            # "PhD Fellowships" on twas.org is a programme whose name lives in the site, not the title: a person
            # names it; a portal or guidance page is rejected above once the page itself is classified
            reasons.append(f"generic title, no programme named: {segment[:60] or '(none)'}")
        state = "needs_review"
    elif own_title and own_title != title and not name_on_page(title, str(own_title), h1, text):
        reasons.append(f"the page title ({str(own_title)[:60]}) does not state the record's name")
        state = "needs_review"
    if text and programme_lines(text) >= 12:
        reasons.append(f"the page lists {programme_lines(text)} programme names: one record may stand for several")
        state = "needs_review"
    provider = (opp.provider_name or "").strip()
    parties = [p for p in getattr(opp, "funding_parties", []) or [] if p.get("name")]
    if (not provider or _HOSTLIKE.match(provider)) and not parties and not (opp.institution or "").strip():
        reasons.append("no provider institution named (only a web address)")
        state = "needs_review"
    if not is_official(opp.source_authority or ""):
        reasons.append(f"not on an official page ({opp.source_authority or 'authority unknown'})")
        state = "needs_review"
    return {"state": state, "name": segment, "reasons": reasons}
