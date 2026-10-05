#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
from drlink_management_drafts import DRAFT_ADMIN, DRAFT_OBSERVE, DRAFT_OPERATE
from drlink_web_auth import WebAuthService, WebPrincipal, permissions_for_role, totp_code
from drlink_web_service import create_server


class V30WebDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-web-draft-")
        os.environ["DRLINK_WEB_QUIET"] = "1"
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        plane = ControlPlane(self.tmp)
        plane.close()

        auth = WebAuthService(self.tmp)
        material = auth.prepare_mfa_material("admin")
        now = datetime.now(timezone.utc)
        code, _ = totp_code(material["totp_secret"], at=now)
        auth.create_first_admin(
            username="admin",
            password="correct horse battery staple",
            totp_secret=material["totp_secret"],
            recovery_codes=material["recovery_codes"],
            totp_value=code,
            now=now,
        )
        self.recovery_code = material["recovery_codes"][0]
        auth.close()

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

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        actual = {"Accept": "application/json"}
        if headers:
            actual.update(headers)
        if self.cookie:
            actual["Cookie"] = self.cookie
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            actual["Content-Type"] = "application/json"
            actual["Content-Length"] = str(len(data))
        conn.request(method, path, body=data, headers=actual)
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
        self.cookie = (headers.get("set-cookie") or "").split(";", 1)[0]
        self.csrf = payload["csrf_token"]
        self.operator_id = payload["operator"]["id"]

    def test_web_roles_map_to_core_draft_authority(self):
        cases = (
            ("Read Only", DRAFT_OBSERVE),
            ("Operator", DRAFT_OPERATE),
            ("Admin", DRAFT_ADMIN),
        )
        for role, expected in cases:
            with self.subTest(role=role):
                principal = WebPrincipal(
                    operator_id="wop-test",
                    username="test",
                    role=role,
                    permissions=permissions_for_role(role),
                    session_id="ws-test",
                )
                actor = self.server.app._actor(principal)
                self.assertEqual(self.server.app.adapter.core._draft_authority(actor), expected)

    def test_draft_test_diff_apply_and_configuration_export(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            revision = plane.current_revision()
        finally:
            plane.close()
        bundle = (
            "configurationBundle:\n"
            "  context: server\n"
            f"  sourceRevision: {revision}\n"
            "  networkObjects:\n"
            "    - name: web-office\n"
            "      type: ip\n"
            "      value: 198.51.100.99\n"
        )

        status, _, _ = self.request(
            "POST", "/api/v1/drafts", {"bundle_text": bundle}
        )
        self.assertEqual(status, 403)

        status, _, draft = self.request(
            "POST",
            "/api/v1/drafts",
            {"bundle_text": bundle},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, draft)
        draft_id = draft["id"]

        status, _, tested = self.request(
            "POST",
            f"/api/v1/drafts/{draft_id}/test",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, tested)
        self.assertEqual(tested["status"], "PASS")
        self.assertTrue(tested["valid"])
        self.assertFalse(tested["no_change"])
        self.assertEqual(tested["change_count"], 1)
        self.assertFalse(tested["authoritative_mutation"])

        status, _, preview = self.request(
            "POST",
            f"/api/v1/drafts/{draft_id}/diff",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, preview)
        self.assertFalse(preview["no_change"])
        self.assertEqual(preview["diff_result"], "CHANGES_PENDING")
        self.assertEqual(preview["changes"][0]["kind"], "network-object")
        self.assertFalse(preview["authoritative_mutation"])

        plane = ControlPlane(self.tmp)
        try:
            self.assertIsNone(plane.get_object("web-office"))
            self.assertEqual(plane.current_revision(), revision)
        finally:
            plane.close()

        status, _, exported = self.request(
            "GET", f"/api/v1/drafts/{draft_id}/export"
        )
        self.assertEqual(status, 200, exported)
        self.assertEqual(exported["bundle_text"], bundle)

        status, _, current_export = self.request(
            "GET", "/api/v1/configuration/export"
        )
        self.assertEqual(status, 200, current_export)
        self.assertTrue(current_export["redacted"])
        self.assertFalse(current_export["authoritative_mutation"])
        self.assertIn("configurationBundle:", current_export["bundle_text"])
        self.assertNotIn("web-office", current_export["bundle_text"])

        status, _, applied = self.request(
            "POST",
            f"/api/v1/drafts/{draft_id}/apply",
            {"change_plan_id": preview["change_plan_id"], "confirmation": "APPLY"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "APPLIED")

        plane = ControlPlane(self.tmp)
        try:
            self.assertIsNotNone(plane.get_object("web-office"))
            self.assertEqual(plane.current_revision(), revision + 1)
            revision_row = plane.conn.execute(
                "SELECT actor,command FROM config_revisions WHERE revision=?",
                (revision + 1,),
            ).fetchone()
            self.assertEqual(
                revision_row["actor"], "web:%s" % self.operator_id
            )
            self.assertTrue(
                revision_row["command"].startswith("web draft apply draft_")
            )
            audit_row = plane.conn.execute(
                "SELECT actor_id,interface,action FROM audit_events "
                "WHERE revision=? AND entity_type='configuration-bundle' "
                "ORDER BY id DESC LIMIT 1",
                (revision + 1,),
            ).fetchone()
            self.assertEqual(
                audit_row["actor_id"], "web:%s" % self.operator_id
            )
            self.assertEqual(audit_row["interface"], "WEB")
            self.assertTrue(audit_row["action"].startswith("web draft apply draft_"))
        finally:
            plane.close()

        status, _, applied_export = self.request(
            "GET", "/api/v1/configuration/export"
        )
        self.assertEqual(status, 200, applied_export)
        self.assertIn("web-office", applied_export["bundle_text"])
        self.assertIn(
            f"sourceRevision: {revision + 1}", applied_export["bundle_text"]
        )

    def test_invalid_bundle_test_is_fail_closed_and_zero_mutation(self):
        self.login()
        plane = ControlPlane(self.tmp)
        try:
            revision = plane.current_revision()
        finally:
            plane.close()
        bad = (
            "configurationBundle:\n"
            "  context: server\n"
            f"  sourceRevision: {revision}\n"
            "  networkObjects:\n"
            "    - name: bad-object\n"
            "      type: cidr\n"
            "      value: definitely-not-a-cidr\n"
        )
        status, _, draft = self.request(
            "POST",
            "/api/v1/drafts",
            {"bundle_text": bad},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 200, draft)
        status, _, result = self.request(
            "POST",
            f"/api/v1/drafts/{draft['id']}/test",
            {},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(status, 400, result)
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision)
            self.assertIsNone(plane.get_object("bad-object"))
        finally:
            plane.close()


    def test_http_layer_has_no_direct_draft_service_dependency(self):
        source = (ROOT / "lib/drlink_web_service.py").read_text(encoding="utf-8")
        self.assertNotIn("ManagementDraftService", source)
        self.assertNotIn(".conn.execute(", source)
        self.assertIn("adapter.draft_test", source)
        self.assertIn("adapter.draft_diff", source)
        self.assertIn("adapter.draft_preview", source)
        self.assertIn("adapter.draft_apply", source)
        self.assertIn("adapter.configuration_export", source)


if __name__ == "__main__":
    unittest.main()
