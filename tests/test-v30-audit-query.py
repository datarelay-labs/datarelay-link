#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_db as DB
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from drlink_management_service import ManagementQueryService
from drlink_v30_audit import AuditIngestor, DurableAuditSpool, build_access_decision_event
import drlink_v24 as v24


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class V30AuditQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-audit-query-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        os.environ["DRLINK_ACTOR"] = "operator-a"
        os.environ["DRLINK_INTERFACE"] = "CLI"
        self.plane = ControlPlane(self.tmp)

        v24.set_network_object(
            self.plane, "one", type="ip", value="198.51.100.1", oneshot=True
        )
        v24.set_network_object(
            self.plane, "two", type="ip", value="198.51.100.2", oneshot=True
        )

        spool = DurableAuditSpool(
            Path(self.tmp) / "var/log/drlink/access/audit-spool",
            "remote-access",
            segment_bytes=16 * 1024,
            high_water_bytes=64 * 1024,
        )
        spool.enqueue(
            build_access_decision_event(
                source="remote-access",
                event_type="remote.access.decision",
                result="ALLOW",
                resource_type="remote-service",
                resource_id="svc-1",
                actor_type="network-client",
                actor_id="client-a",
                interface="FRP_PLUGIN",
                correlation_id="corr-1",
                matched_policy=["allow-ssh"],
                source_meta={"ip": "198.51.100.10"},
                destination_meta={
                    "service_id": "svc-1",
                    "service_name": "ssh-admin",
                    "port": 22,
                    "protocol": "tcp",
                },
            )
        )
        AuditIngestor(self.plane.conn, spool).ingest()
        self.query = ManagementQueryService(self.tmp)

    def tearDown(self):
        self.query.close()
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM", "DRLINK_ACTOR", "DRLINK_INTERFACE"):
            os.environ.pop(key, None)

    def test_unified_query_contains_control_and_access_decision(self):
        page = self.query.audit_query(limit=20)
        categories = {item["category"] for item in page.items}
        self.assertIn("CONTROL", categories)
        self.assertIn("ACCESS_DECISION", categories)

    def test_filters_are_exact_and_bounded(self):
        access = self.query.audit_query(
            category="access_decision",
            actor="client-a",
            resource="svc-1",
            result="ALLOW",
            correlation="corr-1",
        )
        self.assertEqual(len(access.items), 1)
        item = access.items[0]
        self.assertEqual(item["event_type"], "remote.access.decision")
        self.assertEqual(item["matched_policy"], ["allow-ssh"])
        self.assertEqual(item["destination_meta"]["service_name"], "ssh-admin")
        self.assertFalse(item["legacy"])

    def test_control_actor_and_interface_are_queryable(self):
        page = self.query.audit_query(category="CONTROL", actor="operator-a")
        self.assertGreaterEqual(len(page.items), 2)
        self.assertTrue(all(item["interface"] == "CLI" for item in page.items))
        self.assertTrue(all(item["revision_after"] is not None for item in page.items))

    def test_keyset_cursor_descending_has_no_duplicates(self):
        first = self.query.audit_query(limit=2)
        self.assertEqual(len(first.items), 2)
        self.assertIsNotNone(first.next_cursor)
        second = self.query.audit_query(limit=2, cursor=first.next_cursor)
        first_ids = {item["row_id"] for item in first.items}
        second_ids = {item["row_id"] for item in second.items}
        self.assertFalse(first_ids & second_ids)

    def test_time_range_filters_are_bounded_and_query_indexes_exist(self):
        access = self.query.audit_query(category="ACCESS_DECISION", limit=10)
        self.assertEqual(len(access.items), 1)
        occurred = access.items[0]["occurred_at"]
        same = self.query.audit_query(
            start=occurred,
            end=occurred,
            category="ACCESS_DECISION",
            event_type="remote.access.decision",
            result="ALLOW",
            limit=10,
        )
        self.assertEqual(len(same.items), 1)
        self.assertEqual(same.items[0]["event_id"], access.items[0]["event_id"])
        before = self.query.audit_query(
            end="2000-01-01T00:00:00Z",
            category="ACCESS_DECISION",
            limit=10,
        )
        self.assertEqual(before.items, ())

        indexes = {
            row[0]
            for row in self.plane.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for name in (
            "idx_v30_audit_time",
            "idx_v30_audit_category_time",
            "idx_v30_audit_actor_time",
            "idx_v30_audit_resource_time",
            "idx_v30_audit_correlation",
            "idx_v30_audit_event_type_time",
            "idx_v30_audit_result_time",
        ):
            self.assertIn(name, indexes)

    def test_invalid_or_cross_type_cursor_fails_closed(self):
        with self.assertRaises(ControlPlaneError):
            self.query.audit_query(cursor="not-a-cursor")
        inv = self.query.list_inventory("network-object", limit=1)
        if inv.next_cursor:
            with self.assertRaises(ControlPlaneError):
                self.query.audit_query(cursor=inv.next_cursor)

    def test_limit_is_hard_capped(self):
        page = self.query.audit_query(limit=10000)
        self.assertEqual(page.limit, 200)

    def test_legacy_row_is_backfilled_into_unified_query_model(self):
        self.plane.conn.execute(
            "INSERT INTO audit_events("
            "timestamp,revision,actor,action,entity_type,entity_id,operation,"
            "before_summary,after_summary,impact_summary,result"
            ") VALUES ('2026-01-01T00:00:00Z',1,'legacy-admin','legacy action',"
            "'legacy-resource','legacy-1','legacy-op','','','','ok')"
        )
        DB.ensure_v30_schema(self.plane.conn)
        legacy = self.query.audit_query(
            category="CONTROL", actor="legacy-admin", resource="legacy-1"
        )
        self.assertEqual(len(legacy.items), 1)
        item = legacy.items[0]
        self.assertTrue(item["legacy"])
        self.assertEqual(item["occurred_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(item["source"], "legacy-core")
        self.assertEqual(item["revision_after"], 1)
        self.assertEqual(item["revision_before"], 0)

    def test_ready_mcp_descriptors_include_only_implemented_reads(self):
        names = {
            item["name"]
            for item in ManagementQueryService.ready_mcp_descriptors()
        }
        self.assertIn("drlink_audit_query", names)
        self.assertIn("drlink_live_access", names)
        self.assertNotIn("drlink_temporary_access_apply", names)
        self.assertNotIn("drlink_emergency_cutoff_apply", names)


if __name__ == "__main__":
    unittest.main()
