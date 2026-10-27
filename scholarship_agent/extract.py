"""Turn a fetched page into structured, evidence-backed fields.

Everything here is deterministic pattern extraction. Page content is
untrusted: it is only ever matched against patterns, never executed or
followed as instructions, and text that looks like an instruction to an AI is
flagged so downstream LLM steps can quarantine it. Every value produced comes
with the sentence it was read from, and starts as `extracted_unverified`.

A field the page does not mention is left empty. Empty never means "not
required" - see eligibility.py for how that is handled.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin

from . import countries
from .languages import ascii_digits, deadline_words, month_names, words_rx
from .models import (Deadline, DeadlineCertainty, DeadlineKind, Evidence, FundingComponent,
                     LanguageRequirement, NationalityRule, Opportunity, RequiredDocument, SourceType,
                     VerificationStatus)

RULES_VERSION = "rules-r14"   # recorded on rules evidence; bump when extraction rules change materially
BLOCK_TAGS = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "br", "section", "article", "dt",
              "ul", "ol", "table", "header", "footer", "caption"}
# Cells stay on their row's line so "Deadline | 15 January 2027" reads as one statement.
CELL_TAGS = {"td", "th", "dd"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe"}
# Site chrome: its links are kept for discovery, its text is not read as facts about the opportunity.
CHROME_TAGS = {"nav", "header", "footer", "aside"}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self.h1 = ""
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self._skip = 0
        self._chrome = 0
        self._in = {"title": False, "h1": False, "a": False, "ld": False}
        self._href = ""
        self._atext: list[str] = []
        self._ld: list[str] = []
        self.html_lang = ""
        self.tables: list[list[list[str]]] = []   # table -> rows -> cells, text as written
        self._tables: list[list[list[str]]] = []
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.html_lang = a["lang"]
        if tag == "table":
            self._tables.append([])
        elif tag == "tr" and self._tables:
            self._tables[-1].append([])
        elif tag in ("td", "th") and self._tables:
            if not self._tables[-1]:
                self._tables[-1].append([])
            self._cell = []
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in["ld"] = True
            self._ld = []
            return
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag in CHROME_TAGS or (a.get("role") or "").lower() in ("navigation", "banner", "contentinfo"):
            self._chrome += 1
            self._chrome_tags = getattr(self, "_chrome_tags", []) + [tag]
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag in CELL_TAGS:
            self.parts.append(" : " if tag == "dd" else " | ")
        if tag == "title":
            self._in["title"] = True
        if tag == "h1":
            self._in["h1"] = True
        if tag == "a" and a.get("href"):
            self._in["a"], self._href, self._atext = True, a["href"], []
        if tag == "meta":
            k = (a.get("property") or a.get("name") or "").lower()
            if k and a.get("content"):
                self.meta[k] = a["content"]

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._tables:
            self._tables[-1][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        if tag == "table" and self._tables:
            t = [r for r in self._tables.pop() if any(r)]
            if t:
                self.tables.append(t)
        if tag == "script" and self._in["ld"]:
            self._in["ld"] = False
            self.jsonld.append("".join(self._ld))
            return
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if self._chrome and getattr(self, "_chrome_tags", None) and tag == self._chrome_tags[-1]:
            self._chrome -= 1
            self._chrome_tags.pop()
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "title":
            self._in["title"] = False
        if tag == "h1":
            self._in["h1"] = False
        if tag == "a" and self._in["a"]:
            self._in["a"] = False
            self.links.append((self._href, " ".join("".join(self._atext).split())))

    def handle_data(self, data):
        if self._in["ld"]:
            self._ld.append(data)
            return
        if self._skip:
            return
        if self._in["title"]:
            self.title += data
        if self._in["h1"]:
            self.h1 += data
        if self._in["a"]:
            self._atext.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if not self._chrome:
            self.parts.append(data)


def page_from_response(resp) -> "Page":
    """HTML, or text pulled from a PDF. An unreadable PDF yields an empty page with `pdf_status` set."""
    if getattr(resp, "is_pdf", False):
        from .pdf import pdf_text
        text, status = pdf_text(resp.data)
        p = Page.from_text(resp.url, text)
        p.pdf_status = status
        return p
    return Page(resp.url, resp.text)


class Page:
    pdf_status = ""
    og_type = ""
    html_lang = ""
    tables: list = []

    @property
    def language(self) -> str:
        """The page's language: its own <html lang> when registered, else detected from the text."""
        from .languages import detect
        return detect(self.text, self.html_lang)[0]

    def document_links(self) -> list[tuple[str, str]]:
        """Links to documents (PDF, Word) published with the page: calls, guidelines, forms."""
        return [(u, t) for u, t in self.links if re.search(r"\.(?:pdf|docx?)(?:$|[?#])", u, re.I)]

    @classmethod
    def from_text(cls, url: str, text: str, title: str = "") -> "Page":
        """A page whose text came from somewhere other than HTML (a PDF call, for instance)."""
        p = cls(url, "")
        lines = [" ".join(line.split()) for line in (text or "").splitlines()]
        p.text = "\n".join(line for line in lines if line)
        p.title = title or next((line for line in p.text.splitlines() if len(line) > 8), "")[:200]
        return p

    def __init__(self, url: str, html: str):
        p = _Parser()
        try:
            p.feed(html)
        except Exception:
            pass
        self.url = url
        raw = "".join(p.parts)
        lines = [" ".join(line.split()).strip(" |:") for line in raw.splitlines()]
        self.text = "\n".join(line for line in lines if line)
        self.title = " ".join((p.meta.get("og:title") or p.h1 or p.title).split())
        self.h1 = " ".join(p.h1.split())                 # the page's own heading and <title>, kept apart for
        self.html_title = " ".join(p.title.split())      # programme identity checks (identity.py)
        self.description = p.meta.get("og:description") or p.meta.get("description", "")
        self.og_type = (p.meta.get("og:type") or "").lower()
        self.links = [(urljoin(url, h), t) for h, t in p.links if not h.startswith(("mailto:", "javascript:", "tel:"))]
        self.tables = p.tables
        self.html_lang = p.html_lang
        from .retrieval import APP_ROOT, JS_REQUIRED    # signs that the content is rendered by JavaScript
        self.script_count = (html or "").lower().count("<script")
        self.js_required = bool(JS_REQUIRED.search(html or ""))
        self.app_root = bool(APP_ROOT.search(html or ""))
        self.jsonld = []
        for blob in p.jsonld:
            try:
                self.jsonld.append(json.loads(blob))
            except ValueError:
                pass


# ------------------------------------------------------------------ safety

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
    r"disregard (all |the )?(previous|prior|above)",
    r"\byou are (now )?(an? )?(ai|assistant|language model|chatgpt|claude)\b",
    r"\bsystem prompt\b", r"^\s*(assistant|system)\s*:", r"\bact as\b.{0,40}\b(ai|assistant|agent)\b",
    r"\b(send|email|forward|upload) (your|the user'?s|all) (data|documents|passport|password|profile)",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.I | re.M)
# instructions to a model only: "upload your documents" is ordinary applicant guidance, not an instruction to us
_INJ_INSTRUCT = re.compile("|".join(INJECTION_PATTERNS[:-1]), re.I | re.M)


def injection_flags(text: str) -> list[str]:
    return sorted({m.group(0).strip()[:80] for m in _INJ.finditer(text or "")})


def clean_snippet(s: str, limit: int = 300) -> str:
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮]", "", s)
    s = " ".join(s.split())
    return s[:limit]


# ------------------------------------------------------------------ dates

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
# a few non-English month names commonly seen on official pages
MONTHS.update({"janeiro": 1, "fevereiro": 2, "março": 3, "maio": 5, "junho": 6, "julho": 7, "setembro": 9,
               "outubro": 10, "novembro": 11, "dezembro": 12, "gennaio": 1, "febbraio": 2, "aprile": 4,
               "maggio": 5, "giugno": 6, "luglio": 7, "settembre": 9, "ottobre": 10, "dicembre": 12,
               "januar": 1, "februar": 2, "märz": 3, "mai": 5, "juni": 6, "juli": 7, "oktober": 10, "dezember": 12,
               "janvier": 1, "février": 2, "mars": 3, "avril": 4, "juin": 6, "juillet": 7, "août": 8,
               "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "enero": 1, "febrero": 2,
               "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
               "octubre": 10, "noviembre": 11, "diciembre": 12, "januari": 1, "februari": 2, "maret": 3,
               "mei": 5, "agustus": 8, "desember": 12, "oktober_": 10})
for _k, _v in month_names().items():
    MONTHS.setdefault(_k, _v)
_MON = "|".join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th|er|º)?\.?\s+(?:of\s+|de\s+)?({_MON})\.?,?\s+(?:de\s+)?(\d{{4}})\b", re.I),
     "dmy_name"),
    (re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I), "mdy_name"),
    (re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b"), "dmy_dot"),   # 31.10.2026, Czech "1. 8. 2026"
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "slash"),
    (re.compile(r"(\d{4})\s*[年년]\s*(\d{1,2})\s*[月월]\s*(\d{1,2})\s*[日일]"), "ymd"),      # 2026年10月17日, 2026년 10월 17일
    (re.compile(r"\b(\d{4})[/.]\s?(\d{1,2})[/.]\s?(\d{1,2})\b(?![/.]\d)"), "ymd"),            # 2026/10/17, 2026. 10. 17
    (re.compile(r"(?<![\d-])(\d{1,2})-(\d{1,2})-(\d{4})\b"), "slash"),   # 31-10-2026 (same ambiguity rule)
]
DM_PATTERNS = [
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th|er|º)?\.?\s+(?:of\s+|de\s+)?({_MON})\b(?!\.?,?\s+(?:de\s+)?\d{{4}})", re.I), "dm"),
    (re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!,?\s+\d{{4}})(?!\s*[:.]\d)", re.I), "md"),
]
TIME_RX = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(am|pm|h)?\b", re.I)
TZ_RX = re.compile(r"\b(UTC|GMT)\s?[+-]\s?\d{1,2}(?::?\d{2})?\b|\b(CET|CEST|GMT|UTC|BST|EST|EDT|CST|PST|PDT|JST|KST|"
                   r"AEST|AEDT|NZST|NZDT|WIB|WITA|WIT|IST|SGT|HKT|EAT|WAT|SAST)\b")


def parse_dates(sentence: str, context: str = "") -> list[tuple[Optional[date], str]]:
    """(date or None-if-ambiguous, matched text) for each date in the sentence. `context` is the paragraph the
    sentence belongs to: a day-month without a year may take the single year stated there, nothing wider."""
    out = []
    original, sentence = sentence, ascii_digits(sentence)   # same length: matches are cut from the original text
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(sentence):
            g = m.groups()
            try:
                if kind == "ymd":
                    d = date(int(g[0]), int(g[1]), int(g[2]))
                elif kind == "dmy_name":
                    d = date(int(g[2]), MONTHS[g[1].lower()], int(g[0]))
                elif kind == "mdy_name":
                    d = date(int(g[2]), MONTHS[g[0].lower()], int(g[1]))
                elif kind == "dmy_dot":
                    d = date(int(g[2]), int(g[1]), int(g[0]))
                else:  # a/b/yyyy: only unambiguous when one side cannot be a month
                    a, b, y = int(g[0]), int(g[1]), int(g[2])
                    if a > 12 >= b:
                        d = date(y, b, a)
                    elif b > 12 >= a:
                        d = date(y, a, b)
                    else:
                        d = None
            except (ValueError, KeyError):
                continue
            out.append((d, original[m.start():m.end()]))
    # drop matches contained in an earlier, longer match
    out.sort(key=lambda t: -len(t[1]))
    kept: list[tuple[Optional[date], str]] = []
    for d, s in out:
        if not any(s in k for _, k in kept):
            kept.append((d, s))
    # Day + month without a year ("until May 1st", "el 18 de febrero") take the year of a full date in the SAME
    # sentence - never a year guessed from elsewhere. Without one they are skipped.
    years = {d.year for d, _ in kept if d}
    if not years:
        own = set(re.findall(r"(?<![\d/–-])(20\d{2})(?![\d/–-])", sentence))
        if not own and context:
            ctx_dates = [d for d, _ in parse_dates(context) if d]
            own = {str(d.year) for d in ctx_dates} or set(re.findall(r"(?<![\d/–-])(20\d{2})(?![\d/–-])", context))
        years = {int(y) for y in own}
    if len(years) == 1:
        y = years.pop()
        for rx, order in DM_PATTERNS:
            for m in rx.finditer(sentence):
                raw = original[m.start():m.end()]
                if any(raw in k or k in raw for _, k in kept):
                    continue
                try:
                    day, mon = (m.group(1), m.group(2)) if order == "dm" else (m.group(2), m.group(1))
                    d = date(y, MONTHS[mon.lower()], int(day))
                except (ValueError, KeyError):
                    continue
                kept.append((d, raw))
    return kept


CYCLE_RX = re.compile(r"\b(20\d{2})\s?[/–-]\s?(20\d{2}|\d{2})\b|\b(?:intake|academic year|cohort|call)\s+(20\d{2})\b",
                      re.I)


def detect_cycle(text: str) -> Optional[str]:
    m = CYCLE_RX.search(text or "")
    if not m:
        return None
    if m.group(1):
        a, b = m.group(1), m.group(2)
        b = b if len(b) == 4 else a[:2] + b
        if int(b) - int(a) == 1:
            return f"{a}/{b}"
        return None
    return m.group(3)


# ------------------------------------------------------------------ field extraction

DEADLINE_WORDS = re.compile(
    r"deadline|closing date|clos(?:es|ed)|apply by|applications? (?:must be )?(?:received|submitted) by|due (?:date|by|on)|"
    r"last date|until|no later than|bewerbungsschluss|bewerbungsfrist|frist|einsendeschluss|date limite|"
    r"date de clôture|clôture des candidatures|fecha l[ií]mite|plazo|cierre de (?:la )?convocatoria|prazo|"
    r"data limite|inscrições até|scadenza|(?-i:termine)|batas (?:akhir|waktu)|pendaftaran (?:ditutup|dibuka)|tenggat|"
    r"applications? close|\bclose (?:on|at|by)\b|closing call|call closes|cierre|cerrará|finaliza(?:rá)?|hasta el|clôture|"
    r"締切|마감|截止" + "|" + words_rx(deadline_words()), re.I)
OPENING_WORDS = re.compile(r"\bopened\b|abierto desde|^\W*applications?\s*:|\bopens?\b|opening call|application (?:period|window)|bewerbungszeitraum|bewerbungsphase|periode pendaftaran|dibuka|from\s+\d|"
                           r"ouverture des candidatures|apertura|abertura das inscrições|bewerbungsbeginn|se abrirá|"
                           r"abrirá|\babre\b", re.I)
EVENT_WORDS = re.compile(r"\b(?:results?|publication|announce\w*|notification|interviews?|selection (?:date|takes)|"
                         r"pengumuman|seleksi|resultados|résultats|ergebnis\w*|webinar|info(?:rmation)? session|charla|"
                         r"open (?:day|evening|house)|tag der offenen tür|journée portes ouvertes|"
                         r"veranstaltung\w*|vortrag|vorträge|lecture|talk|symposium|conference|festakt|feier|"
                         # round 27: dates of other steps ("notified ... by 2 April", "for Masters starting
                         # September 14", "a room allocated to you until 16 July 2028", "MVV visa")
                         r"notif\w*|outcome|starting|commenc\w*|allocated to you|visa|residence permit)\b",
                         re.I)
APPROX_WORDS = re.compile(r"\b(usually|typically|normally|generally|expected|tentative(?:ly)?|approximately|around|"
                          r"early|mid|late)\b", re.I)
# Round 49: a day and month the page says come back every year ("1 March and 1 September of each year", "Closing date
# for applications is 15 July of each year", "1 March for the summer semester and 15 September for the winter
# semester"). No year is written, so the next occurrence is expected, never confirmed: the deadline is EXPECTED with
# recurs="MM-DD" and no date (decisions and benchmarks count dated deadlines only).
RECURRING_RX = re.compile(r"\b(?:(?:of )?(?:each|every) (?:academic |calendar )?year|annually|annual (?:calls?|deadlines?|"
                          r"competitions?|rounds?|intakes?)|jedes jahr(?:es)?|jährlich|chaque année|tous les ans|cada año|"
                          r"todos los años|anualmente|ogni anno|setiap tahun|tiap tahun|elk jaar|jaarlijks|każdego roku|"
                          r"her yıl)\b|毎年|매년|每年", re.I)
SEMESTER_RX = re.compile(r"\bfor the (?:following |next |upcoming )?(?:academic year|(?:winter|summer|spring|fall|autumn) "
                         r"(?:semester|term))\b|\b(?:winter|sommer)semester\b", re.I)
_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December"]


def _recurring(s: str, para: str = "") -> list[tuple[str, str]]:
    """("MM-DD", text) for each day and month without a year in a sentence that says the date recurs every year."""
    if not (RECURRING_RX.search(s) or RECURRING_RX.search(para) or (SEMESTER_RX.search(s) and not detect_cycle(s))):
        return []
    out: list[tuple[str, str]] = []
    sentence = ascii_digits(s)
    for rx, order in DM_PATTERNS:
        for m in rx.finditer(sentence):
            day, mon = (m.group(1), m.group(2)) if order == "dm" else (m.group(2), m.group(1))
            try:
                month = MONTHS[mon.lower()]
                date(2027, month, int(day))   # a real day of that month (29 February is left out)
            except (KeyError, ValueError):
                continue
            raw = s[m.start():m.end()]
            if not any(raw in r or r in raw for _, r in out):
                out.append((f"{month:02d}-{int(day):02d}", raw))
    return sorted(out, key=lambda t: s.find(t[1]))


def _kind(sentence: str) -> DeadlineKind:
    s = sentence.lower()
    if re.search(r"recommendation|reference letter|referee", s):
        return DeadlineKind.RECOMMENDATION
    if re.search(r"\b(ielts|toefl|test date|language test)\b", s):
        return DeadlineKind.TEST
    if re.search(r"admission|programme application|program application|university application|apply to the (?:university|programme|program)", s) \
            and "scholarship" not in s:
        return DeadlineKind.ADMISSION
    if re.search(r"\bdocument|transcript|upload", s) and "scholarship" not in s \
            and not re.search(r"\bdeadline for (?:the )?applications?\b|\bapplications? and (?:the )?submission\b", s):
        return DeadlineKind.DOCUMENT
    return DeadlineKind.SCHOLARSHIP


def _sentences(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        # no split after "15." (German/Nordic dates) or common abbreviations
        out.extend(s.strip() for s in re.split(r"(?<=[^\d\s][.!?])(?<!\b[A-Z]\.)(?<!\bvs\.)(?<!\bca\.)\s+(?=[A-Z0-9])", line)
                   if s.strip())
    return out


LABEL_LINE = re.compile(r"^(?:applications?\s+(?:open|close|deadline)s?|(?:application\s+)?deadline|closing date|"
                        r"opening date|bewerbungsschluss|date limite|fecha l[ií]mite|plazo|batas akhir|tenggat)\b.{0,40}$",
                        re.I)
HEADER_CELL = re.compile(r"^(?:opening|closing|deadline|application deadline|open|close)s?\s*(?:dates?)?$", re.I)


def _deadline_units(text: str) -> list[tuple[str, str]]:
    """(unit, paragraph) pairs: sentences, plus two layouts sentences miss - a label line followed by its date
    line, and tables whose cells were rendered one per line under a header row (Opening dates / Closing dates)."""
    units = [(s, line, s) for line in text.splitlines() for s in _sentences(line)]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines[:-1]):
        if len(line) <= 60 and LABEL_LINE.match(line) and not parse_dates(line):
            nxt = lines[i + 1]
            if len(nxt) <= 80 and (parse_dates(nxt) or _recurring(nxt)):   # "Application Deadline" / "15 July of each year"
                units.append((f"{line} {nxt}", "", f"{line} {nxt}"))
    for i, line in enumerate(lines):
        if parse_dates(line) and not (DEADLINE_WORDS.search(line) or OPENING_WORDS.search(line)) \
                and not EVENT_WORDS.search(line):
            for back in (1, 2):
                if i - back >= 0 and len(lines[i - back]) <= 120 and (DEADLINE_WORDS.search(lines[i - back]) or
                                                                       OPENING_WORDS.search(lines[i - back])):
                    units.append((f"{lines[i - back]} {line}", "", " ".join(lines[i - back:i + 1])))
                    break
    i = 0
    while i < len(lines):
        hdr = []
        j = i
        while j < len(lines) and len(lines[j]) <= 40 and (HEADER_CELL.match(lines[j]) or (hdr and not parse_dates(lines[j])
                                                                                           and len(hdr) < 1)):
            hdr.append(lines[j])
            j += 1
        cols = [h for h in hdr if HEADER_CELL.match(h)]
        if len(cols) >= 2 or (cols and i > 0 and not parse_dates(lines[i - 1])):
            # rows: a label line followed by up to len(cols) date lines
            k = j
            while k < len(lines):
                label = lines[k]
                if parse_dates(label) or len(label) > 80:
                    break
                dates_ = []
                m = k + 1
                while m < len(lines) and len(dates_) < len(cols) and parse_dates(lines[m]) and len(lines[m]) <= 40:
                    dates_.append(lines[m])
                    m += 1
                if not dates_:
                    break
                names = cols[-len(dates_):] if len(dates_) < len(cols) else cols
                verbatim = " ".join([label] + dates_)
                for name, d in zip(names, dates_):
                    word = "opens" if re.match(r"open", name, re.I) else "deadline"
                    units.append((f"{label} {word}: {d}", "", verbatim))  # parse text carries the column name
                k = m
            i = max(k, i + 1)
        else:
            i += 1
    return units


