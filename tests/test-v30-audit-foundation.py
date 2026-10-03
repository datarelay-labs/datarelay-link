#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_db as DB
from drlink_control_plane import ControlPlane
from drlink_v30_audit import (
    ACCESS_DECISION,
    AuditEventInvalid,
    AuditIngestor,
    AuditUnavailable,
    DurableAuditSpool,
    build_access_decision_event,
)
import drlink_v24 as v24


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class V30AuditSchemaAndControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-audit-control-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_CONFIRM", None)
        os.environ.pop("DRLINK_INTERFACE", None)

    def test_schema_has_v3_audit_envelope_and_checkpoint(self):
        cols = {r[1] for r in self.plane.conn.execute("PRAGMA table_info(audit_events)")}
        for name in (
            "event_id",
            "schema_version",
            "category",
            "event_type",
            "occurred_at",
            "source",
            "source_sequence",
            "actor_id",
            "interface",
            "correlation_id",
            "revision_before",
            "revision_after",
        ):
            self.assertIn(name, cols)
        self.assertIsNotNone(
            self.plane.conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='audit_ingest_checkpoints'"
            ).fetchone()
        )

    def test_control_mutation_populates_v3_envelope_in_same_revision(self):
        os.environ["DRLINK_INTERFACE"] = "CLI"
        before = self.plane.current_revision()
        v24.set_network_object(
            self.plane, "audit-object", type="ip", value="198.51.100.50", oneshot=True
        )
        row = self.plane.conn.execute(
            "SELECT * FROM audit_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["category"], "CONTROL")
        self.assertEqual(row["schema_version"], 1)
        self.assertTrue(str(row["event_id"]).startswith("evt_"))
        self.assertEqual(row["occurred_at"], row["timestamp"])
        self.assertEqual(row["source"], "core")
        self.assertEqual(row["interface"], "CLI")
        self.assertEqual(row["revision"], before + 1)
        self.assertEqual(row["revision_before"], before)
        self.assertEqual(row["revision_after"], before + 1)

    def test_control_event_ids_are_unique(self):
        v24.set_network_object(
            self.plane, "a", type="ip", value="198.51.100.1", oneshot=True
        )
        v24.set_network_object(
            self.plane, "b", type="ip", value="198.51.100.2", oneshot=True
        )
        ids = [
            r["event_id"]
            for r in self.plane.conn.execute(
                "SELECT event_id FROM audit_events WHERE event_id IS NOT NULL ORDER BY id"
            )
        ]
        self.assertEqual(len(ids), len(set(ids)))


class V30AuditSpoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="drlink-v30-audit-spool-"))
        self.spool = DurableAuditSpool(
            self.tmp / "spool",
            "remote-access",
            segment_bytes=16 * 1024,
            high_water_bytes=64 * 1024,
        )

    def _event(self, result="ALLOW", **kwargs):
        return build_access_decision_event(
            source="remote-access",
            event_type="remote.access.decision",
            result=result,
            resource_type="remote-service",
            resource_id="svc-1",
            matched_policy=["allow-ssh"],
            source_meta={"ip": "198.51.100.10"},
            destination_meta={"service_id": "svc-1", "port": 22, "protocol": "tcp"},
            **kwargs,
        )

    def test_sequence_is_durable_across_spool_instances(self):
        one = self.spool.enqueue(self._event())
        again = DurableAuditSpool(
            self.tmp / "spool",
            "remote-access",
            segment_bytes=16 * 1024,
            high_water_bytes=64 * 1024,
        )
        two = again.enqueue(self._event(result="DENY"))
        self.assertEqual(one["source_sequence"], 1)
        self.assertEqual(two["source_sequence"], 2)
        self.assertNotEqual(one["event_id"], two["event_id"])

    def test_secret_like_metadata_is_not_serialized(self):
        event = build_access_decision_event(
            source="remote-access",
            event_type="remote.access.decision",
            result="ALLOW",
            source_meta={
                "ip": "198.51.100.10",
                "credential": "do-not-log",
                "token": "do-not-log",
            },
            destination_meta={
                "host": "example.com",
                "port": 443,
                "payload": "secret body",
                "url": "https://example.com/?secret=1",
            },
        )
        stored = self.spool.enqueue(event)
        text = json.dumps(stored, sort_keys=True)
        self.assertIn("198.51.100.10", text)
        self.assertIn("example.com", text)
        self.assertNotIn("do-not-log", text)
        self.assertNotIn("secret body", text)
        self.assertNotIn("?secret=1", text)

    def test_spool_seals_active_segment(self):
        self.spool.enqueue(self._event())
        segment = self.spool.seal_active()
        self.assertIsNotNone(segment)
        self.assertTrue(segment.is_file())
        self.assertFalse(self.spool.active_path.exists())
        self.assertEqual(len(self.spool.segments()), 1)

    def test_high_water_fails_closed(self):
        tight = DurableAuditSpool(
            self.tmp / "tight",
            "remote-access",
            segment_bytes=16 * 1024,
            high_water_bytes=32 * 1024,
        )
        failed = False
        for idx in range(200):
            try:
                tight.enqueue(
                    build_access_decision_event(
                        source="remote-access",
                        event_type="remote.access.decision",
                        result="ALLOW",
                        resource_id="svc-%s" % idx,
                        reason_code="x" * 240,
                        destination_meta={"host": "h" * 200, "port": 443},
                    )
                )
            except AuditUnavailable:
                failed = True
                break
        self.assertTrue(failed)
        self.assertLessEqual(tight.spool_bytes(), tight.high_water_bytes)

    def test_wrong_source_or_category_rejected(self):
        bad = self._event()
        bad["source"] = "internet-access"
        with self.assertRaises(AuditEventInvalid):
            self.spool.enqueue(bad)
        bad2 = self._event()
        bad2["category"] = "CONTROL"
        with self.assertRaises(AuditEventInvalid):
            self.spool.enqueue(bad2)


