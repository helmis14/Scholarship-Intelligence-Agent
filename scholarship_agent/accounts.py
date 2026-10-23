"""Accounts for the multi-user service (round 46): registration, login, sessions, password change, account deletion.

- Passwords: scrypt (N=2^15, r=8, p=1, 16-byte salt per user), compared in constant time; the parameters are stored
  with the hash so they can be raised later. Policy: 10 to 256 characters, not a common password, not the e-mail.
- E-mail: stored encrypted (crypto.FieldCipher) and found through a keyed hash, so the database holds no address in
  clear. Messages never say whether an address is registered.
- Tokens: 256 random bits, given to the client once and stored as SHA-256 only; sessions expire after 30 days or 7 idle
  days; a password change or account deletion ends every session.
- Lockout: 5 failed logins lock the account for 15 minutes (the HTTP layer also limits attempts per client).
- auth_events keeps what happened and when, with no IP address or user agent.
Each account owns one applicant profile (`profile_id`); every private route of the service is called with it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from .store import Store, now

SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
MAXMEM = 64 * 1024 * 1024
SESSION_DAYS, IDLE_DAYS = 30, 7
MAX_FAILED, LOCK_MINUTES = 5, 15
TERMS_VERSION, PRIVACY_VERSION = "2026-10-23", "2026-10-23"
COMMON = {"password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop", "iloveyou12", "letmein123",
          "admin12345", "welcome123", "abcdefghij", "0123456789", "1111111111", "beasiswa123", "scholarship", "qwerty1234",
          "passw0rd12", "football12", "monkey1234", "dragon1234", "sunshine12", "princess12", "indonesia1"}
EMAIL_RX = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


class AuthError(ValueError):
    """Wrong credentials, a locked account or an invalid token (HTTP 401/403)."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RX.match(e) or len(e) > 320:
        raise ValueError("enter a valid e-mail address")
    return e


def check_password(password: str, email: str = "") -> None:
    if not isinstance(password, str) or not 10 <= len(password) <= 256:
        raise ValueError("the password must have 10 to 256 characters")
    low = password.lower()
    if low in COMMON or len(set(password)) < 4:
        raise ValueError("this password is too common; choose a longer phrase")
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and local in low:
        raise ValueError("the password must not contain your e-mail name")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, maxmem=MAXMEM, **SCRYPT)
    return "scrypt${n}${r}${p}${salt}${dk}".format(**SCRYPT, salt=base64.b64encode(salt).decode(),
                                                    dk=base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=32, maxmem=MAXMEM)
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


_DUMMY = None


def _dummy_hash() -> str:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_urlsafe(16))
    return _DUMMY


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


