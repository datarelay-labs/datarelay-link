#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
from drlink_management_service import ManagementQueryService
from drlink_v30_jobs import BoundedAgentRpcWorkerPool, ManagementJobEngine, RUNNING, SUCCEEDED
import drlink_v24 as v24


class V30ManagementMixedLoadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-mixed-")
        plane = ControlPlane(self.tmp)
        try:
            now = "2026-10-04T03:00:00Z"
            for idx in range(100):
                ident = "host-%03d" % idx
                plane.conn.execute(
                    "INSERT INTO clients("
                    "id,label,hostname,status,trust_status,connected,last_seen,"
                    "agent_heartbeat_at,agent_lifecycle_state,agent_platform,agent_version,"
                    "row_version,created_at,updated_at"
                    ") VALUES (?,?,?,'active','trusted',1,?,?,?,'linux','3.0.0',1,?,?)",
                    (
                        ident,
                        ident,
                        ident + ".example",
                        now,
                        now,
                        "connected",
                        now,
                        now,
                    ),
                )
        finally:
            plane.close()

    def test_mixed_reads_configuration_write_and_rpc_wait_do_not_starve_each_other(self):
        engine = ManagementJobEngine(self.tmp, max_active_jobs=8, max_targets=8)
        job = engine.enqueue(
            job_type="doctor",
            targets=["host-000"],
            requested_by="operator",
            timeout_seconds=300,
        )

        rpc_entered = threading.Event()
        rpc_release = threading.Event()

        def rpc_handler(claim):
            rpc_entered.set()
            if not rpc_release.wait(5):
                raise RuntimeError("test RPC release timed out")
            return {"target": claim["target_id"], "doctor": "pass"}

        pool = BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0)
        try:
            futures = pool.dispatch_once(
                engine, rpc_handler, worker_id="mixed-load-worker", limit=1
            )
            self.assertEqual(len(futures), 1)
            self.assertTrue(rpc_entered.wait(2))
            self.assertFalse(futures[0].done())
            self.assertEqual(engine.get(job["id"])["status"], RUNNING)

            plane = ControlPlane(self.tmp)
            try:
                revision_before = plane.current_revision()
                remote_before = [dict(row) for row in plane.list_rules("remote")]
                internet_before = [dict(row) for row in plane.list_rules("internet")]
            finally:
                plane.close()

            reader_errors: list[BaseException] = []
            reader_counts: list[int] = []

            def reader() -> None:
                try:
                    with ManagementQueryService(self.tmp) as query:
                        page = query.list_inventory("managed-host", limit=50)
                        summary = query.overview_summary()
                        reader_counts.append(len(page.items))
                        if summary["managed_hosts"]["total"] != 100:
                            raise AssertionError(summary)
                except BaseException as exc:
                    reader_errors.append(exc)

            readers = [threading.Thread(target=reader) for _ in range(4)]
            for thread in readers:
                thread.start()

            writer_done = threading.Event()
            writer_error: list[BaseException] = []

            def writer() -> None:
                plane = ControlPlane(self.tmp)
                try:
                    v24.set_network_object(
                        plane,
                        "mixed-load-object",
                        type="ip",
                        value="198.51.100.99",
                        oneshot=True,
                    )
                except BaseException as exc:
                    writer_error.append(exc)
                finally:
                    plane.close()
                    writer_done.set()

            writer_thread = threading.Thread(target=writer)
            writer_thread.start()

            # This must complete while the simulated Agent RPC is still blocked.
            self.assertTrue(writer_done.wait(5), "configuration writer was starved by RPC wait")
            writer_thread.join(timeout=1)
            self.assertFalse(writer_thread.is_alive())
            self.assertEqual(writer_error, [])

            for thread in readers:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(reader_errors, [])
            self.assertEqual(sorted(reader_counts), [50, 50, 50, 50])

            # The Job must not claim success before the RPC result actually exists.
            self.assertFalse(futures[0].done())
            self.assertEqual(engine.get(job["id"])["status"], RUNNING)

            plane = ControlPlane(self.tmp)
            try:
                self.assertEqual(plane.current_revision(), revision_before + 1)
                self.assertIsNotNone(plane.get_object("mixed-load-object"))
                self.assertEqual(
                    [dict(row) for row in plane.list_rules("remote")],
                    remote_before,
                )
                self.assertEqual(
                    [dict(row) for row in plane.list_rules("internet")],
                    internet_before,
                )
            finally:
                plane.close()

            rpc_release.set()
            futures[0].result(timeout=5)
            self.assertEqual(engine.get(job["id"])["status"], SUCCEEDED)
        finally:
            rpc_release.set()
            pool.close()
            engine.close()


if __name__ == "__main__":
    unittest.main()
