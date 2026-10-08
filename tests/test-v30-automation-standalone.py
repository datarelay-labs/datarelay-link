#!/usr/bin/env python3
"""Real HTTP acceptance of independent Automation adapter without Web server."""
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_automation_server import create_server
from drlink_control_db import ControlPlaneError
from drlink_service_accounts import ServiceAccountStore


class IndependentAutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-standalone-auto-")
        self.server = create_server(root=self.tmp.name, listen="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        with ServiceAccountStore(self.tmp.name) as store:
            self.credential = store.create("reader", ["management-read"])["credential"]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, method, path, data=None, credential=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"Content-Type": "application/json"}
        if credential is not None:
            headers["Authorization"] = "Bearer " + credential
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        payload = json.loads(response.read())
        result = response.status
        conn.close()
        return result, payload

    def test_independent_listener_authorization_and_resource_bounds(self):
        status, payload = self.request("GET", "/healthz")
        self.assertEqual((status, payload["service"]), (200, "drlink-automation"))
        status, problem = self.request("GET", "/api/v1/service-accounts")
        self.assertEqual(status, 405)
        self.assertEqual(problem["code"], "METHOD_NOT_ALLOWED")
        status, payload = self.request("POST",
             "/api/automation/v1/drlink_inventory_list",
             {"resource_type": "managed-host"}, credential=self.credential)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["resource_type"], "managed-host")
        status, problem = self.request("POST", "/api/automation/v1/drlink_inventory_list",
                                 {"resource_type": "managed-host"})
        self.assertEqual(status, 401)
        self.assertEqual(problem["code"], "UNAUTHENTICATED")
        status, problem = self.request("POST", "/api/automation/v1/drlink_policy_test",
                                 {"plane": "remote", "source": "a", "destination": "b"},
                                 credential=self.credential)
        self.assertEqual(status, 403)
        self.assertEqual(problem["code"], "OPERATION_DENIED")
        status, _ = self.request("POST",
                                 "/api/automation/v1/drlink_agent_update_rollout_start",
                                 {}, credential=self.credential)
        self.assertEqual(status, 403)
        self.assertTrue(self.server.concurrent.acquire(blocking=False))
        try:
            status, _ = self.request("POST", "/api/automation/v1/drlink_inventory_list",
                                     {"resource_type": "managed-host"}, credential=self.credential)
            # Only one permit was acquired; normal requests still have capacity.
            self.assertEqual(status, 200)
        finally:
            self.server.concurrent.release()

    def test_error_codes_remain_secret_safe_for_invalid_payload_and_route(self):
        status, bad_route = self.request(
            "POST", "/api/automation/v1/not-published?secret=do-not-echo",
            {"resource_type": "managed-host"}, credential=self.credential,
        )
        self.assertEqual(status, 404)
        self.assertEqual(bad_route["code"], "NOT_FOUND")
        self.assertNotIn("do-not-echo", json.dumps(bad_route))

        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(
                "POST", "/api/automation/v1/drlink_inventory_list",
                body=b"{not-valid-json}",
                headers={
                    "Authorization": "Bearer " + self.credential,
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            problem = json.loads(response.read())
            self.assertEqual(response.status, 400)
            self.assertEqual(problem["code"], "INVALID_REQUEST")
            self.assertNotIn(self.credential, json.dumps(problem))
        finally:
            connection.close()

    def test_remote_bind_requires_tls(self):
        with self.assertRaises(ControlPlaneError):
            create_server(root=self.tmp.name, listen="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
