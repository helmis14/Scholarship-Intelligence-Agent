"""Text from permitted PDF calls for applications.

Uses pypdf when it is installed (better font handling). Otherwise a small
stdlib reader handles the common case: Flate-compressed content streams with
simple (WinAnsi/standard) fonts. PDFs whose text is drawn with embedded CID
fonts, scanned images, or encryption come back as `unreadable` with a reason -
never as guessed text.
"""

from __future__ import annotations

import re
import zlib



def _unescape(s: bytes) -> str:
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == 0x5C and i + 1 < len(s):  # backslash
            n = s[i + 1]
            esc = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40, ord(")"): 41,
                   ord("\\"): 92}
            if n in esc:
                out.append(esc[n])
                i += 2
                continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
                continue
            if n in (10, 13):  # line continuation
                i += 2
                continue
            i += 1
            continue
        out.append(c)
        i += 1
    return out.decode("cp1252", "replace")


def _raw_unescape(s: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == 0x5C and i + 1 < len(s):
            n = s[i + 1]
            esc = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40, ord(")"): 41,
                   ord("\\"): 92}
            if n in esc:
                out.append(esc[n])
                i += 2
                continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
                continue
            i += 2 if n in (10, 13) else 1
            continue
        out.append(c)
        i += 1
    return bytes(out)


TOKEN = re.compile(rb"<<|>>|\((?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*\)|<[0-9A-Fa-f\s]*>|\[|\]|-?\d*\.?\d+|"
                   rb"/[^\s/\[\]()<>]+|[A-Za-z'\"*]+")


def parse_cmap(data: bytes) -> dict[int, str]:
    """ToUnicode CMap: bfchar and bfrange entries -> {code: text}."""
    out: dict[int, str] = {}

    def u(h: bytes) -> str:
        try:
            return bytes.fromhex(h.decode()).decode("utf-16-be", "replace")
        except ValueError:
            return ""
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            out[int(a, 16)] = u(b)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for a, b, rest in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]+>)", block):
            lo, hi = int(a, 16), int(b, 16)
            if hi - lo > 5000:
                continue
            if rest.startswith(b"["):
                for k, h in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", rest)):
                    out[lo + k] = u(h)
            else:
                base = int(rest[1:-1], 16)
                for k in range(hi - lo + 1):
                    try:
                        out[lo + k] = chr(base + k)
                    except (ValueError, OverflowError):
                        pass
    return out


def _decode(raw: bytes, cmap: dict[int, str]) -> str:
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be", "replace")
    if cmap:
        two = max(cmap) > 255
        if two and len(raw) % 2 == 0:
            return "".join(cmap.get(int.from_bytes(raw[k:k + 2], "big"), "") for k in range(0, len(raw), 2))
        if not two:
            return "".join(cmap.get(b, chr(b)) for b in raw)
    return raw.decode("cp1252", "replace")


def _content_text(data: bytes, cmap: dict[int, str] | None = None, fonts: dict[bytes, dict[int, str]] | None = None) -> str:
    cmap = cmap or {}
    fonts = fonts or {}
    parts: list[str] = []
    in_array = False
    depth = 0          # inside << >> (marked-content properties such as /Lang (en-GB)): not page text
    nums: list[float] = []
    last_name = b""
    cur = cmap
    for m in TOKEN.finditer(data):
        t = m.group(0)
        if t == b"<<":
            depth += 1
            continue
        if t == b">>":
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        if t.startswith(b"/"):
            last_name = t[1:]
            continue
        if t.startswith(b"("):
            parts.append(_decode(_raw_unescape(t[1:-1]), cur))
        elif t.startswith(b"<") and len(t) > 2:
            h = re.sub(rb"\s", b"", t[1:-1])
            try:
                parts.append(_decode(bytes.fromhex(h.decode() + ("0" if len(h) % 2 else "")), cur))
            except ValueError:
                pass
        elif t == b"[":
            in_array = True
        elif t == b"]":
            in_array = False
        elif re.fullmatch(rb"-?\d*\.?\d+", t):
            nums.append(float(t))
            if in_array and float(t) < -180:
                parts.append(" ")
            continue
        elif t == b"Tf":
            cur = fonts.get(last_name, cmap if not fonts else {})
        elif t in (b"Td", b"TD"):
            # a move with a vertical component starts a new line; a horizontal one is a word gap
            parts.append("\n" if len(nums) >= 2 and abs(nums[-1]) > 0.5 else " ")
        elif t in (b"T*", b"'", b'"', b"ET", b"Tm"):
            parts.append("\n")
        nums = []
    text = "".join(parts)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text))


def _rejoin(text: str) -> str:
    """Word processors place every text run separately; glue fragments back into lines."""
    out: list[str] = []
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        if out:
            prev = out[-1]
            if prev[-1:].isdigit() and line[:1].isdigit() and len(line) <= 3:
                out[-1] = prev + line           # "202" + "4"
                continue
            if not re.search(r"[.:;!?]$", prev) and (line[:1].islower() or line[:1] in ",.;:)–-" or len(prev) < 40
                                                     and not line[:1].isupper()):
                out[-1] = prev + ("" if line[:1] in ",.;:)" or prev.endswith("-") else " ") + line
                continue
        out.append(line)
    return "\n".join(out)


