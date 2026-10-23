"""Round 46: encryption at rest, accounts, and the HTTP API with per-user isolation."""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scholarship_agent.accounts import Accounts, AuthError, check_password, hash_password, verify_password
from scholarship_agent.crypto import CryptoConfigError, FieldCipher, new_key
from scholarship_agent.store import Store

PW = "correct horse battery staple"


class TestCrypto(unittest.TestCase):
    def setUp(self):
        self.k1, self.k2, self.lk = new_key(), new_key(), new_key()

    def cipher(self, spec):
        with mock.patch.dict(os.environ, {"SCHOLAR_DATA_KEYS": spec, "SCHOLAR_LOOKUP_KEY": self.lk}, clear=False):
            return FieldCipher.from_env(Path(tempfile.mkdtemp()))

    def test_round_trip_and_field_binding(self):
        c = self.cipher(f"k1:{self.k1}")
        v = c.encrypt("Nadia, citizen of Indonesia", "profiles.data")
        self.assertTrue(v.startswith("enc1:k1:"))
        self.assertNotIn("Nadia", v)
        self.assertEqual(c.decrypt(v, "profiles.data"), "Nadia, citizen of Indonesia")
        with self.assertRaises(CryptoConfigError):   # moved to another column: integrity check fails
            c.decrypt(v, "outcomes.lessons")

    def test_plaintext_from_before_is_still_read(self):
        self.assertEqual(self.cipher(f"k1:{self.k1}").decrypt("plain old note", "status_history.note"), "plain old note")

    def test_rotation_reads_old_key_and_rewraps(self):
        old = self.cipher(f"k1:{self.k1}")
        v = old.encrypt("secret", "outcomes.lessons")
        new = self.cipher(f"k2:{self.k2},k1:{self.k1}")
        self.assertEqual(new.decrypt(v, "outcomes.lessons"), "secret")
        self.assertTrue(new.needs_rewrap(v))
        self.assertTrue(new.encrypt("secret", "outcomes.lessons").startswith("enc1:k2:"))

    def test_production_needs_keys_from_environment(self):
        env = {"SCHOLAR_ENV": "production"}
        with mock.patch.dict(os.environ, env, clear=False):
            for k in ("SCHOLAR_DATA_KEYS", "SCHOLAR_DATA_KEY", "SCHOLAR_LOOKUP_KEY"):
                os.environ.pop(k, None)
            with self.assertRaises(CryptoConfigError):
                FieldCipher.from_env(Path(tempfile.mkdtemp()))


