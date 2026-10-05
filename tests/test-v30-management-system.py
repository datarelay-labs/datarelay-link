from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_mcp_tls as mcp_tls
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from drlink_management_core import (
    ManagementActor,
    ManagementAuthorizationError,
    ManagementCoreService,
)
from drlink_management_system import ManagementSystemService


class V30ManagementSystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-system-")
        root = Path(self.tmp)
        (root / "etc/drlink").mkdir(parents=True, exist_ok=True)
        (root / "var/lib/drlink/backups").mkdir(parents=True, exist_ok=True)
        (root / "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\n"
            "FRP_VERSION=0.71.0\n"
            "RELEASE_CHANNEL=development\n"
            "SOURCE_REF=0123456789abcdef0123456789abcdef01234567\n"
            "SOURCE_HEAD=0123456789abcdef0123456789abcdef01234567\n"
            "BUNDLE_SHA256=" + ("a" * 64) + "\n",
            encoding="utf-8",
        )
        plane = ControlPlane(self.tmp)
        plane.close()

    def test_system_status_is_read_only_and_certificate_view_is_redacted(self):
        service = ManagementSystemService(self.tmp)
        status = service.status()
        self.assertTrue(status["read_only"])
        self.assertTrue(status["side_effect_free"])
        self.assertEqual(status["identity"]["project_version"], "3.0.0")
        self.assertEqual(status["identity"]["relay_engine_version"], "0.71.0")
        self.assertEqual(status["identity"]["channel"], "development")
        self.assertNotIn("raw", status["certificate"])
        self.assertNotIn("active_key_path", status["certificate"])
        self.assertNotIn("active_cert_path", status["certificate"])
        self.assertTrue(status["backup"]["directory_present"])
        self.assertTrue(status["backup"]["validate_available"])

    def test_certificate_preflight_uses_configured_hostname_without_mutation(self):
        plane = ControlPlane(self.tmp)
        try:
            revision = plane.current_revision()
            state = mcp_tls.default_state()
            state["hostname"] = "mcp.example.test"
            state["mode"] = mcp_tls.MODE_PRIVATE_CA
            mcp_tls.save_state(plane, state)
        finally:
            plane.close()
        expected = {
            "hostname": "mcp.example.test",
            "resolves": True,
            "addresses": ["203.0.113.5"],
            "private_only": False,
            "challenge_port_80_open": None,
            "ok": True,
            "warnings": [],
            "errors": [],
        }
        with mock.patch(
            "drlink_management_system.mcp_tls.preflight_hostname",
            return_value=expected,
        ) as preflight:
            result = ManagementSystemService(self.tmp).certificate_preflight()
        preflight.assert_called_once_with(
            "mcp.example.test", require_public_dns=False
        )
        self.assertEqual(result["mode"], mcp_tls.MODE_PRIVATE_CA)
        self.assertFalse(result["authoritative_mutation"])
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision)
        finally:
            plane.close()

    def test_backup_validate_delegates_to_canonical_restore_validator(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Backup valid.\n", stderr=""
        )
        with mock.patch(
            "drlink_management_system.subprocess.run", return_value=completed
        ) as run:
            result = ManagementSystemService(self.tmp).backup_validate(
                "/var/lib/drlink/backups/test.tar.gz"
            )
        self.assertTrue(result["valid"])
        self.assertFalse(result["authoritative_mutation"])
        command = run.call_args.args[0]
        self.assertIn("--validate", command)
        self.assertEqual(
            command[-1],
            str(Path(self.tmp, "var/lib/drlink/backups/test.tar.gz").resolve()),
        )
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["FRP_DEPLOY_TEST_ROOT"], self.tmp)
        self.assertNotIn("DRLINK_CONFIRM", env)
        self.assertNotIn("FRP_RESTORE_YES", env)

    def test_backup_validate_rejects_paths_outside_canonical_backup_directory(self):
        service = ManagementSystemService(self.tmp)
        for path in (
            "/etc/passwd",
            "/var/lib/drlink/backups/../../etc/passwd",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(
                    ControlPlaneError, "/var/lib/drlink/backups/"
                ):
                    service.backup_validate(path)

    def test_core_role_and_permission_guard(self):
        core = ManagementCoreService(self.tmp)
        reader = ManagementActor.authenticated(
            "web:reader",
            {"management-read", "management-diagnose"},
            role="Read Only",
        )
        self.assertTrue(core.system_status(actor=reader)["read_only"])
        denied = ManagementActor.authenticated(
            "web:denied", {"management-read"}, role="Read Only"
        )
        with self.assertRaises(ManagementAuthorizationError):
            core.certificate_preflight(actor=denied)


if __name__ == "__main__":
    unittest.main()
