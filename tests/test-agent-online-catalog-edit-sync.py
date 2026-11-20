#!/usr/bin/env python3
"""An online Service Object edit must reach the Agent runtime without a manual synchronize.

S-011b/S-011c (HEAD b6a8500c): after the Server catalog changed a Service Object port
while the Agent stayed connected, the signed status-only verification path kept
re-verifying the *installed* (stale) target and never compared it with the desired
runtime. A DEGRADED/unreachable service stayed DEGRADED (frpc keeps the old
localPort) and a HEALTHY service turned DEGRADED "Runtime proxy is not present in
the verified generation." forever; only `drlink system synchronize` recovered both.

Drift between the desired runtime and the installed record must fall through to the
normal full reconciliation (with its concurrency and rollback guards). Plain
transport loss and an unchanged unreachable target must stay on the status-only path
so healthy sibling proxies are never replayed.
"""
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_mgmt_sync as mgmt  # noqa: E402
import drlink_v24 as v24  # noqa: E402
import drlink_v24_runtime as runtime  # noqa: E402


class FellThroughToFullReconcile(Exception):
    pass


def make_plane(status, runtime_verified, reason=""):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE agent_remote_services (name TEXT, service_object TEXT, destination TEXT,"
        " destination_client_id TEXT, enabled INTEGER, status TEXT, reason TEXT,"
        " runtime_verified INTEGER, endpoint_port INTEGER, pending_allocation INTEGER,"
        " delete_pending INTEGER, enrollment_seed INTEGER, updated_at TEXT);"
    )
    conn.execute(
        "INSERT INTO agent_remote_services VALUES ('svc-rs','svc','this-host','',1,?,?,?,6001,0,0,0,'')",
        (status, reason, runtime_verified),
    )
    return SimpleNamespace(conn=conn, root="/tmp/none", _batch_mode=False)


class OnlineCatalogEditSync(unittest.TestCase):
    def status_only(self, plane, live, drift):
        """Run the status-only path; return (fell_through, report_called)."""
        def ack(root=None, services=None):
            # The authenticated Server confirms every claim unchanged.
            return {"services": [dict(claim, pending_allocation=0) for claim in services or []]}

        report = mock.Mock(side_effect=ack)
        patches = [
            mock.patch.object(v24, "project_enrolled_services_into_agent_catalog", return_value=[]),
            mock.patch.object(v24, "repair_enrolled_lan_seed_destinations", return_value=[]),
            mock.patch.object(v24, "_bootstrap_seed_names", return_value=set()),
            mock.patch.object(v24, "detect_server_reachable", return_value=True),
            mock.patch.object(v24, "sync_agent_catalog_from_server"),
            mock.patch.object(v24, "_destination_dependency_status", return_value=None),
            mock.patch.object(v24, "_service_dependency_status", return_value=None),
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True),
            mock.patch.object(mgmt, "report_remote_service_status_on_server", report),
            mock.patch.object(runtime, "verified_remote_service_status", return_value=live),
            mock.patch.object(runtime, "desired_runtime_drift", return_value=drift, create=True),
            mock.patch.object(v24, "_reconcile_agent_from_server_status"),
            mock.patch.object(v24, "_demote_agent_runtime_for_reverification",
                              side_effect=FellThroughToFullReconcile),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        try:
            v24.synchronize_agent_remote_services(
                plane, root="/tmp/none", force_runtime=False, server_verification_only=True)
        except FellThroughToFullReconcile:
            return True, report.called
        except Exception:
            # Any other error is a different failure than the one under test.
            raise
        return False, report.called

    UNREACHABLE = ("DEGRADED", "Destination is currently unreachable from Relay Host.")
    MISSING = ("DEGRADED", "Runtime proxy is not present in the verified generation.")

    def test_degraded_unreachable_with_edited_target_falls_through(self):
        # S-011b/S-011c s11c: stale installed target 18999 unreachable, desired 18080.
        plane = make_plane("DEGRADED", 0, "Destination is currently unreachable from Relay Host.")
        fell, reported = self.status_only(plane, self.UNREACHABLE, drift=True)
        self.assertTrue(fell, "edited target must trigger full reconciliation")
        self.assertFalse(reported, "no stale DEGRADED claim may be reported for a drifted service")

    def test_healthy_service_with_edited_target_falls_through(self):
        # S-011c s11e: HEALTHY service whose desired target changed online.
        plane = make_plane("HEALTHY", 1)
        fell, reported = self.status_only(plane, self.MISSING, drift=True)
        self.assertTrue(fell)
        self.assertFalse(reported)

    def test_unchanged_unreachable_target_stays_status_only(self):
        # Same target still down: replaying every Remote Service cannot help.
        plane = make_plane("DEGRADED", 0, "Destination is currently unreachable from Relay Host.")
        fell, reported = self.status_only(plane, self.UNREACHABLE, drift=False)
        self.assertFalse(fell)
        self.assertTrue(reported)

    def test_transport_loss_without_drift_stays_status_only(self):
        # Management presence survives loss of the FRP transport: report, do not replay.
        plane = make_plane("HEALTHY", 1)
        fell, reported = self.status_only(plane, self.MISSING, drift=False)
        self.assertFalse(fell)
        self.assertTrue(reported)


class DesiredRuntimeDriftHelper(unittest.TestCase):
    def drift(self, record, desired, row_enabled=True):
        plane = make_plane("HEALTHY", 1)
        plane.conn.execute("UPDATE agent_remote_services SET enabled=?", (1 if row_enabled else 0,))
        with mock.patch.object(runtime, "load_client_state",
                               return_value={"services": {runtime.remote_service_proxy_id("svc-rs"): record}
                                             if record is not None else {}}), \
                mock.patch.object(runtime, "build_desired_runtime_services",
                                  return_value={runtime.remote_service_proxy_id("svc-rs"): desired}
                                  if desired is not None else {}):
            return runtime.desired_runtime_drift(plane, "svc-rs", root="/tmp/none")

    def test_equal_record_and_desired_is_not_drift(self):
        rec = {"local_ip": "127.0.0.1", "local_port": 18080, "remote_port": 6001}
        self.assertFalse(self.drift(dict(rec), dict(rec)))

    def test_changed_local_port_is_drift(self):
        old = {"local_ip": "127.0.0.1", "local_port": 18999, "remote_port": 6001}
        new = {"local_ip": "127.0.0.1", "local_port": 18080, "remote_port": 6001}
        self.assertTrue(self.drift(old, new))

    def test_missing_record_or_desired_is_not_drift(self):
        rec = {"local_ip": "127.0.0.1", "local_port": 18080, "remote_port": 6001}
        self.assertFalse(self.drift(None, rec))
        self.assertFalse(self.drift(rec, None))

    def test_disabled_service_is_not_drift(self):
        old = {"local_ip": "127.0.0.1", "local_port": 18999, "remote_port": 6001}
        new = {"local_ip": "127.0.0.1", "local_port": 18080, "remote_port": 6001}
        self.assertFalse(self.drift(old, new, row_enabled=False))


if __name__ == "__main__":
    unittest.main()