class TestStoreEncryption(unittest.TestCase):
    def test_private_values_are_not_stored_in_clear(self):
        from scholarship_agent import profile as profile_mod, tracker
        d = Path(tempfile.mkdtemp())
        st = Store(d)
        profile_mod.upsert(st, {"name": "Siti Rahmawati", "citizenships": ["ID"]}, "p1")
        aid = tracker.application_id("p1", "opp-1")
        st.x("INSERT INTO applications VALUES (?,?,?,?,?,?,?)", (aid, "p1", "opp-1", "discovered", "t", "t", ""))
        tracker.save_document(st, aid, "sop", "SOP", "My father lost his job in 2024 ...")
        tracker.record_outcome  # noqa: B018 (exists)
        st.close()
        raw = sqlite3.connect(d / "private" / "private.db")
        dump = "\n".join(str(r) for t in ("profiles", "profile_history", "document_versions")
                         for r in raw.execute(f"SELECT * FROM {t}"))
        self.assertNotIn("Siti Rahmawati", dump)
        self.assertNotIn("father lost his job", dump)
        st = Store(d)
        self.assertEqual(st.get_profile("p1").name, "Siti Rahmawati")
        self.assertIn("father lost his job", tracker.documents(st, aid)[0]["content"])

    def test_encrypt_private_rewrites_plaintext_rows(self):
        d = Path(tempfile.mkdtemp())
        st = Store(d)
        st.private.execute("INSERT INTO outcomes VALUES (?,?,?,?)", ("app1", "rejected", "too late with references", "t"))
        st.private.commit()
        out = st.encrypt_private()
        self.assertEqual(out["by_table"].get("outcomes"), 1)
        raw = st.private.execute("SELECT lessons FROM outcomes").fetchone()[0]
        self.assertTrue(raw.startswith("enc1:"))
        self.assertEqual(st.dec(raw, "outcomes", "lessons"), "too late with references")

    def test_lessons_are_per_profile(self):
        from scholarship_agent import tracker
        st = Store(Path(tempfile.mkdtemp()))
        for pid in ("alice", "bob"):
            aid = tracker.application_id(pid, "o1")
            st.x("INSERT INTO applications VALUES (?,?,?,?,?,?,?)", (aid, pid, "o1", "submitted", "t", "t", ""))
            st.x("INSERT INTO outcomes VALUES (?,?,?,?)", (aid, "rejected", st.enc(f"lesson of {pid}", "outcomes", "lessons"), "t"))
        self.assertEqual([r["lessons"] for r in tracker.lessons(st, "alice")], ["lesson of alice"])

    def test_profile_history_is_trimmed(self):
        from scholarship_agent import profile as profile_mod
        st = Store(Path(tempfile.mkdtemp()))
        with mock.patch.dict(os.environ, {"SCHOLAR_PROFILE_HISTORY_KEEP": "3"}):
            for i in range(6):
                profile_mod.upsert(st, {"name": f"N{i}"}, "p")
        self.assertEqual(st.q("SELECT COUNT(*) n FROM profile_history")[0]["n"], 3)


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.st = Store(Path(tempfile.mkdtemp()))
        self.acc = Accounts(self.st)

    def reg(self, email="nadia@example.org", pw=PW):
        return self.acc.register(email, pw, True, True, age_confirmed=True)

    def test_password_hash(self):
        h = hash_password(PW)
        self.assertTrue(h.startswith("scrypt$"))
        self.assertTrue(verify_password(PW, h))
        self.assertFalse(verify_password(PW + "x", h))

    def test_password_policy(self):
        for bad in ("short", "password123", "aaaaaaaaaaaa"):
            with self.assertRaises(ValueError):
                check_password(bad)
        with self.assertRaises(ValueError):
            check_password("nadiaputri-2026!", "nadiaputri@example.org")

    def test_register_login_and_no_email_in_clear(self):
        r = self.reg()
        self.assertEqual(r["user"]["email"], "nadia@example.org")
        self.assertTrue(r["token"])
        raw = self.st.private.execute("SELECT email, email_lookup FROM users").fetchone()
        self.assertNotIn("nadia", raw[0] + raw[1])
        self.assertEqual(self.acc.authenticate(r["token"])["id"], r["user"]["user_id"])
        t2 = self.acc.login("NADIA@example.org ", PW)["token"]
        self.assertTrue(self.acc.authenticate(t2))
        with self.assertRaises(ValueError):   # no second account on the same address
            self.reg()

    def test_registration_needs_consent_and_age(self):
        with self.assertRaises(ValueError):
            self.acc.register("a@example.org", PW, True, False, age_confirmed=True)
        with self.assertRaises(ValueError):
            self.acc.register("a@example.org", PW, True, True, age_confirmed=False)

    def test_wrong_password_and_lockout(self):
        self.reg()
        for _ in range(5):
            with self.assertRaises(AuthError):
                self.acc.login("nadia@example.org", "wrong password here")
        with self.assertRaises(AuthError) as e:   # locked even with the right password
            self.acc.login("nadia@example.org", PW)
        self.assertIn("try again later", str(e.exception))
        with self.assertRaises(AuthError) as e2:
            self.acc.login("nobody@example.org", PW)
        self.assertEqual(str(e2.exception), "the e-mail or password is wrong")

    def test_logout_expiry_and_password_change_end_sessions(self):
        r = self.reg()
        self.acc.logout(r["token"])
        with self.assertRaises(AuthError):
            self.acc.authenticate(r["token"])
        t = self.acc.login("nadia@example.org", PW)["token"]
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        self.st.x("UPDATE auth_tokens SET last_used_at = ?", (old,))
        with self.assertRaises(AuthError):   # idle for more than 7 days
            self.acc.authenticate(t)
        t = self.acc.login("nadia@example.org", PW)["token"]
        u = self.acc.authenticate(t)
        new = self.acc.change_password(u, PW, "another long passphrase 42")
        with self.assertRaises(AuthError):
            self.acc.authenticate(t)
        self.assertTrue(self.acc.authenticate(new["token"]))

    def test_password_reset_with_a_mailer(self):
        sent = []

        class FakeMailer:
            def send(self, to, subject, body):
                sent.append((to, body))

        r = self.reg()
        same = self.acc.request_reset("nobody@example.org", FakeMailer())
        self.assertEqual(sent, [])
        self.assertEqual(self.acc.request_reset("nadia@example.org", FakeMailer()), same)
        code = sent[0][1].split("Reset code: ")[1].split()[0]
        with self.assertRaises(AuthError):
            self.acc.confirm_reset("wrong-code", "a new long passphrase 9")
        tok = self.acc.confirm_reset(code, "a new long passphrase 9")
        self.assertTrue(self.acc.authenticate(tok["token"]))
        with self.assertRaises(AuthError):   # the old session ended, the code works once
            self.acc.authenticate(r["token"])
        with self.assertRaises(AuthError):
            self.acc.confirm_reset(code, "yet another passphrase 7")
        self.assertTrue(self.acc.login("nadia@example.org", "a new long passphrase 9")["token"])

    def test_export_and_delete_account(self):
        from scholarship_agent import profile as profile_mod
        r = self.reg()
        u = self.acc.authenticate(r["token"])
        profile_mod.upsert(self.st, {"name": "Nadia"}, u["profile_id"])
        ex = self.acc.export(u)
        self.assertEqual(ex["profile"]["name"], "Nadia")
        self.assertEqual(ex["account"]["email"], "nadia@example.org")
        with self.assertRaises(AuthError):
            self.acc.delete(u, "not the password")
        counts = self.acc.delete(u, PW)
        self.assertEqual(counts["users"], 1)
        self.assertEqual(counts["profiles"], 1)
        self.assertEqual(self.st.q("SELECT COUNT(*) n FROM auth_tokens")[0]["n"], 0)
        with self.assertRaises(AuthError):
            self.acc.authenticate(r["token"])


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scholarship_agent.web import make_handler
        from http.server import ThreadingHTTPServer
        cls.dir = Path(tempfile.mkdtemp())
        Store(cls.dir).close()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.dir, quiet=True))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}/api/v1"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, token=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"{}"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), dict(e.headers)

    def register(self, email):
        s, b, _ = self.call("POST", "/auth/register", {"email": email, "password": PW, "accept_terms": True,
                                                       "accept_privacy": True, "age_confirmed": True})
        self.assertEqual(s, 201, b)
        return b["token"]

    def test_health_and_security_headers(self):
        s, b, h = self.call("GET", "/health")
        self.assertEqual(s, 200)
        self.assertTrue(b["encryption_at_rest"])
        self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(h.get("Cache-Control"), "no-store")

    def test_private_routes_need_login(self):
        for path in ("/profile", "/account", "/applications", "/ranking", "/account/export"):
            s, b, _ = self.call("GET", path)
            self.assertEqual(s, 401, path)
        s, _, _ = self.call("GET", "/profile", token="made-up-token")
        self.assertEqual(s, 401)

    def test_users_only_see_their_own_profile(self):
        ta, tb = self.register("a-user@example.org"), self.register("b-user@example.org")
        s, b, _ = self.call("PATCH", "/profile", {"name": "Ayu", "citizenships": ["ID"]}, ta)
        self.assertEqual(s, 200, b)
        s, b, _ = self.call("GET", "/profile", token=tb)
        self.assertIsNone(b["profile"])   # B has no profile yet and never sees A's
        s, b, _ = self.call("GET", "/profile", token=ta)
        self.assertEqual(b["profile"]["name"], "Ayu")
        s, b, _ = self.call("PATCH", "/profile", {"id": "someone-else", "name": "X"}, tb)
        self.assertEqual(s, 200)
        s, b, _ = self.call("GET", "/profile", token=ta)
        self.assertEqual(b["profile"]["name"], "Ayu")
        s, b, _ = self.call("GET", "/account/export", token=ta)
        self.assertEqual(b["account"]["email"], "a-user@example.org")
        self.assertEqual(b["profile"]["name"], "Ayu")

    def test_bad_input_and_unknown_routes(self):
        s, b, _ = self.call("GET", "/nothing-here")
        self.assertEqual(s, 404)
        s, b, _ = self.call("DELETE", "/health")
        self.assertEqual(s, 405)
        req = urllib.request.Request(self.base + "/auth/login", data=b"{not json", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
        s, b, _ = self.call("POST", "/auth/login", {"email": "x@example.org", "password": "whatever-it-is"})
        self.assertEqual(s, 401)
        self.assertNotIn("Traceback", json.dumps(b))

    def test_delete_account_through_api(self):
        t = self.register("c-user@example.org")
        s, b, _ = self.call("DELETE", "/account", {"password": PW}, t)
        self.assertEqual(s, 200, b)
        self.assertEqual(b["deleted"]["users"], 1)
        s, _, _ = self.call("GET", "/account", token=t)
        self.assertEqual(s, 401)

    def test_login_rate_limit(self):
        # its own server, so the other tests keep their allowance
        from http.server import ThreadingHTTPServer
        from scholarship_agent import web
        d = Path(tempfile.mkdtemp())
        Store(d).close()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(d, quiet=True))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/api/v1/auth/login"
            codes = []
            for _ in range(web.LIMITS["auth"][0] + 2):
                req = urllib.request.Request(url, data=json.dumps({"email": "rl@example.org", "password": "wrong-pass-x1"}).encode(),
                                             method="POST", headers={"Content-Type": "application/json"})
                try:
                    urllib.request.urlopen(req, timeout=20)
                except urllib.error.HTTPError as e:
                    codes.append(e.code)
            self.assertIn(429, codes)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()


