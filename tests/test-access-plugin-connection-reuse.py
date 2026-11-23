#!/usr/bin/env python3
"""Opt-in SQLite connection reuse for the NewUserConn access plugin (FRP_ACCESS_CONNECTION_REUSE).

Evidence (claude-run-20261112, installed build 7a9c7f3b, disposable host, per-request CPU of the strict path):
opening + closing a fresh read-only SQLite connection per authorization (connect, PRAGMAs, schema parse, close)
costs ~4.8 ms of a ~8.0 ms request; the same request on a reused connection costs ~3.2 ms. The complete integrity +
foreign-key scan (~2.2 ms) is still the largest remaining item and is NOT touched.

Contract pinned here:
* DEFAULT OFF. The shipped behaviour (a request-private connection that is closed after every request) is unchanged.
* Reuse keeps no policy, decision, revision or validation result. Every request still starts a fresh read
  transaction (a new WAL snapshot), runs the complete integrity + foreign-key scan, re-reads the revision and every
  plane generation and re-evaluates the policy. A policy change committed between two requests is visible to the
  very next request.
* A connection is returned to the pool only after a request that finished without error and without an open
  transaction; any error discards it. A replaced database file (restore / rollback) discards the pooled connection
  (the unlinked-inode hazard). The pool is bounded by the DB reader bound and never exceeds it.
* The DB reader slot is held only while a request uses the connection, never while it idles in the pool.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

NOW = "2026-11-17T00:00:00Z"


def load_plugin(env=None):
    saved = {}
    for key, value in (env or {}).items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        path = ROOT / "server" / "frp-access-plugin.py"
        spec = importlib.util.spec_from_file_location("frp_access_plugin_reuse", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ConnectionReuse(unittest.TestCase):
    reuse = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved_env = os.environ.get("FRP_DEPLOY_TEST_ROOT")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = str(self.root)
        self.cfg = self.root / "etc/drlink/config.json"
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text(json.dumps({"egress_listen_addr": "127.0.0.1", "egress_listen_port": 6102}) + "\n")
        self.CP = importlib.import_module("drlink_control_plane")
        self.DB = importlib.import_module("drlink_control_db")
        self.RP = importlib.import_module("drlink_runtime_policy")
        plane = self.CP.ControlPlane(str(self.root))
        try:
            plane.conn.execute(
                "INSERT INTO clients (id, label, hostname, created_at, updated_at) VALUES ('cid0001','lbl','reuse-host',?,?)",
                (NOW, NOW),
            )
            plane.conn.execute(
                "INSERT INTO published_services (id, client_id, name, service_type, target_mode, target_host,"
                " target_port, public_port, enabled, released, created_at, updated_at)"
                " VALUES ('svc1','cid0001','web','tcp','self','127.0.0.1',8080,6001,1,0,?,?)",
                (NOW, NOW),
            )
            plane.compile_runtime()
        finally:
            plane.close()
        self.db_file = self.DB.db_path(str(self.root))
        probe = self.CP.ControlPlane(str(self.root), read_only=True)
        try:
            self.proxy_name = next(iter(self.RP.build_proxy_map(probe)))
        finally:
            probe.close()

        self.plugin = load_plugin({"FRP_ACCESS_CONNECTION_REUSE": "1"} if self.reuse else None)
        self.cache = self.plugin.PolicyCache(self.cfg)
        handler = self.plugin.make_handler(self.cache, "/access-auth")
        self.server = self.plugin.AccessServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        self.opened = []
        self.scans = []
        self.PRP = self.plugin.RP  # the plugin's private module copy
        self.orig_plane = self.PRP.ControlPlane
        self.orig_authorize = self.PRP.authorize_remote
        self.orig_scan = self.CP.integrity_check
        outer = self

        class CountingPlane(self.orig_plane):
            def __init__(plane_self, *a, **k):
                outer.opened.append(1)
                super().__init__(*a, **k)

        def counting_scan(conn):
            outer.scans.append(1)
            return outer.orig_scan(conn)

        self.PRP.ControlPlane = CountingPlane
        self.CP.integrity_check = counting_scan

    def tearDown(self):
        self.PRP.ControlPlane = self.orig_plane
        self.PRP.authorize_remote = self.orig_authorize
        self.CP.integrity_check = self.orig_scan
        self.server.shutdown()
        self.server.server_close()
        drop = getattr(self.cache, "_drop_idle", None)
        if drop:
            drop()
        if self.saved_env is None:
            os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        else:
            os.environ["FRP_DEPLOY_TEST_ROOT"] = self.saved_env
        self.tmp.cleanup()

    def _request(self, proxy=None, settle=True):
        body = json.dumps({"op": "NewUserConn", "content": {"proxy_name": proxy or self.proxy_name, "remote_addr": "203.0.113.9:4000"}})
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/access-auth?op=NewUserConn", body, {"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            self.assertEqual(resp.status, 200)
        finally:
            conn.close()
        if settle:
            self._settle()
        return data

    def _settle(self):
        """Wait until every in-flight request has released its reader slot (release runs after the reply is sent)."""
        import time
        capacity = self.plugin.ACCESS_DB_MAX_CONCURRENT
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            idle = len(getattr(self.cache, "_idle", []))
            if self.cache._reader_slots._value + 0 == capacity:
                return
            time.sleep(0.005)

    def _idle(self):
        self._settle()
        return len(getattr(self.cache, "_idle", []))

    def _set_enabled(self, value):
        conn = sqlite3.connect(str(self.db_file))
        try:
            conn.execute("UPDATE published_services SET enabled = ? WHERE id = 'svc1'", (value,))
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    def test_default_is_off(self):
        self.assertFalse(load_plugin().ACCESS_CONNECTION_REUSE, "reuse must stay opt-in")


class ConnectionReuseDefaultOff(ConnectionReuse):
    reuse = False

    def test_shipped_default_closes_every_connection(self):
        for _ in range(4):
            self.assertFalse(self._request()["reject"])
        self.assertEqual(len(self.opened), 4, "default path must open one connection per request")
        self.assertEqual(self._idle(), 0)
        self.assertEqual(len(self.scans), 4)


class ConnectionReuseOn(ConnectionReuse):
    reuse = True

    def test_requests_share_one_connection(self):
        for _ in range(6):
            self.assertFalse(self._request()["reject"])
        self.assertEqual(len(self.opened), 1, "6 sequential requests must reuse one pooled connection")
        self.assertEqual(self._idle(), 1)

    def test_full_integrity_scan_still_runs_for_every_request(self):
        for _ in range(5):
            self._request()
        self.assertEqual(len(self.scans), 5, "reuse must not relax the per-connection integrity + foreign-key scan")

    def test_policy_change_is_visible_to_the_next_request(self):
        self.assertFalse(self._request()["reject"])
        self._set_enabled(0)
        denied = self._request()
        self.assertTrue(denied["reject"], "a pooled connection must see a policy change committed between requests")
        self.assertIn("disabled", denied.get("reject_reason", "").lower())
        self._set_enabled(1)
        self.assertFalse(self._request()["reject"])
        self.assertEqual(len(self.opened), 1)

    def test_replaced_database_file_discards_the_pooled_connection(self):
        self.assertFalse(self._request()["reject"])
        self.assertEqual(len(self.opened), 1)
        restored = Path(str(self.db_file) + ".restored")
        src = sqlite3.connect(str(self.db_file))
        dst = sqlite3.connect(str(restored))
        try:
            src.backup(dst)
            dst.execute("UPDATE published_services SET enabled = 0 WHERE id = 'svc1'")
            dst.commit()
        finally:
            dst.close()
            src.close()
        os.replace(str(restored), str(self.db_file))
        for suffix in ("-wal", "-shm"):
            try:
                os.unlink(str(self.db_file) + suffix)
            except FileNotFoundError:
                pass
        verdict = self._request()
        self.assertTrue(verdict["reject"], "the unlinked inode must not keep serving the pre-restore policy")
        self.assertEqual(len(self.opened), 2, "a replaced DB file must force a fresh connection")

    def test_failed_request_is_not_returned_to_the_pool(self):
        self.assertFalse(self._request()["reject"])
        self.assertEqual(self._idle(), 1)

        def boom(plane, **kwargs):
            raise RuntimeError("simulated authorization fault")

        self.PRP.authorize_remote = boom
        try:
            failed = self._request()
        finally:
            self.PRP.authorize_remote = self.orig_authorize
        self.assertTrue(failed["reject"], "an authorization fault must still fail closed")
        self.assertEqual(self._idle(), 0, "a connection that served a failed request must be discarded")
        self.assertFalse(self._request()["reject"])
        self.assertEqual(len(self.opened), 2)

    def test_corrupt_scan_fails_closed_and_discards_the_connection(self):
        self.assertFalse(self._request()["reject"])

        def broken(conn):
            self.scans.append(1)
            raise self.CP.DatabaseCorruptError("simulated corruption")

        self.CP.integrity_check = broken
        bad = self._request()
        self.assertTrue(bad["reject"])
        self.assertEqual(self._idle(), 0)
        self.CP.integrity_check = self.orig_scan
        self.assertFalse(self._request()["reject"])

    def test_reader_slots_are_held_only_while_a_request_runs(self):
        for _ in range(5):
            self._request()
        capacity = self.plugin.ACCESS_DB_MAX_CONCURRENT
        self._settle()
        self.assertEqual(self.cache._reader_slots._value, capacity, "an idle pooled connection must not hold a reader slot")
        self.assertLessEqual(self._idle(), capacity)

    def test_concurrent_requests_are_bounded_and_correct(self):
        results = []
        errors = []

        def worker(n):
            try:
                for _ in range(8):
                    results.append(self._request(settle=False)["reject"])
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 96)
        self.assertEqual(set(results), {False})
        capacity = self.plugin.ACCESS_DB_MAX_CONCURRENT
        self.assertLessEqual(self._idle(), capacity)
        self.assertEqual(self.cache._reader_slots._value, capacity)
        self.assertEqual(len(self.scans), 96, "every concurrent request must run its own complete scan")

    def test_unmapped_proxy_still_rejected(self):
        self._request()
        data = self._request(proxy="no-such-proxy")
        self.assertTrue(data["reject"])


if __name__ == "__main__":
    unittest.main()