RANGE_RX = re.compile(rf"(?:from|between|del|du|vom|dari|de|desde(?: el)?)?\s*(\d{{1,2}}(?:st|nd|rd|th|er)?\.?\s+(?:de\s+)?(?:{_MON})"
                      rf"(?:\.?,?\s+(?:de\s+)?\d{{4}})?|(?:{_MON})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?)\s*"
                      rf"(?:-|–|to|until|till|al|au|bis(?:\s+zum)?|sampai|hingga|s\.?d\.?|a|hasta(?: el)?)\s*"
                      rf"(\d{{1,2}}(?:st|nd|rd|th|er)?\.?\s+(?:de\s+)?(?:{_MON})\.?,?\s+(?:de\s+)?\d{{4}}|"
                      rf"(?:{_MON})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|\d{{1,2}}(?:st|nd|rd|th|er)?\.?\s+(?:de\s+)?(?:{_MON})|"
                      rf"(?:{_MON})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?)", re.I)


def _quote(verbatim: str, raw: str = "", limit: int = 240) -> str:
    """Verbatim evidence for one date: the unit itself, or a window of it that still contains the date."""
    full = clean_snippet(verbatim, 100_000)
    i = full.find(raw) if raw else -1
    if len(full) <= limit or i < 0 or i + len(raw) <= limit:
        return full[:limit]
    start = max(0, i + len(raw) - limit)
    start = full.find(" ", start) + 1 if full.find(" ", start) != -1 and start > 0 else start
    return full[start:i + len(raw) + 40][:limit]


# Round 27: a call the page says is closed, with or without a date ("Applications for the Rhodes Scholarship are now
# closed", "The call for the academic year 2026-2027 is now closed", "Applications closed for 2026", "STATUS Closed")
CLOSED_RX = re.compile(r"^(?!(?:if|when|once|after)\b).{0,80}?(?:\bapplications?\b[^.]{0,60}?\b(?:are|is|have|has)? ?(?:now )?"
                       r"closed\b|\b(?:call|round|competition|application (?:period|window))\b[^.]{0,50}?\b(?:is|are|has|have)"
                       r" (?:now )?(?:been )?closed\b|\bno longer accepting applications\b|^applications closed\b|"
                       r"^status:?\s*closed$|"
                       # round 30: "The application deadline has passed", "Die Frist zur Bewerbung ... ist verstrichen"
                       r"\b(?:deadline|frist|bewerbungsfrist)\b[^.]{0,80}?\b(?:has (?:now )?(?:passed|expired)|"
                       r"ist (?:bereits )?(?:verstrichen|abgelaufen))\b)", re.I)
# "The scholarship is currently unavailable": no cycle is running and the next one is not announced
UNAVAILABLE_RX = re.compile(r"\b(?:scholarships?|programm?es?|awards?|fellowships?|grants?) (?:is|are) (?:currently |"
                            r"temporarily )?(?:unavailable|not available|suspended|not (?:being )?offered)\b|"
                            r"\bnot (?:currently )?(?:open|accepting applications) (?:at (?:this|the moment)|this year)\b", re.I)
CLOSED_NOTE, UNAVAILABLE_NOTE = "closed: no date stated", "currently unavailable"
_MONTHS3 = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_WINDOW_RX = re.compile(r"\bapplication (?:period|window)s?:?\s+(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|"
                             r"sep\w*|oct\w*|nov\w*|dec\w*)\.? (20\d\d)\s*[-–]\s*[a-z]{3,9}\.? 20\d\d\b", re.I)
# "assessed and awarded on a rolling basis" orders the review of applications; it is not a rolling cycle
ROLLING_ASSESSMENT = re.compile(r"\b(?:assess|award|select|evaluat|allocat|process)\w*\b[^.]{0,30}\bon a rolling basis", re.I)


def _date_role(s: str, raw: str, prev: list[str], raws: list[str]) -> Optional[DeadlineKind]:
    """Round 28: what one date in a sentence is for, read from the words next to it.
    NOMINATION  "School nomination deadline: October 9", "selection deadline by master's program coordinators",
                "access to the nomination form beginning July 6"
    OPENING     "1 December 2026: Application opens", "The next call will open on November 15, 2026"
    DOCUMENT    "must submit proof no later than October 15" (a document, not the application)
    None        the sentence's own reading stands (an application deadline unless other rules said otherwise)"""
    from .evidence import clause_before
    start = s.find(raw)
    if start < 0:
        return None
    before = clause_before(s, raw, prev)[:-len(raw) or None]
    nxt = [s.find(r, start + len(raw)) for r in raws if r != raw and s.find(r, start + len(raw)) > 0]
    after = s[start + len(raw): min(nxt) if nxt else len(s)]
    after = re.split(r"[.;]\s|\.$", after, maxsplit=1)[0]
    before = re.sub(r"(?:external link)?,? opens in a new (?:tab|window)", " ", before, flags=re.I)   # link text
    near = before[-90:] + " " + after[:70]
    # round 30: later steps and other periods. "30 March: Applicants are informed", "Aufenthaltsbeginn ... ab dem 1.
    # August 2028", "have paid the application fee by 2 February", "receive an offer ... by 31st March, must accept
    # ... as a Firm choice by 3 May", "residence permit is still valid until"
    # round 31: "News from Dec 10, 2025", "published April 21, 2026": the page's own date, not a deadline
    if re.search(r"\b(?:news|posted|published|updated|last modified|stand)\s*(?:from|on|am)?\s*:?\s*$", before[-40:], re.I):
        return DeadlineKind.OTHER
    if re.search(r"renovaci[o\u00f3]n|renovaciones|\brenewals?\b|renouvellement|verl[a\u00e4]ngerung", s, re.I):
        return DeadlineKind.OTHER   # round 41: the renewal period of current awardees, not an application window
    # round 31: "The fellowship term must begin no earlier than July 1, 2027 ... must conclude no later than ..."
    if re.search(r"\b(?:term|tenure|award (?:period|year)|funding period|fellowship period)\b[^.;]{0,60}"
                 r"\b(?:begin|start|commenc|end|conclude)", s[max(0, start - 120):start], re.I) \
            or re.search(r"\bconclude\b[^.;]{0,30}$", before[-50:], re.I):
        return DeadlineKind.EVENT
    # round 31: "1 February 2027: deadline to submit supporting documentation and pay the application fee"
    if re.match(r"\W{0,3}(?:deadline )?(?:to submit|for submitting|for the submission of) (?:supporting |the |your )?document", after, re.I):
        return DeadlineKind.DOCUMENT
    if re.match(r"\W{0,3}(?:deadline )?for (?:sending|submitting|giving|providing) (?:the )?feedback\b", after, re.I):
        return DeadlineKind.OTHER   # round 34: "17 November 2027: deadline for sending feedback"
    if re.search(r"\b(?:programs?|programmes?|courses?|studies|study|stays?|projects?)\s+(?:beginning|starting|commencing|that (?:begin|start))"
                 r"\s+(?:between|on|after|before|from|in|by)?\s*[^.;()]{0,45}$", s[max(0, start - 120):start], re.I):
        return DeadlineKind.EVENT   # round 42: "(for study abroad programs beginning between December 1, 2026, to October 31, 2027)"
    if re.search(r"\b(?:the )?week of\s*$", before[-30:], re.I):
        return DeadlineKind.EVENT   # round 45: "a workshop the week of August 12-13, 2026"
    if re.search(r"\b(?:closed|close)\s+(?:until|till)\s*$", before[-30:], re.I):
        return DeadlineKind.OPENING   # round 45: "Applications are now closed until November 10, 2026"
    if re.match(r"\W{0,3}opening call\b", after, re.I):
        return DeadlineKind.OPENING
    if re.match(r"\W{0,3}closing call\b", after, re.I):
        return DeadlineKind.SCHOLARSHIP
    if re.match(r"\W{0,3}(?:applicants?|candidates?|you|students?)?\s*(?:are|will be)?\s*(?:informed|notified)\b", after, re.I) \
            or re.search(r"\b(?:informed|notified|communication of (?:the )?decisions?|decisions? (?:will be )?"
                         r"(?:communicated|announced)|results? (?:will be )?(?:announced|published|communicated))\b"
                         r"[^.;]{0,40}$", before[-60:], re.I):
        return DeadlineKind.EVENT
    if re.search(r"\b(?:aufenthalt\w*|stay|tenure|arrival|start of (?:the )?(?:programme|program|studies|fellowship|award)|"
                 r"(?:programme|program|course|studies|fellowship) (?:start|begin|beginning|commencement))\b"   # round 49
                 r"[^.;]{0,50}$", before[-70:], re.I):
        return DeadlineKind.EVENT
    if re.search(r"\bas of\s*$|\bt[ií]tulo\b[^.;]{0,25}$|\b(?:inscrit\w*|enrolled|registered|matricul\w+)\b[^.;]{0,70}\b(?:avant le|before|prior to|by|hasta)\s*$", before[-100:], re.I):
        return DeadlineKind.OTHER   # round 34: "residing in Japan as of July 1", "obtendrán su título hasta el 1 de agosto"
    if re.search(r"\b(?:paid|pay) (?:the |your )?(?:application |tuition )?fees?\b[^.;]{0,20}$|"
                 r"\boffer\b[^.;]{0,40}\bby\s*$|\baccept\b[^.;]{0,60}\bby\s*$|"
                 r"\b(?:visa|residence permit)\b[^.;]{0,60}$", before[-80:], re.I):
        return DeadlineKind.OTHER
    if re.search(r"\b(?:fee )?payment\b|\bpay (?:the |your )?(?:tuition|fees?)\b", near, re.I) \
            and not re.search(r"\bappl", near, re.I):
        return DeadlineKind.OTHER   # "The deadline for tuition fee payment ... is 31 August": paying, not applying
    if re.search(r"\b(?:campus|internal|university|departmental|faculty) deadline\b", near, re.I):
        return DeadlineKind.NOMINATION   # round 39: "the campus deadline of Sept. 11" is the university's own step
    if re.search(r"nominat|selection deadline by|\bby (?:the )?(?:[\w']+ ){0,3}coordinators?\b|\bendorsement\b", near, re.I):
        return DeadlineKind.NOMINATION
    if re.search(r"\bproof\b|\bsubmit (?:your )?(?:final )?(?:transcripts?|certificates?|degree)", before[-90:], re.I) \
            and not re.search(r"\bappl", before[-30:] + after[:40], re.I) \
            and not re.search(r"\bapplications? and (?:the )?submission\b", before[-90:], re.I):
        return DeadlineKind.DOCUMENT   # but "Deadline for application and submission of documentation" is the deadline
    if re.search(r"\b(?:close|closes|closing(?: date)?|last (?:application )?date|final (?:application )?deadline)\s*:?\s*$", before[-30:], re.I):
        return DeadlineKind.SCHOLARSHIP   # round 34: "Open: 1 December 2026 / Close: 12 February 2027"
    if re.match(r"\s*[:–-]?\s*(?:the )?(?:applications?|call|portal|registration)?\s*(?:opens?|starts?|begins?)\b", after, re.I) \
            or (re.search(r"\b(?:will )?(?:open(?:s|ing)?|begin(?:s|ning)?|start(?:s|ing)?)\s*(?:on|from)?\s*$", before, re.I)
                and not re.search(r"\buntil\b|\bclos|deadline|\bby\s*$|\bthrough\s*$", before[-40:], re.I)):
        return DeadlineKind.OPENING
    return None


FAQ_HEAD = re.compile(r"^(?:frequently asked questions|faqs?|questions and answers|q\s*&\s*a)\b", re.I | re.M)


def _old_references(out: list, text: str, today: date) -> None:
    """Round 28: when the page states an applicant deadline ahead, past applicant dates in its FAQ, or more than ~10
    months before that deadline, belong to an earlier cycle ("This year's deadline ... is October 10, 2025" in an
    FAQ written for last year). They stay on the record as REFERENCE, never as the application deadline."""
    appl = (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION)
    ahead = sorted(date.fromisoformat(d.date) for d in out if d.kind in appl and d.date and date.fromisoformat(d.date) >= today)
    faq = FAQ_HEAD.search(text)
    if not ahead:
        # round 31: a date more than ~13 months old inside an FAQ ("When is the deadline? Applications closed on
        # September 1, 2019") is an old answer, not this deadline; a dated "Application Close" line elsewhere stays
        for d in out:
            pos = text.find(d.label[:40]) if d.label else -1
            if faq and pos > faq.start() and d.kind in appl and d.date and (today - date.fromisoformat(d.date)).days > 400:
                d.kind = DeadlineKind.REFERENCE
        return
    for d in out:
        if d.kind in appl and d.date and date.fromisoformat(d.date) < today:
            pos = text.find(d.label[:40]) if d.label else -1
            age = (today - date.fromisoformat(d.date)).days
            if (faq and pos > faq.start() and age > 180) or (ahead[0] - date.fromisoformat(d.date)).days > 300:
                d.kind = DeadlineKind.REFERENCE


# Round 29: which programme a date belongs to. A page often names other awards ("apply by the deadline for the Gates
# Cambridge Scholarship", "Vingroup Young Talent Scholarship at SMU: applications close ...") or a partner's own window
# ("Application period at Tec: August 3 - September 3"); those dates are not the evaluated programme's deadline.
AWARD_NAME_RX = re.compile(r"\b((?:[A-Z][\w'’&-]+\s+){1,5}(?:Scholarships?|Fellowships?|Awards?|Grants?|Bursar(?:y|ies)|"
                           r"Studentships?|Prizes?|Internships?))\b|\bthe ((?:[A-Z][\w'’&-]+\s){1,4})(?:deadline|application)\b")
_OWN_GENERIC = {"the", "a", "an", "of", "for", "and", "in", "at", "to", "on", "scholarship", "scholarships", "fellowship",
                "fellowships", "award", "awards", "grant", "grants", "bursary", "bursaries", "studentship", "studentships",
                "prize", "prizes", "programme", "programmes", "program", "programs", "university", "college", "school",
                "msc", "ma", "mba", "master", "masters", "phd", "doctoral", "bachelor", "undergraduate", "graduate",
                "postgraduate", "degree", "study", "studies", "research", "application", "admission", "home", "page"}
PARTNER_WINDOW_RX = re.compile(r"\b(?:application period|applications?|deadline)\s+(?:at|for)\s+(?!(?:Fall|Spring|Summer|Winter|"
                               r"Autumn|January|February|March|April|May|June|July|August|September|October|November|"
                               r"December|Master|Bachelor|PhD|Undergraduate|Graduate|International|Domestic|Round|Window|"
                               r"Intake|Entry|the|this|all)\b)((?:[A-Z][\w'’&.-]*\s?){1,4}):", re.I)


def _name_tokens(name: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in _OWN_GENERIC and not w.isdigit()}


def own_programme_tokens(text: str, title: str) -> set:
    """Distinctive words of the programme a page is about: its title, plus the award name the page repeats most."""
    counts: dict = {}
    for m in AWARD_NAME_RX.finditer(text):
        k = frozenset(_name_tokens(m.group(1) or m.group(2)))
        if k:
            counts[k] = counts.get(k, 0) + 1
    top = max(counts.items(), key=lambda kv: kv[1], default=(frozenset(), 0))
    return _name_tokens(title) | (set(top[0]) if top[1] >= 2 else set())


def _foreign(name: str, own: set) -> bool:
    toks = _name_tokens(name)
    return bool(toks) and bool(own) and bool(toks - own) and bool(own - toks)


def _owned_elsewhere(d: Deadline, own: set) -> bool:
    """True when the nearest award named before the date in its quotation is another programme, or the date sits in a
    partner institution's own window."""
    if not d.label or not own:
        return False
    pos = next((d.label.find(raw) for x, raw in parse_dates(d.label) if x and x.isoformat() == d.date and raw in d.label), -1)
    if pos < 0:
        return False
    before = d.label[:pos]
    if PARTNER_WINDOW_RX.search(before[-90:]):
        return True
    # a track named in brackets after the date label ("Closing Date (Music Practice Grant): 15 December 2026") is part
    # of this call, not another programme
    before = re.sub(r"\b(?:closing date|deadline|application period|opening date)\s*\([^)]*\)", " ", before, flags=re.I)
    names = [m.group(1) or m.group(2) for m in AWARD_NAME_RX.finditer(before)]
    return bool(names) and _foreign(names[-1], own)


