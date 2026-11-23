#!/usr/bin/env python3
"""A lost-then-restored Server heartbeat is a reconnect: the Agent must fully synchronize.

The Server only asks for reconciliation when the Agent heartbeat was stale for
more than AGENT_HEARTBEAT_SECONDS. A shorter outage during which an operator
changed the Server catalog (for example a Service Object port) therefore never
reached the Agent until a manual `drlink system synchronize`. The Agent itself
knows its heartbeat failed, so the first successful heartbeat afterwards must
run the normal full reconciliation (docs: DRLink synchronizes after reconnect).
"""
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_agent_lifecycle as lifecycle  # noqa: E402
import drlink_control_plane as cp  # noqa: E402
import drlink_v24 as v24  # noqa: E402


class AgentLifecycleReconnectSync(unittest.TestCase):
    def setUp(self):
        importlib.reload(lifecycle)  # fresh in-process reconnect tracking
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-reconnect-sync-")
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def run_cycles(self, heartbeats, sync_results=None):
        """Run one reconcile per heartbeat outcome; return the sync mock."""
        sync_results = sync_results or [{"status": "SYNCHRONIZED"}] * len(heartbeats)
        with mock.patch.object(lifecycle, "load_lifecycle_intent", return_value="running"), \
                mock.patch.object(lifecycle, "heartbeat_once", side_effect=heartbeats), \
                mock.patch.object(lifecycle, "reconciliation_needed", return_value=False), \
                mock.patch.object(lifecycle, "local_verification_retry_needed", return_value=False), \
                mock.patch.object(lifecycle, "current_runtime_verification_lost", return_value=False), \
                mock.patch.object(cp, "ControlPlane") as plane, \
                mock.patch.object(v24, "ensure_v2_schema"), \
                mock.patch.object(v24, "synchronize_agent_remote_services",
                                  side_effect=sync_results) as sync:
            self.plane = plane
            for outcome in heartbeats:
                try:
                    lifecycle.reconcile_once(self.root)
                except OSError:
                    self.assertIsInstance(outcome, OSError)
            return sync

    def full_call(self):
        return mock.call(self.plane.return_value, root=self.root, force_runtime=False)

    def test_first_heartbeat_after_failure_runs_full_synchronization(self):
        sync = self.run_cycles([OSError("Server unreachable"), {"reconcile_required": False}])
        self.assertEqual(sync.call_args_list, [self.full_call()])

    def test_reconnect_synchronization_happens_once(self):
        sync = self.run_cycles([OSError("down"), {"reconcile_required": False},
                                {"reconcile_required": False}])
        self.assertEqual(sync.call_args_list, [self.full_call()])

    def test_steady_heartbeats_never_synchronize(self):
        sync = self.run_cycles([{"reconcile_required": False}] * 3)
        sync.assert_not_called()

    def test_synchronization_is_retried_until_the_server_is_reachable(self):
        sync = self.run_cycles(
            [OSError("down"), {"reconcile_required": False}, {"reconcile_required": False},
             {"reconcile_required": False}],
            [{"status": "OFFLINE"}, {"status": "SYNCHRONIZED"}])
        self.assertEqual(sync.call_args_list, [self.full_call(), self.full_call()])

    def test_server_verification_request_stays_verification_only(self):
        sync = self.run_cycles([{"reconcile_required": True}])
        sync.assert_called_once_with(self.plane.return_value, root=self.root,
                                     force_runtime=False, server_verification_only=True)


if __name__ == "__main__":
    unittest.main()
