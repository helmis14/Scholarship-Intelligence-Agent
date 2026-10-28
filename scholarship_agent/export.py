"""Round 51: application documents as files people send - Word and PDF laid out like a typed application essay.

One reading of the Markdown draft feeds both writers. Essays and letters: the applicant's name and the scholarship at
the top left, the document's title centred, serif text justified with a first-line indent, page numbers at the foot.
CVs: the name large, the contact line under it, section headings over a rule, bullets with a hanging indent. The
writer's notes ("> " lines) stay in the Word draft in grey and are left out of the PDF; unwritten [YOU WRITE] parts stay
visible in both, so nothing half-done goes out unnoticed. Stdlib only: the PDF uses the standard Times fonts that every
reader has, so no font is embedded.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
import zlib
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

from . import pdf_metrics

CV_KINDS = {"academic_cv", "scholarship_cv"}
ESSAY_KINDS = {"motivation_letter", "sop", "personal_statement", "essay", "research_proposal", "study_plan",
               "career_goals", "leadership_essay"}
SMALL_WORDS = {"a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to"}


def style_of(kind: str) -> str:
    return "cv" if kind in CV_KINDS else "essay" if kind in ESSAY_KINDS else "plain"


def title_case(text: str) -> str:
    words = text.split()
    return " ".join(w if (i and w.lower() in SMALL_WORDS) or w[:1].isupper() else w[:1].upper() + w[1:]
                    for i, w in enumerate(words))


def blocks(markdown: str, kind: str = "", header: Optional[list[str]] = None, title: str = "",
           notes: bool = True) -> list[tuple[str, str]]:
    """[(type, text)] with types header, title, name, contact, heading, para, bullet, sub, note, note_bullet."""
    cv = kind in CV_KINDS
    out: list[tuple[str, str]] = [("header", x) for x in (header or []) if x and not cv]
    para: list[str] = []

    def flush():
        if para:
            out.append(("para", " ".join(para)))
            para.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s or s.startswith("<!--"):
            flush()
            continue
        if s.startswith("# ") and not any(t in ("title", "name") for t, _ in out):
            flush()
            text = s[2:].strip()
            out.append(("name", text) if cv else ("title", title_case(title or text.split(" - ")[0])))
            continue
        if s.startswith("## "):
            flush()
            out.append(("heading", s[3:].strip()))
            continue
        if s.startswith(">"):
            flush()
            if notes:
                n = s.lstrip(">").strip()
                out.append(("note_bullet", n[2:]) if n.startswith("- ") else ("note", n))
            continue
        if line.startswith(("- ", "* ")):
            flush()
            out.append(("bullet", s[2:].strip()))
            continue
        if line.startswith("  ") and out and out[-1][0] in ("bullet", "sub") and not para:
            out.append(("sub", s))
            continue
        if cv and out and out[-1][0] == "name" and not para and " | " in s:
            out.append(("contact", s))
            continue
        para.append(s)
    flush()
    if title and not cv and not any(t == "title" for t, _ in out):   # an edited draft without its heading keeps its title
        out.insert(sum(t == "header" for t, _ in out), ("title", title_case(title)))
    return out


def short_line(text: str) -> bool:
    """A salutation, a sign-off or a name ("Dear Committee," "Rina Test"): never indented or stretched."""
    return len(text.split()) <= 6


def runs(text: str, font: str = "R") -> list[tuple[str, str]]:
    """**bold** spans as their own runs; everything else in `font`."""
    return [("B", p[2:-2]) if p.startswith("**") and p.endswith("**") and len(p) > 4 else (font, p)
            for p in re.split(r"(\*\*.+?\*\*)", text) if p]


# ---------------------------------------------------------------------------------------------------------------- PDF

A4 = (595.28, 841.89)
MARGIN = 72.0
FONTS = {"R": ("F1", pdf_metrics.ROMAN), "B": ("F2", pdf_metrics.BOLD), "I": ("F3", pdf_metrics.ITALIC)}
# per style: body size, leading factor, justify, first-line indent, space after a paragraph
STYLES = {"essay": (12.0, 1.32, True, 36.0, 10.0), "plain": (11.5, 1.3, False, 0.0, 8.0), "cv": (11.0, 1.28, False, 0.0, 5.0)}


def _enc(text: str) -> bytes:
    """WinAnsi bytes; a letter outside it falls back to its unaccented form, anything else to '?'."""
    out = bytearray()
    for ch in text:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            out += unicodedata.normalize("NFKD", ch).encode("cp1252", "ignore") or b"?"
    return bytes(b if b >= 32 else 32 for b in out)


def _w(data: bytes, font: str, size: float) -> float:
    widths = FONTS[font][1]
    return sum(widths[b - 32] for b in data) * size / 1000


def _lit(data: bytes) -> bytes:
    return b"(" + data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class _Pages:
    def __init__(self, style: str):
        self.style = style
        self.pages: list[list[bytes]] = []
        self.width = A4[0] - 2 * MARGIN
        self.new_page()

    def new_page(self):
        self.pages.append([])
        self.y = A4[1] - MARGIN

    def room(self, height: float):
        if self.y - height < MARGIN + 6:
            self.new_page()

    def emit(self, op: str | bytes):
        self.pages[-1].append(op.encode("latin-1") if isinstance(op, str) else op)

    def rule(self, gap: float = 3.0):
        self.y -= gap
        self.emit(f"0.6 G 0.5 w {MARGIN:.2f} {self.y:.2f} m {MARGIN + self.width:.2f} {self.y:.2f} l S 0 G")

    def words(self, text: str, font: str) -> list[list[tuple[str, bytes]]]:
        """Words as lists of (font, bytes) pieces: a bold span ending in a comma stays one word."""
        out: list[list[tuple[str, bytes]]] = []
        glue = False
        for f, part in runs(text, font):
            for tok in re.split(r"( +)", part):
                if not tok:
                    continue
                if tok.isspace():
                    glue = False
                    continue
                if glue and out:
                    out[-1].append((f, _enc(tok)))
                else:
                    out.append([(f, _enc(tok))])
                glue = True
        return out

    def text(self, text: str, size: float, font: str = "R", indent: float = 0.0, first: float = 0.0,
             justify: bool = False, align: str = "left", leading: Optional[float] = None, gray: float = 0.0):
        """Wrapped text at the current position; `first` is the extra indent of the first line."""
        leading = leading or size * STYLES[self.style][1]
        space = 0.25 * size   # the space is 250/1000 em in Times-Roman, -Bold and -Italic
        words = self.words(text, font)
        lines: list[tuple[list, float]] = []
        cur: list = []
        cur_w = 0.0
        for word in words:
            ww = sum(_w(b, f, size) for f, b in word)
            avail = self.width - indent - (first if not lines else 0.0)
            if cur and cur_w + space + ww > avail:
                lines.append((cur, cur_w))
                cur, cur_w = [word], ww
            else:
                cur_w += (space if cur else 0.0) + ww
                cur.append(word)
        if cur:
            lines.append((cur, cur_w))
        for i, (line, lw) in enumerate(lines):
            self.room(leading)
            self.y -= leading
            x = MARGIN + indent + (first if i == 0 else 0.0)
            avail = self.width - indent - (first if i == 0 else 0.0)
            if align == "center":
                x += max(0.0, (avail - lw) / 2)
            gaps = len(line) - 1
            tw = (avail - lw) / gaps if justify and gaps and i < len(lines) - 1 and avail > lw else 0.0
            segs: list[list] = []   # one string per change of font; the spaces stretch by Tw when justified
            for j, word in enumerate(line):
                for k, (f, data) in enumerate(word):
                    data = (b" " if j and k == 0 else b"") + data
                    if segs and segs[-1][0] == f:
                        segs[-1][1] += data
                    else:
                        segs.append([f, data])
            ops = [b"BT", f"{gray:.2f} g {x:.2f} {self.y:.2f} Td {tw:.3f} Tw".encode()]
            for f, data in segs:
                ops += [f"/{FONTS[f][0]} {size:.1f} Tf".encode(), _lit(data) + b" Tj"]
            ops.append(b"ET")
            self.emit(b" ".join(ops))

    def gap(self, h: float):
        self.y -= h


def to_pdf(markdown: str, kind: str = "", header: Optional[list[str]] = None, title: str = "") -> bytes:
    style = style_of(kind)
    size, _, justify, indent, after = STYLES[style]
    pg = _Pages(style)
    items = blocks(markdown, kind, header, title, notes=False)
    for n, (t, text) in enumerate(items):
        if t == "header":
            pg.text(text, 11.0, leading=13.5)
            if n + 1 < len(items) and items[n + 1][0] != "header":
                pg.gap(10)
        elif t == "title":
            pg.gap(8)
            pg.text(text, 13.0, "B", align="center")
            pg.gap(14)
        elif t == "name":
            pg.text(text, 18.0, "B", leading=22)
        elif t == "contact":
            pg.text(text, 10.0, gray=0.25)
            pg.gap(6)
        elif t == "heading":
            pg.room(40)
            pg.gap(8 if style == "cv" else 6)
            pg.text(text.upper() if style == "cv" else text, 11.0 if style == "cv" else size, "B")
            if style == "cv":
                pg.rule(4)
            pg.gap(4)
        elif t == "bullet":
            pg.room(size * 1.4)   # the first line stays on this page, so the bullet sits beside it
            pg.emit(f"BT 0 g /F1 {size:.1f} Tf {MARGIN + 3:.2f} {pg.y - size * STYLES[style][1]:.2f} Td ".encode()
                    + _lit(b"\x95") + b" Tj ET")
            pg.text(text, size, indent=14)
            pg.gap(2)
        elif t == "sub":
            pg.text(text, size - 0.5, indent=14, gray=0.2)
            pg.gap(2)
        else:   # a paragraph
            pg.text(text, size, first=0.0 if short_line(text) else indent, justify=justify)
            pg.gap(after)
    for i, ops in enumerate(pg.pages, 1):   # page numbers at the foot, centred
        label = _enc(f"- {i} -")
        x = (A4[0] - _w(label, "R", 10)) / 2
        ops.append(f"BT 0.35 g /F1 10 Tf {x:.2f} {MARGIN / 2:.2f} Td ".encode() + _lit(label) + b" Tj ET")
    return _assemble([b"\n".join(p) for p in pg.pages], title or kind.replace("_", " "))


def _assemble(contents: list[bytes], title: str) -> bytes:
    objs: list[bytes] = [b"", b""]   # 1 catalog, 2 pages: written last
    font_ids = []
    for name in ("Times-Roman", "Times-Bold", "Times-Italic"):
        objs.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} /Encoding /WinAnsiEncoding >>".encode())
        font_ids.append(len(objs))
    objs.append(b"<< /Producer (Scholarship Intelligence) /Title " + _lit(_enc(title)) + b" >>")
    info = len(objs)
    kids = []
    for content in contents:
        data = zlib.compress(content)
        objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
        cid = len(objs)
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {A4[0]} {A4[1]}] /Resources << /Font << "
                     f"/F1 {font_ids[0]} 0 R /F2 {font_ids[1]} 0 R /F3 {font_ids[2]} 0 R >> >> /Contents {cid} 0 R >>").encode())
        kids.append(len(objs))
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, info, xref)
    return bytes(out)


# --------------------------------------------------------------------------------------------------------------- Word

W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _wruns(text: str, size: int, font: str = "R", color: str = "", italic: bool = False) -> str:
    out = []
    for f, part in runs(text, font):
        props = (("<w:b/>" if f == "B" else "") + ("<w:i/>" if italic or f == "I" else "")
                 + (f'<w:color w:val="{color}"/>' if color else "") + f'<w:sz w:val="{size}"/>')
        out.append(f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
    return "".join(out)


def _wpara(inner: str, jc: str = "left", before: int = 0, after: int = 0, line: int = 276, first: int = 0,
           left: int = 0, hanging: int = 0, border: bool = False) -> str:
    ind = (f'<w:ind w:left="{left}"' + (f' w:hanging="{hanging}"' if hanging else "")
           + (f' w:firstLine="{first}"' if first else "") + "/>") if (left or first or hanging) else ""
    bdr = '<w:pBdr><w:bottom w:val="single" w:sz="4" w:space="1" w:color="999999"/></w:pBdr>' if border else ""
    return (f'<w:p><w:pPr>{bdr}<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>'
            f'{ind}<w:jc w:val="{jc}"/></w:pPr>{inner}</w:p>')


def to_docx(markdown: str, kind: str = "", header: Optional[list[str]] = None, title: str = "") -> bytes:
    """Word draft with the same layout as the PDF; notes stay, in grey italics, for the writer to delete."""
    style = style_of(kind)
    body = {"essay": 24, "plain": 23, "cv": 22}[style]
    paras = []
    items = blocks(markdown, kind, header, title, notes=True)
    for n, (t, text) in enumerate(items):
        if t == "header":
            last = n + 1 >= len(items) or items[n + 1][0] != "header"
            paras.append(_wpara(_wruns(text, 22), after=200 if last else 0))
        elif t == "title":
            paras.append(_wpara(_wruns(text, 26, "B"), jc="center", before=120, after=280))
        elif t == "name":
            paras.append(_wpara(_wruns(text, 36, "B"), after=40))
        elif t == "contact":
            paras.append(_wpara(_wruns(text, 20, color="444444"), after=160))
        elif t == "heading":
            paras.append(_wpara(_wruns(text.upper() if style == "cv" else text, 22 if style == "cv" else body, "B"),
                                before=200, after=80, border=style == "cv"))
        elif t == "bullet":
            dot = f'<w:r><w:rPr><w:sz w:val="{body}"/></w:rPr><w:t>•</w:t><w:tab/></w:r>'
            paras.append(_wpara(dot + _wruns(text, body), left=360, hanging=240, after=40))
        elif t == "sub":
            paras.append(_wpara(_wruns(text, body - 1, color="333333"), left=360, after=60))
        elif t in ("note", "note_bullet"):
            paras.append(_wpara(_wruns(("– " if t == "note_bullet" else "") + text, 20, color="6D6C66", italic=True),
                                after=40, left=360 if t == "note_bullet" else 0))
        else:
            essay = style == "essay" and not short_line(text)
            paras.append(_wpara(_wruns(text, body), jc="both" if essay else "left", first=720 if essay else 0,
                                after=200 if style == "essay" else 120))
    sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rId2"/><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
            '</w:sectPr>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>'
                + "".join(paras) + sect + "</w:body></w:document>")
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W_NS}><w:docDefaults><w:rPrDefault><w:rPr>'
              '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>'
              f'<w:sz w:val="{body}"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
              '<w:spacing w:after="0" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults></w:styles>')
    footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {W_NS}><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
              '<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="595959"/></w:rPr><w:t xml:space="preserve">- </w:t></w:r>'
              '<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="595959"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="595959"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
              '<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="595959"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
              '<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="595959"/></w:rPr><w:t>1</w:t></w:r>'
              '<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="595959"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>'
              '<w:r><w:rPr><w:sz w:val="20"/><w:color w:val="595959"/></w:rPr><w:t xml:space="preserve"> -</w:t></w:r></w:p></w:ftr>')
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                '</Relationships>')
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/footer1.xml", footer)
    return buf.getvalue()