OBJ_RX = re.compile(rb"(\d+)\s+\d+\s+obj\b(.*?)\bendobj", re.S)


def _stream_of(body: bytes) -> bytes | None:
    m = re.search(rb"stream\r?\n", body)
    if not m:
        return None
    raw = body[m.end():]
    k = raw.rfind(b"endstream")
    raw = raw[:k] if k >= 0 else raw
    raw = raw.rstrip(b"\r\n")
    head = body[:m.start()]
    if b"FlateDecode" in head:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(raw)
            except zlib.error:
                return None
    if b"/Filter" in head:
        return None
    return raw


def _objects(data: bytes) -> dict[int, bytes]:
    """Object number -> body, including objects packed in compressed object streams."""
    objs: dict[int, bytes] = {}
    for m in OBJ_RX.finditer(data):
        objs[int(m.group(1))] = m.group(2)
    for num, body in list(objs.items()):
        if b"/ObjStm" not in body[:400]:
            continue
        st = _stream_of(body)
        n = re.search(rb"/N\s+(\d+)", body)
        first = re.search(rb"/First\s+(\d+)", body)
        if not (st and n and first):
            continue
        hdr = [int(x) for x in st[:int(first.group(1))].split()]
        pairs = list(zip(hdr[0::2], hdr[1::2]))
        for k, (onum, off) in enumerate(pairs):
            start = int(first.group(1)) + off
            end = int(first.group(1)) + pairs[k + 1][1] if k + 1 < len(pairs) else len(st)
            objs.setdefault(onum, st[start:end])
    return objs


def _stdlib_text(data: bytes) -> tuple[str, str]:
    if re.search(rb"/Encrypt\s+\d+\s+\d+\s+R", data) or b"/Encrypt" in data[:4096]:
        return "", "encrypted PDF"
    objs = _objects(data)
    # fonts: object -> ToUnicode map; resource names (/F1) -> font object
    cmaps: dict[int, dict[int, str]] = {}
    for num, body in objs.items():
        m = re.search(rb"/ToUnicode\s+(\d+)\s+\d+\s+R", body)
        if m and int(m.group(1)) in objs:
            st = _stream_of(objs[int(m.group(1))])
            if st:
                cmaps[num] = parse_cmap(st)
    names: dict[bytes, dict[int, str]] = {}

    def font_dict(b: bytes):
        for nm, ref in re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+\d+\s+R", b):
            if int(ref) in cmaps:
                names.setdefault(nm, cmaps[int(ref)])
    for body in objs.values():
        for m in re.finditer(rb"/Font\s*<<(.*?)>>", body, re.S):
            font_dict(m.group(1))
        for m in re.finditer(rb"/Font\s+(\d+)\s+\d+\s+R", body):
            font_dict(objs.get(int(m.group(1)), b""))
    chunks = []
    for i, body in enumerate(objs.values()):
        if i > 4000 or b"stream" not in body or b"/Subtype /Image" in body[:300] or b"/Subtype/Image" in body[:300]:
            continue
        st = _stream_of(body)
        if st and (b"Tj" in st or b"TJ" in st) and b"BT" in st:
            chunks.append(_content_text(st, None, names))
    if not objs:  # no parsable object table: fall back to raw stream scan
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
            try:
                st = zlib.decompress(m.group(1).rstrip(b"\r\n"))
            except zlib.error:
                continue
            if b"Tj" in st or b"TJ" in st:
                chunks.append(_content_text(st))
    text = _rejoin("\n".join(c for c in chunks if c.strip()))
    if not text.strip():
        return "", "no extractable text (scanned images or unsupported encoding)"
    letters = sum(ch.isalpha() for ch in text)
    if letters < 0.4 * len(text.replace(" ", "").replace("\n", "")):
        return "", "text uses an embedded font encoding this reader cannot map; install pypdf for better results"
    return text, "ok (stdlib reader)"


def pdf_text(data: bytes) -> tuple[str, str]:
    """(text, status). Empty text means the PDF could not be read; status says why."""
    if not data.startswith(b"%PDF"):
        return "", "not a PDF"
    try:
        import pypdf  # optional
        import io
        r = pypdf.PdfReader(io.BytesIO(data))
        if r.is_encrypted:
            return "", "encrypted PDF"
        text = "\n".join((p.extract_text() or "") for p in r.pages[:60])
        if text.strip():
            return text, "ok (pypdf)"
    except ImportError:
        pass
    except Exception as e:  # malformed file: fall back to the stdlib reader
        status = f"pypdf failed ({type(e).__name__})"
        text, s2 = _stdlib_text(data)
        return text, f"{status}; {s2}"
    return _stdlib_text(data)


def make_pdf(lines: list[str]) -> bytes:
    """Build a minimal one-page PDF (Helvetica, Flate-compressed). Used by tests and fixtures."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 11 Tf 50 780 Td 14 TL\n" + "\n".join(f"({esc(l)}) Tj T*" for l in lines) + "\nET"
    stream = zlib.compress(content.encode("cp1252", "replace"))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" /Filter /FlateDecode >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
