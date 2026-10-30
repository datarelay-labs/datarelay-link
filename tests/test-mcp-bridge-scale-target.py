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

By default the Bridge and all 100 Agents share ONE Python process (one GIL), which
production never does. `SCALE_AGENT_PROCS=N` hosts the Agent fleet in N child
processes instead (they still talk to the Bridge over loopback HTTP), so the
Bridge process is measured on its own. `SCALE_SERVER_PROCS=M` (needs SCALE_AGENT_PROCS)
additionally serves the Agent-facing `/agent/v1/*` endpoints from M child processes on the
same database, like production where the Agents talk to the allocator and not to the Bridge;
the caller-facing Bridge stays in the test process. `SCALE_BRIDGE_PROCS=K` instead serves
Bridge requests (callers and Agents) with the product code `drlink_mcp_bridge.serve(workers=K)`:
K worker processes sharing one port (SO_REUSEPORT) and one database. Every run prints one `SCALE_METRICS` line
with the latency percentiles and the CPU the test process (Bridge + the callers)
used while the calls ran. `SCALE_CALLS=N` changes the number of simultaneous calls (default 30).
"""
from __future__ import annotations

import importlib.util
import json
import os
import resource
import statistics
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import drlink_ai_agent  # noqa: E402
from drlink_ai_agent import AgentLoop  # noqa: E402


def _agent_child_main() -> None:
    """Host a slice of the Agent fleet in this process (spec arrives on stdin)."""
    spec = json.loads(sys.stdin.readline())
    drlink_ai_agent.DEFAULT_CLAIM_WAIT_MS = int(spec["held_wait_ms"])
    stops, threads = [], []
    for token in spec["tokens"]:
        stop = threading.Event()
        loop = AgentLoop(spec["base"], token, stop_event=stop)
        thread = threading.Thread(target=loop.run, daemon=True)
        thread.start()
        stops.append(stop)
        threads.append(thread)
    print("READY %d" % len(threads), flush=True)
    sys.stdin.read()  # the parent closing the pipe is the stop signal
    for stop in stops:
        stop.set()
    for thread in threads:
        thread.join(timeout=int(spec["held_wait_ms"]) / 1000.0 + 5.0)


def _agent_server_child_main() -> None:
    """Serve the Agent-facing endpoints from this process on the shared test database."""
    spec = json.loads(sys.stdin.readline())
    os.environ["DRLINK_TEST_ROOT"] = spec["root"]
    os.environ["DRLINK_CONFIRM"] = "yes"
    from drlink_control_plane import ControlPlane
    from drlink_mcp_bridge import MCPBridge, ThreadingHTTPServer, make_handler

    class _Server(ThreadingHTTPServer):
        allow_reuse_port = bool(spec.get("port"))

    plane = ControlPlane(spec["root"])
    bridge = MCPBridge(root=spec["root"], plane=plane, auto_agents=False)
    httpd = _Server(("127.0.0.1", int(spec.get("port") or 0)), make_handler(bridge))
    bridge.listen_host = "127.0.0.1"
    bridge.listen_port = httpd.server_address[1]
    serving = threading.Thread(target=httpd.serve_forever, daemon=True)
    serving.start()
    print("PORT %d" % httpd.server_address[1], flush=True)
    sys.stdin.read()  # the parent closing the pipe is the stop signal
    httpd.shutdown()
    httpd.server_close()
    bridge.close()
    plane.close()


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--agent-child":
    _agent_child_main()
    sys.exit(0)
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--agent-server-child":
    _agent_server_child_main()
    sys.exit(0)


def _load_e2e_harness():
    path = ROOT / "tests" / "test-ai-access-mcp-e2e.py"
    spec = importlib.util.spec_from_file_location("ai_access_mcp_e2e_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_E2E = _load_e2e_harness()

TARGET_AGENTS = 100
TARGET_CONCURRENT_CALLS = int(os.environ.get("SCALE_CALLS", "30") or 30)  # SCALE_CALLS=N: measure fewer simultaneous calls
ROUNDS = 3
MAX_IDLE_CLAIMS_PER_SECOND = 10.0
MAX_P95_SECONDS = 0.5
AGENT_PROCS = int(os.environ.get("SCALE_AGENT_PROCS", "0") or 0)
SERVER_PROCS = int(os.environ.get("SCALE_SERVER_PROCS", "0") or 0)
BRIDGE_PROCS = int(os.environ.get("SCALE_BRIDGE_PROCS", "0") or 0)


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
        procs = getattr(self, "_agent_procs", [])
        for proc in procs:  # stop signal to every child first, so they wind down in parallel
            try:
                proc.stdin.close()
            except Exception:
                pass
        for proc in procs:
            try:
                proc.wait(timeout=self.HELD_WAIT_MS / 1000.0 + 15.0)
            except Exception:
                proc.kill()
                proc.wait(timeout=10)
        supervisor = getattr(self, "_bridge_supervisor", None)
        if supervisor is not None:
            for proc in getattr(self, "_agent_procs", []):
                try:
                    proc.wait(timeout=self.HELD_WAIT_MS / 1000.0 + 15.0)
                except Exception:
                    proc.kill()
            try:
                os.killpg(supervisor.pid, 15)
                supervisor.wait(timeout=20)
            except Exception:
                try:
                    os.killpg(supervisor.pid, 9)
                except OSError:
                    pass
        server_procs = getattr(self, "_server_procs", [])
        for proc in server_procs:  # the fleet is gone, so the Agent-facing servers can stop
            try:
                proc.stdin.close()
            except Exception:
                pass
        for proc in server_procs:
            try:
                proc.wait(timeout=20)
            except Exception:
                proc.kill()
                proc.wait(timeout=10)
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
        if AGENT_PROCS:
            # The harness would start its two endpoint Agents as threads of this
            # process; they join the external fleet below instead.
            external = mock.patch.object(_E2E, "start_endpoint_workers", lambda bridge, base: ([], []))
            external.start()
            self.addCleanup(external.stop)
        self._harness_setup()
        plane = self.bridge.plane
        # The harness already runs two hosts; add the rest of the target fleet.
        for index in range(TARGET_AGENTS - 2):
            plane.upsert_client("client-scale-%03d-xxxxxxxx" % index, label="scale%03d" % index)
        if AGENT_PROCS:
            self._start_agent_processes()
            return
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

    def _start_agent_processes(self):
        plane = self.bridge.plane
        tokens = [
            plane.issue_agent_credential(client["id"], rotate=True)
            for client in plane.connected_clients()
        ]
        self.assertEqual(len(tokens), TARGET_AGENTS)
        self._server_procs = []
        if BRIDGE_PROCS:
            # The product code: serve(workers=K) forks K Bridge workers (and the full-control
            # process) on one port and the same database as this test.
            import socket
            import urllib.error

            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            shared_port = probe.getsockname()[1]
            probe.close()
            code = (
                "import sys; sys.path.insert(0, %r); import drlink_mcp_bridge as b; "
                "b.serve('127.0.0.1', %d, root=%r, workers=%d)"
                % (str(ROOT / "lib"), shared_port, self.tmp, BRIDGE_PROCS)
            )
            supervisor = subprocess.Popen(
                [sys.executable, "-c", code],
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._bridge_supervisor = supervisor
            deadline = time.monotonic() + 60
            while True:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:%d/healthz" % shared_port, timeout=2) as resp:
                        if resp.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                self.assertIsNone(supervisor.poll(), "the Bridge supervisor exited")
                self.assertLess(time.monotonic(), deadline, "the Bridge workers did not start")
                time.sleep(0.2)
            time.sleep(2.0)  # let every worker finish its warm-up and bind
            self.base = "http://127.0.0.1:%d" % shared_port  # callers and Agents use the workers
            self.url = self.base + "/mcp"
        bases = [self.base]
        if SERVER_PROCS:
            bases = []
            for _ in range(SERVER_PROCS):
                server = subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), "--agent-server-child"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                )
                self._server_procs.append(server)
                server.stdin.write(json.dumps({"root": self.tmp}) + "\n")
                server.stdin.flush()
                line = server.stdout.readline().strip()
                self.assertTrue(line.startswith("PORT "), line)
                bases.append("http://127.0.0.1:%s" % line.split()[1])
        self._agent_procs = []
        for index in range(AGENT_PROCS):
            share = tokens[index::AGENT_PROCS]
            proc = subprocess.Popen(
                [sys.executable, os.path.abspath(__file__), "--agent-child"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            )
            self._agent_procs.append(proc)
            spec = {"base": bases[index % len(bases)], "tokens": share, "held_wait_ms": self.HELD_WAIT_MS}
            proc.stdin.write(json.dumps(spec) + "\n")
            proc.stdin.flush()
        for proc in self._agent_procs:
            self.assertTrue(proc.stdout.readline().startswith("READY"))
        time.sleep(3.0)  # let every Agent settle into its held claim

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
        by_round = {}
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
                    if outcome[0] is not None:
                        by_round.setdefault(rnd, []).append(outcome[0])

        # urllib builds its default opener (and loads the system CA bundle, about 100 ms of CPU)
        # on the first urlopen() of the process. 30 callers released at the same instant each
        # built their own, which made the first round look slow. Real clients keep their opener,
        # so build it once before the burst and measure the Server only.
        urllib.request.install_opener(urllib.request.build_opener())
        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True)
            for i in range(TARGET_CONCURRENT_CALLS)
        ]
        mark = os.environ.get("SCALE_BURST_MARK")
        if mark:  # lets a profiler attach exactly for the burst
            Path(mark).write_text("start\n")
        cpu_started = time.process_time()
        ru_started = resource.getrusage(resource.RUSAGE_SELF)
        wall_started = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=180)
        cpu_used = time.process_time() - cpu_started
        if mark:
            Path(mark).write_text("end\n")
        ru_ended = resource.getrusage(resource.RUSAGE_SELF)
        wall_used = time.perf_counter() - wall_started
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
        def _pct(values, q):
            values = sorted(values)
            return values[min(len(values) - 1, int(round(q * (len(values) - 1))))] * 1000

        rounds_text = " ".join(
            "r%d=%.0f/%.0f" % (rnd + 1, _pct(vals, 0.5), _pct(vals, 0.95)) for rnd, vals in sorted(by_round.items())
        )
        print(
            "SCALE_METRICS rounds(median/p95 ms)[%s] agent_procs=%d server_procs=%d bridge_procs=%d calls=%d median_ms=%.0f p95_ms=%.0f max_ms=%.0f "
            "test_process_cpu_s=%.2f (user %.2f sys %.2f) wall_s=%.2f cpu_per_call_ms=%.0f "
            "ctx_voluntary=%d ctx_involuntary=%d"
            % (
                rounds_text,
                AGENT_PROCS,
                SERVER_PROCS,
                BRIDGE_PROCS,
                len(durations),
                statistics.median(durations) * 1000,
                p95 * 1000,
                durations[-1] * 1000,
                cpu_used,
                ru_ended.ru_utime - ru_started.ru_utime,
                ru_ended.ru_stime - ru_started.ru_stime,
                wall_used,
                cpu_used / max(1, len(durations)) * 1000,
                ru_ended.ru_nvcsw - ru_started.ru_nvcsw,
                ru_ended.ru_nivcsw - ru_started.ru_nivcsw,
            ),
            file=sys.stderr,
            flush=True,
        )
        self.assertLessEqual(
            p95,
            MAX_P95_SECONDS,
            "p95 %.0f ms exceeds %.0f ms (median %.0f ms)"
            % (p95 * 1000, MAX_P95_SECONDS * 1000, statistics.median(durations) * 1000),
        )


if __name__ == "__main__":
    unittest.main()
