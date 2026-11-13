#!/usr/bin/env python3
"""AUD-21: an MCP `internal error` must be diagnosable without leaking data.

Before this change the bridge turned every unexpected exception in `tools/call`
into a bare `-32603 internal error` with no log, so the real cause (concurrent
use of one SQLite connection) was invisible. The response stays generic; the
log now carries a correlation id, the exception class, the innermost frames and,
only for DB/OS errors, a short message. Arguments, tokens and caller-supplied
text are never logged.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane, ControlPlaneError  # noqa: E402
from drlink_mcp_bridge import MCPBridge  # noqa: E402

LOGGER = "drlink.mcp_bridge"
SECRET_ARG = "drk_SECRET_ARGUMENT_VALUE"
SECRET_EXC = "drk_SECRET_IN_EXCEPTION_TEXT"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class InternalErrorLoggingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-mcp-log-")
        self.plane = ControlPlane(self.tmp)
        self.bridge = MCPBridge(root=self.tmp, plane=self.plane, auto_agents=False)
        self.capture = _Capture()
        self.logger = logging.getLogger(LOGGER)
        self.logger.addHandler(self.capture)
        self._old_level = self.logger.level
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        self.logger.removeHandler(self.capture)
        self.logger.setLevel(self._old_level)
        self.bridge.close()
        self.plane.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, side_effect, name="exec"):
        body = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": {"endpoint": "lab1", "command": "echo " + SECRET_ARG},
            },
        }
        with patch.object(MCPBridge, "call_tool", side_effect=side_effect):
            return self.bridge.handle_rpc(body, {}, {"name": "tester", "id": "p1"})

    def _errors(self):
        return [r for r in self.capture.records if r.levelno >= logging.ERROR]

    def test_db_error_is_logged_with_class_location_and_correlation_id(self):
        status, payload = self._call(sqlite3.InterfaceError("bad parameter or other API misuse"))
        self.assertEqual(status, 200)
        self.assertEqual(payload["error"]["code"], -32603)
        self.assertEqual(payload["error"]["message"], "internal error")
        cid = payload["error"]["data"]["correlation_id"]
        self.assertTrue(cid.startswith("mcp-"), cid)
        records = self._errors()
        self.assertEqual(len(records), 1)
        text = records[0].getMessage()
        for needle in (cid, "tool=exec", "sqlite3.InterfaceError", "bad parameter", "handle_rpc"):
            self.assertIn(needle, text)

    def test_response_never_carries_exception_text(self):
        _, payload = self._call(sqlite3.InterfaceError("bad parameter or other API misuse"))
        rendered = json.dumps(payload)
        self.assertNotIn("bad parameter", rendered)
        self.assertNotIn("InterfaceError", rendered)

    def test_secrets_in_arguments_or_exception_text_are_not_logged(self):
        class Boom(Exception):
            pass

        status, payload = self._call(Boom("token=" + SECRET_EXC))
        self.assertEqual(payload["error"]["code"], -32603)
        text = "\n".join(r.getMessage() for r in self.capture.records)
        self.assertIn("Boom", text)
        self.assertNotIn(SECRET_EXC, text)
        self.assertNotIn(SECRET_ARG, text)
        self.assertNotIn(SECRET_EXC, json.dumps(payload))

    def test_caller_supplied_tool_name_cannot_inject_log_lines(self):
        _, payload = self._call(RuntimeError("x"), name="exec\nFAKE internal error cid=evil")
        self.assertEqual(payload["error"]["code"], -32603)
        message = self._errors()[0].getMessage()
        self.assertIn("tool=unknown", message)
        self.assertNotIn("\n", message)
        self.assertNotIn("evil", message)

    def test_policy_denial_is_not_an_internal_error_and_is_not_logged_as_one(self):
        status, payload = self._call(ControlPlaneError("denied for test"))
        self.assertEqual(status, 200)
        self.assertNotIn("error", payload)
        self.assertTrue(payload["result"]["isError"])
        self.assertEqual(self._errors(), [])


if __name__ == "__main__":
    unittest.main()
