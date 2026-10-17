#!/usr/bin/env python3
"""Regression: Server Service Object deletion and Agent publication must serialize."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
import drlink_v24 as v24
import drlink_mgmt_sync as mgmt

OWNER = "aabbccddeeff00112233445566778899"


class ServiceObjectReferenceRace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-ref-pub-race-")
        path = Path(self.tmp.name, "etc/drlink")
        path.mkdir(parents=True)
        (path / "config.json").write_text('{"role":"server"}\n')
        self.env = mock.patch.dict(os.environ, {
            "FRP_DEPLOY_TEST_ROOT": self.tmp.name,
            "DRLINK_SKIP_ACTIVATION": "1",
            "DRLINK_CONFIRM": "yes",
        })
        self.env.start()
        self.deleting = ControlPlane(self.tmp.name)
        self.competing = ControlPlane(self.tmp.name)
        v24.ensure_v2_schema(self.deleting.conn)
        v24.ensure_v2_schema(self.competing.conn)
        self.deleting.upsert_client(OWNER, label="test-gateway", hostname="test-gateway")
        v24.set_service_object(self.deleting, "target", type="fixed-tcp",
                               port=29771, oneshot=True)

    def tearDown(self):
        self.competing.close()
        self.deleting.close()
        self.env.stop()
        self.tmp.cleanup()

    def publish(self, plane):
        return mgmt.server_upsert_remote_service(
            plane,
            mgmt.MgmtAuthContext(OWNER, {"id": OWNER}, "test-nonce", 1),
            {"name": "racing-publication", "destination": "this-host",
             "service": "target", "pool_class": "fixed-tcp", "enabled": True},
        )

    def test_upsert_rechecks_deleted_service_object_after_early_resolution(self):
        # Emulate a second independently committed CLI delete between initial
        # authoritative resolution and the publication write transaction.
        original = mgmt._mutate_publication
        def delete_between_read_and_write(*args, **kwargs):
            v24.unset_service_object(self.competing, "target", confirm=True)
            return original(*args, **kwargs)
        with mock.patch.object(mgmt, "_mutate_publication",
                               side_effect=delete_between_read_and_write):
            with self.assertRaises((ControlPlaneError, mgmt.MgmtSyncError)):
                self.publish(self.deleting)
        self.assertIsNone(self.deleting.conn.execute(
            "SELECT id FROM published_services WHERE name='racing-publication'"
        ).fetchone())
        self.assertIsNone(self.deleting.conn.execute(
            "SELECT id FROM service_objects WHERE name='target'"
        ).fetchone())

    def test_upsert_rechecks_service_object_edit_after_early_resolution(self):
        original = mgmt._mutate_publication

        def edit_between_read_and_write(*args, **kwargs):
            v24.set_service_object(self.competing, "target", type="fixed-tcp",
                                   port=29772, oneshot=True)
            return original(*args, **kwargs)

        with mock.patch.object(mgmt, "_mutate_publication",
                               side_effect=edit_between_read_and_write):
            with self.assertRaises((ControlPlaneError, mgmt.MgmtSyncError)):
                self.publish(self.deleting)
        self.assertIsNone(self.deleting.conn.execute(
            "SELECT id FROM published_services WHERE name='racing-publication'"
        ).fetchone())
        obj = self.deleting.conn.execute(
            "SELECT port FROM service_objects WHERE name='target'"
        ).fetchone()
        self.assertIsNotNone(obj)
        self.assertEqual(int(obj["port"]), 29772)

    def test_delete_rechecks_publication_added_after_reference_preflight(self):
        # Emulate a signed Agent publication commit while a public destructive
        # delete is between its preflight/read and BEGIN IMMEDIATE write.
        original = self.deleting._mutate
        def publish_between_read_and_delete(*args, **kwargs):
            self.publish(self.competing)
            return original(*args, **kwargs)
        with mock.patch.object(self.deleting, "_mutate",
                               side_effect=publish_between_read_and_delete):
            with self.assertRaisesRegex(ControlPlaneError, "(?i)referenc"):
                v24.unset_service_object(self.deleting, "target", confirm=True)
        object_row = self.deleting.conn.execute(
            "SELECT id FROM service_objects WHERE name='target'"
        ).fetchone()
        self.assertIsNotNone(object_row)
        meta = self.deleting.conn.execute(
            "SELECT service_object_id FROM remote_service_meta"
        ).fetchone()
        self.assertIsNotNone(meta)
        self.assertEqual(meta["service_object_id"], object_row["id"])


if __name__ == "__main__":
    unittest.main()
