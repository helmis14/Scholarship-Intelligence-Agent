"""HTTP JSON API for the multi-user service (round 46), standard library only.

    python3 -m scholarship_agent serve --host 127.0.0.1 --port 8765

Run it behind a reverse proxy that terminates HTTPS (Caddy, nginx); it binds to 127.0.0.1 unless
SCHOLAR_ALLOW_PUBLIC_BIND=1. Set SCHOLAR_HTTPS=1 behind HTTPS (adds Strict-Transport-Security) and
SCHOLAR_TRUST_PROXY=1 only when the proxy sets X-Forwarded-For (used for rate limits). SCHOLAR_CORS_ORIGINS lists the
web front ends allowed to call the API (comma separated; none by default).

Public routes read the catalog; account and applicant routes need `Authorization: Bearer <token>` from
/auth/register or /auth/login, and only ever see the caller's own profile. Discovery, ingestion and operator routes are
not exposed here (they stay on the command line). Request bodies are JSON, at most 1 MB.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from .accounts import Accounts, AuthError
from .service import NotFound, ScholarshipService
from .store import Store
from .tracker import TransitionError

PREFIX = "/api/v1"
MAX_BODY = 1024 * 1024
LIMITS = {"auth": (10, 60), "report": (5, 60), "default": (120, 60)}   # requests per window (seconds) and client


class RateLimiter:
    def __init__(self):
        self.hits: dict[tuple, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, bucket: str, client: str) -> bool:
        n, window = LIMITS[bucket]
        t = time.monotonic()
        with self.lock:
            if len(self.hits) > 50000:   # forget idle clients
                for k in [k for k, q in self.hits.items() if not q or q[-1] <= t - 300]:
                    del self.hits[k]
            q = self.hits[(bucket, client)]
            while q and q[0] <= t - window:
                q.popleft()
            if len(q) >= n:
                return False
            q.append(t)
            return True


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


ROUTES: list[tuple[str, re.Pattern, str, bool, str]] = []   # method, path, handler name, needs login, rate bucket


def route(method: str, path: str, auth: bool = False, bucket: str = "default"):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + PREFIX + path + "$"), fn.__name__, auth, bucket))
        return fn
    return deco


class Api:
    """The route handlers; `ctx` carries the request's service, accounts, user, query and body."""

    # ---------------------------------------------------------------- public

    @route("GET", "/health")
    def health(self, ctx):
        return {"ok": True, "schema_version": "1.0", "encryption_at_rest": ctx.store.cipher.enabled}

    @route("GET", "/opportunities")
    def opportunities(self, ctx):
        q = ctx.query
        return ctx.svc.search_opportunities(country=q.get("country", ""), level=q.get("level", ""), text=q.get("text", "")[:200])

    @route("GET", r"/opportunities/(?P<ref>[^/]{1,200})")
    def opportunity(self, ctx, ref):
        return ctx.svc.get_opportunity(ref)

    @route("GET", r"/opportunities/(?P<ref>[^/]{1,200})/card")
    def card(self, ctx, ref):
        return ctx.svc.decision_card(ref)

    @route("POST", r"/opportunities/(?P<ref>[^/]{1,200})/reports", bucket="report")
    def report(self, ctx, ref):
        b = ctx.body
        return ctx.svc.report_issue(ref, str(b.get("field", "")), str(b.get("note", "")), str(b.get("shown_value", "")))

    # ---------------------------------------------------------------- accounts

    @route("POST", "/auth/register", bucket="auth")
    def register(self, ctx):
        b = ctx.body
        return ctx.accounts.register(str(b.get("email", "")), str(b.get("password", "")), b.get("accept_terms") is True,
                                     b.get("accept_privacy") is True, b.get("ai_drafting_consent") is True,
                                     b.get("age_confirmed") is True)

    @route("POST", "/auth/login", bucket="auth")
    def login(self, ctx):
        return ctx.accounts.login(str(ctx.body.get("email", "")), str(ctx.body.get("password", "")))

    @route("POST", "/auth/password-reset/request", bucket="auth")
    def reset_request(self, ctx):
        return ctx.accounts.request_reset(str(ctx.body.get("email", "")))

    @route("POST", "/auth/password-reset/confirm", bucket="auth")
    def reset_confirm(self, ctx):
        return ctx.accounts.confirm_reset(str(ctx.body.get("code", "")), str(ctx.body.get("new_password", "")))

    @route("POST", "/auth/logout", auth=True)
    def logout(self, ctx):
        ctx.accounts.logout(ctx.token)
        return {"logged_out": True}

    @route("POST", "/auth/password", auth=True, bucket="auth")
    def password(self, ctx):
        return ctx.accounts.change_password(ctx.user, str(ctx.body.get("current_password", "")),
                                            str(ctx.body.get("new_password", "")))

    @route("GET", "/account", auth=True)
    def account(self, ctx):
        return {"account": ctx.accounts.public(ctx.user)}

    @route("PATCH", "/account/consent", auth=True)
    def consent(self, ctx):
        return {"consent": ctx.accounts.update_consent(ctx.user, ctx.body.get("ai_drafting") is True)}

    @route("GET", "/account/export", auth=True)
    def export(self, ctx):
        return ctx.accounts.export(ctx.user)

    @route("DELETE", "/account", auth=True, bucket="auth")
    def delete_account(self, ctx):
        return {"deleted": ctx.accounts.delete(ctx.user, str(ctx.body.get("password", "")))}

    # ---------------------------------------------------------------- applicant (own profile only)

    @route("GET", "/profile", auth=True)
    def profile(self, ctx):
        try:
            return ctx.svc.get_profile(ctx.pid)
        except NotFound:
            return {"profile": None, "missing": ["everything: send PATCH /profile"]}

    @route("PATCH", "/profile", auth=True)
    def profile_patch(self, ctx):
        patch = ctx.body.get("profile", ctx.body)
        if not isinstance(patch, dict):
            raise ValueError("send the profile fields as a JSON object")
        patch.pop("id", None)
        return ctx.svc.setup_profile(patch, ctx.pid)

    @route("GET", "/ranking", auth=True)
    def ranking(self, ctx):
        return ctx.svc.rank(ctx.pid, top=min(int(ctx.query.get("top", "20") or 20), 100))

    @route("GET", r"/matches/(?P<ref>[^/]{1,200})", auth=True)
    def match(self, ctx, ref):
        return ctx.svc.match(ref, ctx.pid)

    @route("GET", "/applications", auth=True)
    def applications(self, ctx):
        return ctx.svc.track(profile_id=ctx.pid)

    @route("GET", r"/applications/(?P<ref>[^/]{1,200})", auth=True)
    def application(self, ctx, ref):
        return ctx.svc.track(ref, profile_id=ctx.pid)

    @route("PATCH", r"/applications/(?P<ref>[^/]{1,200})", auth=True)
    def application_patch(self, ctx, ref):
        b = ctx.body
        return ctx.svc.track(ref, b.get("status"), str(b.get("note", ""))[:2000], b.get("item"), b.get("item_status"),
                             profile_id=ctx.pid)

    @route("POST", r"/applications/(?P<ref>[^/]{1,200})/plan", auth=True)
    def plan(self, ctx, ref):
        return ctx.svc.plan(ref, ctx.pid)

    @route("GET", r"/applications/(?P<ref>[^/]{1,200})/briefs/(?P<kind>[a-z_]{2,40})", auth=True)
    def brief(self, ctx, ref, kind):
        return ctx.svc.brief(ref, kind, ctx.pid)

    @route("PUT", r"/applications/(?P<ref>[^/]{1,200})/documents/(?P<kind>[a-z_]{2,40})", auth=True)
    def save_draft(self, ctx, ref, kind):
        content = ctx.body.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("send the draft as {\"content\": \"...\"}")
        return ctx.svc.save_draft(ref, kind, content, ctx.pid)

    @route("GET", r"/applications/(?P<ref>[^/]{1,200})/readiness", auth=True)
    def readiness(self, ctx, ref):
        return ctx.svc.documents_audit(ref, ctx.pid)

    @route("GET", "/deadlines", auth=True)
    def deadlines(self, ctx):
        return ctx.svc.deadlines(min(int(ctx.query.get("within_days", "90") or 90), 730), ctx.pid,
                                 ctx.query.get("tracked_only") == "1")


