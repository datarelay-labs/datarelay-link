from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_cli as control_cli
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

    def test_certificate_configure_issue_and_import_reuse_canonical_tls_boundary(self):
        service = ManagementSystemService(self.tmp)
        with mock.patch(
            "drlink_management_system.mcp_tls.require_public_frontend"
        ), mock.patch(
            "drlink_management_system.mcp_tls.status_view",
            return_value={
                "hostname": "mcp.example.test",
                "mode": mcp_tls.MODE_PRIVATE_CA,
                "certificate": "VALID",
                "raw": {"secret": "no"},
                "active_key_path": "/secret/key",
            },
        ):
            configured = service.certificate_configure(
                {
                    "mode": "private-ca",
                    "hostname": "mcp.example.test",
                    "contact_email": "ops@example.test",
                    "acme_environment": "staging",
                },
                actor_id="web:admin",
            )
        self.assertEqual(configured["status"], "CONFIGURED")
        self.assertNotIn("raw", configured["certificate"])
        self.assertNotIn("active_key_path", configured["certificate"])

        plane = ControlPlane(self.tmp)
        try:
            state = mcp_tls.load_state(plane)
            self.assertEqual(state["mode"], mcp_tls.MODE_PRIVATE_CA)
            self.assertEqual(state["hostname"], "mcp.example.test")
            self.assertEqual(state["contact_email"], "ops@example.test")
        finally:
            plane.close()

        with mock.patch(
            "drlink_management_system.mcp_tls.require_public_frontend"
        ), mock.patch(
            "drlink_management_system.mcp_tls.issue_and_activate",
            return_value={"status": "VALID"},
        ) as issue, mock.patch(
            "drlink_management_system.mcp_tls.status_view",
            return_value={
                "hostname": "mcp.example.test",
                "mode": mcp_tls.MODE_PRIVATE_CA,
                "certificate": "VALID",
            },
        ):
            issued = service.certificate_issue(actor_id="web:admin")
        self.assertEqual(issued["status"], "ISSUED")
        issue.assert_called_once()

        captured = {}
        def fake_import(plane, root, *, cert_path, key_path, chain_path=None, **kwargs):
            del plane, root, kwargs
            cert = Path(cert_path)
            key = Path(key_path)
            captured["cert"] = cert.read_text(encoding="utf-8")
            captured["key"] = key.read_text(encoding="utf-8")
            captured["key_mode"] = key.stat().st_mode & 0o777
            captured["chain"] = (
                Path(chain_path).read_text(encoding="utf-8")
                if chain_path
                else ""
            )
            return {"status": "VALID"}

        with mock.patch(
            "drlink_management_system.mcp_tls.require_public_frontend"
        ), mock.patch(
            "drlink_management_system.mcp_tls.import_user_certificate",
            side_effect=fake_import,
        ) as imported, mock.patch(
            "drlink_management_system.mcp_tls.status_view",
            return_value={
                "hostname": "mcp.example.test",
                "mode": mcp_tls.MODE_USER_CERTIFICATE,
                "certificate": "VALID",
            },
        ):
            result = service.certificate_import(
                cert_pem="-----BEGIN CERTIFICATE-----\nCERT\n-----END CERTIFICATE-----\n",
                key_pem="-----BEGIN PRIVATE KEY-----\nKEY\n-----END PRIVATE KEY-----\n",
                chain_pem="-----BEGIN CERTIFICATE-----\nCHAIN\n-----END CERTIFICATE-----\n",
                actor_id="web:admin",
            )
        self.assertEqual(result["status"], "IMPORTED")
        imported.assert_called_once()
        self.assertIn("CERT", captured["cert"])
        self.assertIn("KEY", captured["key"])
        self.assertEqual(captured["key_mode"], 0o600)
        self.assertIn("CHAIN", captured["chain"])
        staging = Path(self.tmp, "var/lib/drlink/certificate-import-staging")
        self.assertTrue(staging.is_dir())
        self.assertEqual(list(staging.iterdir()), [])

    def test_update_check_is_read_only_and_engine_apply_uses_canonical_updater(self):
        service = ManagementSystemService(self.tmp)
        calls = []
        def fake_run(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            if "--check" in command:
                if "frp-project-update" in command[1]:
                    out = "Update                    : available\nState mutation             : NO\n"
                else:
                    out = "Update      : not needed\n"
                return subprocess.CompletedProcess(
                    args=command, returncode=0, stdout=out, stderr=""
                )
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="Relay Engine update completed.\n",
                stderr="",
            )
        plane = ControlPlane(self.tmp)
        try:
            revision = plane.current_revision()
        finally:
            plane.close()
        with mock.patch(
            "drlink_management_system.subprocess.run", side_effect=fake_run
        ):
            product = service.update_check("product")
            engine = service.update_check("engine")
            product_applied = service.update_product_apply(actor_id="web:admin")
            applied = service.update_engine_apply(actor_id="web:admin")
        self.assertEqual(product["availability"], "AVAILABLE")
        self.assertEqual(engine["availability"], "NOT_NEEDED")
        self.assertFalse(product["authoritative_mutation"])
        self.assertFalse(engine["authoritative_mutation"])
        self.assertEqual(product_applied["status"], "UPDATED")
        self.assertTrue(product_applied["authoritative_mutation"])
        self.assertEqual(applied["status"], "UPDATED")
        self.assertTrue(applied["authoritative_mutation"])
        self.assertEqual(calls[-1][1]["env"]["DRLINK_ACTOR"], "web:admin")
        self.assertEqual(calls[-1][1]["env"]["DRLINK_INTERFACE"], "WEB")
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision)
            audit = plane.conn.execute(
                "SELECT actor_id,interface,action FROM audit_events "
                "WHERE entity_type='system-update' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(audit["actor_id"], "web:admin")
            self.assertEqual(audit["interface"], "WEB")
            self.assertEqual(audit["action"], "web relay-engine update")
        finally:
            plane.close()

    def test_update_engine_failure_surfaces_recovery_required(self):
        service = ManagementSystemService(self.tmp)
        failed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="UPDATE_ROLLBACK_FAILED\nRECOVERY_REQUIRED\n",
            stderr="update failed\n",
        )
        with mock.patch(
            "drlink_management_system.subprocess.run", return_value=failed
        ):
            with self.assertRaisesRegex(ControlPlaneError, "RECOVERY_REQUIRED"):
                service.update_engine_apply(actor_id="web:admin")

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

    def test_audit_retention_configure_run_is_audited_and_revision_neutral(self):
        plane = ControlPlane(self.tmp)
        try:
            revision = plane.current_revision()

            def seed(event_id, category, occurred_at, actor_id, result):
                plane.conn.execute(
                    "INSERT INTO audit_events("
                    "timestamp,revision,actor,action,entity_type,entity_id,operation,"
                    "result,event_id,schema_version,category,event_type,occurred_at,"
                    "source,actor_type,actor_id,interface"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        occurred_at,
                        None,
                        actor_id,
                        "seed",
                        "test",
                        event_id,
                        "seed.event",
                        result,
                        event_id,
                        1,
                        category,
                        "seed.event",
                        occurred_at,
                        "test",
                        "operator",
                        actor_id,
                        "TEST",
                    ),
                )

            seed(
                "evt-old-control",
                "CONTROL",
                "2026-08-01T00:00:00Z",
                "old-control",
                "ok",
            )
            seed(
                "evt-new-control",
                "CONTROL",
                "2026-10-04T00:00:00Z",
                "new-control",
                "ok",
            )
            seed(
                "evt-old-access",
                "ACCESS_DECISION",
                "2026-09-01T00:00:00Z",
                "old-access",
                "DENY",
            )
            seed(
                "evt-new-access",
                "ACCESS_DECISION",
                "2026-10-04T00:00:00Z",
                "new-access",
                "ALLOW",
            )
        finally:
            plane.close()

        service = ManagementSystemService(self.tmp)
        configured = service.audit_retention_configure(
            control_days=30,
            access_days=7,
            max_events=1000,
            actor_id="web:admin",
            interface="WEB",
        )
        self.assertEqual(configured["status"], "CONFIGURED")
        self.assertFalse(configured["configuration_revision_created"])
        result = service.audit_retention_run(
            actor_id="web:admin",
            interface="WEB",
            now=datetime(2026, 10, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["control_deleted"], 1)
        self.assertEqual(result["access_deleted"], 1)
        self.assertTrue(result["capacity_guardrail_satisfied"])

        plane = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(plane.current_revision(), revision)
            ids = {
                row["event_id"]
                for row in plane.conn.execute(
                    "SELECT event_id FROM audit_events WHERE event_id IS NOT NULL"
                )
            }
            self.assertNotIn("evt-old-control", ids)
            self.assertNotIn("evt-old-access", ids)
            self.assertIn("evt-new-control", ids)
            self.assertIn("evt-new-access", ids)
            ops = {
                row["operation"]: (row["actor_id"], row["interface"])
                for row in plane.conn.execute(
                    "SELECT operation,actor_id,interface FROM audit_events "
                    "WHERE operation IN ('audit.retention.configure','audit.retention.run')"
                )
            }
            self.assertEqual(
                ops["audit.retention.configure"], ("web:admin", "WEB")
            )
            self.assertEqual(
                ops["audit.retention.run"], ("web:admin", "WEB")
            )
        finally:
            plane.close()

    def test_audit_export_is_filtered_bounded_and_execution_is_audited(self):
        plane = ControlPlane(self.tmp)
        try:
            revision = plane.current_revision()
            for event_id, actor_id, result in (
                ("evt-export-a", "client-a", "DENY"),
                ("evt-export-b", "client-b", "ALLOW"),
            ):
                occurred = "2026-10-04T12:00:00Z"
                plane.conn.execute(
                    "INSERT INTO audit_events("
                    "timestamp,revision,actor,action,entity_type,entity_id,operation,"
                    "result,event_id,schema_version,category,event_type,occurred_at,"
                    "source,actor_type,actor_id,interface"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        occurred,
                        None,
                        actor_id,
                        "authorize",
                        "remote-service",
                        "svc-export",
                        "authorize",
                        result,
                        event_id,
                        1,
                        "ACCESS_DECISION",
                        "remote.access.decision",
                        occurred,
                        "remote-access",
                        "network-client",
                        actor_id,
                        "FRP_PLUGIN",
                    ),
                )
        finally:
            plane.close()

        result = ManagementSystemService(self.tmp).audit_export_create(
            filters={
                "category": "ACCESS_DECISION",
                "actor": "client-a",
                "result": "DENY",
            },
            actor_id="web:reader",
            interface="WEB",
        )
        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["schema_version"], 1)
        self.assertFalse(result["download_exposed"])
        path = Path(self.tmp, result["path"].lstrip("/"))
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(records[0]["record_type"], "audit-export-meta")
        self.assertEqual(records[1]["event"]["event_id"], "evt-export-a")
        self.assertNotIn("evt-export-b", path.read_text(encoding="utf-8"))

        plane = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(plane.current_revision(), revision)
            audit = plane.conn.execute(
                "SELECT actor_id,interface,after_summary FROM audit_events "
                "WHERE operation='audit.export' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(audit)
            self.assertEqual(audit["actor_id"], "web:reader")
            self.assertEqual(audit["interface"], "WEB")
            self.assertIn(result["path"], audit["after_summary"])
        finally:
            plane.close()

    def test_inventory_export_is_bounded_sanitized_and_non_authoritative(self):
        plane = ControlPlane(self.tmp)
        try:
            before = plane.current_revision()
            plane.upsert_client(
                "host-export",
                label="export-host",
                hostname="export.example",
                connected=True,
            )
            plane.set_client_tag("host-export", "site", "lab")
            plane.set_client_group("export-group")
            plane.set_client_group_member("export-group", "host-export")
            plane.set_published_service(
                "host-export",
                "ssh-export",
                service_type="ssh",
                target_mode="self",
                target_port=22,
                public_port=6060,
                enabled=True,
            )
            seeded = plane.current_revision()
            self.assertGreater(seeded, before)
        finally:
            plane.close()

        result = ManagementSystemService(self.tmp).inventory_export_create(
            actor_id="web:reader"
        )
        self.assertEqual(result["status"], "CREATED")
        self.assertTrue(result["path"].startswith("/var/lib/drlink/exports/"))
        self.assertTrue(result["path"].endswith(".ndjson"))
        self.assertTrue(result["sanitized"])
        self.assertFalse(result["download_exposed"])
        self.assertFalse(result["authoritative_mutation"])
        actual = Path(self.tmp, result["path"].lstrip("/"))
        self.assertTrue(actual.is_file())
        self.assertEqual(actual.stat().st_mode & 0o777, 0o600)
        rows = [
            json.loads(line)
            for line in actual.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(rows[0]["record_type"], "inventory-export-meta")
        self.assertTrue(rows[0]["bounded"])
        resources = {row.get("resource_type") for row in rows[1:]}
        self.assertIn("managed-host", resources)
        self.assertIn("remote-service", resources)
        self.assertIn("managed-host-group", resources)
        self.assertIn("managed-host-tag", resources)
        self.assertNotIn("password", actual.read_text(encoding="utf-8").lower())
        plane = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(plane.current_revision(), seeded)
        finally:
            plane.close()

    def test_public_cli_audit_retention_and_export_use_core_contract(self):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(
                ["system", "audit", "retention"], root=self.tmp
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("Audit retention", out.getvalue())

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(
                [
                    "system",
                    "audit",
                    "retention",
                    "set",
                    "180",
                    "30",
                    "100000",
                ],
                root=self.tmp,
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("configured", out.getvalue())

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(
                ["system", "audit", "export", "category", "CONTROL"],
                root=self.tmp,
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("Audit export created", out.getvalue())
        exports = sorted(
            Path(self.tmp, "var/lib/drlink/audit-exports").glob("*.ndjson")
        )
        self.assertEqual(len(exports), 1)

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(
                ["system", "audit", "retention", "run"], root=self.tmp
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("Audit retention: COMPLETE", out.getvalue())

        plane = ControlPlane(self.tmp, read_only=True)
        try:
            operations = {
                row["operation"]: (row["actor_id"], row["interface"])
                for row in plane.conn.execute(
                    "SELECT operation,actor_id,interface FROM audit_events "
                    "WHERE operation IN ("
                    "'audit.retention.configure','audit.export','audit.retention.run'"
                    ")"
                )
            }
            self.assertEqual(
                operations["audit.retention.configure"], ("cli:local", "CLI")
            )
            self.assertEqual(operations["audit.export"], ("cli:local", "CLI"))
            self.assertEqual(
                operations["audit.retention.run"], ("cli:local", "CLI")
            )
        finally:
            plane.close()

    def test_public_cli_inventory_export_uses_same_bounded_artifact_contract(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.upsert_client(
                "cli-export-host",
                label="cli-export-host",
                hostname="cli-export.example",
                connected=True,
            )
            revision = plane.current_revision()
        finally:
            plane.close()

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(
                ["system", "export", "inventory"], root=self.tmp
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("Inventory export created", out.getvalue())
        exports = sorted(
            Path(self.tmp, "var/lib/drlink/exports").glob("*.ndjson")
        )
        self.assertEqual(len(exports), 1)
        self.assertEqual(exports[0].stat().st_mode & 0o777, 0o600)
        meta = json.loads(
            exports[0].read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertTrue(meta["bounded"])
        self.assertEqual(meta["counts"]["managed_hosts"], 1)
        check = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(check.current_revision(), revision)
        finally:
            check.close()

    def test_inventory_export_fails_closed_above_host_bound(self):
        plane = ControlPlane(self.tmp)
        try:
            for index in range(101):
                plane.upsert_client(
                    "bound-%03d" % index,
                    label="bound-%03d" % index,
                    hostname="bound-%03d.example" % index,
                    connected=False,
                )
        finally:
            plane.close()
        with self.assertRaises(ControlPlaneError):
            ManagementSystemService(self.tmp).inventory_export_create(
                actor_id="web:reader"
            )

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
            core.certificate_configure(
                {"mode": "private-ca"},
                actor=operator,
                confirmation="APPLY",
            )
        with self.assertRaisesRegex(ControlPlaneError, "confirmation"):
            core.certificate_configure(
                {"mode": "private-ca"},
                actor=admin,
                confirmation="",
            )
        with self.assertRaises(ManagementAuthorizationError):
            core.certificate_issue(actor=operator, confirmation="ISSUE")
        with self.assertRaises(ManagementAuthorizationError):
            core.certificate_import(
                actor=operator,
                cert_pem="cert",
                key_pem="key",
                chain_pem="",
                confirmation="IMPORT",
            )
        with self.assertRaises(ManagementAuthorizationError):
            core.certificate_renew(actor=operator, confirmation="RENEW")
        with self.assertRaisesRegex(ControlPlaneError, "confirmation"):
            core.certificate_renew(actor=admin, confirmation="")
        with mock.patch.object(
            ManagementSystemService,
            "update_check",
            return_value={"target": "product", "status": "CHECKED"},
        ) as check:
            self.assertEqual(
                core.update_check("product", actor=reader)["target"],
                "product",
            )
            check.assert_called_once_with("product")
        with self.assertRaises(ManagementAuthorizationError):
            core.update_product_apply(
                actor=operator,
                confirmation="UPDATE PRODUCT",
            )
        with self.assertRaisesRegex(ControlPlaneError, "confirmation"):
            core.update_product_apply(actor=admin, confirmation="")
        with self.assertRaises(ManagementAuthorizationError):
            core.update_engine_apply(
                actor=operator,
                confirmation="UPDATE ENGINE",
            )
        with self.assertRaisesRegex(ControlPlaneError, "confirmation"):
            core.update_engine_apply(actor=admin, confirmation="")
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
