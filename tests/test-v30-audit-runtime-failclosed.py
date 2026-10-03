#!/usr/bin/env python3
from __future__ import annotations

import http.client
import importlib.util
import json
import socket
import sys
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
SERVER = ROOT / "server"
sys.path.insert(0, str(LIB))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class AuditFailClosedRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.access = _load("test_v30_access_plugin", SERVER / "frp-access-plugin.py")
        cls.gateway = _load("test_v30_egress_gateway", SERVER / "frp-egress-gateway.py")
        cls.tcp = _load("test_v30_tcp_egress", SERVER / "drlink-tcp-egress.py")

    def test_egress_gateway_helper_converts_allow_to_deny(self):
        original = self.gateway.EG.emit_durable_access_audit
        try:
            self.gateway.EG.emit_durable_access_audit = (
                lambda *_a, **_k: (_ for _ in ()).throw(OSError("spool down"))
            )
            decision = self.gateway._durably_audit_new_decision(
                {
                    "decision": self.gateway.EG.DECISION_ALLOW,
                    "reason": "POLICY_ALLOW",
                    "authorized_candidates": ["93.184.216.34"],
                },
                {},
            )
            self.assertEqual(decision["decision"], self.gateway.EG.DECISION_DENY)
            self.assertEqual(decision["reason"], "AUDIT_UNAVAILABLE")
            self.assertEqual(decision["authorized_candidates"], [])

            denied = self.gateway._durably_audit_new_decision(
                {
                    "decision": self.gateway.EG.DECISION_DENY,
                    "reason": "POLICY_DENY",
                },
                {},
            )
            self.assertEqual(denied["decision"], self.gateway.EG.DECISION_DENY)
            self.assertEqual(denied["reason"], "POLICY_DENY")
        finally:
            self.gateway.EG.emit_durable_access_audit = original

    def test_remote_plugin_durable_failure_rejects_would_be_allow(self):
        module = self.access

        class DummyPlane:
            def close(self):
                pass

        class DummyCache:
            def open_isolated(self):
                return DummyPlane(), None, {}

        original_auth = module.RP.authorize_remote
        original_durable = module.ACL.emit_durable_access_audit
        original_legacy = module.ACL.emit_conn_log
        server = None
        thread = None
        try:
            module.RP.authorize_remote = lambda *_a, **_k: {
                "decision": module.RP.DECISION_ALLOW,
                "reason": "REMOTE_ACCESS_ALLOW",
                "proxy_name": "alpha-ssh",
                "service_id": "svc-1",
                "client_id": "client-a",
                "source_ip": "198.51.100.10",
                "evaluation": {"winner": {"name": "allow-ssh"}},
            }
            module.ACL.emit_durable_access_audit = (
                lambda *_a, **_k: (_ for _ in ()).throw(OSError("spool down"))
            )
            module.ACL.emit_conn_log = lambda *_a, **_k: None

            handler = module.make_handler(DummyCache(), "/handler")
            server = module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            body = json.dumps(
                {
                    "op": "NewUserConn",
                    "content": {
                        "proxy_name": "alpha-ssh",
                        "remote_addr": "198.51.100.10:54321",
                    },
                }
            )
            conn = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=3
            )
            conn.request(
                "POST",
                "/handler?op=NewUserConn",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            conn.close()
            self.assertEqual(response.status, 200)
            self.assertTrue(payload["reject"])
            self.assertEqual(payload["reject_reason"], "AUDIT_UNAVAILABLE")
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=2)
            module.RP.authorize_remote = original_auth
            module.ACL.emit_durable_access_audit = original_durable
            module.ACL.emit_conn_log = original_legacy

    def test_fixed_tcp_durable_failure_stops_before_connect(self):
        module = self.tcp
        logged = []

        class Cache:
            def snapshot(self):
                return object(), None, {}, types.SimpleNamespace(generation=7)

        class State:
            cache = Cache()

            def release_source(self, _source):
                pass

            def release(self):
                pass

        original_auth = module.RP.authorize_fixed_tcp
        original_durable = module.EG.emit_durable_access_audit
        original_legacy = module.EG.emit_conn_log
        left, right = socket.socketpair()
        try:
            module.RP.authorize_fixed_tcp = lambda *_a, **_k: {
                "decision": module.RP.DECISION_ALLOW,
                "reason": "INTERNET_ACCESS_ALLOW",
                "hostname": "example.com",
                "port": 443,
                "relay_name": "api",
                "rule_name": "allow-api",
            }
            module.EG.emit_durable_access_audit = (
                lambda *_a, **_k: (_ for _ in ()).throw(OSError("spool down"))
            )
            module.EG.emit_conn_log = lambda event, **_k: logged.append(dict(event))

            module.handle_tcp_client(
                State(),
                left,
                ("198.51.100.10", 12345),
                "relay-1",
                admitted=True,
            )
            self.assertTrue(logged)
            self.assertEqual(logged[-1]["decision"], module.EG.DECISION_DENY)
            self.assertEqual(logged[-1]["reason"], "AUDIT_UNAVAILABLE")
        finally:
            try:
                right.close()
            except OSError:
                pass
            module.RP.authorize_fixed_tcp = original_auth
            module.EG.emit_durable_access_audit = original_durable
            module.EG.emit_conn_log = original_legacy


if __name__ == "__main__":
    unittest.main()