class Context:
    def __init__(self, store: Store, svc: ScholarshipService, query: dict, body: dict):
        self.store, self.svc, self.query, self.body = store, svc, query, body
        self.accounts = Accounts(store)
        self.user: Optional[dict] = None
        self.token = ""

    @property
    def pid(self) -> str:
        return self.user["profile_id"]


def make_handler(data_dir: Optional[Path] = None, service_factory: Optional[Callable[[Store], ScholarshipService]] = None,
                 quiet: bool = False):
    api, limiter = Api(), RateLimiter()
    origins = {o.strip() for o in os.environ.get("SCHOLAR_CORS_ORIGINS", "").split(",") if o.strip()}
    https = os.environ.get("SCHOLAR_HTTPS") == "1"
    trust_proxy = os.environ.get("SCHOLAR_TRUST_PROXY") == "1"

    def resources():
        # one connection pair per request: sqlite connections stay in their own thread, and nothing is kept between
        # requests except the rate-limit counters
        store = Store(data_dir)
        return store, (service_factory or (lambda st: ScholarshipService(store=st, search=None, llm=None,
                                                                       extractor_llm=None)))(store)

    class Handler(BaseHTTPRequestHandler):
        server_version = "ScholarshipAPI"
        sys_version = ""

        def log_message(self, fmt, *args):   # method, path without query string, status; no tokens, no bodies
            if not quiet:
                sys.stderr.write("%s %s %s\n" % (self.command, urlsplit(self.path).path, args[1] if len(args) > 1 else ""))

        def _client(self) -> str:
            if trust_proxy and self.headers.get("X-Forwarded-For"):
                return self.headers["X-Forwarded-For"].split(",")[0].strip()
            return self.client_address[0]

        def _send(self, status: int, payload: dict, extra: Optional[dict] = None) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            headers = {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body)),
                       "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                       "X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"}
            if https:
                headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            origin = self.headers.get("Origin", "")
            if origin and origin in origins:
                headers |= {"Access-Control-Allow-Origin": origin, "Vary": "Origin",
                            "Access-Control-Allow-Headers": "Authorization, Content-Type",
                            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS"}
            for k, v in (headers | (extra or {})).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD" and status != 204:
                self.wfile.write(body)

        def _error(self, status: int, code: str, message: str) -> None:
            self._send(status, {"error": code, "message": message})

        def do_OPTIONS(self):
            self._send(204 if self.headers.get("Origin", "") in origins else 403, {})

        def do_GET(self):
            self._dispatch()

        def do_POST(self):
            self._dispatch()

        def do_PUT(self):
            self._dispatch()

        def do_PATCH(self):
            self._dispatch()

        def do_DELETE(self):
            self._dispatch()

        def _dispatch(self):
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            match = None
            for method, rx, name, needs_auth, bucket in ROUTES:
                m = rx.match(path)
                if m and method == self.command:
                    match = (name, needs_auth, bucket, {k: unquote(v) for k, v in m.groupdict().items()})
                    break
                if m:
                    match = match or ("__method__", False, "default", {})
            if not match:
                return self._error(404, "not_found", "no such route")
            name, needs_auth, bucket, args = match
            if name == "__method__":
                return self._error(405, "method_not_allowed", "this route does not take that method")
            if not limiter.allow(bucket, self._client()):
                return self._send(429, {"error": "rate_limited", "message": "too many requests; wait a minute"},
                                  {"Retry-After": "60"})
            store = None
            try:
                body = self._body()
                store, svc = resources()
                ctx = Context(store, svc, {k: v[0] for k, v in parse_qs(parts.query).items()}, body)
                if needs_auth:
                    auth = self.headers.get("Authorization", "")
                    ctx.token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
                    ctx.user = ctx.accounts.authenticate(ctx.token)
                status = 201 if name == "register" else 200
                return self._send(status, getattr(api, name)(ctx, **args))
            except ApiError as e:
                return self._error(e.status, e.code, e.message)
            except AuthError as e:
                return self._error(401, "unauthorized", str(e))
            except NotFound as e:
                return self._error(404, "not_found", str(e))
            except (TransitionError, ValueError) as e:
                return self._error(400, "invalid", str(e)[:500])
            except Exception:   # never leak internals; a request id ties the log line to the answer
                rid = uuid.uuid4().hex[:12]
                sys.stderr.write(f"error {rid} on {self.command} {path}\n")
                import traceback
                traceback.print_exc(file=sys.stderr)
                return self._error(500, "server_error", f"internal error (request {rid})")
            finally:
                if store is not None:
                    store.close()

        def _body(self) -> dict:
            if self.command in ("GET", "DELETE") and not self.headers.get("Content-Length"):
                return {}
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ApiError(413, "too_large", "the request body is larger than 1 MB")
            if n == 0:
                return {}
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ApiError(415, "unsupported_media_type", "send JSON with Content-Type: application/json")
            try:
                data = json.loads(self.rfile.read(n).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ApiError(400, "invalid_json", "the body is not valid JSON")
            if not isinstance(data, dict):
                raise ApiError(400, "invalid_json", "the body must be a JSON object")
            return data

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, data_dir: Optional[Path] = None) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "::1", "localhost") and os.environ.get("SCHOLAR_ALLOW_PUBLIC_BIND") != "1":
        raise ValueError("bind to 127.0.0.1 behind an HTTPS reverse proxy, or set SCHOLAR_ALLOW_PUBLIC_BIND=1")
    Store(data_dir).close()   # migrations and key checks before the first request (fails early in production)
    httpd = ThreadingHTTPServer((host, port), make_handler(data_dir))
    httpd.daemon_threads = True
    return httpd
