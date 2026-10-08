#!/usr/bin/env python3
"""Real HTTP-loopback acceptance for bounded Service Account automation."""
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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_service_accounts import ServiceAccountStore
from drlink_web_auth import WebAuthService, totp_code
from drlink_web_service import create_server


class AutomationHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-auto-http-")
        self.root = self.tmp.name
        self._env = patch.dict(os.environ, {"DRLINK_SKIP_ACTIVATION": "1", "DRLINK_WEB_QUIET": "1",
                                         "FRP_DEPLOY_TEST_ROOT": self.root})
        self._env.start()
        conf = Path(self.root, "etc/drlink")
        conf.mkdir(parents=True, exist_ok=True)
        (conf / "config.json").write_text('{"role":"server"}\n')
        (conf / "version").write_text("PROJECT_VERSION=3.0.0\n")
        with WebAuthService(self.root) as auth:
            material = auth.prepare_mfa_material("admin")
            code, _ = totp_code(material["totp_secret"], at=datetime.now(timezone.utc))
            auth.create_first_admin(
                username="admin", password="ValidPass1",
                totp_secret=material["totp_secret"],
                recovery_codes=material["recovery_codes"], totp_value=code,
                now=datetime.now(timezone.utc),
            )
            self.recovery_code = material["recovery_codes"][0]
        self.server = create_server(root=self.root, listen="127.0.0.1", port=0,
                                    static_root=str(ROOT / "web/dist"))
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self._env.stop()
        self.tmp.cleanup()

    def request(self, method, path, body=None, *, token=None, browser=False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=6)
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if browser:
            headers["Cookie"] = self.cookie
            headers["X-CSRF-Token"] = self.csrf
        if body is not None:
            raw = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        else:
            raw = None
        conn.request(method, path, body=raw, headers=headers)
        response = conn.getresponse()
        payload = json.loads(response.read().decode())
        h = dict(response.getheaders())
        status = response.status
        conn.close()
        return status, payload, h

    def login(self):
        status, payload, hdr = self.request("POST", "/api/v1/auth/login", {
            "username": "admin", "password": "ValidPass1", "recovery_code": self.recovery_code,
        })
        self.assertEqual(status, 200, payload)
        self.cookie = hdr["Set-Cookie"].split(";", 1)[0]
        self.csrf = payload["csrf_token"]

    def test_end_to_end_admin_lifecycle_read_only_scope_and_rate(self):
        self.login()
        status, created, _ = self.request(
            "POST", "/api/v1/service-accounts", {
                "name": "ci-reader", "permissions": ["management-read"],
            }, browser=True,
        )
        self.assertEqual(status, 200, created)
        token = created["credential"]
        self.assertTrue(token.startswith("drlink_sa_"))

        status, listing, _ = self.request("GET", "/api/v1/service-accounts", browser=True)
        self.assertEqual(status, 200, listing)
        self.assertEqual(len(listing["items"]), 1)
        self.assertNotIn(token, json.dumps(listing))
        self.assertEqual(listing["items"][0]["permissions"], ["management-read"])

        route = "/api/automation/v1/drlink_inventory_list"
        status, payload, _ = self.request(
            "POST", route, {"resource_type": "managed-host", "limit": 5}, token=token)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["resource_type"], "managed-host")

        status, payload, _ = self.request(
            "POST", route, {"resource_type": "managed-host"}, token="drlink_sa_invalid")
        self.assertEqual(status, 401, payload)
        status, payload, _ = self.request(
            "POST", "/api/automation/v1/drlink_policy_test",
            {"plane": "remote", "source": "a", "destination": "b"}, token=token)
        self.assertEqual(status, 403, payload)
        status, _, _ = self.request(
            "POST", "/api/automation/v1/drlink_agent_update_rollout_start", {}, token=token)
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", route, token=token)
        self.assertEqual(status, 405)
        status, _, _ = self.request("POST", route, {"resource_type": "managed-host"})
        self.assertEqual(status, 401)

        # The count is persisted across fresh request handlers, not just a process-local dict.
        with patch("drlink_service_accounts.MAX_REQUESTS_PER_MINUTE", 3):
            status, _, _ = self.request(
                "POST", route, {"resource_type": "managed-host"}, token=token)
            self.assertEqual(status, 200)
            status, _, _ = self.request(
                "POST", route, {"resource_type": "managed-host"}, token=token)
            self.assertEqual(status, 429)

        status, rotated, _ = self.request(
            "POST", "/api/v1/service-accounts/rotate", {"account_id": created["id"]},
            browser=True,
        )
        self.assertEqual(status, 200, rotated)
        status, _, _ = self.request(
            "POST", route, {"resource_type": "managed-host"}, token=token)
        self.assertEqual(status, 401)
        status, payload, _ = self.request(
            "POST", route, {"resource_type": "managed-host"}, token=rotated["credential"])
        self.assertEqual(status, 200, payload)
        status, hygiene_web, _ = self.request(
            "GET", "/api/v1/access-hygiene", browser=True)
        self.assertEqual(status, 200, hygiene_web)
        status, hygiene_api, _ = self.request(
            "POST", "/api/automation/v1/drlink_access_hygiene", {},
            token=rotated["credential"])
        self.assertEqual(status, 200, hygiene_api)
        self.assertTrue(hygiene_api["read_only"])
        self.assertFalse(hygiene_api["auto_mutation"])
        self.assertEqual(hygiene_api["items"], hygiene_web["items"])
        status, revoked, _ = self.request(
            "POST", "/api/v1/service-accounts/revoke", {"account_id": created["id"]},
            browser=True,
        )
        self.assertEqual(status, 200, revoked)
        status, _, _ = self.request(
            "POST", route, {"resource_type": "managed-host"}, token=rotated["credential"])
        self.assertEqual(status, 401)
        with ServiceAccountStore(self.root) as store:
            actions = [str(r[0]) for r in store.conn.execute(
                "SELECT event_type FROM audit_events WHERE entity_type='service-account'"
            ).fetchall()]
            self.assertIn("service_account.created", actions)
            self.assertIn("service_account.rotated", actions)
            self.assertIn("service_account.revoked", actions)
            self.assertIn("service_account.request.allowed", actions)
            self.assertIn("service_account.request.denied", actions)
            self.assertIn("service_account.request_limited", actions)
            self.assertNotIn(token.encode(), Path(self.root, "var/lib/drlink/drlink.db").read_bytes())

    def test_webhook_admin_http_lifecycle_and_private_secret_inventory(self):
        self.login()
        status, created, _ = self.request(
            "POST", "/api/v1/webhooks",
            {"name": "ops-alert", "url": "https://hooks.example.com/alerts",
             "event_classes": ["attention"]}, browser=True,
        )
        self.assertEqual(status, 200, created)
        self.assertTrue(created["secret"].startswith("drlink_wh_"))
        status, listed, _ = self.request("GET", "/api/v1/webhooks", browser=True)
        self.assertEqual(status, 200, listed)
        self.assertEqual(len(listed["items"]), 1)
        self.assertNotIn(created["secret"], json.dumps(listed))
        self.assertEqual(listed["items"][0]["url"], "https://hooks.example.com/alerts")
        status, rotated, _ = self.request(
            "POST", "/api/v1/webhooks/rotate", {"webhook_id": created["id"]},
            browser=True,
        )
        self.assertEqual(status, 200, rotated)
        self.assertNotEqual(rotated["secret"], created["secret"])
        status, denied, _ = self.request(
            "POST", "/api/v1/webhooks",
            {"name": "unsafe", "url": "https://127.0.0.1/callback",
             "event_classes": ["attention"]}, browser=True,
        )
        self.assertEqual(status, 400, denied)
        status, _, _ = self.request(
            "POST", "/api/v1/webhooks/disable", {"webhook_id": created["id"]},
            browser=True,
        )
        self.assertEqual(status, 200)
        status, listed, _ = self.request("GET", "/api/v1/webhooks", browser=True)
        self.assertFalse(listed["items"][0]["enabled"])
        status, _, _ = self.request(
            "POST", "/api/v1/webhooks",
            {"name": "bad", "url": "http://hooks.example.com",
             "event_classes": ["attention"]},
        )
        self.assertEqual(status, 403)
        from drlink_webhooks import WebhookStore
        with WebhookStore(self.root) as store:
            db = Path(self.root, "var/lib/drlink/drlink.db").read_bytes()
            self.assertNotIn(created["secret"].encode(), db)
            self.assertNotIn(rotated["secret"].encode(), db)
            self.assertTrue(store.key_file.is_file())
            events = [row[0] for row in store.conn.execute(
                "SELECT event_type FROM audit_events WHERE entity_type='management-webhook'"
            ).fetchall()]
            for expected in ("management_webhook.created", "management_webhook.rotated",
                             "management_webhook.disabled"):
                self.assertIn(expected, events)

    def test_without_browser_csrf_create_is_denied(self):
        status, _, _ = self.request("POST", "/api/v1/service-accounts", {
            "name": "unsafe", "permissions": ["management-read"]})
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", "/api/v1/service-accounts")
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
