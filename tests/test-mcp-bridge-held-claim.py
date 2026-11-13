#!/usr/bin/env python3
"""AUD-21 step 2c: the Bridge holds a claim and waits for results by event.

* ``POST /agent/v1/claim`` with ``wait_ms`` is held and answers the moment a job
  is queued for that host; without ``wait_ms`` it still answers immediately.
* The Bridge's result wait follows the database change feed, and still returns
  the result when that feed is silent (lost signal), by rereading the database.

Disposable temp root, real ControlPlane and HTTP server; no service or
credential is touched.
"""
from __future__ import annotations

import importlib.util
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
import drlink_mcp_bridge  # noqa: E402


def _load_e2e_harness():
    path = ROOT / "tests" / "test-ai-access-mcp-e2e.py"
    spec = importlib.util.spec_from_file_location("ai_access_mcp_e2e_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_E2E = _load_e2e_harness()

HELD_CLIENT = "client-held-claim-xxxxxxxx"


class _SilentSubscription:
    """A subscription whose signal never arrives (lost signals): only the
    bounded fallback wait ends the sleep."""

    def clear(self):
        pass

    def wait(self, timeout):
        time.sleep(timeout)
        return False

    def close(self):
        pass


class _UnusedSubscription:
    """For a feed that is not ready: the caller must poll, never wait."""

    def clear(self):
        pass

    def wait(self, timeout):  # pragma: no cover - must not be used
        raise AssertionError("wait() must not be used when the feed is not ready")

    def close(self):
        pass


class BridgeHeldClaimTests(unittest.TestCase):
    _harness_setup = _E2E.MCPBridgeE2ETests.setUp
    _harness_teardown = _E2E.MCPBridgeE2ETests.tearDown
    _token = _E2E.MCPBridgeE2ETests._token
    call = _E2E.MCPBridgeE2ETests.call
    text_of = _E2E.MCPBridgeE2ETests.text_of

    SHORT_HOLD_MS = 2000

    def setUp(self):
        self._harness_setup()
        plane = self.bridge.plane
        # A host with no worker of its own, so nothing else claims its jobs.
        plane.upsert_client(HELD_CLIENT, label="heldhost")
        self.held_token = plane.issue_agent_credential(HELD_CLIENT, rotate=True)
        self.assertTrue(self.held_token)
        self.principal = plane.get_principal("cursor-dev")

    def tearDown(self):
        self._harness_teardown()

    def _claim(self, **body):
        payload = {"limit": 4}
        payload.update(body)
        timeout = 10 + (payload.get("wait_ms") or 0) / 1000.0
        return drlink_ai_agent._agent_post(
            self.base + "/agent/v1/claim", self.held_token, payload, timeout=timeout
        )

    def _enqueue(self):
        return self.bridge.plane.enqueue_ai_job(
            principal_id=self.principal["id"],
            endpoint_object_id="ep-held",
            client_id=HELD_CLIENT,
            capability="exec",
            arguments={"command": "echo held"},
            patterns=[],
            timeout=30,
        )

    def test_claim_without_wait_ms_answers_immediately(self):
        started = time.monotonic()
        self.assertEqual(self._claim().get("jobs"), [])
        self.assertLess(time.monotonic() - started, 0.5)

    def test_claim_with_wait_ms_returns_as_soon_as_a_job_is_queued(self):
        ids = []

        def later():
            time.sleep(0.4)
            ids.append(self._enqueue())

        thread = threading.Thread(target=later, daemon=True)
        thread.start()
        started = time.monotonic()
        payload = self._claim(wait_ms=5000)
        elapsed = time.monotonic() - started
        thread.join(2.0)
        self.assertEqual([job["id"] for job in payload.get("jobs") or []], ids)
        self.assertGreaterEqual(elapsed, 0.35)
        self.assertLess(elapsed, 1.0, "the held claim must follow the enqueue within milliseconds")

    def test_claim_with_wait_ms_times_out_empty(self):
        started = time.monotonic()
        payload = self._claim(wait_ms=600)
        elapsed = time.monotonic() - started
        self.assertEqual(payload.get("jobs"), [])
        self.assertGreaterEqual(elapsed, 0.5)
        self.assertLess(elapsed, 2.0)

    def test_a_held_claim_does_not_block_other_requests(self):
        done = threading.Event()
        threading.Thread(
            target=lambda: (self._claim(wait_ms=3000), done.set()), daemon=True
        ).start()
        time.sleep(0.2)
        started = time.monotonic()
        status, payload = self.call(
            self.cursor, "exec", {"endpoint": "lab1", "command": "echo parallel"}
        )
        self.assertEqual(status, 200)
        self.assertIn("parallel", self.text_of(payload))
        # lab1's own worker polls every 2 s, so allow for that, but the held
        # claim of another host must not add its 3 s on top.
        self.assertLess(time.monotonic() - started, 2.8)
        done.wait(5.0)

    def test_result_wait_still_returns_when_the_change_feed_is_silent(self):
        class Silent:
            """A watcher that is ready but never signals (lost signals)."""

            ready = True
            generation = 0

            def wait(self, since, timeout):
                time.sleep(timeout)
                return since

            def subscribe(self, kind, key):
                return _SilentSubscription()

        with mock.patch.object(drlink_mcp_bridge, "get_watcher", return_value=Silent()):
            started = time.monotonic()
            status, payload = self.call(
                self.cursor, "exec", {"endpoint": "lab1", "command": "echo fallback"}
            )
            elapsed = time.monotonic() - started
        self.assertEqual(status, 200)
        self.assertNotIn("error", payload)
        self.assertIn("fallback", self.text_of(payload))
        # Worker poll (<= 2 s) plus at most one fallback interval.
        self.assertLess(elapsed, 2.0 + drlink_mcp_bridge.RESULT_WAIT_FALLBACK_SECONDS + 1.0)

    def test_result_wait_works_without_a_change_feed(self):
        class NotReady:
            ready = False
            generation = 0

            def wait(self, since, timeout):  # pragma: no cover - must not be used
                raise AssertionError("wait() must not be used when the feed is not ready")

            def subscribe(self, kind, key):
                return _UnusedSubscription()

        with mock.patch.object(drlink_mcp_bridge, "get_watcher", return_value=NotReady()):
            status, payload = self.call(
                self.cursor, "exec", {"endpoint": "lab1", "command": "echo poll"}
            )
        self.assertEqual(status, 200)
        self.assertIn("poll", self.text_of(payload))


if __name__ == "__main__":
    unittest.main(verbosity=2)
