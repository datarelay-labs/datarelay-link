#!/usr/bin/env python3
"""F014: finish an already-executed Agent job after transient delivery trouble.

Never repeat a command, reassign a job, or perform a remote mutation in tests.
"""
from __future__ import annotations
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import drlink_ai_agent as agent
import drlink_mgmt_sync as mgmt
from drlink_control_plane import ControlPlaneError


class AgentCompletionDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.worker = agent.AgentLoop(
            base_url="http://127.0.0.1:9", token="non-secret-fixture",
            stop_event=threading.Event(),
        )
        self.job = {
            "id": "job-f014-fixture",
            "capability": "exec",
            "arguments": {"command": "printf marker"},
            "patterns": [],
            "timeout": 5,
            "claim_token": "test-claim-token",
            "attempt_id": "test-attempt-id",
        }

    def test_transient_failure_retries_same_result_without_reexecution(self):
        result = {"result": "ALLOW", "stdout": "marker", "exit_status": 0}
        calls = []
        def complete(jid, body, **kwargs):
            calls.append((jid, body, dict(kwargs)))
            if len(calls) == 1:
                raise OSError("simulated transient delivery drop")
        with mock.patch.object(self.worker, "_claim", return_value=[self.job]), \
             mock.patch.object(agent, "execute_local", return_value=result) as execute, \
             mock.patch.object(self.worker, "_complete", side_effect=complete):
            self.assertEqual(self.worker.run_once(), 1)
            execute.assert_called_once()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[1][2]["claim_token"], "test-claim-token")
        self.assertEqual(calls[1][2]["attempt_id"], "test-attempt-id")

    def test_auth_denial_is_not_retried(self):
        with mock.patch.object(self.worker, "_claim", return_value=[self.job]), \
             mock.patch.object(agent, "execute_local", return_value={"result": "DENY"}) as execute, \
             mock.patch.object(self.worker, "_complete",
                               side_effect=ControlPlaneError("identity revoked")) as completed:
            self.assertEqual(self.worker.run_once(), 1)
            self.assertEqual(completed.call_count, 1)
            execute.assert_called_once()

    def test_signed_management_wrapped_network_error_is_retryable(self):
        # Production _request_json wraps network URLError in MgmtSyncError.
        import urllib.error
        def network_error(*_args, **_kwargs):
            try:
                raise urllib.error.URLError("temporary network disconnect")
            except urllib.error.URLError as cause:
                raise mgmt.MgmtSyncError("signed management path unreachable") from cause
        self.assertTrue(self.worker._transient_completion_failure(
            self._wrapped_error(network_error)
        ))

    @staticmethod
    def _wrapped_error(f):
        try:
            f()
        except Exception as exc:
            return exc
        raise AssertionError("expected network fault")

    def test_mgmt_identity_failure_never_retried(self):
        denied = mgmt.MgmtAuthError("identity revoked")
        calls = []
        def complete(*_args, **_kwargs):
            calls.append(1)
            raise denied
        with mock.patch.object(self.worker, "_claim", return_value=[self.job]), \
             mock.patch.object(agent, "execute_local", return_value={"result": "ALLOW"}) as execute, \
             mock.patch.object(self.worker, "_complete", side_effect=complete):
            self.worker.run_once()
        self.assertEqual(len(calls), 1)
        execute.assert_called_once()

    def test_persistent_transient_failure_is_bounded_three_attempts(self):
        with mock.patch.object(self.worker, "_claim", return_value=[self.job]), \
             mock.patch.object(agent, "execute_local", return_value={"result": "ALLOW"}) as execute, \
             mock.patch.object(self.worker, "_complete",
                               side_effect=ConnectionResetError("fixture")) as send:
            self.worker.run_once()
        execute.assert_called_once()
        self.assertEqual(send.call_count, 3)

    def test_expired_job_never_executes_or_retries_complete(self):
        expired = dict(self.job, deadline_at="2000-01-01T00:00:00Z")
        with mock.patch.object(self.worker, "_claim", return_value=[expired]), \
             mock.patch.object(agent, "execute_local") as execute, \
             mock.patch.object(self.worker, "_complete",
                               side_effect=OSError("offline")) as send:
            self.worker.run_once()
        execute.assert_not_called()
        self.assertEqual(send.call_count, 1)

    def test_server_rejected_ack_never_counts_as_completed(self):
        # A 4xx bearer response can be JSON with an error field; a response
        # is successful only when the Server actually acknowledges completion.
        with mock.patch.object(agent, "_agent_post",
                               return_value={"error": "authorization denied"}):
            with self.assertRaisesRegex(ControlPlaneError, "not acknowledged"):
                self.worker._complete(
                    "job-f014-fixture", {"result": "ALLOW"},
                    claim_token="test-claim-token",
                    attempt_id="test-attempt-id",
                )

    def test_signed_agent_ack_must_explicitly_confirm_ok(self):
        signed = agent.AgentLoop(
            agent_root="/tmp/drlink-agent-f014-fixture",
            stop_event=threading.Event(),
        )
        with mock.patch.object(mgmt, "complete_ai_job_on_server",
                               return_value={"error": "claim mismatch"}):
            with self.assertRaisesRegex(ControlPlaneError, "not acknowledged"):
                signed._complete(
                    "job-f014-fixture", {"result": "ALLOW"},
                    claim_token="test-claim-token",
                    attempt_id="test-attempt-id",
                )

    def test_signed_completion_has_bounded_large_result_timeout(self):
        with mock.patch.dict(os.environ, {"DRLINK_MGMT_URL": "https://example.invalid"}), \
             mock.patch.object(mgmt, "_request_json", return_value={"ok": True}) as send:
            mgmt.complete_ai_job_on_server(
                root="/tmp/drlink-unreachable-fixture",
                job_id="job-f014-fixture", result={"stdout": "x" * 65536},
                claim_token="test-claim-token", attempt_id="test-attempt-id",
            )
        self.assertEqual(send.call_args.args[0], "POST")
        self.assertTrue(send.call_args.args[1].endswith("/v1/ai-jobs/complete"))
        self.assertGreater(send.call_args.kwargs.get("timeout", 8.0), 8.0)


if __name__ == "__main__":
    unittest.main()
