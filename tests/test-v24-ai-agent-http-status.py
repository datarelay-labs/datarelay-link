#!/usr/bin/env python3
"""Bearer Agent HTTP status is authoritative, never the error response JSON."""
from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_ai_agent import AgentLoop, _agent_post
from drlink_control_db import ControlPlaneError


def failed_response(url: str, code: int, payload: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url, code, "Synthetic failure", {}, io.BytesIO(payload)
    )


class BearerAgentHTTPStatusTests(unittest.TestCase):
    def test_rejected_http_completion_cannot_forge_successful_ack(self):
        loop = AgentLoop("http://127.0.0.1:9", "temporary-test-token")
        url = "http://127.0.0.1:9/agent/v1/complete"
        for code in (400, 401, 403, 409, 503):
            with self.subTest(http_status=code):
                error = failed_response(
                    url, code,
                    b'{"ok":true,"job":{"status":"done"},"secret":"PRIVATE"}',
                )
                with mock.patch(
                    "drlink_ai_agent.urllib.request.urlopen",
                    side_effect=error,
                ):
                    with self.assertRaisesRegex(
                        ControlPlaneError, "agent RPC HTTP %s" % code
                    ) as failure:
                        loop._complete(
                            "job_test", {"result": "ALLOW"},
                            claim_token="atk_test", attempt_id="att_test",
                        )
                    self.assertNotIn("PRIVATE", str(failure.exception))

    def test_rejected_http_claim_cannot_start_local_operation(self):
        loop = AgentLoop("http://127.0.0.1:9", "temporary-test-token")
        url = "http://127.0.0.1:9/agent/v1/claim"
        job = {
            "id": "job_test", "claim_token": "atk_test",
            "attempt_id": "att_test", "capability": "write_file",
            "arguments": {"path": "/tmp/not-to-be-written", "content": "x"},
            "patterns": ["/tmp/**"], "timeout": 5,
            "deadline_at": (
                datetime.now(timezone.utc) + timedelta(minutes=3)
            ).isoformat(),
        }
        error = failed_response(
            url, 403, json.dumps({"jobs": [job]}).encode("utf-8")
        )
        with mock.patch(
            "drlink_ai_agent.urllib.request.urlopen", side_effect=error,
        ), mock.patch(
            "drlink_ai_agent.execute_local", return_value={"result": "ALLOW"},
        ) as executed, mock.patch.object(loop, "_complete") as completed:
            with self.assertRaisesRegex(ControlPlaneError, "agent RPC HTTP 403"):
                loop.run_once()
            executed.assert_not_called()
            completed.assert_not_called()

    def test_actual_2xx_response_remains_usable(self):
        with mock.patch(
            "drlink_ai_agent.urllib.request.urlopen",
            return_value=io.BytesIO(b'{"ok":true}'),
        ):
            self.assertEqual(
                _agent_post(
                    "http://127.0.0.1:9/agent/v1/complete",
                    "temporary-test-token",
                    {"id": "job_test", "result": {"result": "ALLOW"}},
                ),
                {"ok": True},
            )


if __name__ == "__main__":
    unittest.main()
