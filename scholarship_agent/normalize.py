"""URL normalization and duplicate detection."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|_hs|ref$|source$|campaign$|yclid$|msclkid$)", re.I)


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url.strip())
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = p.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    path = re.sub(r"/(index|default)\.(html?|php|aspx?)$", "/", path, flags=re.I)
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)))
    return urlunsplit(("https" if scheme in ("http", "https") else scheme, netloc, path, query, ""))


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(the|of|for|and|in|programme|program|scholarships?|20\d{2}(?:[/-]\d{2,4})?)\b", " ", s)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


GENERIC = set("phd master masters bachelor research studentship studentships fellowship fellowships graduate "
              "postgraduate international students student award awards grant grants funding funded university "
              "excellence merit government".split())


def dedup_key(title: str, provider: str) -> str:
    return f"{_fold(provider)}|{_fold(title)}"


def similar(a_title: str, a_provider: str, b_title: str, b_provider: str, threshold: float = 0.88) -> bool:
    """Same opportunity? Providers are compared only when both are real names: a search hit or
    aggregator page only knows its hostname, which says nothing about who funds the award."""
    real = lambda p: p and "." not in p  # noqa: E731
    if real(a_provider) and real(b_provider) and \
            SequenceMatcher(None, _fold(a_provider), _fold(b_provider)).ratio() < 0.8:
        return False
    a, b = _fold(a_title), _fold(b_title)
    if not a or not b:
        return False
    short, long_ = sorted((a, b), key=len)
    distinctive = [w for w in short.split() if w not in GENERIC]
    if len(short.split()) >= 2 and distinctive and f" {short} " in f" {long_} ":
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold
