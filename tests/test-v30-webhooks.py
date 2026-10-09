#!/usr/bin/env python3
from __future__ import annotations
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"lib"))
from drlink_control_db import ControlPlaneError
from drlink_webhooks import WebhookStore, validate_webhook_url

class WebhookTests(unittest.TestCase):
    def test_explicit_test_delivery_is_audited_atomically_and_bounded(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(prefix="drlink-wh-test-event-") as root:
            with WebhookStore(root) as store:
                hook = store.create(
                    "test-sink", "https://hooks.example.org/events",
                    ["security.lifecycle"], actor_id="web:admin",
                )
                queued = store.test_delivery(hook["id"], actor_id="web:admin")
                self.assertEqual(queued["webhook_id"], hook["id"])
                self.assertEqual(queued["status"], "QUEUED")
                self.assertNotIn("secret", queued)
                row = store.conn.execute(
                    "SELECT event_type,status,payload_json FROM management_webhook_outbox "
                    "WHERE event_id=?", (queued["event_id"],),
                ).fetchone()
                self.assertEqual((row["event_type"], row["status"]),
                                 ("security.lifecycle", "PENDING"))
                self.assertEqual(__import__("json").loads(row["payload_json"])["data"],
                                 {"kind": "test-delivery"})
                self.assertNotIn(hook["secret"], row["payload_json"])
                audit = store.conn.execute(
                    "SELECT actor_id FROM audit_events WHERE "
                    "event_type='management_webhook.test_requested' AND entity_id=?",
                    (hook["id"],),
                ).fetchone()
                self.assertEqual(audit["actor_id"], "web:admin")
                before = store.conn.execute(
                    "SELECT COUNT(*) FROM management_webhook_outbox"
                ).fetchone()[0]
                with patch.object(store, "_audit", side_effect=RuntimeError("audit down")):
                    with self.assertRaises(RuntimeError):
                        store.test_delivery(hook["id"], actor_id="web:admin")
                self.assertEqual(store.conn.execute(
                    "SELECT COUNT(*) FROM management_webhook_outbox"
                ).fetchone()[0], before)
                store.disable(hook["id"], actor_id="web:admin")
                with self.assertRaises(ControlPlaneError):
                    store.test_delivery(hook["id"], actor_id="web:admin")

    def test_https_webhook_rejects_empty_userinfo_in_authority(self):
        for url in (
            "https://@hooks.example.org/events",
            "https://:@hooks.example.org/events",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ControlPlaneError):
                    validate_webhook_url(url)
        self.assertEqual(
            validate_webhook_url("https://hooks.example.org/events"),
            ("https://hooks.example.org/events", "hooks.example.org", "/events"),
        )

    def test_https_signature_and_event_filter(self):
        root=tempfile.mkdtemp(prefix="drlink-wh-")
        with WebhookStore(root) as store:
            with self.assertRaises(ControlPlaneError):
                store.create("bad","http://example.test/hook",["attention"])
            wh=store.create("ops","https://example.test/hook",["attention"])
            event=store.enqueue(wh["id"],"attention",{"kind":"version-drift","count":2})
            rotated=store.rotate_secret(wh["id"])
            self.assertNotEqual(rotated["secret"],wh["secret"])
            self.assertEqual(store.conn.execute("SELECT secret_hash FROM management_webhooks WHERE id=?",(wh["id"],)).fetchone()[0],__import__('hashlib').sha256(rotated["secret"].encode()).hexdigest())
            sig=store.signature(wh["secret"],event)
            self.assertTrue(store.verify(wh["secret"],event,sig))
            self.assertEqual(len(store.pending()),1)
            for attempt in range(5):
                claim = store.claim_due()[0]
                self.assertEqual(claim["event_id"], event["event_id"])
                self.assertTrue(store.record_attempt(
                    event["event_id"], lease_token=claim["lease_token"],
                    delivered=False, error="temporary failure",
                ))
                if attempt != 4:
                    store.conn.execute(
                        "UPDATE management_webhook_outbox SET next_attempt_at=? WHERE event_id=?",
                        ("2000-01-01T00:00:00Z", event["event_id"]),
                    )
            self.assertEqual(store.pending(),[])
            row=store.conn.execute("SELECT status,attempts FROM management_webhook_outbox WHERE event_id=?",(event["event_id"],)).fetchone()
            self.assertEqual((row["status"],row["attempts"]),("FAILED",5))
            with self.assertRaises(ControlPlaneError):
                store.enqueue(wh["id"],"control",{"kind":"other"})
    def test_terminal_history_retention_never_erases_pending(self):
        with WebhookStore(tempfile.mkdtemp(prefix="drlink-wh-retention-")) as store:
            hook = store.create("retention","https://hooks.example.org/hook",["attention"])
            for i in range(12):
                event = store.enqueue(hook["id"],"attention",{"sequence":i})
                claim = store.claim_due()[0]
                self.assertTrue(store.record_attempt(
                    event["event_id"], lease_token=claim["lease_token"], delivered=True,
                ))
            keep = store.enqueue(hook["id"],"attention",{"sequence":"pending"})
            self.assertEqual(store.prune_history(max_completed=10), 2)
            self.assertEqual(len(store.pending()), 1)
            self.assertEqual(store.pending()[0]["event_id"],keep["event_id"])
            self.assertEqual(store.conn.execute(
                "SELECT COUNT(*) FROM management_webhook_outbox WHERE status='DELIVERED'"
            ).fetchone()[0], 10)

    def test_attention_surfaces_delivery_failure_without_mutating_policy(self):
        from drlink_management_service import ManagementQueryService
        root = tempfile.mkdtemp(prefix="drlink-wh-health-")
        from drlink_control_db import open_control_db
        open_control_db(root).close()  # Base Core installed; optional Webhooks absent.
        with ManagementQueryService(root) as service:
            self.assertEqual(service._webhook_delivery_attention()["failed"], 0)
        with WebhookStore(root) as store:
            hook = store.create("health", "https://hooks.example.org/health", ["attention"])
            event = store.enqueue(hook["id"], "attention", {"kind": "warning"})
            for attempt in range(5):
                claim = store.claim_due()[0]
                self.assertTrue(store.record_attempt(
                    event["event_id"], lease_token=claim["lease_token"],
                    delivered=False, error="timeout",
                ))
                if attempt != 4:
                    store.conn.execute(
                        "UPDATE management_webhook_outbox SET next_attempt_at=? WHERE event_id=?",
                        ("2000-01-01T00:00:00Z", event["event_id"]),
                    )
        with ManagementQueryService(root) as service:
            self.assertEqual(service._webhook_delivery_attention()["failed"], 1)
            result = service.attention_summary()
            self.assertIn("webhook-delivery", {x["kind"] for x in result["items"]})
            self.assertEqual(result["signals"]["webhook_delivery"]["failed"], 1)

    def test_existing_webhook_outbox_adds_lease_token_without_losing_events(self):
        from drlink_control_db import open_control_db

        root = tempfile.mkdtemp(prefix="drlink-wh-migrate-")
        conn = open_control_db(root)
        try:
            conn.execute("""
                CREATE TABLE management_webhook_outbox (
                    event_id TEXT PRIMARY KEY, webhook_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT, last_attempt_at TEXT,
                    last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO management_webhook_outbox "
                "(event_id,webhook_id,event_type,payload_json,status,created_at) "
                "VALUES (?,?,?,?,?,?)",
                ("legacy-event", "legacy-hook", "attention", "{}", "PENDING",
                 "2026-10-08T00:00:00Z"),
            )
        finally:
            conn.close()
        with WebhookStore(root) as migrated:
            columns = {str(r[1]) for r in migrated.conn.execute(
                "PRAGMA table_info(management_webhook_outbox)"
            )}
            self.assertIn("lease_token", columns)
            row = migrated.conn.execute(
                "SELECT event_id,status,lease_token FROM management_webhook_outbox "
                "WHERE event_id='legacy-event'"
            ).fetchone()
            self.assertEqual((row["event_id"], row["status"], row["lease_token"]),
                             ("legacy-event", "PENDING", ""))

    def test_reclaimed_delivery_rejects_old_lease_and_preserves_event_id(self):
        root = tempfile.mkdtemp(prefix="drlink-wh-reclaim-")
        with WebhookStore(root) as first_worker:
            hook = first_worker.create(
                "recovery", "https://hooks.example.org/events", ["attention"]
            )
            event = first_worker.enqueue(hook["id"], "attention", {"kind": "recovery"})
            original = first_worker.claim_due()
            self.assertEqual(len(original), 1)
            old_lease = original[0]["lease_token"]
            with self.assertRaises(ControlPlaneError):
                first_worker.record_attempt(
                    event["event_id"], lease_token="not-a-lease", delivered=True,
                )
            first_worker.conn.execute(
                "UPDATE management_webhook_outbox SET last_attempt_at=? WHERE event_id=?",
                ("2000-01-01T00:00:00Z", event["event_id"]),
            )
            with WebhookStore(root) as second_worker:
                recovered = second_worker.claim_due()
                self.assertEqual(len(recovered), 1)
                self.assertEqual(recovered[0]["event_id"], event["event_id"])
                new_lease = recovered[0]["lease_token"]
                self.assertNotEqual(old_lease, new_lease)
                self.assertFalse(first_worker.record_attempt(
                    event["event_id"], lease_token=old_lease, delivered=True,
                ))
                self.assertTrue(second_worker.record_attempt(
                    event["event_id"], lease_token=new_lease,
                    delivered=False, error="temporary outage",
                ))
                self.assertFalse(second_worker.record_attempt(
                    event["event_id"], lease_token=new_lease, delivered=True,
                ))
                row = second_worker.conn.execute(
                    "SELECT status,attempts,lease_token FROM management_webhook_outbox "
                    "WHERE event_id=?", (event["event_id"],),
                ).fetchone()
                self.assertEqual((row["status"], row["attempts"], row["lease_token"]),
                                 ("PENDING", 1, ""))
                self.assertEqual(second_worker.claim_due(), [])  # honor retry backoff
                second_worker.conn.execute(
                    "UPDATE management_webhook_outbox SET next_attempt_at=? WHERE event_id=?",
                    ("2000-01-01T00:00:00Z", event["event_id"]),
                )
                final_claim = second_worker.claim_due()[0]
                self.assertTrue(second_worker.record_attempt(
                    event["event_id"], lease_token=final_claim["lease_token"],
                    delivered=True,
                ))
                self.assertFalse(first_worker.record_attempt(
                    event["event_id"], lease_token=old_lease, delivered=False,
                ))
                row = second_worker.conn.execute(
                    "SELECT status,attempts FROM management_webhook_outbox WHERE event_id=?",
                    (event["event_id"],),
                ).fetchone()
                self.assertEqual((row["status"], row["attempts"]), ("DELIVERED", 2))

if __name__=="__main__": unittest.main()