def extract_deadlines(text: str, url: str, today: date, title: str = "") -> list[Deadline]:

    out: list[Deadline] = []
    page_cycle = detect_cycle(text)
    from .evidence import ROLLING_RX, UNPUBLISHED_RX, clause_before, clause_role, clause_scope
    role_open: set = set()   # dates the words next to them call an opening ("1 December 2026: Application opens")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):   # "STATUS" on one line and "Closed" on the next
        if line.lower() in ("status", "status:") and i + 1 < len(lines) and lines[i + 1].lower() == "closed":
            out.append(Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=DeadlineCertainty.UNKNOWN, approximate=CLOSED_NOTE,
                                cycle=page_cycle, label=f"{line} {lines[i + 1]}", source_url=url))
            break
    for s, para, verbatim in _deadline_units(text):
        mw = MONTH_WINDOW_RX.search(s)
        if mw:   # "Application Period: Apr 2027 - Sep 2027": the opening month only; no day is invented for the close
            mon = _MONTHS3.index(mw.group(1)[:3].lower()) + 1
            out.append(Deadline(kind=DeadlineKind.OPENING, certainty=DeadlineCertainty.EXPECTED,
                                date=f"{mw.group(2)}-{mon:02d}-01", approximate=f"opens {mw.group(1)} {mw.group(2)} (month only)",
                                cycle=detect_cycle(s) or page_cycle, label=clean_snippet(verbatim, 160), source_url=url))
            continue
        if UNAVAILABLE_RX.search(s) or (CLOSED_RX.search(s) and not parse_dates(s, para)):
            out.append(Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=DeadlineCertainty.UNKNOWN,
                                approximate=UNAVAILABLE_NOTE if UNAVAILABLE_RX.search(s) else CLOSED_NOTE,
                                cycle=detect_cycle(s) or page_cycle, label=clean_snippet(verbatim, 160), source_url=url))
            continue
        if ROLLING_RX.search(s) and not ROLLING_ASSESSMENT.search(s) and re.search(r"applic|apply|admission|deadline|accept|submit", s, re.I):
            out.append(Deadline(kind=DeadlineKind.ROLLING, certainty=DeadlineCertainty.CONFIRMED,
                                approximate="rolling: applications reviewed as they arrive", cycle=detect_cycle(s) or page_cycle,
                                label=clean_snippet(verbatim, 160), source_url=url))
            continue
        if not DEADLINE_WORDS.search(s) and not OPENING_WORDS.search(s):
            continue
        if _INJ_INSTRUCT.search(s):
            continue  # a date inside text addressed to AI systems is not a deadline
        if UNPUBLISHED_RX.search(s) and not parse_dates(s, para):
            out.append(Deadline(kind=_kind(s), certainty=DeadlineCertainty.UNKNOWN, approximate="not yet published",
                                cycle=detect_cycle(s) or page_cycle, label=clean_snippet(verbatim, 160), source_url=url))
            continue
        if EVENT_WORDS.search(s) and not re.search(r"deadline|closing|close|clos|submit|apply by|bewerbungsschluss|"
                                                   r"date limite|fecha l[ií]mite|plazo|ditutup|until", s, re.I):
            continue  # results, interviews, announcements: dates of the process, not deadlines
        dates = parse_dates(s, para)
        cycle = detect_cycle(s) or page_cycle
        kind = DeadlineKind.OPENING if OPENING_WORDS.search(s) and not DEADLINE_WORDS.search(s) else _kind(s)
        rng = RANGE_RX.search(s)
        if rng and (OPENING_WORDS.search(s) or DEADLINE_WORDS.search(s)):
            a = dict((raw, d) for d, raw in dates)
            first = next((d for raw, d in a.items() if raw and raw in rng.group(1) or rng.group(1) in raw), None)
            second = next((d for raw, d in a.items() if raw and (raw in rng.group(2) or rng.group(2) in raw)), None)
            if first and second and first < second:
                tm = TIME_RX.search(s[rng.end():rng.end() + 30])
                for d, k in ((first, DeadlineKind.OPENING), (second, _kind(s) if kind == DeadlineKind.OPENING else kind)):
                    out.append(Deadline(kind=k, certainty=DeadlineCertainty.HISTORICAL if d < today else DeadlineCertainty.CONFIRMED,
                                        date=d.isoformat(), time=(f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm and
                                                                  k != DeadlineKind.OPENING else None),
                                        timezone=None, cycle=cycle, label=_quote(verbatim, rng.group(0)), source_url=url))
                dates = [(d, raw) for d, raw in dates if d not in (first, second)]
                if not dates:
                    continue
        tm = TIME_RX.search(s)
        tz = TZ_RX.search(s)
        if not dates:
            rec = _recurring(s, para)
            # an applicant's date, not "Form 1042-S will be mailed no later than February 28th of each year"
            if rec and re.search(r"appl|submi|deadline|clos|bewerb|candida|inscri|postul|convocatoria|pendaftaran", s, re.I):
                raws = [r for _, r in rec]
                both = OPENING_WORDS.search(s) and DEADLINE_WORDS.search(s)
                for i, (md, raw) in enumerate(rec):
                    k = kind
                    if rng and raw in rng.group(1):   # "1 October to 15 January (midnight) for ... the winter semester"
                        k = DeadlineKind.OPENING
                    elif rng and raw in rng.group(2):
                        k = _kind(s) if kind == DeadlineKind.OPENING else kind
                    elif both and len(rec) == 2:
                        k = DeadlineKind.OPENING if i == 0 else _kind(s)
                    own = _date_role(s, raw, raws[:i], raws)
                    k = own if own is not None else k
                    out.append(Deadline(kind=k, certainty=DeadlineCertainty.EXPECTED, recurs=md, cycle=cycle,
                                        approximate=f"every year on {int(md[3:])} {_MONTH_NAMES[int(md[:2]) - 1]}",
                                        label=_quote(verbatim, raw), source_url=url))
                continue
            mon = re.search(rf"\b({_MON})\b", s, re.I)
            if mon and APPROX_WORDS.search(s):
                out.append(Deadline(kind=kind, certainty=DeadlineCertainty.EXPECTED, approximate=clean_snippet(verbatim, 160),
                                    cycle=cycle, label=clean_snippet(verbatim, 160), source_url=url))
            continue
        both = OPENING_WORDS.search(s) and DEADLINE_WORDS.search(s)
        dated = sorted(d for d, _ in dates if d)
        in_order = sorted(dates, key=lambda t: s.find(t[1]))
        base_kind = kind
        for d, raw in dates:
            kind = base_kind
            if both and len(dated) == 2:
                # "opens on X and closes on Y": the earlier date is the opening
                kind = DeadlineKind.OPENING if d == dated[0] else _kind(s)
            # Several dates in one sentence: each belongs to its own clause ("for students ... 31-10-2026 and for
            # institute verification ... 15-11-2026"). A clause about institutions or events is not the applicant's.
            prev = [r for _, r in in_order[:[r for _, r in in_order].index(raw)]] if len(dates) > 1 else []
            clause = clause_before(s, raw, prev) if len(dates) > 1 else s
            role = clause_role(clause)
            if role is not None and kind != DeadlineKind.OPENING:
                kind = role
            if kind == DeadlineKind.OPENING and re.search(r"\b(?:through|until|till)\s*$", s[:max(0, s.find(raw))], re.I):
                kind = _kind(s)   # round 30: "open now and accepting applications through October 27": the close
            own = _date_role(s, raw, prev, [r for _, r in in_order])
            if own is not None:
                kind = own
                if own == DeadlineKind.OPENING and d:
                    role_open.add(d.isoformat())
            scope, applies = clause_scope(clause, s)
            if d is None:
                out.append(Deadline(kind=kind, certainty=DeadlineCertainty.UNKNOWN, approximate=f"ambiguous date '{raw}'",
                                    cycle=cycle, label=_quote(verbatim, raw), source_url=url))
                continue
            if APPROX_WORDS.search(s) and re.search(r"usually|typically|expected|tentative", s, re.I):
                certainty = DeadlineCertainty.EXPECTED
            elif d < today:
                certainty = DeadlineCertainty.HISTORICAL
            else:
                certainty = DeadlineCertainty.CONFIRMED  # confirmed by *this page*; verify.py decides officialness
            out.append(Deadline(kind=kind, certainty=certainty,
                                date=d.isoformat() if certainty != DeadlineCertainty.EXPECTED else None,
                                approximate=raw if certainty == DeadlineCertainty.EXPECTED else None,
                                time=f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None,
                                timezone=tz.group(0) if tz else None, cycle=cycle,
                                label=_quote(verbatim, raw), source_url=url, scope=scope, applies_to=applies))
    own = own_programme_tokens(text, title)
    for d in out:
        if d.date and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION, DeadlineKind.OPENING) and _owned_elsewhere(d, own):
            d.kind = DeadlineKind.OTHER_PROGRAMME
    _old_references(out, text, today)
    # one entry per date and kind; a date read as an opening, nomination or reference in one unit is that in all
    # (a heading glued to "1 December 2026: Application opens" must not turn the opening into a deadline)
    for d in out:
        if d.date in role_open and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION):
            d.kind = DeadlineKind.OPENING
    # one entry per (kind, date, approximate)
    uniq, seen = [], set()
    for d in out:
        k = (d.kind, d.date, d.approximate)
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


CURRENCIES = {"￥": "JPY", "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "$": "USD", "usd": "USD", "us$": "USD",
              "£": "GBP", "gbp": "GBP", "¥": "JPY", "jpy": "JPY", "yen": "JPY", "aud": "AUD", "a$": "AUD",
              "cad": "CAD", "c$": "CAD", "chf": "CHF", "sek": "SEK", "nok": "NOK", "dkk": "DKK", "krw": "KRW",
              "₩": "KRW", "cny": "CNY", "rmb": "CNY", "yuan": "CNY", "huf": "HUF", "ft": "HUF", "try": "TRY",
              "₺": "TRY", "idr": "IDR", "rp": "IDR", "inr": "INR", "₹": "INR", "nzd": "NZD", "sgd": "SGD",
              "s$": "SGD", "pln": "PLN", "czk": "CZK", "myr": "MYR", "rm": "MYR", "twd": "TWD", "nt$": "TWD",
              # more currencies seen on official pages; "kr" is left out (Danish, Norwegian and Swedish crowns)
              "zł": "PLN", "r$": "BRL", "brl": "BRL", "mxn": "MXN", "hk$": "HKD", "hkd": "HKD", "₽": "RUB", "rub": "RUB",
              "zar": "ZAR", "egp": "EGP", "sar": "SAR", "aed": "AED", "qar": "QAR", "ngn": "NGN", "₦": "NGN", "kes": "KES",
              "thb": "THB", "฿": "THB", "vnd": "VND", "₫": "VND", "ron": "RON", "₱": "PHP", "uah": "UAH", "₴": "UAH",
              "isk": "ISK", "clp": "CLP", "cop": "COP", "ars": "ARS", "pen": "PEN", "円": "JPY", "元": "CNY", "원": "KRW"}
_CUR = "|".join(sorted((re.escape(c) for c in CURRENCIES), key=len, reverse=True))
AMOUNT_RX = re.compile(rf"(?:(?P<c1>{_CUR})\s?(?P<a1>\d[\d,.'’ ]*\d(?:\s?[kK]\b)?|\d(?:\s?[kK]\b)?))|(?:(?P<a2>\d[\d,.'’ ]*\d|\d)\s?(?P<c2>{_CUR})(?!\w))",
                       re.I)
PERIOD_RX = re.compile(r"per month|a month|monthly|/\s?month|per (?:academic )?year|a year|per annum|annually|/\s?year|"
                       r"per semester|a semester|/\s?semester|pro semester|par semestre|"
                       r"monatlich|pro monat|im monat|par mois|mensuel(?:le)?|al mes|mensual(?:es)?|por mes|"
                       r"por m[eê]s|mensais|per bulan|/\s?bulan|setiap bulan|jährlich|pro jahr|par an|al año|"
                       r"por año|por ano|per tahun|"
                       r"one[- ]off|lump sum|in total|total", re.I)

FUNDING_KEYS = [
    ("tuition", r"tuition|(?:university|college)(?: and college)? fees|course fees?|programme fees?|study fees?|fee waiver|fees? (?:are )?waived|fee offset|"
                # round 30: "a contribution of up to £15,000 towards fees paid directly to your university"
                r"\btowards (?:the |your )?fees\b|"
                r"studiengebühren|frais de scolarité|frais d'inscription|matr[ií]cula|tasas académicas|"
                r"mensalidades?|tasse universitarie|biaya (?:pendidikan|kuliah)|\bspp\b|\bukt\b"),
    ("award", r"monetary award|award (?:of|amount)|amount of the grant|the grant (?:is|amounts to)|grant of|prize money|"
              r"\bcrédito\b|préstamo|\bloan\b|preisgeld|bursary of|"
              # "These fellowships, worth CHF 10,000 per semester", "a grant amounting to CHF 10'000"
              r"(?:scholarships?|fellowships?|grants?),? worth|grant amounting to|"
              # round 49: "The fellowship is worth 3,600 EUR per month", "grant: 1,500 EUR per month"
              r"(?:scholarships?|fellowships?|grants?) (?:is|are|will be) worth|"
              r"\b(?:grant|funding|scholarship amount|scholarship value)\s*:\s*(?:up to\s*)?(?=[\d€$£])"),
    ("stipend", r"\bstipends?\b|\b(?:monthly )?base amount\b|\d[\d.,]* ?(?:euro|€) (?:im|pro) monat|monthly allowance|maintenance|salary|bursary payment|(?<!processes )(?<!process )scholarship payments?|stipendienleistung|"
                r"monatliche (?:rate|zahlung)|\bmonatlich\b|(?<!other )(?<!any )(?<!existing )(?<!graduate )financial support(?! to (?:aid|help|assist|support|enable|allow)\b)(?! (?:for|to) (?:students|applicants|those|people|yourself|individuals|young|recipients|[\w-]+ (?:students|scholars)))|"
                r"monthly (?:scholarship|payment|rate|instalment)|monatlich(?:e|es)? (?:stipendium|rate)|"
                r"allocation mensuelle|asignaci[oó]n mensual|manuten[cç][aã]o|uang saku|tunjangan bulanan"),
    ("living_allowance", r"living (?:and related )?(?:allowance|costs?|expenses)|subsistence|cost[- ]of[- ]living|"
                         r"room and board|board and lodging|housing,? (?:and )?(?:food|meals)|"
                         r"lebenshaltung|frais de vie|gastos de manutenci[oó]n|biaya hidup"),
    ("accommodation", r"accommodation|housing|dormitor(?:y|ies)|lodging|residence halls?|wohnheim|unterkunft|"
                      r"logement|alojamiento|moradia|asrama"),
    ("travel", r"travel|airfare|air ticket|flight|return ticket|reisekosten|billet d'avion|pasaje|passagem|"
               r"tiket pesawat|biaya transportasi"),
    ("insurance", r"health insurance|medical insurance|insurance|health cover\b|krankenversicherung|assurance maladie|"
                  r"seguro m[eé]dico|asuransi kesehatan"),
    ("relocation", r"settling[- ]in|relocation|arrival allowance|installation allowance"),
    ("research", r"research (?:grant|allowance|costs)|thesis allowance|conference|study allowance|book allowance"),
]
def _amount_owner(low: str, amount) -> Optional[str]:
    """The funding component an amount belongs to: the nearest keyword before it, else the nearest after."""
    before, after = None, None
    for k, rx in FUNDING_KEYS:
        for m in re.finditer(rx, low):
            if m.end() <= amount.start():
                if before is None or m.end() > before[1]:
                    before = (k, m.end())
            elif m.start() >= amount.end() and (after is None or m.start() < after[1]):
                after = (k, m.start())
    return (before or after or (None,))[0]


def _other_key_between(low: str, kind: str, key, amount) -> bool:
    lo, hi = sorted((key.end(), amount.start()))
    between = low[lo:hi]
    return any(re.search(rx, between) for k, rx in FUNDING_KEYS if k != kind)


NEGATION = re.compile(r"\b(not|no|excluding|except|does not|doesn't|won't|will not|nor|nicht|kein(?:e|en)?|"
                      r"ne (?:couvre|comprend) pas|no (?:cubre|incluye)|tidak)\b", re.I)


def _amount(m) -> tuple[Optional[float], Optional[str]]:
    a = m.group("a1") or m.group("a2")
    c = (m.group("c1") or m.group("c2") or "").lower()
    a = a.replace(" ", "").replace("'", "").replace("’", "")
    mult = 1
    if a[-1:] in "kK":
        a, mult = a[:-1], 1000
    if re.search(r",\d{2}$", a) and "." not in a:   # 1.200,50 / 934,00
        a = a.replace(".", "").replace(",", ".")
    else:
        a = a.replace(",", "")
        if a.count(".") > 1 or re.search(r"\.\d{3}$", a):
            a = a.replace(".", "")
    try:
        return float(a) * mult, CURRENCIES.get(c)
    except ValueError:
        return None, CURRENCIES.get(c)


BENEFIT_HEAD = re.compile(r"^(?:scholarship )?(?:benefits?|entitlements|what (?:the|does the|is) .{0,30}cover\w*|"
                          r"scholarship (?:covers|value|amount)|value|leistungen|stipendienleistung|beneficios|"
                          r"komponen beasiswa|avantages|monthly stipend.{0,30})\s*:?$", re.I)