class TestCycleCheck(unittest.TestCase):
    """Round 46: the second reading also reads the application status; a different status holds the cycle."""
    TODAY = __import__("datetime").date(2026, 10, 21)
    TEXT = ("Example Scholarship\nThe scholarship is open to citizens of Kenya and Uganda.\n"
            "Application deadline: 15 January 2027.")

    def status(self, reading_value, quote="Application deadline: 15 January 2027."):
        from scholarship_agent.ai_check import attach_second_reading
        from scholarship_agent.audit import field_status
        from scholarship_agent.extract import Page, extract_opportunity
        from scholarship_agent.models import ProviderType, SourceType

        class Fake:
            def complete_json(self, system, user, fields=None, meta=None):
                return {"fields": [{"field": "application_status", "value": reading_value, "quote": quote}]}

        o, _ = extract_opportunity(Page("https://example.org/c", self.TEXT), provider_name="x", provider_type=ProviderType.OTHER,
                                   source_type=SourceType.OFFICIAL, country_hint=[], retrieved_at="t", today=self.TODAY)
        base = field_status(o, self.TODAY)["cycle"]["state"]
        with mock.patch.dict(os.environ, {"SCHOLAR_SECOND_READING_STATUS": "1"}):
            attach_second_reading(o, self.TEXT, Fake(), self.TODAY)
        return base, field_status(o, self.TODAY)["cycle"]["state"]

    def test_same_status_keeps_the_cycle(self):
        base, got = self.status("open")
        self.assertEqual(base, "open")
        self.assertEqual(got, "open")

    def test_different_status_holds_the_cycle(self):
        self.assertEqual(self.status("closed")[1], "needs_review")

    def test_silence_holds_the_cycle(self):
        self.assertEqual(self.status("not_stated", quote="")[1], "needs_review")

    def test_a_status_quote_not_on_the_page_holds_nothing(self):
        self.assertEqual(self.status("closed", quote="applications closed last year")[1], "open")

    def test_status_is_not_asked_by_default(self):
        from scholarship_agent.ai_check import asked_fields
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCHOLAR_SECOND_READING_STATUS", None)
            self.assertNotIn("application_status", asked_fields())
