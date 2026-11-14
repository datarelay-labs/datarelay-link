#!/usr/bin/env python3
"""OBS-P005 / P-023 regression: NewUserConn authorization must not run a full SQLite scan per connection.

Evidence (claude-run-20261112, installed build 02a1e498): relay new-connection rate plateaued at ~30-43 CPS and
collapsed to ~24 CPS with 3.7% client timeouts under combined load. Server-side sampling showed the access plugin
burning 35-58 ms CPU per connection (frps ~10%); a local profile showed 94% of that is `PRAGMA integrity_check` +
`foreign_key_check` executed by ControlPlane.status() on EVERY request, and its cost grows with the control DB
(`revision_snapshots` makes up ~85% of the 8.3 MB production DB and grows with every config revision).

Contract kept: the first request, every DB/WAL file change, and a bounded periodic recheck still run the full
fail-closed scan; unchanged-DB requests only do the cheap revision/generation check.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))


def load_plugin():
    path = ROOT / "server" / "frp-access-plugin.py"
    spec = importlib.util.spec_from_file_location("frp_access_plugin_hotpath", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AccessPluginIntegrityHotPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved_env = os.environ.get("FRP_DEPLOY_TEST_ROOT")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = str(self.root)
        self.cfg = self.root / "etc/drlink/config.json"
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text(json.dumps({"egress_listen_addr": "127.0.0.1", "egress_listen_port": 6102}) + "\n")
        self.CP = importlib.import_module("drlink_control_plane")
        self.drlink_v24 = importlib.import_module("drlink_v24")
        self._commit("seed-a")
        self.plugin = load_plugin()
        self.plugin.ACCESS_INTEGRITY_RECHECK_SECONDS = 60.0  # opt-in fast path under test; default (0) is covered below
        self.cache = self.plugin.PolicyCache(self.cfg)
        handler = self.plugin.make_handler(self.cache, "/access-auth")
        self.server = self.plugin.AccessServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.calls = []
        self.orig_check = self.CP.integrity_check

        def counting(conn):
            self.calls.append(1)
            return self.orig_check(conn)

        self.CP.integrity_check = counting

    def tearDown(self):
        self.CP.integrity_check = self.orig_check
        self.server.shutdown()
        self.server.server_close()
        if self.saved_env is None:
            os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        else:
            os.environ["FRP_DEPLOY_TEST_ROOT"] = self.saved_env
        self.tmp.cleanup()

    def _commit(self, name):
        """A real policy mutation through the public control-plane API (changes DB/WAL files + revision)."""
        plane = self.CP.ControlPlane(str(self.root))
        try:
            self.drlink_v24.set_network_object(plane, name, type="ip", value="127.0.0.1", oneshot=True)
            plane.compile_runtime()
        finally:
            plane.close()

    def _request(self):
        body = json.dumps({"op": "NewUserConn", "content": {"proxy_name": "no-such-proxy", "remote_addr": "203.0.113.9:4000"}})
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/access-auth?op=NewUserConn", body, {"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            self.assertEqual(resp.status, 200)
            return data
        finally:
            conn.close()

    def test_unchanged_db_runs_one_full_scan_for_many_connections(self):
        for _ in range(8):
            self.assertTrue(self._request()["reject"])  # unmapped proxy: rejected, but only after the health gate
        self.assertEqual(len(self.calls), 1, "full integrity scan ran %d times for 8 unchanged-DB connections" % len(self.calls))

    def test_db_change_triggers_exactly_one_more_full_scan(self):
        self._request()
        self._request()
        self.assertEqual(len(self.calls), 1)
        self._commit("seed-b")
        self._request()
        self._request()
        self.assertEqual(len(self.calls), 2, "a committed policy change must be re-validated once, then cached")

    def test_failed_scan_fails_closed_and_is_not_cached_as_valid(self):
        self._request()
        self._commit("seed-c")

        def broken(conn):
            self.calls.append(1)
            raise self.CP.DatabaseCorruptError("simulated corruption")

        self.CP.integrity_check = broken
        first = self._request()
        second = self._request()
        for data in (first, second):
            self.assertTrue(data["reject"])
            self.assertNotEqual(data.get("reject_reason"), "unmapped proxy",
                                "corrupt DB must be denied by the health gate, not fall through to policy lookup")
        self.assertGreaterEqual(len(self.calls), 3, "an unhealthy result must not be remembered as validated")
        self.CP.integrity_check = self.orig_check
        healed = self._request()
        self.assertTrue(healed["reject"])  # unmapped proxy again, i.e. the health gate passed

    def test_default_is_strict_one_scan_per_connection(self):
        """Unset/0 keeps the existing contract (also asserted by test-access-control)."""
        self.plugin.ACCESS_INTEGRITY_RECHECK_SECONDS = 0.0
        for _ in range(4):
            self._request()
        self.assertEqual(len(self.calls), 4, "interval 0 must scan every connection (strict default)")
        self.assertEqual(float(os.environ.get("FRP_ACCESS_INTEGRITY_RECHECK_SECONDS", "0") or 0), 0.0)
        fresh_plugin = load_plugin()
        self.assertEqual(fresh_plugin.ACCESS_INTEGRITY_RECHECK_SECONDS, 0.0, "shipped default must stay strict")

    def test_stale_validation_is_rescanned_after_interval(self):
        """The opt-in window is bounded: once older than the interval the full scan runs again."""
        self.plugin.ACCESS_INTEGRITY_RECHECK_SECONDS = 0.2
        self._request()
        self._request()
        self.assertEqual(len(self.calls), 1)
        import time as _t
        _t.sleep(0.3)
        self._request()
        self.assertEqual(len(self.calls), 2, "a validation older than the interval must be repeated")


if __name__ == "__main__":
    unittest.main()