def _funding_units(text: str) -> list[str]:
    """Sentences, with a benefits heading glued to the line under it ("Scholarship Benefits: Airfare, tuition...")."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    merged = []
    i = 0
    while i < len(lines):
        if len(lines[i]) <= 50 and BENEFIT_HEAD.match(lines[i]) and i + 1 < len(lines):
            merged.append(f"{lines[i]} {lines[i + 1]}")  # verbatim: evidence must quote the page
            i += 2
            continue
        merged.append(lines[i])
        i += 1
    return [s for line in merged for s in _sentences(line)]


OWN_COST = re.compile(r"own funds|proof of (?:your )?(?:own )?funds|may not cover|not cover all|might not cover|"
                      r"own (?:cost|expense)s?\b|at (?:your|their) own|you (?:may|might|will) (?:already )?have (?:various )?"
                      r"expenses", re.I)
EXCL_HEAD = re.compile(r"costs? (?:we|which) will not|will not (?:reimburse|cover|pay)|not (?:be )?(?:covered|reimbursed)|"
                       r"not included|excluded|not be eligible|not eligible if|ineligible", re.I)
LIST_BENEFIT_HEAD = re.compile(r"benefits?|will provide|provides the following|covers?:|includes?:|what (?:the )?"
                               r"(?:scholarship|grant) cover|what does the (?:funding|scholarship|grant) cover|"
                               r"provides support .{0,40}in the form of|"
                               # round 30: a heading line "The scholarship covers" with the items below it
                               r"\b(?:scholarships?|awards?|grants?|fellowships?) (?:covers?|includes?|provides?)\s*$", re.I)
# Round 27: sentences that state a condition on the applicant, not a benefit ("you must ... be required to pay tuition
# fees", "not eligible for the lower EU/EEA tuition fee", "candidates secure their own ... tuition awards")
COST_OF_ATTENDANCE_RX = re.compile(r"\b(?:entire|full|total|complete) cost of attendance\b|\ball (?:educational )?costs of attendance\b|"
                                   r"\bcovers? (?:the )?(?:entire|full|total) cost of (?:attending|study(?:ing)?)\b", re.I)
MIXED_EXTENT_RX = re.compile(r"\b(?:full or partial|partial or full|part or all|all or part)\b|\d+ ?% (?:or|and|to) 100 ?%|"
                             r"ranging from \d+ ?% to 100 ?%|up to 100 ?%|full tuition fees? ?/ ?partial|full tuition (?:fee )?discount for (?:the )?first year", re.I)
# tuition support stated as partial: a discount, a reduction, a share, a cap in money ("up to two years" is a duration)
PARTIAL_TUITION = re.compile(r"partial|(?<!any )part of|part or all|reimburse|discount|reduction|depends on|contribut|"
                             r"up to (?![\w ]{0,8}\b(?:years?|months?|semesters?|terms?|meals?|credits?|hours?)\b)|\d+ ?%(?<!100%)(?<!100 %)", re.I)
# wording that states full coverage outright, whatever cap or duration follows ("Full tuition ... (worth up to USD 35,000)")
STRONG_FULL = re.compile(r"full tuition|full (?:course |tuition )?fees? (?:are |is )?(?:covered|waived|paid)|tuition fees? (?:are |is )?"
                         r"fully (?:covered|paid|waived)|full fee (?:waiver|offset)|full funding for (?:the )?tuition|"
                         r"full costs? of (?:the )?tuition|100 ?% (?:of )?(?:the )?tuition", re.I)
NOT_BENEFIT = re.compile(r"\b(?:you|applicants?|candidates?) (?:must|should|need to)\b|\brequired to pay\b|"
                         r"\b(?:are|is) not (?:eligible|the recipient)|eligible for the lower|cannot secure|"
                         r"\bsecure their own\b|\bindependently\b|sponsorship that covers|\bif you (?:receive|hold)\b|"
                         r"can be combined with|does not exceed|responsible for (?:covering|paying|the cost)|"
                         r"\bliable (?:for|to pay)\b|\brestitution\b|\brepay(?:ment)?\b|\bpay (?:it )?back\b|"
                         # round 30: "Applicants are obliged to declare ...", "you will be required to cover the costs
                         # of tuition fees at the regular Quebec rate"
                         r"\bobliged to\b|\breduced accordingly\b|\brequired to cover\b", re.I)


def _list_context(lines: list[str], unit: str) -> tuple[Optional[str], str]:
    """('exclusion' | 'benefit', the heading) when a short list item sits under such a heading, else (None, "")."""
    u = " ".join(unit.lower().split())[:50]
    for i, line in enumerate(lines):
        if u and u in " ".join(line.lower().split()):
            for prev in reversed(lines[max(0, i - 10):i]):
                if OWN_COST.search(prev) or (len(prev) <= 90 and EXCL_HEAD.search(prev)):
                    return "exclusion", prev
                if len(prev) <= 90 and LIST_BENEFIT_HEAD.search(prev):
                    return "benefit", prev
                if len(prev) > 200:
                    break
            return None, ""
    return None, ""


def extract_funding(text: str) -> tuple[list[FundingComponent], list[str]]:
    from .ai_extract import _paid_from_allowance
    comps: dict[str, FundingComponent] = {}
    snippets: dict[str, str] = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    partial_tuition = False
    for s in _funding_units(text):
        low = s.lower()
        if OWN_COST.search(s) or NOT_BENEFIT.search(s):
            continue  # expenses the scholar must plan for, or conditions on the applicant: not benefits
        if s.strip().endswith("?") or re.search(r"\b(?:include|explain|indicate|list|submit|attach|identify) (?:a |the |your )?"
                                                r"(?:table|budget|justification|source|amount|how|why|what|total)\b", low):
            continue  # round 33: "How long do holders receive financial support?", "include a table showing ... graduate stipends"
        if COST_OF_ATTENDANCE_RX.search(low):
            # round 31: "cover the entire cost of attendance for four years": tuition and living costs together
            for kind in ("tuition", "living_allowance"):
                comp = comps.get(kind) or FundingComponent(kind=kind, covered=True)
                comp.covered = True if comp.covered is not False else comp.covered
                if kind == "tuition":
                    comp.full = True
                comps[kind] = comp
                snippets.setdefault(kind, clean_snippet(s))
            continue
        context, head = _list_context(lines, s) if len(s) <= 160 else (None, "")
        if context == "exclusion":
            continue
        allowance_unit = False
        matched = set()
        for kind, rx in FUNDING_KEYS:
            m = re.search(rx, low)
            if not m:
                continue
            if (kind not in ("stipend", "living_allowance") or re.search(r"housing|board|food|meals", m.group(0))) \
                    and _paid_from_allowance(s, rx):   # "housing, food" paid out of an allowance is that allowance
                allowance_unit = True
                continue  # paid out of the allowance ("which you can use for housing, travel")
            matched.add(kind)
            # "not included" style negation within a few words of the keyword
            # round 49: a condition is not a negation ("if no guest room is available, an accommodation allowance")
            wide = re.sub(r"\bif\b[^,]*,", " ", low[max(0, m.start() - 80): m.start()])
            before = re.split(r"\b(?:but|however|whereas|while)\b|;", wide[-40:])[-1]
            after = low[m.end(): m.end() + 25]
            negated = (bool(NEGATION.search(before)) or bool(re.match(r"[^,.;]{0,12}\bnot\b", after))) \
                and not re.search(r"not only", before + low[m.start():m.end()] + after)
            comp = comps.get(kind) or FundingComponent(kind=kind, covered=None)
            if kind == "tuition" and (context == "benefit" or re.search(r"\bbenefits?\b", low)) \
                    and re.search(r"\bno tuition fees?\b|\bfree (?:study|tuition)\b|\btuition[- ]free\b", low):
                negated = False   # round 30: "Other benefits: Free study, No tuition fee" is tuition paid in full
                comp.full = True
            if negated and comp.covered is not True:   # a stated benefit is not undone by a later caveat
                comp.covered = False
            elif context == "benefit" or re.search(r"cover|include|provid|receive|award|grant|pa(?:y|id)|waive|full|free|offer|benefit|"
                           r"übernimmt|umfasst|erhalten|couvre|comprend|cubre|incluye|inclui|termasuk|mendapat|"
                           r"ditanggung|\d", low):
                comp.covered = True if comp.covered is not False else comp.covered
            if kind == "tuition" and STRONG_FULL.search(low):
                comp.full = True
            elif kind == "tuition" and re.search(r"full tuition|tuition fees? (?:are )?(?:fully )?(?:covered|waived)|"
                                               r"full(?:y)? (?:covers?|waive)|100 ?%|full fee waiver|"
                                               r"vollständig|intégralement|totalidad|penuh|completa|integral|"
                                               r"tuition fees? (?:will be|is|are) (?:fully )?covered|"
                                               r"cover(?:s|ing)? (?:the )?(?:full )?tuition|"
                                               # round 27: "Full fee offset", "Full funding for tuition fees",
                                               # "covers University of Oxford course fees", "the full cost of
                                               # tuition"
                                               r"full fee offset|full funding for (?:the )?tuition|"
                                               r"covers? (?:[\w-]+ ){0,4}(?:course|tuition|programme) fees|"
                                               # "a tuition fee waiver" alone does not say how much is waived
                                               r"full cost of (?:the )?tuition|tuition fees? (?:is|are) waived", low) \
                    and (not PARTIAL_TUITION.search(low) or STRONG_FULL.search(low)):
                comp.full = True
            if kind == "tuition" and comp.full is not True and PARTIAL_TUITION.search(low):
                comp.full = False   # "£16,000 tuition fee discount", "25% of tuition": partial, stated as such
                partial_tuition = partial_tuition or bool(comp.covered) and not MIXED_EXTENT_RX.search(low)
            if kind == "tuition" and MIXED_EXTENT_RX.search(low):
                # round 30: "50% or 100%", "a full or partial waiver", "20% to 100%": most awards are partial, so the
                # page does not prove full tuition for an applicant
                comp.full = False
            if kind == "tuition" and re.search(r"application fees?", low) and re.search(r"fee waiver|waived|waiver", low):
                comps.pop("tuition", None) if comps.get("tuition") is comp else None
                continue   # round 35: "application fee waivers" are about applying
            if kind == "tuition" and re.search(r"fee waiver|waived|waiver", low):
                comp.note = (comp.note or "fee waiver mentioned")
            # the amount nearest the keyword, and only if it is close: one sentence often lists several components
            ams = [a for a in AMOUNT_RX.finditer(low) if abs(a.start() - m.start()) <= 60
                   and not _other_key_between(low, kind, m, a) and _amount_owner(low, a) == kind]
            am = min(ams, key=lambda a: abs(a.start() - m.start())) if ams else None
            if am and comp.amount is None and kind in ("stipend", "living_allowance", "travel", "relocation",
                                                        "tuition", "research", "award"):
                comp.amount, comp.currency = _amount(am)
                snippets[kind] = clean_snippet(s)   # the quotation must state the amount it supports
                p = PERIOD_RX.search(low, am.end(), am.end() + 25) or PERIOD_RX.search(low, max(0, m.start() - 30), am.start()) \
                    or re.search(r"per academic year|per semester", low[am.end():am.end() + 50])
                if p:
                    pt = p.group(0).lower()
                    comp.period = ("semester" if re.search(r"semest", pt) else   # before "mes", which it contains
                                   "month" if re.search(r"month|monat|mois|mensu|mes|m[eê]s|bulan", pt) else
                                   "year" if re.search(r"year|annum|annual|jahr|\ban\b|año|ano|tahun", pt) else "total")
            comps[kind] = comp
            snippets.setdefault(kind, clean_snippet(f"{head}: {s}" if head and len(s.split()) < 6 else s))
        if allowance_unit and not matched & {"stipend", "living_allowance"}:
            # "€1,400 per month ..., which you can use for housing, food, travel": that is the living allowance
            comp = comps.get("living_allowance") or FundingComponent(kind="living_allowance", covered=True)
            am = AMOUNT_RX.search(low)
            if am and comp.amount is None:
                comp.amount, comp.currency = _amount(am)
                pr = PERIOD_RX.search(low, am.end(), am.end() + 25)
                if pr:
                    comp.period = "month" if re.search(r"month|monat|mois|mensu|mes|bulan", pr.group(0), re.I) else \
                        "year" if re.search(r"year|annum|annual|jahr|año|tahun", pr.group(0), re.I) else "total"
            comp.covered = True if comp.covered is not False else comp.covered
            comps["living_allowance"] = comp
            snippets["living_allowance"] = clean_snippet(s)
    if partial_tuition and comps.get("tuition") and comps["tuition"].full:
        # round 30: the page also states a partial or mixed tuition extent; the full-tuition sentence is often another
        # scheme on the same page, so full tuition is not proven for this award
        comps["tuition"].full = False
    # round 27: only the word "assistantship" in a sentence that is not a condition, quoted from that sentence
    # (a page that mentions "research assistants" is not an assistantship)
    asent = next((x for x in _funding_units(text) if re.search(r"\bassistantships?\b", x, re.I)
                  and not NOT_BENEFIT.search(x)
                  # round 30: "training must be completed ... if the fellow is involved in teaching assistantship duties"
                  and not re.search(r"\bmust\b|\bif (?:the|you|a)\b|\bsuch as\b|click here|more information", x, re.I)), "")
    if asent:
        comps.setdefault("assistantship", FundingComponent(kind="assistantship", covered=True))
        snippets.setdefault("assistantship", clean_snippet(asent))
    # a recurring cash grant with no other label ("fellowships worth CHF 10,000 per semester", "a grant of €10.225 ...
    # per academic year") is what the scholar lives on: a stipend. A one-off or unperiodic award stays an award.
    aw = comps.get("award")
    if aw and aw.covered and aw.amount and aw.period in ("month", "year", "semester") \
            and not re.search(r"\bminimum\b", snippets.get("award", ""), re.I) \
            and not any(comps.get(k) and comps[k].covered for k in ("stipend", "living_allowance")):
        comps["stipend"] = FundingComponent(kind="stipend", covered=True, amount=aw.amount, currency=aw.currency,
                                            period=aw.period, note="a recurring cash grant")
        snippets["stipend"] = snippets["award"]
        del comps["award"]
    return list(comps.values()), [snippets[c.kind] for c in comps.values()]


LANG_RX = [
    ("IELTS", re.compile(r"IELTS[^.\d]{0,60}?(\d(?:\.\d)?)\b", re.I)),
    ("TOEFL_IBT", re.compile(r"TOEFL(?:\s*iBT)?[^.\d]{0,60}?(\d{2,3})\b", re.I)),
    ("PTE", re.compile(r"\bPTE(?: Academic)?[^.\d]{0,40}?(\d{2})\b", re.I)),
    ("DUOLINGO", re.compile(r"Duolingo(?: English Test)?[^.\d]{0,40}?(\d{2,3})\b", re.I)),
    ("TESTDAF", re.compile(r"TestDaF[^.\d]{0,40}?(?:TDN\s*)?([3-5])\b", re.I)),
    ("DSH", re.compile(r"\bDSH[- ]?([1-3])\b")),
    ("DELF_DALF", re.compile(r"\b(?:DELF|DALF)\s*(?:niveau\s*)?([ABC][12])\b", re.I)),
    ("TOPIK", re.compile(r"TOPIK[^.\d]{0,30}?(?:level\s*)?([1-6])\b", re.I)),
    ("HSK", re.compile(r"\bHSK[^.\d]{0,20}?(?:level\s*)?([1-9])\b", re.I)),
    ("JLPT", re.compile(r"\bJLPT[^.\d]{0,20}?N([1-5])\b", re.I)),
]
CEFR = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
MOI_RX = re.compile(r"medium of instruction|\bMOI\b|taught (?:entirely |exclusively )?in English|"
                    r"English[- ]taught (?:degree|programme|program)|language of instruction", re.I)


def extract_language(text: str) -> tuple[list[LanguageRequirement], str, list[str]]:
    reqs, snips = [], []
    for test, rx in LANG_RX:
        for m in rx.finditer(text):
            g = m.group(1).upper()
            v = float(CEFR[g]) if g in CEFR else float(g)
            if test == "IELTS" and not 3 <= v <= 9:
                continue
            if test == "TOEFL_IBT" and not 40 <= v <= 120:
                continue
            sent = next((s for s in _sentences(text) if m.group(0) in s), m.group(0))
            optional = bool(re.search(r"recommended|preferred|advantage|desirable", sent, re.I))
            lang = {"TESTDAF": "German", "DSH": "German", "DELF_DALF": "French", "TOPIK": "Korean", "HSK": "Chinese",
                    "JLPT": "Japanese"}.get(test, "English")
            note = f"CEFR {g} (stored as {int(v)} on a 1-6 scale)" if g in CEFR else ""
            reqs.append(LanguageRequirement(test=test, minimum=v, mandatory=not optional, language=lang, note=note))
            snips.append(clean_snippet(sent))
            break
    moi = ""
    for s in _sentences(text):
        if MOI_RX.search(s):
            moi = clean_snippet(s)
            break
    return reqs, moi, snips


# Words match in any case; acronyms (BA, MA, S2) only as written. Not a level (tests/levels_eval.py): "master" as a verb,
# a master class or "Boston, MA"; English "promotion" (German "Promotion" counts after an article); "non-degree" (a
# student status); "exchange" other than exchange students ("exchange rate", "Academic Exchange Service").
LEVEL_RX = {
    "bachelor": r"(?i:\bbachelor'?s?\b|\bundergraduate\b|\blicenciatura\b|\bgradua[cç][aã]o\b|\bsarjana\b)|\bBSc\b|\bBA\b|\bS1\b",
    "master": r"(?i:\bm[aá]ster'?s?\b(?!\s*(?:class|promissory|the|a|an|skills?)\b)|\bmaestr[ií]a\b|\bmestrado\b|"
              r"\bmagister\b|\bpostgraduate taught\b|\bgraduate (?:degree|study))|\bMSc\b|\bM\.Sc\b|(?<!, )\bMA\b|\bMBA\b|"
              r"\bLLM\b|\bS2\b",
    "phd": r"(?i:\bdoctoral\b|\bdoctorate\b|\bdoctorat\b|\bdoctorado\b|\bdoutorado\b|\bdoktorand|\bprogram doktor\b)|"
           r"\bPh\.?D\b|\bDPhil\b|\bS3\b|\b(?:[Dd]er|[Dd]ie|[Zz]ur|[Ee]ine[rn]?|[Ii]hre[rn]?) Promotion\b",
    "postdoc": r"(?i:\bpost-?doc(?:toral)?\b|\bpostdoctorado\b|\bpós-doutorado\b)",
    "short_course": r"(?i:\bshort course\b|\bsummer school\b)",
    "exchange": r"(?i:\bexchange students?\b|\bintercambio\b|\bé?change universitaire\b)",
}


# a degree the applicant already has, or is finishing, is not a level the award is for
PREREQ_RX = re.compile(r"\b(hold|holds|holding|holders?|completed|graduated|obtained|possess|have earned|must have|"
                       r"(?:will|should|shall) have|equivalent|graduates? (?:of|from)|"
                       r"(?:applicants?|candidates?|students?|those|persons?|individuals?|researchers?|scholars?) with (?:a|an)|"
                       r"(?<!to )(?:earn\w*|achieved|awarded|receiv\w*|receipt of|obtain\w*)\s+"
                       r"(?:a|an|the|their|your|his|her)?\s*(?:[\w'’/-]+\s+){0,4}?(?:degrees?|diplomas?|qualifications?)|"
                       r"complete (?:their|your|his|her|a|an) (?:\w+ ){0,2}?(?:degree|studies|programme|program)|"
                       r"(?<!upon )(?<!successful )(?<!until )(?<!or )completion of|"
                       r"(?<!non-)final[- ]year|final (?:semester|term)|last year of|senior year|"
                       r"post-?PhD|after (?:their|the|your|his|her|completing|completion of|obtaining|receiving) "
                       r"(?:\w+ ){0,2}?(?:PhD|doctora\w*|Ph\.D)|years? (?:after|since|from) (?:the )?(?:completion|award)|"
                       r"GPA|grade point average|graduation grade|academic (?:record|performance)|undergraduate record|"
                       r"cop(?:y|ies) of|copie|photocop\w+|proof of|"
                       # French, Spanish, Norwegian, Indonesian
                       r"titulaire|d[ée]tention|t[ií]tulo|contar con|hayan? (?:estudiado|obtenido|cursado|concluido)|"
                       r"avlagt|lulusan)\b", re.I)
# a level named without being offered: an exclusion, teaching duties, a first-person story
NOT_OFFERED_RX = re.compile(r"\bnot (?:\w+ ){0,2}?(?:eligible|funded|considered|accepted|supported)\b|\bineligible\b|"
                            r"\b(?:do|does|will|can|shall)(?:n't| not) (?:\w+ )?"
                            r"(?:fund|offer|support|accept|cover|apply|award)\b|\bexclud(?:ed|ing)\b|\bnicht gefördert\b|"
                            r"\b(?:teaching|supervis(?:e|ing|ion)|lectures?|lecturing)\b|"
                            r"(?-i:\b(?:my|me)\b|\bI (?:am|was|have|had|could|would|will|can|did|do)\b)", re.I)
# "she pursued a PhD" is someone's story; "his or her degree" and "HE institutions" are not
STORY_RX = re.compile(r"\b(?:[Ss]he|[Hh]e|[Hh]er|[Hh]is|[Hh]ers|[Hh]im)\b")
EITHER_SEX_RX = re.compile(r"\b(?:his|he|him|her|she)\s*(?:or|/)\s*(?:her|she|his|he|him)\b", re.I)
# with four words or fewer, a section of the site ("PhD Programmes", "Undergraduate study"), not who the award is for
HEADING_RX = re.compile(r"\b(?:programs?|programmes?|studies|courses?|students|school|research|admissions?|prospectus|"
                        r"council|office|degrees?|levels?|application form|study)\b", re.I)


def _level_sentences(text: str) -> list[str]:
    return [s for s in _sentences(text) if not (PREREQ_RX.search(s) or NOT_OFFERED_RX.search(s)
                                                or (STORY_RX.search(s) and not EITHER_SEX_RX.search(s))
                                                or (len(s.split()) <= 4 and HEADING_RX.search(s)))]


def extract_levels(text: str) -> list[str]:
    """Levels the award is *for*. Sentences about degrees an applicant must already hold, and other sentences that
    name a level without offering it, are skipped."""
    sents = _level_sentences(text)
    return [lvl for lvl, rx in LEVEL_RX.items() if any(re.search(rx, s) for s in sents)]


NAT_CONTEXT = re.compile(r"citizens? of|nationals? of|nationality|eligible countr|applicants? from|residents? of|"
                         r"resident in|resid(?:e|ing) in|wohnhaft in|résid(?:ant|ent)s? (?:en|au|dans)|residentes? en|"
                         r"berdomisili di|"
                         r"staatsangehörig|staatsbürger|ressortissants?|nationalité|nacionales? de|nacionalidad|"
                         r"nacionalidade|cidadãos|warga negara|\bWNI\b|"
                         r"open to|passport holders?|countries? (?:listed|eligible)|from the following|"
                         r"must be living in|must live in|domiciled in", re.I)
# "Students from China are not eligible": counts only as an exclusion ("PhD students from Africa, Australia, ..."
# and "candidates from Cambodia may be eligible for English training" are not nationality rules)
FROM_EXCLUDED = re.compile(r"\b(?:students|candidates|applicants|nationals|citizens) from\b", re.I)
# Round 27: an invitation ("students from around the world", "du monde entier") is not an eligibility rule and no
# longer counts; only wording that states the rule does ("no restrictions on nationality", "any nationality can apply").
NAT_ANY = re.compile(r"citizens of all countries|(?:students|applicants|candidates|researchers|scientists|scholars)\s+"
                     r"from all countries|no (?:restrictions?|limitations?) (?:on|of|regarding) (?:the )?nationality|"
                     r"(?:of|from) any nationality|any nationality (?:can|may|is eligible|are eligible)|"
                     r"irrespective of (?:their )?nationality|nationality is not (?:a )?(?:restricted|restriction|"
                     r"an eligibility)|"
                     r"(?:open to|available to|for) (?:students |applicants |candidates )?(?:of |from )?"
                     r"(?:all|any) (?:nationalit|countr)(?![^.]{0,30}\b(?:outside|except|other than))|all nationalities|"
                     r"regardless of (?:their )?nationality|"
                     r"\b(?:and|or) foreign (?:citizens|nationals)\b[^.]{0,40}\beligib|"
                     r"alle(?:r)? nationalitäten|unabhängig von der staatsangehörigkeit|toutes (?:les )?nationalités|"
                     r"todas las nacionalidades|todas as nacionalidades|semua negara|"
                     r"international (?:students|applicants) from (?:all|any) countr", re.I)
NAT_EXCLUDE = re.compile(r"not eligible|are excluded|cannot apply|ineligible|\bneither\b[^.]*\bnor\b[^.]*\bmay\b|except(?:ion)? (?:for )?(?:citizens|nationals)|"
                         r"not (?:be )?(?:a )?(?:citizens?|nationals?|permanent residents?)\b[^.]{0,40}? of|must not be|"
                         r"\bdo(?:es)? not (?:have|hold)\b|"
                         r"nicht berechtigt|"
                         r"no (?:son )?elegibles", re.I)
NAT_CITIZEN = re.compile(r"citizen|\bnationals?\b|passport|nationalit|warga negara|ciudadan|nacionalidad|cidadã|ressortissant|"
                         r"staatsangeh|staatsbürger|citoyen", re.I)
PERSON_NOUN = r"(?:citizens?|nationals?|students?|professionals?|researchers?|applicants?|graduates?|ciudadan[oa]s|" \
              r"profesionales|estudiantes|mahasiswa|warga)"
_DEM = "|".join(sorted((re.escape(d) for d in countries.DEMONYMS), key=len, reverse=True))
DEMONYM_CONTEXT = re.compile(rf"\b(?:{_DEM})\s+{PERSON_NOUN}\b|\b{PERSON_NOUN}\s+(?:{_DEM})\b", re.I)
HEAD_INCLUDE = re.compile(r"^(?:eligible (?:groups|applicants|countries)|who can apply|eligibility|wer kann sich bewerben|"
                          r"qui peut (?:candidater|postuler)|quién puede|siapa yang dapat)\b", re.I)
HEAD_EXCLUDE = re.compile(r"^(?:ineligible|not eligible|excluded|who cannot apply|nicht berechtigt|no elegibles)", re.I)


# "citizens of ECOWAS member states other than Ghana": the countries after these words are excluded
NAT_EXCEPT = re.compile(r"\b(?:other than|except(?: for)?|excluding|with the exception of|but not|apart from|"
                        r"a excepción de|con excepción de|excepto|salvo|sauf|à l'exception d[eu']|außer|ausgenommen|"
                        r"mit Ausnahme von|selain|kecuali)\s+", re.I)
# groups whose members a sentence may name without listing them
NAT_GROUP = re.compile(r"\b(?:ECOWAS|SADC|EAC|ASEAN|SAARC|CARICOM|Commonwealth|African Union|Arab League|OIC|"
                       r"EU|EEA|EFTA|European Union|OAS|OEA|Latin America\w*|Africa\w*|Asia\w*|Pacific|Caribbean|"
                       r"developing countries|member (?:states|countries)|Estados Miembros|États membres|partner countries)\b")


# "a citizen of a country outside the EU/EEA (and Switzerland)", "a non-EU/EEA passport", "do not hold the nationality
# of one of the EEA countries", "from any country outside the UK": everyone except the group (and countries) named
OUTSIDE_RX = re.compile(r"\b(?:outside(?: of)?(?: the)?\s+|non[- ](?=EU|EEA|European)|do(?:es)? not (?:hold|have) (?:the |a )?"
                        r"nationality (?:of|from)(?: one of)?(?: the)?\s+)(.{2,80})", re.I)
# a demonym sentence about the process of one track ("the 2026 application window for Japanese nationals closed")
# or a menu item ("Japanese Nationals") says nothing about who may apply to this programme
TRACK_ONLY = re.compile(r"\bwindows?\b|\bdates? of\b|\bdeadlines?\b|\bhave been announced\b|\bclosed on\b", re.I)
# "Related scholarships" near the end of a page: what follows describes other programmes
RELATED_HEAD = re.compile(r"^(?:related|other|similar|more|explore (?:other|more)|you (?:may|might) also (?:like|be "
                          r"interested in)|see also)\b.{0,30}\b(?:scholarships?|awards?|funding|opportunities|programm?es?|"
                          r"fellowships?|grants?)\s*:?$", re.I)


QUOTA_RX = re.compile(r"ring-?fenced|reserved for|set aside for|earmarked|quota|allocated (?:to|for)|priority countr|"
                      r"priorty countr", re.I)


def programme_text(text: str) -> str:
    """The page without a trailing "Related scholarships" section, whose sentences are about sibling programmes
    (Melbourne's "China Scholarship Council - Melbourne PhD Scholarship ... offered to citizens of the PRC").
    Only a heading in the second half counts, so a navigation menu at the top never cuts the page."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > len(lines) * 0.5 and len(line.strip()) <= 60 and RELATED_HEAD.match(line.strip()):
            return "\n".join(lines[:i])
    return text


def _outside(sentence: str) -> list[str]:
    """Countries a sentence excludes by saying who is outside: the EU/EEA expanded, other names as written."""
    if not (NAT_CITIZEN.search(sentence) or re.search(r"\bfrom (?:a |any )?countr|\b(?:students|candidates|applicants|"
                                                      r"those) from outside", sentence, re.I)):
        return []   # "studying outside the EU" is about the destination, not the applicant
    out = []
    if re.search(r"\bmay need\b|\bneed to\b|verification|\bif you are\b|regulations|entry and stay|"
                 r"information for|\b(?:establish|maintain) (?:permanent )?residence\b|\bduring the (?:period|term|tenure)\b",
                 sentence, re.I):
        return []   # "applicants from outside South Africa may need to complete SAQA verification", visa notes
    if not re.search(r"\b(?:eligib\w*|must|only|open to|aimed at|hold|can be|reserved|intended|available to|"
                     r"offered to|for (?:international )?students)\b|"
                     # round 30: a list item under "you must": "are a citizen of a country outside of the EU/EEA"
                     r"\bcitizens? of a (?:country|state) outside\b", sentence, re.I):
        return []   # a heading ("Entry and Stay Information for Non-EU Citizens") states no rule
    for m in OUTSIDE_RX.finditer(sentence):
        if re.search(r"\b(?:African|Asian|European|Latin American|Arab|Pacific|Caribbean|developing|member)\b[^.]{0,25}$",
                     sentence[:m.start()], re.I):
            continue   # "a citizen of an African country outside of South Africa": a region minus one, not a list
        span = re.split(r"[.;]|\b(?:and (?:be|are|have|meet|hold)|who|which|that|where)\b", m.group(1), maxsplit=1)[0]
        out += countries.group_members(span)
    return list(dict.fromkeys(out))


def _excepted(sentence: str) -> list[str]:
    """Countries named right after an exception word, up to the end of that clause."""
    out = []
    for m in NAT_EXCEPT.finditer(sentence):
        span = re.split(r"[.;:()]|\b(?:and|who|which|that|y|et|und|dan)\b(?! (?:the )?[A-ZÀ-Ý])",
                        sentence[m.end():], maxsplit=1)[0]
        out += countries.mentions(span)
    return out


def _country_line(line: str) -> bool:
    """A list line that is just a country ("Belgium (Federation Wallonia - Brussels)", "*The United States")."""
    if len(line) > (200 if "," in line else 60) or not countries.mentions(line):
        return False
    rest = countries._NAME_RX.sub(" ", line)                 # names first: "Côte d'Ivoire" keeps its apostrophe
    rest = re.sub(r"\([^)]*\)|[*•,;.\-–`'’]", " ", rest)
    return len([w for w in rest.split() if w.lower() not in ("the", "and", "of", "republic")]) <= 2


def _nat_units(text: str) -> list[tuple[str, str]]:
    """(sentence, heading context). A sentence ending in "the following countries" absorbs the next line;
    short heading lines ("Ineligible Groups") colour the lines under them."""
    out = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    head = ""
    for i, line in enumerate(lines):
        if len(line) <= 40 and (HEAD_INCLUDE.match(line) or HEAD_EXCLUDE.match(line)):
            head = "exclude" if HEAD_EXCLUDE.match(line) else "include"
            continue
        if len(line) <= 40 and not countries.mentions(line) and line.istitle():
            head = ""  # a new, unrelated heading ends the context
        intro = re.search(r"(?:following|these) (?:countries|nations|territories)[^.]*[:;]?$|"
                          r"(?:countries|nations|territories) (?:listed )?below\b", line, re.I) or (
            # "I. Citizens from countries that have signed an Agreement ..." followed by one country per line
            re.search(r"citizens?|nationals?|nationalit|eligible countr|ciudadan|ressortissant|staatsangeh|warga negara",
                      line, re.I) and not countries.mentions(line)
            and i + 2 < len(lines) and _country_line(lines[i + 1]) and _country_line(lines[i + 2]))
        if intro and i + 1 < len(lines) \
                and re.search(r"citizen|national|eligible|must be|open to|staatsangeh|ressortissant|nacional|warga|"
                              r"living in|resid", line, re.I):
            # the list may be one country per line ("Austria", "Bulgaria", "*The United States"): take every such line
            j = i + 1
            if j + 1 < len(lines) and not _country_line(lines[j]) and _country_line(lines[j + 1]):
                j += 1   # one explanatory line between "the countries listed below" and the list
            items = []
            while j < len(lines) and _country_line(lines[j].lstrip("*• -")):
                items.append(lines[j].lstrip("*• -"))
                j += 1
            # the list is what the intro sentence is about: read it as such ("... science: citizens of A, B, C")
            joined = ", ".join(items) if len(items) > 1 else lines[i + 1]
            line = line.rstrip(" .") + (" — citizens of: " + joined if len(items) > 1 and NAT_CITIZEN.search(line)
                                        else ": " + joined)
        for s in _sentences(line):
            out.append((s, head))
    return out


DOC_FOR_RX = re.compile(r"\b(?:applicants?|students?|candidates?)\s+(?:from|of)\b[^.:;]{0,120}:\s*(?:an?\s+|the\s+)?"
                        r"(?:APS|certificates?|documents?|proof|translations?|visas?|cop(?:y|ies)|original|apostille|"
                        r"legali[sz]ation|diplomas?)\b|\b(?:must|need to|are required to|should)\s+(?:also\s+)?(?:submit|provide|"
                        r"upload|present|attach|obtain)\b[^.;]{0,40}\b(?:APS|certificate|translation|apostille|legali[sz]ation)",
                        re.I)
# Round 28: negation is read explicitly, per clause. A clause names countries as eligible, excluded or neither.
CLAUSE_SPLIT = re.compile(r";\s+|,\s+(?:but|while|whereas)\s+|\s+but\s+(?=(?:citizens?|nationals?|applicants?|students?)\b)", re.I)
FEE_RULE = re.compile(r"\bliable to pay\b|\bfees? (?:will be|are|is) charged\b|\bpay\w*\s+(?:the\s+)?(?:tuition\s+)?fees?\s+if\b|\bfee[- ]paying status\b", re.I)
NON_RX = re.compile(r"\bnon[- ]?((?:U\.\s?S\.(?:\s?A\.)?|[A-Z][a-zé]+(?:[ -][A-Z][a-zé]+)?))(?=[\s,.)])")
NEVER_RX = re.compile(r"\b(?:have|has) never held (?:the )?(?:[A-Z][\w]+ ){1,2}(?:[Nn]ationality|[Cc]itizenship)|"
                      r"\b(?:are|is|be) not (?:a |an )?(?:[A-Z][\w.]+ ){1,2}(?:citizens?|nationals?)\b|"
                      r"\bmust not (?:hold|have)\b[^.]{0,30}?(?:[A-Z][\w.]+ ){1,2}(?:citizenship|nationality|passport)")


CONDITION_RX = re.compile(r"\bhost institutions?\b|\b(?:governments?|organizations?|organisations?|universities)\b[^.]{0,60}"
                          r"\bnot eligible to (?:participate|host)\b|"
                          r"\b(?:who|that|if you|if they|those)\s+(?:are|is|have)\b[^.]{0,220}\b(?:may|can|must)\s+(?:only\s+)?"
                          r"(?:hold|take up|be held|study at)\b|\b(?:who|if you|if they)\s+(?:are|is)\s+not\b[^.]{0,80}"
                          r"\b(?:may|can)\b", re.I)


# Round 29: negation by scope. A negator governs the noun phrase after it, up to the end of its clause; the
# countries named in that phrase are excluded only when the phrase is about citizenship or nationality.
NEGATOR_RX = re.compile(r"\b(?i:not|never|neither|nor|excluding)\b|\b(?i:non)[- ]?(?=[A-Z])")   # "non-U.S.", not "non-binding"
SCOPE_END_RX = re.compile(r"[;:()]|\.(?:\s|$)|\b(?:but|and (?:be|have|must|meet|hold|who|are|is|will)|who|which|"
                          r"may|can|will|should|are eligible|is eligible|are not|is not)\b", re.I)
CITIZEN_NOUN_RX = re.compile(r"\bcitizen(?:s|ship)?\b|\bnationals\b|\b(?:a|an) (?:[A-Z][\w.]+ ){1,2}national\b|\bnationality\b|"
                             r"\bpassports?\b|\bpermanent residen|"
                             r"\b(?:students|applicants|candidates) from\b", re.I)


def _negated_countries(s: str) -> list[str]:
    """Countries a clause excludes by negation: "non-U.S. citizens", "(ie not an Australian citizen, New Zealand citizen
    or permanent resident)", "who are not Canadian citizens", "not a German national", "must not hold Swiss
    citizenship", "have never held Taiwan nationality", "Russian and Belarusian nationals are not eligible".
    Not negation: "not only", "not eligible" as the predicate of an eligible-by-negation clause ("applicants who are not
    Kenyan citizens are not eligible" names who IS eligible), and groups such as "non-EU" (left to _outside)."""
    if _double_negation(s):
        return []
    if re.match(r"\W*(?:if|when|whether|unless)\b", s, re.I):
        return []   # "If you were born abroad as a non-US citizen, then ...": a branch of the rules, not an exclusion
    t = re.sub(r"\bnot only\b", " ", s, flags=re.I)
    out = []
    for m in NEGATOR_RX.finditer(t):
        rest = t[m.end():]
        if m.group(0).lower().startswith("non"):
            w = re.match(r"((?:United States|[A-Z][\w.]+)(?: [A-Z][a-z]+)?)", rest)
            thing = re.match(r"\s+(?:institutions?|universit(?:y|ies)|schools?|colleges?|organi[sz]ations?|compan(?:y|ies)|"
                             r"sources?|fund(?:s|ing)?|banks?|degrees?|programmes?|programs?|governments?|locations?|"
                             r"addresses|currenc(?:y|ies)|soil|territor(?:y|ies))\b", rest[w.end():] if w else "", re.I)
            if thing or (w and re.match(r"\s*(?:\||\d|students? \|)", rest[w.end():])):
                continue   # round 30: "tuition at any non-U.S. institution" is about places, not people;
                # round 31: "Non-Saudi | 7500" is a fee-table column
            if w and countries.mentions(w.group(1)) and not re.match(r"(?:EU|EEA|EFTA|European)\b", w.group(1)):
                out += countries.mentions(w.group(1))   # "a non-Canadian", "non-U.S."
                continue
        if re.match(r"\s*(?:EU|EEA|EFTA|European)\b", rest) or re.match(r"\s*(?:be\s+)?eligible\b", rest, re.I):
            continue
        end = SCOPE_END_RX.search(rest, 1)
        phrase = rest[:end.start() if end else 120][:160]
        if re.search(r"\b(?:establish|maintain|take up|have) (?:their |a |your )?(?:permanent )?residen|\bresid(?:e|ing|ence) "
                     r"(?:outside|abroad|in)\b", phrase, re.I):
            continue   # round 31: "do not establish permanent residence outside the United States": where to live, not who
        if re.match(r"\s*open (?:for|to) (?:[\w-]+ ){0,3}from\b", phrase, re.I):
            # round 31: "NOT open for students from the twelve countries ... (Bangladesh, Bolivia, ...)": the list in
            # brackets, else the rest of the sentence
            br = re.search(r"\(([^)]{3,400})\)", rest)
            out += countries.mentions(br.group(1) if br else rest)
            continue
        if CITIZEN_NOUN_RX.search(phrase):
            out += countries.mentions(phrase)
    m = re.search(r"\b(?:citizens?|nationals?|students?|applicants?|passport holders?)\b[^.;]{0,30}?\s(?:are|is)\s+not\s+"
                  r"eligible\b", t, re.I)
    if m and not re.search(r"\b(?:only|except|other than|not)\b", t[:m.start()], re.I):
        out += countries.mentions(t[:m.end()])   # "Russian and Belarusian nationals are not eligible"
    return list(dict.fromkeys(out))


RELATIVES_RX = re.compile(r"\b(?:parents?|mother|father|grandparents?|spouse|partner's|family members?|relatives?)\b", re.I)
COUNTRY_CITIZENS_RX = re.compile(r"\b((?:[A-Z][\w.]+ ){1,3})(?:[Cc]itizens?|nationals?|Nationals(?! [A-Z]))\b")   # not "National University"


def _double_negation(s: str) -> list[str]:
    """"Applicants who are not Kenyan citizens are not eligible": the countries named are the eligible ones."""
    m = re.search(r"\bwho (?:are|is) not ([^.;]{0,80}?)(?:citizens?|nationals?)\b[^.;]{0,40}?\b(?:are|is) not eligible\b", s, re.I)
    return countries.mentions(m.group(1)) if m else []


def _clauses(s: str) -> list[str]:
    """A sentence split where each side states its own rule ("Citizens of A are eligible; citizens of B are not
    eligible"); a list separated by semicolons ("nationals of: Armenia; Belarus, Georgia") stays whole."""
    parts = CLAUSE_SPLIT.split(s)
    if len(parts) > 1 and all(re.search(r"\beligib|\bcitizens?\b|\bnationals?\b|\bpassport|\bmay\b|\bcannot\b|"
                                        r"\bmust\b", p, re.I) for p in parts):
        return parts
    return [s]


def _scope(s: str) -> str:
    """Who the page says may apply by fee status, which is not a nationality rule: "international students" are
    usually everyone without domestic status, and the page rarely lists who counts as domestic."""
    dom = re.search(r"\bdomestic\b|\bhome (?:students|fee)", s, re.I)
    intl = re.search(r"\binternational (?:students?|applicants?|candidates?)\b", s, re.I)
    if not (dom or intl) or not re.search(r"eligib|open to|available to|offered to|for|must be|apply", s, re.I):
        return ""
    return "domestic_and_international" if dom and intl and re.search(r"\b(?:and|or|both)\b", s) else \
        "international" if intl else ""


FOREIGN_ALSO_RX = re.compile(r"\bforeign nationals?\b[^.;]{0,200}\b(?:is|are) (?:also )?eligible\b|"
                             r"\bnon-[A-Z][\w ]{1,30}?\b(?:applicants?|candidates?|students?|nationals?)\b[^.;]{0,60}\bmay also (?:be considered|apply|be eligible)", re.I)
INTL_GROUP_RX = re.compile(r"\b(?:and|or) (?:an? )?international (?:\w+ )?(?:students?|applicants?)\b", re.I)
US_TERRITORIES = {"AS", "GU", "PR", "VI", "MP", "UM"}


def extract_nationality(text: str) -> tuple[NationalityRule, list[str]]:
    rule = NationalityRule()
    snips = []
    inc, exc, res = [], [], []
    if re.search(r"warga negara indonesia|\bWNI\b", text, re.I):
        text = re.sub(r"warga negara indonesia|\bWNI\b", "citizens of Indonesia", text, flags=re.I)
    text = text.replace("@", "o")  # "profesionales colombian@" -> colombiano
    text = re.sub(r"\bU\.?S\.?\s+(?=(?:law|laws|government|embassy|consulate|visa|Department|institutions?|universit\w+|dollars?|J-1|immigration)\b)", "", text)   # round 34
    text = re.sub(r"(?<!ciudadan[oa]s )(?<!residentes )(?<!nacionales )\b(?:en|a) los Estados Unidos\b(?! de Am)", "en el pa\u00eds anfitri\u00f3n", text)
    text = re.sub(r"\b(universidades|instituciones|programas|empresas|colegios) estadounidenses\b", r"\1", text)   # round 34
    # round 34: "to study ... in the United States", "Awards to the U.S.", "Japan-United States Educational Commission"
    text = re.sub(r"\b(?:in|to|at|within|towards?)\s+the\s+(?:U\.S\.?|United States)(?!\s*(?:citizen|national|permanent|resident|passport))", "in the host country", text)
    text = re.sub(r"\b[\w-]*(?:United States|American)\s+(?:Educational\s+)?(?:Commission|Foundation|Council|Institute)\b", "the Commission", text)
    # "US Citizens", "non-US citizens": the letters US only before a citizenship word (never the pronoun "us")
    text = re.sub(r"\bU\.?S\.?(?=[\s-]+(?:[Cc]itizens?|[Nn]ationals?|[Pp]assport|[Pp]ermanent))", "United States", text)
    text = re.sub(r"\bAmerican Indians?\b", "Native American", text)   # round 30: not India
    text = re.sub(r"\b(?:same|equal|equivalent)\b[^.;]{0,30}?\bas\s+(?:[A-Z][\w-]+\s+){0,2}(?:citizens|nationals)\b", "the same conditions", text)   # round 41
    text = re.sub(r"\b(agreements?|treat(?:y|ies)|arrangements?)\s+(?:with|between)\s+(?:the\s+)?[A-Z][\w'-]+(?: [A-Z][\w'-]+)?", r"\1", text)   # round 41: not an applicant nationality
    text = re.sub(r"(?i:\b(citizens?|nationals?)\s+of\s+any\s+(?:other\s+)?countr(?:y|ies)\s+(?:outside|other than|excluding|except|apart from)\s+(?:of\s+)?(?:the\s+)?)(United Kingdom|UK|U\.K\.|[A-Z][\w'-]+(?: [A-Z][\w'-]+)?)", r"non-\2 citizens", text)   # round 41
    text = re.sub(r"\b(?:UK|U\.K\.|British|American|Australian|Canadian|German|French)\s+(?=(?:first|second|upper|lower|2:[12]|honou?rs?|bachelor|master|undergraduate|degree|diploma|qualifications?)\b)", "", text)   # round 41: "equivalent of a UK first class honours degree"
    text = re.sub(r"\(\s*outside (?:of )?(?:the )?[A-Z][\w'-]+(?: [A-Z][\w'-]+)?\s*\)", "", text)   # round 41: "overseas (outside of New Zealand)"
    text = re.sub(r"(?i:\bdual (?:nationals?|citizens?|nationality holders?)\s+(?:are|is)\s+not\s+eligible[^.;]*[.;]?)", " ", text)   # round 45: a rule about dual citizens, not a list
    text = re.sub(r"(?i:\b(?:UK|U\.K\.|home|EU|domestic)\s+(?:and|&|or)\s+(?:overseas|international|non-UK|non-EU|EU)\s+(?:students|applicants|candidates)\b)", "all students", text)   # round 45
    text = re.sub(r"(?i:\b(education|studies|schooling|school|degree|qualifications?|diploma|completed|obtained|earned|graduated)\b([^.;]{0,30}?)\boutside\s+(?:of\s+)?(?:the\s+)?)(?:UAE|UK|USA|US|U\.S\.|EU|[A-Z][a-z][\w'-]+(?: [A-Z][\w'-]+)?)\b", r"\1\2 abroad", text)   # round 44: "completed their secondary education outside the UAE"
    text = re.sub(r"(?i:\bfrom\s+(?:any\s+|all\s+)?(?:other\s+)?countr(?:y|ies)\s+(?:outside|other than|except)\s+(?:of\s+)?(?:the\s+)?)(United Kingdom|UK|U\.K\.|[A-Z][\w'-]+(?: [A-Z][\w'-]+)?)", r"from non-\1 citizens", text)   # round 44
    text = re.sub(r"\b[Cc]urrent\s+(?:[A-Z][\w&-]*\s+){1,4}students?\b", "current students", text)   # round 43: "Current VCUarts Qatar students are not eligible"
    text = re.sub(r"\bBritish (?:Protected Persons?|Overseas (?:citizens?|territor\w+)|Nationals? \(Overseas\))", "protected person", text)   # round 43
    text = re.sub(r"\b(?:Latin|South|North|Central|Ibero)[- ]America\b|\bthe Americas\b", "the region", text)   # round 43: not the United States
    text = re.sub(r"(?i:\b(?:applicants?|students?|candidates?|people|individuals)\s+from\s+(?:any\s+|all\s+)?(?:other\s+)?countr(?:y|ies)\s+(?:outside|other than|except)\s+(?:of\s+)?(?:the\s+)?)(United Kingdom|UK|U\.K\.|[A-Z][\w'-]+(?: [A-Z][\w'-]+)?)", r"non-\1 citizens", text)   # round 43
    review = []
    foreign_also = False
    banned: list[str] = []   # countries a clause excludes by negation; another sentence never turns them eligible
    units = [(c, head) for s0, head in _nat_units(text) for c in _clauses(s0) if c.strip()]
    for s, head in units:
        if FEE_RULE.search(s):
            continue  # "you must pay tuition fees if you are a citizen of ...": who pays fees, not who may apply
        if DOC_FOR_RX.search(s):
            continue  # round 49: "Applicants from China, India and Vietnam: APS certificate ...": a document, not who may apply
        if re.match(r"\W*(?:if|when|unless)\b[^.]*\bthen\b", s, re.I):
            continue  # "If you were born abroad as a non-US citizen then one of the following must be true": a branch
        if CONDITION_RX.search(s) or (RELATIVES_RX.search(s) and not re.search(
                r"\b(?:applicants?|you|students?|candidates?) and (?:their|your) parents\b", s, re.I)):
            continue  # "applicants who are not Canadian citizens may only hold it in Canada": where, not who;
            # "your birth parents must have been born ... as non-US citizens": the parents' status, not the applicant's
        if re.search(r"\b(?:dual|double|doble)\b[^.;]{0,40}(?:citizen|nationalit|nacionalidad|ciudadan)|"
                     r"\bdual[- ][\w.]+[-–/][\w.]+ (?:citizen|national)", s, re.I) \
                and re.search(r"not eligible|ineligible|no son elegibles|no se acepta|not accepted|not (?:be )?considered|no pueden|cannot", s, re.I):
            continue  # round 34: "persons holding dual Japan-U.S. citizenship are NOT eligible": the rule names who is excluded, not a second country
        if re.fullmatch(r"\W*(?:individuals|persons|people|applicants|students|candidates|those) who (?:are|is) not (?!.*\b(?:are|is|may|must|can|cannot|will|should|do|does)\b)[^,;]*(?:citizens?|nationals?|residents?)[^.;]*\.?\W*", s, re.I):
            continue  # round 36: "Individuals who are not United States citizens, ..." under "who is not eligible": a list item, not the rule
        if re.search(r"\bdoes not (?:refer to|include|mean|apply to)\b", s, re.I):
            continue  # round 30: "It does not refer to a citizen of another country ...": a definition, not a ban
        if re.search(r"\b(?:is|are|be) (?:considered|classified|defined|recognized|recognised|treated) (?:as |to be )?(?:an? )?international|"
                     r"\binternational (?:student|applicant)s? (?:is|are|means|refers to|includes?) (?:anyone|any|a person|students?|those|applicants?|"
                     r"someone|an? \w+)\b|\bwho is an international (?:student|applicant)|\bdefinition of (?:an? )?international|"
                     r"\bshould follow the\b|\bfollow the [\w ]{0,30}(?:requirements|instructions|process)\b", s, re.I):
            continue  # round 33: "you are considered an international applicant if you are not a U.S. citizen", "U.S. citizens
            # who completed coursework abroad should follow the international admissions requirements": who the office
            # calls international and which form to use, not who may apply
        if re.search(r"\bother (?:scholarships?|awards?|funding|programmes?|programs?|opportunities)\b", s, re.I):
            continue  # round 33: "other scholarship opportunities ... some are for U.S. citizens only"
        if INTL_GROUP_RX.search(s) and not NEGATOR_RX.search(s):
            continue  # round 30: "US citizens, permanent residents ... and international students": open to almost all
        if FOREIGN_ALSO_RX.search(s):
            foreign_also = True   # round 31: "a foreign national who has been living in the US ... is also eligible"
            continue
        dn = _double_negation(s)
        if dn:
            inc += dn
            snips.append(clean_snippet(s))
            continue
        negated = _negated_countries(s)
        banned += negated
        if negated:
            # "must be non-U.S. citizens", "a non-Canadian", "not a German national", "never held Taiwan nationality"
            exc += negated
            snips.append(clean_snippet(s))
            continue
        if not rule.applicant_scope:
            rule.applicant_scope = _scope(s)
        outside = _outside(s)
        # "citizens of Armenia, ..., and citizens of Lithuanian origin of non-EU countries": the sentence lists who is
        # eligible; the non-EU part adds a group, it does not exclude everyone else
        if outside and set(countries.mentions(s)) <= set(outside):
            exc += outside
            snips.append(clean_snippet(s))
            continue
        if QUOTA_RX.search(s) and not re.search(r"provided to|open to|eligib|\bmust\b|\bonly\b", s, re.I):
            continue  # "five ring-fenced for students from India": a quota inside an open call, not a restriction
        anym = NAT_ANY.search(s)
        excepted = _excepted(s)
        if anym and not NAT_EXCLUDE.search(s) and not re.search(r"\bnot\b[^.]{0,25}$", s[:anym.start()], re.I):
            rule.mode = "any"
            snips.append(clean_snippet(s))
            exc += excepted          # "all nationalities except X" = everyone but X
            continue
        dem = DEMONYM_CONTEXT.search(re.sub(r"\bNational (?:University|Agency|Institute|Council|Academy|Laborator\w*|"
                                            r"Library|Museum|Bank|Science)", "", s)) \
            and len(s.split()) > 3 and not TRACK_ONLY.search(s)
        cc = any(countries.mentions(m.group(1)) for m in COUNTRY_CITIZENS_RX.finditer(s)) \
            and len(s.split()) > 3 and not TRACK_ONLY.search(s)   # "United States Citizens", not a menu item
        if not NAT_CONTEXT.search(s) and not dem and not cc and not (FROM_EXCLUDED.search(s) and NAT_EXCLUDE.search(s)):
            continue  # a bare country name (a selector, a list of offices, a menu item) says nothing about eligibility
        # "...to study in Spain": a destination named in an eligibility sentence is not a nationality
        dest_free = re.sub(r"\b(?:in|en|à|au|aux|nach|in der|di|em|ke|at|to study in|cursar[^,.]*? en)\s+"
                           r"(?:la |el |le |der |the )?[A-ZÀ-Ý][\w'-]+(?: [A-ZÀ-Ý][\w'-]+)?", " ", s)
        # "the Government of the Czech Republic offers": the funder's country is not the applicant's
        dest_free = re.sub(r"\b(?:government|ministry|embassy|cooperation|universit(?:y|ies)|council|agency|president|"
                           r"king|queen)\b[^,.;]{0,20}?\bof (?:the )?[A-ZÀ-Ý][\w'-]+(?: [A-ZÀ-Ý][\w'-]+)?",
                           " ", dest_free, flags=re.I)
        residence = re.search(r"residents? (?:of|in)|resid(?:e|ing) in|living in|domiciled in|wohnhaft|résid|residentes?|"
                              r"berdomisili", s, re.I)
        # "resident in Peru" names where the applicant lives, not a study destination: keep it
        found = countries.mentions(s if residence and not NAT_CITIZEN.search(s) else dest_free)
        if excepted:
            found = [c for c in found if c not in excepted]
            if not found:
                # "citizens of ECOWAS member states other than Ghana": the members are not listed here, so the rule
                # cannot be written down; never read the excepted country as eligible
                if NAT_GROUP.search(s):
                    review.append(clean_snippet(s))
                else:
                    exc += excepted
                    snips.append(clean_snippet(s))
                continue
        if not found:
            continue
        snips.append(clean_snippet(s))
        if NAT_EXCLUDE.search(s) or head == "exclude":
            exc += found
        elif re.search(r"residents? of|residents? in|resid(?:e|ing) in|living in|domiciled in|wohnhaft|résid|residentes?|"
                       r"berdomisili", s, re.I) \
                and not NAT_CITIZEN.search(s):
            res += found
        else:
            inc += found
            if residence:   # "an Indian passport holder who is resident in India": both a nationality and a residence
                res += countries.mentions(s[residence.end():])
    inc = [c for c in inc if c not in banned]   # "non-U.S. citizens" vs "graduate studies in the U.S."
    if foreign_also and inc and not exc:
        # the page also admits nationals of other countries under a residence condition: not a nationality rule
        rule.note = "nationals of other countries may also apply under conditions stated on the page"
        inc = []
    if "US" in inc:   # round 30: "nationals of the United States such as American Samoa" are part of the US rule
        inc = [c for c in inc if c not in US_TERRITORIES]
    if inc and rule.mode != "any":
        rule.mode, rule.countries = "include", sorted(set(inc))
        rule.basis = ("citizenship" if any(NAT_CITIZEN.search(x) for x in snips) else
                      "origin" if any(re.search(r"\bfrom\b|coming from|originat|\basal\b|proveniente|originaire", x, re.I)
                                      for x in snips) else "unstated")
    elif exc:
        rule.mode = "exclude" if rule.mode != "any" else "any"
        rule.countries = sorted(set(exc))
    rule.residency_required = sorted(set(res))
    if rule.mode == "any" and exc:
        rule.mode, rule.countries = "exclude", sorted(set(exc))
    if review and rule.mode == "unknown":
        rule.note = "needs review: eligibility is a group of countries with an exception, not listed: " + review[0][:200]
    return rule, snips


DOC_KEYS = [
    ("Passport", r"\bpassport\b|reisepass|passeport|pasaporte|passaporte|paspor", "admission"),
    ("Academic transcripts", r"transcripts?|academic records?|mark ?sheets?|notenspiegel|relevé de notes|"
                             r"historial académico|transkrip nilai", "admission"),
    ("Degree certificate", r"degree certificates?|diploma(?! supplement)|graduation certificate|abschlusszeugnis|"
                           r"ijazah|título universitario", "admission"),
    ("CV", r"\bCV\b|curriculum vitae|r[ée]sum[ée]|lebenslauf|daftar riwayat hidup", "scholarship"),
    ("Motivation letter", r"motivation(?:al)? letter|letter of motivation|motivationsschreiben|lettre de motivation|"
                          r"carta de motiva[cç]i[oó]n|carta de motiva[cç][aã]o|lettera motivazionale|"
                          r"surat motivasi", "scholarship"),
    ("Statement of purpose", r"statement of purpose|\bSOP\b", "admission"),
    ("Personal statement", r"personal statement", "scholarship"),
    ("Scholarship essay", r"\bessays?\b|\besai\b|\bensayo\b|\bessai\b|\baufsatz\b|\bredação\b", "scholarship"),
    ("Recommendation letters", r"recommendation letters?|letters? of recommendation|reference letters?|referees?|"
                               r"empfehlungsschreiben|gutachten|lettres? de recommandation|cartas? de recomenda[cç]"
                               r"(?:i[oó]n|[aã]o)|surat rekomendasi", "scholarship"),
    ("Research proposal", r"research proposal|research plan|project proposal", "scholarship"),
    ("Study plan", r"study plan|plan of study", "scholarship"),
    ("Language test certificate", r"IELTS|TOEFL|language (?:test|certificate|proficiency)", "admission"),
    ("MOI letter", r"medium of instruction (?:letter|certificate)|\bMOI letter\b", "admission"),
    ("Admission or acceptance letter", r"(?:letter of )?(?:admission|acceptance|offer) letter|unconditional offer",
     "scholarship"),
    ("Financial statement", r"financial (?:statement|documents?|proof)|bank statement|proof of funds", "visa"),
    ("Medical certificate", r"medical (?:certificate|examination|report)|health certificate", "visa"),
    ("Police clearance", r"police (?:clearance|certificate)|criminal record", "visa"),
    ("Portfolio or writing sample", r"portfolio|writing sample", "admission"),
]
LIMIT_RX = re.compile(r"(?:max(?:imum)?(?: of)?|up to|no more than|not exceed(?:ing)?|limit(?:ed)? to)?\s*"
                      r"(\d{2,5})\s*(words|characters)", re.I)
PROMPT_RX = re.compile(r"\b(describe|explain|discuss|tell us|outline|how will|why do you|what are your|reflect on)\b", re.I)


def _limit_owner(sentence: str, pos: int) -> Optional[str]:
    """A word limit belongs to the document named closest before it in the sentence."""
    best, best_end = None, -1
    for name, rx, _ in DOC_KEYS:
        for m in re.finditer(rx, sentence[:pos], re.I):
            if m.end() > best_end:
                best, best_end = name, m.end()
    return best


def extract_documents(text: str, url: str) -> tuple[list[RequiredDocument], list[str]]:
    docs: dict[str, RequiredDocument] = {}
    snips = []
    for s in _sentences(text):
        for name, rx, cat in DOC_KEYS:
            if not re.search(rx, s, re.I):
                continue
            d = docs.get(name) or RequiredDocument(name=name, category=cat, source_url=url)
            if re.search(r"optional|if available|if applicable|recommended|\bmay\b", s, re.I):
                d.mandatory = False
            lim = next((x for x in LIMIT_RX.finditer(s) if _limit_owner(s, x.start()) == name), None)
            if lim:
                n = int(lim.group(1))
                if lim.group(2).lower().startswith("word"):
                    d.word_limit = d.word_limit or n
                else:
                    d.char_limit = d.char_limit or n
            if re.search(r"translat", s, re.I):
                d.translation = clean_snippet(s, 200)
            if re.search(r"certif(?:ied|ication)|notari[sz]ed|apostille|legali[sz]", s, re.I):
                d.certification = clean_snippet(s, 200)
            if name in ("Scholarship essay", "Personal statement", "Motivation letter", "Statement of purpose",
                        "Research proposal", "Study plan") and (PROMPT_RX.search(s) or s.endswith("?")):
                d.prompt = d.prompt or clean_snippet(s, 400)
            m = re.search(r"\b(one|two|three|four|\d) (?:recommendation|reference)", s, re.I)
            if m and name == "Recommendation letters":
                d.format = d.format or f"{m.group(1)} letters"
            if name not in docs:
                snips.append(clean_snippet(s))
            docs[name] = d
    return list(docs.values()), snips


GPA_RX = re.compile(r"(?:C?GPA|grade point average)[^.\d]{0,30}?(\d(?:\.\d{1,2})?)\s*(?:/|out of|on a)\s*(\d(?:\.\d)?)?",
                    re.I)
GPA_SIMPLE = re.compile(r"(?:C?GPA|grade point average)[^.\d]{0,30}?(\d\.\d{1,2})", re.I)
AGE_UNIT = r"(?:years?(?: old| of age)?|yrs|jahre?n?(?: alt)?|ans|años(?: de edad)?|anos|tahun)"
AGE_RANGE_RX = re.compile(
    rf"(?:between(?:\s+the\s+ages?\s+of)?|aged|age(?: of)?|zwischen|entre|antara|berusia|usia)\s*(\d{{2}})\s*(?:and|to|-|–|und|et|y|e|hingga|sampai|s\.?d\.?)\s*"
    rf"(\d{{2}})\s*{AGE_UNIT}|\b(\d{{2}})\s*(?:-|–|to)\s*(\d{{2}})\s*{AGE_UNIT}", re.I)
AGE_MAX_RX = re.compile(
    rf"(?:under|below|younger than|not (?:be )?older than|no older than|not over|maximum age(?: of| is)?|max\.? age(?: of)?|"
    rf"age limit(?: of| is)?|upper age limit(?: of| is)?|not exceed(?:ing)?(?: the age of)?|up to the age of|aged? (?:up to|under)|"
    rf"nicht älter als|unter|höchstens|höchstalter(?: von)?|moins de|au plus|âgée?s? de moins de|menores de|no mayor(?:es)? de|"
    rf"edad máxima(?: de)?|usia maksimal|maksimal berusia|berusia paling tinggi|paling tinggi berusia|usia paling tinggi|"
    rf"batas usia(?: maksimal)?)\s*(?:the age of\s*)?(\d{{2}})\s*{AGE_UNIT}?"
    rf"|\b(\d{{2}})\s*{AGE_UNIT}\s*(?:or|and) (?:younger|less|under|below)|up to (\d{{2}}) years? (?:old|of age)", re.I)
AGE_MIN_RX = re.compile(
    rf"(?:at least|minimum age(?: of| is)?|min\.? age(?: of)?|older than|over the age of|aged? (?:at least|over)|"
    rf"mindestens|au moins|mayores de|al menos|minimal berusia|usia minimal|berusia minimal|berusia paling rendah)\s*"
    rf"(?:the age of\s*)?(\d{{2}})\s*{AGE_UNIT}?|\b(\d{{2}})\s*{AGE_UNIT}\s*(?:or|and) (?:older|over|above)|"
    rf"must be (\d{{2}}) years? (?:old|of age)", re.I)
AGE_NOT_APPLICANT = re.compile(r"\b(?:child|children|kids|dependants?|sons?|daughters?|kinder|enfants?|hij[oa]s|anak)\b",
                               re.I)
AGE_PREFERENCE = re.compile(r"\bprefer|preference|priority|bevorzugt|de preferencia|diutamakan", re.I)
NO_UPPER_AGE = re.compile(r"no upper age limit|no (?:maximum )?age limit|no age (?:limit|restrictions?)|keine altersgrenze|"
                          r"sin límite de edad|tidak ada batas usia", re.I)
AGE_CONTEXT = re.compile(r"\bage\b|aged|years? old|years? of age|older than|younger than|alter|jahre|\bans\b|edad|años|usia|umur|tahun|born", re.I)


AGE_LEVELS = [("advanced_master", r"advanced\s+master'?s?"), ("postdoc", r"post-?docs?\b|postdoctoral"),
              ("phd", r"\bph\.?d\b|doctoral|doctorate|postgraduates?"), ("master", r"\bmaster'?s?\b|\bgraduates?\b"),
              ("bachelor", r"\bbachelor'?s?\b|undergraduates?|associate'?s?")]
AGE_NUM = re.compile(r"\b(1[5-9]|[2-6]\d|7[0-5])\b(?!\s*(?:%|ects|credits|months?|semesters?|days?|weeks?|hours?|"
                     r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|euro|eur|usd|tl\b|€))")