class V30AuditIngestorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-audit-ingest-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        self.plane = ControlPlane(self.tmp)
        self.spool = DurableAuditSpool(
            Path(self.tmp) / "var/log/drlink/access/audit-spool",
            "remote-access",
            segment_bytes=16 * 1024,
            high_water_bytes=64 * 1024,
        )
        self.ingestor = AuditIngestor(self.plane.conn, self.spool)

    def tearDown(self):
        self.plane.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def _event(self, result, correlation):
        return build_access_decision_event(
            source="remote-access",
            event_type="remote.access.decision",
            result=result,
            resource_type="remote-service",
            resource_id="svc-1",
            action="authorize",
            reason_code="POLICY_ALLOW" if result == "ALLOW" else "POLICY_DENY",
            actor_type="network-client",
            interface="AGENT_RPC",
            correlation_id=correlation,
            matched_policy=["allow-ssh"],
            source_meta={"ip": "198.51.100.10"},
            destination_meta={
                "service_id": "svc-1",
                "service_name": "ssh-admin",
                "port": 22,
                "protocol": "tcp",
            },
        )

    def test_ingest_is_bounded_checkpointed_and_queryable(self):
        first = self.spool.enqueue(self._event("ALLOW", "corr-1"))
        second = self.spool.enqueue(self._event("DENY", "corr-2"))
        result = self.ingestor.ingest(max_segments=1)
        self.assertEqual(result["segments_processed"], 1)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["deduplicated"], 0)
        self.assertEqual(result["last_sequence"], 2)
        self.assertEqual(self.spool.segments(), [])

        rows = self.plane.conn.execute(
            "SELECT * FROM audit_events WHERE category='ACCESS_DECISION' ORDER BY source_sequence"
        ).fetchall()
        self.assertEqual([r["event_id"] for r in rows], [first["event_id"], second["event_id"]])
        self.assertEqual([r["result"] for r in rows], ["allow", "deny"])
        self.assertEqual(rows[0]["correlation_id"], "corr-1")
        self.assertEqual(json.loads(rows[0]["matched_policy_json"]), ["allow-ssh"])
        checkpoint = self.plane.conn.execute(
            "SELECT * FROM audit_ingest_checkpoints WHERE source='remote-access'"
        ).fetchone()
        self.assertEqual(checkpoint["last_sequence"], 2)

    def test_reingest_duplicate_event_id_is_idempotent(self):
        first = self.spool.enqueue(self._event("ALLOW", "corr-1"))
        self.ingestor.ingest()
        duplicate = self._event("ALLOW", "corr-1-repeat")
        duplicate["event_id"] = first["event_id"]
        self.spool.enqueue(duplicate)
        result = self.ingestor.ingest()
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["deduplicated"], 1)
        count = self.plane.conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE event_id=?", (first["event_id"],)
        ).fetchone()[0]
        self.assertEqual(count, 1)
        checkpoint = self.plane.conn.execute(
            "SELECT last_sequence FROM audit_ingest_checkpoints WHERE source='remote-access'"
        ).fetchone()[0]
        self.assertEqual(checkpoint, 2)

    def test_invalid_segment_is_retained_and_not_checkpointed(self):
        bad = self.spool.root / "segment-00000000000000000001-bad.jsonl"
        bad.write_text("{not-json}\n", encoding="utf-8")
        with self.assertRaises(AuditEventInvalid):
            self.ingestor.ingest()
        self.assertTrue(bad.exists())
        self.assertIsNone(
            self.plane.conn.execute(
                "SELECT * FROM audit_ingest_checkpoints WHERE source='remote-access'"
            ).fetchone()
        )

    def test_ingest_does_not_create_configuration_revision(self):
        self.spool.enqueue(self._event("ALLOW", "corr-1"))
        before = self.plane.current_revision()
        self.ingestor.ingest()
        after = self.plane.current_revision()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
