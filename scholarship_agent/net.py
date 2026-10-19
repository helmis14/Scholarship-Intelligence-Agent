"""Polite HTTP: robots.txt gate, per-host rate limit, retries with backoff.

Never bypasses authentication, CAPTCHAs or bot walls: a 401/403/429-with-
challenge is recorded as a failure, not retried with a disguised client.
The robots.txt reading (RFC 9309, fails closed) is scholarship_agent/robots.py.

The transport is injectable so every test runs offline.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from .robots import allowed as robots_allowed, has_undecodable_rule, is_robots_body

USER_AGENT = os.environ.get("SCHOLAR_USER_AGENT",
                            "ScholarshipIntelligenceAgent/1.0 (+research; respects robots.txt)")
ROBOTS_AGENT = "ScholarshipIntelligenceAgent"
MAX_BYTES = 3_000_000
MAX_PDF_BYTES = 15_000_000
ALLOWED_TYPES = ("application/pdf", "text/javascript", "application/javascript", "text/html", "application/xhtml", "text/plain", "application/xml", "text/xml",
                 "application/rss", "application/atom", "application/json", "application/ld+json")


@dataclass
class Response:
    url: str
    status: int
    content_type: str
    text: str
    data: bytes = b""          # raw body for binary types (PDF)

    @property
    def is_pdf(self) -> bool:
        return "pdf" in (self.content_type or "").lower() or self.data[:4] == b"%PDF"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data or self.text.encode("utf-8", "replace")).hexdigest()


class FetchError(Exception):
    def __init__(self, url: str, reason: str, status: int = 0):
        super().__init__(f"{reason}: {url}")
        self.url, self.reason, self.status = url, reason, status


Transport = Callable[[str, dict], Response]


def curl_transport(url: str, headers: dict) -> Response:
    """Same request via the system curl, which validates certificates against the OS trust store and fetches
    missing intermediates. Used only when Python's own TLS verification fails; certificates are still verified."""
    import subprocess
    import tempfile
    args = ["curl", "-sS", "-L", "--compressed", "--max-redirs", "5", "--max-time", "25", "--max-filesize", str(MAX_PDF_BYTES)]
    for k, v in headers.items():
        args += ["-H", f"{k}: {v}"]
    with tempfile.NamedTemporaryFile() as body:
        args += ["-o", body.name, "-w", "%{http_code} %{content_type} %{url_effective}", "--", url]
        r = subprocess.run(args, capture_output=True, timeout=40)
        if r.returncode != 0:
            raise OSError(f"curl exit {r.returncode}: {r.stderr.decode('utf-8', 'replace')[:120]}")
        code, _, rest = r.stdout.decode("utf-8", "replace").partition(" ")
        ctype, _, final = rest.rpartition(" ")
        data = Path(body.name).read_bytes()
    if "pdf" in ctype.lower():
        return Response(final or url, int(code), ctype, "", data)
    m = __import__("re").search(r"charset=([\w-]+)", ctype)
    return Response(final or url, int(code), ctype, data[:MAX_BYTES].decode(m.group(1) if m else "utf-8", "replace"))


def _cert_failure(e: Exception) -> bool:
    import ssl
    return isinstance(getattr(e, "reason", e), ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e)


def urllib_transport(url: str, headers: dict) -> Response:
    try:
        return _urllib(url, headers)
    except urllib.error.URLError as e:
        if _cert_failure(e):
            return curl_transport(url, headers)
        raise


def _decoded(raw: bytes, encoding: str) -> bytes:
    import gzip
    import zlib
    enc = (encoding or "").lower()
    try:
        if "gzip" in enc or raw[:2] == b"\x1f\x8b":
            return gzip.decompress(raw)
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
    except (OSError, EOFError, zlib.error):
        return raw  # truncated or not really compressed: keep the bytes we have
    return raw


def _urllib(url: str, headers: dict) -> Response:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get("Content-Type", "")
            if "pdf" in ctype.lower():
                raw = _decoded(r.read(MAX_PDF_BYTES + 1), r.headers.get("Content-Encoding", ""))
                if len(raw) > MAX_PDF_BYTES:
                    raise ValueError("PDF larger than limit")
                return Response(r.geturl(), r.status, ctype, "", raw)
            # some servers compress even when not asked; urllib does not undo it
            raw = _decoded(r.read(MAX_BYTES + 1), r.headers.get("Content-Encoding", ""))
            charset = r.headers.get_content_charset() or "utf-8"
            return Response(r.geturl(), r.status, ctype, raw[:MAX_BYTES].decode(charset, "replace"))
    except urllib.error.HTTPError as e:
        return Response(url, e.code, e.headers.get("Content-Type", "") if e.headers else "", "")


