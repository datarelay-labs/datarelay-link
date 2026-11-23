#!/usr/bin/env python3
"""An orphan Remote Service after `system restore` must not churn the Server DB revision.

S-025-F1 (HEAD 38038b98): `drlink system restore` rolls the Server back to a backup
taken before an Agent-owned Remote Service was created. The Agent keeps that row
(its Service Object is gone from the restored catalog), so it is an *orphan*. The
Agent never deletes it and never silently retargets it: it stays DEGRADED and
fail-closed with the dependency reason.

Before the fix, every lifecycle heartbeat saw `_service_dependency_status()` return
a reason for the orphan, fell through the status-only path into a full
reconciliation, rewrote the orphan row (fresh updated_at) and re-applied every
sibling Remote Service through POST /v1/remote-services. The Server records a new
revision for each such POST, so the DB revision climbed ~2 per minute although
nothing changed.

Contract after the fix:
  * an orphan that is already recorded DEGRADED/unverified with the dependency
    reason is a STABLE state: the heartbeat stays status-only, claims only the
    siblings, never touches the orphan row and never replays siblings;
  * a NEW orphan (not yet recorded) and a RECOVERED orphan (Service Object is back
    but the row still carries the orphan reason) still fall through to the full,
    guarded reconciliation exactly once;
  * the full reconciliation writes a dependency-degraded row idempotently.
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

ORPHAN_SERVICE = "r25-post"
ORPHAN_NAME = "r25-post-rs"
ORPHAN_REASON = "Required Service Object '%s' is missing or invalid after reconnect." % ORPHAN_SERVICE
STALE_STAMP = "2026-11-20T00:00:00Z"

SCHEMA = (
    "CREATE TABLE agent_remote_services (name TEXT, service_object TEXT, destination TEXT,"
    " destination_client_id TEXT, enabled INTEGER, status TEXT, reason TEXT,"
    " runtime_verified INTEGER, endpoint_port INTEGER, pending_allocation INTEGER,"
    " delete_pending INTEGER, enrollment_seed INTEGER, updated_at TEXT);"
)


class FellThroughToFullReconcile(Exception):
    pass


def new_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_row(conn, name, service, status, verified, reason="", port=6001):
    conn.execute(
        "INSERT INTO agent_remote_services VALUES (?,?,'this-host','',1,?,?,?,?,0,0,0,?)",
        (name, service, status, reason, verified, port, STALE_STAMP),
    )


def make_plane(*, orphan=True, orphan_status="DEGRADED", orphan_verified=0,
               orphan_reason=ORPHAN_REASON, sibling=True, conn=None):
    conn = conn or new_conn()
    if sibling:
        add_row(conn, "r25-echo-rs", "r25-echo", "HEALTHY", 1, "", 6001)
    if orphan:
        add_row(conn, ORPHAN_NAME, ORPHAN_SERVICE, orphan_status, orphan_verified,
                orphan_reason, 6003)
    return SimpleNamespace(conn=conn, root="/tmp/none", _batch_mode=False)


def clone_plane(plane):
    """A process restart / backup re-restore: same persisted rows, nothing in memory."""
    plane.conn.commit()  # a backup of an open write transaction never completes
    conn = new_conn()
    plane.conn.backup(conn)
    return SimpleNamespace(conn=conn, root="/tmp/none", _batch_mode=False)


def snapshot(plane):
    return [tuple(row) for row in plane.conn.execute(
        "SELECT * FROM agent_remote_services ORDER BY name")]


class HeartbeatHarness(unittest.TestCase):
    missing_services = {ORPHAN_SERVICE}

    def service_status(self, plane_db, svc_name):
        return ORPHAN_REASON if svc_name in self.missing_services else None

    def heartbeat(self, plane, *, missing=None):
        """One signed status-only heartbeat. Returns (fell_through, claims, result)."""
        if missing is not None:
            self.missing_services = set(missing)
        reports = []

        def ack(root=None, services=None):
            reports.append(list(services or []))
            return {"services": [dict(c, pending_allocation=0) for c in services or []]}

        report = mock.Mock(side_effect=ack)
        patches = [
            mock.patch.object(v24, "project_enrolled_services_into_agent_catalog", return_value=[]),
            mock.patch.object(v24, "repair_enrolled_lan_seed_destinations", return_value=[]),
            mock.patch.object(v24, "_bootstrap_seed_names", return_value=set()),
            mock.patch.object(v24, "detect_server_reachable", return_value=True),
            mock.patch.object(v24, "sync_agent_catalog_from_server"),
            mock.patch.object(v24, "_destination_dependency_status", return_value=None),
            mock.patch.object(v24, "_service_dependency_status", side_effect=self.service_status),
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True),
            mock.patch.object(mgmt, "report_remote_service_status_on_server", report),
            mock.patch.object(runtime, "verified_remote_service_status",
                              return_value=("HEALTHY", "")),
            mock.patch.object(runtime, "desired_runtime_drift", return_value=False, create=True),
            mock.patch.object(v24, "_reconcile_agent_from_server_status"),
            mock.patch.object(v24, "_demote_agent_runtime_for_reverification",
                              side_effect=FellThroughToFullReconcile),
        ]
        for p in patches:
            p.start()
        try:
            try:
                result = v24.synchronize_agent_remote_services(
                    plane, root="/tmp/none", force_runtime=False,
                    server_verification_only=True)
            except FellThroughToFullReconcile:
                return True, (reports[-1] if reports else None), None
            return False, (reports[-1] if reports else None), result
        finally:
            for p in patches:
                p.stop()


class OrphanAfterRestoreStaysStatusOnly(HeartbeatHarness):
    def test_orphan_with_healthy_sibling_does_not_fall_through(self):
        plane = make_plane()
        before = snapshot(plane)
        fell, claims, result = self.heartbeat(plane)
        self.assertFalse(fell, "recorded orphan must not force a full reconcile (revision churn)")
        self.assertEqual(snapshot(plane), before, "orphan row (incl. updated_at) must not be rewritten")
        self.assertEqual([c["name"] for c in claims], ["r25-echo-rs"],
                         "the Server has no Service Object for the orphan: never claim it")
        self.assertEqual(result["status"], "DEGRADED")
        self.assertTrue(result.get("no_change"))
        self.assertEqual([(a["name"], a["reason"]) for a in result["affected"]],
                         [(ORPHAN_NAME, ORPHAN_REASON)])

    def test_orphan_is_kept_fail_closed_and_not_deleted(self):
        plane = make_plane()
        self.heartbeat(plane)
        row = plane.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name=?", (ORPHAN_NAME,)).fetchone()
        self.assertIsNotNone(row, "orphan reservation must never be deleted")
        self.assertEqual((row["status"], row["runtime_verified"], row["reason"]),
                         ("DEGRADED", 0, ORPHAN_REASON))
        self.assertEqual(row["endpoint_port"], 6003, "the reserved endpoint is preserved")

    def test_repeated_heartbeats_never_fall_through_or_touch_rows(self):
        plane = make_plane()
        before = snapshot(plane)
        for cycle in range(6):
            fell, claims, _ = self.heartbeat(plane)
            self.assertFalse(fell, "heartbeat %d fell through to full reconcile" % cycle)
            self.assertEqual([c["name"] for c in claims], ["r25-echo-rs"])
        self.assertEqual(snapshot(plane), before)

    def test_only_orphans_present_stays_status_only(self):
        plane = make_plane(sibling=False)
        before = snapshot(plane)
        fell, _claims, result = self.heartbeat(plane)
        self.assertFalse(fell)
        self.assertEqual(snapshot(plane), before)
        self.assertEqual(result["status"], "DEGRADED")

    def test_restart_and_backup_rerestore_keep_the_same_classification(self):
        plane = make_plane()
        self.assertFalse(self.heartbeat(plane)[0])
        restarted = clone_plane(plane)           # process restart: only persisted rows survive
        before = snapshot(restarted)
        self.assertFalse(self.heartbeat(restarted)[0])
        rerestored = clone_plane(restarted)      # backup, then restore of that backup again
        self.assertFalse(self.heartbeat(rerestored)[0])
        self.assertEqual(snapshot(rerestored), before)


class OrphanTransitionsStillReconcile(HeartbeatHarness):
    def test_new_orphan_not_yet_recorded_falls_through_once(self):
        # The row still claims HEALTHY/verified but its Service Object just vanished.
        plane = make_plane(orphan_status="HEALTHY", orphan_verified=1, orphan_reason="")
        fell, _claims, _ = self.heartbeat(plane)
        self.assertTrue(fell, "a newly missing dependency must be demoted by full reconcile")

    def test_orphan_with_different_stored_reason_falls_through(self):
        plane = make_plane(orphan_reason="Some older reason.")
        fell, _claims, _ = self.heartbeat(plane)
        self.assertTrue(fell, "the recorded reason must match before the state is stable")

    def test_recovered_orphan_falls_through_to_reapply(self):
        # The restored Server catalog regained the Service Object: the stale orphan
        # reason must be cleared by the guarded full reconciliation, not kept forever.
        plane = make_plane()
        fell, _claims, _ = self.heartbeat(plane, missing=set())
        self.assertTrue(fell, "a recovered dependency must trigger one full reconcile")

    def test_disabled_row_with_unrecorded_missing_dependency_falls_through(self):
        # Existing fail-closed behaviour is preserved: a DISABLED row whose Service
        # Object vanished is demoted once by the guarded full reconciliation.
        plane = make_plane()
        plane.conn.execute(
            "UPDATE agent_remote_services SET enabled=0, status='DISABLED', reason='' "
            "WHERE name=?", (ORPHAN_NAME,))
        fell, _claims, _ = self.heartbeat(plane)
        self.assertTrue(fell)

    def test_disabled_orphan_already_recorded_degraded_is_stable(self):
        # That one full reconciliation leaves enabled=0/DEGRADED/orphan-reason, which
        # must not be re-triggered on every heartbeat either.
        plane = make_plane()
        plane.conn.execute("UPDATE agent_remote_services SET enabled=0 WHERE name=?",
                           (ORPHAN_NAME,))
        before = snapshot(plane)
        fell, claims, _ = self.heartbeat(plane)
        self.assertFalse(fell)
        self.assertEqual(snapshot(plane), before)
        self.assertEqual([c["name"] for c in claims], ["r25-echo-rs"])


class DependencyDegradeWriteIsIdempotent(unittest.TestCase):
    def test_identical_degrade_does_not_rewrite_updated_at(self):
        plane = make_plane()
        row = plane.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name=?", (ORPHAN_NAME,)).fetchone()
        changed = v24._mark_dependency_degraded(plane, row, ORPHAN_REASON)
        self.assertFalse(changed)
        after = plane.conn.execute(
            "SELECT updated_at FROM agent_remote_services WHERE name=?", (ORPHAN_NAME,)).fetchone()
        self.assertEqual(after["updated_at"], STALE_STAMP)

    def test_new_degrade_is_written(self):
        plane = make_plane(orphan_status="HEALTHY", orphan_verified=1, orphan_reason="")
        row = plane.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name=?", (ORPHAN_NAME,)).fetchone()
        self.assertTrue(v24._mark_dependency_degraded(plane, row, ORPHAN_REASON))
        after = plane.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name=?", (ORPHAN_NAME,)).fetchone()
        self.assertEqual((after["status"], after["runtime_verified"], after["reason"]),
                         ("DEGRADED", 0, ORPHAN_REASON))
        self.assertNotEqual(after["updated_at"], STALE_STAMP)


if __name__ == "__main__":
    unittest.main()