class Accounts:
    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------------ helpers

    def _event(self, user_id: Optional[str], event: str) -> None:
        self.store.x("INSERT INTO auth_events (user_id, event, at) VALUES (?,?,?)", (user_id, event, now()))

    def _user(self, user_id: str) -> Optional[dict]:
        rows = self.store.q("SELECT * FROM users WHERE id = ?", (user_id,))
        return self.store.dec_row(rows[0], "users") if rows else None

    def _issue_token(self, user_id: str, kind: str = "session") -> dict:
        token = secrets.token_urlsafe(32)
        t = _now()
        self.store.x("INSERT INTO auth_tokens (token_hash, user_id, kind, created_at, expires_at, last_used_at) "
                     "VALUES (?,?,?,?,?,?)", (_token_hash(token), user_id, kind, t.isoformat(),
                                              (t + timedelta(days=SESSION_DAYS)).isoformat(), t.isoformat()))
        return {"token": token, "token_type": "Bearer", "expires_in_days": SESSION_DAYS, "idle_timeout_days": IDLE_DAYS}

    @staticmethod
    def public(user: dict) -> dict:
        return {"user_id": user["id"], "email": user["email"], "profile_id": user["profile_id"],
                "created_at": user["created_at"], "consent": json.loads(user["consent"] or "{}")}

    # ------------------------------------------------------------------ flows

    def register(self, email: str, password: str, accept_terms: bool, accept_privacy: bool,
                 ai_drafting_consent: bool = False, age_confirmed: bool = False) -> dict:
        e = normalize_email(email)
        check_password(password, e)
        if not (accept_terms and accept_privacy):
            raise ValueError("accept the terms of service and the privacy notice to create an account")
        if not age_confirmed:
            raise ValueError("confirm that you are at least 18 years old (or have a parent's or guardian's consent "
                             "where the law requires it)")
        lookup = self.store.cipher.lookup(e)
        if self.store.q("SELECT 1 FROM users WHERE email_lookup = ?", (lookup,)):
            # same answer as a new registration would need: no hint that the address exists
            raise ValueError("this e-mail address cannot be registered; try logging in or resetting the password")
        uid, pid = "usr_" + secrets.token_hex(10), "prf_" + secrets.token_hex(10)
        consent = {"terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION, "accepted_at": now(),
                   "ai_drafting": bool(ai_drafting_consent), "age_confirmed": True}
        import sqlite3
        try:
            self.store.x("INSERT INTO users (id, email_lookup, email, pw_hash, profile_id, created_at, consent) "
                         "VALUES (?,?,?,?,?,?,?)", (uid, lookup, self.store.enc(e, "users", "email"),
                                                    hash_password(password), pid, now(), json.dumps(consent)))
        except sqlite3.IntegrityError:   # two registrations of one address at the same moment
            raise ValueError("this e-mail address cannot be registered; try logging in or resetting the password")
        self._event(uid, "register")
        return {"user": self.public(self._user(uid)), **self._issue_token(uid)}

    def login(self, email: str, password: str) -> dict:
        try:
            e = normalize_email(email)
        except ValueError:
            verify_password(password or "", _dummy_hash())
            raise AuthError("the e-mail or password is wrong")
        rows = self.store.q("SELECT * FROM users WHERE email_lookup = ?", (self.store.cipher.lookup(e),))
        if not rows:
            verify_password(password or "", _dummy_hash())   # same work as a real check: no timing hint
            raise AuthError("the e-mail or password is wrong")
        u = dict(rows[0])
        t = _now()
        if u["disabled"] or (u["locked_until"] and datetime.fromisoformat(u["locked_until"]) > t):
            verify_password(password or "", _dummy_hash())   # same work as a real check
            raise AuthError("this account is disabled" if u["disabled"] else "too many failed logins; try again later")
        if not verify_password(password or "", u["pw_hash"]):
            failed = u["failed_logins"] + 1
            locked = (t + timedelta(minutes=LOCK_MINUTES)).isoformat() if failed >= MAX_FAILED else None
            self.store.x("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                         (0 if locked else failed, locked, u["id"]))
            self._event(u["id"], "login_failed" if not locked else "locked")
            raise AuthError("the e-mail or password is wrong")
        self.store.x("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
                     (t.isoformat(), u["id"]))
        self._event(u["id"], "login")
        return {"user": self.public(self._user(u["id"])), **self._issue_token(u["id"])}

    def authenticate(self, token: str) -> dict:
        """The account behind a bearer token, or AuthError."""
        if not token or len(token) > 200:
            raise AuthError("log in first")
        rows = self.store.q("SELECT * FROM auth_tokens WHERE token_hash = ?", (_token_hash(token),))
        if not rows:
            raise AuthError("the session has ended; log in again")
        tk, t = dict(rows[0]), _now()
        if datetime.fromisoformat(tk["expires_at"]) <= t or \
                datetime.fromisoformat(tk["last_used_at"]) + timedelta(days=IDLE_DAYS) <= t:
            self.store.x("DELETE FROM auth_tokens WHERE token_hash = ?", (tk["token_hash"],))
            raise AuthError("the session has ended; log in again")
        u = self._user(tk["user_id"])
        if not u or u["disabled"]:
            raise AuthError("this account is disabled")
        self.store.x("UPDATE auth_tokens SET last_used_at = ? WHERE token_hash = ?", (t.isoformat(), tk["token_hash"]))
        return u

    def logout(self, token: str) -> None:
        self.store.x("DELETE FROM auth_tokens WHERE token_hash = ?", (_token_hash(token or ""),))

    def change_password(self, user: dict, old: str, new: str) -> dict:
        if not verify_password(old or "", user["pw_hash"]):
            self._event(user["id"], "password_change_failed")
            raise AuthError("the current password is wrong")
        check_password(new, user["email"])
        self.store.x("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(new), user["id"]))
        self.store.x("DELETE FROM auth_tokens WHERE user_id = ?", (user["id"],))
        self._event(user["id"], "password_changed")
        return self._issue_token(user["id"])

    def update_consent(self, user: dict, ai_drafting: bool) -> dict:
        consent = json.loads(user["consent"] or "{}") | {"ai_drafting": bool(ai_drafting), "ai_drafting_changed_at": now()}
        self.store.x("UPDATE users SET consent = ? WHERE id = ?", (json.dumps(consent), user["id"]))
        self._event(user["id"], "consent_changed")
        return consent

    def export(self, user: dict) -> dict:
        from . import profile as profile_mod
        events = [dict(r) for r in self.store.q("SELECT event, at FROM auth_events WHERE user_id = ? ORDER BY id", (user["id"],))]
        self._event(user["id"], "export")
        return {"account": self.public(user) | {"last_login_at": user["last_login_at"]}, "account_events": events,
                **profile_mod.export(self.store, user["profile_id"])}

    def delete(self, user: dict, password: str) -> dict:
        """Delete the account, its sessions and every private record of its profile, in one step."""
        from . import profile as profile_mod
        if not verify_password(password or "", user["pw_hash"]):
            raise AuthError("the password is wrong")
        counts = profile_mod.delete(self.store, user["profile_id"])
        with self.store.private as c:
            counts["auth_tokens"] = c.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user["id"],)).rowcount
            counts["auth_events"] = c.execute("DELETE FROM auth_events WHERE user_id = ?", (user["id"],)).rowcount
            counts["users"] = c.execute("DELETE FROM users WHERE id = ?", (user["id"],)).rowcount
        self.store.private.execute("VACUUM")
        return counts

    # ------------------------------------------------------------------ password reset

    RESET_MINUTES = 30

    def request_reset(self, email: str, mailer=None) -> dict:
        """Send a one-time reset code to the address if it has an account. The answer is the same either way."""
        same = {"accepted": True, "message": "If this address has an account, a reset code is on its way."}
        try:
            e = normalize_email(email)
        except ValueError:
            return same
        rows = self.store.q("SELECT id FROM users WHERE email_lookup = ? AND disabled = 0", (self.store.cipher.lookup(e),))
        mailer = mailer or Mailer.from_env()
        if not rows or mailer is None:
            if rows:
                self._event(rows[0]["id"], "reset_requested_no_mailer")
            return same
        code = secrets.token_urlsafe(24)
        uid = rows[0]["id"]
        self.store.x("DELETE FROM password_resets WHERE user_id = ?", (uid,))
        self.store.x("INSERT INTO password_resets (code_hash, user_id, expires_at) VALUES (?,?,?)",
                     (_token_hash(code), uid, (_now() + timedelta(minutes=self.RESET_MINUTES)).isoformat()))
        mailer.send(e, "Your password reset code",
                    f"Someone asked to reset the password of your scholarship account.\n\nReset code: {code}\n\n"
                    f"The code works once, for {self.RESET_MINUTES} minutes. If it was not you, ignore this message; "
                    f"your password stays the same.")
        self._event(uid, "reset_requested")
        return same

    def confirm_reset(self, code: str, new_password: str) -> dict:
        rows = self.store.q("SELECT * FROM password_resets WHERE code_hash = ?", (_token_hash(code or ""),))
        if not rows or rows[0]["used_at"] or datetime.fromisoformat(rows[0]["expires_at"]) <= _now():
            raise AuthError("the reset code is wrong or has expired; ask for a new one")
        u = self._user(rows[0]["user_id"])
        check_password(new_password, u["email"])
        self.store.x("UPDATE users SET pw_hash = ?, failed_logins = 0, locked_until = NULL WHERE id = ?",
                     (hash_password(new_password), u["id"]))
        self.store.x("UPDATE password_resets SET used_at = ? WHERE code_hash = ?", (now(), rows[0]["code_hash"]))
        self.store.x("DELETE FROM auth_tokens WHERE user_id = ?", (u["id"],))
        self._event(u["id"], "password_reset")
        return self._issue_token(u["id"])

    def purge_expired(self) -> int:
        """Remove expired sessions (run on a schedule)."""
        t = _now()
        with self.store.private as c:
            return c.execute("DELETE FROM auth_tokens WHERE expires_at <= ? OR last_used_at <= ?",
                             (t.isoformat(), (t - timedelta(days=IDLE_DAYS)).isoformat())).rowcount


class Mailer:
    """Sends account e-mails (password reset only) through an SMTP server the operator configures:
    SCHOLAR_SMTP_HOST, SCHOLAR_SMTP_PORT (587), SCHOLAR_SMTP_USER, SCHOLAR_SMTP_PASSWORD, SCHOLAR_SMTP_FROM.
    STARTTLS is required. Without SCHOLAR_SMTP_HOST nothing is sent and reset requests are only recorded."""

    def __init__(self, host: str, port: int, user: str, password: str, sender: str):
        self.host, self.port, self.user, self.password, self.sender = host, port, user, password, sender

    @classmethod
    def from_env(cls) -> Optional["Mailer"]:
        import os
        host = os.environ.get("SCHOLAR_SMTP_HOST", "").strip()
        if not host:
            return None
        return cls(host, int(os.environ.get("SCHOLAR_SMTP_PORT", "587")), os.environ.get("SCHOLAR_SMTP_USER", ""),
                   os.environ.get("SCHOLAR_SMTP_PASSWORD", ""), os.environ.get("SCHOLAR_SMTP_FROM", ""))

    def send(self, to: str, subject: str, body: str) -> None:
        import smtplib
        import ssl
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            if self.user:
                s.login(self.user, self.password)
            s.send_message(msg)