def _levels_in(s: str) -> list[tuple[int, str]]:
    """(position, level) mentions; 'advanced master' is not also read as 'master'."""
    found, taken = [], []
    for lvl, rx in AGE_LEVELS:
        for m in re.finditer(rx, s, re.I):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), lvl))
    return sorted(found)


def age_limits_by_level(sentence: str) -> list[dict]:
    """Level-specific limits in one sentence: 'bachelor ... not older than 35, while advanced master ... 45',
    'Undergraduates, Graduates: 35 years; Postdocs: 45 years', '35 years for undergraduates ..., 45 years for postdocs'.
    Empty unless at least two different numbers are tied to levels."""
    nums = [(m.start(), int(m.group(1))) for m in AGE_NUM.finditer(sentence)]
    levels = _levels_in(sentence)
    if len({n for _, n in nums}) < 2 or not levels:
        return []
    levels_first = levels[0][0] < nums[0][0]
    out = []
    for i, (pos, n) in enumerate(nums):
        if levels_first:
            lo = nums[i - 1][0] if i else -1
            group = [lvl for p, lvl in levels if lo < p < pos]
        else:
            hi = nums[i + 1][0] if i + 1 < len(nums) else len(sentence)
            group = [lvl for p, lvl in levels if pos < p < hi]
        around = sentence[max(0, pos - 60):pos]
        is_min = bool(re.search(r"at least|minimum|min\.?\s*age|or older|must be$", around, re.I)) and \
            not re.search(r"not (?:be )?older|older than\s*$|maximum|max\.", around[-30:], re.I)
        for lvl in dict.fromkeys(group):
            out.append({"level": lvl, ("min" if is_min else "max"): n})
    return out if len({(d.get("max"), d.get("min")) for d in out}) > 1 else []


