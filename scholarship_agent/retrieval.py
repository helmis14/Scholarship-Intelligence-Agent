"""Layered retrieval. Layer A is the ordinary HTTP Fetcher (robots.txt, throttling, retries, size and type limits).
Layer B is the HTML/PDF parsing in extract.py and pdf.py (text, tables, JSON-LD, links, document references).
Layer C, a headless browser, runs only when the HTTP page itself shows that its content is rendered by JavaScript.

The browser never bypasses anything: robots.txt was already checked for the URL, a login or CAPTCHA page stops
the browser path, and the result is cached against the HTTP body so an unchanged page is not rendered again.
Playwright is optional (`pip install playwright`); without it the agent records that a page needed a browser.
"""

from __future__ import annotations

import re
import threading
from typing import Optional, Protocol

from .net import USER_AGENT, Response

JS_REQUIRED = re.compile(r"enable javascript|requires? javascript|javascript is (?:disabled|required|needed)|"
                         r"turn on javascript|activez javascript|javascript aktivieren|aktifkan javascript|"
                         r"habilite javascript|activa javascript", re.I)
APP_ROOT = re.compile(r"<div[^>]+id=[\"'](?:root|app|__next|__nuxt|q-app)[\"'][^>]*>\s*</div>", re.I)
ACCESS_CONTROL = re.compile(r"captcha|cf-challenge|challenge-platform|are you a robot|verify you are (?:a )?human|"
                            r"access denied|sign in to continue|log ?in to (?:view|continue)|please log ?in", re.I)


def needs_browser(resp: Response, page) -> tuple[bool, str]:
    """(True, why) only when the HTTP response is evidently a JavaScript shell; a short page is not enough."""
    if resp.is_pdf:
        return False, "PDF: parsed directly"
    html = resp.text or ""
    n = len(page.text or "")
    # visible text only: script code on ordinary pages often mentions captcha libraries
    if ACCESS_CONTROL.search((page.title or "") + " " + (page.text or "")[:5000]) and n < 3000:
        return False, "login or CAPTCHA page: access controls are not bypassed"
    scripts = html.lower().count("<script")
    if JS_REQUIRED.search(html) and n < 1500:
        return True, "the page says JavaScript is required"
    if APP_ROOT.search(html) and n < 800:
        return True, "empty client-side application root"
    if n < 300 and scripts >= 5:
        return True, "almost no text but many scripts"
    return False, "HTTP text is sufficient"


MIN_READABLE = 80   # visible characters beyond the title below which a page cannot be judged at all


def load_status(page) -> tuple[bool, str]:
    """(loaded, why): could the page's content be read at all? A page that did not load (JavaScript shell, login
    or CAPTCHA wall, unreadable PDF, almost no text) is "not assessed", never "not a programme"."""
    text = page.text or ""
    body = text.replace(page.title or "", "", 1).strip() if page.title else text.strip()
    if getattr(page, "pdf_status", "") and not text:
        return False, f"PDF unreadable: {page.pdf_status}"
    if ACCESS_CONTROL.search((page.title or "") + " " + text[:5000]) and len(text) < 3000:
        return False, "login or CAPTCHA page: access controls are not bypassed; check the page by hand"
    if getattr(page, "js_required", False) and len(text) < 1500:
        return False, "the page says JavaScript is required"
    if getattr(page, "app_root", False) and len(text) < 800:
        return False, "empty client-side application root (needs a browser)"
    if len(text) < 300 and getattr(page, "script_count", 0) >= 5:
        return False, "almost no text but many scripts (needs a browser)"
    toks = text.split()
    if len(toks) >= 50 and sum(len(t) == 1 for t in toks) > 0.6 * len(toks):
        return False, "text extracted letter by letter (spaced-out PDF or image text): unreadable"
    if len(body) < MIN_READABLE:
        return False, f"only {len(body)} readable characters: content missing or loaded by JavaScript"
    return True, "loaded"


class Browser(Protocol):
    name: str

    def render(self, url: str) -> tuple[str, str, int]:
        """(final URL, rendered HTML, HTTP status)"""
        ...

    def close(self) -> None: ...


class PlaywrightBrowser:
    """One Chromium for the whole run; one page at a time by default; images, fonts and media blocked;
    navigation and script time bounded; pages and contexts always closed."""
    name = "playwright"

    def __init__(self, max_pages: int = 1, timeout_ms: int = 20000, block=("image", "font", "media")):
        self.timeout_ms, self.block = timeout_ms, set(block)
        self._sem = threading.Semaphore(max_pages)
        self._pw = self._browser = None
        self.renders = 0

    @staticmethod
    def available() -> tuple[bool, str]:
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            return False, "Python Playwright is not installed (pip install playwright); browser fallback is off"
        return True, "ok"

    def _ensure(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            import os
            self._pw = sync_playwright().start()
            # SCHOLAR_BROWSER_EXECUTABLE: an already-installed Chromium (no browser download)
            exe = os.environ.get("SCHOLAR_BROWSER_EXECUTABLE") or None
            self._browser = self._pw.chromium.launch(headless=True, executable_path=exe)

    def render(self, url: str) -> tuple[str, str, int]:
        with self._sem:
            self._ensure()
            ctx = self._browser.new_context(user_agent=USER_AGENT)
            try:
                ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in self.block
                          else route.continue_())
                page = ctx.new_page()
                page.set_default_timeout(self.timeout_ms)
                r = page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                self.renders += 1
                return page.url, page.content(), (r.status if r else 0)
            finally:
                ctx.close()

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
            if self._pw is not None:
                self._pw.stop()
        finally:
            self._browser = self._pw = None


def default_browser() -> tuple[Optional[Browser], str]:
    """SCHOLAR_BROWSER=playwright turns the fallback on; anything else (default) keeps it off."""
    import os
    if (os.environ.get("SCHOLAR_BROWSER") or "").lower() != "playwright":
        return None, "browser fallback off (set SCHOLAR_BROWSER=playwright to enable)"
    ok, why = PlaywrightBrowser.available()
    return (PlaywrightBrowser(), "playwright") if ok else (None, why)


def rendered(store, browser: Browser, resp: Response, max_bytes: int = 3_000_000) -> tuple[Optional[Response], str]:
    """Render `resp.url` with the browser, reusing the cached rendering while the HTTP body is unchanged."""
    from .normalize import normalize_url
    key = normalize_url(resp.url) + "#rendered"
    row = store.cached_page(key) if store is not None else None
    if row is not None and row["sha256"] == resp.sha256 and row["text"]:
        out = Response(row["final_url"] or resp.url, 200, "text/html", row["text"])
        out.method = "browser-cache"
        return out, "cached rendering (HTTP body unchanged)"
    try:
        final, html, status = browser.render(resp.url)
    except Exception as e:   # a browser failure must never lose the HTTP page
        return None, f"browser failed ({type(e).__name__})"
    from .extract import Page
    seen = Page(final, html)
    if ACCESS_CONTROL.search((seen.title or "") + " " + seen.text[:5000]) and len(seen.text) < 3000:
        return None, "rendered page is a login or CAPTCHA page: not bypassed"
    if not html or len(html) > max_bytes:
        return None, "rendered page empty or too large"
    if store is not None:
        store.cache_page(key, status or 200, resp.sha256, "text/html", html, final_url=final, method="browser")
    out = Response(final, status or 200, "text/html", html)
    out.method = "browser"
    return out, "rendered"
