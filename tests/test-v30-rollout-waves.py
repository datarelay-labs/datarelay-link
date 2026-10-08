#!/usr/bin/env python3
"""Bounded staged Agent rollout scheduler contract; no remote Agent mutation."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
from drlink_control_db import ControlPlaneError
from drlink_v30_jobs import (
    CANCELLED, FAILED, QUEUED, SUCCEEDED, BoundedAgentRpcWorkerPool,
    ManagementJobEngine,
)


class StagedRolloutSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-rollout-waves-")
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        plane = ControlPlane(self.tmp.name)
        try:
            for host in ("a-first", "b-second", "z-canary"):
                plane.upsert_client(host, hostname=host)
        finally:
            plane.close()
        self.engine = ManagementJobEngine(self.tmp.name, max_targets=8, lease_seconds=30)
        self.artifact = {
            "version": "3.0.0-rc.1",
            "source_ref": "a" * 40,
            "sha256": "b" * 64,
        }

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def _start(self, *, threshold: int = 20):
        return self.engine.enqueue_rollout(
            targets=("a-first", "b-second", "z-canary"),
            canary_targets=("z-canary",),
            requested_by="ops-admin",
            artifact=self.artifact,
            wave_size=1,
            failure_threshold_percent=threshold,
            now=self.now,
        )

    def _claim(self, t: int = 1):
        return self.engine.claim_targets(
            worker_id="worker-a", limit=1,
            now=self.now + timedelta(seconds=t),
        )

    def _complete(self, job, claim, state, *, tick=2):
        return self.engine.complete_target(
            job_id=job["id"], target_id=claim["target_id"],
            claim_token=claim["claim_token"], status=state,
            now=self.now + timedelta(seconds=tick),
        )

    def test_canary_wins_even_if_sorted_last_then_waves_are_serial(self):
        job = self._start()
        first = self._claim()
        self.assertEqual([c["target_id"] for c in first], ["z-canary"])
        self.assertEqual(self._claim(), [])
        self._complete(job, first[0], SUCCEEDED)
        self.assertEqual(self.engine.get(job["id"])["status"], QUEUED)
        second = self._claim(3)
        self.assertEqual([c["target_id"] for c in second], ["a-first"])
        self.assertEqual(self._claim(4), [])
        self._complete(job, second[0], SUCCEEDED, tick=5)
        third = self._claim(6)
        self.assertEqual([c["target_id"] for c in third], ["b-second"])
        final = self._complete(job, third[0], SUCCEEDED, tick=7)
        self.assertEqual(final["status"], SUCCEEDED)
        self.assertEqual(final["payload"]["rollout_state"], "WAVE")
        self.assertEqual({x["status"] for x in final["targets"]}, {SUCCEEDED})

    def test_generic_rpc_worker_cannot_falsely_complete_unqualified_rollout(self):
        job = self._start()
        executed = []

        def unqualified_handler(claim):
            executed.append(claim)
            return {"claimed_success": True}

        with BoundedAgentRpcWorkerPool(max_workers=1, max_pending=0) as pool:
            futures = pool.dispatch_once(
                self.engine, unqualified_handler, worker_id="generic-rpc", limit=1
            )
            self.assertEqual(len(futures), 1)
            finished = futures[0].result(timeout=3)
            self.assertEqual(finished["status"], FAILED)
            self.assertEqual(
                pool.dispatch_once(
                    self.engine, unqualified_handler, worker_id="generic-rpc", limit=2
                ),
                [],
            )

        self.assertEqual(executed, [])
        result = self.engine.get(job["id"])
        self.assertEqual(result["payload"]["rollout_state"], "HALTED")
        self.assertEqual(result["payload"]["halt_reason"], "CANARY_FAILED")
        by_id = {row["target_id"]: row for row in result["targets"]}
        self.assertIn("AGENT_UPDATER_NOT_QUALIFIED", by_id["z-canary"]["error"])
        self.assertEqual(by_id["a-first"]["status"], CANCELLED)
        self.assertEqual(by_id["b-second"]["status"], CANCELLED)

    def test_canary_failure_halts_without_claiming_remaining_hosts(self):
        job = self._start()
        first = self._claim()
        self.assertEqual(len(first), 1)
        failed = self._complete(job, first[0], FAILED, tick=2)
        self.assertEqual(failed["status"], FAILED)
        self.assertEqual(failed["payload"]["halt_reason"], "CANARY_FAILED")
        self.assertEqual(self._claim(3), [])
        final = self.engine.get(job["id"])
        self.assertEqual(final["status"], FAILED)
        self.assertEqual(final["payload"]["rollout_state"], "HALTED")
        self.assertEqual(final["payload"]["halt_reason"], "CANARY_FAILED")
        by_id = {x["target_id"]: x["status"] for x in final["targets"]}
        self.assertEqual(by_id["z-canary"], FAILED)
        self.assertEqual(by_id["a-first"], CANCELLED)
        self.assertEqual(by_id["b-second"], CANCELLED)

    def test_explicit_pause_keeps_noncanaries_queued_until_canary_pass(self):
        job = self._start()
        paused = self.engine.rollout_control(job["id"], action="pause")
        self.assertTrue(paused["payload"]["operator_paused"])
        self.assertEqual(self._claim(), [])
        resumed = self.engine.rollout_control(job["id"], action="resume")
        self.assertEqual(resumed["payload"]["rollout_state"], "CANARY")
        self.assertEqual([c["target_id"] for c in self._claim()], ["z-canary"])
        self.assertEqual(self._claim(), [])

    def test_failure_threshold_halts_subsequent_wave(self):
        job = self._start(threshold=20)
        canary = self._claim()[0]
        self._complete(job, canary, SUCCEEDED, tick=2)
        wave = self._claim(3)[0]
        self.assertEqual(wave["target_id"], "a-first")
        self._complete(job, wave, FAILED, tick=4)
        self.assertEqual(self._claim(5), [])
        result = self.engine.get(job["id"])
        self.assertEqual(result["payload"]["halt_reason"], "FAILURE_THRESHOLD_REACHED")
        self.assertEqual(result["status"], FAILED)
        remaining = {x["target_id"]: x["status"] for x in result["targets"]}
        self.assertEqual(remaining["b-second"], CANCELLED)

    def test_expired_canary_lease_halts_and_cancels_queued_targets(self):
        job = self._start()
        self.assertEqual(self._claim()[0]["target_id"], "z-canary")
        recovered = self.engine.recover_expired_claims(
            now=self.now + timedelta(seconds=32)
        )
        self.assertEqual(recovered, 1)
        state = self.engine.get(job["id"])
        self.assertEqual(state["status"], FAILED)
        self.assertEqual(state["payload"]["rollout_state"], "HALTED")
        self.assertEqual(state["payload"]["halt_reason"], "WORKER_LEASE_EXPIRED")
        targets = {item["target_id"]: item for item in state["targets"]}
        self.assertEqual(targets["z-canary"]["status"], FAILED)
        self.assertEqual(targets["z-canary"]["error"], "WORKER_LEASE_EXPIRED")
        self.assertEqual(targets["a-first"]["status"], CANCELLED)
        self.assertEqual(targets["b-second"]["status"], CANCELLED)
        self.assertEqual(self._claim(33), [])

    def test_restart_and_deadline_mark_rollout_halted(self):
        for reason in ("SERVER_RESTART_INTERRUPTED", "DEADLINE_EXCEEDED"):
            with self.subTest(reason=reason):
                job = self._start()
                if reason == "SERVER_RESTART_INTERRUPTED":
                    self._claim()
                    count = self.engine.recover_interrupted(
                        now=self.now + timedelta(seconds=2)
                    )
                else:
                    count = self.engine.expire_deadlines(
                        now=self.now + timedelta(seconds=301)
                    )
                self.assertEqual(count, 1)
                state = self.engine.get(job["id"])
                self.assertEqual(state["status"], FAILED)
                self.assertEqual(state["payload"]["rollout_state"], "HALTED")
                self.assertEqual(state["payload"]["halt_reason"], reason)
                self.assertEqual(
                    {item["status"] for item in state["targets"]}, {FAILED}
                )

    def test_halted_partial_wave_rejects_resume_and_pause(self):
        job = self.engine.enqueue_rollout(
            targets=("a-first", "b-second", "z-canary"),
            canary_targets=("z-canary",),
            requested_by="ops-admin", artifact=self.artifact,
            wave_size=2, failure_threshold_percent=20, now=self.now,
        )
        canary = self._claim()[0]
        self._complete(job, canary, SUCCEEDED)
        first, second = self.engine.claim_targets(
            worker_id="worker-a", limit=2,
            now=self.now + timedelta(seconds=3),
        )
        self._complete(job, first, FAILED, tick=4)
        state = self.engine.get(job["id"])
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["payload"]["rollout_state"], "HALTED")
        self.assertEqual(state["payload"]["halt_reason"], "FAILURE_THRESHOLD_REACHED")
        self.assertEqual(
            next(item["status"] for item in state["targets"]
                 if item["target_id"] == second["target_id"]),
            "RUNNING",
        )
        for action in ("resume", "pause"):
            with self.subTest(action=action), self.assertRaises(ControlPlaneError):
                self.engine.rollout_control(job["id"], action=action)
            self.assertEqual(
                self.engine.get(job["id"])["payload"]["rollout_state"], "HALTED"
            )

    def test_cancelled_inflight_rollout_cannot_be_restarted(self):
        job = self._start()
        self._claim()
        requested = self.engine.cancel(
            job["id"], now=self.now + timedelta(seconds=2)
        )
        self.assertEqual(requested["status"], "RUNNING")
        self.assertEqual(requested["cancel_requested"], 1)
        for action in ("pause", "resume"):
            with self.subTest(action=action), self.assertRaises(ControlPlaneError):
                self.engine.rollout_control(job["id"], action=action)
        current = self.engine.get(job["id"])
        self.assertEqual(current["cancel_requested"], 1)
        self.assertFalse(current["payload"].get("operator_paused"))

    def test_expired_rollout_halt_persists_across_new_engine_connection(self):
        job = self._start()
        self._claim()
        self.engine.recover_expired_claims(now=self.now + timedelta(seconds=33))
        with ManagementJobEngine(self.tmp.name, max_targets=8) as restarted:
            current = restarted.get(job["id"])
            self.assertEqual(current["status"], FAILED)
            self.assertEqual(current["payload"]["rollout_state"], "HALTED")
            self.assertEqual(current["payload"]["halt_reason"], "WORKER_LEASE_EXPIRED")
            self.assertEqual(
                restarted.recover_expired_claims(
                    now=self.now + timedelta(seconds=34)
                ), 0,
            )
            self.assertEqual(
                restarted.claim_targets(
                    worker_id="restarted", limit=8,
                    now=self.now + timedelta(seconds=35),
                ), [],
            )

    def test_mutable_source_ref_rejected_even_with_valid_digest(self):
        for ref in ("main", "feature/v3.0-drl3-0", "v3.0.0", "a" * 39, "f" * 41):
            with self.subTest(ref=ref), self.assertRaises(ControlPlaneError):
                self.engine.enqueue_rollout(
                    targets=("a-first",), requested_by="ops-admin",
                    artifact={"version": "3.0.0-rc.1", "source_ref": ref,
                              "sha256": "b" * 64}, wave_size=1, now=self.now,
                )

    def test_preview_never_enqueues_and_matches_canary_scheduler(self):
        before = self.engine.conn.execute("SELECT COUNT(*) FROM management_jobs").fetchone()[0]
        preview = self.engine.preview_rollout(
            targets=("a-first", "b-second", "z-canary"),
            canary_targets=("z-canary",),
            requested_by="ops-admin", artifact=self.artifact,
            wave_size=1,
        )
        self.assertTrue(preview["read_only"])
        self.assertTrue(preview["eligible"])
        self.assertFalse(preview["ready_to_apply"])
        self.assertEqual(preview["artifact_qualification"], "NOT_VERIFIED")
        self.assertEqual(preview["targets"], ["a-first", "b-second", "z-canary"])
        self.assertEqual(preview["canary_targets"], ["z-canary"])
        self.assertEqual(preview["target_count"], 3)
        self.assertEqual(preview["wave_size"], 1)
        self.assertEqual(preview["artifact"]["source_ref"], "a" * 40)
        self.assertEqual(
            self.engine.conn.execute("SELECT COUNT(*) FROM management_jobs").fetchone()[0],
            before,
        )
        actual = self._start()
        self.assertEqual(preview["canary_targets"], actual["payload"]["canary_targets"])

    def test_preview_shows_observed_versions_without_claiming_artifact_provenance(self):
        self.engine.conn.execute(
            "UPDATE clients SET agent_version='2.4.0', agent_platform='linux',"
            " agent_heartbeat_at=?,agent_lifecycle_state='connected' "
            "WHERE id='a-first'", (self.now.isoformat(),),
        )
        self.engine.conn.execute(
            "UPDATE clients SET agent_version='3.0.0-rc.1', agent_platform='darwin',"
            " agent_heartbeat_at=?,agent_lifecycle_state='disconnected' "
            "WHERE id='b-second'", (self.now.isoformat(),),
        )
        before = self.engine.conn.execute("SELECT COUNT(*) FROM management_jobs").fetchone()[0]
        preview = self.engine.preview_rollout(
            targets=("a-first", "b-second", "z-canary"),
            requested_by="ops-admin", artifact=self.artifact, wave_size=1,
        )
        versions = {x["target_id"]: x for x in preview["target_observations"]}
        self.assertEqual(versions["a-first"]["current_version"], "2.4.0")
        self.assertEqual(versions["a-first"]["platform"], "linux")
        self.assertEqual(versions["a-first"]["version_relation"], "DIFFERENT")
        self.assertEqual(versions["b-second"]["version_relation"], "SAME_VERSION")
        self.assertEqual(versions["z-canary"]["version_relation"], "UNKNOWN")
        self.assertEqual(versions["z-canary"]["current_version"], "unknown")
        self.assertTrue(versions["a-first"]["agent_heartbeat_fresh"])
        self.assertEqual(versions["a-first"]["agent_lifecycle_state"], "connected")
        # A disconnected Host is never considered recent even with a fresh timestamp.
        self.assertFalse(versions["b-second"]["agent_heartbeat_fresh"])
        self.assertFalse(versions["z-canary"]["agent_heartbeat_fresh"])
        for row in versions.values():
            self.assertEqual(row["provenance"], "NOT_VERIFIED")
            self.assertEqual(row["update_available"], "UNKNOWN")
        self.assertEqual(
            self.engine.conn.execute("SELECT COUNT(*) FROM management_jobs").fetchone()[0],
            before,
        )

    def test_preview_rejects_mutable_artifact_and_invalid_canary_without_jobs(self):
        invalid = {"version": "3.0.0", "source_ref": "main", "sha256": "b" * 64}
        with self.assertRaises(ControlPlaneError):
            self.engine.preview_rollout(
                targets=("a-first",), artifact=invalid,
                requested_by="ops-admin", wave_size=1,
            )
        with self.assertRaises(ControlPlaneError):
            self.engine.preview_rollout(
                targets=("a-first",), artifact=self.artifact,
                canary_targets=("unknown-host",), requested_by="ops-admin",
                wave_size=1,
            )
        self.assertEqual(
            self.engine.conn.execute("SELECT COUNT(*) FROM management_jobs").fetchone()[0],
            0,
        )

    def test_preview_surfaces_ineligible_hosts_without_mutation(self):
        plane = ControlPlane(self.tmp.name)
        try:
            plane.conn.execute(
                "UPDATE clients SET admission_state='QUARANTINED' WHERE id='b-second'"
            )
            plane.conn.commit()
            revision = plane.current_revision()
        finally:
            plane.close()
        preview = self.engine.preview_rollout(
            targets=("a-first", "b-second", "z-canary"),
            artifact=self.artifact, wave_size=1,
            requested_by="ops-admin",
        )
        self.assertFalse(preview["eligible"])
        self.assertEqual(preview["blocked_targets"], ["b-second"])
        self.assertEqual(
            self.engine.conn.execute("SELECT COUNT(*) FROM management_jobs").fetchone()[0], 0
        )
        with self.assertRaises(ControlPlaneError):
            self.engine.enqueue_rollout(
                targets=("a-first", "b-second", "z-canary"),
                artifact=self.artifact, wave_size=1, requested_by="ops-admin",
            )
        check = ControlPlane(self.tmp.name, read_only=True)
        try:
            self.assertEqual(check.current_revision(), revision)
        finally:
            check.close()

    def test_generator_canaries_are_materialized_once(self):
        job = self.engine.enqueue_rollout(
            targets=("a-first", "b-second", "z-canary"),
            canary_targets=(target for target in ("z-canary",)),
            requested_by="ops-admin", artifact=self.artifact,
            wave_size=1, now=self.now,
        )
        self.assertEqual(job["payload"]["canary_targets"], ["z-canary"])
        self.assertEqual([c["target_id"] for c in self._claim()], ["z-canary"])

    def test_no_explicit_canary_uses_first_wave_instead_of_parallel_fanout(self):
        job = self.engine.enqueue_rollout(
            targets=("a-first", "b-second", "z-canary"),
            requested_by="ops-admin", artifact=self.artifact,
            wave_size=1, now=self.now,
        )
        self.assertEqual(job["payload"]["canary_targets"], ["a-first"])
        self.assertEqual(job["payload"]["rollout_state"], "CANARY")
        first = self._claim()
        self.assertEqual([c["target_id"] for c in first], ["a-first"])
        self.assertEqual(self._claim(), [])
        self._complete(job, first[0], SUCCEEDED)
        self.assertEqual([c["target_id"] for c in self._claim(3)], ["b-second"])


if __name__ == "__main__":
    unittest.main()
