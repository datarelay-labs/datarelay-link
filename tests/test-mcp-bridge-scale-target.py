#!/usr/bin/env python3
"""AUD-21: the MCP Bridge must hold the product scale target.

Product target: up to 100 managed hosts (Agents) and about 30 simultaneous AI
calls. This characterization test runs 100 real AgentLoop workers against the
real bridge in a disposable temp root and checks two things.

1. Idle load: 100 idle Agents must not drive the Server with a constant stream of
   claim requests. On main every Agent claims every AI_AGENT_IDLE_POLL_SECONDS
   (2.0 s), about 44-47 claims per second.
2. Simultaneous calls: 30 valid `exec` calls released at the same instant, three
   rounds, must all succeed quickly. On main 34 and 50 of 90 failed in two runs
   (`-32603` and connection resets) and the successful ones took about 2.1 s.

Not registered in run-fast-pr.sh/run-all.sh (orphan allowlist) on purpose: after
steps 1 and 2 the idle-load test is GREEN (100 Agents, held claim) and the 30
simultaneous calls all succeed, but their p95 is still above the 500 ms target
(see docs/MCP_BRIDGE_DISPATCH_DESIGN.md). It is registered when that test is GREEN.
The Agents run with the held claim the production Agent uses (`DEFAULT_CLAIM_WAIT_MS`
is switched on for the test only). No service or credential is touched.
"""
from __future__ import annotations

import importlib.util
import statistics
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import drlink_ai_agent  # noqa: E402
from drlink_ai_agent import AgentLoop  # noqa: E402


