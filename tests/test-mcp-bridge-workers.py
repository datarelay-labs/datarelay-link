#!/usr/bin/env python3
"""AUD-21 D7: serve the MCP Bridge from several worker processes.

Written before the code (RED). It covers what docs/MCP_BRIDGE_DISPATCH_DESIGN.md
section 3 (D7) and section 6 require:

* ``serve(workers=K)`` runs K Bridge worker processes (and one full-control process) on
  one port and one database; ``workers=1`` stays the current single-process Bridge.
* A revocation made in the database is refused by the next call on every worker.
* A killed worker is restarted; the others keep answering.
* The per-source rate limits are shared by the workers, not multiplied by K and not
  divided by K (dividing would reject legitimate bursts of up to 90 calls).
* Server-local full-control jobs (`server_exec`, `server_job_*`) keep working when the
  runtime lives in one process and the workers reach it over a Unix socket.
* An OAuth refresh token can be redeemed once even when two requests redeem it at the
  same time (the previous code selected, then updated, without claiming the row).

Disposable temp roots and loopback only; no service or credential is touched.
"""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import drlink_mcp_bridge as bridge_mod  # noqa: E402
import drlink_mcp_full_control as full  # noqa: E402
from drlink_control_plane import ControlPlane  # noqa: E402


def _load_e2e_harness():
    path = ROOT / "tests" / "test-ai-access-mcp-e2e.py"
    spec = importlib.util.spec_from_file_location("ai_access_mcp_e2e_harness_workers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_E2E = _load_e2e_harness()
v24 = _E2E.v24


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def children_of(pid: int) -> list[int]:
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat_text = Path("/proc/%s/stat" % entry).read_text()
        except OSError:
            continue
        ppid = int(stat_text.rsplit(")", 1)[1].split()[1])
        if ppid == pid:
            found.append(int(entry))
    return sorted(found)


def http_json(url, token, body, timeout=20):
    """POST one JSON-RPC body on a fresh connection; return (status, payload, worker header)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer %s" % token,
        "MCP-Protocol-Version": _E2E.MCP_PROTOCOL_VERSION,
        "Mcp-Method": "tools/call",
        "Mcp-Name": "list_hosts",
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {}), resp.headers.get("X-DRLink-Worker")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {"raw": raw}
        return exc.code, parsed, exc.headers.get("X-DRLink-Worker")


def list_hosts_body(req_id=1):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {
            "name": "list_hosts",
            "arguments": {},
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": _E2E.MCP_PROTOCOL_VERSION,
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        },
    }


class WorkerSupervisorTests(unittest.TestCase):
    _harness_setup = _E2E.MCPBridgeE2ETests.setUp
    _harness_teardown = _E2E.MCPBridgeE2ETests.tearDown
    _token = _E2E.MCPBridgeE2ETests._token

    def setUp(self):
        patcher = mock.patch.object(_E2E, "start_endpoint_workers", lambda bridge, base: ([], []))
        patcher.start()
        self.addCleanup(patcher.stop)
        self._harness_setup()
        self._supervisors = []

    def tearDown(self):
        for proc in self._supervisors:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except OSError:
                    pass
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
        self._harness_teardown()

    def start_supervisor(self, workers):
        port = free_port()
        code = (
            "import sys; sys.path.insert(0, %r); import drlink_mcp_bridge as b; "
            "b.serve('127.0.0.1', %d, root=%r, workers=%d)" % (str(ROOT / "lib"), port, self.tmp, workers)
        )
        env = dict(os.environ, DRLINK_TEST_ROOT=self.tmp, DRLINK_CONFIRM="yes", PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.Popen([sys.executable, "-c", code], env=env, start_new_session=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._supervisors.append(proc)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                self.fail("supervisor exited early with %s" % proc.returncode)
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=2) as resp:
                    if resp.status == 200:
                        return proc, port
            except OSError:
                time.sleep(0.2)
        self.fail("workers did not answer /healthz")

    def calls(self, port, token, count):
        results = []
        for index in range(count):
            results.append(http_json("http://127.0.0.1:%d/mcp" % port, token, list_hosts_body(index)))
        return results

    def test_single_worker_is_the_current_single_process_bridge(self):
        proc, port = self.start_supervisor(1)
        self.assertEqual(children_of(proc.pid), [], "workers=1 must not fork")
        status, payload, worker = http_json("http://127.0.0.1:%d/mcp" % port, self.cursor, list_hosts_body())
        self.assertEqual(status, 200)
        self.assertIsNone(worker, "no worker header for a single process")
        self.assertIn("lab1", json.dumps(payload))

    def test_k_workers_serve_one_port_and_name_themselves(self):
        proc, port = self.start_supervisor(3)
        # three Bridge workers plus the one full-control process
        self.assertEqual(len(children_of(proc.pid)), 4)
        results = self.calls(port, self.cursor, 45)
        self.assertTrue(all(status == 200 and "lab1" in json.dumps(payload) for status, payload, _ in results))
        seen = {worker for _, _, worker in results}
        self.assertTrue(seen <= {"0", "1", "2"}, seen)
        self.assertGreaterEqual(len(seen), 2, "45 fresh connections reached only one worker: %s" % seen)

    def test_revocation_is_immediate_on_every_worker(self):
        proc, port = self.start_supervisor(3)
        before = self.calls(port, self.cursor, 30)
        self.assertTrue(all("lab1" in json.dumps(payload) for _, payload, _ in before))
        v24.set_ai_access_rule(self.plane, "mcp-lab-maintenance", enabled=False)
        after = self.calls(port, self.cursor, 30)
        self.assertTrue(
            all(status == 200 and "lab1" not in json.dumps(payload) for status, payload, _ in after),
            "a worker still showed the revoked host",
        )
        _E2E.run_cli(self.tmp, ["system", "credential", "revoke", "ai-identity", "cursor-dev"])
        denied = self.calls(port, self.cursor, 30)
        self.assertEqual({status for status, _, _ in denied}, {401})
        self.assertGreaterEqual(len({worker for _, _, worker in denied}), 2)

    def test_a_killed_worker_is_restarted(self):
        proc, port = self.start_supervisor(3)
        before = children_of(proc.pid)
        self.assertEqual(len(before), 4)
        victim = before[1]
        os.kill(victim, signal.SIGKILL)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            now = children_of(proc.pid)
            if len(now) == 4 and victim not in now:
                break
            time.sleep(0.2)
        else:
            self.fail("supervisor did not replace the killed child: %s -> %s" % (before, children_of(proc.pid)))
        results = self.calls(port, self.cursor, 20)
        self.assertTrue(all(status == 200 for status, _, _ in results))

    def test_stopping_the_supervisor_stops_every_child(self):
        proc, port = self.start_supervisor(3)
        kids = children_of(proc.pid)
        self.assertEqual(len(kids), 4)
        os.kill(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(Path("/proc/%d" % kid).exists() for kid in kids):
            time.sleep(0.1)
        self.assertFalse([kid for kid in kids if Path("/proc/%d" % kid).exists()], "children outlived the supervisor")


class SharedRateLimiterTests(unittest.TestCase):
    def test_workers_share_one_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "rate.sqlite")
            workers = [bridge_mod.SharedRateLimiter(path) for _ in range(3)]
            outcomes = []
            for index in range(40):
                outcomes.append(workers[index % 3].limited("post:src", limit=30, window_s=60))
            self.assertEqual(outcomes.count(False), 30, "exactly the first 30 hits are within the limit")
            self.assertTrue(all(outcomes[30:]))
            # another source has its own budget
            self.assertFalse(workers[0].limited("post:other", limit=30, window_s=60))

    def test_window_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            limiter = bridge_mod.SharedRateLimiter(os.path.join(directory, "rate.sqlite"))
            self.assertFalse(limiter.limited("k", limit=1, window_s=1, now=1000.0))
            self.assertTrue(limiter.limited("k", limit=1, window_s=1, now=1000.5))
            self.assertFalse(limiter.limited("k", limit=1, window_s=1, now=1001.5))

    def test_concurrent_hits_never_exceed_the_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "rate.sqlite")
            allowed = []
            guard = threading.Lock()

            def hammer():
                limiter = bridge_mod.SharedRateLimiter(path)
                for _ in range(20):
                    if not limiter.limited("burst", limit=50, window_s=60):
                        with guard:
                            allowed.append(1)

            threads = [threading.Thread(target=hammer) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            self.assertEqual(len(allowed), 50)


class FullControlOverSocketTests(unittest.TestCase):
    def setUp(self):
        import pwd

        account = pwd.getpwuid(os.geteuid())
        self.dir = tempfile.mkdtemp(prefix="drlink-fc-test-")
        os.chmod(self.dir, 0o700)
        self.work = Path(tempfile.mkdtemp(prefix="drlink-fc-work-")).resolve()
        self.flags = mock.patch.dict(os.environ, {
            "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
            "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1",
            "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED": "1",
            "DRLINK_MCP_SERVER_EXEC_USER": account.pw_name,
            "DRLINK_MCP_SERVER_ALLOWED_ROOTS": str(self.work),
            "DRLINK_MCP_SERVER_ADMIN_ENABLED": "1" if os.geteuid() == 0 else "0",
        })
        self.flags.start()
        self.runtime = full.FullControlRuntime()
        self.path = os.path.join(self.dir, "fullcontrol.sock")
        self.server = full.serve_full_control(self.path, self.runtime)
        self.patterns = [str(self.work) + "/**"]
        self.owner = "ai-owner-1"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.runtime.close()
        self.flags.stop()
        import shutil

        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.work, ignore_errors=True)

    def test_socket_is_private(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_a_job_started_through_one_worker_is_polled_and_stopped_through_another(self):
        worker_a = full.RemoteFullControlRuntime(self.path)
        worker_b = full.RemoteFullControlRuntime(self.path)
        started = worker_a.start(self.owner, {"cwd": str(self.work), "argv": ["sleep", "30"], "wait_ms": 0}, self.patterns)
        job = started["job_id"]
        self.assertEqual(started["state"], "running")
        self.assertEqual(worker_b.context(self.owner, job), str(self.work))
        polled = worker_b.poll(self.owner, job, wait_ms=0)
        self.assertEqual(polled["job_id"], job)
        stopped = worker_b.stop(self.owner, job)
        self.assertEqual(stopped["state"], "completed")

    def test_input_and_output_round_trip(self):
        worker_a = full.RemoteFullControlRuntime(self.path)
        worker_b = full.RemoteFullControlRuntime(self.path)
        started = worker_a.start(self.owner, {"cwd": str(self.work), "argv": ["cat"], "wait_ms": 0}, self.patterns)
        job = started["job_id"]
        sent = worker_b.send(self.owner, job, "hello\n", eof=True)
        self.assertTrue(sent["input_closed"])
        done = worker_a.poll(self.owner, job, wait_ms=3000)
        self.assertEqual(done["state"], "completed")
        self.assertIn("hello", json.dumps(done["stdout"]))

    def test_ownership_and_denials_cross_the_socket_unchanged(self):
        worker = full.RemoteFullControlRuntime(self.path)
        job = worker.start(self.owner, {"cwd": str(self.work), "argv": ["sleep", "30"], "wait_ms": 0}, self.patterns)["job_id"]
        try:
            with self.assertRaises(full.FullControlDenied):
                worker.poll("someone-else", job)
            with self.assertRaises(full.FullControlDenied):
                worker.start(self.owner, {"cwd": "/", "argv": ["true"]}, self.patterns)
            with self.assertRaises(full.FullControlDenied):
                worker.start("", {"cwd": str(self.work), "argv": ["true"]}, self.patterns)
        finally:
            worker.stop(self.owner, job)

    def test_the_bridge_uses_the_shared_runtime_only_when_workers_run(self):
        bridge = bridge_mod.MCPBridge(root=self.dir, plane=mock.MagicMock())
        with mock.patch.dict(os.environ, {"DRLINK_MCP_FULLCONTROL_SOCKET": self.path}):
            shared = bridge._full_control_runtime(full)
            self.assertIsInstance(shared, full.RemoteFullControlRuntime)
            self.assertIs(bridge._full_control_runtime(full), shared)
        env = dict(os.environ)
        env.pop("DRLINK_MCP_FULLCONTROL_SOCKET", None)
        with mock.patch.dict(os.environ, env, clear=True):
            local = bridge._full_control_runtime(full)
            self.assertIsInstance(local, full.FullControlRuntime)
            self.assertIs(bridge._full_control_runtime(full), local)
            local.close()

    def test_an_unreachable_runtime_fails_closed(self):
        missing = full.RemoteFullControlRuntime(os.path.join(self.dir, "absent.sock"))
        with self.assertRaises(full.FullControlDenied):
            missing.poll(self.owner, "sj_none")


class OAuthRefreshTokenRaceTests(unittest.TestCase):
    """Two requests redeeming one refresh token at once must not both succeed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-oauth-race-")
        os.environ["DRLINK_TEST_ROOT"] = self.tmp
        self.plane = ControlPlane(self.tmp)
        self.plane.set_ai_principal("race-id", enabled=True)
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status = 'active', enabled = 1 WHERE name = 'race-id'"
        )
        self.plane.conn.commit()
        self.principal_id = self.plane.get_principal("race-id")["id"]

    def tearDown(self):
        self.plane.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def issue_refresh(self):
        issued = self.plane.issue_oauth_access_token(
            principal_id=self.principal_id,
            client_id="race-client",
            resource="https://example.invalid/mcp",
            include_refresh=True,
            scope="drlink.ai offline_access",
        )
        return issued["refresh_token"]

    def test_sequential_reuse_is_refused(self):
        refresh = self.issue_refresh()
        first = self.plane.exchange_refresh_token(
            refresh_token=refresh, client_id="race-client", resource="https://example.invalid/mcp")
        self.assertIsNotNone(first)
        again = self.plane.exchange_refresh_token(
            refresh_token=refresh, client_id="race-client", resource="https://example.invalid/mcp")
        self.assertIsNone(again)

    def test_concurrent_redemption_succeeds_exactly_once(self):
        refresh = self.issue_refresh()
        results = []
        guard = threading.Lock()
        barrier = threading.Barrier(4)

        def widen_the_window(statement):
            # The statement that follows the validating SELECT starts here; holding it back
            # lets every racing request finish its SELECT first, which is the interleaving
            # that two processes can produce at any time.
            if statement.lstrip().startswith("UPDATE ai_oauth_tokens SET revoked_at"):
                time.sleep(0.3)

        def redeem():
            with self.plane.request_scope():
                connection = self.plane.conn
                connection.set_trace_callback(widen_the_window)
                try:
                    barrier.wait(timeout=10)
                    outcome = self.plane.exchange_refresh_token(
                        refresh_token=refresh, client_id="race-client", resource="https://example.invalid/mcp")
                finally:
                    connection.set_trace_callback(None)
            with guard:
                results.append(outcome)

        threads = [threading.Thread(target=redeem) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(len(results), 4)
        self.assertEqual(sum(1 for item in results if item is not None), 1, "refresh token redeemed more than once")


if __name__ == "__main__":
    unittest.main()
