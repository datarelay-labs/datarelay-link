#!/usr/bin/env python3
"""AUD-21 step 1: the MCP Bridge must not share one SQLite connection across threads.

Every request thread used to run on the single connection opened by
ControlPlane.__init__, which produced SQLITE_MISUSE and interleaved cursors under
concurrent calls. `ControlPlane.request_scope()` now lends each request a pooled,
lightweight connection of its own; the listener backlog is raised so a burst of
simultaneous connects is not reset.

Disposable temp roots only; no service or credential is touched.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import BUSY_TIMEOUT_MS  # noqa: E402
from drlink_control_plane import ControlPlane  # noqa: E402
from drlink_mcp_bridge import MCPBridge, ThreadingHTTPServer, make_handler  # noqa: E402


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class RequestScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-db-own-")
        self.plane = ControlPlane(self.tmp)
        self.plane.conn.execute("CREATE TABLE IF NOT EXISTS scratch_t (x INTEGER)")

    def tearDown(self):
        self.plane.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _hold_scopes(self, count):
        """Hold `count` scopes open at the same instant, one per thread."""
        seen, barrier, guard = [], threading.Barrier(count), threading.Lock()

        def worker():
            with self.plane.request_scope():
                barrier.wait(timeout=30)
                with guard:
                    seen.append(self.plane.conn)
                barrier.wait(timeout=30)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return seen

    def test_concurrent_scopes_get_distinct_connections(self):
        seen = self._hold_scopes(8)
        self.assertEqual(len(seen), 8)
        self.assertEqual(len({id(conn) for conn in seen}), 8)
        self.assertNotIn(id(self.plane.conn), {id(conn) for conn in seen})

    def test_sequential_scopes_reuse_one_pooled_connection(self):
        with self.plane.request_scope():
            first = self.plane.conn
        with self.plane.request_scope():
            second = self.plane.conn
        self.assertIs(first, second)

    def test_nested_scope_on_one_thread_keeps_the_same_connection(self):
        with self.plane.request_scope():
            outer = self.plane.conn
            with self.plane.request_scope():
                self.assertIs(self.plane.conn, outer)
            self.assertIs(self.plane.conn, outer)

    def test_unscoped_thread_still_uses_the_primary_connection(self):
        primary = self.plane.conn
        with self.plane.request_scope():
            self.assertIsNot(self.plane.conn, primary)
        self.assertIs(self.plane.conn, primary)

    def test_scoped_connection_keeps_safety_settings_and_does_not_rewrite_the_db(self):
        with self.plane.request_scope():
            conn = self.plane.conn
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 2)  # FULL
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], BUSY_TIMEOUT_MS)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertIs(conn.row_factory, sqlite3.Row)

    def test_open_transaction_is_rolled_back_when_the_scope_ends(self):
        capture = _Capture()
        logger = logging.getLogger("drlink.control_plane")
        logger.addHandler(capture)
        try:
            with self.plane.request_scope():
                self.plane.conn.execute("BEGIN")
                self.plane.conn.execute("INSERT INTO scratch_t VALUES (1)")
            # The next borrower must not inherit, or later commit, that work.
            with self.plane.request_scope():
                self.assertFalse(self.plane.conn.in_transaction)
            self.assertEqual(self.plane.conn.execute("SELECT COUNT(*) FROM scratch_t").fetchone()[0], 0)
        finally:
            logger.removeHandler(capture)
        self.assertTrue(any("rolled back" in r.getMessage() for r in capture.records))

    def test_invalidated_pool_never_hands_out_a_stale_connection(self):
        with self.plane.request_scope():
            old = self.plane.conn
        self.plane._invalidate_worker_pool()
        with self.assertRaises(sqlite3.ProgrammingError):
            old.execute("SELECT 1")  # idle pooled connection was closed
        with self.plane.request_scope():
            self.assertIsNot(self.plane.conn, old)
            self.assertEqual(self.plane.conn.execute("SELECT 1").fetchone()[0], 1)

    def test_idle_pool_is_bounded(self):
        self._hold_scopes(self.plane.WORKER_POOL_IDLE_MAX + 8)
        self.assertLessEqual(len(self.plane._worker_pool), self.plane.WORKER_POOL_IDLE_MAX)

    def test_writes_from_concurrent_scopes_all_land(self):
        count, barrier = 16, threading.Barrier(16)

        def worker(index):
            with self.plane.request_scope():
                barrier.wait(timeout=30)
                for step in range(10):
                    self.plane.conn.execute("INSERT INTO scratch_t VALUES (?)", (index * 100 + step,))

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertEqual(self.plane.conn.execute("SELECT COUNT(*) FROM scratch_t").fetchone()[0], count * 10)

    def test_read_only_plane_lends_read_only_connections(self):
        reader = ControlPlane(self.tmp, read_only=True)
        try:
            with reader.request_scope():
                self.assertEqual(reader.conn.execute("PRAGMA query_only").fetchone()[0], 1)
        finally:
            reader.close()


class InjectedConnectionTests(unittest.TestCase):
    def test_an_injected_connection_is_never_replaced_by_the_pool(self):
        tmp = tempfile.mkdtemp(prefix="drlink-db-own-inj-")
        mem = sqlite3.connect(":memory:", isolation_level=None)
        try:
            plane = ControlPlane(tmp, conn=mem)
            with plane.request_scope():
                self.assertIs(plane.conn, mem)
        finally:
            mem.close()
            shutil.rmtree(tmp, ignore_errors=True)


class BridgeIntegrationTests(unittest.TestCase):
    def test_listener_backlog_is_large_enough_for_a_burst_of_connects(self):
        self.assertGreaterEqual(ThreadingHTTPServer.request_queue_size, 128)

    def test_every_http_method_runs_inside_a_request_scope(self):
        tmp = tempfile.mkdtemp(prefix="drlink-db-own-http-")
        plane = ControlPlane(tmp)
        bridge = MCPBridge(root=tmp, plane=plane, auto_agents=False)
        entered = {"count": 0}
        original = plane.request_scope

        def counting_scope():
            entered["count"] += 1
            return original()

        plane.request_scope = counting_scope
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bridge))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%s" % httpd.server_address[1]
        try:
            for method, path in (("GET", "/mcp"), ("POST", "/mcp"), ("DELETE", "/mcp"), ("OPTIONS", "/mcp")):
                request = urllib.request.Request(base + path, data=b"{}" if method == "POST" else None, method=method)
                try:
                    urllib.request.urlopen(request, timeout=10).read()
                except urllib.error.HTTPError:
                    pass  # status is irrelevant; the handler must have run in a scope
            self.assertEqual(entered["count"], 4)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
            bridge.close()
            plane.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
