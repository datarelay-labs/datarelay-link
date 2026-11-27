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

    def _account_profile(self, users, reader=None):
        import pwd
        cfg = Path(self.agent_a_tmp, "etc/drlink/ai-execution.json")
        cfg.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        entries = {name:{"uid":pwd.getpwnam(name).pw_uid, "cwd":str(self.agent_a_root),
                         "roots":[str(self.agent_a_root)]} for name in users}
        cfg.write_text(json.dumps({"version":1,"accounts":entries,"reader":reader,
                                  "allow_root":any(item["uid"]==0 for item in entries.values())}))
        cfg.chmod(0o600)
        from drlink_ai_agent import local_execution_profile
        profile = local_execution_profile(self.agent_a_tmp)
        self.assertEqual(profile["state"],"configured")
        return profile

    def test_signed_account_profile_default_and_fail_closed_claim(self):
        import pwd
        user = pwd.getpwuid(os.geteuid()).pw_name
        profile = self._account_profile([user], user if os.geteuid() else None)
        # Only the authenticated Agent claim publishes eligibility.
        mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp, execution_profile=profile)
        self.assertEqual(json.loads(self.plane.conn.execute(
            "SELECT ai_execution_profile_json FROM clients WHERE id=?",(MACHINE_A,)).fetchone()[0]), profile)
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,
            execution={"default":user,"accounts":[user]},confirm=True)
        grant = v24.resolve_managed_execution_grant(self.plane, identity="ops", principal_id=self.principal["id"],
            destination=HOST_A, capability="exec", arguments={}, profile=profile)
        self.assertEqual(grant["action"],"ALLOW")
        job = self.plane.enqueue_ai_job(principal_id=self.principal["id"],
            endpoint_object_id="ep-"+MACHINE_A[:8],client_id=MACHINE_A,capability="exec",
            arguments={"command":"id -u","cwd":str(self.agent_a_root)},patterns=grant["patterns"],
            timeout=30,execution_binding=grant["binding"])
        # An old or bearer-only Agent cannot receive a bound command.
        self.assertEqual(self.plane.claim_ai_jobs(MACHINE_A),[])
        self.assertEqual(self.plane.get_ai_job(job)["status"],"cancelled")
        job = self.plane.enqueue_ai_job(principal_id=self.principal["id"],
            endpoint_object_id="ep-"+MACHINE_A[:8],client_id=MACHINE_A,capability="exec",
            arguments={"command":"id -u","cwd":str(self.agent_a_root)},patterns=grant["patterns"],
            timeout=30,execution_binding=grant["binding"])
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,enabled=False,confirm=True)
        self.assertEqual(mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp,execution_profile=profile)["jobs"],[])
        self.assertEqual(self.plane.get_ai_job(job)["status"],"cancelled")
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,enabled=True,confirm=True)
        self._start_mgmt_worker(self.agent_a_tmp)
        ctx = self.bridge.call_tool(self.principal,"get_host",{"endpoint":HOST_A})
        self.assertEqual(ctx["structuredContent"]["execution_context"]["default_account"],user)
        result = self.bridge.call_tool(self.principal,"exec",{"endpoint":HOST_A,"command":"id -u"})
        self.assertFalse(result.get("isError"),result)
        data=json.loads(result["content"][0]["text"])
        self.assertEqual(data["execution_uid"],os.geteuid())
        self.assertEqual(data["stdout"].strip(),str(os.geteuid()))
        for args in ({"run_as":"not-approved"},{"run_as":""},{"cwd":"/"},{"cwd":None}):
            self.assertTrue(self.bridge.call_tool(self.principal,"exec",
                {"endpoint":HOST_A,"command":"id -u",**args}).get("isError"))
        dest=self.agent_a_root/"bound-file"
        result=self.bridge.call_tool(self.principal,"write_file",{"endpoint":HOST_A,"path":str(dest),"content":"bound"})
        self.assertFalse(result.get("isError"),result)
        self.assertEqual(dest.stat().st_uid,os.geteuid())
        self.assertEqual(dest.read_text(),"bound")

    def test_agent_operator_setup_reviews_and_rolls_back(self):
        import pwd
        import io
        from contextlib import redirect_stdout
        from drlink_control_cli import dispatch
        from drlink_v24_wizard import ScriptedIO,set_wizard_io
        from drlink_ai_agent import local_execution_profile,save_local_execution_profile
        user=pwd.getpwuid(os.geteuid()).pw_name
        path=Path(self.agent_a_tmp,"etc/drlink/ai-execution.json")
        self.assertFalse(path.parent.exists())
        # Actual CLI dispatch; no installed host or production policy touched.
        agent=ControlPlane(self.agent_a_tmp)
        def wizard(confirm):
            answers=[user,str(self.agent_a_root)]
            answers+=["y"] if os.geteuid()==0 else ["1"]
            answers += [confirm]
            scripted=ScriptedIO(answers)
            set_wizard_io(scripted)
            try:
                self.assertEqual(dispatch(["set","agent-execution"],root=self.agent_a_tmp,plane=agent),0)
            finally:
                set_wizard_io(None)
            return "".join(scripted.out)
        try:
            self.assertIn("Cancelled",wizard("n"))
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())
            self.assertIn("awaiting authenticated Agent advertisement",wizard("y"))
            previous=path.read_bytes()
            profile=local_execution_profile(self.agent_a_tmp)
            self.assertEqual(profile["accounts"][user]["uid"],os.geteuid())
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(dispatch(["show","agent-execution"],root=self.agent_a_tmp,plane=agent),0)
            self.assertEqual(json.loads(out.getvalue()),profile)
            with mock.patch("drlink_ai_agent.local_execution_profile",return_value={"version":1,"state":"unavailable"}):
                with self.assertRaisesRegex(ControlPlaneError,"restored"):
                    save_local_execution_profile(self.agent_a_tmp,json.loads(previous),previous=previous)
            self.assertEqual(path.read_bytes(),previous)
            with self.assertRaisesRegex(ControlPlaneError,"changed after review"):
                save_local_execution_profile(self.agent_a_tmp,json.loads(previous),previous=b"stale")
            self.assertEqual(path.read_bytes(),previous)
        finally:
            agent.close()

    def test_running_account_job_revoked_without_another_mcp_call(self):
        import pwd
        user=pwd.getpwuid(os.geteuid()).pw_name
        profile=self._account_profile([user])
        mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp,execution_profile=profile)
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,execution={"default":user,"accounts":[user]},confirm=True)
        self._start_mgmt_worker(self.agent_a_tmp)
        marker=self.agent_a_root/"started"
        late=self.agent_a_root/"late"
        result=[]
        command="touch started; sleep 8; touch late"
        thread=threading.Thread(target=lambda:result.append(self.bridge.call_tool(self.principal,"exec",
            {"endpoint":HOST_A,"command":command})),daemon=True)
        thread.start()
        end=time.monotonic()+6
        while not marker.exists() and time.monotonic()<end:
            time.sleep(.05)
        self.assertTrue(marker.exists(),"job never started")
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,enabled=False,confirm=True)
        thread.join(6)
        self.assertFalse(thread.is_alive(),"job did not stop on grant revocation")
        self.assertTrue(result and result[0].get("isError"),result)
        self.assertFalse(late.exists())
        self.assertIn("DENY",result[0]["content"][0]["text"])
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,enabled=True,confirm=True)
        self.assertFalse(late.exists())

    def test_profile_downgrade_cannot_restore_legacy_service_execution(self):
        import pwd
        user=pwd.getpwuid(os.geteuid()).pw_name
        profile=self._account_profile([user])
        mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp,execution_profile=profile)
        queued=self._enqueue_with_timeout(MACHINE_A,"exec",30,command="id")
        self.assertEqual(mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp)["jobs"],[])
        self.assertEqual(self.plane.get_ai_job(queued)["status"],"cancelled")
        stored=json.loads(self.plane.conn.execute("SELECT ai_execution_profile_json FROM clients WHERE id=?",(MACHINE_A,)).fetchone()[0])
        self.assertEqual(stored["state"],"unavailable")
        self.assertTrue(self.bridge.call_tool(self.principal,"exec",{"endpoint":HOST_A,"command":"id"}).get("isError"))
        mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp,execution_profile=profile)
        self.assertEqual(json.loads(self.plane.conn.execute("SELECT ai_execution_profile_json FROM clients WHERE id=?",(MACHINE_A,)).fetchone()[0])["state"],"configured")

    @unittest.skipUnless(os.geteuid()==0,"two real OS accounts require root in disposable fixtures")
    def test_signed_two_real_os_accounts(self):
        import pwd
        normal=pwd.getpwuid(ROOT.stat().st_uid) if ROOT.stat().st_uid else pwd.getpwnam("nobody")
        self.assertNotEqual(normal.pw_uid,0)
        Path(self.agent_a_tmp).chmod(0o711)
        os.chown(self.agent_a_root,normal.pw_uid,normal.pw_gid)
        profile=self._account_profile([normal.pw_name,"root"],normal.pw_name)
        mgmt.claim_ai_jobs_on_server(root=self.agent_a_tmp,execution_profile=profile)
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,
            execution={"default":normal.pw_name,"accounts":[normal.pw_name,"root"]},confirm=True)
        self._start_mgmt_worker(self.agent_a_tmp)
        for args,uid in (({},normal.pw_uid),({"run_as":"root"},0)):
            response=self.bridge.call_tool(self.principal,"exec",{"endpoint":HOST_A,"command":"id -u",**args})
            self.assertFalse(response.get("isError"),response)
            data=json.loads(response["content"][0]["text"])
            self.assertEqual(data["execution_uid"],uid)
            self.assertEqual(data["stdout"].strip(),str(uid))
        file=self.agent_a_root/"owned-by-user"
        response=self.bridge.call_tool(self.principal,"write_file",{"endpoint":HOST_A,"path":str(file),"content":"fixture"})
        self.assertFalse(response.get("isError"),response)
        self.assertEqual(file.stat().st_uid,normal.pw_uid)
        v24.set_ai_access_rule(self.plane,"ops-"+HOST_A,
            execution={"default":normal.pw_name,"accounts":[normal.pw_name]},confirm=True)
        response=self.bridge.call_tool(self.principal,"exec",{"endpoint":HOST_A,"command":"id -u","run_as":"root"})
        self.assertTrue(response.get("isError"),response)

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
