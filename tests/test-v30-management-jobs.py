#!/usr/bin/env python3
from __future__ import annotations

import io
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError, open_control_db
import drlink_control_cli as control_cli
from drlink_management_service import ManagementQueryService
from drlink_v30_jobs import (
    BoundedAgentRpcWorkerPool,
    ADMITTED_JOB_TYPES,
    MUTATING_AGENT_JOB_TYPES,
    READ_ONLY_AGENT_JOB_TYPES,
    CANCELLED,
    FAILED,
    ManagementJobEngine,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    job_operational_summary,
)


class V30ManagementJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-jobs-")
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.engine = ManagementJobEngine(
            self.tmp, max_active_jobs=8, max_targets=8, lease_seconds=5
        )

    def tearDown(self):
        self.engine.close()

    def _enqueue(self, targets=("host-a",), **kwargs):
        return self.engine.enqueue(
            job_type=kwargs.pop("job_type", "doctor"),
            targets=targets,
            requested_by=kwargs.pop("requested_by", "operator-a"),
            now=kwargs.pop("now", self.now),
            **kwargs,
        )

    def test_schema_is_separate_from_ai_jobs(self):
        tables = {
            row[0]
            for row in self.engine.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("management_jobs", tables)
        self.assertIn("management_job_targets", tables)
        self.assertIn("ai_jobs", tables)
        job = self._enqueue()
        self.assertTrue(job["id"].startswith("mjob_"))
        ai_count = self.engine.conn.execute("SELECT COUNT(*) FROM ai_jobs").fetchone()[0]
        self.assertEqual(ai_count, 0)

    def test_engine_rejects_invalid_queue_configuration_before_db_open(self):
        from drlink_v30_jobs import MAX_ACTIVE_JOBS

        cases = (
            ("max_active_jobs", 0), ("max_active_jobs", -1),
            ("max_active_jobs", True), ("max_active_jobs", 1.5),
            ("max_active_jobs", "8"),
            ("max_active_jobs", MAX_ACTIVE_JOBS + 1),
            ("max_targets", 0), ("max_targets", -1),
            ("max_targets", False), ("max_targets", 2.5),
            ("max_targets", "8"),
            ("lease_seconds", 0), ("lease_seconds", -3),
            ("lease_seconds", True), ("lease_seconds", 30.5),
            ("lease_seconds", "60"),
        )
        for field, invalid in cases:
            with self.subTest(field=field, value=repr(invalid)):
                fresh = Path(tempfile.mkdtemp(prefix="drlink-job-invalid-"))
                with self.assertRaises(ControlPlaneError):
                    with ManagementJobEngine(str(fresh), **{field: invalid}):
                        pass
                self.assertEqual(list(fresh.rglob("*")), [])

    def test_existing_schema_v3_additively_gains_job_tables(self):
        legacy_root = tempfile.mkdtemp(prefix="drlink-v30-existing-schema-")
        conn = open_control_db(legacy_root)
        conn.execute("DROP TABLE management_job_targets")
        conn.execute("DROP TABLE management_jobs")
        self.assertEqual(
            conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 3
        )
        conn.close()

        upgraded = ManagementJobEngine(legacy_root)
        try:
            tables = {
                row[0]
                for row in upgraded.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertIn("management_jobs", tables)
            self.assertIn("management_job_targets", tables)
        finally:
            upgraded.close()

    def test_new_job_families_do_not_inherit_observational_admission(self):
        self.assertEqual(READ_ONLY_AGENT_JOB_TYPES, {"doctor", "version-check"})
        self.assertEqual(
            MUTATING_AGENT_JOB_TYPES, ADMITTED_JOB_TYPES - READ_ONLY_AGENT_JOB_TYPES
        )
        self.assertIn("support-bundle", MUTATING_AGENT_JOB_TYPES)
        self.assertIn("refresh", MUTATING_AGENT_JOB_TYPES)
        self.assertNotIn("doctor", MUTATING_AGENT_JOB_TYPES)

    def test_only_admitted_safe_job_families_can_start(self):
        with self.assertRaises(ControlPlaneError):
            self._enqueue(job_type="bulk-delete")
        with self.assertRaises(ControlPlaneError):
            self._enqueue(job_type="restart-everything")

    def test_managed_update_rollout_is_bounded_and_artifact_pinned(self):
        from drlink_control_plane import ControlPlane
        plane = ControlPlane(self.tmp)
        try:
            for host in ("host-a","host-b","host-c"):
                plane.upsert_client(host, hostname=host)
        finally:
            plane.close()
        digest = "a" * 64
        job = self.engine.enqueue_rollout(
            targets=("host-a", "host-b", "host-c"),
            canary_targets=("host-a",),
            requested_by="admin-a",
            artifact={"version": "3.0.0-rc.1", "source_ref": "a" * 40, "sha256": digest},
            wave_size=2,
            failure_threshold_percent=25,
            now=self.now,
        )
        self.assertEqual(job["job_type"], "agent-update-rollout")
        self.assertEqual(job["payload"]["rollout_state"], "CANARY")
        self.assertEqual(job["payload"]["canary_targets"], ["host-a"])
        self.assertEqual(job["payload"]["artifact"]["sha256"], digest)
        paused = self.engine.rollout_control(job["id"], action="pause")
        self.assertTrue(paused["payload"]["operator_paused"])
        self.assertEqual(paused["payload"]["rollout_state"], "PAUSED")
        resumed = self.engine.rollout_control(job["id"], action="resume")
        self.assertFalse(resumed["payload"]["operator_paused"])

    def test_generic_job_api_cannot_bypass_rollout_artifact_and_canary_validation(self):
        with self.assertRaisesRegex(ControlPlaneError, "Rollout"):
            self.engine.enqueue(
                job_type="agent-update-rollout", targets=("host-a",),
                requested_by="admin-a",
                payload={"artifact": {"source_ref": "main", "sha256": "not-verified"}},
                now=self.now,
            )
        self.assertEqual(
            self.engine.conn.execute("SELECT COUNT(*) FROM management_jobs").fetchone()[0],
            0,
        )

    def test_managed_update_rollout_rejects_unsafe_scope(self):
        artifact = {"version": "3.0.0", "source_ref": "b" * 40, "sha256": "c" * 64}
        with self.assertRaises(ControlPlaneError):
            self.engine.enqueue_rollout(
                targets=("host-a",),
                canary_targets=("host-b",),
                requested_by="admin-a",
                artifact=artifact,
                now=self.now,
            )
        with self.assertRaises(ControlPlaneError):
            self.engine.enqueue_rollout(
                targets=("host-a",),
                requested_by="admin-a",
                artifact={"version": "3.0.0", "source_ref": "mutable-main", "sha256": "bad"},
                now=self.now,
            )

    def test_admission_blocks_mutating_agent_jobs_without_blocking_diagnostics(self):
        from drlink_control_plane import ControlPlane

        plane = ControlPlane(self.tmp)
        try:
            for host, admission in (
                ("pending-host", "PENDING_APPROVAL"),
                ("quarantined-host", "QUARANTINED"),
                ("approved-host", "APPROVED"),
            ):
                plane.upsert_client(host, hostname=host)
                plane.conn.execute(
                    "UPDATE clients SET admission_state=? WHERE id=?",
                    (admission, host),
                )
            plane.conn.commit()
        finally:
            plane.close()

        self.engine.max_active_jobs = 16  # This test deliberately covers 14 targets.
        mutating_kinds = (
            "refresh", "support-bundle", "remote-service-set", "remote-service-delete",
        )
        for target in ("pending-host", "quarantined-host", "approved-host"):
            for kind in mutating_kinds:
                self._enqueue(
                    targets=(target,), job_type=kind, now=self.now,
                    payload={"name": "ssh-access"},
                )
            if target != "approved-host":
                self._enqueue(targets=(target,), job_type="doctor", now=self.now)

        for target in ("pending-host", "quarantined-host"):
            claims = self.engine.claim_targets_for_target(
                target_id=target, worker_id="agent:" + target, limit=4,
                now=self.now + timedelta(seconds=1),
            )
            self.assertEqual([item["job_type"] for item in claims], ["doctor"])
            queued = self.engine.conn.execute(
                "SELECT j.job_type,t.status FROM management_job_targets t "
                "JOIN management_jobs j ON j.id=t.job_id WHERE t.target_id=?",
                (target,),
            ).fetchall()
            self.assertEqual(
                {row["job_type"]: row["status"] for row in queued
                 if row["job_type"] in mutating_kinds},
                {kind: QUEUED for kind in mutating_kinds},
            )

        approved_claims = self.engine.claim_targets_for_target(
            target_id="approved-host", worker_id="agent:approved-host",
            limit=4, now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(
            {item["job_type"] for item in approved_claims},
            set(mutating_kinds),
        )

    def test_queue_and_target_bounds_fail_closed(self):
        bounded = ManagementJobEngine(
            self.tmp, max_active_jobs=1, max_targets=2, lease_seconds=5
        )
        try:
            bounded.enqueue(
                job_type="doctor",
                targets=["a"],
                requested_by="operator",
                now=self.now,
            )
            with self.assertRaises(ControlPlaneError):
                bounded.enqueue(
                    job_type="doctor",
                    targets=["b"],
                    requested_by="operator",
                    now=self.now,
                )
        finally:
            bounded.close()

        other = tempfile.mkdtemp(prefix="drlink-v30-job-target-bound-")
        bounded = ManagementJobEngine(other, max_active_jobs=2, max_targets=2)
        try:
            with self.assertRaises(ControlPlaneError):
                bounded.enqueue(
                    job_type="doctor",
                    targets=["a", "b", "c"],
                    requested_by="operator",
                    now=self.now,
                )
        finally:
            bounded.close()

    def test_claim_and_per_target_results_are_truthful(self):
        job = self._enqueue(targets=("host-a", "host-b"))
        claims = self.engine.claim_targets(
            worker_id="worker-a", limit=2, now=self.now + timedelta(seconds=1)
        )
        self.assertEqual(len(claims), 2)
        self.assertEqual(self.engine.get(job["id"])["status"], RUNNING)

        first, second = claims
        self.engine.complete_target(
            job_id=first["job_id"],
            target_id=first["target_id"],
            claim_token=first["claim_token"],
            status=SUCCEEDED,
            result={"doctor": "pass"},
            now=self.now + timedelta(seconds=2),
        )
        final = self.engine.complete_target(
            job_id=second["job_id"],
            target_id=second["target_id"],
            claim_token=second["claim_token"],
            status=FAILED,
            error="agent offline",
            now=self.now + timedelta(seconds=2),
        )
        self.assertEqual(final["status"], FAILED)
        states = {item["target_id"]: item["status"] for item in final["targets"]}
        self.assertEqual(set(states.values()), {SUCCEEDED, FAILED})
        result_by_target = {item["target_id"]: item["result"] for item in final["targets"]}
        self.assertEqual(result_by_target[first["target_id"]], {"doctor": "pass"})

    def test_target_filtered_claim_cannot_take_another_agent_job(self):
        self._enqueue(targets=("agent-a",), now=self.now)
        self._enqueue(targets=("agent-b",), now=self.now)
        claims = self.engine.claim_targets_for_target(
            target_id="agent-a",
            worker_id="agent-a",
            limit=4,
            now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["target_id"], "agent-a")
        remaining = self.engine.conn.execute(
            "SELECT target_id,status FROM management_job_targets ORDER BY target_id"
        ).fetchall()
        states = {str(row["target_id"]): str(row["status"]) for row in remaining}
        self.assertEqual(states["agent-a"], RUNNING)
        self.assertEqual(states["agent-b"], QUEUED)

    def test_cancel_stops_queued_targets_without_claiming_running_target_terminated(self):
        job = self._enqueue(targets=("host-a", "host-b"))
        claim = self.engine.claim_targets(
            worker_id="worker-a", limit=1, now=self.now + timedelta(seconds=1)
        )[0]
        cancelling = self.engine.cancel(job["id"], now=self.now + timedelta(seconds=2))
        self.assertTrue(cancelling["cancel_requested"])
        self.assertEqual(cancelling["status"], RUNNING)
        queued = [t for t in cancelling["targets"] if t["target_id"] != claim["target_id"]]
        self.assertEqual(queued[0]["status"], CANCELLED)

        final = self.engine.complete_target(
            job_id=claim["job_id"],
            target_id=claim["target_id"],
            claim_token=claim["claim_token"],
            status=SUCCEEDED,
            result={"completed_before_cancel": True},
            now=self.now + timedelta(seconds=3),
        )
        self.assertEqual(final["status"], CANCELLED)
        running_target = next(t for t in final["targets"] if t["target_id"] == claim["target_id"])
        self.assertEqual(running_target["status"], SUCCEEDED)

    def test_deadline_and_lease_prevent_late_false_success(self):
        deadline_job = self._enqueue(targets=("deadline-host",), timeout_seconds=2)
        expired = self.engine.expire_deadlines(now=self.now + timedelta(seconds=3))
        self.assertEqual(expired, 1)
        self.assertEqual(self.engine.get(deadline_job["id"])["status"], FAILED)
        self.assertEqual(
            self.engine.get(deadline_job["id"])["targets"][0]["error"],
            "DEADLINE_EXCEEDED",
        )

        lease_job = self._enqueue(
            targets=("lease-host",), timeout_seconds=60, now=self.now + timedelta(seconds=10)
        )
        claim = self.engine.claim_targets(
            worker_id="worker-a", limit=1, now=self.now + timedelta(seconds=11)
        )[0]
        late = self.engine.complete_target(
            job_id=claim["job_id"],
            target_id=claim["target_id"],
            claim_token=claim["claim_token"],
            status=SUCCEEDED,
            result={"should_not": "be accepted"},
            now=self.now + timedelta(seconds=17),
        )
        self.assertEqual(late["status"], FAILED)
        self.assertEqual(late["targets"][0]["error"], "WORKER_LEASE_EXPIRED")
        self.assertEqual(late["targets"][0]["result"], {})

    def test_restart_fails_entire_partially_inflight_job(self):
        job = self._enqueue(targets=("host-a", "host-b"))
        self.engine.claim_targets(
            worker_id="worker-a", limit=1, now=self.now + timedelta(seconds=1)
        )
        changed = self.engine.recover_interrupted(now=self.now + timedelta(seconds=2))
        self.assertEqual(changed, 1)
        recovered = self.engine.get(job["id"])
        self.assertEqual(recovered["status"], FAILED)
        self.assertEqual(
            {target["status"] for target in recovered["targets"]}, {FAILED}
        )
        self.assertEqual(
            {target["error"] for target in recovered["targets"]},
            {"SERVER_RESTART_INTERRUPTED"},
        )

    def test_job_queries_are_bounded_keyset_and_include_target_truth(self):
        first_job = self._enqueue(targets=("host-a",), now=self.now)
        second_job = self._enqueue(targets=("host-b",), now=self.now)
        self.engine.cancel(first_job["id"], now=self.now + timedelta(seconds=1))

        query = ManagementQueryService(self.tmp)
        try:
            page1 = query.job_list(limit=1)
            self.assertEqual(len(page1.items), 1)
            self.assertIsNotNone(page1.next_cursor)
            page2 = query.job_list(limit=1, cursor=page1.next_cursor)
            self.assertEqual(len(page2.items), 1)
            self.assertNotEqual(page1.items[0]["id"], page2.items[0]["id"])

            cancelled = query.job_list(status=CANCELLED, limit=10)
            self.assertEqual([item["id"] for item in cancelled.items], [first_job["id"]])

            detail = query.job_get(second_job["id"])
            self.assertEqual(detail["id"], second_job["id"])
            self.assertEqual(detail["targets"][0]["target_id"], "host-b")
            ready = {item["name"] for item in query.ready_mcp_descriptors()}
            self.assertIn("drlink_job_list", ready)
            self.assertIn("drlink_job_get", ready)
            self.assertNotIn("drlink_diagnostic_job_start", ready)
        finally:
            query.close()

    def test_public_cli_job_inspect_cancel_and_recovery(self):
        job = self._enqueue(targets=("host-a", "host-b"))
        claim = self.engine.claim_targets(
            worker_id="worker-a", limit=1, now=self.now + timedelta(seconds=1)
        )[0]

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(["system", "jobs"], root=self.tmp)
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn(job["id"], out.getvalue())
        self.assertIn("RUNNING", out.getvalue())

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(
                ["system", "job", job["id"]], root=self.tmp
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("Management Job: %s" % job["id"], out.getvalue())
        self.assertIn("host-a", out.getvalue())
        self.assertIn("host-b", out.getvalue())

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(
                ["system", "job", "cancel", job["id"]], root=self.tmp
            )
        self.assertEqual(rc, 0, err.getvalue())
        current = self.engine.get(job["id"])
        self.assertEqual(current["status"], RUNNING)
        self.assertTrue(current["cancel_requested"])
        queued = [
            item for item in current["targets"] if item["target_id"] != claim["target_id"]
        ][0]
        self.assertEqual(queued["status"], CANCELLED)
        self.assertIn("not claimed terminated", out.getvalue())

        self.engine.complete_target(
            job_id=claim["job_id"],
            target_id=claim["target_id"],
            claim_token=claim["claim_token"],
            status=SUCCEEDED,
            result={"completed_before_cancel": True},
            now=self.now + timedelta(seconds=2),
        )
        self.assertEqual(self.engine.get(job["id"])["status"], CANCELLED)

        interrupted = self._enqueue(
            targets=("host-c", "host-d"),
            now=self.now + timedelta(seconds=10),
        )
        self.engine.claim_targets(
            worker_id="worker-b",
            limit=1,
            now=self.now + timedelta(seconds=11),
        )
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = control_cli.dispatch(["system", "jobs", "recover"], root=self.tmp)
        self.assertEqual(rc, 0, err.getvalue())
        recovered = self.engine.get(interrupted["id"])
        self.assertEqual(recovered["status"], FAILED)
        self.assertEqual(
            {item["error"] for item in recovered["targets"]},
            {"SERVER_RESTART_INTERRUPTED"},
        )
        self.assertIn("failed closed", out.getvalue())

    def test_job_read_reconciles_unclaimed_deadline_to_failed(self):
        old = self.now - timedelta(seconds=30)
        job = self._enqueue(targets=("offline-agent",), timeout_seconds=1, now=old)
        query = ManagementQueryService(self.tmp)
        try:
            detail = query.job_get(job["id"])
            self.assertEqual(detail["status"], FAILED)
            self.assertEqual(detail["targets"][0]["status"], FAILED)
            self.assertEqual(detail["targets"][0]["error"], "DEADLINE_EXCEEDED")
        finally:
            query.close()

    def test_operational_summary_is_rebuildable_and_reports_saturation(self):
        self._enqueue(targets=("host-a",))
        summary = job_operational_summary(self.engine.conn, max_active_jobs=1)
        self.assertEqual(summary["queued_jobs"], 1)
        self.assertEqual(summary["queued_targets"], 1)
        self.assertTrue(summary["saturated"])

    def test_worker_pool_backpressure_does_not_preclaim_unbounded_targets(self):
        job = self._enqueue(targets=("host-a", "host-b"), timeout_seconds=3600)
        entered = threading.Event()
        release = threading.Event()

        def handler(claim):
            # A separate writer can acquire the DB while this RPC handler is waiting,
            # proving the worker does not hold the Job Engine write transaction.
            other = open_control_db(self.tmp)
            try:
                other.execute(
                    "INSERT OR REPLACE INTO system_meta(key,value) VALUES ('worker_probe','ok')"
                )
            finally:
                other.close()
            entered.set()
            release.wait(2)
            return {"target": claim["target_id"]}

        pool = BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0)
        try:
            futures = pool.dispatch_once(
                self.engine, handler, worker_id="rpc-worker", limit=2
            )
            self.assertEqual(len(futures), 1)
            self.assertTrue(entered.wait(1))
            second_attempt = pool.dispatch_once(
                self.engine, handler, worker_id="rpc-worker", limit=2
            )
            self.assertEqual(second_attempt, [])
            current = self.engine.get(job["id"])
            self.assertEqual(
                sum(1 for target in current["targets"] if target["status"] == RUNNING), 1
            )
            self.assertEqual(
                sum(1 for target in current["targets"] if target["status"] == QUEUED), 1
            )
            release.set()
            futures[0].result(timeout=2)

            follow = pool.dispatch_once(
                self.engine, lambda claim: {"target": claim["target_id"]},
                worker_id="rpc-worker",
                limit=2,
            )
            self.assertEqual(len(follow), 1)
            follow[0].result(timeout=2)
            self.assertEqual(self.engine.get(job["id"])["status"], SUCCEEDED)
        finally:
            release.set()
            pool.close()


if __name__ == "__main__":
    unittest.main()
