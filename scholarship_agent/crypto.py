"""Encryption of private data at rest (round 46).

Private fields (profile, notes, checklist data, document text and reviews, outcome lessons, account e-mail) are stored
as `enc1:<key id>:<base64(nonce | ciphertext | tag)>`, AES-256-GCM with the table and column as associated data, so a
value cannot be moved to another column unnoticed. Reading accepts plaintext written before encryption was switched
on; `python3 -m scholarship_agent encrypt-private` rewrites such rows and rewraps old keys after a key change.

Keys, in order of precedence:
  SCHOLAR_DATA_KEYS   "k2:<base64 32 bytes>,k1:<base64 32 bytes>"  (the first is used for new values; the rest
                      only decrypt, for key rotation)
  SCHOLAR_DATA_KEY    one base64 key (id "k1")
  <data>/private/keys.json  created 0600 on first use, outside production only
SCHOLAR_LOOKUP_KEY (base64) keys the HMAC that finds an account by e-mail without storing the address in clear; it is
also kept in keys.json outside production.
SCHOLAR_ENV=production refuses to start without the `cryptography` package and keys from the environment (a key file
next to the database it protects is not enough for a hosted service; use the platform's secret store).

Without `cryptography` outside production, values are stored as before (file permissions only) and `enabled` is
False; `doctor()` says so.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Optional

PREFIX = "enc1:"


class CryptoConfigError(RuntimeError):
    pass


def _b64d(s: str) -> bytes:
    raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)) if ("-" in s or "_" in s) else base64.b64decode(s + "=" * (-len(s) % 4))
    return raw


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def new_key() -> str:
    """A fresh base64 key for SCHOLAR_DATA_KEY / SCHOLAR_LOOKUP_KEY."""
    return base64.b64encode(secrets.token_bytes(32)).decode()


def production() -> bool:
    return os.environ.get("SCHOLAR_ENV", "").strip().lower() == "production"


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except ImportError:
        return None


class FieldCipher:
    def __init__(self, keys: dict[str, bytes], current: Optional[str], lookup_key: bytes):
        for kid, k in keys.items():
            if len(k) != 32:
                raise CryptoConfigError(f"data key {kid} must be 32 bytes (base64 of 32 random bytes)")
        self.keys = keys
        self.current = current
        self.lookup_key = lookup_key
        self._aes = _aesgcm()
        self.enabled = bool(self._aes and current)

    # ------------------------------------------------------------------ setup

    @classmethod
    def from_env(cls, private_dir: Path) -> "FieldCipher":
        keys, current = {}, None
        spec = os.environ.get("SCHOLAR_DATA_KEYS", "").strip()
        if spec:
            for part in spec.split(","):
                kid, _, val = part.strip().partition(":")
                if not kid or not val:
                    raise CryptoConfigError("SCHOLAR_DATA_KEYS must look like 'k2:<base64>,k1:<base64>'")
                keys[kid] = _b64d(val)
                current = current or kid
        elif os.environ.get("SCHOLAR_DATA_KEY", "").strip():
            keys["k1"] = _b64d(os.environ["SCHOLAR_DATA_KEY"].strip())
            current = "k1"
        lookup = os.environ.get("SCHOLAR_LOOKUP_KEY", "").strip()
        lookup_key = _b64d(lookup) if lookup else None
        if production():
            if _aesgcm() is None:
                raise CryptoConfigError("SCHOLAR_ENV=production needs the 'cryptography' package for encryption at rest")
            if not keys or lookup_key is None:
                raise CryptoConfigError("SCHOLAR_ENV=production needs SCHOLAR_DATA_KEY (or SCHOLAR_DATA_KEYS) and "
                                        "SCHOLAR_LOOKUP_KEY from the environment or a secret store")
            return cls(keys, current, lookup_key)
        if not keys or lookup_key is None:
            stored = cls._key_file(private_dir)
            if not keys and _aesgcm() is not None:
                keys, current = {stored["current"]: _b64d(stored["keys"][stored["current"]])}, stored["current"]
                keys |= {k: _b64d(v) for k, v in stored["keys"].items() if k not in keys}
            lookup_key = lookup_key or _b64d(stored["lookup"])
        return cls(keys, current, lookup_key)

    @staticmethod
    def _key_file(private_dir: Path) -> dict:
        path = Path(private_dir) / "keys.json"
        if path.exists():
            return json.loads(path.read_text())
        private_dir.mkdir(parents=True, exist_ok=True)
        data = {"current": "k1", "keys": {"k1": new_key()}, "lookup": new_key(),
                "note": "development keys; in production set SCHOLAR_DATA_KEY and SCHOLAR_LOOKUP_KEY from a secret store"}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        return data

    # ------------------------------------------------------------------ use

    def encrypt(self, value: Optional[str], field: str) -> Optional[str]:
        if value is None or not self.enabled:
            return value
        nonce = secrets.token_bytes(12)
        ct = self._aes(self.keys[self.current]).encrypt(nonce, value.encode("utf-8"), field.encode())
        return f"{PREFIX}{self.current}:{_b64e(nonce + ct)}"

    def decrypt(self, value: Optional[str], field: str) -> Optional[str]:
        if not isinstance(value, str) or not value.startswith(PREFIX):
            return value   # written before encryption was switched on
        kid, _, blob = value[len(PREFIX):].partition(":")
        if self._aes is None:
            raise CryptoConfigError("this database holds encrypted values; install 'cryptography' to read them")
        if kid not in self.keys:
            raise CryptoConfigError(f"no key {kid!r} to decrypt a stored value (set SCHOLAR_DATA_KEYS with the old key)")
        raw = _b64d(blob)
        from cryptography.exceptions import InvalidTag
        try:
            return self._aes(self.keys[kid]).decrypt(raw[:12], raw[12:], field.encode()).decode("utf-8")
        except InvalidTag as e:
            raise CryptoConfigError(f"a stored value in {field} failed its integrity check") from e

    def needs_rewrap(self, value: Optional[str]) -> bool:
        """Plaintext (when encryption is on) or a value under an older key."""
        if not isinstance(value, str) or not self.enabled:
            return False
        return not value.startswith(f"{PREFIX}{self.current}:")

    def lookup(self, text: str) -> str:
        """Keyed hash for finding a record by a secret value (an e-mail address) without storing it in clear."""
        return hmac.new(self.lookup_key, text.encode("utf-8"), hashlib.sha256).hexdigest()

    def describe(self) -> dict:
        return {"encryption_at_rest": self.enabled, "algorithm": "AES-256-GCM" if self.enabled else None,
                "current_key": self.current if self.enabled else None, "decrypt_only_keys": sorted(set(self.keys) - {self.current}),
                "production": production(),
                "note": None if self.enabled else "install 'cryptography' to encrypt private data at rest"}
