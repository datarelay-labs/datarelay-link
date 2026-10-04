#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import (
    LEGACY_AI_ACTIVITY_CONVERGENCE_BATCH,
    converge_legacy_ai_activity,
)
from drlink_control_plane import ControlPlane
from drlink_v30_audit import legacy_connection_evidence_contract
from frp_state_paths import (
    ACCESS_CONN_LOG,
    ACCESS_CONN_LOG_LEGACY,
    EGRESS_CONN_LOG,
    EGRESS_CONN_LOG_LEGACY,
    backup_optional_files,
)


class V30AuditConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-audit-converge-")

    def _plane(self):
        return ControlPlane(self.tmp)

    @staticmethod
    def _seed_legacy_pair(plane: ControlPlane, ident: int = 1) -> None:
        ts = "2026-10-04T01:00:%02dZ" % (ident % 60)
        plane.conn.execute(
            "INSERT INTO ai_activity("
            "id,timestamp,principal_id,principal_name,endpoint_id,endpoint_name,"
            "capability,matched_rule,result,duration_ms,revision,operand_summary"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ident,
                ts,
                None,
                "legacy-bot",
                None,
                "host-a",
                "get_system_info",
                "allow-info",
                "ALLOW",
                7,
                0,
                "/safe/path",
            ),
        )
        plane.conn.execute(
            "INSERT INTO audit_events("
            "timestamp,revision,actor,action,entity_type,entity_id,operation,"
            "before_summary,after_summary,impact_summary,result"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts,
                None,
                "legacy-bot",
                "ai get_system_info",
                "ai-principal",
                "legacy-bot",
                "get_system_info",
                "",
                "host-a /safe/path",
                "allow-info",
                "ALLOW",
            ),
        )

    def test_legacy_ai_activity_adopts_companion_audit_row_without_duplicate(self):
        plane = self._plane()
        try:
            self._seed_legacy_pair(plane)
            before = int(
                plane.conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            )
        finally:
            plane.close()

        plane = self._plane()
        try:
            after = int(
                plane.conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            )
            self.assertEqual(after, before)
            row = plane.conn.execute(
                "SELECT * FROM audit_events WHERE source='legacy-ai_activity' "
                "AND source_sequence=1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["event_id"], "legacy-ai-activity-00000000000000000001")
            self.assertEqual(row["category"], "ACCESS_DECISION")
            self.assertEqual(row["event_type"], "ai.tool")
            self.assertEqual(row["actor_id"], "legacy-bot")
            self.assertEqual(row["entity_type"], "managed-endpoint")
            self.assertEqual(row["entity_id"], "host-a")
            self.assertEqual(row["duration_ms"], 7)
            self.assertEqual(json.loads(row["matched_policy_json"]), ["allow-info"])

            projected = plane.list_ai_activity(
                principal="legacy-bot", endpoint="host-a"
            )
            self.assertEqual(len(projected), 1)
            self.assertEqual(projected[0]["matched_rule"], "allow-info")
            self.assertEqual(projected[0]["operand_summary"], "/safe/path")

            # The legacy table remains forensic migration input only. Modifying it
            # after convergence must not change compatibility reads.
            plane.conn.execute(
                "UPDATE ai_activity SET matched_rule='tampered' WHERE id=1"
            )
            projected = plane.list_ai_activity(
                principal="legacy-bot", endpoint="host-a"
            )
            self.assertEqual(projected[0]["matched_rule"], "allow-info")
        finally:
            plane.close()

    def test_new_ai_activity_writes_unified_audit_only(self):
        plane = self._plane()
        try:
            before = int(
                plane.conn.execute("SELECT COUNT(*) FROM ai_activity").fetchone()[0]
            )
            plane.record_ai_activity(
                principal="bot",
                endpoint="host-b",
                capability="read_file",
                result="DENY",
                rule="deny-secret",
                duration_ms=11,
                operand="/etc/secret",
            )
            after = int(
                plane.conn.execute("SELECT COUNT(*) FROM ai_activity").fetchone()[0]
            )
            self.assertEqual(after, before)
            row = plane.conn.execute(
                "SELECT * FROM audit_events WHERE source='ai-mcp' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["category"], "ACCESS_DECISION")
            self.assertEqual(row["event_type"], "ai.tool")
            self.assertEqual(row["actor_id"], "bot")
            self.assertEqual(row["entity_id"], "host-b")
            self.assertEqual(row["operation"], "read_file")
            self.assertEqual(row["result"], "DENY")
            self.assertEqual(row["duration_ms"], 11)

            projected = plane.list_ai_activity(principal="bot", endpoint="host-b")
            self.assertEqual(len(projected), 1)
            self.assertEqual(projected[0]["capability"], "read_file")
            self.assertEqual(projected[0]["matched_rule"], "deny-secret")
            self.assertEqual(projected[0]["operand_summary"], "/etc/secret")
        finally:
            plane.close()

    def test_legacy_convergence_is_bounded_and_resumable(self):
        plane = self._plane()
        try:
            rows = []
            for ident in range(1, LEGACY_AI_ACTIVITY_CONVERGENCE_BATCH + 6):
                rows.append(
                    (
                        ident,
                        "2026-10-04T01:%02d:%02dZ" % ((ident // 60) % 60, ident % 60),
                        None,
                        "bulk-bot",
                        None,
                        "host-%03d" % ident,
                        "get_host",
                        "allow",
                        "ALLOW",
                        ident % 17,
                        0,
                        "",
                    )
                )
            plane.conn.executemany(
                "INSERT INTO ai_activity("
                "id,timestamp,principal_id,principal_name,endpoint_id,endpoint_name,"
                "capability,matched_rule,result,duration_ms,revision,operand_summary"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            first = converge_legacy_ai_activity(plane.conn)
            self.assertEqual(first["processed"], LEGACY_AI_ACTIVITY_CONVERGENCE_BATCH)
            self.assertEqual(first["remaining"], 5)
            converged = int(
                plane.conn.execute(
                    "SELECT COUNT(*) FROM audit_events "
                    "WHERE source='legacy-ai_activity'"
                ).fetchone()[0]
            )
            self.assertEqual(converged, LEGACY_AI_ACTIVITY_CONVERGENCE_BATCH)
            state = plane.conn.execute(
                "SELECT value FROM system_meta "
                "WHERE key='v30_ai_activity_convergence'"
            ).fetchone()
            self.assertEqual(state["value"], "in-progress")

            second = converge_legacy_ai_activity(plane.conn)
            self.assertEqual(second["processed"], 5)
            self.assertEqual(second["remaining"], 0)
            state = plane.conn.execute(
                "SELECT value FROM system_meta "
                "WHERE key='v30_ai_activity_convergence'"
            ).fetchone()
            self.assertEqual(state["value"], "complete")
        finally:
            plane.close()

    def test_connection_jsonl_is_explicit_forensic_no_import_evidence(self):
        contract = legacy_connection_evidence_contract(self.tmp)
        self.assertEqual(contract["policy"], "PRESERVE_PRE_V3_FORENSIC")
        self.assertEqual(contract["state_class"], "FORENSIC_EVIDENCE")
        self.assertFalse(contract["authoritative"])
        self.assertFalse(contract["import_to_unified_audit"])
        self.assertFalse(contract["query_backend"])
        self.assertFalse(contract["live_backend"])
        self.assertEqual(contract["upgrade_action"], "PRESERVE_IN_PLACE")

        specs = (
            ACCESS_CONN_LOG,
            ACCESS_CONN_LOG_LEGACY,
            EGRESS_CONN_LOG,
            EGRESS_CONN_LOG_LEGACY,
        )
        optional = set(backup_optional_files())
        for spec in specs:
            with self.subTest(path=spec.path):
                self.assertEqual(
                    spec.migration_policy, "retain-pre-v3-forensic-no-import"
                )
                self.assertIn(spec.path, optional)


if __name__ == "__main__":
    unittest.main()
