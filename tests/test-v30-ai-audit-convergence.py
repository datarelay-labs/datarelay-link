#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import open_control_db
from drlink_control_plane import ControlPlane
from drlink_management_service import ManagementQueryService


class V30AiAuditConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-ai-audit-")

    def test_more_than_one_batch_converges_before_open_returns(self):
        plane = ControlPlane(self.tmp)
        try:
            for ident in range(451):
                stamp = "2026-10-04T%02d:%02d:%02dZ" % (
                    (ident // 3600) % 24,
                    (ident // 60) % 60,
                    ident % 60,
                )
                principal = "bot-%03d" % (ident % 7)
                endpoint = "host-%03d" % (ident % 11)
                capability = "host-info"
                result = "ALLOW"
                plane.conn.execute(
                    "INSERT INTO ai_activity("
                    "timestamp,principal_id,principal_name,endpoint_id,endpoint_name,"
                    "capability,matched_rule,result,duration_ms,revision,operand_summary"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        stamp,
                        None,
                        principal,
                        None,
                        endpoint,
                        capability,
                        "allow-host-info",
                        result,
                        ident % 50,
                        0,
                        "/safe/path/%03d" % ident,
                    ),
                )
                plane.conn.execute(
                    "INSERT INTO audit_events("
                    "timestamp,revision,actor,action,entity_type,entity_id,operation,"
                    "before_summary,after_summary,impact_summary,result"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        stamp,
                        None,
                        principal,
                        "ai %s" % capability,
                        "ai-principal",
                        principal,
                        capability,
                        "",
                        endpoint,
                        "allow-host-info",
                        result,
                    ),
                )
        finally:
            plane.close()

        conn = open_control_db(self.tmp)
        try:
            migrated = conn.execute(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE source='legacy-ai_activity' AND event_type='ai.tool'"
            ).fetchone()[0]
            remaining = conn.execute(
                "SELECT COUNT(*) FROM ai_activity a WHERE NOT EXISTS ("
                "SELECT 1 FROM audit_events e "
                "WHERE e.source='legacy-ai_activity' AND e.source_sequence=a.id)"
            ).fetchone()[0]
            marker = conn.execute(
                "SELECT value FROM system_meta WHERE key='v30_ai_activity_convergence'"
            ).fetchone()
            self.assertEqual(migrated, 451)
            self.assertEqual(remaining, 0)
            self.assertIsNotNone(marker)
            self.assertEqual(marker[0], "complete")
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(DISTINCT event_id) FROM audit_events "
                    "WHERE source='legacy-ai_activity'"
                ).fetchone()[0],
                451,
            )
        finally:
            conn.close()

        # Re-open proves migration idempotence and does not duplicate history.
        conn = open_control_db(self.tmp)
        try:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM audit_events "
                    "WHERE source='legacy-ai_activity'"
                ).fetchone()[0],
                451,
            )
        finally:
            conn.close()

    def test_new_ai_activity_uses_unified_authority_and_legacy_projection(self):
        plane = ControlPlane(self.tmp)
        try:
            before_legacy = plane.conn.execute(
                "SELECT COUNT(*) FROM ai_activity"
            ).fetchone()[0]
            plane.record_ai_activity(
                principal="bot",
                endpoint="host-a",
                capability="host-info",
                result="ALLOW",
                rule="allow-host-info",
                duration_ms=17,
                operand="/etc/os-release",
            )
            after_legacy = plane.conn.execute(
                "SELECT COUNT(*) FROM ai_activity"
            ).fetchone()[0]
            self.assertEqual(before_legacy, after_legacy)

            legacy_projection = plane.list_ai_activity(
                principal="bot", endpoint="host-a"
            )
            self.assertEqual(len(legacy_projection), 1)
            self.assertEqual(legacy_projection[0]["capability"], "host-info")
            self.assertEqual(legacy_projection[0]["matched_rule"], "allow-host-info")
            self.assertEqual(legacy_projection[0]["duration_ms"], 17)
        finally:
            plane.close()

        query = ManagementQueryService(self.tmp)
        try:
            page = query.audit_query(
                category="ACCESS_DECISION",
                event_type="ai.tool",
                actor="bot",
                resource="host-a",
                limit=10,
            )
            self.assertEqual(len(page.items), 1)
            item = page.items[0]
            self.assertTrue(str(item["event_id"]).startswith("evt_ai_"))
            self.assertEqual(item["source"], "ai-mcp")
            self.assertEqual(item["actor_type"], "ai-identity")
            self.assertEqual(item["interface"], "MCP")
            self.assertEqual(item["operation"], "host-info")
            self.assertEqual(item["result"], "ALLOW")
            self.assertEqual(item["matched_policy"], ["allow-host-info"])
            self.assertEqual(item["source_meta"], {"ai_identity": "bot"})
            self.assertEqual(item["destination_meta"], {"host": "host-a"})
            self.assertFalse(item["legacy"])
        finally:
            query.close()


if __name__ == "__main__":
    unittest.main()
