#!/usr/bin/env python3
"""AUD-21: an idle Agent must pick up a newly queued job promptly.

Characterization test for the dispatch latency measured on main: end-to-end
`exec` p50 was 62 ms but p95 was 2.03 s, while the bridge-side cost per call
(authorization, audit write, result poll) is about 2 ms in total. The tail comes
from the Agent claim loop: after a job it polls every 0.05 s once, then waits
`AI_AGENT_IDLE_POLL_SECONDS` (2.0 s) between claims, and `/agent/v1/claim`
returns immediately instead of waiting for work.

Each call below is sent `SETTLE_SECONDS` after the previous one finished, which
is longer than the busy poll and shorter than the idle poll, so the Agent is
always inside its idle wait. A connected Agent should pick the job up in well
under a second regardless of that wait.

Known RED on main. Not registered in run-fast-pr.sh/run-all.sh on purpose; it is
registered by the change that makes claim wake on enqueue (see
docs/MCP_BRIDGE_DISPATCH_DESIGN.md). Disposable temp root, real ControlPlane,
real HTTP server and real AgentLoop worker; no service or credential is touched.
"""
from __future__ import annotations

import importlib.util
import statistics
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import drlink_ai_agent  # noqa: E402


def _load_e2e_harness():
    path = ROOT / "tests" / "test-ai-access-mcp-e2e.py"
    spec = importlib.util.spec_from_file_location("ai_access_mcp_e2e_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_E2E = _load_e2e_harness()


class MCPAgentDispatchLatencyTests(unittest.TestCase):
    # Borrow the harness plumbing without inheriting (and re-running) its tests.
    setUp = _E2E.MCPBridgeE2ETests.setUp
    tearDown = _E2E.MCPBridgeE2ETests.tearDown
    _token = _E2E.MCPBridgeE2ETests._token
    call = _E2E.MCPBridgeE2ETests.call
    text_of = _E2E.MCPBridgeE2ETests.text_of

    CALLS = 6
    WARMUP_CALLS = 2
    SETTLE_SECONDS = 0.4
    TARGET_MEDIAN_SECONDS = 0.25

    def _exec(self, marker):
        started = time.perf_counter()
        status, payload = self.call(
            self.cursor,
            "exec",
            {"endpoint": "lab1", "command": "echo %s" % marker},
        )
        elapsed = time.perf_counter() - started
        self.assertEqual(status, 200, marker)
        self.assertNotIn("error", payload, "%s: %s" % (marker, payload))
        self.assertIn(marker, self.text_of(payload))
        return elapsed

    def test_idle_agent_picks_up_new_job_promptly(self):
        # Guard: the settle gap must keep the Agent in its idle wait.
        self.assertGreater(self.SETTLE_SECONDS, drlink_ai_agent.AI_AGENT_BUSY_POLL_SECONDS)
        for index in range(self.WARMUP_CALLS):
            self._exec("warm-%d" % index)
        latencies = []
        for index in range(self.CALLS):
            time.sleep(self.SETTLE_SECONDS)
            latencies.append(self._exec("idle-%d" % index))
        median = statistics.median(latencies)
        self.assertLessEqual(
            median,
            self.TARGET_MEDIAN_SECONDS,
            "idle pickup median %.0f ms exceeds %.0f ms (calls ms=%s; Agent idle poll=%.1fs)"
            % (
                median * 1000,
                self.TARGET_MEDIAN_SECONDS * 1000,
                [round(v * 1000) for v in latencies],
                drlink_ai_agent.AI_AGENT_IDLE_POLL_SECONDS,
            ),
        )


if __name__ == "__main__":
    unittest.main()
