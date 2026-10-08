#!/usr/bin/env python3
from __future__ import annotations
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"lib"))
from drlink_control_db import ControlPlaneError
from drlink_service_accounts import ServiceAccountStore

class ServiceAccountTests(unittest.TestCase):
    def test_display_once_hash_rotate_revoke_and_permissions(self):
        root=tempfile.mkdtemp(prefix="drlink-sa-")
        with ServiceAccountStore(root) as store:
            created=store.create("backup-bot",["management-read","management-diagnose"])
            token=created["credential"]
            db=(Path(root)/"var/lib/drlink/drlink.db").read_bytes()
            self.assertNotIn(token.encode(),db)
            actor=store.authenticate(token)
            self.assertEqual(actor.role,"Service Account")
            self.assertEqual(actor.permissions,frozenset({"management-read","management-diagnose"}))
            rotated=store.rotate(created["id"])
            with self.assertRaises(ControlPlaneError): store.authenticate(token)
            self.assertEqual(store.authenticate(rotated["credential"]).actor_id,created["id"])
            store.revoke(created["id"])
            with self.assertRaises(ControlPlaneError): store.authenticate(rotated["credential"])
    def test_rejects_unknown_permission(self):
        with ServiceAccountStore(tempfile.mkdtemp(prefix="drlink-sa-")) as store:
            with self.assertRaises(ControlPlaneError): store.create("bad",["command-exec"])
    def test_duplicate_names_expiry_and_atomic_audit(self):
        with ServiceAccountStore(tempfile.mkdtemp(prefix="drlink-sa-validation-")) as store:
            from datetime import datetime, timedelta, timezone
            with self.assertRaises(ControlPlaneError):
                store.create("past", ["management-read"],
                             (datetime.now(timezone.utc)-timedelta(days=1)).isoformat())
            first = store.create("same-name", ["management-read"])
            with self.assertRaises(ControlPlaneError):
                store.create("SAME-NAME", ["management-read"])
            actor = store.authenticate(first["credential"])
            store.audit_request(actor, operation="drlink_inventory_list", allowed=True)
            event = store.conn.execute(
                "SELECT operation,actor_id FROM audit_events "
                "WHERE event_type='service_account.request.allowed' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(tuple(event), ("drlink_inventory_list", first["id"]))
            self.assertEqual(len(store.list_accounts()["items"]), 1)

if __name__=="__main__": unittest.main()