def _load_e2e_harness():
    path = ROOT / "tests" / "test-ai-access-mcp-e2e.py"
    spec = importlib.util.spec_from_file_location("ai_access_mcp_e2e_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_E2E = _load_e2e_harness()

TARGET_AGENTS = 100
TARGET_CONCURRENT_CALLS = 30
ROUNDS = 3
MAX_IDLE_CLAIMS_PER_SECOND = 10.0
MAX_P95_SECONDS = 0.5


class MCPBridgeScaleTargetTests(unittest.TestCase):
    # Borrow the harness plumbing without inheriting (and re-running) its tests.
    _harness_setup = _E2E.MCPBridgeE2ETests.setUp
    _harness_teardown = _E2E.MCPBridgeE2ETests.tearDown
    _token = _E2E.MCPBridgeE2ETests._token
    call = _E2E.MCPBridgeE2ETests.call
    text_of = _E2E.MCPBridgeE2ETests.text_of

    # The Agents hold each empty claim for this long (production holds 25 s).
    # 100 Agents / 15 s is about 6.7 claim requests per second.
    HELD_WAIT_MS = 15000

    def tearDown(self):
        # Workers sit inside a held claim; let them finish it before the harness
        # joins them with its own short timeout.
        for stop in getattr(self, "_agent_stops", []):
            stop.set()
        for thread in getattr(self, "_agent_threads", []):
            thread.join(timeout=self.HELD_WAIT_MS / 1000.0 + 5.0)
        self._harness_teardown()

    def setUp(self):
        patcher = mock.patch.object(drlink_ai_agent, "DEFAULT_CLAIM_WAIT_MS", self.HELD_WAIT_MS)
        patcher.start()
        self.addCleanup(patcher.stop)
        self._harness_setup()
        plane = self.bridge.plane
        # The harness already runs two hosts; add the rest of the target fleet.
        for index in range(TARGET_AGENTS - 2):
            plane.upsert_client("client-scale-%03d-xxxxxxxx" % index, label="scale%03d" % index)
        for client in plane.connected_clients():
            if "client-scale-" not in client["id"]:
                continue
            token = plane.issue_agent_credential(client["id"], rotate=True)
            stop = threading.Event()
            loop = AgentLoop(self.base, token, stop_event=stop)
            thread = threading.Thread(target=loop.run, daemon=True, name="scale-agent-%s" % client["id"][13:16])
            thread.start()
            self._agent_stops.append(stop)
            self._agent_threads.append(thread)
        self.assertEqual(len(self._agent_threads), TARGET_AGENTS)

    def test_idle_fleet_does_not_flood_the_server_with_claims(self):
        plane = self.bridge.plane
        counter = {"claims": 0}
        original = plane.claim_ai_jobs

        def counted(*args, **kwargs):
            counter["claims"] += 1
            return original(*args, **kwargs)

        plane.claim_ai_jobs = counted
        time.sleep(3.0)  # let every Agent settle into its idle behaviour
        counter["claims"] = 0
        started = time.perf_counter()
        # One full hold period, so every Agent's re-claim is counted exactly once
        # whatever the phase of its hold.
        time.sleep(self.HELD_WAIT_MS / 1000.0 + 1.0)
        rate = counter["claims"] / (time.perf_counter() - started)
        self.assertLessEqual(
            rate,
            MAX_IDLE_CLAIMS_PER_SECOND,
            "%d idle Agents produced %.1f claim requests/s (limit %.0f/s)"
            % (TARGET_AGENTS, rate, MAX_IDLE_CLAIMS_PER_SECOND),
        )

    def test_thirty_simultaneous_calls_all_succeed_quickly(self):
        """Worst case: all 30 calls target ONE host (served one after another)."""
        self._simultaneous_calls(lambda index: "lab1")

    def test_thirty_calls_spread_over_thirty_hosts_all_succeed_quickly(self):
        """Expected load: 30 simultaneous calls, each to a different host."""
        v24 = _E2E.v24
        for index in range(TARGET_CONCURRENT_CALLS):
            label = "scale%03d" % index
            rule = "mcp-scale-%03d" % index
            v24.set_ai_access_rule(
                self.plane,
                rule,
                mode="whitelist",
                source="cursor-dev",
                destination=label,
                permission="lab-maintenance-perms",
                enabled=True,
                oneshot=True,
            )
            v24.set_ai_policy_path_scopes(
                self.plane, rule, [self.etc_glob, self.opt_glob, self.vendor_glob]
            )
        self._simultaneous_calls(lambda index: "scale%03d" % index)

    def _simultaneous_calls(self, endpoint_of):
        results = []
        guard = threading.Lock()
        barrier = threading.Barrier(TARGET_CONCURRENT_CALLS)

        def worker(index):
            for rnd in range(ROUNDS):
                marker = "scale-%d-%d" % (index, rnd)
                try:
                    barrier.wait(timeout=60)
                    started = time.perf_counter()
                    status, payload = self.call(
                        self.cursor,
                        "exec",
                        {"endpoint": endpoint_of(index), "command": "echo %s" % marker},
                        req_id=index * 100 + rnd,
                    )
                    elapsed = time.perf_counter() - started
                    failed = status != 200 or "error" in payload or marker not in self.text_of(payload)
                    outcome = (elapsed, None if not failed else (payload.get("error") or {}).get("code", "bad-result"))
                except Exception as exc:  # connection reset, timeout, ...
                    outcome = (None, "transport:%s" % type(exc).__name__)
                with guard:
                    results.append(outcome)

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True)
            for i in range(TARGET_CONCURRENT_CALLS)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=180)
        total = TARGET_CONCURRENT_CALLS * ROUNDS
        failures = [code for _, code in results if code is not None]
        self.assertEqual(
            (len(results), len(failures)),
            (total, 0),
            "%d of %d simultaneous calls failed: %s"
            % (len(failures) + (total - len(results)), total, sorted(set(map(str, failures)))),
        )
        durations = sorted(d for d, _ in results if d is not None)
        p95 = durations[min(len(durations) - 1, int(round(0.95 * (len(durations) - 1))))]
        self.assertLessEqual(
            p95,
            MAX_P95_SECONDS,
            "p95 %.0f ms exceeds %.0f ms (median %.0f ms)"
            % (p95 * 1000, MAX_P95_SECONDS * 1000, statistics.median(durations) * 1000),
        )


if __name__ == "__main__":
    unittest.main()
