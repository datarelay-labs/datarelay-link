#!/usr/bin/env python3
"""P0: Real Managed Host AI executor — Server must not impersonate endpoints."""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_ai_agent import AgentLoop  # noqa: E402
from drlink_control_plane import ControlPlane, ControlPlaneError  # noqa: E402
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


def _enroll_agent(agent_root: str, machine_id: str, hostname: str, *, replace_keys: bool = False):
    Path(agent_root, "etc/frp").mkdir(parents=True, exist_ok=True)
    Path(agent_root, "etc/frp/client-state.json").write_text(
        json.dumps({"machine_id": machine_id, "hostname": hostname, "label": hostname}),
        encoding="utf-8",
    )
    key = Path(agent_root, "etc/frp/client-identity.key")
    pub = Path(agent_root, "etc/frp/client-identity.pub")
    if replace_keys:
        for path in (key, pub):
            if path.exists():
                path.unlink()
    if not key.exists():
        MGMT.generate_keypair(key, pub)
        os.chmod(key, 0o600)
    mac = MGMT.new_mac_key()
    mac_path = Path(agent_root, "etc/frp/client-identity.mac")
    mac_path.write_text(mac, encoding="utf-8")
    os.chmod(mac_path, 0o600)
    return pub.read_text(encoding="utf-8"), mac


