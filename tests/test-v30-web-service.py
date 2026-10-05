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
            "/api/v1/audit?limit=10",
            "/api/v1/revisions?limit=10",
            "/api/v1/health",
            "/api/v1/saved-views",
            "/api/v1/sessions",
        ):
            status, _, payload = self.request("GET", path)
            self.assertEqual(status, 200, (path, payload))

        status, _, versions = self.request("GET", "/api/v1/versions")
        self.assertEqual(status, 200)
        self.assertEqual(versions["server_version"], "3.0.0")
        self.assertEqual(versions["drift_count"], 1)

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
