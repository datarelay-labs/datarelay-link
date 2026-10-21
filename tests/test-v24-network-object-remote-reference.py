#!/usr/bin/env python3
"""Network destination deletion must preserve live Relay publications."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
import drlink_mgmt_sync as mgmt
import drlink_v24 as v24
from drlink_v24_bundle import apply_v24_plan, prepare_v24_plan

OWNER = "aabbccddeeff00112233445566778899"


class NetworkRemoteReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-network-ref-")
        config = Path(self.tmp.name, "etc/drlink/config.json")
        config.parent.mkdir(parents=True)
        config.write_text('{"role":"server"}\n')
        self.env = mock.patch.dict(os.environ, {
            "FRP_DEPLOY_TEST_ROOT": self.tmp.name,
            "DRLINK_SKIP_ACTIVATION": "1",
            "DRLINK_CONFIRM": "yes",
        })
        self.env.start()
        self.plane = ControlPlane(self.tmp.name)
        self.other = ControlPlane(self.tmp.name)
        self.plane.upsert_client(OWNER, label="relay-agent", hostname="relay-agent")
        v24.set_network_object(self.plane, "lan-target", type="ip",
                               value="192.0.2.19", oneshot=True)
        v24.set_service_object(self.plane, "web", type="tcp", port=8080, oneshot=True)

    def tearDown(self):
        self.other.close()
        self.plane.close()
        self.env.stop()
        self.tmp.cleanup()

    def publish(self, plane=None, *, enabled=True):
        return mgmt.server_upsert_remote_service(
            plane or self.plane,
            mgmt.MgmtAuthContext(OWNER, {"id": OWNER}, "test-nonce", 1),
            {"name": "lan-web", "destination": "lan-target", "service": "web",
             "pool_class": "normal", "enabled": enabled,
             # Reference integrity does not need a host socket/port scan.
             "preserve_endpoint_port": 6010},
        )

    def test_live_and_disabled_publications_are_listed_and_block_delete(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                self.publish(enabled=enabled)
                before = self.plane.current_revision()
                refs = self.plane.object_references("LAN-TARGET")
                self.assertTrue(any(r["kind"] == "remote-service" and
                                    r["name"] == "lan-web" and
                                    "relay-agent" in r["display"] for r in refs), refs)
                with self.assertRaisesRegex(ControlPlaneError, "(?i)referenc"):
                    v24.unset_network_object(self.plane, "lan-target", confirm=True)
                self.assertEqual(self.plane.current_revision(), before)
                self.assertIsNotNone(self.plane.get_object("lan-target"))

    def test_internal_delete_also_protects_relay_destination(self):
        self.publish()
        with self.assertRaisesRegex(ControlPlaneError, "(?i)referenc"):
            self.plane.unset_object("lan-target", confirm=True)
        self.assertIsNotNone(self.plane.get_object("lan-target"))

    def test_delete_rechecks_publication_committed_after_preflight(self):
        original = self.plane._mutate

        def publish_then_delete(*args, **kwargs):
            self.publish(self.other)
            return original(*args, **kwargs)

        with mock.patch.object(self.plane, "_mutate", side_effect=publish_then_delete):
            with self.assertRaisesRegex(ControlPlaneError, "(?i)referenc"):
                self.plane.unset_object("lan-target", confirm=True)
        self.assertIsNotNone(self.plane.get_object("lan-target"))

    def test_released_publication_allows_destination_cleanup(self):
        self.publish()
        mgmt.server_delete_remote_service(
            self.plane, mgmt.MgmtAuthContext(OWNER, {"id": OWNER}, "test-nonce", 1),
            "lan-web",
        )
        self.assertFalse(self.plane.object_references("lan-target"))
        v24.unset_network_object(self.plane, "lan-target", confirm=True)
        self.assertIsNone(self.plane.get_object("lan-target"))

    def test_bundle_cannot_delete_a_live_relay_destination(self):
        self.publish()
        before = self.plane.current_revision()
        with self.assertRaisesRegex(ControlPlaneError, "(?i)referenc"):
            plan = prepare_v24_plan(self.plane, """configurationBundle:
  context: server
  networkObjects:
    - name: lan-target
      state: absent
""")
            apply_v24_plan(self.plane, plan, confirm=True)
        self.assertEqual(self.plane.current_revision(), before)
        self.assertIsNotNone(self.plane.get_object("lan-target"))


if __name__ == "__main__":
    unittest.main()
