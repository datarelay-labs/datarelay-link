#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_partial_state_write_is_completed_before_event_persistence(self):
        original_write = os.write
        shortened = []

        def partial_state_write(fd, data):
            path = os.readlink("/proc/self/fd/%d" % fd)
            if ".state." in path and not shortened:
                shortened.append(True)
                return original_write(fd, data[:7])
            return original_write(fd, data)

        with patch("drlink_v30_audit.os.write", side_effect=partial_state_write):
            event = self.spool.enqueue(self._event())
        self.assertEqual(shortened, [True])
        state = json.loads(self.spool.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["next_sequence"], event["source_sequence"] + 1)
        recorded = json.loads(self.spool.active_path.read_text(encoding="utf-8"))
        self.assertEqual(recorded["event_id"], event["event_id"])

    def test_partial_event_write_is_completed_before_enqueue_success(self):
        original_write = os.write
        shortened = []

        def partial_event_write(fd, data):
            path = os.readlink("/proc/self/fd/%d" % fd)
            if path.endswith("/active.jsonl") and not shortened:
                shortened.append(True)
                return original_write(fd, data[:13])
            return original_write(fd, data)

        with patch("drlink_v30_audit.os.write", side_effect=partial_event_write):
            event = self.spool.enqueue(self._event())
        self.assertEqual(shortened, [True])
        lines = self.spool.active_path.read_bytes().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event_id"], event["event_id"])
        self.assertEqual(json.loads(lines[0])["source_sequence"], 1)

    def test_state_commit_failure_never_appends_or_leaks_uncommitted_state(self):
        original_replace = os.replace
        injected = []

        def fail_state_commit(source, destination):
            if str(destination) == str(self.spool.state_path):
                injected.append(True)
                raise OSError("state storage was unavailable")
            return original_replace(source, destination)

        with patch("drlink_v30_audit.os.replace", side_effect=fail_state_commit):
            with self.assertRaises(AuditUnavailable):
                self.spool.enqueue(self._event())
        self.assertEqual(injected, [True])
        self.assertFalse(self.spool.state_path.exists())
        self.assertFalse(self.spool.active_path.exists())
        self.assertEqual(list(self.spool.root.glob(".state.*.tmp")), [])

    def test_failed_state_replacement_preserves_previous_event_and_sequence(self):
        first = self.spool.enqueue(self._event())
        before_state = self.spool.state_path.read_bytes()
        before_active = self.spool.active_path.read_bytes()
        original_replace = os.replace

        def reject_state_replace(source, destination):
            if str(destination) == str(self.spool.state_path):
                raise OSError("state commit interrupted")
            return original_replace(source, destination)

        with patch("drlink_v30_audit.os.replace", side_effect=reject_state_replace):
            with self.assertRaises(AuditUnavailable):
                self.spool.enqueue(self._event(result="DENY"))
        self.assertEqual(self.spool.state_path.read_bytes(), before_state)
        self.assertEqual(self.spool.active_path.read_bytes(), before_active)
        self.assertEqual(list(self.spool.root.glob(".state.*.tmp")), [])
        second = self.spool.enqueue(self._event(result="DENY"))
        self.assertEqual(second["source_sequence"], first["source_sequence"] + 1)

    def test_state_open_failure_never_appends_or_leaks_credentials(self):
        original_open = os.open
        injected = []

        def fail_state_open(path, flags, *args, **kwargs):
            if Path(path).name.startswith(".state."):
                injected.append(True)
                raise OSError("state file could not be created")
            return original_open(path, flags, *args, **kwargs)

        with patch("drlink_v30_audit.os.open", side_effect=fail_state_open):
            with self.assertRaises(AuditUnavailable):
                self.spool.enqueue(self._event())
        self.assertEqual(injected, [True])
        self.assertFalse(self.spool.state_path.exists())
        self.assertFalse(self.spool.active_path.exists())
        self.assertEqual(list(self.spool.root.glob(".state.*.tmp")), [])

    def test_zero_progress_state_write_never_commits_or_appends(self):
        original_write = os.write
        injected = []

        def zero_state_write(fd, data):
            path = os.readlink("/proc/self/fd/%d" % fd)
            if ".state." in path and not injected:
                injected.append(True)
                return 0
            return original_write(fd, data)

        with patch("drlink_v30_audit.os.write", side_effect=zero_state_write):
            with self.assertRaises(AuditUnavailable):
                self.spool.enqueue(self._event())
        self.assertEqual(injected, [True])
        self.assertFalse(self.spool.state_path.exists())
        self.assertFalse(self.spool.active_path.exists())
        self.assertEqual(list(self.spool.root.glob(".state.*.tmp")), [])

    def test_zero_progress_event_write_fails_closed(self):
        original_write = os.write
        injected = []

        def zero_event_write(fd, data):
            path = os.readlink("/proc/self/fd/%d" % fd)
            if path.endswith("/active.jsonl") and not injected:
                injected.append(True)
                return 0
            return original_write(fd, data)

        with patch("drlink_v30_audit.os.write", side_effect=zero_event_write):
            with self.assertRaises(AuditUnavailable):
                self.spool.enqueue(self._event())
        self.assertEqual(injected, [True])
        self.assertEqual(self.spool.active_path.read_bytes(), b"")

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

    def test_corrupt_sequence_state_fails_closed_without_reusing_sequence(self):
        first = self.spool.enqueue(self._event())
        self.assertEqual(first["source_sequence"], 1)
        state = json.loads(self.spool.state_path.read_text(encoding="utf-8"))
        before = self.spool.active_path.read_bytes()
        for invalid in (0, -1, True, False, 2.9, "2", None, "MISSING"):
            with self.subTest(next_sequence=repr(invalid)):
                corrupted = dict(state)
                if invalid == "MISSING":
                    corrupted.pop("next_sequence")
                else:
                    corrupted["next_sequence"] = invalid
                self.spool.state_path.write_text(
                    json.dumps(corrupted) + "\n", encoding="utf-8"
                )
                with self.assertRaises(AuditUnavailable):
                    self.spool.enqueue(self._event())
                self.assertEqual(self.spool.active_path.read_bytes(), before)
                self.assertEqual(self.spool.segments(), [])
        self.spool.state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
        second = self.spool.enqueue(self._event(result="DENY"))
        self.assertEqual(second["source_sequence"], 2)

    def test_missing_sequence_state_with_pending_spool_fails_closed(self):
        self.spool.enqueue(self._event())
        before = self.spool.active_path.read_bytes()
        self.spool.state_path.unlink()
        with self.assertRaises(AuditUnavailable):
            self.spool.enqueue(self._event(result="DENY"))
        self.assertEqual(self.spool.active_path.read_bytes(), before)
        self.assertFalse(self.spool.state_path.exists())

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

    def test_spool_rejects_unapproved_event_fields_before_durability(self):
        # Direct callers and imported segments must follow the same secret-safe envelope.
        cases = (
            {"source_meta": {"ip": "198.51.100.10", "credential": "hidden-token"}},
            {"destination_meta": {"port": 22, "authorization": "hidden-token"}},
            {"raw_payload": "hidden-token"},
        )
        for extra in cases:
            with self.subTest(extra=tuple(extra)):
                event = self._event()
                event.update(extra)
                previous_bytes = self.spool.spool_bytes()
                with self.assertRaises(AuditEventInvalid):
                    self.spool.enqueue(event)
                self.assertEqual(self.spool.spool_bytes(), previous_bytes)

    def test_matched_policy_envelope_rejects_untrusted_values_without_sequence_loss(self):
        first = self.spool.enqueue(self._event())
        self.assertEqual(first["source_sequence"], 1)
        before_state = self.spool.state_path.read_bytes()
        before_active = self.spool.active_path.read_bytes()
        malformed = (
            "allow-ssh",
            {"policy": "allow-ssh"},
            [42],
            [{"credential": "sensitive-not-a-rule"}],
            [None],
            [""],
            [" "],
            ["x" * 257],
            ["rule-%02d" % i for i in range(33)],
        )
        for value in malformed:
            with self.subTest(value=repr(value)[:70]):
                event = self._event()
                event["matched_policy"] = value
                with self.assertRaises(AuditEventInvalid):
                    self.spool.enqueue(event)
                self.assertEqual(self.spool.state_path.read_bytes(), before_state)
                self.assertEqual(self.spool.active_path.read_bytes(), before_active)
        second = self.spool.enqueue(self._event(result="DENY"))
        self.assertEqual(second["source_sequence"], 2)

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

    def test_invalid_ingest_batch_limit_never_seals_or_mutates_audit(self):
        self.spool.enqueue(self._event("ALLOW", "invalid-limit"))
        before_active = self.spool.active_path.read_bytes()
        before_state = self.spool.state_path.read_bytes()
        for invalid in (0, -1, True, False, 1.5, "1", b"1", None):
            with self.subTest(limit=repr(invalid)):
                with self.assertRaises(ValueError):
                    self.ingestor.ingest(max_segments=invalid)
                self.assertEqual(self.spool.active_path.read_bytes(), before_active)
                self.assertEqual(self.spool.state_path.read_bytes(), before_state)
                self.assertEqual(self.spool.segments(), [])
                self.assertEqual(
                    self.plane.conn.execute(
                        "SELECT COUNT(*) FROM audit_events WHERE category='ACCESS_DECISION'"
                    ).fetchone()[0], 0
                )
        self.assertEqual(self.ingestor.ingest(max_segments=1)["inserted"], 1)

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

    def test_ingest_rejects_coerced_schema_and_sequence_before_checkpoint(self):
        valid = self.spool.enqueue(self._event("ALLOW", "typed-evidence"))
        segment = self.spool.seal_active()
        self.assertIsNotNone(segment)
        for key, invalid in (
            ("schema_version", True),
            ("schema_version", "1"),
            ("schema_version", 1.5),
            ("source_sequence", True),
            ("source_sequence", "1"),
            ("source_sequence", 1.7),
        ):
            with self.subTest(field=key, value=repr(invalid)):
                malformed = dict(valid, **{key: invalid})
                segment.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
                with self.assertRaises(AuditEventInvalid):
                    self.ingestor.ingest(max_segments=1)
                self.assertTrue(segment.exists())
                self.assertIsNone(
                    self.plane.conn.execute(
                        "SELECT * FROM audit_ingest_checkpoints WHERE source='remote-access'"
                    ).fetchone()
                )
                self.assertEqual(
                    self.plane.conn.execute(
                        "SELECT COUNT(*) FROM audit_events WHERE category='ACCESS_DECISION'"
                    ).fetchone()[0], 0
                )
        segment.write_text(json.dumps(valid) + "\n", encoding="utf-8")
        self.assertEqual(self.ingestor.ingest(max_segments=1)["inserted"], 1)

    def test_ingest_rejects_nested_or_nonlist_policy_evidence(self):
        valid = self.spool.enqueue(self._event("ALLOW", "strict-policy-evidence"))
        segment = self.spool.seal_active()
        self.assertIsNotNone(segment)
        for invalid in ("allow-ssh", {"policy": "allow-ssh"},
                        [{"credential": "must-not-be-imported"}], [False],
                        [" "], ["x" * 257]):
            with self.subTest(value=repr(invalid)[:70]):
                malformed = dict(valid, matched_policy=invalid)
                segment.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
                with self.assertRaises(AuditEventInvalid):
                    self.ingestor.ingest(max_segments=1)
                self.assertTrue(segment.exists())
                self.assertIsNone(self.plane.conn.execute(
                    "SELECT * FROM audit_ingest_checkpoints WHERE source='remote-access'"
                ).fetchone())
                self.assertEqual(self.plane.conn.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE category='ACCESS_DECISION'"
                ).fetchone()[0], 0)
        segment.write_text(json.dumps(valid) + "\n", encoding="utf-8")
        self.assertEqual(self.ingestor.ingest(max_segments=1)["inserted"], 1)

    def test_ingest_rejects_coerced_destination_port_evidence(self):
        valid = self.spool.enqueue(self._event("ALLOW", "port-evidence"))
        segment = self.spool.seal_active()
        self.assertIsNotNone(segment)
        for invalid in ("22", 22.9, True, False):
            with self.subTest(port=repr(invalid)):
                malformed = dict(valid)
                malformed["destination_meta"] = dict(valid["destination_meta"], port=invalid)
                segment.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
                with self.assertRaises(AuditEventInvalid):
                    self.ingestor.ingest(max_segments=1)
                self.assertIsNone(self.plane.conn.execute(
                    "SELECT * FROM audit_ingest_checkpoints WHERE source='remote-access'"
                ).fetchone())
                self.assertEqual(self.plane.conn.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE category='ACCESS_DECISION'"
                ).fetchone()[0], 0)
        segment.write_text(json.dumps(valid) + "\n", encoding="utf-8")
        self.assertEqual(self.ingestor.ingest(max_segments=1)["inserted"], 1)

    def test_invalid_segment_is_retained_and_not_checkpointed(self):
        # A durable producer has sequence state even when a segment is corrupt.
        self.spool.state_path.write_text(
            json.dumps({"next_sequence": 2, "enqueue_failures": 0, "dropped_deny_count": 0}) + "\n",
            encoding="utf-8",
        )
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
