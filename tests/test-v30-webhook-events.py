#!/usr/bin/env python3
"""Webhook audit cursor persistence, event filtering and idempotent outbox."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_service_accounts import ServiceAccountStore
from drlink_webhook_events import stage_audit_events
from drlink_webhooks import WebhookStore


class AuditEventBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-audit-to-hook-")
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_security_lifecycle_stages_once_with_stable_event_id(self):
        with WebhookStore(self.root) as hooks:
            hook = hooks.create("security", "https://sink.example.net/events", [
                "security.lifecycle",
            ])
            self.assertEqual(stage_audit_events(hooks)["staged"], 0)
        with ServiceAccountStore(self.root) as accounts:
            created = accounts.create("audit-bot", ["management-read"])
        with WebhookStore(self.root) as hooks:
            result = stage_audit_events(hooks)
            self.assertEqual(result["staged"], 1)
            row = hooks.conn.execute(
                "SELECT event_id,payload_json FROM management_webhook_outbox WHERE webhook_id=?",
                (hook["id"],),
            ).fetchone()
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["event_id"], row["event_id"])
            self.assertEqual(payload["event_type"], "security.lifecycle")
            self.assertEqual(payload["data"]["event"], "service_account.created")
            self.assertEqual(payload["data"]["resource_type"], "service-account")
            self.assertNotIn("resource_id", payload["data"])
            self.assertRegex(payload["data"]["resource_fingerprint"], r"^[0-9a-f]{16}$")
            self.assertNotIn(created["credential"], row["payload_json"])
            self.assertEqual(stage_audit_events(hooks)["staged"], 0)
        # A second independent worker process does not replay old audit events.
        with WebhookStore(self.root) as hooks:
            self.assertEqual(stage_audit_events(hooks)["staged"], 0)
            self.assertEqual(hooks.conn.execute(
                "SELECT COUNT(*) FROM management_webhook_outbox"
            ).fetchone()[0], 1)

    def test_explicit_test_delivery_does_not_emit_a_second_audit_notification(self):
        # The operator intentionally queues exactly one test event. Its audit
        # receipt is retained locally but must not fan out as an extra event.
        with WebhookStore(self.root) as hooks:
            a = hooks.create("a", "https://sink.example.net/a", ["security.lifecycle"])
            b = hooks.create("b", "https://sink.example.net/b", ["security.lifecycle"])
            # Previously emitted administrative lifecycle events are legitimate.
            stage_audit_events(hooks)
            existing = {
                row["event_id"] for row in hooks.conn.execute(
                    "SELECT event_id FROM management_webhook_outbox"
                )
            }
            requested = hooks.test_delivery(a["id"], actor_id="web:admin")
            self.assertEqual(stage_audit_events(hooks)["staged"], 0)
            outbox = hooks.conn.execute(
                "SELECT event_id, webhook_id FROM management_webhook_outbox"
            ).fetchall()
            self.assertEqual(
                {
                    (row["event_id"], row["webhook_id"]) for row in outbox
                    if row["event_id"] not in existing
                },
                {(requested["event_id"], a["id"])},
            )
            self.assertEqual(hooks.conn.execute(
                "SELECT COUNT(*) FROM audit_events WHERE "
                "event_type='management_webhook.test_requested'"
            ).fetchone()[0], 1)
            self.assertEqual(stage_audit_events(hooks)["staged"], 0)

    def test_nonpositive_audit_stage_batch_leaves_cursors_and_queue_unchanged(self):
        from drlink_control_db import ControlPlaneError
        with WebhookStore(self.root) as hooks:
            created = hooks.create(
                "security", "https://sink.example.net/events", ["security.lifecycle"]
            )
            baseline = hooks.conn.execute(
                "SELECT last_audit_id FROM management_webhook_audit_cursors "
                "WHERE webhook_id=?", (created["id"],)
            ).fetchone()[0]
        with ServiceAccountStore(self.root) as accounts:
            accounts.create("batch-check", ["management-read"])
        with WebhookStore(self.root) as hooks:
            for invalid in (0, -1, False, True, 1.5, "0"):
                with self.subTest(batch_limit=invalid), self.assertRaises(ControlPlaneError):
                    stage_audit_events(hooks, limit=invalid)
                self.assertEqual(hooks.conn.execute(
                    "SELECT last_audit_id FROM management_webhook_audit_cursors "
                    "WHERE webhook_id=?", (created["id"],)
                ).fetchone()[0], baseline)
                self.assertEqual(hooks.conn.execute(
                    "SELECT COUNT(*) FROM management_webhook_outbox"
                ).fetchone()[0], 0)
            self.assertEqual(stage_audit_events(hooks, limit=1)["staged"], 1)

    def test_bounded_multi_subscription_backlog_preserves_each_audit_cursor(self):
        import drlink_webhook_events
        from unittest.mock import patch
        with WebhookStore(self.root) as hooks:
            first = hooks.create(
                "first", "https://sink.example.net/first", ["security.lifecycle"]
            )
            second = hooks.create(
                "second", "https://sink.example.net/second", ["security.lifecycle"]
            )
            # Drain legitimate administrative events before measuring this audit.
            stage_audit_events(hooks)
            for claim in hooks.claim_due():
                self.assertTrue(hooks.record_attempt(
                    claim["event_id"], lease_token=claim["lease_token"],
                    delivered=True,
                ))
        with ServiceAccountStore(self.root) as accounts:
            accounts.create("bounded-multi-sink", ["management-read"])
        with patch.object(drlink_webhook_events, "MAX_OUTBOX", 1):
            with WebhookStore(self.root) as hooks:
                self.assertEqual(stage_audit_events(hooks)["staged"], 1)
                pending = hooks.pending()
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["webhook_id"], first["id"])
                # Repeated worker ticks must not steal the other sink's event.
                self.assertEqual(stage_audit_events(hooks)["staged"], 0)
                claim = hooks.claim_due()[0]
                self.assertTrue(hooks.record_attempt(
                    claim["event_id"], lease_token=claim["lease_token"],
                    delivered=True,
                ))
                self.assertEqual(stage_audit_events(hooks)["staged"], 1)
                pending = hooks.pending()
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["webhook_id"], second["id"])
                self.assertEqual(stage_audit_events(hooks)["staged"], 0)
                rows = hooks.conn.execute(
                    "SELECT webhook_id,payload_json FROM management_webhook_outbox "
                    "WHERE event_type='security.lifecycle'"
                ).fetchall()
                observed = [
                    (row["webhook_id"], json.loads(row["payload_json"])["data"]["event"])
                    for row in rows
                ]
                self.assertEqual(
                    sorted((hook_id, event) for hook_id, event in observed
                           if event == "service_account.created"),
                    [(first["id"], "service_account.created"),
                     (second["id"], "service_account.created")],
                )

    def test_irrelevant_events_do_not_generate_deliveries(self):
        with WebhookStore(self.root) as hooks:
            hook = hooks.create("attention-only", "https://sink.example.net/alert", ["attention"])
        with ServiceAccountStore(self.root) as accounts:
            accounts.create("ignored-bot", ["management-read"])
        with WebhookStore(self.root) as hooks:
            result = stage_audit_events(hooks)
            self.assertEqual(result["staged"], 0)
            self.assertEqual(hooks.conn.execute(
                "SELECT COUNT(*) FROM management_webhook_outbox"
            ).fetchone()[0], 0)

    def test_backlog_full_preserves_cursor_for_next_tick(self):
        import drlink_webhook_events
        with WebhookStore(self.root) as hooks:
            hook = hooks.create("security", "https://sink.example.net/events", [
                "security.lifecycle",
            ])
        with ServiceAccountStore(self.root) as accounts:
            accounts.create("sensitive", ["management-read"])
        from unittest.mock import patch
        with patch.object(drlink_webhook_events, "MAX_OUTBOX", 0):
            with WebhookStore(self.root) as hooks:
                self.assertEqual(stage_audit_events(hooks)["staged"], 0)
        with WebhookStore(self.root) as hooks:
            self.assertEqual(stage_audit_events(hooks)["staged"], 1)


if __name__ == "__main__":
    unittest.main()
