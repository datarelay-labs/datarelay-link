#!/usr/bin/env python3
"""Agent previews stay local; apply uses synchronization-before-SQLite order."""
import contextlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from drlink_control_plane import ControlPlane, ControlPlaneError
import drlink_v24 as v24
from drlink_v24_bundle import apply_v24_plan, prepare_v24_plan

RAW = """configurationBundle:
  context: agent
  remoteServices:
    - name: lock-proof
      destination: this-host
      service: ssh
      enabled: true
"""


class AgentBundleSynchronizationLock(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.environment = mock.patch.dict(os.environ, {"FRP_DEPLOY_TEST_ROOT": self.root})
        self.environment.start()
        self.plane = ControlPlane(self.root)
        folder = Path(self.root, "etc/frp")
        folder.mkdir(parents=True, exist_ok=True)
        folder.joinpath("client-state.json").write_text(
            '{"machine_id":"aabbccddeeff00112233445566778899","hostname":"agent-1"}\n'
        )
        folder.joinpath("frpc.toml").write_text("[common]\n")
        folder.joinpath("client-identity.key").write_text("unit-test-identity\n")

    def tearDown(self):
        self.plane.close()
        self.environment.stop()
        self.temp.cleanup()

    def test_preview_never_takes_live_synchronization_lock(self):
        before = self.plane.current_revision()
        for readonly in (False, True):
            plane = ControlPlane(self.root, read_only=True) if readonly else self.plane
            try:
                with mock.patch("frp_control_locks.ExclusiveFileLock", side_effect=AssertionError("preview touched live lock")):
                    plan = prepare_v24_plan(plane, RAW)
                self.assertFalse(plan.no_change)
                self.assertEqual(self.plane.current_revision(), before)
                self.assertIsNone(self.plane.conn.execute(
                    "SELECT name FROM agent_remote_services WHERE name='lock-proof'"
                ).fetchone())
            finally:
                if readonly:
                    plane.close()

    def test_apply_takes_sync_lock_before_database_write_transaction(self):
        plan = prepare_v24_plan(self.plane, RAW)
        entered = []

        @contextlib.contextmanager
        def lock(*args, **kwargs):
            self.assertFalse(self.plane.conn.in_transaction)
            entered.append(True)
            yield

        with mock.patch("frp_control_locks.ExclusiveFileLock", side_effect=lock), \
                mock.patch.object(v24, "detect_server_reachable", return_value=False), \
                mock.patch("drlink_v24_bundle._finalize_agent_bundle_runtime"):
            result = apply_v24_plan(self.plane, plan, confirm=True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(len(entered), 1)
        self.assertFalse(v24._agent_synchronize_lock_held())
        self.assertFalse(self.plane.conn.in_transaction)

    def test_ordinary_offline_mutation_still_requires_sync_lock(self):
        with mock.patch("frp_control_locks.ExclusiveFileLock") as lock, \
                mock.patch("drlink_v24_runtime.apply_agent_runtime", return_value={"ok": True}), \
                mock.patch.object(v24, "_push_agent_remote_service_status"):
            v24.set_remote_service_agent(self.plane, "ordinary", destination="this-host",
                                        service="ssh", enabled=True, oneshot=True,
                                        root=self.root, server_reachable=False)
        self.assertEqual(lock.call_count, 1)
        self.assertFalse(v24._agent_synchronize_lock_held())

    def test_local_validation_exemption_rejects_operational_calls(self):
        for reachable in (False, True):
            with self.assertRaisesRegex(ControlPlaneError, "offline batch transaction"):
                v24.set_remote_service_agent(self.plane, "unsafe", destination="this-host",
                                            service="ssh", enabled=True, oneshot=True,
                                            root=self.root, server_reachable=reachable,
                                            _local_validation=True)


if __name__ == "__main__":
    unittest.main()
