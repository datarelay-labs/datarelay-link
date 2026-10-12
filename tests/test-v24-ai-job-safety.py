#!/usr/bin/env python3
"""P0: AI job queue fairness + timeout/cancel/late-completion safety."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_ai_agent import AgentLoop  # noqa: E402
from drlink_control_db import ensure_ai_jobs_safety_schema, utc_now_iso  # noqa: E402
from drlink_control_plane import (  # noqa: E402
    ControlPlane,
    ControlPlaneError,
    _ai_job_deadline_iso,
)
from drlink_mcp_bridge import MCPBridge  # noqa: E402
import drlink_mgmt_sync as mgmt  # noqa: E402
import drlink_v24 as v24  # noqa: E402
import frp_mgmt_auth as MGMT  # noqa: E402

MACHINE_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
MACHINE_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
HOST_A = "agent-a"
HOST_B = "agent-b"


def _verify(plane: ControlPlane, name: str) -> None:
    plane.conn.execute(
        "UPDATE ai_principals SET credential_status = 'active', enabled = 1 WHERE name = ?",
        (name,),
    )
    plane.commit_if_autonomous()


def _enroll_agent(agent_root: str, machine_id: str, hostname: str):
    Path(agent_root, "etc/frp").mkdir(parents=True, exist_ok=True)
    Path(agent_root, "etc/frp/client-state.json").write_text(
        json.dumps({"machine_id": machine_id, "hostname": hostname, "label": hostname}),
        encoding="utf-8",
    )
    key = Path(agent_root, "etc/frp/client-identity.key")
    pub = Path(agent_root, "etc/frp/client-identity.pub")
    if not key.exists():
        MGMT.generate_keypair(key, pub)
        os.chmod(key, 0o600)
    mac = MGMT.new_mac_key()
    mac_path = Path(agent_root, "etc/frp/client-identity.mac")
    mac_path.write_text(mac, encoding="utf-8")
    os.chmod(mac_path, 0o600)
    return pub.read_text(encoding="utf-8"), mac


class AiJobSafetyTests(unittest.TestCase):
    def setUp(self):
        self.server_tmp = tempfile.mkdtemp(prefix="drlink-p6-srv-")
        self.agent_a_tmp = tempfile.mkdtemp(prefix="drlink-p6-a-")
        self.agent_b_tmp = tempfile.mkdtemp(prefix="drlink-p6-b-")
        os.environ["DRLINK_TEST_ROOT"] = self.server_tmp
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.server_tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        for key in ("DRLINK_AI_TEST_LOCAL_EXEC", "DRLINK_AI_TEST_LOCAL_AGENTS", "DRLINK_AI_LOCAL_EXEC"):
            os.environ.pop(key, None)
        Path(self.server_tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.server_tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        self.agent_a_root = Path(self.agent_a_tmp) / "workspace"
        self.agent_b_root = Path(self.agent_b_tmp) / "workspace"
        self.agent_a_root.mkdir(parents=True)
        self.agent_b_root.mkdir(parents=True)
        (self.agent_a_root / "AGENT_MARKER").write_text("AGENT_A\n", encoding="utf-8")
        (self.agent_b_root / "AGENT_MARKER").write_text("AGENT_B\n", encoding="utf-8")
        pub_a, mac_a = _enroll_agent(self.agent_a_tmp, MACHINE_A, HOST_A)
        pub_b, mac_b = _enroll_agent(self.agent_b_tmp, MACHINE_B, HOST_B)
        self.plane = ControlPlane(self.server_tmp)
        ensure_ai_jobs_safety_schema(self.plane.conn)
        v24.ensure_v2_schema(self.plane.conn)
        self.plane.upsert_client(MACHINE_A, label=HOST_A, hostname=HOST_A)
        self.plane.upsert_client(MACHINE_B, label=HOST_B, hostname=HOST_B)
        self.plane.set_ai_principal("ops", enabled=True)
        _verify(self.plane, "ops")
        self.principal = self.plane.get_principal("ops")
        v24.set_permission_object(
            self.plane,
            "full",
            permissions=[
                "host-info",
                "process-read",
                "file-read",
                "file-write",
                "file-upload",
                "file-download",
                "command-exec",
            ],
            oneshot=True,
        )
        for dest in (HOST_A, HOST_B):
            v24.set_ai_access_rule(
                self.plane,
                "ops-%s" % dest,
                mode="whitelist",
                source="ops",
                destination=dest,
                permission="full",
                enabled=True,
                oneshot=True,
            )
        for rule in ("ops-%s" % HOST_A, "ops-%s" % HOST_B):
            v24.set_ai_policy_path_scopes(
                self.plane,
                rule,
                [str(self.agent_a_root) + "/**", str(self.agent_b_root) + "/**"],
            )
        self.bridge = MCPBridge(root=self.server_tmp, plane=self.plane, auto_agents=False)
        self.verifier = mgmt.InMemoryMgmtVerifier()
        self.verifier.enroll(MACHINE_A, pub_a, mac_key=mac_a, hostname=HOST_A)
        self.verifier.enroll(MACHINE_B, pub_b, mac_key=mac_b, hostname=HOST_B)
        self.mgmt_httpd, self.mgmt_url, _ = mgmt.start_mgmt_server(
            self.plane, verifier=self.verifier
        )
        os.environ["DRLINK_MGMT_URL"] = self.mgmt_url
        for agent_root in (self.agent_a_tmp, self.agent_b_tmp):
            Path(agent_root, "etc/frp/server-endpoint.json").write_text(
                json.dumps({"mgmt_url": self.mgmt_url}),
                encoding="utf-8",
            )
        self._stops = []
        self._threads = []

    def tearDown(self):
        for stop in self._stops:
            stop.set()
        for thread in self._threads:
            thread.join(timeout=1)
        try:
            self.bridge.close()
        except Exception:
            pass
        try:
            mgmt.stop_mgmt_server(self.mgmt_httpd)
        except Exception:
            pass
        try:
            self.plane.close()
        except Exception:
            pass
        for key in (
            "DRLINK_TEST_ROOT",
            "FRP_DEPLOY_TEST_ROOT",
            "DRLINK_CONFIRM",
            "DRLINK_MGMT_URL",
            "DRLINK_AI_TEST_LOCAL_EXEC",
            "DRLINK_AI_TEST_LOCAL_AGENTS",
            "DRLINK_AI_LOCAL_EXEC",
        ):
            os.environ.pop(key, None)
        shutil.rmtree(self.server_tmp, ignore_errors=True)
        shutil.rmtree(self.agent_a_tmp, ignore_errors=True)
        shutil.rmtree(self.agent_b_tmp, ignore_errors=True)

    def _start_mgmt_worker(self, agent_root: str):
        stop = threading.Event()
        loop = AgentLoop(agent_root=agent_root, stop_event=stop)
        thread = threading.Thread(target=loop.run, daemon=True)
        thread.start()
        self._stops.append(stop)
        self._threads.append(thread)
        time.sleep(0.15)
        return stop

    def _enqueue_with_timeout(self, client_id: str, capability: str, timeout: int, **arguments) -> str:
        args = dict(arguments)
        if capability in ("read_file", "write_file") and "path" not in args:
            root = self.agent_a_root if client_id == MACHINE_A else self.agent_b_root
            if capability == "read_file":
                args["path"] = str(root / "AGENT_MARKER")
            else:
                args["path"] = str(root / "out.txt")
                args.setdefault("content", "x")
        return self.plane.enqueue_ai_job(
            principal_id=self.principal["id"],
            endpoint_object_id="ep-%s" % client_id[:8],
            client_id=client_id,
            capability=capability,
            arguments=args,
            patterns=[str(self.agent_a_root) + "/**", str(self.agent_b_root) + "/**"],
            timeout=timeout,
        )

    def test_cross_host_head_of_line_fairness(self):
        for _ in range(40):
            self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
        job_b = self._enqueue_with_timeout(MACHINE_B, "read_file", 60)
        claimed_b = self.plane.claim_ai_jobs(MACHINE_B, limit=4)
        self.assertEqual(len(claimed_b), 1)
        self.assertEqual(claimed_b[0]["id"], job_b)
        self.assertTrue(all(j["id"] != job_b or True for j in claimed_b))
        for job in claimed_b:
            row = self.plane.get_ai_job(job["id"])
            payload = json.loads(
                self.plane.conn.execute(
                    "SELECT payload_json FROM ai_jobs WHERE id = ?", (job["id"],)
                ).fetchone()[0]
            )
            self.assertEqual(payload["client_id"], MACHINE_B)
        claimed_a = self.plane.claim_ai_jobs(MACHINE_A, limit=4)
        self.assertEqual(len(claimed_a), 4)
        for job in claimed_a:
            payload = json.loads(
                self.plane.conn.execute(
                    "SELECT payload_json FROM ai_jobs WHERE id = ?", (job["id"],)
                ).fetchone()[0]
            )
            self.assertEqual(payload["client_id"], MACHINE_A)

    def test_atomic_single_claim(self):
        job_id = self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
        first = self.plane.claim_ai_jobs(MACHINE_A, limit=1)
        second = self.plane.claim_ai_jobs(MACHINE_A, limit=1)
        self.assertEqual([j["id"] for j in first], [job_id])
        self.assertEqual(second, [])
        row = self.plane.get_ai_job(job_id)
        self.assertEqual(row["status"], "running")
        self.assertTrue(row["claim_token"])

    def test_queued_timeout_blocks_late_side_effect(self):
        target = self.agent_a_root / "must-not-appear.txt"
        if target.exists():
            target.unlink()
        # Short MCP wait via tiny timeout; no worker during wait.
        text = self.bridge.call_tool(
            self.principal,
            "write_file",
            {"endpoint": HOST_A, "path": str(target), "content": "late"},
        )
        body = (text.get("content") or [{}])[0].get("text") or ""
        self.assertIn("TIMEOUT", body)
        self.assertFalse(target.exists())
        # Late worker must not claim/execute the terminal job.
        claimed = self.plane.claim_ai_jobs(MACHINE_A, limit=8)
        self.assertEqual(claimed, [])
        rows = list(
            self.plane.conn.execute(
                "SELECT status FROM ai_jobs WHERE client_id = ?", (MACHINE_A,)
            )
        )
        self.assertTrue(rows)
        self.assertTrue(all(r["status"] == "timeout" for r in rows))
        self.assertFalse(target.exists())

    def test_expired_before_claim_skips_to_newer_job(self):
        old = self._enqueue_with_timeout(MACHINE_A, "read_file", 30)
        newer = self._enqueue_with_timeout(MACHINE_A, "read_file", 30)
        past = _ai_job_deadline_iso(utc_now_iso(), -30)
        self.plane.conn.execute(
            "UPDATE ai_jobs SET deadline_at = ? WHERE id = ?", (past, old)
        )
        self.plane.commit_if_autonomous()
        claimed = self.plane.claim_ai_jobs(MACHINE_A, limit=4)
        self.assertEqual([j["id"] for j in claimed], [newer])
        self.assertEqual(self.plane.get_ai_job(old)["status"], "expired")

    def test_late_completion_rejected_after_timeout(self):
        job_id = self._enqueue_with_timeout(MACHINE_A, "write_file", 60, path=str(self.agent_a_root / "x.txt"), content="a")
        claimed = self.plane.claim_ai_jobs(MACHINE_A, limit=1)
        self.assertEqual(claimed[0]["id"], job_id)
        token = claimed[0]["claim_token"]
        attempt = claimed[0]["attempt_id"]
        self.plane.terminalize_ai_job(job_id, "timeout")
        with self.assertRaises(ControlPlaneError):
            self.plane.complete_ai_job(
                job_id,
                MACHINE_A,
                {"result": "ALLOW"},
                claim_token=token,
                attempt_id=attempt,
            )
        self.assertEqual(self.plane.get_ai_job(job_id)["status"], "timeout")

    def test_legacy_agent_http_never_accepts_ambiguous_claim_or_result(self):
        # The optional bearer-Agent fallback is distinct from signed
        # management auth, but cannot bypass the same Core state boundary.
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        from drlink_mcp_bridge import ThreadingHTTPServer, make_handler

        token = self.plane.issue_agent_credential(MACHINE_A, rotate=True)
        self.assertTrue(token)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.bridge))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = "http://127.0.0.1:%d/agent/v1/" % server.server_address[1]

        def send(name, body):
            request = Request(
                endpoint + name,
                data=json.dumps(body).encode("utf-8"),
                headers={"Authorization": "Bearer " + token,
                         "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=5) as response:
                    return response.status, json.load(response)
            except HTTPError as response:
                return response.code, json.load(response)

        try:
            job_id = self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
            for invalid in (0, -1, True, False, 1.5, "2", None, []):
                with self.subTest(claim_limit=invalid):
                    status, _ = send("claim", {"limit": invalid})
                    self.assertEqual(status, 400)
                    self.assertEqual(
                        self.plane.get_ai_job(job_id)["status"], "queued"
                    )
            status, response = send("claim", {"limit": 1})
            self.assertEqual(status, 200)
            self.assertEqual([j["id"] for j in response["jobs"]], [job_id])
            claimed = response["jobs"][0]
            for invalid in (None, [], "", 0, False):
                with self.subTest(completion_result=invalid):
                    status, _ = send(
                        "complete", {"id": job_id,
                                     "claim_token": claimed["claim_token"],
                                     "attempt_id": claimed["attempt_id"],
                                     "result": invalid},
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(
                        self.plane.get_ai_job(job_id)["status"], "running"
                    )
                    self.assertNotIn(job_id, self.bridge._job_results)
            status, response = send(
                "complete", {"id": job_id,
                             "claim_token": claimed["claim_token"],
                             "attempt_id": claimed["attempt_id"],
                             "result": {"ok": True}},
            )
            self.assertEqual(status, 200)
            self.assertTrue(response["ok"])
            self.assertEqual(self.plane.get_ai_job(job_id)["status"], "done")
            self.assertEqual(self.bridge._job_results[job_id], {"ok": True})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_agent_loop_rejects_replayed_claim_batch_before_any_local_work(self):
        # Both signed management identity and the optional local bearer
        # adapter must validate the complete claimed batch before execution.
        from datetime import datetime, timedelta, timezone
        future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        legitimate = {
            "id": "ai-job-one", "claim_token": "atk_test_one",
            "attempt_id": "att_test_one", "capability": "write_file",
            "arguments": {"path": str(self.agent_a_root / "not-written.txt"),
                          "content": "not-written"},
            "patterns": [str(self.agent_a_root / "**")],
            "timeout": 5, "deadline_at": future,
        }
        peer = {
            **legitimate, "id": "ai-job-two",
            "claim_token": "atk_test_two", "attempt_id": "att_test_two",
        }
        invalid_batches = (
            {"jobs": [legitimate, dict(legitimate)]},
            {"jobs": [legitimate, {**peer, "capability": "unknown-privileged"}]},
            {"jobs": [legitimate, {**peer, "patterns": [{"secret": "path"}]}]},
            {"jobs": [legitimate, {**peer, "timeout": True}]},
            {"jobs": [legitimate, {**peer, "timeout": "5"}]},
            {"jobs": [legitimate, {**peer, "timeout": 0}]},
            {"jobs": [legitimate, {**peer, "timeout": 1.5}]},
            {"jobs": [legitimate, {**peer, "timeout": 3601}]},
            {"jobs": [legitimate, {**peer, "attempt_id": legitimate["attempt_id"]}]},
            {"jobs": [legitimate, {**peer, "claim_token": "bad\\nline"}]},
            {"jobs": [legitimate, {"id": "malformed"}]},
            {"jobs": [legitimate] * 5},
            {"jobs": "not-a-list"},
            {"jobs": None},
            {},
            # Unknown or timezone-naive deadlines previously looked
            # "not expired" and could authorize local mutating operations.
            {"jobs": [{**legitimate, "deadline_at": None}]},
            {"jobs": [{**legitimate, "deadline_at": "invalid"}]},
            {"jobs": [{**legitimate, "deadline_at": "2099-01-01T00:00:00"}]},
            {"jobs": [{**legitimate, "deadline_at": []}]},
        )
        modes = (
            (AgentLoop(agent_root=self.agent_a_tmp),
             "drlink_mgmt_sync.claim_ai_jobs_on_server"),
            (AgentLoop("http://127.0.0.1:1", "disposable-test-token"),
             "drlink_ai_agent._agent_post"),
        )
        for loop, target in modes:
            for reply in invalid_batches:
                with self.subTest(target=target, reply=reply):
                    with mock.patch(target, return_value=reply), mock.patch(
                        "drlink_ai_agent.execute_local",
                        return_value={"result": "ALLOW"},
                    ) as executed, mock.patch.object(loop, "_complete") as completed:
                        with self.assertRaisesRegex(
                            ValueError, "AI job claim response UNKNOWN"
                        ):
                            loop.run_once()
                        executed.assert_not_called()
                        completed.assert_not_called()
            with self.subTest(valid_target=target):
                with mock.patch(
                    target, return_value={"jobs": [legitimate]},
                ), mock.patch(
                    "drlink_ai_agent.execute_local",
                    return_value={"result": "ALLOW"},
                ) as executed, mock.patch.object(loop, "_complete") as completed:
                    self.assertEqual(loop.run_once(), 1)
                    executed.assert_called_once()
                    completed.assert_called_once()

    def test_agent_exec_timeout_never_outlives_core_deadline(self):
        # A verified signed claim may be queued for several seconds before
        # local execution. Its original timeout cannot extend Core authority.
        from datetime import datetime, timedelta, timezone
        job = {
            "id": "ai-exec-time-budget", "claim_token": "atk_budget",
            "attempt_id": "att_budget", "capability": "exec",
            "arguments": {"command": "echo test"}, "patterns": [],
            "timeout": 60,
            "deadline_at": (
                datetime.now(timezone.utc) + timedelta(seconds=4)
            ).isoformat(),
        }
        loop = AgentLoop(agent_root=self.agent_a_tmp)
        with mock.patch.object(loop, "_claim", return_value=[job]), mock.patch(
            "drlink_ai_agent.execute_local", return_value={"result": "ALLOW"},
        ) as executed, mock.patch.object(loop, "_complete") as completed:
            self.assertEqual(loop.run_once(), 1)
        executed.assert_called_once()
        budget = executed.call_args.kwargs["timeout"]
        self.assertGreaterEqual(budget, 1)
        self.assertLessEqual(budget, 3)
        completed.assert_called_once()

    def test_agent_refuses_new_execution_with_subsecond_core_deadline(self):
        from datetime import datetime, timedelta, timezone
        job = {
            "id": "ai-exec-too-late", "claim_token": "atk_late",
            "attempt_id": "att_late", "capability": "exec",
            "arguments": {"command": "echo must-not-run"}, "patterns": [],
            "timeout": 60,
            "deadline_at": (
                datetime.now(timezone.utc) + timedelta(milliseconds=350)
            ).isoformat(),
        }
        loop = AgentLoop(agent_root=self.agent_a_tmp)
        with mock.patch.object(loop, "_claim", return_value=[job]), mock.patch(
            "drlink_ai_agent.execute_local",
        ) as executed, mock.patch.object(loop, "_complete") as completed:
            self.assertEqual(loop.run_once(), 1)
        executed.assert_not_called()
        completed.assert_called_once()
        self.assertEqual(completed.call_args.args[1]["result"], "DENY")

    def test_ai_agent_exception_text_never_leaves_local_host(self):
        # Local executor exceptions may contain paths, credentials or raw
        # payloads. The Core completion must receive only fixed safe codes.
        from datetime import datetime, timedelta, timezone
        secret = "Bearer PRIVATE_AI_AGENT_TOKEN_DO_NOT_EXPORT"
        future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        job = {
            "id": "ai-exception-fixture", "claim_token": "atk_fixture",
            "attempt_id": "att_fixture", "capability": "read_file",
            "arguments": {}, "patterns": [],
            "timeout": 5, "deadline_at": future,
        }
        loop = AgentLoop(agent_root=self.agent_a_tmp)
        cases = (
            (ControlPlaneError(secret), "DENY"),
            (RuntimeError(secret), "ERROR"),
        )
        for thrown, status in cases:
            with self.subTest(exception=type(thrown).__name__):
                with mock.patch.object(loop, "_claim", return_value=[job]), mock.patch(
                    "drlink_ai_agent.execute_local", side_effect=thrown
                ), mock.patch.object(loop, "_complete") as completion:
                    self.assertEqual(loop.run_once(), 1)
                completion.assert_called_once()
                args, kwargs = completion.call_args
                self.assertEqual(args[0], job["id"])
                self.assertEqual(args[1]["result"], status)
                self.assertEqual(kwargs["claim_token"], job["claim_token"])
                self.assertEqual(kwargs["attempt_id"], job["attempt_id"])
                self.assertNotIn(secret, json.dumps(args[1]))
                self.assertTrue(args[1].get("error"))

    def test_core_ai_claim_rejects_coerced_limits_without_leasing(self):
        job_id = self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
        for invalid in (0, -1, True, False, 1.5, "2", None):
            with self.subTest(limit=invalid):
                with self.assertRaisesRegex(
                    ControlPlaneError, "AI job claim limit must be a positive integer"
                ):
                    self.plane.claim_ai_jobs(MACHINE_A, limit=invalid)
                self.assertEqual(self.plane.get_ai_job(job_id)["status"], "queued")
        # Existing bridge backends legitimately request 64 at a time.
        claims = self.plane.claim_ai_jobs(MACHINE_A, limit=64)
        self.assertEqual([job["id"] for job in claims], [job_id])

    def test_signed_ai_completion_rejects_explicit_nonobject_results(self):
        job_id = self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
        claims = mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp, limit=1)["jobs"]
        self.assertEqual([claim["id"] for claim in claims], [job_id])
        claim = claims[0]
        endpoint = self.mgmt_url + "/v1/ai-jobs/complete"
        for invalid in (None, [], "", 0, False):
            with self.subTest(result=invalid):
                with self.assertRaises(mgmt.MgmtSyncError):
                    mgmt._request_json(
                        "POST", endpoint,
                        {"id": job_id, "claim_token": claim["claim_token"],
                         "attempt_id": claim["attempt_id"], "result": invalid},
                        root=self.agent_a_tmp,
                    )
                self.assertEqual(self.plane.get_ai_job(job_id)["status"], "running")
        accepted = mgmt.complete_ai_job_on_server(
            root=self.agent_a_tmp, job_id=job_id,
            claim_token=claim["claim_token"], attempt_id=claim["attempt_id"],
            result={"ok": True},
        )
        self.assertTrue(accepted["ok"])
        self.assertEqual(self.plane.get_ai_job(job_id)["status"], "done")

    def test_stale_attempt_rejection(self):
        job_id = self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
        claimed = self.plane.claim_ai_jobs(MACHINE_A, limit=1)
        token = claimed[0]["claim_token"]
        attempt = claimed[0]["attempt_id"]
        with self.assertRaises(ControlPlaneError):
            self.plane.complete_ai_job(
                job_id,
                MACHINE_A,
                {"result": "ALLOW"},
                claim_token="atk_wrong",
                attempt_id=attempt,
            )
        with self.assertRaises(ControlPlaneError):
            self.plane.complete_ai_job(
                job_id,
                MACHINE_A,
                {"result": "ALLOW"},
                claim_token=token,
                attempt_id="att_stale",
            )
        self.plane.complete_ai_job(
            job_id,
            MACHINE_A,
            {"result": "ALLOW", "ok": True},
            claim_token=token,
            attempt_id=attempt,
        )
        self.assertEqual(self.plane.get_ai_job(job_id)["status"], "done")

    def test_worker_crash_after_claim_not_replayed(self):
        target = self.agent_a_root / "ambiguous.txt"
        job_id = self._enqueue_with_timeout(
            MACHINE_A,
            "write_file",
            1,
            path=str(target),
            content="nope",
        )
        claimed = self.plane.claim_ai_jobs(MACHINE_A, limit=1)
        self.assertEqual(claimed[0]["id"], job_id)
        # Simulate wall-clock expiry while still running / ambiguous.
        past = _ai_job_deadline_iso(utc_now_iso(), -5)
        self.plane.conn.execute(
            "UPDATE ai_jobs SET deadline_at = ? WHERE id = ?", (past, job_id)
        )
        self.plane.commit_if_autonomous()
        again = self.plane.claim_ai_jobs(MACHINE_A, limit=4)
        self.assertEqual(again, [])
        self.assertEqual(self.plane.get_ai_job(job_id)["status"], "recovery_required")
        self.assertFalse(target.exists())

    def test_agent_pre_execution_deadline_check(self):
        loop = AgentLoop(agent_root=self.agent_a_tmp)
        past = _ai_job_deadline_iso(utc_now_iso(), -10)
        fixture = {
            "id": "job_fixture",
            "capability": "write_file",
            "arguments": {
                "path": str(self.agent_a_root / "skip.txt"),
                "content": "should-not-write",
            },
            "patterns": [str(self.agent_a_root) + "/**"],
            "timeout": 5,
            "deadline_at": past,
            "claim_token": "atk_fixture",
            "attempt_id": "att_fixture",
        }
        with mock.patch.object(loop, "_claim", return_value=[fixture]):
            with mock.patch(
                "drlink_ai_agent.execute_local", side_effect=AssertionError("must not execute")
            ) as exec_mock:
                with mock.patch.object(loop, "_complete") as complete_mock:
                    n = loop.run_once()
        self.assertEqual(n, 1)
        exec_mock.assert_not_called()
        complete_mock.assert_called_once()
        args, kwargs = complete_mock.call_args
        self.assertEqual(args[0], "job_fixture")
        self.assertEqual(args[1]["result"], "DENY")
        self.assertIn("deadline", args[1]["error"])

    def test_read_only_normal_success(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        result = self.bridge.call_tool(
            self.principal,
            "read_file",
            {"endpoint": HOST_A, "path": str(self.agent_a_root / "AGENT_MARKER")},
        )
        text = (result.get("content") or [{}])[0].get("text") or ""
        self.assertNotIn("TIMEOUT", text)
        self.assertNotIn("DENY", text)
        data = json.loads(text)
        self.assertIn("content_b64", data)
        rows = list(self.plane.conn.execute("SELECT status FROM ai_jobs"))
        self.assertTrue(any(r["status"] == "done" for r in rows))

    def test_mutating_normal_success_once(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        dest = self.agent_a_root / "written-once.txt"
        result = self.bridge.call_tool(
            self.principal,
            "write_file",
            {"endpoint": HOST_A, "path": str(dest), "content": "once"},
        )
        text = (result.get("content") or [{}])[0].get("text") or ""
        self.assertNotIn("TIMEOUT", text)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_text(encoding="utf-8"), "once")
        done = list(
            self.plane.conn.execute(
                "SELECT status FROM ai_jobs WHERE status = 'done'"
            )
        )
        self.assertEqual(len(done), 1)

    def test_host_fairness_and_isolation(self):
        for _ in range(20):
            self._enqueue_with_timeout(MACHINE_A, "read_file", 60)
        job_b = self._enqueue_with_timeout(MACHINE_B, "read_file", 60)
        t0 = time.monotonic()
        claimed_b = mgmt.claim_ai_jobs_on_server(root=self.agent_b_tmp, limit=4)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 2.0)
        ids = [j["id"] for j in claimed_b.get("jobs") or []]
        self.assertEqual(ids, [job_b])
        claimed_a = mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp, limit=2)
        for job in claimed_a.get("jobs") or []:
            self.assertNotEqual(job["id"], job_b)

    def test_bridge_restart_preserves_terminal_and_queue(self):
        expired = self._enqueue_with_timeout(MACHINE_A, "write_file", 30, path=str(self.agent_a_root / "e.txt"), content="e")
        self.plane.terminalize_ai_job(expired, "timeout")
        queued = self._enqueue_with_timeout(MACHINE_B, "read_file", 60)
        again = MCPBridge(root=self.server_tmp, plane=self.plane, auto_agents=False)
        self.assertFalse(again.auto_agents)
        self.assertEqual(again._agents, {})
        self.assertEqual(self.plane.get_ai_job(expired)["status"], "timeout")
        claimed = self.plane.claim_ai_jobs(MACHINE_B, limit=4)
        self.assertEqual([j["id"] for j in claimed], [queued])
        again.close()


if __name__ == "__main__":
    unittest.main()