def _merge_age_limits(items: list[dict]) -> list[dict]:
    merged: dict = {}
    for d in items:
        merged.setdefault(d["level"], {"level": d["level"]}).update({k: v for k, v in d.items() if k != "level"})
    order = [lvl for lvl, _ in reversed(AGE_LEVELS)]
    return sorted(merged.values(), key=lambda d: order.index(d["level"]))


def extract_age(text: str) -> dict:
    """{'min_age', 'max_age', 'snip'}: ranges first, then explicit maxima and minima. 'At least 18' is a minimum.
    When limits differ by study level, {'age_limits': [...], 'snip'} instead: no single number is reported."""
    out: dict = {}
    per_level, level_snip = [], ""
    for s in _sentences(text):
        if AGE_CONTEXT.search(s) and not AGE_PREFERENCE.search(s):
            got = age_limits_by_level(s)
            if got:
                per_level += got
                level_snip = level_snip or clean_snippet(s)
    if per_level:
        # single-level statements in the same text ("bachelor ... at least 19") belong to the same table
        for s in _sentences(text):
            lv = _levels_in(s)
            nums = [int(m.group(1)) for m in AGE_NUM.finditer(s)]
            if AGE_CONTEXT.search(s) and len(lv) == 1 and len(nums) == 1 and not age_limits_by_level(s):
                is_min = bool(re.search(r"at least|minimum|or older", s, re.I))
                per_level.append({"level": lv[0][1], ("min" if is_min else "max"): nums[0]})
        return {"age_limits": _merge_age_limits(per_level), "snip": level_snip}
    no_upper = bool(NO_UPPER_AGE.search(text))
    for s in _sentences(text):
        if not AGE_CONTEXT.search(s):
            continue
        if AGE_PREFERENCE.search(s):
            continue  # "we prefer applicants under 40" is a preference, not a limit
        kid = AGE_NOT_APPLICANT.search(s)
        if kid:
            s = s[:kid.start()]  # "...travel with children under the age of 18": the age is the child's
        m = AGE_RANGE_RX.search(s)
        if m:
            a, b = (int(x) for x in (m.group(1), m.group(2)) if x) if m.group(1) else (int(m.group(3)), int(m.group(4)))
            if 12 <= a < b <= 75:
                out.setdefault("min_age", a)
                out.setdefault("max_age", b)
                out.setdefault("snip", clean_snippet(s))
                continue
        mx = None if no_upper else AGE_MAX_RX.search(s)
        if mx and not re.search(r"\b(?:at least|mindestens|au moins|minimal)\s*" + (mx.group(1) or mx.group(2) or mx.group(3) or "x"),
                                s, re.I):
            v = int(mx.group(1) or mx.group(2) or mx.group(3))
            if 15 <= v <= 75 and "max_age" not in out:
                out["max_age"] = v
                out.setdefault("snip", clean_snippet(s))
        mn = AGE_MIN_RX.search(s)
        if mn and re.search(r"(?:not|n't|no)\s+(?:be\s+)?$", s[:mn.start()], re.I):
            mn = None  # "cannot be older than 35" is a maximum, never a minimum
        if mn and not re.search(r"\b(?:under|below|up to|younger than)\s+(?:the age of\s+)?" + (mn.group(1) or mn.group(2) or mn.group(3)),
                                s, re.I):
            v = int(mn.group(1) or mn.group(2) or mn.group(3))
            if 12 <= v <= 70 and "min_age" not in out:
                out["min_age"] = v
                out.setdefault("snip", clean_snippet(s))
    if no_upper:
        out["no_upper_age_limit"] = True
    if "min_age" in out and "max_age" in out and out["min_age"] >= out["max_age"]:
        out.pop("max_age")  # contradictory reading; keep the minimum, leave the maximum unknown
    return out


