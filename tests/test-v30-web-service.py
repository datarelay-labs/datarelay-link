#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
import drlink_v24 as v24
import frp_pki
from drlink_control_plane import ControlPlane
from drlink_web_auth import WebAuthService, totp_code
from drlink_web_service import create_server, validate_web_bind


class V30WebServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-web-service-")
        os.environ["DRLINK_WEB_QUIET"] = "1"
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        Path(self.tmp, "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\n", encoding="utf-8"
        )
        plane = ControlPlane(self.tmp)
        try:
            now = "2026-10-04T01:00:00Z"
            plane.conn.execute(
                "INSERT INTO clients("
                "id,label,hostname,status,trust_status,connected,agent_heartbeat_at,"
                "agent_lifecycle_state,agent_platform,agent_version,created_at,updated_at"
                ") VALUES ('host-a','alpha','alpha.example','active','trusted',1,?,"
                "'connected','linux','2.4.0',?,?)",
                (now, now, now),
            )
            plane.set_client_description("host-a", "web test host")
        finally:
            plane.close()

        self.auth = WebAuthService(self.tmp)
        material = self.auth.prepare_mfa_material("admin")
        now_dt = datetime.now(timezone.utc)
        code, _ = totp_code(material["totp_secret"], at=now_dt)
        self.auth.create_first_admin(
            username="admin",
            password="correct horse battery staple",
            totp_secret=material["totp_secret"],
            recovery_codes=material["recovery_codes"],
            totp_value=code,
            now=now_dt,
        )
        self.recovery_code = material["recovery_codes"][0]
        self.auth.close()

        self.server = create_server(
            root=self.tmp,
            listen="127.0.0.1",
            port=0,
            static_root=str(ROOT / "web/dist"),
        )
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        os.environ.pop("DRLINK_WEB_QUIET", None)
        os.environ.pop("DRLINK_SKIP_ACTIVATION", None)
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        data = None
        actual_headers = {"Accept": "application/json"}
        if headers:
            actual_headers.update(headers)
        if self.cookie:
            actual_headers["Cookie"] = self.cookie
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            actual_headers["Content-Type"] = "application/json"
            actual_headers["Content-Length"] = str(len(data))
        conn.request(method, path, body=data, headers=actual_headers)
        response = conn.getresponse()
        raw = response.read()
        result_headers = {key.lower(): value for key, value in response.getheaders()}
        conn.close()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = raw.decode("utf-8", errors="replace")
        return response.status, result_headers, payload

    def login(self):
        status, headers, payload = self.request(
            "POST",
            "/api/v1/auth/login",
            {
                "username": "admin",
                "password": "correct horse battery staple",
                "recovery_code": self.recovery_code,
            },
        )
        self.assertEqual(status, 200, payload)
        cookie = headers.get("set-cookie") or ""
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertNotIn("Secure", cookie)
        self.cookie = cookie.split(";", 1)[0]
        self.csrf = payload["csrf_token"]
        self.assertNotIn("session_token", json.dumps(payload))
        return payload

    def test_loopback_health_static_and_security_headers(self):
        status, headers, payload = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(payload["service"], "drlink-web")
        self.assertEqual(payload["status"], "ok")
        self.assertIn("content-security-policy", headers)
        self.assertEqual(headers["x-frame-options"], "DENY")

        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Data Relay Link", body)
        self.assertIn("content-security-policy", headers)

        status, _, body = self.request("GET", "/app.js")
        self.assertEqual(status, 200)
        self.assertNotIn("localStorage", body)
        self.assertNotIn("sessionStorage", body)
        index = (ROOT / "web/dist/index.html").read_text(encoding="utf-8")
        self.assertNotIn('src="http://', index)
        self.assertNotIn('src="https://', index)
        self.assertNotIn('href="http://', index)
        self.assertNotIn('href="https://', index)

    def test_remote_bind_requires_tls(self):
        with self.assertRaises(ControlPlaneError):
            validate_web_bind("0.0.0.0")
        with self.assertRaises(ControlPlaneError):
            validate_web_bind("192.0.2.10")
        validate_web_bind("127.0.0.1")
        validate_web_bind("::1")

    def test_auth_required_on_loopback_and_read_views(self):
        status, _, _ = self.request("GET", "/api/v1/overview")
        self.assertEqual(status, 401)
        self.login()

        for path in (
            "/api/v1/session",
            "/api/v1/overview",
            "/api/v1/inventory?resource_type=managed-host&limit=10",
            "/api/v1/search?q=alpha&limit=10",
            "/api/v1/policies?limit=10",
            "/api/v1/versions",
            "/api/v1/system",
            "/api/v1/audit?limit=10",
            "/api/v1/revisions?limit=10",
            "/api/v1/health",
            "/api/v1/jobs?limit=10",
            "/api/v1/saved-views",
            "/api/v1/sessions",
        ):
            status, _, payload = self.request("GET", path)
            self.assertEqual(status, 200, (path, payload))

        status, _, versions = self.request("GET", "/api/v1/versions")
        self.assertEqual(status, 200)
        self.assertEqual(versions["server_version"], "3.0.0")
        self.assertEqual(versions["drift_count"], 1)

        status, _, system = self.request("GET", "/api/v1/system")
        self.assertEqual(status, 200, system)
        self.assertTrue(system["read_only"])
        self.assertTrue(system["side_effect_free"])
        self.assertEqual(system["identity"]["project_version"], "3.0.0")
        self.assertEqual(system["backup"]["directory"], "/var/lib/drlink/backups")

    def test_system_validation_routes_are_csrf_protected_and_non_mutating(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            revision = plane.current_revision()
        finally:
            plane.close()

        status, _, _ = self.request(
            "POST", "/api/v1/system/certificate/preflight", {}
        )
        self.assertEqual(status, 403)

        status, _, preflight = self.request(
            "POST",
            "/api/v1/system/certificate/preflight",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, preflight)
        self.assertIn("hostname", preflight["error"].lower())

        status, _, outside = self.request(
            "POST",
            "/api/v1/system/backup/validate",
            {"path": "/etc/passwd"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, outside)
        self.assertIn("/var/lib/drlink/backups/", outside["error"])

        status, _, missing = self.request(
            "POST",
            "/api/v1/system/backup/validate",
            {"path": "/var/lib/drlink/backups/missing.tar.gz"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, missing)
        self.assertFalse(missing["valid"])
        self.assertFalse(missing["authoritative_mutation"])
        self.assertEqual(
            missing["path"], "/var/lib/drlink/backups/missing.tar.gz"
        )

        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision)
        finally:
            plane.close()

    def test_certificate_renew_route_requires_csrf_and_explicit_confirmation(self):
        login = self.login()
        operator_id = login["operator"]["id"]

        status, _, _ = self.request(
            "POST",
            "/api/v1/system/certificate/renew",
            {"confirmation": "RENEW"},
        )
        self.assertEqual(status, 403)

        status, _, denied = self.request(
            "POST",
            "/api/v1/system/certificate/renew",
            {"confirmation": ""},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, denied)
        self.assertIn("confirmation", denied["error"].lower())

        from unittest import mock
        with mock.patch(
            "drlink_management_core.ManagementSystemService.certificate_renew",
            return_value={
                "renewed": False,
                "reason": "not_due",
                "failure_class": "",
                "certificate": {"hostname": "mcp.example.test"},
                "authoritative_mutation": False,
            },
        ) as renew:
            status, _, result = self.request(
                "POST",
                "/api/v1/system/certificate/renew",
                {"confirmation": "RENEW"},
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(status, 200, result)
        self.assertFalse(result["renewed"])
        renew.assert_called_once_with(actor_id="web:%s" % operator_id)

    def test_certificate_lifecycle_and_update_routes_use_core_guards(self):
        login = self.login()
        operator_id = login["operator"]["id"]

        status, _, denied = self.request(
            "POST",
            "/api/v1/system/certificate/configure",
            {"mode": "private-ca", "hostname": "mcp.example.test"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, denied)
        self.assertIn("confirmation", denied["error"].lower())

        from unittest import mock
        with mock.patch(
            "drlink_management_core.ManagementSystemService.certificate_configure",
            return_value={
                "status": "CONFIGURED",
                "certificate": {"hostname": "mcp.example.test"},
                "authoritative_mutation": True,
            },
        ) as configure:
            status, _, configured = self.request(
                "POST",
                "/api/v1/system/certificate/configure",
                {
                    "mode": "private-ca",
                    "hostname": "mcp.example.test",
                    "contact_email": "ops@example.test",
                    "acme_environment": "staging",
                    "confirmation": "APPLY",
                },
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(status, 200, configured)
        configure.assert_called_once_with(
            {
                "mode": "private-ca",
                "hostname": "mcp.example.test",
                "contact_email": "ops@example.test",
                "acme_environment": "staging",
            },
            actor_id="web:%s" % operator_id,
        )

        with mock.patch(
            "drlink_management_core.ManagementSystemService.certificate_issue",
            return_value={
                "status": "ISSUED",
                "certificate": {"hostname": "mcp.example.test"},
                "authoritative_mutation": True,
            },
        ) as issue:
            status, _, issued = self.request(
                "POST",
                "/api/v1/system/certificate/issue",
                {"confirmation": "ISSUE"},
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(status, 200, issued)
        issue.assert_called_once_with(actor_id="web:%s" % operator_id)

        with mock.patch(
            "drlink_management_core.ManagementSystemService.certificate_import",
            return_value={
                "status": "IMPORTED",
                "certificate": {"hostname": "mcp.example.test"},
                "authoritative_mutation": True,
            },
        ) as imported:
            status, _, imported_result = self.request(
                "POST",
                "/api/v1/system/certificate/import",
                {
                    "cert_pem": "CERTIFICATE-PEM",
                    "key_pem": "PRIVATE-KEY-PEM",
                    "chain_pem": "CHAIN-PEM",
                    "confirmation": "IMPORT",
                },
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(status, 200, imported_result)
        self.assertNotIn("PRIVATE-KEY-PEM", json.dumps(imported_result))
        imported.assert_called_once_with(
            cert_pem="CERTIFICATE-PEM",
            key_pem="PRIVATE-KEY-PEM",
            chain_pem="CHAIN-PEM",
            actor_id="web:%s" % operator_id,
        )

        with mock.patch(
            "drlink_management_core.ManagementSystemService.update_check",
            return_value={
                "target": "product",
                "status": "CHECKED",
                "availability": "AVAILABLE",
                "authoritative_mutation": False,
            },
        ) as check:
            status, _, checked = self.request(
                "POST",
                "/api/v1/system/update/check",
                {"target": "product"},
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(status, 200, checked)
        self.assertEqual(checked["availability"], "AVAILABLE")
        check.assert_called_once_with("product")

        status, _, denied = self.request(
            "POST",
            "/api/v1/system/update/engine",
            {"confirmation": ""},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, denied)
        with mock.patch(
            "drlink_management_core.ManagementSystemService.update_engine_apply",
            return_value={
                "target": "engine",
                "status": "UPDATED",
                "authoritative_mutation": True,
            },
        ) as update:
            status, _, updated = self.request(
                "POST",
                "/api/v1/system/update/engine",
                {"confirmation": "UPDATE ENGINE"},
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(status, 200, updated)
        update.assert_called_once_with(actor_id="web:%s" % operator_id)

    def test_restore_requires_admin_confirmation_revokes_sessions_and_clears_cookie(self):
        login = self.login()
        operator_id = login["operator"]["id"]

        status, _, _ = self.request(
            "POST",
            "/api/v1/system/restore",
            {
                "path": "/var/lib/drlink/backups/test.tar.gz",
                "confirmation": "RESTORE",
            },
        )
        self.assertEqual(status, 403)

        status, _, denied = self.request(
            "POST",
            "/api/v1/system/restore",
            {
                "path": "/var/lib/drlink/backups/test.tar.gz",
                "confirmation": "",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, denied)
        self.assertIn("confirmation", denied["error"].lower())

        status, _, session = self.request("GET", "/api/v1/session")
        self.assertEqual(status, 200, session)

        from unittest import mock
        with mock.patch(
            "drlink_management_core.ManagementSystemService.restore_apply",
            return_value={
                "status": "RESTORED",
                "path": "/var/lib/drlink/backups/test.tar.gz",
                "web_reauth_required": True,
                "sessions_must_be_revoked": True,
                "recovery_authority": True,
                "authoritative_mutation": True,
            },
        ) as restore:
            status, headers, result = self.request(
                "POST",
                "/api/v1/system/restore",
                {
                    "path": "/var/lib/drlink/backups/test.tar.gz",
                    "confirmation": "RESTORE",
                },
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "RESTORED")
        self.assertTrue(result["web_reauth_required"])
        self.assertGreaterEqual(result["web_sessions_revoked"], 1)
        self.assertIn("Max-Age=0", headers.get("set-cookie", ""))
        restore.assert_called_once_with(
            "/var/lib/drlink/backups/test.tar.gz",
            actor_id="web:%s" % operator_id,
            confirmation="RESTORE",
        )

        status, _, _ = self.request("GET", "/api/v1/session")
        self.assertEqual(status, 401)

    def test_system_artifact_routes_are_csrf_protected_and_bounded(self):
        self.login()

        def fake_run(command, **kwargs):
            output = Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"web-artifact")
            return __import__("subprocess").CompletedProcess(
                args=command, returncode=0, stdout="created\n", stderr=""
            )

        for path in (
            "/api/v1/system/backup/create",
            "/api/v1/system/support-bundle",
        ):
            status, _, _ = self.request("POST", path, {})
            self.assertEqual(status, 403, path)

        from unittest import mock
        with mock.patch(
            "drlink_management_system.subprocess.run", side_effect=fake_run
        ):
            status, _, backup = self.request(
                "POST",
                "/api/v1/system/backup/create",
                {},
                headers={"X-CSRF-Token": self.csrf},
            )
            self.assertEqual(status, 200, backup)
            self.assertEqual(backup["status"], "CREATED")
            self.assertTrue(backup["protected_artifact"])
            self.assertFalse(backup["download_exposed"])
            self.assertTrue(
                backup["path"].startswith("/var/lib/drlink/backups/")
            )

            status, _, support = self.request(
                "POST",
                "/api/v1/system/support-bundle",
                {},
                headers={"X-CSRF-Token": self.csrf},
            )
            self.assertEqual(status, 200, support)
            self.assertEqual(support["status"], "CREATED")
            self.assertTrue(support["sanitized"])
            self.assertFalse(support["download_exposed"])
            self.assertTrue(
                support["path"].startswith("/var/lib/drlink/support-bundles/")
            )

        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(
                plane.conn.execute(
                    "SELECT COUNT(*) FROM config_revisions"
                ).fetchone()[0],
                plane.current_revision(),
            )
        finally:
            plane.close()

    def test_csrf_protects_web_preferences_and_logout(self):
        self.login()
        status, _, _ = self.request(
            "POST", "/api/v1/saved-views", {"name": "Offline", "payload": {}}
        )
        self.assertEqual(status, 403)

        status, _, saved = self.request(
            "POST",
            "/api/v1/saved-views",
            {"name": "Offline", "payload": {"filter": "offline"}},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, saved)
        status, _, views = self.request("GET", "/api/v1/saved-views")
        self.assertEqual(status, 200)
        self.assertEqual(views["items"][0]["name"], "Offline")

        status, headers, payload = self.request(
            "POST",
            "/api/v1/auth/logout",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "logged_out")
        self.assertIn("Max-Age=0", headers.get("set-cookie", ""))

    def test_policy_trace_and_saved_regression_test_routes(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            v24.set_network_object(
                plane, "trace-src", type="ip", value="198.51.100.10",
                oneshot=True, confirm=True,
            )
            v24.set_network_object(
                plane, "trace-dst", type="ip", value="198.51.100.20",
                oneshot=True, confirm=True,
            )
            v24.set_service_object(
                plane, "trace-ssh", type="tcp", port=22,
                oneshot=True, confirm=True,
            )
            v24.set_access_rule(
                plane,
                "remote",
                "trace-allow",
                mode="whitelist",
                source="trace-src",
                destination="trace-dst",
                service="trace-ssh",
                enabled=True,
                oneshot=True,
                confirm=True,
            )
            revision = plane.current_revision()
        finally:
            plane.close()

        flow = {
            "plane": "remote",
            "source": "trace-src",
            "destination": "trace-dst",
            "service": "trace-ssh",
        }
        status, _, _ = self.request(
            "POST", "/api/v1/policy/trace", flow
        )
        self.assertEqual(status, 403)

        status, _, trace = self.request(
            "POST",
            "/api/v1/policy/trace",
            flow,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, trace)
        self.assertEqual(trace["final"]["result"], "ALLOW")
        self.assertIn("trace-allow", trace["policy"]["matched_rules"])

        status, _, graph = self.request(
            "GET", "/api/v1/policy/graph?plane=remote"
        )
        self.assertEqual(status, 200, graph)
        graph_flow = next(
            item
            for item in graph["paths"]
            if item["input"].get("source") == "trace-src"
            and item["input"].get("destination") == "trace-dst"
            and item["input"].get("service") == "trace-ssh"
        )
        self.assertEqual(graph_flow["decision"], "ALLOW")
        self.assertIn("trace-allow", graph_flow["rules"])
        self.assertFalse(graph["network_topology"])

        status, _, guided = self.request(
            "POST",
            "/api/v1/guided/preview",
            {
                "change_type": "remote-access-rule",
                "payload": {
                    "operation": "set",
                    "name": "trace-allow",
                    "enabled": False,
                },
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, guided)
        self.assertTrue(guided["blast_radius"]["access_narrowed"])
        self.assertTrue(guided["blast_radius"]["newly_blocked"])
        self.assertIsNotNone(guided["graph_overlay"])
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision)
            self.assertTrue(bool(plane._get_rule("remote", "trace-allow")["enabled"]))
        finally:
            plane.close()

        status, _, listed = self.request("GET", "/api/v1/policy-tests")
        self.assertEqual(status, 200, listed)
        self.assertEqual(listed["count"], 0)

        definition = {
            "name": "web-critical-ssh",
            **flow,
            "expected": "ALLOW",
            "required": True,
            "enabled": True,
        }
        status, _, preview = self.request(
            "POST",
            "/api/v1/policy-tests/preview",
            {"operation": "set", "definition": definition},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview["confirmation_class"], "APPLY")
        self.assertTrue(preview["preview"]["assertion_ok"])

        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision)
            self.assertEqual(
                plane.conn.execute(
                    "SELECT COUNT(*) FROM management_policy_tests"
                ).fetchone()[0],
                0,
            )
        finally:
            plane.close()

        status, _, denied = self.request(
            "POST",
            "/api/v1/policy-tests/apply",
            {
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "SAVE",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, denied)

        status, _, applied = self.request(
            "POST",
            "/api/v1/policy-tests/apply",
            {
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "APPLY",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "APPLIED")

        status, _, run = self.request(
            "POST",
            "/api/v1/policy-tests/run",
            {"required_only": True},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, run)
        self.assertTrue(run["ok"])
        self.assertEqual(run["passed"], 1)
        self.assertEqual(run["required_failed"], 0)

        status, _, listed = self.request("GET", "/api/v1/policy-tests")
        self.assertEqual(status, 200, listed)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["items"][0]["name"], "web-critical-ssh")

    def test_managed_host_lifecycle_requires_admin_csrf_and_typed_confirmation(self):
        login = self.login()
        operator_id = login["operator"]["id"]

        status, _, _ = self.request(
            "POST",
            "/api/v1/managed-hosts/lifecycle/preview",
            {"host": "host-a", "operation": "revoke-trust"},
        )
        self.assertEqual(status, 403)

        plane = ControlPlane(self.tmp)
        try:
            before = plane.current_revision()
            trust_before = str(plane.require_client("host-a")["trust_status"])
        finally:
            plane.close()

        status, _, preview = self.request(
            "POST",
            "/api/v1/managed-hosts/lifecycle/preview",
            {"host": "host-a", "operation": "revoke-trust"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview["confirmation_class"], "REVOKE")
        self.assertIn("published services", preview["impact"]["kept"])

        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before)
            self.assertEqual(
                str(plane.require_client("host-a")["trust_status"]),
                trust_before,
            )
        finally:
            plane.close()

        status, _, denied = self.request(
            "POST",
            "/api/v1/managed-hosts/lifecycle/apply",
            {
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "APPLY",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, denied)
        self.assertIn("REVOKE", denied["error"])

        status, _, applied = self.request(
            "POST",
            "/api/v1/managed-hosts/lifecycle/apply",
            {
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "REVOKE",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "APPLIED")

        plane = ControlPlane(self.tmp)
        try:
            row = plane.require_client("host-a")
            self.assertEqual(str(row["trust_status"]), "revoked")
            self.assertEqual(plane.current_revision(), before + 1)
            revision = plane.conn.execute(
                "SELECT actor FROM config_revisions WHERE revision=?",
                (before + 1,),
            ).fetchone()
            self.assertEqual(revision["actor"], "web:%s" % operator_id)
            audit = plane.conn.execute(
                "SELECT actor_id,interface FROM audit_events "
                "WHERE revision=? ORDER BY id DESC LIMIT 1",
                (before + 1,),
            ).fetchone()
            self.assertEqual(audit["actor_id"], "web:%s" % operator_id)
            self.assertEqual(audit["interface"], "WEB")
        finally:
            plane.close()

    def test_guided_change_preview_and_apply_use_csrf_and_core_plan(self):
        self.login()
        status, _, payload = self.request(
            "POST",
            "/api/v1/guided/preview",
            {
                "change_type": "network-object",
                "payload": {
                    "name": "web-office",
                    "type": "ip",
                    "value": "198.51.100.44",
                },
            },
        )
        self.assertEqual(status, 403)

        status, _, preview = self.request(
            "POST",
            "/api/v1/guided/preview",
            {
                "change_type": "network-object",
                "payload": {
                    "name": "web-office",
                    "type": "ip",
                    "value": "198.51.100.44",
                },
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        plane = ControlPlane(self.tmp)
        try:
            self.assertIsNone(plane.get_object("web-office"))
            before = plane.current_revision()
        finally:
            plane.close()

        status, _, applied = self.request(
            "POST",
            "/api/v1/guided/apply",
            {
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "APPLY",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["revision"], before + 1)
        plane = ControlPlane(self.tmp)
        try:
            self.assertIsNotNone(plane.get_object("web-office"))
        finally:
            plane.close()

    def test_remote_service_preview_apply_queues_agent_job_without_false_success(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            v24.set_service_object(plane, "web-rs-ssh", type="tcp", port=22, oneshot=True)
            plane.refresh_agent_lifecycle("host-a", "connected")
            before = plane.current_revision()
        finally:
            plane.close()
        body = {
            "owner": "host-a",
            "name": "web-rs",
            "operation": "set",
            "destination": "this-host",
            "service": "web-rs-ssh",
            "enabled": True,
        }
        status, _, _ = self.request("POST", "/api/v1/remote-services/preview", body)
        self.assertEqual(status, 403)
        status, _, preview = self.request(
            "POST", "/api/v1/remote-services/preview", body,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview["owner"]["connectivity"], "connected")
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before)
            self.assertIsNone(
                plane.conn.execute("SELECT id FROM published_services WHERE name='web-rs'").fetchone()
            )
        finally:
            plane.close()
        status, _, queued = self.request(
            "POST",
            "/api/v1/remote-services/apply",
            {"change_plan_id": preview["change_plan_id"], "confirmation": "APPLY"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, queued)
        self.assertEqual(queued["status"], "QUEUED")
        status, _, job = self.request("GET", "/api/v1/jobs/" + queued["job_id"])
        self.assertEqual(status, 200, job)
        self.assertEqual(job["status"], "QUEUED")
        self.assertEqual(job["targets"][0]["target_id"], "host-a")
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before)
        finally:
            plane.close()

    def test_zero_touch_enrollment_is_admin_csrf_protected_and_redacted_in_history(self):
        self.login()
        material = frp_pki.ensure_pki(Path(self.tmp, "etc/drlink/pki"), "127.0.0.1")
        Path(self.tmp, "etc/drlink/config.json").write_text(
            json.dumps({
                "role": "server",
                "allocator_public_url": "https://127.0.0.1:9443/enroll",
                "tls_ca_cert": "/etc/drlink/pki/ca.crt",
                "enrollments_dir": "/var/lib/drlink/enrollments",
                "bootstrap_dir": "/var/lib/drlink/bootstrap",
                "registry_file": "/var/lib/drlink/registry.json",
                "enrollment_retention_days": 30,
            }) + "\n", encoding="utf-8"
        )
        self.assertTrue(Path(material["ca_crt"]).is_file())
        body = {"platform": "linux", "ttl_seconds": 600, "label": "web-agent"}
        status, _, _ = self.request("POST", "/api/v1/enrollments/zero-touch", body)
        self.assertEqual(status, 403)
        status, _, issued = self.request(
            "POST",
            "/api/v1/enrollments/zero-touch",
            body,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, issued)
        self.assertTrue(issued["display_once"])
        self.assertTrue(issued["command"])
        status, _, listing = self.request("GET", "/api/v1/enrollments?limit=10")
        self.assertEqual(status, 200, listing)
        self.assertEqual(listing["total"], 1)
        serialized = json.dumps(listing)
        self.assertNotIn(issued["command"], serialized)
        self.assertNotIn("command", serialized.lower())
        self.assertNotIn("secret", serialized.lower())

        status, _, manual = self.request(
            "POST",
            "/api/v1/enrollments/manual",
            {"platform": "linux", "ttl_seconds": 600, "label": "manual-web-agent"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, manual)
        self.assertTrue(manual["enrollment_code"])
        self.assertNotIn(manual["enrollment_code"], manual["command"])
        status, _, listing = self.request("GET", "/api/v1/enrollments?limit=10")
        self.assertEqual(status, 200, listing)
        self.assertEqual(listing["total"], 2)
        serialized = json.dumps(listing)
        self.assertNotIn(manual["enrollment_code"], serialized)

    def test_guided_remote_access_rule_web_parity(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            v24.set_network_object(plane, "web-src", type="ip", value="198.51.100.10", oneshot=True)
            v24.set_network_object(plane, "web-dst", type="ip", value="198.51.100.20", oneshot=True)
            v24.set_service_object(plane, "web-ssh", type="tcp", port=22, oneshot=True)
            before = plane.current_revision()
        finally:
            plane.close()
        status, _, preview = self.request(
            "POST",
            "/api/v1/guided/preview",
            {
                "change_type": "remote-access-rule",
                "payload": {
                    "name": "web-allow-ssh",
                    "mode": "whitelist",
                    "source": "web-src",
                    "destination": "web-dst",
                    "service": "web-ssh",
                    "enabled": True,
                },
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before)
            self.assertIsNone(plane._get_rule("remote", "web-allow-ssh"))
        finally:
            plane.close()
        status, _, applied = self.request(
            "POST",
            "/api/v1/guided/apply",
            {"change_plan_id": preview["change_plan_id"], "confirmation": "APPLY"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        plane = ControlPlane(self.tmp)
        try:
            self.assertIsNotNone(plane._get_rule("remote", "web-allow-ssh"))
        finally:
            plane.close()

    def test_temporary_access_preview_apply_uses_core_change_plan(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            v24.set_network_object(plane, "temp-src", type="ip", value="198.51.100.10", oneshot=True)
            v24.set_network_object(plane, "temp-dst", type="ip", value="198.51.100.20", oneshot=True)
            v24.set_service_object(plane, "temp-ssh", type="tcp", port=22, oneshot=True)
            v24.set_access_rule(
                plane,
                "remote",
                "temp-rule",
                mode="whitelist",
                source="temp-src",
                destination="temp-dst",
                service="temp-ssh",
                enabled=True,
                oneshot=True,
                confirm=True,
            )
            before = plane.current_revision()
        finally:
            plane.close()

        status, _, _ = self.request(
            "POST",
            "/api/v1/temporary-access/preview",
            {"plane": "remote", "rule": "temp-rule", "operation": "set", "expires_at": "2099-01-01T00:00:00Z"},
        )
        self.assertEqual(status, 403)

        status, _, preview = self.request(
            "POST",
            "/api/v1/temporary-access/preview",
            {"plane": "remote", "rule": "temp-rule", "operation": "set", "expires_at": "2099-01-01T00:00:00Z"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        self.assertTrue(preview["change_plan_id"].startswith("cp_"))
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before)
            self.assertIsNone(plane._get_rule("remote", "temp-rule")["expires_at"])
        finally:
            plane.close()

        status, _, applied = self.request(
            "POST",
            "/api/v1/temporary-access/apply",
            {"change_plan_id": preview["change_plan_id"], "confirmation": "APPLY"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before + 1)
            self.assertEqual(
                plane._get_rule("remote", "temp-rule")["expires_at"],
                "2099-01-01T00:00:00Z",
            )
        finally:
            plane.close()

    def test_audit_export_and_retention_web_routes_are_csrf_and_role_guarded(self):
        self.login()

        status, _, retention = self.request("GET", "/api/v1/audit/retention")
        self.assertEqual(status, 200, retention)
        self.assertEqual(retention["config"]["control_days"], 365)
        self.assertEqual(retention["config"]["access_days"], 90)

        status, _, denied = self.request(
            "POST",
            "/api/v1/audit/retention/configure",
            {
                "control_days": 180,
                "access_days": 30,
                "max_events": 100000,
            },
        )
        self.assertEqual(status, 403, denied)

        status, _, configured = self.request(
            "POST",
            "/api/v1/audit/retention/configure",
            {
                "control_days": 180,
                "access_days": 30,
                "max_events": 100000,
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, configured)
        self.assertEqual(configured["config"]["control_days"], 180)
        self.assertEqual(configured["config"]["access_days"], 30)
        self.assertEqual(configured["config"]["max_events"], 100000)

        status, _, denied_export = self.request(
            "POST",
            "/api/v1/audit/export",
            {"filters": {"category": "CONTROL"}},
        )
        self.assertEqual(status, 403, denied_export)

        status, _, exported = self.request(
            "POST",
            "/api/v1/audit/export",
            {"filters": {"category": "CONTROL"}},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, exported)
        self.assertTrue(
            exported["path"].startswith("/var/lib/drlink/audit-exports/")
        )
        self.assertEqual(exported["schema_version"], 1)
        self.assertFalse(exported["download_exposed"])
        path = Path(self.tmp, exported["path"].lstrip("/"))
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

        status, _, retained = self.request(
            "POST",
            "/api/v1/audit/retention/run",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, retained)
        self.assertIn(retained["status"], ("COMPLETE", "ATTENTION_REQUIRED"))

        plane = ControlPlane(self.tmp, read_only=True)
        try:
            rows = plane.conn.execute(
                "SELECT operation,actor_id,interface FROM audit_events "
                "WHERE operation IN ("
                "'audit.retention.configure','audit.export','audit.retention.run'"
                ") ORDER BY id"
            ).fetchall()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row["interface"] == "WEB" for row in rows))
            self.assertTrue(
                all(str(row["actor_id"]).startswith("web:") for row in rows)
            )
        finally:
            plane.close()

    def test_fleet_artifact_and_metadata_web_paths_are_bounded_and_atomic(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            plane.upsert_client(
                "host-b",
                label="beta",
                hostname="beta.example",
                connected=True,
            )
            before = plane.current_revision()
        finally:
            plane.close()

        status, _, denied_export = self.request(
            "POST", "/api/v1/inventory/export", {}
        )
        self.assertEqual(status, 403, denied_export)

        status, _, exported = self.request(
            "POST",
            "/api/v1/inventory/export",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, exported)
        self.assertTrue(exported["path"].startswith("/var/lib/drlink/exports/"))
        self.assertFalse(exported["download_exposed"])
        self.assertTrue(exported["sanitized"])
        self.assertEqual(exported["counts"]["managed_hosts"], 2)
        export_path = Path(self.tmp) / exported["path"].lstrip("/")
        self.assertTrue(export_path.is_file())
        lines = [
            json.loads(line)
            for line in export_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(lines[0]["record_type"], "inventory-export-meta")
        self.assertEqual(
            sum(1 for item in lines if item.get("resource_type") == "managed-host"),
            2,
        )
        self.assertNotIn("password", export_path.read_text(encoding="utf-8").lower())

        status, _, support_job = self.request(
            "POST",
            "/api/v1/jobs/diagnostic",
            {
                "job_type": "support-bundle",
                "resource_type": "managed-host",
                "resource": "host-a",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, support_job)
        self.assertEqual(support_job["job"]["job_type"], "support-bundle")
        self.assertEqual(support_job["job"]["target_count"], 1)
        self.request(
            "POST",
            "/api/v1/jobs/cancel",
            {"job_id": support_job["job"]["id"]},
            headers={"X-CSRF-Token": self.csrf},
        )

        changes = {
            "description": "fleet-web",
            "tags": {"site": "lab"},
            "add_groups": ["web-fleet"],
        }
        status, _, denied_preview = self.request(
            "POST",
            "/api/v1/fleet/metadata/preview",
            {
                "resource_type": "managed-host",
                "resource": "",
                "changes": changes,
            },
        )
        self.assertEqual(status, 403, denied_preview)

        status, _, preview = self.request(
            "POST",
            "/api/v1/fleet/metadata/preview",
            {
                "resource_type": "managed-host",
                "resource": "",
                "changes": changes,
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview["selection"]["target_count"], 2)
        plane = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(plane.current_revision(), before)
            self.assertIsNone(
                plane.conn.execute(
                    "SELECT 1 FROM client_groups WHERE name='web-fleet'"
                ).fetchone()
            )
        finally:
            plane.close()

        status, _, wrong = self.request(
            "POST",
            "/api/v1/fleet/metadata/apply",
            {
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "CONFIRM",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, wrong)

        status, _, applied = self.request(
            "POST",
            "/api/v1/fleet/metadata/apply",
            {
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "APPLY",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["revision"], before + 1)
        self.assertEqual(applied["result"]["target_count"], 2)

        plane = ControlPlane(self.tmp, read_only=True)
        try:
            group = plane.conn.execute(
                "SELECT id FROM client_groups WHERE name='web-fleet'"
            ).fetchone()
            self.assertIsNotNone(group)
            for host in ("host-a", "host-b"):
                row = plane.require_client(host)
                self.assertEqual(row["description"], "fleet-web")
                self.assertEqual(
                    plane.conn.execute(
                        "SELECT value FROM client_tags "
                        "WHERE client_id=? AND key='site'",
                        (row["id"],),
                    ).fetchone()["value"],
                    "lab",
                )
                self.assertIsNotNone(
                    plane.conn.execute(
                        "SELECT 1 FROM client_group_members "
                        "WHERE group_id=? AND client_id=?",
                        (group["id"], row["id"]),
                    ).fetchone()
                )
        finally:
            plane.close()

    def test_bounded_management_job_web_start_list_detail_and_cancel(self):
        self.login()

        status, _, denied = self.request(
            "POST",
            "/api/v1/jobs/diagnostic",
            {
                "job_type": "doctor",
                "resource_type": "managed-host",
                "resource": "host-a",
            },
        )
        self.assertEqual(status, 403, denied)

        status, _, started = self.request(
            "POST",
            "/api/v1/jobs/diagnostic",
            {
                "job_type": "doctor",
                "resource_type": "managed-host",
                "resource": "host-a",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, started)
        job = started["job"]
        self.assertEqual(job["job_type"], "doctor")
        self.assertEqual(job["status"], "QUEUED")
        self.assertEqual(job["target_count"], 1)
        self.assertEqual(started["selection"]["target_count"], 1)
        self.assertEqual(job["targets"][0]["target_id"], "host-a")

        status, _, jobs = self.request("GET", "/api/v1/jobs?limit=10")
        self.assertEqual(status, 200, jobs)
        self.assertIn(job["id"], {item["id"] for item in jobs["items"]})

        status, _, detail = self.request(
            "GET", "/api/v1/jobs/" + job["id"]
        )
        self.assertEqual(status, 200, detail)
        self.assertEqual(detail["id"], job["id"])
        self.assertEqual(detail["targets"][0]["status"], "QUEUED")

        status, _, denied_cancel = self.request(
            "POST",
            "/api/v1/jobs/cancel",
            {"job_id": job["id"]},
        )
        self.assertEqual(status, 403, denied_cancel)

        status, _, cancelled = self.request(
            "POST",
            "/api/v1/jobs/cancel",
            {"job_id": job["id"]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, cancelled)
        self.assertEqual(cancelled["id"], job["id"])
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertTrue(cancelled["cancel_requested"])
        self.assertEqual(cancelled["targets"][0]["status"], "CANCELLED")
        self.assertEqual(
            cancelled["targets"][0]["error"], "CANCELLED_BY_OPERATOR"
        )

        status, _, version_started = self.request(
            "POST",
            "/api/v1/jobs/diagnostic",
            {
                "job_type": "version-check",
                "resource_type": "managed-host",
                "resource": "host-a",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, version_started)
        version_job = version_started["job"]
        self.assertEqual(
            version_job["payload"]["target_project_version"], "3.0.0"
        )
        self.assertIn("target_relay_engine_version", version_job["payload"])
        status, _, _ = self.request(
            "POST",
            "/api/v1/jobs/cancel",
            {"job_id": version_job["id"]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200)

        status, _, invalid = self.request(
            "POST",
            "/api/v1/jobs/diagnostic",
            {
                "job_type": "remote-service-delete",
                "resource_type": "managed-host",
                "resource": "host-a",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, invalid)
        self.assertIn("doctor, refresh, version-check, or support-bundle", invalid["error"])

    def test_access_operations_diagnosis_live_and_cutoff_web_paths(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            plane.upsert_client(
                "diag-host-id",
                label="diag-host",
                hostname="diag-host.example",
                connected=True,
                addresses=[{"address": "10.20.30.40", "active": True}],
            )
            plane.set_published_service(
                "diag-host-id",
                "diag-ssh-admin",
                service_type="ssh",
                target_mode="self",
                target_port=22,
                public_port=6101,
                enabled=True,
            )
            published = plane.conn.execute(
                "SELECT id FROM published_services WHERE client_id='diag-host-id' "
                "AND name='diag-ssh-admin'"
            ).fetchone()
            plane.conn.execute(
                "INSERT OR REPLACE INTO remote_service_meta("
                "service_id,status,pool_class,pending_allocation,delete_pending,"
                "reason,runtime_verified"
                ") VALUES (?,'HEALTHY','normal',0,0,'',1)",
                (published["id"],),
            )
            v24.set_network_object(
                plane,
                "diag-src",
                type="ip",
                value="198.51.100.44",
                oneshot=True,
            )
            v24.set_service_object(
                plane,
                "diag-ssh",
                type="tcp",
                port=22,
                oneshot=True,
            )
            v24.set_access_rule(
                plane,
                "remote",
                "diag-allow",
                mode="whitelist",
                source="diag-src",
                destination="diag-host",
                service="diag-ssh",
                enabled=True,
                oneshot=True,
            )
            revision = plane.current_revision()
        finally:
            plane.close()

        status, _, denied = self.request(
            "POST",
            "/api/v1/diagnose",
            {
                "plane": "remote",
                "source": "diag-src",
                "destination": "diag-host",
                "service": "diag-ssh",
            },
        )
        self.assertEqual(status, 403, denied)

        status, _, diagnosis = self.request(
            "POST",
            "/api/v1/diagnose",
            {
                "plane": "remote",
                "source": "diag-src",
                "destination": "diag-host",
                "service": "diag-ssh",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, diagnosis)
        layers = {item["layer"]: item for item in diagnosis["layers"]}
        self.assertEqual(layers["policy"]["status"], "HEALTHY")
        self.assertEqual(layers["managed_host"]["status"], "HEALTHY")
        self.assertEqual(layers["remote_service"]["status"], "HEALTHY")
        self.assertEqual(layers["target_reachability"]["status"], "HEALTHY")
        self.assertFalse(diagnosis["network_probe_performed"])
        self.assertTrue(diagnosis["side_effect_free"])
        check = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(check.current_revision(), revision)
        finally:
            check.close()

        status, _, live = self.request(
            "GET", "/api/v1/live-access?plane=remote&limit=10"
        )
        self.assertEqual(status, 200, live)
        self.assertEqual(live["fidelity"], "UNKNOWN")
        self.assertIsNone(live["active_count"])
        self.assertIn("official FRP", live["reason"])

        cutoff_body = {
            "plane": "remote",
            "scope_kind": "plane",
            "operation": "apply",
            "reason": "web-test",
        }
        status, _, _ = self.request(
            "POST", "/api/v1/emergency-cutoff/preview", cutoff_body
        )
        self.assertEqual(status, 403)

        status, _, preview = self.request(
            "POST",
            "/api/v1/emergency-cutoff/preview",
            cutoff_body,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        self.assertFalse(preview["currently_active"])
        self.assertTrue(preview["desired_active"])
        self.assertFalse(preview["active_sessions_terminated"])

        status, _, wrong = self.request(
            "POST",
            "/api/v1/emergency-cutoff/apply",
            {
                "operation": "apply",
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "APPLY",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, wrong)

        status, _, applied = self.request(
            "POST",
            "/api/v1/emergency-cutoff/apply",
            {
                "operation": "apply",
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "CONFIRM CUTOFF",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        self.assertTrue(applied["active"])
        self.assertFalse(applied["active_sessions_terminated"])

        status, _, active_cutoffs = self.request(
            "GET", "/api/v1/emergency-cutoffs?plane=remote"
        )
        self.assertEqual(status, 200, active_cutoffs)
        self.assertEqual(active_cutoffs["count"], 1)
        self.assertEqual(active_cutoffs["returned"], 1)
        self.assertEqual(active_cutoffs["items"][0]["scope_kind"], "plane")

        status, _, overview = self.request("GET", "/api/v1/overview")
        self.assertEqual(status, 200, overview)
        cutoff_attention = next(
            item
            for item in overview["attention"]["items"]
            if item["kind"] == "emergency-cutoff"
        )
        self.assertEqual(cutoff_attention["severity"], "critical")

        status, _, blocked = self.request(
            "POST",
            "/api/v1/diagnose",
            {
                "plane": "remote",
                "source": "diag-src",
                "destination": "diag-host",
                "service": "diag-ssh",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, blocked)
        cutoff_layer = next(
            item for item in blocked["layers"] if item["layer"] == "emergency_cutoff"
        )
        self.assertEqual(cutoff_layer["status"], "FAILED")

        status, _, clear_preview = self.request(
            "POST",
            "/api/v1/emergency-cutoff/preview",
            {
                "plane": "remote",
                "scope_kind": "plane",
                "operation": "clear",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, clear_preview)
        status, _, cleared = self.request(
            "POST",
            "/api/v1/emergency-cutoff/apply",
            {
                "operation": "clear",
                "change_plan_id": clear_preview["change_plan_id"],
                "confirmation": "CONFIRM CUTOFF",
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, cleared)
        self.assertFalse(cleared["active"])
        status, _, recovered = self.request(
            "GET", "/api/v1/emergency-cutoffs?plane=remote"
        )
        self.assertEqual(status, 200, recovered)
        self.assertEqual(recovered["count"], 0)
        self.assertEqual(recovered["items"], [])

    def test_system_status_certificate_preflight_and_backup_validate(self):
        self.login()

        status, _, system = self.request("GET", "/api/v1/system")
        self.assertEqual(status, 200, system)
        self.assertTrue(system["read_only"])
        self.assertEqual(system["identity"]["project_version"], "3.0.0")
        self.assertNotIn("raw", system["certificate"])
        self.assertNotIn("active_key_path", system["certificate"])

        status, _, _ = self.request(
            "POST", "/api/v1/system/certificate/preflight", {}
        )
        self.assertEqual(status, 403)

        status, _, preflight = self.request(
            "POST",
            "/api/v1/system/certificate/preflight",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, preflight)
        self.assertIn("hostname", preflight["error"].lower())

        status, _, validation = self.request(
            "POST",
            "/api/v1/system/backup/validate",
            {"path": "/var/lib/drlink/backups/not-present.tar.gz"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, validation)
        self.assertFalse(validation["valid"])
        self.assertFalse(validation["authoritative_mutation"])

    def test_no_generic_management_mutation_endpoint(self):
        self.login()
        status, _, _ = self.request(
            "POST",
            "/api/v1/drlink_temporary_access_apply",
            {"change_plan_id": "cp_x", "confirmation": "APPLY"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400)

    def test_web_health_does_not_call_core_health(self):
        # Healthz is listener/process health and must remain distinct from Core health.
        original = self.server.app.adapter.invoke
        self.server.app.adapter.invoke = lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("core unavailable")
        )
        try:
            status, _, payload = self.request("GET", "/healthz")
            self.assertEqual(status, 200)
            self.assertEqual(payload["status"], "ok")
        finally:
            self.server.app.adapter.invoke = original


if __name__ == "__main__":
    unittest.main()
