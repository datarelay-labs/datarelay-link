#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_web_auth import (
    ROLE_OPERATOR,
    WebAuthService,
    WebMfaEnrollmentChallenge,
    WebSessionIssue,
    totp_code,
)
from drlink_web_service import WebApplication


class V30WebMfaPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-mfa-policy-")
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
        self.auth = WebAuthService(self.tmp)
        self.admin = self.auth.create_first_admin(
            username="admin",
            password="ValidPass1",
            now=self.now,
        )

    def tearDown(self):
        self.auth.close()

    def test_mfa_defaults_off_then_admin_enable_requires_self_enrollment(self):
        row = self.auth.conn.execute(
            "SELECT mfa_required,mfa_enrolled FROM web_operators WHERE id=?",
            (self.admin["operator_id"],),
        ).fetchone()
        self.assertEqual((row["mfa_required"], row["mfa_enrolled"]), (0, 0))

        initial = self.auth.authenticate(
            username="admin",
            password="ValidPass1",
            now=self.now,
        )
        self.assertIsInstance(initial, WebSessionIssue)

        changed = self.auth.set_operator_mfa_required(
            self.admin["operator_id"], required=True, actor_id=self.admin["operator_id"]
        )
        self.assertTrue(changed["mfa_required"])
        self.assertFalse(changed["mfa_enrolled"])
        self.assertGreaterEqual(changed["sessions_revoked"], 1)

        challenge = self.auth.authenticate(
            username="admin",
            password="ValidPass1",
            now=self.now + timedelta(seconds=1),
        )
        self.assertIsInstance(challenge, WebMfaEnrollmentChallenge)
        self.assertTrue(challenge.totp_secret)
        self.assertIn("otpauth://totp/", challenge.otpauth_uri)

        code, _ = totp_code(challenge.totp_secret, at=self.now + timedelta(seconds=1))
        issued, recovery_codes = self.auth.confirm_mfa_enrollment(
            enrollment_token=challenge.enrollment_token,
            totp_value=code,
            now=self.now + timedelta(seconds=1),
        )
        self.assertIsInstance(issued, WebSessionIssue)
        self.assertEqual(len(recovery_codes), 10)
        row = self.auth.conn.execute(
            "SELECT mfa_required,mfa_enrolled FROM web_operators WHERE id=?",
            (self.admin["operator_id"],),
        ).fetchone()
        self.assertEqual((row["mfa_required"], row["mfa_enrolled"]), (1, 1))

        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.auth.authenticate(
                username="admin",
                password="ValidPass1",
                now=self.now + timedelta(seconds=31),
            )
        next_code, _ = totp_code(challenge.totp_secret, at=self.now + timedelta(seconds=31))
        self.assertIsInstance(
            self.auth.authenticate(
                username="admin",
                password="ValidPass1",
                totp_value=next_code,
                now=self.now + timedelta(seconds=31),
            ),
            WebSessionIssue,
        )

        disabled = self.auth.set_operator_mfa_required(
            self.admin["operator_id"], required=False, actor_id=self.admin["operator_id"]
        )
        self.assertFalse(disabled["mfa_required"])
        row = self.auth.conn.execute(
            "SELECT mfa_required,mfa_enrolled,mfa_secret_ciphertext "
            "FROM web_operators WHERE id=?",
            (self.admin["operator_id"],),
        ).fetchone()
        self.assertEqual((row["mfa_required"], row["mfa_enrolled"]), (0, 0))
        self.assertEqual(row["mfa_secret_ciphertext"], "")
        self.assertIsInstance(
            self.auth.authenticate(
                username="admin",
                password="ValidPass1",
                now=self.now + timedelta(seconds=61),
            ),
            WebSessionIssue,
        )

    def test_cancelled_mfa_enrollment_discards_temporary_secret(self):
        self.auth.set_operator_mfa_required(
            self.admin["operator_id"], required=True, actor_id=self.admin["operator_id"]
        )
        challenge = self.auth.authenticate(
            username="admin", password="ValidPass1", now=self.now
        )
        self.assertIsInstance(challenge, WebMfaEnrollmentChallenge)
        code, _ = totp_code(challenge.totp_secret, at=self.now)
        self.assertTrue(self.auth.cancel_mfa_enrollment(challenge.enrollment_token))
        self.assertFalse(self.auth.cancel_mfa_enrollment(challenge.enrollment_token))
        with self.assertRaisesRegex(ControlPlaneError, "expired"):
            self.auth.confirm_mfa_enrollment(
                enrollment_token=challenge.enrollment_token,
                totp_value=code,
                now=self.now,
            )
        replacement = self.auth.authenticate(
            username="admin", password="ValidPass1", now=self.now + timedelta(seconds=1)
        )
        self.assertIsInstance(replacement, WebMfaEnrollmentChallenge)
        self.assertNotEqual(replacement.totp_secret, challenge.totp_secret)

    def test_local_recovery_preserves_default_off_mfa_policy(self):
        session = self.auth.authenticate(
            username="admin",
            password="ValidPass1",
            now=self.now,
        )
        result = self.auth.recover_admin(
            username="admin",
            new_password="new ValidPass1",
            now=self.now + timedelta(seconds=1),
        )
        self.assertTrue(result["recovered"])
        self.assertFalse(result["mfa_required"])
        self.assertFalse(result["mfa_enrolled"])
        self.assertIsNone(
            self.auth.validate_session(
                session.session_token, now=self.now + timedelta(seconds=2)
            )
        )
        self.assertIsInstance(
            self.auth.authenticate(
                username="admin",
                password="new ValidPass1",
                now=self.now + timedelta(seconds=3),
            ),
            WebSessionIssue,
        )

    def test_admin_api_creates_local_operator_with_mfa_off_and_role_boundary(self):
        admin_session = self.auth.authenticate(
            username="admin", password="ValidPass1", now=self.now
        )
        self.auth.close()
        app = WebApplication(self.tmp, static_root=str(ROOT / "web/dist"))
        try:
            created = app.write_api(
                "/api/v1/operators",
                {"username": "reader", "password": "ReaderPass1", "role": "Read Only"},
                admin_session.principal,
            )
            self.assertEqual(created["role"], "Read Only")
            self.assertFalse(created["mfa_required"])
            reader = app.auth.authenticate(
                username="reader", password="ReaderPass1", now=self.now + timedelta(seconds=1)
            )
            with self.assertRaisesRegex(ControlPlaneError, "Admin role"):
                app.write_api(
                    "/api/v1/operators",
                    {"username": "blocked", "password": "BlockedPass1", "role": "Operator"},
                    reader.principal,
                )
        finally:
            app.close()
        self.auth = WebAuthService(self.tmp)

    def test_additional_operator_defaults_mfa_off_and_admin_api_controls_it(self):
        operator = self.auth.create_operator_local(
            username="operator",
            role=ROLE_OPERATOR,
            password="another ValidPass1",
            now=self.now,
        )
        self.assertFalse(operator["mfa_required"])
        admin_session = self.auth.authenticate(
            username="admin",
            password="ValidPass1",
            now=self.now,
        )
        operator_session = self.auth.authenticate(
            username="operator",
            password="another ValidPass1",
            now=self.now,
        )
        self.auth.close()

        app = WebApplication(self.tmp, static_root=str(ROOT / "web/dist"))
        try:
            with self.assertRaisesRegex(ControlPlaneError, "Admin role"):
                app.read_api("/api/v1/operators", {}, operator_session.principal)
            with self.assertRaisesRegex(ControlPlaneError, "Admin role"):
                app.write_api(
                    "/api/v1/operators/%s/mfa" % operator["operator_id"],
                    {"required": True},
                    operator_session.principal,
                )
            users = app.read_api("/api/v1/operators", {}, admin_session.principal)
            item = next(x for x in users["items"] if x["id"] == operator["operator_id"])
            self.assertFalse(item["mfa_required"])
            result = app.write_api(
                "/api/v1/operators/%s/mfa" % operator["operator_id"],
                {"required": True},
                admin_session.principal,
            )
            self.assertTrue(result["mfa_required"])
            users = app.read_api("/api/v1/operators", {}, admin_session.principal)
            item = next(x for x in users["items"] if x["id"] == operator["operator_id"])
            self.assertTrue(item["mfa_required"])
            self.assertFalse(item["mfa_enrolled"])
        finally:
            app.close()
        self.auth = WebAuthService(self.tmp)


if __name__ == "__main__":
    unittest.main()