DURATION_RX = re.compile(
    r"(?:duration(?: of (?:the )?(?:funding|scholarship|award|grant|programme|program|fellowship))?|funded for|"
    r"funding for|awarded for|granted for|for (?:a (?:maximum|period) of|up to)|(?:will )?lasts\b|laufzeit|förderdauer|"
    r"dauer|durée|duración(?: entre)?|con una duración entre|durasi|jangka waktu|terms? range from [^.]{0,30}? to)"
    r"\s*:?\s*(?:of\s*)?(?:up to\s*|a maximum of\s*|max(?:imum)?\.?\s*)?"
    r"(\d{1,2}|one|two|three|four|five|six|nine|twelve)(?:\s*(?:-|–|to|bis|à|a|y|and)\s*(\d{1,2}|two|three|four|five|six|twelve))?"
    r"\s*(months?|years?|monate?n?|jahre?n?|mois|ans|meses|años|bulan|tahun|semesters?)",
    re.I)
NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "nine": 9, "twelve": 12}


def extract_duration(text: str) -> tuple[str, str]:
    m = DURATION_RX.search(text)
    if not m:
        return "", ""
    unit = m.group(3).lower()
    unit = ("months" if re.match(r"month|monat|mois|mes|bulan", unit) else "semesters" if unit.startswith("sem")
            else "years")
    n = lambda x: str(NUMWORD.get(x.lower(), x))  # noqa: E731
    val = n(m.group(1)) + (f"-{n(m.group(2))}" if m.group(2) else "")
    snip = next((s for s in _sentences(text) if m.group(0) in s), m.group(0))
    return f"{val} {unit}", clean_snippet(snip)


WORK_RX = re.compile(r"(?:at least|minimum(?: of)?|min\.?)?\s*(\d+(?:\.\d)?)\s*\+?\s*years?'?\s+(?:of\s+)?"
                     r"(?:relevant\s+|full[- ]time\s+|professional\s+|work\s+)*(?:work|professional|employment|"
                     r"working)?\s*experience", re.I)


def extract_academics(text: str) -> dict:
    out: dict = {}
    m = GPA_RX.search(text)
    if m:
        out["min_gpa"] = float(m.group(1))
        if m.group(2):
            out["gpa_scale"] = float(m.group(2))
    else:
        m = GPA_SIMPLE.search(text)
        if m:
            out["min_gpa"] = float(m.group(1))
    if m:
        out["_gpa_snip"] = clean_snippet(next((s for s in _sentences(text) if m.group(0) in s), m.group(0)))
    ages = extract_age(text)
    for k in ("min_age", "max_age", "age_limits"):
        if k in ages:
            out[k] = ages[k]
            out["_age_snip"] = ages["snip"]
    w = WORK_RX.search(text)
    if w and re.search(r"experience", w.group(0), re.I):
        out["min_work_years"] = float(w.group(1))
        out["_work_snip"] = clean_snippet(next((s for s in _sentences(text) if w.group(0) in s), w.group(0)))
    if re.search(r"(?:contact|identify|find|secure|letter from|acceptance (?:from|by)) (?:a |an |your |the )?"
                 r"(?:potential |prospective |host )?(?:supervisor|professor|advisor)", text, re.I):
        out["requires_supervisor"] = True
    if re.search(r"research proposal", text, re.I):
        out["requires_research_proposal"] = True
    return out


from .languages import page_terms as _page_terms  # noqa: E402  (programme-page words per language, languages.json)

SCHOLARSHIP_TERMS = re.compile(
    r"scholarships?|fellowships?|bursar(?:y|ies)|grants?|stipend|funding|funded|studentships?|assistantships?|"
    r"stipendi(?:um|en)|bourses?|becas?|borse? di studio|beasiswa|奖学金|奨学金|장학금|burs(?:u|lar[ıi])|"
    r"stypendi|stipendier|apurahat|υποτροφ|منح|стипенди|erasmus mundus|joint master|crédito beca|"
    # calls for research and study funding in the languages of official funders
    r"utlysning(?:er)?|tilskudd|forskningsmidler|stipendiat|forskarstipend|legat|förderung|ausschreibung|"
    r"appel à projets|financement doctoral|convocatoria de ayudas|bolsas? de|hibah|pendanaan riset|"
    r"助成金|연구비 지원|资助项目|beurzen?\b" + _page_terms("scholarship"), re.I)


def candidate_links(page: Page, same_site_only: bool = False) -> list[tuple[str, str]]:
    from urllib.parse import urlsplit
    host = urlsplit(page.url).netloc
    out, seen = [], set()
    for href, text in page.links:
        if not href.startswith("http"):
            continue
        if same_site_only and urlsplit(href).netloc != host:
            continue
        if SCHOLARSHIP_TERMS.search(text) or SCHOLARSHIP_TERMS.search(href.split("?")[0]):
            key = href.split("#")[0]
            if key not in seen and key.rstrip("/") != page.url.rstrip("/"):
                seen.add(key)
                out.append((key, text))
    return out


NEWS_TITLE = re.compile(r"\b(announces?|announced|recipients?|winners?|awarded to|congratulat|press release|news|"
                        r"stories|story|blog|webinar|event recap|celebrat|meet (?:the|our))\b", re.I)
NEWS_PATH = re.compile(r"/(?:news|stories|story|blog|blogs|media|press|press-releases?|events?|people|profiles?|"
                       r"staff|team|berita|aktuelles|actualites|noticias)(?:/|$)")
SECTION_TITLE = re.compile(r"^(?:who can apply|how to apply|get ready|prepare|eligibility|benefits|key dates|timeline|"
                           r"application (?:process|timeline)|selection|faq|what (?:does|is)|why )", re.I)
GUIDE_TITLE = re.compile(r"^(?:funding|scholarships?|grants?|fellowships?|bourses?|becas?|bolsas?|beasiswa|học bổng|"
                         r"المنح(?: الدراسية)?|منح دراسية|وظائف|اسکالرشپ)$|\b(guidance|polic(?:y|ies)|grant conditions|"
                         r"kebijakan|richtlinien|politique|"
                         r"portfolio|finding scholarships|stipendien finden|information (?:for|other)|types of|"
                         r"get ready|prepare to apply|how to apply|faqs?|frequently asked|terms and conditions|"
                         r"search|database|overview|notice board|opportunities)\b", re.I)
OPP_SIGNALS = (r"eligib|wer kann sich bewerben|qui peut|requisitos|persyaratan|who can apply|zielgruppe|hvem kan s[øo]ke|"
               r"vem kan s[öo]ka|hvem kan ans[øo]ge|wie kan|kto mo[żz]e|chi pu[òo]|quem pode|応募資格|지원 ?자격|申请条件|"
               r"申請資格|الأهلية|شروط التقديم",
               r"deadline|closing date|apply by|applications? close|bewerbungsschluss|date limite|fecha l[ií]mite|"
               r"pendaftaran ditutup|prazo|plazo|cierre|s[øo]knadsfrist|ans[øo]gningsfrist|sista ans[öo]kningsdag|"
               r"uiterlijk|sluitingsdatum|termin sk[łl]adania|scadenza|締切|마감|截止|آخر موعد|الموعد النهائي",
               r"how to apply|application|call for applications|bewerbung|candidature|solicitud|solicita|pendaftaran|inscri|convocatoria|seleksi|"
               r"s[øo]knad|ans[öo]kan|ans[øo]gning|aanvraag|wniosek|domanda|inscri[çc][ãa]o|応募|신청|申请|申請|التقديم",
               r"benefit|cover|stipend|tuition|allowance|leistungen|allocation|asignaci|tunjangan|monthly|financ|"
               r"number of (?:scholarships|awards|places|grants)|type of scholarship|scholarship (?:amount|value)|"
               r"stipendienleistung|matrícula|biaya|dekker|t[äa]cker|d[æa]kker|vergoeding|copre|cobre|支給|지원금|资助|"
               r"تغطي",
               r"requirement|criteria|unterlagen|dossier|documentos|dokumen|voraussetzung|jadwal|syarat|\bkrav\b|"
               r"vilk[åa]r|\beisen\b|wymagania|requisiti|要件|요건|要求|متطلبات")
LISTING_TITLE = re.compile(r"\b(deadlines?|key dates|calls(?: for)?|open calls|opportunities|concursos|convocatorias|"
                           r"funding category|programmes? list)\b", re.I)
# eligibility, deadline, application, benefit, requirement words of the languages in languages.json "page" blocks
OPP_SIGNALS = tuple(rx + _page_terms(g) for rx, g in
                    zip(OPP_SIGNALS, ("eligibility", "deadline", "application", "benefit", "requirement")))
_VOCAB = {g: re.compile(_page_terms(g)[1:], re.I) if _page_terms(g) else None for g in ("listing", "guidance", "news")}


def _vocab(group: str, text: str) -> bool:
    rx = _VOCAB[group]
    return bool(rx and rx.search(text))


# The five kinds of page discovery meets, and what happens to each:
#   opportunity   a programme page: one programme's terms (it becomes a record)
#   listing       a catalogue portal: a home page, finder, database, archive or list of many programmes (a lead)
#   guidance      advice about funding in general: how to find, prepare, organise a stay (a lead)
#   news          an announcement: news, award results, alumni stories, press releases (a lead)
#   not_relevant  no scholarship content, or a call for organisations rather than individual applicants
PAGE_KIND_NAMES = {"opportunity": "programme page", "listing": "catalogue portal", "guidance": "guidance page",
                   "news": "announcement", "not_relevant": "not relevant", "not_loaded": "not loaded (not assessed)"}
# weaker announcement words: only an announcement on a news path, an article page or under a dateline
ANNOUNCE_TITLE = re.compile(r"\b(?:welcomes?|welcomed|opens? its doors|ministers?|success|appeal|launch(?:es|ed)?|"
                            r"alumn(?:us|a|i|ae)|benefits? from|receives?|received|graduat(?:es|ed|ion)|ceremony|visits?|"
                            r"visited|meets?|signs?|signed|mou|memorandum|partnership|celebrat\w*|interview|testimonial|"
                            r"spotlight|apply now for|now open|results? (?:of|announced)|selected (?:candidates|scholars)|"
                            r"shortlist\w*|appointed|honou?red|marks?|review)\b", re.I)
NEWS_PATH2 = re.compile(r"/(?:news-nouvelles|nouvelles|articles?|actualites|actualit%C3%A9s|nieuws|noticias|berita|"
                        r"pressemitteilungen?|nyheter|aktuelt|uutiset|haberler|novosti)(?:/|$)|"
                        r"^(?!.*/(?:wp-content|uploads|files|media)/).*/20\d\d/(?:\d{2}/|20\d\d-\d\d-\d\d)")
ORG_APPLICANT = re.compile(r"(?:organi[sz]ations?|institutions|universities|consortia|companies|enterprises|tech hubs|"
                           r"municipalities|higher education institutions|NGOs?)\s+(?:can|may|are eligible to|are invited "
                           r"to|must|should|that wish to)\s+(?:apply|submit|send)|\bfor organi[sz]ations\b|expressions? of "
                           r"interest|\bcall for proposals\b|technical assistance (?:grant|operation)|\bgovernance\b|"
                           r"forskningsorganisasjon|hvem kan s[øo]ke.{0,160}?(?:organisasjon|virksomhet|bedrift)|"
                           r"\bTA grant\b|grant to the (?:government|republic|province)|beneficiary countr",
                           re.I | re.S)
INDIVIDUAL = re.compile(r"\b(?:individual (?:applicants?|students?|researchers?)|students? (?:can|may|must|who)|"
                        r"candidates? (?:can|may|must|should|who)|applicants? (?:can|may|must|should|who|from)|"
                        r"you (?:can|may|must|should|will)|eligible (?:students|candidates|applicants)|"
                        r"scholars? (?:will|must|receive)|grant ?holders?|scholarship holders?|graduates (?:from|of|who)|"
                        r"(?:young |early[- ]career )?researchers (?:from|who)|(?:nationals|citizens) of|target group|"
                        r"phd (?:students|candidates)|master'?s students|doctoral (?:students|candidates))\b", re.I)
HOME_PATH = re.compile(r"^/?(?:[a-z]{2}(?:[-_][a-z]{2})?/?)?(?:(?:web/)?(?:index|main|home|default)(?:page)?(?:\.\w+)?)?/?$",
                       re.I)
INDEX_PATH = re.compile(r"/(?:index|main|default|home)\.(?:aspx?|html?|php|do|jsp)$", re.I)
ORG_TITLE = re.compile(r"\((?:organi[sz]ations?|institutions?)\)|expressions? of interest|\bTA grant\b|"
                       r"\bfor organi[sz]ations\b", re.I)
GUIDE_PATH = re.compile(r"/(?:my-country|your-country|country-information|countries)/", re.I)
HUB_SEGMENT = re.compile(r"\boverview\b|for (?:international|foreign) students|\bstudy in\b|\bstudying in\b|"
                         r"plan your studies", re.I)
GUIDE_PHRASE = re.compile(r"information for (?:scholarship )?(?:applicants|candidates|students)|finding a scholarship|"
                          r"step[- ]by[- ]step|funding your studies|how to (?:apply for|find) (?:a )?(?:scholarship|funding)|"
                          r"get ready|prepare to apply|organi[sz]ing your stay|pre-departure|after (?:your )?arrival|"
                          r"country list|frequently asked|\bfaqs?\b|funding (?:options|sources|types)|types of funding|"
                          r"student funding|sponsorship|studying and scholarships in|study and work in|estudie y trabaje|"
                          r"my country|country information|loans and grants|loans? (?:&|and) grants|para estudiar|"
                          r"estudiar en|^students from|country/region information|your country", re.I)
GUIDE_TEXT = re.compile(r"there are no (?:governmental |government |national )?scholarship programmes|(?:funding|scholarship)"
                        r" (?:options|sources|types)\b|combine (?:funding|several sources|different sources)|explore "
                        r"(?:various|different|the many) (?:funding|scholarship)|navigating|offered by (?:individual|each) "
                        r"universit|start at (?:the )?university|check with your (?:university|institution)", re.I)


DATELINE_LABEL = re.compile(r"^(?:published|posted|updated|date|diterbitkan|publi[ée]|ver[öo]ffentlicht|publicado|"
                            r"pubblicato)\b", re.I)


def _dateline(text: str) -> bool:
    """A news-style dateline in the first lines: a short line that is a date, or "Published 3 March 2026"."""
    for line in text.splitlines()[:6]:
        dated = any(d for d, _ in parse_dates(line))
        if dated and (len(line.split()) <= 6 or DATELINE_LABEL.search(line)):
            return True
    return False


