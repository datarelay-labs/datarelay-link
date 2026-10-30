#!/usr/bin/env python3
"""AUD-21 step 2b: a held claim answers the moment a job is queued.

Covers the pieces below the HTTP layer so each can fail on its own:

* ``ControlPlane.claim_ai_jobs_held`` returns as soon as another connection
  queues a job for that host, returns [] after ``wait_ms`` when nothing arrives,
  never waits for another host's job, and caps ``wait_ms``.
* ``frp_bounded_server.parked_slot`` gives the request slot back while a claim
  waits (so 100 held claims cannot starve ``complete`` and enrollment), takes it
  again before the caller touches the database, and refuses above its own cap.
* The management API route ``POST /v1/ai-jobs/claim`` honours ``wait_ms``.

Disposable temp roots only; no service or credential is touched.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_bounded_server as BOUNDED  # noqa: E402
from drlink_control_plane import ControlPlane  # noqa: E402
import drlink_control_plane as CP  # noqa: E402

MACHINE_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
MACHINE_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _load_job_safety():
    import importlib.util

    path = ROOT / "tests" / "test-v24-ai-job-safety.py"
    spec = importlib.util.spec_from_file_location("ai_job_safety_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SAFETY = _load_job_safety()


class HeldClaimPlaneTests(unittest.TestCase):
    # Reuse the AI-job harness (server root, two enrolled hosts, rules) without
    # inheriting and re-running its tests.
    setUp = _SAFETY.AiJobSafetyTests.setUp
    _enqueue_with_timeout = _SAFETY.AiJobSafetyTests._enqueue_with_timeout

    def tearDown(self):
        for stop in self._stops:
            stop.set()
        try:
            self.bridge.close()
        except Exception:
            pass
        try:
            _SAFETY.mgmt.stop_mgmt_server(self.mgmt_httpd)
        except Exception:
            pass
        for tmp in (self.server_tmp, self.agent_a_tmp, self.agent_b_tmp):
            shutil.rmtree(tmp, ignore_errors=True)

    def _enqueue_from_other_connection(self, machine, delay):
        ids = []

        def run():
            time.sleep(delay)
            other = ControlPlane(self.server_tmp)
            try:
                job_id = other.enqueue_ai_job(
                    principal_id=self.principal["id"],
                    endpoint_object_id="ep-%s" % machine[:8],
                    client_id=machine,
                    capability="read_file",
                    arguments={"path": str(self.agent_a_root / "AGENT_MARKER")},
                    patterns=[str(self.agent_a_root) + "/**", str(self.agent_b_root) + "/**"],
                    timeout=60,
                )
                ids.append(job_id)
            finally:
                other.close()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, ids

    def test_held_claim_returns_when_a_job_is_queued(self):
        thread, ids = self._enqueue_from_other_connection(MACHINE_A, 0.3)
        started = time.monotonic()
        jobs = self.plane.claim_ai_jobs_held(MACHINE_A, 4, wait_ms=5000)
        elapsed = time.monotonic() - started
        thread.join(2.0)
        self.assertEqual([j["id"] for j in jobs], ids)
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertLess(elapsed, 0.8, "claim must follow the enqueue within milliseconds")

    def test_held_claim_times_out_empty(self):
        started = time.monotonic()
        jobs = self.plane.claim_ai_jobs_held(MACHINE_A, 4, wait_ms=300)
        elapsed = time.monotonic() - started
        self.assertEqual(jobs, [])
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertLess(elapsed, 1.0)

    def test_held_claim_ignores_jobs_for_other_hosts(self):
        thread, _ = self._enqueue_from_other_connection(MACHINE_B, 0.1)
        jobs = self.plane.claim_ai_jobs_held(MACHINE_A, 4, wait_ms=500)
        thread.join(2.0)
        self.assertEqual(jobs, [])

    def test_zero_wait_is_the_old_immediate_claim(self):
        started = time.monotonic()
        self.assertEqual(self.plane.claim_ai_jobs_held(MACHINE_A, 4, wait_ms=0), [])
        self.assertLess(time.monotonic() - started, 0.2)

    def test_wait_ms_is_capped(self):
        self.assertEqual(CP.MAX_CLAIM_WAIT_MS, 25000)
        self.assertEqual(CP.clamp_claim_wait_ms(10 ** 9), 25000)
        self.assertEqual(CP.clamp_claim_wait_ms(-5), 0)
        self.assertEqual(CP.clamp_claim_wait_ms("junk"), 0)
        self.assertEqual(CP.clamp_claim_wait_ms(None), 0)

    def test_already_queued_job_is_claimed_without_waiting(self):
        job_id = self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
        started = time.monotonic()
        jobs = self.plane.claim_ai_jobs_held(MACHINE_A, 4, wait_ms=5000)
        self.assertEqual([j["id"] for j in jobs], [job_id])
        self.assertLess(time.monotonic() - started, 0.5)

    def test_management_api_honours_wait_ms(self):
        thread, ids = self._enqueue_from_other_connection(MACHINE_A, 0.3)
        started = time.monotonic()
        payload = _SAFETY.mgmt.claim_ai_jobs_on_server(
            root=self.agent_a_tmp, limit=4, wait_ms=5000
        )
        elapsed = time.monotonic() - started
        thread.join(2.0)
        self.assertEqual([j["id"] for j in payload.get("jobs") or []], ids)
        self.assertLess(elapsed, 1.0)


class _Echo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        gate = self.server.gate
        with BOUNDED.parked_slot() as parked:
            self.server.parked_results.append(parked)
            if parked:
                gate.wait(5.0)
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _make_server(max_concurrent, max_parked):
    class Server(BOUNDED.BoundedThreadingMixIn, http.server.HTTPServer):
        pass

    Server.max_concurrent = max_concurrent
    Server.max_parked = max_parked
    srv = Server(("127.0.0.1", 0), _Echo)
    srv.gate = threading.Event()
    srv.parked_results = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _get(port, timeout=5.0):
    return urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=timeout).read()


class ParkedSlotTests(unittest.TestCase):
    def test_parked_requests_do_not_consume_slots(self):
        srv = _make_server(max_concurrent=2, max_parked=16)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(_get(port)), daemon=True)
            for _ in range(6)
        ]
        for t in threads:
            t.start()
        deadline = time.monotonic() + 3.0
        while len(srv.parked_results) < 6 and time.monotonic() < deadline:
            time.sleep(0.02)
        # Six requests are parked at once although only two slots exist.
        self.assertEqual(len(srv.parked_results), 6)
        self.assertTrue(all(srv.parked_results))
        srv.gate.set()
        for t in threads:
            t.join(5.0)
        self.assertEqual(results, [b"ok"] * 6)

    def test_slot_is_taken_again_before_the_caller_continues(self):
        srv = _make_server(max_concurrent=1, max_parked=4)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        # After every request finished the single slot must be free again:
        srv.gate.set()
        for _ in range(3):
            self.assertEqual(_get(srv.server_address[1]), b"ok")
        # The worker releases its slot just after the response is flushed, so
        # give it a moment instead of racing the client.
        self.assertTrue(srv._slot_sem.acquire(timeout=2.0))
        srv._slot_sem.release()

    def test_parking_is_refused_above_the_cap(self):
        srv = _make_server(max_concurrent=8, max_parked=2)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        threads = [
            threading.Thread(target=lambda: _get(port), daemon=True) for _ in range(4)
        ]
        for t in threads:
            t.start()
        deadline = time.monotonic() + 3.0
        while len(srv.parked_results) < 4 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(sorted(srv.parked_results), [False, False, True, True])
        srv.gate.set()
        for t in threads:
            t.join(5.0)

    def test_outside_a_bounded_server_parking_is_a_noop(self):
        with BOUNDED.parked_slot() as parked:
            self.assertTrue(parked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
