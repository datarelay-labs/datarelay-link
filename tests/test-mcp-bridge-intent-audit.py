#!/usr/bin/env python3
"""AUD-21 D4: intent-first audit for MCP Bridge endpoint dispatch.

Before D4 the Bridge audited a dispatched call only after the job came back, so
an exception in that audit write turned a command that had already run into a
bare `internal error`, and nothing recorded that the call was ever dispatched.
D4 (docs/MCP_BRIDGE_DISPATCH_DESIGN.md, section 3):

- an intent row (`DISPATCHING`, correlation id) is written before enqueue, and
  the call fails closed without enqueue if it cannot be written;
- a failed completion write never replaces the execution result: the result is
  returned with `audit_status: failed` and the failure is logged at ERROR;
- any error after enqueue carries `job_id` and `retryable: false`.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import unittest
from unittest import mock

from mcp_dispatch_fixture import HOST, DispatchFixture

from drlink_control_plane import ControlPlane  # noqa: E402
import drlink_v24 as v24  # noqa: E402

LOGGER = "drlink.mcp_bridge"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _fail_on_result(result_value):
    """record_ai_activity that raises only for rows with the given result."""
    original = ControlPlane.record_ai_activity

    def wrapper(self, **kwargs):
        if kwargs.get("result") == result_value:
            raise sqlite3.OperationalError("disk I/O error")
        return original(self, **kwargs)

    return wrapper


class IntentFirstAuditTests(DispatchFixture):
    def setUp(self):
        super().setUp()
        self.capture = _Capture()
        logger = logging.getLogger(LOGGER)
        logger.addHandler(self.capture)
        self.addCleanup(logger.removeHandler, self.capture)

    def _payload(self, response):
        status, body = response
        self.assertEqual(status, 200)
        self.assertNotIn("error", body)
        return json.loads(body["result"]["content"][0]["text"])

    def test_intent_row_precedes_enqueue_and_shares_the_correlation_id(self):
        seen_at_enqueue = []
        original = ControlPlane.enqueue_ai_job

        def spy(plane, **kwargs):
            seen_at_enqueue.append(self.activity())
            return original(plane, **kwargs)

        with mock.patch.object(ControlPlane, "enqueue_ai_job", spy):
            payload = self._payload(self.rpc_exec())
        self.assertEqual(payload["result"], "ALLOW")
        self.assertEqual(len(seen_at_enqueue), 1)
        intent = seen_at_enqueue[0]
        self.assertEqual([row["result"] for row in intent], ["DISPATCHING"])
        rows = self.activity()
        self.assertEqual([row["result"] for row in rows], ["DISPATCHING", "ALLOW"])
        cid = rows[0]["correlation_id"]
        self.assertTrue(cid and cid.startswith("mcp-"), cid)
        self.assertEqual(rows[1]["correlation_id"], cid)
        self.assertEqual(rows[0]["endpoint_name"], HOST)
        self.assertEqual(rows[0]["operand_summary"], "echo ok")

    def test_intent_write_failure_rejects_without_enqueue(self):
        with mock.patch.object(ControlPlane, "record_ai_activity", _fail_on_result("DISPATCHING")):
            status, body = self.rpc_exec()
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32603)
        self.assertNotIn("job_id", body["error"]["data"])
        self.assertEqual(self.jobs(), [])
        self.assertEqual(self.completed, [])

    def test_completion_write_failure_returns_the_result_with_audit_status_failed(self):
        with mock.patch.object(ControlPlane, "record_ai_activity", _fail_on_result("ALLOW")):
            payload = self._payload(self.rpc_exec())
        self.assertEqual(payload["result"], "ALLOW")
        self.assertEqual(payload["stdout"], "ok\n")
        self.assertEqual(payload["audit_status"], "failed")
        self.assertFalse(payload["retryable"])
        jobs = self.jobs()
        self.assertEqual(payload["job_id"], jobs[0]["id"])
        self.assertEqual(len(self.completed), 1)
        errors = [r.getMessage() for r in self.capture.records if r.levelno >= logging.ERROR]
        self.assertEqual(len(errors), 1)
        cid = self.activity()[0]["correlation_id"]
        for needle in (cid, jobs[0]["id"], "OperationalError"):
            self.assertIn(needle, errors[0])
        self.assertNotIn("echo ok", errors[0])

    def test_error_after_enqueue_carries_job_id_and_is_not_retryable(self):
        with mock.patch.object(ControlPlane, "get_ai_job",
                               side_effect=sqlite3.InterfaceError("bad parameter")):
            status, body = self.rpc_exec()
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32603)
        data = body["error"]["data"]
        jobs = self.jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(data["job_id"], jobs[0]["id"])
        self.assertIs(data["retryable"], False)
        cid = self.activity()[0]["correlation_id"]
        self.assertEqual(data["correlation_id"], cid)
        self.assertNotIn("bad parameter", json.dumps(body))

    def test_denied_call_writes_no_intent_row(self):
        v24.set_ai_access_rule(self.plane, "ops-run", mode="whitelist", source="ops",
                               destination=HOST, permission="run", enabled=False, oneshot=True)
        status, body = self.rpc_exec()
        self.assertTrue(body["result"]["isError"])
        self.assertEqual([row["result"] for row in self.activity()], ["DENY"])
        self.assertEqual(self.jobs(), [])


if __name__ == "__main__":
    unittest.main()