def page_kind(page: Page) -> tuple[str, str]:
    """('opportunity'|'listing'|'guidance'|'news'|'not_relevant', reason); see PAGE_KIND_NAMES. Only programme
    pages become records; portals, guidance and announcements are discovery leads."""
    from .identity import PORTAL_PHRASE, programme_lines, title_specificity
    t, title = page.text, page.title or ""
    if not SCHOLARSHIP_TERMS.search(title + " " + t[:3000]):
        return "not_relevant", "no scholarship/funding terms"
    from urllib.parse import urlsplit
    path = urlsplit(page.url).path.lower()
    ld_types = {str(t).lower() for blob in page.jsonld for n in _ld_nodes(blob)
                for t in (n.get("@type") if isinstance(n.get("@type"), list) else [n.get("@type")]) if t}
    if ORG_TITLE.search(title):
        return "not_relevant", f"a call for organisations or institutions, not individual applicants: {title[:60]}"
    if NEWS_TITLE.search(title) or _vocab("news", title) or NEWS_PATH.search(path) or NEWS_PATH2.search(path) \
            or ld_types & {"newsarticle", "blogposting", "profilepage"}:
        return "news", f"news/article/profile page: {title[:60]}"
    dateline = _dateline(t)
    if ANNOUNCE_TITLE.search(title) and (dateline or page.og_type == "article" or "article" in ld_types):
        return "news", f"announcement under a dateline: {title[:60]}"
    opening = title + " " + t[:1500]
    if ORG_APPLICANT.search(opening) and not INDIVIDUAL.search(t):
        return "not_relevant", "a call for organisations or institutions, not individual applicants"
    n_dates = len({d for line in t.splitlines() if len(line) <= 60 for d, _ in parse_dates(line) if d})
    if LISTING_TITLE.search(title) and (n_dates >= 4 or sum(bool(re.search(rx, t, re.I)) for rx in OPP_SIGNALS) <= 2
                                        or t.count(" | ") >= 6):
        return "listing", f"listing title with {n_dates} dated entries"
    hits = sum(bool(re.search(rx, t, re.I)) for rx in OPP_SIGNALS)
    funding_terms = sum(bool(re.search(rx, t, re.I)) for _, rx in FUNDING_KEYS)
    specific, name = title_specificity(title)
    heading = title + " " + (getattr(page, "h1", "") or "")
    if HOME_PATH.match(path) and not SCHOLARSHIP_TERMS.search(heading):
        if programme_lines(t) >= 3:
            # a programme's own site ("Home | MultiDiverse") names one programme; an organisation's names several
            return "listing", f"an organisation's home page listing programmes: {title[:60]}"
        if len(SCHOLARSHIP_TERMS.findall(t)) <= 3 and funding_terms < 3 and hits < 4:
            return "not_relevant", f"an organisation's home page, scholarships at most mentioned: {title[:60]}"
    if not SCHOLARSHIP_TERMS.search(heading + " " + path.replace("-", " ")) \
            and len(SCHOLARSHIP_TERMS.findall(t)) <= 2 and funding_terms < 3 and hits < 4:
        return "not_relevant", "scholarships only mentioned in passing (not in the title, heading or address)"
    if _vocab("guidance", title):
        return "guidance", f"guidance title: {title[:60]}"
    if not specific and (HOME_PATH.match(path) or INDEX_PATH.search(path)):
        return "listing", f"home or index page without a programme name: {title[:60]}"
    if PORTAL_PHRASE.search(title) or _vocab("listing", title):
        return "listing", f"catalogue/finder/archive title: {title[:60]}"
    if (GUIDE_PHRASE.search(title) or _vocab("guidance", title)) and (not specific or hits < 4):
        return "guidance", f"guidance title: {title[:60]}"
    if not specific and (GUIDE_TEXT.search(t[:5000]) or GUIDE_PATH.search(path)):
        return "guidance", f"general funding information, no programme named: {title[:60]}"
    from .identity import catalogue_evidence
    is_cat, cat_why = catalogue_evidence(t, title)
    if is_cat:
        return "listing", f"a catalogue: {cat_why}"
    if not specific and HUB_SEGMENT.search(name):
        return "listing", f"a country or audience hub, no programme named: {title[:60]}"
    if GUIDE_TITLE.search(title.split("|")[0].split(" - ")[0].strip()) and hits < 4 and funding_terms < 3:
        return "guidance", f"guidance/listing title: {title[:60]}"
    if hits < 2 and funding_terms < 3:
        return "not_relevant", f"only {hits} opportunity signals"
    return "opportunity", f"{hits} opportunity signals"


# Rules decided by the title, path or layout alone; when the page body says otherwise the call is not certain.
_SHAPE_RULES = ("an organisation's home page", "home or index page", "catalogue/finder/archive title", "guidance title",
                "a country or audience hub", "guidance/listing title", "listing title")


def classify_page(page: Page) -> dict:
    """{"kind", "confidence": high | low, "reason"}: the page type (page_kind) and how sure the rules are. Low means
    a person should look: the page's language has no page vocabulary, or the body and the title/path disagree, or
    the evidence is thin either way. Programme identity (identity.py) is a separate, later check."""
    from .retrieval import load_status
    loaded, load_why = load_status(page)
    if not loaded:
        # nothing to judge: neither a programme nor not one (a browser, a retry or a person decides)
        return {"kind": "not_loaded", "confidence": "high", "reason": load_why}
    kind, why = page_kind(page)
    t, title = page.text, page.title or ""
    hits = sum(bool(re.search(rx, t, re.I)) for rx in OPP_SIGNALS)
    funding_terms = sum(bool(re.search(rx, t, re.I)) for _, rx in FUNDING_KEYS)
    from .languages import has_page_vocabulary
    lang = page.language
    low = ""
    if kind == "not_relevant" and not has_page_vocabulary(lang):
        low = f"no page vocabulary for language '{lang}'"
    elif kind == "not_relevant" and why.startswith("only") and (hits >= 1 or funding_terms >= 2) \
            and SCHOLARSHIP_TERMS.search(title):
        low = f"a scholarship title with few signals ({hits} signals, {funding_terms} funding terms)"
    elif kind in ("listing", "guidance") and why.startswith(_SHAPE_RULES) and hits >= 4 and funding_terms >= 3:
        low = f"title/path say {kind}, the body reads like a programme ({hits} signals, {funding_terms} funding terms)"
    elif kind == "listing" and ("but the title names a programme" in why or "but only a few names" in why):
        low = "a programme title on a page that names many programmes"
    elif kind == "opportunity" and hits <= 2 and funding_terms < 3:
        low = f"thin programme evidence ({hits} signals, {funding_terms} funding terms)"
    return {"kind": kind, "confidence": "low" if low else "high", "reason": why + (f"; uncertain: {low}" if low else "")}


SECTION_LINK = re.compile(r"eligib|who can apply|how to apply|apply now|benefit|what (?:the|does the|is) "
                          r"(?:scholarship|award|fellowship) (?:cover|include|offer)|what you (?:get|receive)|"
                          r"deadline|key dates|timeline|requirement|selection|criteria|value of|funding details|"
                          r"wer kann|bewerbung|leistungen|conditions d'admissibilité|candidature|requisitos|"
                          r"persyaratan|pendaftaran|syarat", re.I)


def section_links(page: Page, limit: int = 4) -> list[str]:
    """Same-site links to a programme's own detail sections (eligibility, benefits, deadlines, how to apply)."""
    from urllib.parse import urlsplit
    host = urlsplit(page.url).netloc
    out = []
    for href, text in page.links:
        if urlsplit(href).netloc == host and href.split("#")[0].rstrip("/") != page.url.rstrip("/") \
                and SECTION_LINK.search(text) and not href.lower().endswith((".jpg", ".png", ".zip")):
            u = href.split("#")[0]
            if u not in out:
                out.append(u)
        if len(out) >= limit:
            break
    return out


def looks_like_opportunity(page: Page) -> bool:
    return page_kind(page)[0] == "opportunity"


LD_TYPES = {"grant", "monetarygrant", "scholarship", "educationaloccupationalprogram", "course", "event",
            "jobposting", "fundingscheme", "webpage", "article"}


def _ld_nodes(blob) -> list[dict]:
    out = []
    if isinstance(blob, list):
        for b in blob:
            out += _ld_nodes(b)
    elif isinstance(blob, dict):
        out.append(blob)
        for k in ("@graph", "mainEntity", "about", "funding", "offers"):
            if k in blob:
                out += _ld_nodes(blob[k])
    return out


def _ld_name(v) -> str:
    if isinstance(v, dict):
        return str(v.get("name") or "")
    if isinstance(v, list):
        return ", ".join(_ld_name(x) for x in v if x)
    return str(v or "")


def jsonld_fields(page: "Page") -> dict:
    """Structured data the publisher declared. Only explicitly stated properties are read."""
    out: dict = {}
    for n in [n for blob in page.jsonld for n in _ld_nodes(blob)]:
        types = n.get("@type") or []
        types = {t.lower() for t in (types if isinstance(types, list) else [types]) if isinstance(t, str)}
        if not types & LD_TYPES:
            continue
        if "webpage" in types or "article" in types:
            out.setdefault("published", n.get("datePublished"))
            out.setdefault("modified", n.get("dateModified"))
            continue
        out.setdefault("name", n.get("name"))
        out.setdefault("description", n.get("description"))
        for k in ("applicationDeadline", "validThrough", "endDate", "deadline"):
            if n.get(k):
                out.setdefault("deadline", str(n[k])[:10])
                out.setdefault("deadline_property", k)
        if n.get("applicationStartDate") or n.get("startDate"):
            out.setdefault("opening", str(n.get("applicationStartDate") or n.get("startDate"))[:10])
        amt = n.get("amount") or n.get("offers")
        if isinstance(amt, dict) and (amt.get("value") or amt.get("price") or amt.get("maxValue")):
            try:
                out.setdefault("amount", float(amt.get("value") or amt.get("price") or amt.get("maxValue")))
                out.setdefault("currency", amt.get("currency") or amt.get("priceCurrency"))
            except (TypeError, ValueError):
                pass
        for k in ("funder", "provider", "sponsor", "organizer"):
            if n.get(k):
                out.setdefault("funder", _ld_name(n[k]))
        for k in ("eligibleRegion", "areaServed", "applicantLocationRequirements"):
            if n.get(k):
                out.setdefault("eligible_region", _ld_name(n[k]))
        if n.get("educationalCredentialAwarded") or n.get("educationalLevel"):
            out.setdefault("level", _ld_name(n.get("educationalCredentialAwarded") or n.get("educationalLevel")))
    return {k: v for k, v in out.items() if v}


CRITERIA_RX = re.compile(r"selection criteria|selected (?:on|based on)|assessed on|evaluated on|evaluation criteria|"
                         r"we (?:look|are looking) for|candidates? (?:will be|are) (?:assessed|evaluated|judged)|"
                         r"selection (?:is|will be) based", re.I)


def _apply_jsonld(opp, ld: dict, url: str, add, today: date, source_type) -> None:
    snip = "JSON-LD " + json.dumps(ld, ensure_ascii=False)[:250]
    if ld.get("name") and opp.title in ("", "(untitled page)"):
        opp.title = str(ld["name"])[:200]
    if ld.get("deadline"):
        try:
            d = date.fromisoformat(ld["deadline"])
        except ValueError:
            d = None
        if d and not any(x.date == d.isoformat() for x in opp.deadlines):
            cert = (DeadlineCertainty.HISTORICAL if d < today else
                    DeadlineCertainty.CONFIRMED if source_type == SourceType.OFFICIAL else DeadlineCertainty.EXPECTED)
            dl = Deadline(kind=DeadlineKind.SCHOLARSHIP, certainty=cert, date=d.isoformat(),
                          label=f"JSON-LD {ld.get('deadline_property')}", source_url=url, cycle=opp.current_cycle)
            opp.deadlines.append(dl)
            add(f"deadline.{dl.kind}", dl.date, snip)
    if ld.get("amount") and not any(c.amount for c in opp.funding):
        opp.funding.append(FundingComponent(kind="other", covered=True, amount=ld["amount"],
                                            currency=(ld.get("currency") or None), note="award amount declared in JSON-LD"))
        add("funding.other", ld["amount"], snip)
    if ld.get("eligible_region") and opp.nationality.mode == "unknown":
        found = countries.mentions(ld["eligible_region"])
        if found:
            opp.nationality = NationalityRule(mode="include", countries=sorted(found), note="from JSON-LD eligibleRegion")
            add("nationality", opp.nationality.to_dict(), snip)
    if ld.get("funder") and not opp.institution:
        opp.institution = ld["funder"][:120]


DOLLAR_TLD = {"au": "AUD", "ca": "CAD", "nz": "NZD", "sg": "SGD", "hk": "HKD", "tw": "TWD", "mx": "MXN", "ar": "ARS",
              "cl": "CLP", "co": "COP"}


def _dollar_currency(comps, snippets, url: str) -> None:
    """A bare "$" on an Australian or Canadian page is not US dollars: read it from the country domain; "US$" and
    "USD" stay USD. On other domains a bare "$" keeps the USD reading."""
    from urllib.parse import urlparse
    tld = (urlparse(url).hostname or "").rsplit(".", 1)[-1]
    cur = DOLLAR_TLD.get(tld)
    if not cur:
        return
    for c, snip in zip(comps, snippets):
        if c.currency == "USD" and re.search(r"(?<![A-Za-z])\$", snip) and not re.search(r"US\$|USD|US dollars?", snip):
            c.currency = cur


def extract_opportunity(page: Page, *, provider_name: str, provider_type, source_type: SourceType,
                        country_hint: list[str], retrieved_at: str, today: date) -> tuple[Opportunity, list[str]]:
    """Build an Opportunity whose every populated field has an Evidence entry."""
    from .models import stable_id
    from .normalize import normalize_url
    text = programme_text(page.text)   # round 27: sibling programmes listed at the end are not this programme
    url = page.url
    ev: list[Evidence] = []
    conf = 0.7 if source_type == SourceType.OFFICIAL else 0.4

    def add(field, value, snippet, c=conf):
        ev.append(Evidence(field=field, value=value, source_url=url, source_type=source_type,
                           snippet=clean_snippet(snippet), retrieved_at=retrieved_at, confidence=c,
                           status=VerificationStatus.EXTRACTED))

    title = page.title or "(untitled page)"
    opp = Opportunity(id=stable_id(normalize_url(url), prefix="sch"), title=title[:200], provider_name=provider_name,
                      provider_type=provider_type, info_url=url)
    add("title", title, title)
    # round 47: where the study happens, from the page's own words only (destinations.py). The country a search asked
    # for was the applicants' country or an unrelated one as often as the destination; it is kept as a tag.
    from .destinations import extract_destinations
    dest, dest_snips = extract_destinations(text, page.title or "")
    opp.destination_countries = list(dest)
    for c, snip in zip(dest, dest_snips):
        add("destination", c, snip)
    if country_hint:
        opp.tags.append("searched_for:" + ",".join(country_hint))
    opp.page_language = page.language

    for href, label in page.links:
        if re.search(r"apply (?:now|online|here)|application (?:form|portal)|online application|submit (?:an |your )?application",
                     label, re.I):
            opp.application_url = href
            add("application_url", href, label, c=conf - 0.1)
            break

    opp.own_programme_words = sorted(own_programme_tokens(text, page.title or ""))
    opp.deadlines = extract_deadlines(text, url, today, title=page.title or "")
    if source_type != SourceType.OFFICIAL:  # a non-official page can suggest a date, never confirm one
        for d in opp.deadlines:
            if d.certainty == DeadlineCertainty.CONFIRMED:
                d.certainty = DeadlineCertainty.EXPECTED
                d.label = f"[not from official source] {d.label}"
    for d in opp.deadlines:   # a month-only opening is quoted as the month the page states, not as a day
        add(f"deadline.{d.kind}", d.approximate if "(month only)" in (d.approximate or "") else d.date or d.approximate,
            d.label)
    by_kind: dict = {}
    for d in opp.deadlines:
        if d.date and d.certainty in (DeadlineCertainty.CONFIRMED, DeadlineCertainty.EXPECTED) \
                and d.kind in (DeadlineKind.SCHOLARSHIP, DeadlineKind.ADMISSION) and d.scope == "general":
            by_kind.setdefault((d.kind, d.cycle), set()).add(d.date)
    for (kind, cycle), dates in by_kind.items():
        if len(dates) > 1:
            opp.conflicts.append(f"deadline.{kind} ({cycle or 'cycle unknown'}): page states several dates {', '.join(sorted(dates))} - separate rounds or a conflict; check")
    if opp.conflicts:
        opp.verification_status = VerificationStatus.CONFLICTING
    cycles = [d.cycle for d in opp.deadlines if d.cycle and d.certainty != DeadlineCertainty.HISTORICAL
              and d.approximate != CLOSED_NOTE]   # a call the page calls closed is not the current cycle
    opp.current_cycle = cycles[0] if cycles else detect_cycle(text)

    opp.funding, fsn = extract_funding(text)
    _dollar_currency(opp.funding, fsn, url)
    for c, s in zip(opp.funding, fsn):
        add(f"funding.{c.kind}", c.to_dict(), s)

    opp.language_requirements, opp.moi_policy, lsn = extract_language(text)
    for r, s in zip(opp.language_requirements, lsn):
        add(f"language.{r.test}", r.minimum, s)
    if opp.moi_policy:
        add("moi_policy", opp.moi_policy, opp.moi_policy)

    opp.study_levels = extract_levels(text)
    if opp.study_levels:
        # one piece of evidence per level, each with a sentence that names that level as offered (not as a
        # prerequisite or an exclusion); a level with no such sentence is dropped
        from .evidence import study_levels_supported
        kept = []
        sents = _level_sentences(text)
        for lvl in opp.study_levels:
            snip = next((x for x in sents if re.search(LEVEL_RX[lvl], x) and not study_levels_supported([lvl], x)), "")
            if snip:
                kept.append(lvl)
                add("study_levels", [lvl], snip, c=conf - 0.2)
        opp.study_levels = kept

    opp.nationality, nsn = extract_nationality(text)
    if nsn:
        from .evidence import substantiates as _subst
        best = next((x for x in nsn if not _subst("nationality", opp.nationality.to_dict(), x)), nsn[0])
        add("nationality", opp.nationality.to_dict(), best, c=conf - 0.1)
    elif opp.nationality.note.startswith("needs review"):
        opp.uncertainties.append(opp.nationality.note)
        ev.append(Evidence(field="nationality", value=None, source_url=url, source_type=source_type,
                           snippet=clean_snippet(opp.nationality.note.split(": ", 2)[-1]), retrieved_at=retrieved_at,
                           confidence=0.3, note=opp.nationality.note, verdict="needs_review"))
    if not opp.destination_countries:
        # round 48: a university's own page is about study there, so the country of its web address, unless the page
        # sends people elsewhere or is only for that country's citizens (destinations.host_destination). Marked as
        # inferred: the page does not state it.
        from .destinations import host_destination
        hd, why = host_destination(url, text, page.title or "", opp.nationality.mode, opp.nationality.countries)
        if hd:
            opp.destination_countries = list(hd)
            opp.tags.append("destination:host")
            ev.append(Evidence(field="destination", value=hd[0], source_url=url, source_type=source_type, snippet="",
                               retrieved_at=retrieved_at, confidence=conf - 0.3, note=why[:300]))

    from .org_names import describe
    from .parties import extract_parties, payer
    opp.funding_parties = extract_parties(text)
    for p in opp.funding_parties:
        # the name as written stays the value; aliases are recorded beside it with their source
        d = describe(p["name"], text)
        if d["page_aliases"] or d["registry"]:
            p["aliases"] = d
    for p in opp.funding_parties:
        add(f"party.{p['role']}", p["name"], p["quote"], c=conf - 0.1)
    pay = payer(opp.funding_parties)
    if pay and not opp.institution:
        # only a sentence that says who funds or offers it; a host university or a partner never fills this
        opp.institution = pay["name"][:120]
        add("provider", opp.institution, pay["quote"], c=conf - 0.1)

    opp.required_documents, dsn = extract_documents(text, url)
    for d, s in zip(opp.required_documents, dsn):
        add(f"document.{d.name}", d.to_dict(), s)

    acad = extract_academics(text)
    dur, dsnip = extract_duration(text)
    if dur:
        opp.funding_duration = dur
        add("funding_duration", dur, dsnip)
    for k in ("min_gpa", "gpa_scale", "max_age", "min_age", "age_limits", "min_work_years", "requires_supervisor",
              "requires_research_proposal"):
        if k in acad:
            setattr(opp, k, acad[k])
            snip = acad.get({"min_gpa": "_gpa_snip", "gpa_scale": "_gpa_snip", "max_age": "_age_snip", "min_age": "_age_snip",
                             "age_limits": "_age_snip",
                             "min_work_years": "_work_snip"}.get(k, ""), "")
            if not snip:
                kw = {"requires_supervisor": r"supervisor|professor|advisor", "requires_research_proposal": r"research proposal"}
                snip = next((x for x in _sentences(text) if re.search(kw.get(k, "$^"), x, re.I)), "")
            add(k, acad[k], snip)

    for s in _sentences(text):
        if CRITERIA_RX.search(s) and len(opp.selection_criteria) < 8:
            opp.selection_criteria.append(clean_snippet(s, 300))
    if opp.selection_criteria:
        add("selection_criteria", opp.selection_criteria, opp.selection_criteria[0])

    ld = jsonld_fields(page)
    if ld:
        _apply_jsonld(opp, ld, url, add, today, source_type)

    flags = injection_flags(text)
    if flags:
        opp.uncertainties.append("page contains text addressed to AI systems; treated as untrusted and ignored")
    if not opp.deadlines:
        opp.uncertainties.append("no deadline found on this page")
    if not opp.funding:
        opp.uncertainties.append("funding terms not found on this page")
    if opp.nationality.mode == "unknown":
        opp.uncertainties.append("nationality eligibility not stated on this page")
    from .evidence import substantiates
    for e in ev:
        e.cycle = e.cycle or opp.current_cycle
        bad = substantiates(e.field, e.value, e.snippet) if e.field != "title" else None
        if bad:
            e.warnings.append(bad)
    for d in opp.deadlines:
        d.retrieved_at = retrieved_at
    opp.evidence = ev
    return opp, flags
