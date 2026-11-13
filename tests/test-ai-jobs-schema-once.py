#!/usr/bin/env python3
"""AUD-21 2h: the AI-jobs safety schema is checked once per pooled connection.

``ensure_ai_jobs_safety_schema`` (PRAGMA table_info, a backfill SELECT and
CREATE INDEX IF NOT EXISTS) used to run on every claim/enqueue/complete call.
A pooled request connection now carries a mark, validated against SQLite's
schema cookie, so the check runs once and again whenever the schema changes.

The mark must never turn into a stale "ready": a new connection, a changed
schema, a missing table, an open transaction and a connection that cannot carry
a mark must all keep running the full check.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_db as cdb  # noqa: E402
from drlink_control_plane import ControlPlane  # noqa: E402

MACHINE = "a" * 32
PROBE = "table_info(ai_jobs)"


def _probe_count(statements) -> int:
    return sum(1 for s in statements if PROBE in s)


class AiJobsSchemaOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-aud21-schema-")
        os.environ["DRLINK_TEST_ROOT"] = self.tmp
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        self.plane = ControlPlane(self.tmp)
        self.plane.upsert_client(MACHINE, label="h", hostname="h")

    def tearDown(self):
        self.plane.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _trace(self, conn):
        statements: list = []
        conn.set_trace_callback(statements.append)
        return statements

    def test_repeated_claims_check_the_schema_once(self):
        with self.plane.request_scope():
            statements = self._trace(self.plane.conn)
            for _ in range(5):
                self.assertEqual(self.plane.claim_ai_jobs(MACHINE), [])
            self.plane.conn.set_trace_callback(None)
        self.assertEqual(_probe_count(statements), 1, statements)

    def test_pooled_connection_keeps_its_mark_across_requests(self):
        with self.plane.request_scope():
            self.plane.claim_ai_jobs(MACHINE)
        with self.plane.request_scope():
            statements = self._trace(self.plane.conn)
            self.plane.claim_ai_jobs(MACHINE)
            self.plane.conn.set_trace_callback(None)
        self.assertEqual(_probe_count(statements), 0, statements)

    def test_a_new_connection_runs_the_check_again(self):
        with self.plane.request_scope():
            self.plane.claim_ai_jobs(MACHINE)
        self.plane._invalidate_worker_pool()
        with self.plane.request_scope():
            statements = self._trace(self.plane.conn)
            self.plane.claim_ai_jobs(MACHINE)
            self.plane.conn.set_trace_callback(None)
        self.assertEqual(_probe_count(statements), 1, statements)

    def test_a_schema_change_runs_the_check_again_and_repairs_it(self):
        with self.plane.request_scope():
            conn = self.plane.conn
            self.plane.claim_ai_jobs(MACHINE)
            conn.execute("DROP INDEX idx_ai_jobs_claim")
            self.assertIsNone(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'idx_ai_jobs_claim'"
                ).fetchone()
            )
            self.plane.claim_ai_jobs(MACHINE)
            self.assertIsNotNone(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'idx_ai_jobs_claim'"
                ).fetchone()
            )

    def test_a_connection_that_cannot_carry_a_mark_keeps_checking(self):
        plain = sqlite3.connect(str(Path(self.plane.db_file)), isolation_level=None)
        plain.row_factory = sqlite3.Row
        try:
            statements = self._trace(plain)
            for _ in range(3):
                cdb.ensure_ai_jobs_safety_schema_once(plain)
            plain.set_trace_callback(None)
        finally:
            plain.close()
        self.assertEqual(_probe_count(statements), 3, statements)

    def test_a_missing_table_is_not_marked_ready(self):
        mem = cdb.connect_worker(path=Path(self.plane.db_file))
        try:
            mem.execute("ALTER TABLE ai_jobs RENAME TO ai_jobs_parked")
            cdb.ensure_ai_jobs_safety_schema_once(mem)
            mem.execute("ALTER TABLE ai_jobs_parked RENAME TO ai_jobs")
            mem.execute("DROP INDEX IF EXISTS idx_ai_jobs_claim")
            cdb.ensure_ai_jobs_safety_schema_once(mem)
            self.assertIsNotNone(
                mem.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'idx_ai_jobs_claim'"
                ).fetchone()
            )
        finally:
            mem.close()

    def test_an_open_transaction_is_not_marked_ready(self):
        conn = cdb.connect_worker(path=Path(self.plane.db_file))
        try:
            conn.execute("BEGIN IMMEDIATE")
            cdb.ensure_ai_jobs_safety_schema_once(conn)
            self.assertTrue(conn.in_transaction)
            conn.execute("ROLLBACK")
            statements = self._trace(conn)
            cdb.ensure_ai_jobs_safety_schema_once(conn)
            conn.set_trace_callback(None)
        finally:
            conn.close()
        self.assertEqual(_probe_count(statements), 1, statements)

    def test_a_legacy_row_without_client_id_is_still_backfilled_on_a_new_connection(self):
        with self.plane.request_scope():
            self.plane.claim_ai_jobs(MACHINE)
        self.plane.conn.execute(
            "INSERT INTO ai_jobs(id, principal_id, endpoint_object_id, capability, "
            "payload_json, status, created_at, updated_at, timeout_seconds) "
            "VALUES ('job-legacy', NULL, 'e', 'host-info', ?, 'queued', 'now', 'now', 30)",
            ('{"client_id": "%s"}' % MACHINE,),
        )
        self.plane.commit_if_autonomous()
        self.plane._invalidate_worker_pool()
        with self.plane.request_scope():
            self.plane.claim_ai_jobs(MACHINE)
            row = self.plane.conn.execute(
                "SELECT client_id FROM ai_jobs WHERE id = 'job-legacy'"
            ).fetchone()
        self.assertEqual(row[0], MACHINE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
