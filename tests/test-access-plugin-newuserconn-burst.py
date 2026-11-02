#!/usr/bin/env python3
"""P-006: real HTTP NewUserConn 64-request burst against bounded AccessServer.

This isolates plugin admission, not an end-to-end FRP relay or database speed.
The cache is intentionally paused so all 64 authorization requests overlap.
"""
from __future__ import annotations

import collections
import concurrent.futures
import http.client
import importlib.util
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
spec = importlib.util.spec_from_file_location("access_plugin_burst", ROOT / "server/frp-access-plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class FakePlane:
    def close(self):
        pass


class HeldCache:
    def __init__(self):
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def open_isolated(self):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            # Deliberately hold authorizers while a bounded microburst arrives.
            threading.Event().wait(0.75)
        finally:
            with self.lock:
                self.active -= 1
        return FakePlane(), None, {}


class NewUserConnBurstTests(unittest.TestCase):
    def test_64_overlapping_valid_newuserconn_requests_are_not_capacity_rejected(self):
        cache = HeldCache()
        server = plugin.AccessServer(("127.0.0.1", 0), plugin.make_handler(cache, "/access-auth"))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        barrier = threading.Barrier(65)
        payload = json.dumps({
            "op": "NewUserConn",
            "content": {"proxy_name": "e2e-p006", "remote_addr": "198.51.100.10:5000"}
        }).encode("utf-8")

        def request(_):
            barrier.wait(timeout=10)
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=12)
            try:
                connection.request("POST", "/access-auth?op=NewUserConn", body=payload,
                                   headers={"Content-Type": "application/json"})
                result = connection.getresponse()
                return (result.status, json.loads(result.read().decode()))
            except Exception as exc:
                return ("transport-error", {"error": type(exc).__name__})
            finally:
                connection.close()

        try:
            # Audit payloads are not part of this admission-capacity experiment.
            with mock.patch.object(plugin.RP, "authorize_remote", return_value={"decision": plugin.RP.DECISION_ALLOW}), \
                 mock.patch.object(plugin.ACL, "emit_conn_log", return_value=None):
                with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
                    futures = [pool.submit(request, i) for i in range(64)]
                    barrier.wait(timeout=10)
                    answers = [f.result(timeout=15) for f in futures]
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

        statuses = collections.Counter(str(status) for status, _ in answers)
        print("P006_ISOLATED_PLUGIN_NEWUSERCONN_BURST=" + json.dumps({
            "attempted": 64, "admitted": sum(status == 200 and not body.get("reject") for status, body in answers),
            "statuses": dict(statuses), "active_peak": cache.peak,
            "configured_slots": server.max_concurrent,
        }, sort_keys=True))
        self.assertEqual(len(answers), 64)
        self.assertEqual(
            sum(status == 200 and not body.get("reject") for status, body in answers), 64,
            "normal 64-request burst must not be rejected solely by plugin admission capacity"
        )


class NewUserConnRealSQLiteBurstTests(unittest.TestCase):
    def test_64_policy_reads_through_production_access_server(self):
        """Exercise real SQLite policy checks and reject semantics under 64-client pressure."""
        import os
        spec = importlib.util.spec_from_file_location(
            "access_fixture_test", ROOT / "tests/test-access-control.py"
        )
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        fixture = fixtures.PolicyCacheFailClosedTests(
            "test_concurrent_newuserconn_sqlite_isolation"
        )
        fixture.setUp()
        try:
            import drlink_v24
            from drlink_control_plane import ControlPlane
            policy = ControlPlane(str(fixture.root))
            try:
                drlink_v24.ensure_policy_mode(policy, "remote", "whitelist", oneshot=True)
            finally:
                policy.close()
            fixture.cache.reload(force=True)
            server = fixture.plugin.AccessServer(
                ("127.0.0.1", 0),
                fixture.plugin.make_handler(fixture.cache, "/access-auth")
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            barrier = threading.Barrier(65)
            proxy = fixture.RP.expected_proxy_name("alpha-host", fixture.mid, "ssh")

            def request(i):
                allow = (i % 2 == 0)
                source = "198.51.100.9" if allow else "203.0.113.9"
                payload = json.dumps({
                    "op": "NewUserConn",
                    "content": {"proxy_name": proxy, "remote_addr": source + ":" + str(20000 + i)}
                }).encode()
                barrier.wait(timeout=10)
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=20
                )
                try:
                    connection.request(
                        "POST", "/access-auth?op=NewUserConn", body=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    reply = connection.getresponse()
                    return allow, reply.status, json.loads(reply.read().decode())
                finally:
                    connection.close()

            try:
                with mock.patch.object(fixture.plugin.ACL, "emit_conn_log", return_value=None):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
                        futures = [pool.submit(request, i) for i in range(64)]
                        barrier.wait(timeout=10)
                        answers = [f.result(timeout=24) for f in futures]
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

            counts = collections.Counter(
                ("allow" if allowed else "deny") if status == 200 and
                (body.get("reject") is False) == allowed else "unexpected"
                for allowed, status, body in answers
            )
            print("P006_REAL_SQLITE_PLUGIN_BURST=" +
                  json.dumps({"attempted": 64, "results": dict(counts)}, sort_keys=True))
            self.assertEqual(counts, {"allow": 32, "deny": 32})
        finally:
            fixture.tearDown()
            os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)


if __name__ == "__main__":
    unittest.main()
