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

    def test_agent_invalid_claim_limit_never_contacts_core(self):
        # A local caller cannot claim work from Core before its own bounded
        # request has been validated. Even a signed Core claim changes leases.
        from unittest.mock import patch
        import drlink_agent_lifecycle as agent

        for invalid in (0, -1, True, False, 1.5, "1", None):
            with self.subTest(limit=invalid):
                with patch(
                    "drlink_mgmt_sync.claim_management_jobs_on_server",
                    side_effect=AssertionError("Core must not receive an invalid claim"),
                ) as claim:
                    with self.assertRaisesRegex(
                        ValueError, "Core Management Job claim response UNKNOWN"
                    ):
                        agent.process_management_jobs_once(root=self.tmp, limit=invalid)
                    claim.assert_not_called()

    def test_agent_invalid_identity_never_leases_core_work(self):
        # A valid signed session cannot compensate for absent or malformed
        # local Host identity; do not reserve Core work before this check.
        from unittest.mock import patch
        import drlink_agent_lifecycle as agent

        bad_identities = (
            {}, {"machine_id": None}, {"machine_id": "  "},
            {"machine_id": True}, {"machine_id": "host\nspoof"},
        )
        for identity in bad_identities:
            with self.subTest(identity=identity):
                with patch(
                    "drlink_mgmt_sync._agent_identity", return_value=identity,
                ), patch(
                    "drlink_mgmt_sync.claim_management_jobs_on_server",
                    side_effect=AssertionError("No Core claim with invalid Host identity"),
                ) as claim:
                    with self.assertRaisesRegex(
                        ValueError, "Core Management Job claim response UNKNOWN"
                    ):
                        agent.process_management_jobs_once(root=self.tmp, limit=1)
                    claim.assert_not_called()

    def test_enqueue_rejects_coerced_timeout_before_queue_mutation(self):
        before = self.engine.conn.execute(
            "SELECT COUNT(*) FROM management_jobs"
        ).fetchone()[0]
        for invalid in (True, False, 1.5, "2", None):
            with self.subTest(timeout=invalid):
                with self.assertRaisesRegex(
                    ControlPlaneError, "Management Job timeout must be an integer"
                ):
                    self._enqueue(timeout_seconds=invalid)
                self.assertEqual(
                    self.engine.conn.execute(
                        "SELECT COUNT(*) FROM management_jobs"
                    ).fetchone()[0],
                    before,
                )

    def test_core_claim_rejects_coerced_limit_before_leasing_target(self):
        job = self._enqueue(targets=("host-a",))
        for invalid in (0, -1, True, False, 1.5, "1", None):
            with self.subTest(limit=invalid):
                with self.assertRaisesRegex(
                    ControlPlaneError, "Management Job claim limit must be a positive integer"
                ):
                    self.engine.claim_targets(worker_id="worker-a", limit=invalid)
                self.assertEqual(
                    self.engine.get(job["id"])["targets"][0]["status"], QUEUED
                )
        self.assertEqual(
            len(self.engine.claim_targets(worker_id="worker-a", limit=1)), 1
        )

    def test_enqueue_rejects_nonobject_payload_before_queue_mutation(self):
        before = self.engine.conn.execute(
            "SELECT COUNT(*) FROM management_jobs"
        ).fetchone()[0]
        for invalid in ([], ["not-an-object"], "invalid", False, 1.5):
            with self.subTest(payload=invalid):
                with self.assertRaisesRegex(
                    ControlPlaneError, "Management Job payload must be an object"
                ):
                    self._enqueue(payload=invalid)
                self.assertEqual(
                    self.engine.conn.execute(
                        "SELECT COUNT(*) FROM management_jobs"
                    ).fetchone()[0],
                    before,
                )
        self.assertEqual(self._enqueue(payload={})["status"], QUEUED)
        self.assertEqual(self._enqueue(payload=None)["status"], QUEUED)

    def test_job_targets_reject_scalar_mapping_and_nontext_before_enqueue(self):
        # A scalar hostname must not become one target per character, and a
        # mapping must not silently turn keys into executable Host targets.
        before = self.engine.conn.execute(
            "SELECT COUNT(*) FROM management_jobs"
        ).fetchone()[0]
        malformed = (
            "host-a", b"host-a", {"host-a": True}, None,
            ["host-a", 12], ["host-a", True], ["host-a", {"id": "host-b"}],
        )
        for targets in malformed:
            with self.subTest(targets=targets):
                with self.assertRaisesRegex(
                    ControlPlaneError, "Management Job target"
                ):
                    self._enqueue(targets=targets)
                self.assertEqual(
                    self.engine.conn.execute(
                        "SELECT COUNT(*) FROM management_jobs"
                    ).fetchone()[0],
                    before,
                )
        job = self._enqueue(targets=("host-a", "host-b"))
        self.assertEqual(job["target_count"], 2)

    def test_agent_remote_service_receipt_rejects_unverified_set_state(self):
        # A local mutation acknowledgement cannot be promoted to an Agent
        # success receipt with an invented status. Core accepts only these
        # concrete native states; unknown evidence stays UNKNOWN.
        from drlink_agent_lifecycle import _require_agent_remote_service_receipt
        entity = {
            "type": "remote-service", "id": "ssh-access", "name": "ssh-access",
        }
        base = {
            "operation": "set", "entity": entity,
            "view": {
                "name": "ssh-access", "service": "ssh",
                "enabled": True, "status": "HEALTHY",
            },
        }
        for bad in ("UNKNOWN", "ACTIVE", "", None, True, [], 0):
            with self.subTest(runtime_status=bad):
                receipt = {**base, "view": {**base["view"], "status": bad}}
                with self.assertRaisesRegex(ValueError, "receipt UNKNOWN"):
                    _require_agent_remote_service_receipt(
                        receipt, operation="set", name="ssh-access",
                    )
        for state in ("HEALTHY", "DEGRADED", "DISABLED"):
            with self.subTest(good_runtime_status=state):
                receipt = {**base, "view": {**base["view"], "status": state}}
                self.assertIs(
                    _require_agent_remote_service_receipt(
                        receipt, operation="set", name="ssh-access",
                    ), receipt,
                )
        deletion = {"operation": "delete", "entity": entity}
        self.assertIs(
            _require_agent_remote_service_receipt(
                deletion, operation="delete", name="ssh-access",
            ), deletion,
        )

    def test_nonfinite_job_payload_rejected_before_enqueue(self):
        # The source writer must not persist a Job that the strict lease-time
        # reader will refuse; fail before creating an executable queue row.
        before = self.engine.conn.execute(
            "SELECT COUNT(*) FROM management_jobs"
        ).fetchone()[0]
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(nonfinite=str(value)):
                with self.assertRaisesRegex(
                    ControlPlaneError, "not JSON serializable"
                ):
                    self._enqueue(payload={"score": value})
                after = self.engine.conn.execute(
                    "SELECT COUNT(*) FROM management_jobs"
                ).fetchone()[0]
                self.assertEqual(after, before)

    def test_corrupt_persisted_payload_never_leases_core_job(self):
        # A corrupted queued Job must never be leased to an Agent as an
        # invented empty payload. Leave its target queued for investigation.
        job = self._enqueue(targets=("host-a",), payload={"operation": "doctor"})
        malformed = (
            "", "{", "[]", "null", '"text"', "true",
            '{"value":NaN}', '{"value":Infinity}',
            '{"operation":"doctor","operation":"refresh"}',
            '{"large":"' + "x" * 16385 + '"}',
        )
        for raw in malformed:
            with self.subTest(raw=raw[:70]):
                self.engine.conn.execute(
                    "UPDATE management_jobs SET payload_json=? WHERE id=?",
                    (raw, job["id"]),
                )
                self.engine.conn.commit()
                claims = self.engine.claim_targets_for_target(
                    target_id="host-a", worker_id="agent:host-a", limit=1,
                    now=self.now + timedelta(seconds=1),
                )
                self.assertEqual(claims, [])
                target = self.engine.conn.execute(
                    "SELECT status,attempt,claim_token,lease_expires_at "
                    "FROM management_job_targets WHERE job_id=? AND target_id=?",
                    (job["id"], "host-a"),
                ).fetchone()
                self.assertEqual(target["status"], QUEUED)
                self.assertEqual(target["attempt"], 0)
                self.assertFalse(target["claim_token"])
                self.assertIsNone(target["lease_expires_at"])
        self.engine.conn.execute(
            "UPDATE management_jobs SET payload_json=? WHERE id=?",
            ('{"operation":"doctor"}', job["id"]),
        )
        self.engine.conn.commit()
        claims = self.engine.claim_targets_for_target(
            target_id="host-a", worker_id="agent:host-a", limit=1,
            now=self.now + timedelta(seconds=2),
        )
        self.assertEqual([c["job_id"] for c in claims], [job["id"]])
        self.assertEqual(claims[0]["payload"], {"operation": "doctor"})

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

    def test_core_failed_job_never_persists_unverified_result_payload(self):
        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        claim = self.engine.claim_targets(
            worker_id="worker-result", limit=1, now=self.now + timedelta(seconds=1)
        )[0]
        secret = "Bearer fixture-only-failed-core-result"
        final = self.engine.complete_target(
            job_id=claim["job_id"], target_id=claim["target_id"],
            claim_token=claim["claim_token"], status=FAILED,
            result={"untrusted_credentials": secret}, error="AGENT_JOB_EXECUTION_FAILED",
            now=self.now + timedelta(seconds=2),
        )
        self.assertEqual(final["status"], FAILED)
        self.assertEqual(final["targets"][0]["result"], {})
        self.assertNotIn(secret, str(final))
        self.assertNotIn(secret, str(self.engine.get(job["id"])))

    def test_core_cancelled_job_never_persists_unverified_result_payload(self):
        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        claim = self.engine.claim_targets(
            worker_id="worker-cancel-result", limit=1,
            now=self.now + timedelta(seconds=1),
        )[0]
        self.engine.cancel(job["id"], now=self.now + timedelta(seconds=1))
        secret = "Bearer fixture-only-cancelled-result"
        final = self.engine.complete_target(
            job_id=claim["job_id"], target_id=claim["target_id"],
            claim_token=claim["claim_token"], status=CANCELLED,
            result={"untrusted_credentials": secret}, error="CANCELLED_BEFORE_RPC",
            now=self.now + timedelta(seconds=2),
        )
        self.assertEqual(final["status"], CANCELLED)
        self.assertEqual(final["targets"][0]["result"], {})
        self.assertNotIn(secret, str(self.engine.get(job["id"])))

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

    def test_worker_pool_rejects_stale_or_invalid_core_claim_before_handler(self):
        from unittest import mock

        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        claim = self.engine.claim_targets(
            worker_id="rpc-worker", limit=1, now=self.now + timedelta(seconds=1)
        )[0]
        late = self.now + timedelta(seconds=12)
        cases = [
            {"lease_expires_at": claim["lease_expires_at"]},
            {"deadline_at": (self.now + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "lease_expires_at": (self.now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"lease_expires_at": {"untrusted": "secret"}},
            {"deadline_at": "not-a-core-utc-date"},
        ]
        for change in cases:
            offered = {**claim, **change}
            with self.subTest(change=change), mock.patch(
                "drlink_v30_jobs._utc_now", return_value=late
            ), mock.patch.object(self.engine, "complete_target") as completed:
                with self.assertRaisesRegex(ControlPlaneError, "claim UNKNOWN"):
                    BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0)._run_claim(
                        self.engine, offered,
                        lambda _claim: self.fail("Expired or malformed claim executed")
                    )
                completed.assert_not_called()
        self.assertEqual(self.engine.get(job["id"])["status"], RUNNING)

    def test_worker_pool_submit_failure_returns_reserved_capacity(self):
        from unittest import mock

        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        with BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0) as pool:
            with mock.patch.object(
                pool._executor, "submit", side_effect=RuntimeError("executor shut down")
            ):
                with self.assertRaisesRegex(RuntimeError, "executor shut down"):
                    pool.dispatch_once(
                        self.engine, lambda _claim: {"operation": "doctor"},
                        worker_id="rpc-dispatcher", limit=1,
                    )
            # Core keeps the claimed Job until lease recovery; a rejected
            # local executor must not permanently exhaust the worker slots.
            self.assertTrue(
                pool._slots.acquire(blocking=False),
                "executor rejection leaked bounded RPC capacity",
            )
            pool._slots.release()
        self.assertEqual(self.engine.get(job["id"])["targets"][0]["status"], RUNNING)

    def test_worker_pool_partial_submit_failure_preserves_inflight_capacity(self):
        from concurrent.futures import Future
        from unittest import mock

        job = self._enqueue(
            targets=("host-a", "host-b"), timeout_seconds=3600
        )
        in_flight = Future()
        attempts = []

        def submit_one_then_reject(*args):
            attempts.append(args)
            if len(attempts) == 1:
                return in_flight
            raise RuntimeError("second executor slot rejected")

        with BoundedAgentRpcWorkerPool(max_workers=2, max_pending=0) as pool:
            with mock.patch.object(
                pool._executor, "submit", side_effect=submit_one_then_reject
            ):
                with self.assertRaisesRegex(RuntimeError, "slot rejected"):
                    pool.dispatch_once(
                        self.engine, lambda _claim: {"operation": "doctor"},
                        worker_id="rpc-partial", limit=2,
                    )
            self.assertEqual(len(attempts), 2)
            # Only the unscheduled claim's slot is returned immediately.
            self.assertTrue(pool._slots.acquire(blocking=False))
            self.assertFalse(pool._slots.acquire(blocking=False))
            pool._slots.release()
            in_flight.set_result({"status": SUCCEEDED})
            self.assertTrue(pool._slots.acquire(blocking=False))
            self.assertTrue(pool._slots.acquire(blocking=False))
            pool._slots.release()
            pool._slots.release()
        self.assertEqual(
            [t["status"] for t in self.engine.get(job["id"])["targets"]],
            [RUNNING, RUNNING],
            "No invented worker completions for mock rejected submissions",
        )

    def test_generic_rpc_worker_never_recompletes_after_ambiguous_success_ack(self):
        from unittest import mock

        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        claim = self.engine.claim_targets(
            worker_id="worker-once", limit=1, now=self.now + timedelta(seconds=1)
        )[0]
        commit = self.engine.complete_target
        statuses = []

        def committed_but_unacknowledged(**kwargs):
            statuses.append(kwargs["status"])
            reply = commit(**kwargs, now=self.now + timedelta(seconds=2))
            if kwargs["status"] == SUCCEEDED:
                # A transaction can commit before its response is lost.
                raise TimeoutError("lost receipt Bearer fixture-success-receipt-secret")
            return reply

        with BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0) as pool, mock.patch.object(
            self.engine, "complete_target", side_effect=committed_but_unacknowledged
        ):
            with self.assertRaisesRegex(
                ControlPlaneError, "completion receipt UNKNOWN"
            ) as caught:
                pool._run_claim(
                    self.engine, claim, lambda _claim: {"operation": "doctor"}
                )
        self.assertNotIn("fixture-success-receipt-secret", str(caught.exception))
        self.assertEqual(statuses, [SUCCEEDED], "No contradictory FAILED completion")
        self.assertEqual(self.engine.get(job["id"])["status"], SUCCEEDED)

    def test_generic_rpc_worker_never_recompletes_after_ambiguous_cancel_ack(self):
        from unittest import mock

        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        claim = self.engine.claim_targets(
            worker_id="worker-cancel-once", limit=1, now=self.now + timedelta(seconds=1)
        )[0]
        self.engine.cancel(job["id"], now=self.now + timedelta(seconds=1))
        commit = self.engine.complete_target
        statuses = []

        def committed_but_unacknowledged(**kwargs):
            statuses.append(kwargs["status"])
            commit(**kwargs, now=self.now + timedelta(seconds=2))
            raise TimeoutError("lost receipt Bearer fixture-cancel-receipt-secret")

        with BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0) as pool, mock.patch.object(
            self.engine, "complete_target", side_effect=committed_but_unacknowledged
        ):
            with self.assertRaisesRegex(
                ControlPlaneError, "completion receipt UNKNOWN"
            ) as caught:
                pool._run_claim(
                    self.engine, claim, lambda _claim: self.fail(
                        "cancelled claim must not run the handler"
                    )
                )
        self.assertNotIn("fixture-cancel-receipt-secret", str(caught.exception))
        self.assertEqual(statuses, [CANCELLED], "No contradictory FAILED completion")
        self.assertEqual(self.engine.get(job["id"])["status"], CANCELLED)

    def test_generic_rpc_worker_hides_handler_secrets_when_failure_receipt_is_unknown(self):
        from unittest import mock

        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        claim = self.engine.claim_targets(
            worker_id="worker-failure", limit=1, now=self.now + timedelta(seconds=1)
        )[0]
        secret = "Bearer fixture-only-handler-secret"

        def private_handler(_claim):
            raise ValueError("private job handler failed: " + secret)

        with BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0) as pool, mock.patch.object(
            self.engine, "complete_target", side_effect=OSError("Core DB unavailable")
        ) as completion:
            with self.assertRaisesRegex(
                ControlPlaneError, "completion receipt UNKNOWN"
            ) as caught:
                pool._run_claim(self.engine, claim, private_handler)
        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(completion.call_args.kwargs["status"], FAILED)
        self.assertEqual(self.engine.get(job["id"])["status"], RUNNING)

    def test_generic_rpc_worker_never_persists_handler_exception_secrets(self):
        job = self._enqueue(targets=("host-a",), timeout_seconds=3600)
        secret = "Bearer test-only-core-worker-credential"

        def failing_handler(_claim):
            raise ValueError("remote target refused " + secret)

        with BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0) as pool:
            futures = pool.dispatch_once(
                self.engine, failing_handler, worker_id="rpc-worker", limit=1
            )
            self.assertEqual(len(futures), 1)
            result = futures[0].result(timeout=3)

        self.assertEqual(result["status"], FAILED)
        self.assertEqual(result["targets"][0]["error"], "AGENT_JOB_EXECUTION_FAILED")
        self.assertEqual(result["last_error"], "AGENT_JOB_EXECUTION_FAILED")
        self.assertNotIn(secret, str(result))
        self.assertNotIn(secret, str(self.engine.get(job["id"])))


if __name__ == "__main__":
    unittest.main()