class RealManagedHostExecutorTests(unittest.TestCase):
    def setUp(self):
        self.server_tmp = tempfile.mkdtemp(prefix="drlink-p5-srv-")
        self.agent_a_tmp = tempfile.mkdtemp(prefix="drlink-p5-a-")
        self.agent_b_tmp = tempfile.mkdtemp(prefix="drlink-p5-b-")
        os.environ["DRLINK_TEST_ROOT"] = self.server_tmp
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.server_tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        for key in ("DRLINK_AI_TEST_LOCAL_EXEC", "DRLINK_AI_TEST_LOCAL_AGENTS", "DRLINK_AI_LOCAL_EXEC"):
            os.environ.pop(key, None)
        Path(self.server_tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.server_tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        self.server_marker = Path(self.server_tmp) / "var" / "lib" / "drlink" / "SERVER_MARKER"
        self.server_marker.parent.mkdir(parents=True, exist_ok=True)
        self.server_marker.write_text("SERVER_ONLY\n", encoding="utf-8")
        self.agent_a_root = Path(self.agent_a_tmp) / "workspace"
        self.agent_b_root = Path(self.agent_b_tmp) / "workspace"
        self.agent_a_root.mkdir(parents=True)
        self.agent_b_root.mkdir(parents=True)
        (self.agent_a_root / "AGENT_MARKER").write_text("AGENT_A\n", encoding="utf-8")
        (self.agent_b_root / "AGENT_MARKER").write_text("AGENT_B\n", encoding="utf-8")
        (self.agent_a_root / "hostname").write_text("host-A\n", encoding="utf-8")
        pub_a, mac_a = _enroll_agent(self.agent_a_tmp, MACHINE_A, HOST_A)
        pub_b, mac_b = _enroll_agent(self.agent_b_tmp, MACHINE_B, HOST_B)
        self.plane = ControlPlane(self.server_tmp)
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

    def _text(self, result: dict) -> str:
        content = (result.get("content") or [{}])[0]
        return str(content.get("text") or "")

    def _call(self, capability: str, endpoint: str = HOST_A, **arguments) -> dict:
        args = dict(arguments)
        if capability != "list_hosts":
            args.setdefault("endpoint", endpoint)
        return self.bridge.call_tool(self.principal, capability, args)

    def test_production_bridge_does_not_start_local_agents(self):
        self.assertFalse(self.bridge.auto_agents)
        self.assertEqual(self.bridge._agents, {})
        with self.assertRaises(RuntimeError):
            self.bridge.auto_agents = True
            self.bridge.refresh_local_agents("http://127.0.0.1:9")

    def test_no_worker_means_timeout_without_server_side_effect(self):
        # Path is in-scope for policy; without a Managed Host worker the bridge
        # must TIMEOUT and must not create the file via Server-local execute_local.
        target = self.agent_a_root / "server-must-not-create.txt"
        if target.exists():
            target.unlink()
        text = self._text(
            self._call("write_file", path=str(target), content="LEAK")
        )
        self.assertIn("TIMEOUT", text)
        self.assertFalse(target.exists())
        self.assertEqual(self.server_marker.read_text(encoding="utf-8"), "SERVER_ONLY\n")

    def test_mgmt_worker_get_system_info_delivers(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        text = self._text(self._call("get_system_info"))
        self.assertNotIn("endpoint unavailable", text)
        self.assertNotIn("TIMEOUT", text)
        self.assertIn("sysname", text)
        self.assertIn(os.uname().sysname, text)

    def test_mgmt_worker_reads_agent_marker_not_server(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        text = self._text(
            self._call("read_file", path=str(self.agent_a_root / "AGENT_MARKER"))
        )
        data = json.loads(text)
        content = base64.b64decode(data["content_b64"]).decode("utf-8")
        self.assertEqual(content, "AGENT_A\n")
        self.assertNotIn("SERVER_ONLY", content)

    def test_mgmt_worker_writes_only_on_agent(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        dest = self.agent_a_root / "written-by-ai.txt"
        server_shadow = Path(self.server_tmp) / "workspace" / "written-by-ai.txt"
        text = self._text(self._call("write_file", path=str(dest), content="from-mcp"))
        self.assertIn(str(dest), text)
        self.assertNotIn("TIMEOUT", text)
        self.assertNotIn("DENY", text)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_text(encoding="utf-8"), "from-mcp")
        self.assertFalse(server_shadow.exists())

    def test_invalid_core_ai_job_enqueue_fails_before_queue_mutation(self):
        # Source admission must not create Jobs that the strict claim reader
        # can never lease to an Agent.
        args = {
            "principal_id": None,
            "endpoint_object_id": "ep-a",
            "client_id": MACHINE_A,
            "capability": "read_file",
            "arguments": {"path": str(self.agent_a_root / "AGENT_MARKER")},
            "patterns": [str(self.agent_a_root) + "/**"],
            "timeout": 60,
        }
        invalid_cases = (
            {"arguments": []}, {"arguments": False},
            {"patterns": "unbounded"},
            {"patterns": [17]}, {"patterns": [""]},
            {"patterns": ["bad" + chr(0) + "scope"]},
            {"patterns": ["valid"] * 129},
            {"timeout": 0}, {"timeout": -1}, {"timeout": True},
            {"timeout": 1.5}, {"timeout": "5"}, {"timeout": 3601},
            {"arguments": {"score": float("nan")}},
        )
        before = self.plane.conn.execute(
            "SELECT COUNT(*) FROM ai_jobs"
        ).fetchone()[0]
        for bad in invalid_cases:
            with self.subTest(case=str(bad)[:70]):
                with self.assertRaises(ControlPlaneError):
                    self.plane.enqueue_ai_job(**{**args, **bad})
                count = self.plane.conn.execute(
                    "SELECT COUNT(*) FROM ai_jobs"
                ).fetchone()[0]
                self.assertEqual(count, before)
        # Preserve the explicit optional Core timeout default.
        job_id = self.plane.enqueue_ai_job(
            **{**args, "timeout": None, "patterns": tuple(args["patterns"])}
        )
        row = self.plane.conn.execute(
            "SELECT payload_json FROM ai_jobs WHERE id=?", (job_id,)
        ).fetchone()
        payload = json.loads(row["payload_json"])
        self.assertEqual(payload["timeout"], 30)
        self.assertEqual(payload["patterns"], args["patterns"])

    def test_corrupt_core_ai_job_payload_never_consumes_agent_lease(self):
        # A queued Core AI Job is not authority to hand malformed fields to an
        # Agent. Keep the claim unconsumed, even when SQLite content is damaged.
        job_id = self.plane.enqueue_ai_job(
            principal_id=None, endpoint_object_id="ep-a",
            client_id=MACHINE_A, capability="read_file",
            arguments={"path": str(self.agent_a_root / "AGENT_MARKER")},
            patterns=[str(self.agent_a_root) + "/**"], timeout=60,
        )
        row = self.plane.conn.execute(
            "SELECT payload_json FROM ai_jobs WHERE id=?", (job_id,)
        ).fetchone()
        original = row["payload_json"]
        invalid = (
            "", "{", "[]", "null", "false",
            '{"arguments":[],"patterns":[],"timeout":5}',
            '{"arguments":{},"patterns":"invalid","timeout":5}',
            '{"arguments":{},"patterns":[],"timeout":"5"}',
            '{"arguments":{},"patterns":[],"timeout":NaN}',
            '{"arguments":{},"arguments":true,"patterns":[],"timeout":5}',
        )
        for payload in invalid:
            self.plane.conn.execute(
                "UPDATE ai_jobs SET payload_json=? WHERE id=?", (payload, job_id)
            )
            self.plane.conn.commit()
            with self.subTest(payload=payload[:55]):
                try:
                    claimed = self.plane.claim_ai_jobs(MACHINE_A, limit=1)
                except Exception as exc:
                    self.fail(
                        "Corrupt queued AI Job escaped Core claim as %s"
                        % type(exc).__name__
                    )
                self.assertEqual(claimed, [])
                state = self.plane.conn.execute(
                    "SELECT status,claim_token,attempt_id,claimed_at "
                    "FROM ai_jobs WHERE id=?", (job_id,)
                ).fetchone()
                self.assertEqual(state["status"], "queued")
                self.assertFalse(state["claim_token"])
                self.assertFalse(state["attempt_id"])
                self.assertIsNone(state["claimed_at"])
            # Reset only this disposable fixture for the next malformed case.
            self.plane.conn.execute(
                "UPDATE ai_jobs SET status='queued',claim_token=NULL,"
                "attempt_id=NULL,claimed_at=NULL WHERE id=?", (job_id,)
            )
            self.plane.conn.commit()
        self.plane.conn.execute(
            "UPDATE ai_jobs SET payload_json=? WHERE id=?", (original, job_id)
        )
        self.plane.conn.commit()
        self.assertEqual(
            [item["id"] for item in self.plane.claim_ai_jobs(MACHINE_A, limit=1)],
            [job_id],
        )

    def test_corrupt_ai_head_of_line_does_not_starve_valid_claim(self):
        # Keep the response bound to one job, but inspect a bounded window
        # beyond corrupted entries so another ready Job can still progress.
        def enqueue():
            return self.plane.enqueue_ai_job(
                principal_id=None, endpoint_object_id="ep-a",
                client_id=MACHINE_A, capability="read_file",
                arguments={"path": str(self.agent_a_root / "AGENT_MARKER")},
                patterns=[str(self.agent_a_root) + "/**"], timeout=60,
            )

        corrupt = enqueue()
        healthy = enqueue()
        self.plane.conn.execute(
            "UPDATE ai_jobs SET payload_json=?,created_at=? WHERE id=?",
            ("{", "2000-01-01T00:00:00Z", corrupt),
        )
        self.plane.conn.commit()
        claims = self.plane.claim_ai_jobs(MACHINE_A, limit=1)
        self.assertEqual([item["id"] for item in claims], [healthy])
        status = self.plane.conn.execute(
            "SELECT status,claim_token FROM ai_jobs WHERE id=?", (corrupt,)
        ).fetchone()
        self.assertEqual(status["status"], "queued")
        self.assertFalse(status["claim_token"])

    def test_host_isolation_claim(self):
        job_id = self.plane.enqueue_ai_job(
            principal_id=None,
            endpoint_object_id="ep-a",
            client_id=MACHINE_A,
            capability="read_file",
            arguments={"path": str(self.agent_a_root / "AGENT_MARKER")},
            patterns=[str(self.agent_a_root) + "/**"],
            timeout=5,
        )
        claimed_b = mgmt.claim_ai_jobs_on_server(root=self.agent_b_tmp, limit=4)
        self.assertEqual(claimed_b.get("jobs"), [])
        claimed_a = mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp, limit=4)
        ids = [j["id"] for j in claimed_a.get("jobs") or []]
        self.assertIn(job_id, ids)

    def test_worker_restart_resumes_on_same_identity(self):
        stop = self._start_mgmt_worker(self.agent_a_tmp)
        stop.set()
        time.sleep(0.2)
        self._start_mgmt_worker(self.agent_a_tmp)
        text = self._text(
            self._call("read_file", path=str(self.agent_a_root / "AGENT_MARKER"))
        )
        content = base64.b64decode(json.loads(text)["content_b64"]).decode("utf-8")
        self.assertEqual(content, "AGENT_A\n")

    def test_bridge_does_not_create_local_agent_loops(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        self.assertEqual(self.bridge._agents, {})
        again = MCPBridge(root=self.server_tmp, plane=self.plane, auto_agents=False)
        self.assertEqual(again._agents, {})
        self.assertFalse(again.auto_agents)
        again.close()

    def test_revoked_host_cannot_claim(self):
        self.plane.remove_client(MACHINE_A, revoke_only=True)
        with self.assertRaises(Exception):
            mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp, limit=1)

    def test_same_name_replacement_cannot_claim_old_jobs(self):
        job_id = self.plane.enqueue_ai_job(
            principal_id=None,
            endpoint_object_id="ep-a",
            client_id=MACHINE_A,
            capability="get_system_info",
            arguments={},
            patterns=[],
            timeout=5,
        )
        self.plane.remove_client(MACHINE_A)
        replacement = "cccccccccccccccccccccccccccccccc"
        pub, mac = _enroll_agent(
            self.agent_a_tmp, replacement, HOST_A, replace_keys=True
        )
        self.plane.upsert_client(replacement, label=HOST_A, hostname=HOST_A)
        self.verifier.enroll(replacement, pub, mac_key=mac, hostname=HOST_A)
        claimed = mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp, limit=8)
        ids = [j["id"] for j in claimed.get("jobs") or []]
        self.assertNotIn(job_id, ids)

    def test_path_scope_enforced_on_agent(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        outside = Path(self.agent_a_tmp) / "outside-scope.txt"
        outside.write_text("secret\n", encoding="utf-8")
        text = self._text(self._call("read_file", path=str(outside)))
        self.assertIn("DENY", text)
        self.assertNotIn("secret", text)

    def test_command_execution_reports_agent_marker(self):
        self._start_mgmt_worker(self.agent_a_tmp)
        text = self._text(
            self._call(
                "exec",
                command="cat %s" % (self.agent_a_root / "hostname"),
            )
        )
        self.assertIn("host-A", text)
        self.assertNotIn("SERVER_ONLY", text)

    def test_linux_service_unit_ships_with_product(self):
        unit = ROOT / "client" / "drlink-ai-agent.service"
        self.assertTrue(unit.is_file())
        text = unit.read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/bin/python3 /usr/local/lib/drlink/drlink_ai_agent.py", text)
        self.assertIn("Restart=always", text)
        self.assertNotIn("Environment=", text)
        install = (ROOT / "install-client.sh").read_text(encoding="utf-8")
        self.assertIn("drlink-ai-agent.service", install)
        uninstall = (ROOT / "uninstall-client.sh").read_text(encoding="utf-8")
        self.assertIn("drlink-ai-agent.service", uninstall)
        # macOS has no durable AI executor in v2.4, but it does ship the
        # independent lifecycle worker required for Agent connectivity truth.
        self.assertIn("macOS intentionally has no durable AI executor in v2.4", install)
        self.assertIn("frp_macos_lifecycle_install", install)


if __name__ == "__main__":
    unittest.main()
