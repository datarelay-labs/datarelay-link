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
