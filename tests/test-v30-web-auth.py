#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError, open_control_db
from drlink_web_auth import (
    LOGIN_MAX_FAILURES,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_READ_ONLY,
    SESSION_IDLE_SECONDS,
    SESSION_LIFETIME_SECONDS,
    WebAuthService,
    _master_key_path,
    permissions_for_role,
    totp_code,
)


class V30WebAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-web-auth-")
        self.base = datetime(2026, 10, 4, 3, 0, 0, tzinfo=timezone.utc)
        self.auth = WebAuthService(self.tmp)
        self.material = self.auth.prepare_mfa_material("admin")
        code, _ = totp_code(self.material["totp_secret"], at=self.base)
        self.admin = self.auth.create_first_admin(
            username="admin",
            password="correct horse battery staple",
            totp_secret=self.material["totp_secret"],
            recovery_codes=self.material["recovery_codes"],
            totp_value=code,
            now=self.base,
        )

    def tearDown(self):
        self.auth.close()

    def _login_totp(self, *, seconds=30, password="correct horse battery staple"):
        at = self.base + timedelta(seconds=seconds)
        code, _ = totp_code(self.material["totp_secret"], at=at)
        return self.auth.authenticate(
            username="admin",
            password=password,
            totp_value=code,
            source_addr="127.0.0.1",
            user_agent="test-browser",
            now=at,
        )

    def test_schema_and_first_admin_bootstrap_are_core_owned(self):
        self.assertEqual(self.admin["role"], ROLE_ADMIN)
        self.assertTrue(self.admin["recovery_admin"])
        tables = {
            row[0]
            for row in self.auth.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("web_operators", tables)
        self.assertIn("web_recovery_codes", tables)
        self.assertIn("web_sessions", tables)
        self.assertIn("web_saved_views", tables)
        with self.assertRaises(ControlPlaneError):
            self.auth.create_first_admin(
                username="admin2",
                password="another correct horse password",
                totp_secret=self.material["totp_secret"],
                recovery_codes=self.material["recovery_codes"],
                totp_value=totp_code(
                    self.material["totp_secret"], at=self.base + timedelta(seconds=30)
                )[0],
                now=self.base + timedelta(seconds=30),
            )

    def test_plaintext_password_mfa_and_recovery_codes_are_not_in_database(self):
        db_bytes = Path(self.tmp, "var/lib/drlink/drlink.db").read_bytes()
        self.assertNotIn(b"correct horse battery staple", db_bytes)
        self.assertNotIn(self.material["totp_secret"].encode("ascii"), db_bytes)
        for code in self.material["recovery_codes"]:
            self.assertNotIn(code.encode("ascii"), db_bytes)
        key_path = _master_key_path(self.tmp)
        self.assertTrue(key_path.is_file())
        self.assertEqual(stat.S_IMODE(key_path.stat().st_mode), 0o600)

    def test_totp_login_session_csrf_idle_and_revocation(self):
        issued = self._login_totp(seconds=30)
        principal = self.auth.validate_session(
            issued.session_token,
            now=self.base + timedelta(seconds=31),
        )
        self.assertIsNotNone(principal)
        self.assertEqual(principal.username, "admin")
        self.assertEqual(principal.role, ROLE_ADMIN)

        self.assertIsNone(
            self.auth.validate_session(
                issued.session_token,
                csrf_token="wrong",
                require_csrf=True,
                now=self.base + timedelta(seconds=31),
            )
        )
        self.assertIsNotNone(
            self.auth.validate_session(
                issued.session_token,
                csrf_token=issued.csrf_token,
                require_csrf=True,
                now=self.base + timedelta(seconds=31),
            )
        )

        self.assertTrue(
            self.auth.revoke_session(
                issued.session_id, actor_id=principal.operator_id
            )
        )
        self.assertIsNone(
            self.auth.validate_session(
                issued.session_token,
                now=self.base + timedelta(seconds=32),
            )
        )

    def test_session_absolute_and_idle_limits(self):
        issued = self._login_totp(seconds=30)
        self.assertIsNone(
            self.auth.validate_session(
                issued.session_token,
                now=self.base
                + timedelta(seconds=30 + SESSION_IDLE_SECONDS + 1),
            )
        )

        # New session; keep it active inside idle window, then absolute lifetime wins.
        issued2 = self._login_totp(seconds=60)
        cursor = self.base + timedelta(seconds=60)
        for _ in range(1, 16):
            cursor += timedelta(seconds=SESSION_IDLE_SECONDS - 60)
            if cursor >= self.base + timedelta(seconds=60 + SESSION_LIFETIME_SECONDS):
                break
            self.assertIsNotNone(
                self.auth.validate_session(issued2.session_token, now=cursor)
            )
        self.assertIsNone(
            self.auth.validate_session(
                issued2.session_token,
                now=self.base
                + timedelta(seconds=60 + SESSION_LIFETIME_SECONDS + 1),
            )
        )

    def test_totp_replay_and_recovery_code_one_time_use(self):
        issued = self._login_totp(seconds=30)
        self.assertIsNotNone(issued)
        code, _ = totp_code(
            self.material["totp_secret"], at=self.base + timedelta(seconds=30)
        )
        with self.assertRaises(ControlPlaneError):
            self.auth.authenticate(
                username="admin",
                password="correct horse battery staple",
                totp_value=code,
                source_addr="127.0.0.2",
                now=self.base + timedelta(seconds=31),
            )

        recovery = self.material["recovery_codes"][0]
        recovered = self.auth.authenticate(
            username="admin",
            password="correct horse battery staple",
            recovery_code=recovery,
            source_addr="127.0.0.3",
            now=self.base + timedelta(seconds=35),
        )
        self.assertIsNotNone(recovered)
        with self.assertRaises(ControlPlaneError):
            self.auth.authenticate(
                username="admin",
                password="correct horse battery staple",
                recovery_code=recovery,
                source_addr="127.0.0.4",
                now=self.base + timedelta(seconds=36),
            )

    def test_local_recovery_resets_password_mfa_and_revokes_sessions(self):
        issued = self._login_totp(seconds=30)
        material = self.auth.prepare_mfa_material("admin")
        at = self.base + timedelta(minutes=2)
        code, _ = totp_code(material["totp_secret"], at=at)
        result = self.auth.recover_admin(
            username="admin",
            new_password="new correct horse battery staple",
            totp_secret=material["totp_secret"],
            recovery_codes=material["recovery_codes"],
            totp_value=code,
            now=at,
        )
        self.assertTrue(result["recovered"])
        self.assertIsNone(
            self.auth.validate_session(
                issued.session_token, now=at + timedelta(seconds=1)
            )
        )

        next_at = at + timedelta(seconds=30)
        new_code, _ = totp_code(material["totp_secret"], at=next_at)
        new_session = self.auth.authenticate(
            username="admin",
            password="new correct horse battery staple",
            totp_value=new_code,
            source_addr="127.0.0.1",
            now=next_at,
        )
        self.assertIsNotNone(new_session)
        with self.assertRaises(ControlPlaneError):
            self.auth.authenticate(
                username="admin",
                password="correct horse battery staple",
                recovery_code=material["recovery_codes"][1],
                source_addr="127.0.0.8",
                now=next_at + timedelta(seconds=1),
            )

    def test_roles_map_to_management_permissions_without_target_os_permissions(self):
        read = permissions_for_role(ROLE_READ_ONLY)
        operator = permissions_for_role(ROLE_OPERATOR)
        admin = permissions_for_role(ROLE_ADMIN)
        self.assertIn("management-read", read)
        self.assertNotIn("management-temporary-access", read)
        self.assertIn("management-temporary-access", operator)
        self.assertNotIn("management-recovery", read)
        self.assertNotIn("management-recovery", operator)
        self.assertIn("management-emergency-cutoff", admin)
        self.assertIn("management-recovery", admin)
        for permissions in (read, operator, admin):
            self.assertNotIn("command-exec", permissions)
            self.assertNotIn("file-write", permissions)

    def test_additional_operator_roles_authenticate_with_distinct_permissions(self):
        for offset, role in enumerate((ROLE_OPERATOR, ROLE_READ_ONLY), start=4):
            username = "user%d" % offset
            material = self.auth.prepare_mfa_material(username)
            at = self.base + timedelta(minutes=offset)
            code, _ = totp_code(material["totp_secret"], at=at)
            created = self.auth.create_operator_local(
                username=username,
                role=role,
                password="role specific correct horse password",
                totp_secret=material["totp_secret"],
                recovery_codes=material["recovery_codes"],
                totp_value=code,
                now=at,
            )
            self.assertEqual(created["role"], role)
            login_at = at + timedelta(seconds=30)
            next_code, _ = totp_code(material["totp_secret"], at=login_at)
            issued = self.auth.authenticate(
                username=username,
                password="role specific correct horse password",
                totp_value=next_code,
                source_addr="127.0.0.%d" % offset,
                now=login_at,
            )
            self.assertEqual(issued.principal.role, role)
            if role == ROLE_READ_ONLY:
                self.assertNotIn("management-temporary-access", issued.principal.permissions)
            else:
                self.assertIn("management-temporary-access", issued.principal.permissions)

    def test_login_rate_limit_is_bounded_and_generic(self):
        for _ in range(LOGIN_MAX_FAILURES):
            with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
                self.auth.authenticate(
                    username="admin",
                    password="wrong-password-is-long-enough",
                    totp_value="000000",
                    source_addr="203.0.113.10",
                    now=self.base + timedelta(seconds=30),
                )
        with self.assertRaisesRegex(ControlPlaneError, "Invalid credentials or MFA"):
            self.auth.authenticate(
                username="admin",
                password="correct horse battery staple",
                totp_value=totp_code(
                    self.material["totp_secret"],
                    at=self.base + timedelta(seconds=30),
                )[0],
                source_addr="203.0.113.10",
                now=self.base + timedelta(seconds=30),
            )

    def test_saved_views_are_nonsecurity_operator_preferences(self):
        operator_id = self.admin["operator_id"]
        saved = self.auth.save_view(
            operator_id,
            name="Offline Hosts",
            payload={"resource_type": "managed-host", "filter": "offline"},
        )
        self.assertTrue(saved["id"].startswith("wsv_"))
        views = self.auth.list_saved_views(operator_id)
        self.assertEqual(len(views), 1)
        self.assertEqual(views[0]["name"], "Offline Hosts")
        self.assertEqual(views[0]["payload"]["filter"], "offline")
        with self.assertRaises(ControlPlaneError):
            self.auth.save_view(
                operator_id,
                name="too-large",
                payload={"blob": "x" * 9000},
            )

    def test_security_lifecycle_events_do_not_create_configuration_revision(self):
        before = self.auth.conn.execute(
            "SELECT COALESCE(MAX(revision),0) FROM config_revisions"
        ).fetchone()[0]
        self._login_totp(seconds=30)
        after = self.auth.conn.execute(
            "SELECT COALESCE(MAX(revision),0) FROM config_revisions"
        ).fetchone()[0]
        self.assertEqual(before, after)
        events = self.auth.conn.execute(
            "SELECT event_type,result FROM audit_events "
            "WHERE category='SECURITY_LIFECYCLE' ORDER BY id"
        ).fetchall()
        names = [row["event_type"] for row in events]
        self.assertIn("web.operator.bootstrap", names)
        self.assertIn("web.login.succeeded", names)


if __name__ == "__main__":
    unittest.main()
