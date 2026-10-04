#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ensure_v30_schema, open_control_db
from drlink_control_plane import ControlPlane
from drlink_v30_readmodels import overview_summary


class V30AdditiveManagementSchemaTests(unittest.TestCase):
    def test_prior_v3_shape_adds_agent_inventory_before_indexes(self):
        conn = sqlite3.connect(":memory:", isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE clients (
              id TEXT PRIMARY KEY,
              label TEXT,
              hostname TEXT,
              status TEXT NOT NULL DEFAULT 'connected'
            );
            CREATE TABLE policy_rules (
              id TEXT PRIMARY KEY,
              plane TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 0,
              position INTEGER NOT NULL,
              expires_at TEXT
            );
            CREATE TABLE ai_policy_rules (
              id TEXT PRIMARY KEY,
              enabled INTEGER NOT NULL DEFAULT 0,
              expires_at TEXT
            );
            CREATE TABLE published_services (
              id TEXT PRIMARY KEY,
              enabled INTEGER NOT NULL DEFAULT 1,
              released INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE audit_events (
              id INTEGER PRIMARY KEY,
              timestamp TEXT,
              operation TEXT,
              actor TEXT,
              revision INTEGER,
              entity_type TEXT,
              entity_id TEXT
            );
            """
        )
        ensure_v30_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(clients)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(clients)")}
        audit_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(audit_events)")
        }
        self.assertIn("agent_platform", columns)
        self.assertIn("agent_version", columns)
        self.assertIn("idx_v30_clients_agent_version", indexes)
        self.assertIn("idx_v30_clients_platform", indexes)
        self.assertIn("duration_ms", audit_columns)
        conn.close()

    def test_inventory_change_bypasses_heartbeat_coalescing_without_revision(self):
        root = tempfile.mkdtemp(prefix="drlink-v30-inventory-coalesce-")
        plane = ControlPlane(root)
        try:
            now = "2026-10-04T01:00:00Z"
            plane.conn.execute(
                "INSERT INTO clients("
                "id,label,hostname,status,trust_status,connected,last_seen,"
                "agent_heartbeat_at,agent_lifecycle_state,agent_platform,agent_version,"
                "row_version,created_at,updated_at"
                ") VALUES ("
                "'host-a','host-a','host-a','active','trusted',1,NULL,?,"
                "'connected','linux','3.0.0-rc.1',1,?,?)",
                (now, now, now),
            )
            before = plane.current_revision()
            self.assertTrue(
                plane.refresh_agent_lifecycle(
                    "host-a",
                    "connected",
                    agent_platform="Linux",
                    agent_version="3.0.0-rc.2",
                )
            )
            row = plane.conn.execute(
                "SELECT agent_platform,agent_version FROM clients WHERE id='host-a'"
            ).fetchone()
            self.assertEqual(row["agent_platform"], "linux")
            self.assertEqual(row["agent_version"], "3.0.0-rc.2")
            self.assertEqual(plane.current_revision(), before)
        finally:
            plane.close()

    def test_legacy_host_summary_matches_core_connectivity_compatibility(self):
        root = tempfile.mkdtemp(prefix="drlink-v30-legacy-summary-")
        conn = open_control_db(root)
        try:
            conn.execute(
                "INSERT INTO clients("
                "id,label,hostname,status,trust_status,connected,last_seen,"
                "agent_heartbeat_at,agent_lifecycle_state,agent_platform,agent_version,"
                "row_version,created_at,updated_at"
                ") VALUES ("
                "'legacy-a','legacy-a','legacy-a','active','trusted',0,NULL,NULL,"
                "'legacy','linux','2.4.0',1,'2026-10-04T00:00:00Z','2026-10-04T00:00:00Z')"
            )
            summary = overview_summary(
                conn, now=datetime(2026, 10, 4, 2, 0, tzinfo=timezone.utc)
            )
            self.assertEqual(summary["managed_hosts"]["total"], 1)
            self.assertEqual(summary["managed_hosts"]["connected"], 1)
            self.assertEqual(summary["managed_hosts"]["stale"], 0)
            self.assertEqual(summary["managed_hosts"]["disconnected"], 0)
            self.assertEqual(summary["managed_hosts"]["legacy"], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
