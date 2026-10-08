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
    CANCELLED, FAILED, QUEUED, SUCCEEDED, ManagementJobEngine,
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

    def test_mutable_source_ref_rejected_even_with_valid_digest(self):
        for ref in ("main", "feature/v3.0-drl3-0", "v3.0.0", "a" * 39, "f" * 41):
            with self.subTest(ref=ref), self.assertRaises(ControlPlaneError):
                self.engine.enqueue_rollout(
                    targets=("a-first",), requested_by="ops-admin",
                    artifact={"version": "3.0.0-rc.1", "source_ref": ref,
                              "sha256": "b" * 64}, wave_size=1, now=self.now,
                )

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
