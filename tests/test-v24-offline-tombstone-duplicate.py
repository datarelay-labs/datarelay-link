#!/usr/bin/env python3
"""Offline Remote Service tombstones must not block new desired-state mappings.

Reproduces the authentic CLI-only O-005/S-012 failure on installed 4d: offline
delete leaves an Agent tombstone; changing a second Remote Service to the same
Destination+Service is falsely rejected as an active duplicate.
"""
from __future__ import annotations

import json
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


class OfflineTombstoneDuplicate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-offline-tombstone-")
        root = Path(self.tmp.name)
        etc = root / "etc/frp"
        etc.mkdir(parents=True, exist_ok=True)
        (etc / "client-state.json").write_text(
            json.dumps({
                "machine_id": "107107107107107107107107107107aa",
                "hostname": "test-agent-107",
                "label": "test-agent-107",
            }) + "\n", encoding="utf-8",
        )
        (etc / "frpc.toml").write_text("[common]\n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {
            "FRP_DEPLOY_TEST_ROOT": self.tmp.name,
            "DRLINK_SERVER_REACHABLE": "0",
            "DRLINK_MGMT_MODE": "offline",
            "DRLINK_SKIP_ACTIVATION": "1",
            "DRLINK_CONFIRM": "yes",
        })
        self.env.start()
        self.plane = ControlPlane(self.tmp.name)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_service_object(
            self.plane, "local-ssh", type="tcp", port=22, oneshot=True
        )
        v24.set_service_object(
            self.plane, "local-https", type="tcp", port=443, oneshot=True
        )

    def tearDown(self):
        self.plane.close()
        self.env.stop()
        self.tmp.cleanup()

    def set_offline(self, name: str, *, destination: str, service: str):
        return v24.set_remote_service_agent(
            self.plane,
            name,
            destination=destination,
            service=service,
            enabled=True,
            oneshot=True,
            root=self.tmp.name,
            server_reachable=False,
        )

    def tombstone(self, name: str):
        v24.unset_remote_service_agent(
            self.plane, name, root=self.tmp.name, server_reachable=False
        )
        row = self.plane.conn.execute(
            "SELECT delete_pending, endpoint_port, service_object FROM "
            "agent_remote_services WHERE name=?", (name,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(int(row["delete_pending"]), 1)
        self.assertIsNone(row["endpoint_port"])
        return row

    def test_deleted_self_tombstone_does_not_block_second_service_edit(self):
        self.set_offline("old", destination="this-host", service="local-ssh")
        self.set_offline("old", destination="this-host", service="local-https")
        self.tombstone("old")
        self.set_offline("new", destination="this-host", service="local-ssh")

        # Before fix: rejected as duplicate of the delete-pending "old" row.
        updated = self.set_offline(
            "new", destination="this-host", service="local-https"
        )
        self.assertEqual(updated["view"]["status"], "DEGRADED")
        self.assertEqual(updated["view"]["endpoint"], "Pending allocation")
        rows = {
            row["name"]: row
            for row in self.plane.conn.execute(
                "SELECT name,service_object,delete_pending FROM agent_remote_services"
            )
        }
        self.assertEqual(int(rows["old"]["delete_pending"]), 1)
        self.assertEqual(int(rows["new"]["delete_pending"]), 0)
        self.assertEqual(rows["new"]["service_object"], "local-https")

        # An ACTUAL active desired service must still reject a duplicate.
        with self.assertRaisesRegex(ControlPlaneError, "(?i)already exists"):
            self.set_offline(
                "another", destination="this-host", service="local-https"
            )

    def test_deleted_routed_tombstone_does_not_block_new_mapping(self):
        address = "192.0.2.45"
        self.set_offline("old-route", destination=address, service="local-ssh")
        self.tombstone("old-route")
        candidate = self.set_offline(
            "new-route", destination=address, service="local-ssh"
        )
        self.assertEqual(candidate["view"]["status"], "DEGRADED")
        self.assertEqual(candidate["view"]["endpoint"], "Pending allocation")
        with self.assertRaisesRegex(ControlPlaneError, "(?i)already exists"):
            self.set_offline(
                "third-route", destination=address, service="local-ssh"
            )


if __name__ == "__main__":
    unittest.main()
