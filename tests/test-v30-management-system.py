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

    def test_certificate_renew_reuses_canonical_lifecycle_and_redacts_response(self):
        plane = ControlPlane(self.tmp)
        try:
            state = mcp_tls.default_state()
            state["hostname"] = "mcp.example.test"
            state["mode"] = mcp_tls.MODE_PRIVATE_CA
            state["renewal_enabled"] = True
            mcp_tls.save_state(plane, state)
            revision = plane.current_revision()
        finally:
            plane.close()

        status_view = {
            "hostname": "mcp.example.test",
            "mode": mcp_tls.MODE_PRIVATE_CA,
            "certificate": "VALID",
            "fingerprint_sha256": "abc",
            "raw": {"private_key": "must-not-leak"},
            "active_key_path": "/secret/key",
        }
        with mock.patch(
            "drlink_management_system.mcp_tls.require_public_frontend"
        ) as frontend, mock.patch(
            "drlink_management_system.mcp_tls.renew_if_due",
            return_value={"renewed": False, "reason": "not_due", "state": state},
        ) as renew, mock.patch(
            "drlink_management_system.mcp_tls.status_view",
            return_value=status_view,
        ):
            result = ManagementSystemService(self.tmp).certificate_renew(
                actor_id="web:admin"
            )

        frontend.assert_called_once_with(self.tmp)
        renew.assert_called_once()
        self.assertFalse(result["renewed"])
        self.assertEqual(result["reason"], "not_due")
        self.assertFalse(result["authoritative_mutation"])
        self.assertNotIn("raw", result["certificate"])
        self.assertNotIn("active_key_path", result["certificate"])

        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision)
            audit = plane.conn.execute(
                "SELECT actor_id,interface,action,result FROM audit_events "
                "WHERE entity_type='certificate' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(audit["actor_id"], "web:admin")
            self.assertEqual(audit["interface"], "WEB")
            self.assertEqual(audit["action"], "web certificate renew")
            self.assertEqual(audit["result"], "ok")
        finally:
            plane.close()

    def test_certificate_renew_reports_failed_attempt_as_state_mutation(self):
        plane = ControlPlane(self.tmp)
        try:
            state = mcp_tls.default_state()
            state["hostname"] = "mcp.example.test"
            state["mode"] = mcp_tls.MODE_PRIVATE_CA
            mcp_tls.save_state(plane, state)
        finally:
            plane.close()
        with mock.patch(
            "drlink_management_system.mcp_tls.require_public_frontend"
        ), mock.patch(
            "drlink_management_system.mcp_tls.renew_if_due",
            return_value={
                "renewed": False,
                "reason": "failed",
                "failure_class": "TLS_TEST_FAILURE",
                "state": state,
            },
        ), mock.patch(
            "drlink_management_system.mcp_tls.status_view",
            return_value={"hostname": "mcp.example.test", "certificate": "RENEWAL_FAILED"},
        ):
            result = ManagementSystemService(self.tmp).certificate_renew(
                actor_id="web:admin"
            )
        self.assertFalse(result["renewed"])
        self.assertTrue(result["authoritative_mutation"])
        self.assertEqual(result["failure_class"], "TLS_TEST_FAILURE")

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

    def test_restore_requires_confirmation_revalidates_and_uses_canonical_recovery(self):
        service = ManagementSystemService(self.tmp)
        with self.assertRaisesRegex(ControlPlaneError, "confirmation"):
            service.restore_apply(
                "/var/lib/drlink/backups/test.tar.gz",
                actor_id="web:admin",
                confirmation="",
            )

        calls = []

        def fake_run(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            if "--validate" in command:
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout="Backup valid.\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=(
                    "Restore completed. Pre-restore snapshot: "
                    "server-backup-pre-restore.tar.gz (VALIDATED)\n"
                ),
                stderr="",
            )

        with mock.patch(
            "drlink_management_system.subprocess.run", side_effect=fake_run
        ):
            result = service.restore_apply(
                "/var/lib/drlink/backups/test.tar.gz",
                actor_id="web:admin",
                confirmation="RESTORE",
            )
        self.assertEqual(result["status"], "RESTORED")
        self.assertTrue(result["authoritative_mutation"])
        self.assertTrue(result["web_reauth_required"])
        self.assertTrue(result["sessions_must_be_revoked"])
        self.assertEqual(len(calls), 2)
        self.assertIn("--validate", calls[0][0])
        self.assertIn("--yes", calls[1][0])
        self.assertEqual(calls[1][1]["env"]["DRLINK_ACTOR"], "web:admin")
        self.assertEqual(calls[1][1]["env"]["DRLINK_INTERFACE"], "WEB")

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

    def test_artifact_generation_uses_owned_paths_and_never_exposes_download(self):
        def fake_run(command, **kwargs):
            del kwargs
            output = Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"artifact")
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="created\n", stderr=""
            )

        service = ManagementSystemService(self.tmp)
        with mock.patch(
            "drlink_management_system.subprocess.run", side_effect=fake_run
        ) as run:
            backup = service.backup_create(actor_id="web:admin")
            support = service.support_bundle_create(actor_id="web:operator")

        self.assertEqual(backup["status"], "CREATED")
        self.assertTrue(backup["protected_artifact"])
        self.assertFalse(backup["sanitized"])
        self.assertFalse(backup["download_exposed"])
        self.assertTrue(backup["path"].startswith("/var/lib/drlink/backups/"))
        self.assertEqual(len(backup["sha256"]), 64)

        self.assertEqual(support["status"], "CREATED")
        self.assertFalse(support["protected_artifact"])
        self.assertTrue(support["sanitized"])
        self.assertFalse(support["download_exposed"])
        self.assertTrue(
            support["path"].startswith("/var/lib/drlink/support-bundles/")
        )
        self.assertEqual(len(support["sha256"]), 64)

        calls = run.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["env"]["DRLINK_ACTOR"], "web:admin")
        self.assertEqual(calls[0].kwargs["env"]["DRLINK_INTERFACE"], "WEB")
        self.assertEqual(calls[1].kwargs["env"]["DRLINK_ACTOR"], "web:operator")

    def test_artifact_generation_rejects_symlinked_owned_directory(self):
        service = ManagementSystemService(self.tmp)
        backups = Path(self.tmp, "var/lib/drlink/backups")
        backups.rmdir()
        target = Path(self.tmp, "outside")
        target.mkdir()
        backups.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ControlPlaneError, "symlink"):
            service.backup_create(actor_id="web:admin")

    def test_core_role_and_permission_guard(self):
        core = ManagementCoreService(self.tmp)
        reader = ManagementActor.authenticated(
            "web:reader",
            {"management-read", "management-diagnose"},
            role="Read Only",
        )
        operator = ManagementActor.authenticated(
            "web:operator",
            {
                "management-read",
                "management-diagnose",
                "management-job-run",
                "management-config",
            },
            role="Operator",
        )
        admin = ManagementActor.authenticated(
            "web:admin",
            {
                "management-read",
                "management-diagnose",
                "management-job-run",
                "management-config",
                "management-recovery",
            },
            role="Admin",
        )
        self.assertTrue(core.system_status(actor=reader)["read_only"])
        denied = ManagementActor.authenticated(
            "web:denied", {"management-read"}, role="Read Only"
        )
        with self.assertRaises(ManagementAuthorizationError):
            core.certificate_preflight(actor=denied)
        with self.assertRaises(ManagementAuthorizationError):
            core.certificate_renew(actor=operator, confirmation="RENEW")
        with self.assertRaisesRegex(ControlPlaneError, "confirmation"):
            core.certificate_renew(actor=admin, confirmation="")
        with mock.patch.object(
            ManagementSystemService,
            "certificate_renew",
            return_value={"renewed": False, "reason": "not_due"},
        ) as renew:
            result = core.certificate_renew(
                actor=admin,
                confirmation="RENEW",
            )
            self.assertEqual(result["reason"], "not_due")
            renew.assert_called_once_with(actor_id="web:admin")
        with self.assertRaises(ManagementAuthorizationError):
            core.backup_create(actor=operator)
        with self.assertRaises(ManagementAuthorizationError):
            core.restore_apply(
                "/var/lib/drlink/backups/test.tar.gz",
                actor=operator,
                confirmation="RESTORE",
            )
        with mock.patch.object(
            ManagementSystemService,
            "restore_apply",
            return_value={"status": "RESTORED"},
        ) as restore:
            self.assertEqual(
                core.restore_apply(
                    "/var/lib/drlink/backups/test.tar.gz",
                    actor=admin,
                    confirmation="RESTORE",
                )["status"],
                "RESTORED",
            )
            restore.assert_called_once_with(
                "/var/lib/drlink/backups/test.tar.gz",
                actor_id="web:admin",
                confirmation="RESTORE",
            )
        with mock.patch.object(
            ManagementSystemService,
            "backup_create",
            return_value={"status": "CREATED"},
        ):
            self.assertEqual(
                core.backup_create(actor=admin)["status"], "CREATED"
            )
        with mock.patch.object(
            ManagementSystemService,
            "support_bundle_create",
            return_value={"status": "CREATED"},
        ):
            self.assertEqual(
                core.support_bundle_create(actor=operator)["status"], "CREATED"
            )
        with self.assertRaises(ManagementAuthorizationError):
            core.support_bundle_create(actor=reader)


if __name__ == "__main__":
    unittest.main()
