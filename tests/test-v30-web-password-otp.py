#!/usr/bin/env python3
"""PF-9 real two-stage Web password -> OTP sign-in, no session until factor."""
from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_web_auth import (
    WebAuthService, WebSessionIssue, WebMfaLoginChallenge,
    totp_code,
)


class PasswordThenOtpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-two-stage-web-")
        self.base = datetime(2026, 10, 9, 0, 0, 0, tzinfo=timezone.utc)
        self.auth = WebAuthService(self.temp.name)
        material = self.auth.prepare_mfa_material("admin")
        self.secret = material["totp_secret"]
        self.recovery_codes = material["recovery_codes"]
        initial, _ = totp_code(self.secret, at=self.base)
        self.admin = self.auth.create_first_admin(
            username="admin", password="ValidPass1",
            totp_secret=self.secret, recovery_codes=self.recovery_codes,
            totp_value=initial, now=self.base,
        )
        self.step = self.base + timedelta(seconds=60)

    def tearDown(self):
        self.auth.close()
        self.temp.cleanup()

    def start(self, **overrides):
        data = dict(
            username="admin", password="ValidPass1",
            source_addr="127.0.0.1", user_agent="fixture-client",
            now=self.step,
        )
        data.update(overrides)
        return self.auth.begin_password_login(**data)

    def finish(self, challenge: WebMfaLoginChallenge, **overrides):
        code, _ = totp_code(self.secret, at=self.step)
        data = dict(
            challenge_token=challenge.challenge_token, totp_value=code,
            source_addr="127.0.0.1", user_agent="fixture-client",
            now=self.step,
        )
        data.update(overrides)
        return self.auth.complete_password_login(**data)

    def test_password_stage_issues_only_ephemeral_challenge_not_a_session(self):
        challenge = self.start()
        self.assertIsInstance(challenge, WebMfaLoginChallenge)
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)
        self.assertNotIn("password", repr(challenge).lower())
        self.assertNotIn(self.secret, repr(challenge))
        self.assertNotIn("session_token", repr(challenge))
        self.assertLessEqual(len(challenge.challenge_token), 128)

    def test_valid_otp_creates_session_only_after_second_stage(self):
        challenge = self.start()
        session = self.finish(challenge)
        self.assertIsInstance(session, WebSessionIssue)
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 1)
        self.assertIsNotNone(self.auth.validate_session(
            session.session_token, now=self.step + timedelta(seconds=1)
        ))
        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.finish(challenge)

    def test_invalid_otp_consumes_challenge_and_never_creates_session(self):
        challenge = self.start()
        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.finish(challenge, totp_value="000000")
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)
        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.finish(challenge)

    def test_otp_replay_rejected_across_separate_password_challenges(self):
        first = self.start()
        second = self.start()
        self.finish(first)
        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.finish(second)
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 1)

    def test_source_and_user_agent_mismatch_rejected_without_session(self):
        for changed in (dict(source_addr="203.0.113.10"), dict(user_agent="different-browser")):
            challenge = self.start()
            with self.assertRaises(ControlPlaneError):
                self.finish(challenge, **changed)
            self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)

    def test_password_or_role_revision_change_invalidates_pre_auth(self):
        for query in (
            "UPDATE web_operators SET row_version=row_version+1 WHERE username='admin'",
            "UPDATE web_operators SET role='Operator',row_version=row_version+1 WHERE username='admin'",
        ):
            challenge = self.start()
            self.auth.conn.execute(query)
            with self.assertRaises(ControlPlaneError):
                self.finish(challenge)
            self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)

    def test_disabling_account_between_factors_rejects_challenge(self):
        challenge = self.start()
        self.auth.conn.execute("UPDATE web_operators SET enabled=0 WHERE username='admin'")
        with self.assertRaises(ControlPlaneError):
            self.finish(challenge)
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)

    def test_bounded_expiration_without_host_sleep(self):
        with patch("drlink_web_auth.time.monotonic", return_value=100.0):
            challenge = self.start()
        with patch("drlink_web_auth.time.monotonic", return_value=400.0):
            with self.assertRaises(ControlPlaneError):
                self.finish(challenge)
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)

    def test_recovery_code_is_consumed_atomically_only_once(self):
        challenge = self.start()
        session = self.finish(challenge, totp_value="", recovery_code=self.recovery_codes[0])
        self.assertIsInstance(session, WebSessionIssue)
        new_challenge = self.start()
        with self.assertRaises(ControlPlaneError):
            self.finish(new_challenge, totp_value="", recovery_code=self.recovery_codes[0])

    def test_cancel_is_idempotent_and_no_session_created(self):
        challenge = self.start()
        self.assertTrue(self.auth.cancel_password_login(challenge.challenge_token))
        self.assertFalse(self.auth.cancel_password_login(challenge.challenge_token))
        with self.assertRaises(ControlPlaneError):
            self.finish(challenge)
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)

    def test_default_off_user_gets_session_after_password_without_otp(self):
        other = self.auth.create_operator_local(
            username="viewer", role="Read Only", password="ReaderPass1",
            now=self.base,
        )
        session = self.auth.begin_password_login(
            username="viewer", password="ReaderPass1",
            source_addr="127.0.0.1", user_agent="fixture-client", now=self.step,
        )
        self.assertIsInstance(session, WebSessionIssue)
        self.assertEqual(session.principal.role, "Read Only")
        self.assertTrue(other["mfa_required"] is False)

    def test_new_password_stage_cannot_clear_failed_otp_rate_limit(self):
        # An attacker who knows only the password must not get unbounded
        # OTP attempts by requesting another password challenge each time.
        for _ in range(5):
            pending = self.start()
            with self.assertRaises(ControlPlaneError):
                self.finish(pending, totp_value="invalid")
        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.start()
        self.assertEqual(self.auth.conn.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0], 0)

    def test_wrong_password_never_returns_challenge_or_session(self):
        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.start(password="not-valid")
        self.assertEqual(self.auth.conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
