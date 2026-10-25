#!/usr/bin/env python3
"""F008: Agent Bundle absence is desired state, not a repeated delete command."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane, ControlPlaneError
import drlink_v24 as v24
from drlink_v24_bundle import apply_v24_plan, prepare_v24_plan


ABSENT = """configurationBundle:
  context: agent
  remoteServices:
    - name: PUB1
      state: absent
"""


class AgentBundleAbsentIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-agent-absence-")
        self.root = self.tmp.name
        config = Path(self.root, "etc/frp")
        config.mkdir(parents=True)
        (config / "client-state.json").write_text(json.dumps({
            "machine_id": "aabbccddeeff00112233445566778899",
            "hostname": "agent-1", "label": "agent-1",
        }))
        (config / "frpc.toml").write_text("[common]\n")
        self.env = patch.dict(os.environ, {
            "FRP_DEPLOY_TEST_ROOT": self.root,
            "DRLINK_CONFIRM": "yes",
            "DRLINK_SKIP_ACTIVATION": "1",
            "DRLINK_SERVER_REACHABLE": "0",
        })
        self.env.start()
        self.plane = ControlPlane(self.root)
        v24.ensure_v2_schema(self.plane.conn)

    def tearDown(self):
        self.plane.close()
        self.env.stop()
        self.tmp.cleanup()

    def assert_absence_no_change(self):
        revision = self.plane.current_revision()
        plan = prepare_v24_plan(self.plane, ABSENT)
        self.assertTrue(plan.no_change)
        with patch.object(v24, "unset_remote_service_agent") as delete:
            self.assertEqual(apply_v24_plan(self.plane, plan)["status"], "NO_CHANGE")
            delete.assert_not_called()
        self.assertEqual(self.plane.current_revision(), revision)

    def test_already_missing_service_is_no_change_without_delete_or_rpc(self):
        self.assert_absence_no_change()

    def test_offline_delete_reapply_preserves_pending_server_deletion(self):
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_remote_service_agent(
            self.plane, "pub1", destination="this-host", service="ssh",
            enabled=False, oneshot=True, root=self.root, server_reachable=False,
        )
        plan = prepare_v24_plan(self.plane, ABSENT)
        self.assertFalse(plan.no_change)
        self.assertEqual(apply_v24_plan(self.plane, plan)["status"], "APPLIED")
        before = dict(self.plane.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name='pub1' COLLATE NOCASE"
        ).fetchone())
        self.assertEqual(before["delete_pending"], 1)
        self.assert_absence_no_change()
        after = dict(self.plane.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name='pub1' COLLATE NOCASE"
        ).fetchone())
        self.assertEqual(before, after)

    def test_direct_delete_still_rejects_an_unknown_service(self):
        with self.assertRaisesRegex(ControlPlaneError, "not found"):
            v24.unset_remote_service_agent(
                self.plane, "unknown", root=self.root, server_reachable=False,
            )


if __name__ == "__main__":
    unittest.main()