class Fetcher:
    def __init__(self, transport: Optional[Transport] = None, min_interval: float = 2.0,
                 retries: int = 3, backoff: float = 2.0, sleep: Callable[[float], None] = time.sleep,
                 respect_robots: bool = True):
        self.transport = transport or urllib_transport
        self.min_interval, self.retries, self.backoff = min_interval, retries, backoff
        self.sleep = sleep
        self.respect_robots = respect_robots
        self._last: dict[str, float] = {}
        self.host_interval: dict[str, float] = {}   # per-host slowdowns learned from HTTP 429
        self.rate_limited_wait = 15.0
        self._robots: dict[str, Optional[str]] = {}
        self._why: dict[str, str] = {}
        self.clock = time.monotonic
        # one lock per host: parallel fetches to different hosts, never two at once to the same host
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self.requests = 0   # HTTP requests sent (robots.txt included), for benchmarks

    def _lock(self, host: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(host, threading.Lock())

    def _throttle(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            wait = max(self.min_interval, self.host_interval.get(host, 0)) - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def robots_ok(self, url: str) -> tuple[bool, str]:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            try:
                self._throttle(parts.netloc)
                self.requests += 1
                r = self.transport(base + "/robots.txt", {"User-Agent": USER_AGENT})
                if r.status == 404 or r.status == 410:
                    self._robots[base] = ""
                elif r.status == 200 and is_robots_body(r.text) and not has_undecodable_rule(r.text):
                    self._robots[base] = r.text
                elif r.status in (401, 403, 429):
                    self._robots[base] = None
                    self._why[base] = (f"robots.txt answered HTTP {r.status}: the site blocks automated clients - "
                                       "not bypassed; check the page manually or via an official API/feed")
                else:
                    self._robots[base] = None
                    self._why[base] = f"robots.txt answered HTTP {r.status} - permission unconfirmed, not fetching"
            except Exception as e:
                self._robots[base] = None
                self._why[base] = f"robots.txt unreachable ({type(e).__name__}) - permission unconfirmed, not fetching"
        body = self._robots[base]
        if body is None:
            return False, self._why.get(base, "robots.txt unreadable - not fetching")
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        for agent in (ROBOTS_AGENT, "*"):
            if not robots_allowed(body, agent, path):
                return False, f"robots.txt disallows {agent}"
        return True, "allowed"

    def get(self, url: str) -> Response:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise FetchError(url, "unsupported URL")
        with self._lock(parts.netloc):
            return self._get(url, parts)

    def _get(self, url: str, parts) -> Response:
        if self.respect_robots:
            ok, why = self.robots_ok(url)
            if not ok:
                raise FetchError(url, why)
        last_err = "no attempt"
        for attempt in range(self.retries):
            self._throttle(parts.netloc)
            try:
                self.requests += 1
                r = self.transport(url, {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.5",
                                         "Accept-Language": "en,*;q=0.5"})
            except Exception as e:  # network error: retry
                last_err = f"{type(e).__name__}: {e}"
            else:
                if r.status in (401, 403):
                    raise FetchError(url, f"HTTP {r.status} - access restricted, not bypassed", r.status)
                if r.status in (404, 410):
                    raise FetchError(url, f"HTTP {r.status} - page gone", r.status)
                if r.status == 429 or r.status >= 500:
                    last_err = f"HTTP {r.status}"
                elif 200 <= r.status < 300:
                    ctype = (r.content_type or "").lower()
                    if ctype and not ctype.startswith(ALLOWED_TYPES):
                        raise FetchError(url, f"content type {ctype} not parsed", r.status)
                    return r
                else:
                    raise FetchError(url, f"HTTP {r.status}", r.status)
            if attempt < self.retries - 1:
                wait = self.backoff * (2 ** attempt)
                if last_err == "HTTP 429":
                    # the site asked us to slow down: back off much more, and slow every later request to it
                    wait = max(wait, self.rate_limited_wait * (2 ** attempt))
                    self.host_interval[parts.netloc] = max(self.host_interval.get(parts.netloc, 0), self.rate_limited_wait)
                self.sleep(wait)
        raise FetchError(url, f"gave up after {self.retries} attempts ({last_err})")
