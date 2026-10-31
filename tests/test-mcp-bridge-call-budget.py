#!/usr/bin/env python3
"""AUD-21 D5: per-worker call budget with an explicit `busy` for MCP Bridge dispatch.

Owner-approved definition (2026-10-31), recorded in docs/MCP_BRIDGE_DISPATCH_DESIGN.md 5e:

- the budget counts endpoint (Agent job queue) dispatches in flight in ONE Bridge worker
  process (64 by default, `DRLINK_MCP_DISPATCH_BUDGET`); `server_*` full-control calls,
  `list_hosts` and `get_host` are not counted;
- it is decided after authorization allowed the call and the host is available, and before
  the intent row and the enqueue: a refused call writes no audit row and enqueues nothing;
- the refusal is a JSON-RPC error `-32001 busy` with `retryable: true` and `retry_after_ms`;
- refusals are counted (`busy_refused`) and logged once per 100, never with arguments.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import unittest
from unittest import mock

from mcp_dispatch_fixture import HOST, DispatchFixture

from drlink_control_plane import ControlPlane  # noqa: E402


class CallBudgetTests(DispatchFixture):
    agent_delay = 0.8

    def _rpc(self, command="echo ok"):
        # The HTTP handler lends every request its own pooled SQLite connection; threads
        # that share the primary connection would only test SQLite, not the budget.
        with self.plane.request_scope():
            return self.rpc_exec(command)

    def _in_background(self, results):
        thread = threading.Thread(target=lambda: results.append(self._rpc()), daemon=True)
        thread.start()
        return thread

    def _fill(self, count):
        results, threads = [], []
        for _ in range(count):
            threads.append(self._in_background(results))
        deadline = time.monotonic() + 5
        while len(self.jobs()) < count and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(len(self.jobs()), count)
        return results, threads

    def test_default_budget_is_64(self):
        self.assertEqual(self.bridge.dispatch_budget, 64)

    def test_a_call_over_the_budget_is_refused_busy_before_audit_and_enqueue(self):
        self.bridge.dispatch_budget = 2
        results, threads = self._fill(2)
        status, body = self._rpc("echo third")
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32001)
        self.assertEqual(body["error"]["message"], "busy")
        data = body["error"]["data"]
        self.assertIs(data["retryable"], True)
        self.assertIsInstance(data["retry_after_ms"], int)
        self.assertGreater(data["retry_after_ms"], 0)
        self.assertNotIn("job_id", data)
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(len(results), 2)
        for status, body in results:
            payload = json.loads(body["result"]["content"][0]["text"])
            self.assertEqual(payload["result"], "ALLOW")
        self.assertEqual(len(self.jobs()), 2)
        self.assertEqual(sorted(row["result"] for row in self.activity()),
                         ["ALLOW", "ALLOW", "DISPATCHING", "DISPATCHING"])
        self.assertEqual(self.bridge.busy_refused, 1)

    def test_the_slot_is_released_when_the_call_completes(self):
        self.bridge.dispatch_budget = 1
        results, threads = self._fill(1)
        self.assertEqual(self._rpc()[1]["error"]["code"], -32001)
        threads[0].join(timeout=10)
        self.assertEqual(self.bridge.inflight, 0)
        status, body = self._rpc()
        self.assertNotIn("error", body)

    def test_the_slot_is_released_when_dispatch_fails(self):
        self.bridge.dispatch_budget = 1
        with mock.patch.object(ControlPlane, "enqueue_ai_job", side_effect=RuntimeError("boom")):
            status, body = self._rpc()
        self.assertEqual(body["error"]["code"], -32603)
        self.assertEqual(self.bridge.inflight, 0)
        status, body = self._rpc()
        self.assertNotIn("error", body)

    def test_calls_that_do_not_dispatch_are_not_counted(self):
        self.bridge.dispatch_budget = 1
        results, threads = self._fill(1)
        body = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "list_hosts", "arguments": {}}}
        with self.plane.request_scope():
            status, response = self.bridge.handle_rpc(body, {}, self.principal)
        self.assertEqual(status, 200)
        self.assertNotIn("error", response)
        body["params"] = {"name": "get_host", "arguments": {"endpoint": HOST}}
        with self.plane.request_scope():
            status, response = self.bridge.handle_rpc(body, {}, self.principal)
        self.assertNotIn("error", response)
        for thread in threads:
            thread.join(timeout=10)

    def test_refusals_are_logged_without_arguments_and_not_every_time(self):
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = _H(level=logging.DEBUG)
        logger = logging.getLogger("drlink.mcp_bridge")
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        self.bridge.dispatch_budget = 1
        results, threads = self._fill(1)
        for _ in range(3):
            self._rpc("echo SECRET-ARGUMENT")
        for thread in threads:
            thread.join(timeout=10)
        busy_logs = [r for r in records if "busy" in r.getMessage()]
        self.assertEqual(len(busy_logs), 1)
        self.assertNotIn("SECRET-ARGUMENT", busy_logs[0].getMessage())
        self.assertEqual(self.bridge.busy_refused, 3)


if __name__ == "__main__":
    unittest.main()
