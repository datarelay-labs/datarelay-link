#!/usr/bin/env python3
from __future__ import annotations
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"lib"))
from drlink_control_db import ControlPlaneError
from drlink_webhooks import WebhookStore

class WebhookTests(unittest.TestCase):
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
                store.record_attempt(event["event_id"],delivered=False,error="temporary failure")
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
                store.record_attempt(event["event_id"],delivered=True)
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
            for _ in range(5):
                store.record_attempt(event["event_id"], delivered=False, error="timeout")
        with ManagementQueryService(root) as service:
            self.assertEqual(service._webhook_delivery_attention()["failed"], 1)
            result = service.attention_summary()
            self.assertIn("webhook-delivery", {x["kind"] for x in result["items"]})
            self.assertEqual(result["signals"]["webhook_delivery"]["failed"], 1)

if __name__=="__main__": unittest.main()
