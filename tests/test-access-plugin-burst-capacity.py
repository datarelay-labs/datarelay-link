#!/usr/bin/env python3
"""F-008 regression: a burst of new Remote Service user connections must not be rejected.

P-006 (claude-run-20261112) showed that ~300 simultaneous new connections through
a Relay Remote Service lost 50% of connections: the frps access plugin
(NewUserConn authorization) answered HTTP 503 "server busy" once its small
worker bound (32) and TCP backlog were exhausted. Authorization latency is a
few milliseconds, so the default capacity must absorb a realistic burst while
overload beyond the bound still fails closed (covered by test-access-control).
"""
from __future__ import annotations

import importlib.util
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    path = ROOT / "server" / "frp-access-plugin.py"
    spec = importlib.util.spec_from_file_location("frp_access_plugin_burst", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AccessPluginBurstCapacityTests(unittest.TestCase):
    BURST = 300

    def test_default_capacity_absorbs_burst_without_503(self):
        plugin = load_plugin()
        self.assertIsNotNone(plugin.AccessServer)

        class FakePlane:
            def status(self):
                return {"clients": 1, "services": 1}

            def close(self):
                pass

        class SlowCache:
            def open_isolated(self):
                time.sleep(0.02)  # authorization/DB latency per request
                return FakePlane(), None, {}

        handler = plugin.make_handler(SlowCache(), "/access-auth")
        server = plugin.AccessServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        barrier = threading.Barrier(self.BURST)

        def one():
            barrier.wait(10)
            conn = HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                conn.request("GET", "/healthz")
                resp = conn.getresponse()
                resp.read()
                return resp.status
            except OSError:
                return -1
            finally:
                conn.close()

        try:
            with ThreadPoolExecutor(max_workers=self.BURST) as pool:
                statuses = [f.result() for f in [pool.submit(one) for _ in range(self.BURST)]]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        bad = [s for s in statuses if s != 200]
        self.assertEqual(
            bad, [], "%d/%d burst connections rejected: %r" % (len(bad), self.BURST, sorted(set(bad)))
        )
        self.assertGreaterEqual(plugin.ACCESS_MAX_CONCURRENT, self.BURST)


if __name__ == "__main__":
    unittest.main()
