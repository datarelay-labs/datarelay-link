#!/usr/bin/env python3
"""AUD-21 D6: per-job latency metrics for MCP Bridge endpoint dispatch.

Each dispatched job records `queue_ms` (enqueue to claim), `run_ms` (claim to
completion) and `total_ms` (enqueue to completion) and keeps the correlation id
of its intent audit row (D4), so a slow call can be traced from the audit log
to the job and split into waiting for an Agent and running on it
(docs/MCP_BRIDGE_DISPATCH_DESIGN.md, section 3).
"""
from __future__ import annotations

import json
import unittest

from mcp_dispatch_fixture import DispatchFixture

AGENT_DELAY_S = 0.25


class JobMetricsTests(DispatchFixture):
    agent_delay = AGENT_DELAY_S

    def test_completed_job_records_queue_run_and_total_ms(self):
        status, body = self.rpc_exec()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body["result"]["content"][0]["text"])["result"], "ALLOW")
        jobs = self.jobs()
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        for key in ("queue_ms", "run_ms", "total_ms"):
            self.assertIsInstance(job[key], int, key)
            self.assertGreaterEqual(job[key], 0, key)
        # The fake Agent sleeps between claim and completion: that is run time.
        self.assertGreaterEqual(job["run_ms"], int(AGENT_DELAY_S * 1000) - 5)
        self.assertLess(job["queue_ms"], job["run_ms"])
        self.assertEqual(job["total_ms"], job["queue_ms"] + job["run_ms"])

    def test_job_keeps_the_correlation_id_of_its_audit_rows(self):
        self.rpc_exec()
        job = self.jobs()[0]
        rows = self.activity()
        self.assertTrue(job["correlation_id"].startswith("mcp-"))
        self.assertEqual({row["correlation_id"] for row in rows}, {job["correlation_id"]})

    def test_queued_job_has_no_run_metrics_yet(self):
        self._stop.set()
        self._agent.join(timeout=5)
        job_id = self.plane.enqueue_ai_job(
            principal_id=self.principal["id"], endpoint_object_id="obj", client_id="nobody",
            capability="exec", arguments={}, patterns=[], timeout=5, correlation_id="mcp-test",
        )
        job = self.plane.get_ai_job(job_id)
        self.assertEqual(job["correlation_id"], "mcp-test")
        self.assertIsNone(job["queue_ms"])
        self.assertIsNone(job["run_ms"])
        self.assertIsNone(job["total_ms"])


if __name__ == "__main__":
    unittest.main()
