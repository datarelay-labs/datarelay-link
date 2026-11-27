#!/usr/bin/env python3
"""Real loopback HTTP tests for Native MCP full control in disposable fixtures.

Temporary static bearer identities, policy DB, files and local bare Git only.
This is protocol integration evidence, not installed ChatGPT user acceptance.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import pwd
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_cli import dispatch
from drlink_control_plane import ControlPlane
from drlink_mcp_bridge import MCPBridge, MCP_PROTOCOL_VERSION, ThreadingHTTPServer, make_handler
import drlink_v24 as v24


class NativeFullControlPublicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-native-public-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        account = pwd.getpwuid(os.geteuid())
        self.env = patch.dict(os.environ, {
            "DRLINK_TEST_ROOT": str(self.root), "DRLINK_CONFIRM": "yes",
            "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
            "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1",
            "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED": "1",
            "DRLINK_MCP_SERVER_EXEC_USER": account.pw_name,
            "DRLINK_MCP_SERVER_ALLOWED_ROOTS": str(self.root),
            "DRLINK_MCP_SERVER_DEFAULT_CWD": str(self.root),
            "DRLINK_MCP_SERVER_ADMIN_ENABLED": "1" if os.geteuid() == 0 else "0",
            "DRLINK_MCP_NATIVE_PUBLIC_URL": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.plane = ControlPlane(str(self.root))
        self.addCleanup(self.plane.close)
        self.tokens = {}
        self.identities = {"owner": "native-public-owner", "other": "native-public-other"}
        for key, name in self.identities.items():
            self.plane.set_ai_principal(name, enabled=True)
            output = self.cli("set", "ai-identity", name, "rotate")
            self.tokens[key] = next(line.split(" ", 1)[1].strip()
                                    for line in output.splitlines() if line.startswith("Token: "))
        self.cli("set", "permission-object", "native-public-permissions", "permissions",
                 "host-info,process-read,file-read,file-write,file-upload,file-download,command-exec")
        for key, name in self.identities.items():
            self.cli("set", "ai-access", self.rule(key), "source", name, "destination", "server:self", "permission",
                     "native-public-permissions", "paths", str(self.root) + "/**", "enabled")
        config = self.root / "etc" / "drlink" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({
            "public_host": "127.0.0.1", "deployment_mode": "single443",
            "frp_control_public_port": 443,
        }), encoding="utf-8")
        self.bridge = MCPBridge(root=str(self.root), plane=self.plane)
        self.addCleanup(self.bridge.close)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.bridge))
        self.bridge.listen_host = "127.0.0.1"
        self.bridge.listen_port = self.httpd.server_address[1]
        self.url = "http://127.0.0.1:%s/mcp" % self.bridge.listen_port
        self.http_thread = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.http_thread.start()
        self.addCleanup(self.stop_http)
        self.request_id = 0

    @staticmethod
    def rule(identity):
        return "native-public-%s-rule" % identity

    def stop_http(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.http_thread.join(timeout=2)

    def cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = dispatch(list(args), root=str(self.root))
        self.assertEqual(code, 0, errors.getvalue())
        return output.getvalue()

    def rpc(self, method, params=None, *, identity="owner", bearer=None):
        self.request_id += 1
        params = dict(params or {})
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        headers = {
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION, "Mcp-Method": method,
            "Connection": "close",
        }
        if method == "tools/call":
            headers["Mcp-Name"] = params["name"]
        token = bearer if bearer is not None else self.tokens.get(identity)
        if token:
            headers["Authorization"] = "Bearer " + token
        body = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
        request = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}, dict(response.headers)
        except urllib.error.HTTPError as error:
            raw = error.read()
            return error.code, json.loads(raw) if raw else {}, dict(error.headers)

    def call(self, name, arguments, *, identity="owner"):
        status, body, _ = self.rpc(
            "tools/call", {"name": name, "arguments": arguments}, identity=identity)
        self.assertEqual(status, 200, body)
        self.assertNotIn("error", body, body)
        return body["result"]

    def allowed(self, name, arguments, *, identity="owner"):
        result = self.call(name, arguments, identity=identity)
        self.assertFalse(result.get("isError"), result)
        self.assertIn("structuredContent", result)
        return result["structuredContent"]

    def denied(self, name, arguments, *, identity="owner"):
        result = self.call(name, arguments, identity=identity)
        self.assertTrue(result.get("isError"), result)
        self.assertIn("DENY", json.dumps(result))
        return result

    def completed(self, job, *, identity="owner"):
        deadline = time.monotonic() + 8
        while job["state"] != "completed" and time.monotonic() < deadline:
            job = self.allowed("server_job_poll", {
                "job_id": job["job_id"], "wait_ms": 100,
            }, identity=identity)
        self.assertEqual(job["state"], "completed", job)
        return job

    def command(self, argv, *, cwd=None, identity="owner"):
        return self.completed(self.allowed("server_run", {
            "cwd": str(cwd or self.root), "argv": argv, "wait_ms": 1000,
            "timeout_seconds": 15,
        }, identity=identity), identity=identity)

    def assert_activity(self, capability, result, *, identity="owner"):
        rows = self.plane.list_ai_activity(
            principal=self.identities[identity], endpoint="server:self")
        self.assertTrue(any(row["capability"] == capability and row["result"] == result
                            for row in rows), (capability, result, rows))
        audit = self.plane.list_audit(principal=self.identities[identity])
        self.assertTrue(any(row["action"] == "ai " + capability and row["result"] == result
                            for row in audit), (capability, result, audit))

    def test_discovery_typed_optional_schemas_and_truthful_annotations(self):
        status, body, _ = self.rpc("tools/list")
        self.assertEqual(status, 200, body)
        tools = {tool["name"]: tool for tool in body["result"]["tools"]}
        for name in ("server_exec", "server_run", "server_git", "server_job_poll",
                     "server_job_input", "server_job_stop", "server_read_file",
                     "server_write_file", "server_delete_file"):
            self.assertIn(name, tools)
            self.assertIn({"type": "oauth2", "scopes": ["drlink.ai", "offline_access"]}, tools[name]["securitySchemes"])
        for name, field in (("server_exec", "command"), ("server_run", "argv"),
                            ("server_git", "argv")):
            schema = tools[name]["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertEqual(set(schema["required"]), {field})
            self.assertEqual(schema["properties"]["cwd"]["type"], "string")
            for option, low, high in (("wait_ms", 0, 5000), ("timeout_seconds", 1, 86400)):
                self.assertNotIn(option, schema["required"])
                self.assertEqual(schema["properties"][option]["type"], "integer")
                self.assertEqual(schema["properties"][option]["minimum"], low)
                self.assertEqual(schema["properties"][option]["maximum"], high)
            if field == "argv":
                self.assertEqual(schema["properties"][field]["type"], "array")
                self.assertEqual(schema["properties"][field]["items"]["type"], "string")
            else:
                self.assertEqual(schema["properties"][field]["type"], "string")
        for name in ("server_exec", "server_run", "server_git", "server_job_input"):
            hints = tools[name]["annotations"]
            self.assertFalse(hints["readOnlyHint"], name)
            self.assertTrue(hints["destructiveHint"], name)
            self.assertTrue(hints["openWorldHint"], name)
        poll = tools["server_job_poll"]["inputSchema"]
        self.assertEqual(set(poll["required"]), {"job_id"})
        for field in ("stdout_cursor", "stderr_cursor", "wait_ms"):
            self.assertEqual(poll["properties"][field]["type"], "integer")
            self.assertNotIn(field, poll["required"])
        process_input = tools["server_job_input"]["inputSchema"]
        self.assertEqual(set(process_input["required"]), {"job_id"})
        self.assertEqual(process_input["properties"]["data"]["type"], "string")
        self.assertEqual(process_input["properties"]["eof"]["type"], "boolean")
        self.assertEqual(set(tools["server_job_stop"]["inputSchema"]["required"]), {"job_id"})

    def test_no_authentication_rejects_before_side_effects(self):
        marker = self.root / "unauthenticated-marker"
        for bearer in (None, "invalid-isolated-fixture-token"):
            status, body, headers = self.rpc("tools/call", {
                "name": "server_exec",
                "arguments": {"cwd": str(self.root), "command": "touch unauthenticated-marker"},
            }, identity=None, bearer=bearer)
            self.assertEqual(status, 401, body)
            self.assertIn("resource_metadata=", headers.get("WWW-Authenticate", ""))
            self.assertFalse(marker.exists())

    def test_account_rule_binding_is_atomic_and_not_usable_by_legacy_executor(self):
        binding = {"default": "aella", "accounts": ["aella", "root"]}
        v24.set_ai_access_rule(self.plane, self.rule("owner"), execution=binding, confirm=True)
        row = self.plane.conn.execute("SELECT * FROM ai_policy_rules WHERE name=?", (self.rule("owner"),)).fetchone()
        self.assertEqual(v24.ai_rule_execution(row), binding)
        v24.set_ai_access_rule(self.plane, self.rule("owner"), enabled=True, confirm=True)
        row = self.plane.conn.execute("SELECT * FROM ai_policy_rules WHERE name=?", (self.rule("owner"),)).fetchone()
        self.assertEqual(v24.ai_rule_execution(row), binding)
        for invalid in ({"default":"root","accounts":["aella"]}, {"default":"aella","accounts":["aella","aella"]},
                        {"default":"aella","accounts":["aella","root "]}):
            with self.assertRaises(v24.ControlPlaneError):
                v24.set_ai_access_rule(self.plane, self.rule("owner"), execution=invalid, confirm=True)
        result = v24.authorize_ai_capability_v24(self.plane, identity=self.identities["owner"],
                     destination="server:self", capability="exec", operand=str(self.root))
        self.assertEqual(result["action"], "DENY")
        self.assertEqual(v24.authorize_ai_capability_v24(self.plane, identity=self.identities["owner"],
                     destination="server:self", capability="get_system_info")["action"], "ALLOW")

    def test_complete_execution_grants_do_not_combine_account_and_path(self):
        name = self.identities["owner"]
        a = str(self.root / "a")
        b = str(self.root / "b")
        (self.root / "a").mkdir()
        (self.root / "b").mkdir()
        v24.set_ai_access_rule(self.plane, self.rule("owner"), paths=[a+"/**"],
            execution={"default":"aella","accounts":["aella"]}, confirm=True)
        v24.set_ai_access_rule(self.plane, "second-execution", source=name, destination="server:self",
            permission="native-public-permissions", paths=[b+"/**"], enabled=True,
            execution={"default":"root","accounts":["root"]}, confirm=True)
        def decide(cap="read_file", operand=a+"/sample", run_as=None, local=("aella","root")):
            return v24.resolve_ai_execution_grant(self.plane, identity=name, destination="server:self",
                capability=cap, operand=operand, run_as=run_as, local_accounts=local)
        self.assertEqual(decide()["account"], "aella")
        self.assertEqual(decide(run_as="root")["action"], "DENY")
        self.assertEqual(decide(operand=b+"/sample", run_as="root")["account"], "root")
        self.assertEqual(decide(operand=b+"/sample", run_as="root", local=("aella",))["action"], "DENY")
        self.assertEqual(decide(run_as="ubuntu")["action"], "DENY")
        self.assertEqual(decide(cap="exec", operand=None)["reason_code"], "AMBIGUOUS_DEFAULT")
        self.assertEqual(decide(cap="exec", operand=None, run_as="aella")["account"], "aella")
        self.assertEqual(decide(cap="exec", operand=None, run_as="root")["account"], "root")
        self.assertEqual(decide(cap="exec", operand=None, run_as="root", local=("aella",))["action"], "DENY")
        self.plane.conn.execute("UPDATE ai_policy_rules SET enabled=0 WHERE name='second-execution'")
        self.plane.conn.commit()
        self.assertEqual(decide(cap="exec", operand=None)["account"], "aella")
        self.assertEqual(decide(cap="exec", operand=None, run_as="root")["action"], "DENY")

    def test_legacy_rule_does_not_grant_newly_eligible_accounts(self):
        name = self.identities["owner"]
        def decide(run_as=None, legacy=None):
            return v24.resolve_ai_execution_grant(self.plane, identity=name, destination="server:self",
                capability="exec", operand=None, run_as=run_as, local_accounts=["aella","root"],
                legacy_account=legacy)
        self.assertEqual(decide(legacy="aella")["account"], "aella")
        self.assertEqual(decide(run_as="root", legacy="aella")["action"], "DENY")
        self.assertEqual(decide()["action"], "DENY")

    def test_revoked_running_job_is_terminated_without_another_mcp_call(self):
        job = self.allowed("server_run", {"argv":[sys.executable,"-c","import time; time.sleep(60)"],"wait_ms":0})
        runtime = self.bridge._full_control_runtime(__import__("drlink_mcp_full_control"))
        original = runtime.jobs[job["job_id"]]
        self.cli("set","ai-access",self.rule("owner"),"disabled")
        self.assertTrue(original.done.wait(4), "revoked job continued without client polling")
        self.assertTrue(original.revoked)
        self.assertLess(original.process.returncode, 0)
        self.cli("set","ai-access",self.rule("owner"),"enabled")
        self.denied("server_job_poll", {"job_id":job["job_id"]})

    def test_execution_snapshot_never_mixes_concurrent_rule_versions(self):
        user = pwd.getpwuid(os.geteuid()).pw_name
        v24.set_ai_access_rule(self.plane, self.rule("owner"), paths=[str(self.root)+"/**"],
            execution={"default":user,"accounts":[user]}, confirm=True)
        owner = self.identities["owner"]
        owner_id = self.plane.get_principal(owner)["id"]
        separate = ControlPlane(str(self.root))
        try:
            original = v24._matched_ai_rule_rows
            def change_between_reads(plane, names):
                separate.conn.execute("UPDATE ai_policy_rules SET enabled=0 WHERE name=?", (self.rule("owner"),))
                separate.conn.commit()
                return original(plane, names)
            with patch.object(v24, "_matched_ai_rule_rows", side_effect=change_between_reads):
                decision = v24.resolve_ai_execution_grant(self.plane, identity=owner,
                    principal_id=owner_id, destination="server:self", capability="exec",
                    local_accounts=[user], operand=str(self.root))
            self.assertEqual(decision["action"], "ALLOW")  # one coherent pre-change snapshot
            self.assertFalse(self.plane.conn.in_transaction)
            self.assertEqual(v24.resolve_ai_execution_grant(self.plane, identity=owner,
                principal_id=owner_id, destination="server:self", capability="exec",
                local_accounts=[user], operand=str(self.root))["action"], "DENY")
            self.assertEqual(v24.resolve_ai_execution_grant(self.plane, identity=owner,
                principal_id="replaced-id", destination="server:self", capability="exec",
                local_accounts=[user], operand=str(self.root))["reason_code"], "AI_IDENTITY_CHANGED")
        finally:
            separate.close()

    def test_migrated_profile_only_retains_unchanged_legacy_grants(self):
        user = pwd.getpwuid(os.geteuid())
        rule = self.plane.conn.execute("SELECT * FROM ai_policy_rules WHERE name=?", (self.rule("owner"),)).fetchone()
        fingerprint = v24.legacy_execution_rule_fingerprint(self.plane, rule)
        snapshots = v24.snapshot_legacy_server_execution_rules(self.plane)
        self.assertEqual(snapshots[rule["id"]], fingerprint)
        self.assertEqual(len(snapshots), 2)
        profile = {user.pw_name: {"uid":user.pw_uid,"cwd":str(self.root),"roots":[str(self.root)]}}
        env = {"DRLINK_MCP_SERVER_EXEC_ACCOUNTS":json.dumps(profile),
               "DRLINK_MCP_SERVER_EXEC_USER":"",
               "DRLINK_MCP_SERVER_ALLOWED_ROOTS":"/",
               "DRLINK_MCP_SERVER_LEGACY_ACCOUNT":user.pw_name,
               "DRLINK_MCP_SERVER_LEGACY_RULE_IDS":json.dumps({rule["id"]:fingerprint})}
        with patch.dict(os.environ, env):
            result = self.completed(self.allowed("server_run", {"argv":["id","-u"]}))
            self.assertEqual(result["stdout"]["text"].strip(), str(user.pw_uid))
            self.denied("server_run", {"argv":["pwd"],"cwd":"/"})
            self.denied("server_run", {"argv":["id"]}, identity="other")
            v24.set_ai_access_rule(self.plane, self.rule("owner"), paths=["/**"], confirm=True)
            self.denied("server_run", {"argv":["id"]})
            v24.set_ai_access_rule(self.plane, self.rule("owner"),
                execution={"default":user.pw_name,"accounts":[user.pw_name]}, confirm=True)
            self.assertEqual(self.completed(self.allowed("server_run", {"argv":["id"]}))["exit_status"],0)
            self.denied("server_run", {"argv":["pwd"],"cwd":"/"})
            self.denied("server_read_file", {"path":"/etc/passwd"})

    def test_explicit_binding_uses_current_uid_and_does_not_expand_legacy_rules(self):
        user = pwd.getpwuid(os.geteuid())
        profile = {user.pw_name: {"uid": user.pw_uid, "cwd": str(self.root)}}
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_EXEC_ACCOUNTS": json.dumps(profile)}):
            self.denied("server_run", {"argv": ["id"]})
            v24.set_ai_access_rule(self.plane, self.rule("owner"), confirm=True,
                execution={"default":user.pw_name,"accounts":[user.pw_name]})
            ctx = self.allowed("get_server", {})["execution_context"]
            self.assertEqual(ctx["default_account"], user.pw_name)
            self.assertEqual([item["account"] for item in ctx["accounts"]], [user.pw_name])
            job = self.completed(self.allowed("server_run", {"argv":["id","-u"]}))
            self.assertEqual(job["stdout"]["text"].strip(), str(user.pw_uid))
            self.denied("server_run", {"argv":["id"], "run_as":"nonexistent-account"})
            self.denied("server_run", {"argv":["id"], "run_as":""})
            self.denied("server_run", {"argv":["id"]}, identity="other")
            with patch.dict(os.environ, {"DRLINK_MCP_SERVER_EXEC_ACCOUNTS": json.dumps(
                    {user.pw_name: {"uid":user.pw_uid+1, "cwd":str(self.root)}})}):
                self.denied("server_run", {"argv":["id"], "run_as":user.pw_name})

    @unittest.skipUnless(os.geteuid() == 0, "actual two-account fixture requires root")
    def test_real_two_account_uid_file_owner_and_job_grant(self):
        ordinary = pwd.getpwuid(ROOT.stat().st_uid) if ROOT.stat().st_uid else pwd.getpwnam("nobody")
        admin = pwd.getpwuid(0)
        if ordinary.pw_uid == 0:
            self.fail("ordinary fixture account is privileged")
        # This is a new disposable test directory, not an installed service.
        self.root.chmod(0o711)
        workspace = self.root / "account-fixture"
        workspace.mkdir(mode=0o700)
        os.chown(workspace, ordinary.pw_uid, ordinary.pw_gid)
        names = sorted([ordinary.pw_name, admin.pw_name])
        local = {entry.pw_name: {"uid":entry.pw_uid, "cwd":str(workspace)}
                 for entry in (ordinary, admin)}
        v24.set_ai_access_rule(self.plane, self.rule("owner"), confirm=True,
            execution={"default":ordinary.pw_name,"accounts":names})
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_EXEC_ACCOUNTS":json.dumps(local)}):
            ctx = self.allowed("get_server", {})["execution_context"]
            self.assertEqual(ctx["default_account"], ordinary.pw_name)
            self.assertEqual({x["uid"] for x in ctx["accounts"]}, {0, ordinary.pw_uid})
            for name, uid in ((ordinary.pw_name, ordinary.pw_uid),(admin.pw_name, 0)):
                args = {"argv":["id","-u"]}
                if uid == 0:
                    args["run_as"] = name
                result = self.completed(self.allowed("server_run", args))
                self.assertEqual(result["stdout"]["text"].strip(), str(uid))
                self.assertEqual(result["execution_user"], name)
            file = workspace / "owned.txt"
            self.allowed("server_write_file", {"path":str(file),"content":"account test"})
            self.assertEqual(file.stat().st_uid, ordinary.pw_uid)
            self.allowed("server_read_file", {"path":str(file),"run_as":admin.pw_name})
            self.denied("server_run", {"argv":["id"],"run_as":admin.pw_name}, identity="other")
            self.cli("set", "permission-object", "reader", "permissions", "host-info,file-read")
            self.cli("set", "ai-access", self.rule("other"), "permission", "reader")
            with patch.dict(os.environ, {"DRLINK_MCP_SERVER_READ_USER":ordinary.pw_name}):
                self.allowed("server_read_file", {"path":str(file)}, identity="other")
                self.denied("server_read_file", {"path":str(file),"run_as":admin.pw_name}, identity="other")
                self.denied("server_run", {"argv":["id"]}, identity="other")
            with patch.dict(os.environ, {"DRLINK_MCP_SERVER_ADMIN_ENABLED":"0"}):
                self.denied("server_run", {"argv":["id"], "run_as":admin.pw_name})
                self.assertEqual(self.completed(self.allowed("server_run", {"argv":["id","-u"]}))["stdout"]["text"].strip(),
                                 str(ordinary.pw_uid))
            job = self.allowed("server_run", {"argv":[sys.executable,"-c","import time; time.sleep(60)"],"wait_ms":0})
            self.denied("server_job_poll", {"job_id":job["job_id"],"run_as":admin.pw_name})
            v24.set_ai_access_rule(self.plane, self.rule("owner"), confirm=True,
                execution={"default":admin.pw_name,"accounts":[admin.pw_name]})
            self.denied("server_job_poll", {"job_id":job["job_id"]})
            runtime = self.bridge._full_control_runtime(__import__("drlink_mcp_full_control"))
            original = runtime.jobs[job["job_id"]]
            self.assertTrue(original.done.wait(3))
            self.assertLess(original.process.returncode, 0)

    def test_discover_context_and_omit_cwd_without_widening_scope(self):
        ctx = self.allowed("get_server", {})["execution_context"]
        self.assertEqual(ctx["state"], "configured")
        self.assertEqual(ctx["default_cwd"], str(self.root))
        self.assertEqual(ctx["default_account"], pwd.getpwuid(os.geteuid()).pw_name)
        self.assertFalse(ctx["os_access_verified"])
        result = self.completed(self.allowed("server_run", {"argv": ["pwd"]}))
        self.assertEqual(result["exit_status"], 0)
        self.assertEqual(result["cwd"], str(self.root))
        for bad in ("", "/", "/nonexistent"):
            self.denied("server_exec", {"cwd": bad, "command": "pwd"})
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_DEFAULT_CWD": "/"}):
            self.assertEqual(self.allowed("get_server", {})["execution_context"],
                             {"state": "not_authorized_or_unavailable"})
            self.denied("server_exec", {"command": "pwd"})
            self.assertEqual(self.completed(self.allowed("server_exec", {
                "cwd": str(self.root), "command": "pwd"}))["exit_status"], 0)
        self.cli("set", "permission-object", "hostinfo-only", "permissions", "host-info")
        self.cli("set", "ai-access", self.rule("other"), "permission", "hostinfo-only")
        self.assertEqual(self.allowed("get_server", {}, identity="other")["execution_context"],
                         {"state": "not_authorized_or_unavailable"})
        self.denied("server_run", {"argv": ["pwd"]}, identity="other")

    def test_public_argv_shell_receipts_and_audit(self):
        argv = self.command([sys.executable, "-c", "print('PUBLIC_ARGV_OK')"])
        self.assertEqual(argv["exit_status"], 0, argv)
        self.assertEqual(argv["stdout"]["text"].strip(), "PUBLIC_ARGV_OK")
        self.assertEqual(argv["execution_user"], pwd.getpwuid(os.geteuid()).pw_name)
        shell = self.completed(self.allowed("server_exec", {
            "cwd": str(self.root),
            "command": "printf '%s' PUBLIC_SHELL_OK | tr '[:upper:]' '[:lower:]'",
        }))
        self.assertEqual(shell["exit_status"], 0, shell)
        self.assertEqual(shell["stdout"]["text"], "public_shell_ok")
        self.assert_activity("server_run", "ALLOW")
        self.assert_activity("server_exec", "ALLOW")

    def test_public_full_filesystem_cwd_alias_and_scoped_denial(self):
        target = self.root / "actual"
        target.mkdir()
        alias = self.root / "current"
        alias.symlink_to(target, target_is_directory=True)
        args = {"cwd": str(alias), "command": "pwd -P"}
        self.denied("server_exec", args)
        v24.set_ai_policy_path_scopes(self.plane, self.rule("owner"), ["/**"])
        self.denied("server_exec", args)  # Local operator roots remain scoped.
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_ALLOWED_ROOTS": "/"}):
            result = self.completed(self.allowed("server_exec", args))
            self.assertEqual(result["exit_status"], 0, result)
            self.assertEqual(result["cwd"], str(target.resolve()))
            self.assertEqual(result["stdout"]["text"].strip(), str(target.resolve()))
            self.denied("server_read_file", {"path": str(alias / "missing")})
            self.assert_activity("server_exec", "ALLOW")
            self.assert_activity("server_read_file", "DENY")
            v24.set_ai_policy_path_scopes(self.plane, self.rule("owner"), [])
            self.denied("server_exec", args)

    def test_public_file_create_read_update_delete(self):
        path = self.root / "public-file.txt"
        for content in ("created\n", "updated\n"):
            self.allowed("server_write_file", {"path": str(path), "content": content})
            read = self.allowed("server_read_file", {"path": str(path)})
            self.assertEqual(base64.b64decode(read["content_b64"]), content.encode())
            self.assertEqual(path.read_text(), content)
        self.allowed("server_delete_file", {"path": str(path)})
        self.assertFalse(path.exists())
        for name in ("server_write_file", "server_read_file", "server_delete_file"):
            self.assert_activity(name, "ALLOW")

    def test_public_writable_git_and_local_bare_push_clone(self):
        def git(*args, cwd=None):
            result = self.completed(self.allowed("server_git", {
                "cwd": str(cwd or self.root), "argv": ["git", *args],
                "wait_ms": 1000, "timeout_seconds": 15,
            }))
            self.assertEqual(result["exit_status"], 0, result)
            return result

        bare, work, clone = (self.root / name for name in ("remote.git", "work", "clone"))
        git("init", "--bare", str(bare))
        git("init", "-b", "main", str(work))
        self.allowed("server_write_file", {
            "path": str(work / "fixture.txt"), "content": "public MCP Git fixture\n"})
        git("add", "fixture.txt", cwd=work)
        git("-c", "user.name=Native Public Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-m", "isolated public MCP fixture", cwd=work)
        git("remote", "add", "origin", str(bare), cwd=work)
        git("push", "-u", "origin", "main", cwd=work)
        git("clone", "-b", "main", str(bare), str(clone))
        read = self.allowed("server_read_file", {"path": str(clone / "fixture.txt")})
        self.assertEqual(base64.b64decode(read["content_b64"]), b"public MCP Git fixture\n")
        self.assert_activity("server_git", "ALLOW")

    def test_public_prompt_stdin_eof_and_output_continuation(self):
        job = self.allowed("server_run", {
            "cwd": str(self.root), "wait_ms": 0, "timeout_seconds": 15,
            "argv": [sys.executable, "-u", "-c",
                     "import sys; print('READY>', end='', flush=True); "
                     "line=sys.stdin.readline(); print('GOT:'+line.strip())"],
        })
        deadline = time.monotonic() + 3
        while "READY>" not in job["stdout"]["text"] and time.monotonic() < deadline:
            job = self.allowed("server_job_poll", {"job_id": job["job_id"], "wait_ms": 25})
        self.assertEqual(job["state"], "running", job)
        self.assertEqual(job["stdout"]["text"], "READY>")
        cursor = job["stdout"]["next_cursor"]
        sent = self.allowed("server_job_input", {
            "job_id": job["job_id"], "data": "public-input\n", "eof": True})
        self.assertEqual(sent["accepted_bytes"], len(b"public-input\n"))
        self.assertTrue(sent["input_closed"])
        final = self.completed(job)
        self.assertEqual(final["exit_status"], 0, final)
        continued = self.allowed("server_job_poll", {
            "job_id": job["job_id"], "stdout_cursor": cursor, "stderr_cursor": 0})
        self.assertEqual(continued["stdout"]["text"], "GOT:public-input\n")
        self.assertFalse(continued["stdout"]["cursor_was_evicted"])
        self.assert_activity("server_job_input", "ALLOW")
        self.assert_activity("server_job_poll", "ALLOW")

    def test_public_stop_terminates_own_job(self):
        job = self.allowed("server_run", {
            "cwd": str(self.root), "wait_ms": 0, "timeout_seconds": 30,
            "argv": [sys.executable, "-c", "import time; time.sleep(60)"],
        })
        stopped = self.completed(self.allowed("server_job_stop", {"job_id": job["job_id"]}))
        self.assertLess(stopped["exit_status"], 0, stopped)
        self.assertFalse(stopped["timed_out"])
        self.assert_activity("server_job_stop", "ALLOW")

    def test_other_authorized_identity_cannot_control_owner_job(self):
        other = self.command([sys.executable, "-c", "print('OTHER_ALLOWED')"], identity="other")
        self.assertEqual(other["exit_status"], 0, other)
        job = self.allowed("server_run", {
            "cwd": str(self.root), "wait_ms": 0, "timeout_seconds": 30,
            "argv": [sys.executable, "-u", "-c", "import sys; sys.stdin.read()"],
        })
        for name in ("server_job_poll", "server_job_input", "server_job_stop"):
            arguments = {"job_id": job["job_id"]}
            if name == "server_job_input":
                arguments["data"] = "must-not-enter"
            self.denied(name, arguments, identity="other")
            self.assert_activity(name, "DENY", identity="other")
        still_running = self.allowed("server_job_poll", {"job_id": job["job_id"]})
        self.assertEqual(still_running["state"], "running", still_running)
        self.allowed("server_job_stop", {"job_id": job["job_id"]})

    def test_revoked_policy_denies_each_job_operation_and_new_commands(self):
        job = self.allowed("server_run", {
            "cwd": str(self.root), "wait_ms": 0, "timeout_seconds": 30,
            "argv": [sys.executable, "-u", "-c", "import sys; sys.stdin.read()"],
        })
        v24.set_ai_policy_path_scopes(self.plane, self.rule("owner"), [])
        for name in ("server_job_poll", "server_job_input", "server_job_stop"):
            arguments = {"job_id": job["job_id"]}
            if name == "server_job_input":
                arguments.update({"data": "", "eof": True})
            self.denied(name, arguments)
            self.assert_activity(name, "DENY")
        self.denied("server_exec", {"cwd": str(self.root), "command": "touch revoked-must-not-exist"})
        self.assertFalse((self.root / "revoked-must-not-exist").exists())
        self.assert_activity("server_exec", "DENY")
        v24.set_ai_policy_path_scopes(self.plane, self.rule("owner"), [str(self.root) + "/**"])
        self.denied("server_job_stop", {"job_id": job["job_id"]})
        replacement = self.allowed("server_run", {"argv":["id"],"wait_ms":1000})
        self.assertEqual(self.completed(replacement)["exit_status"], 0)

    def test_missing_or_invalid_content_preserves_file_and_explicit_empty_is_allowed(self):
        path = self.root / "preserved-content.txt"
        original = "existing data must survive invalid calls\n"
        self.allowed("server_write_file", {"path": str(path), "content": original})
        for name in ("server_write_file", "write_file", "upload_file"):
            base = {"path": str(path)}
            if name != "server_write_file":
                base["endpoint"] = "server:self"
            for options in ({}, {"content": None}, {"content": 17}, {"content": False},
                            {"content": ["wrong type"]}):
                self.denied(name, {**base, **options})
                self.assertEqual(path.read_text(), original, (name, options))
        for name in ("server_write_file", "write_file", "upload_file"):
            arguments = {"path": str(path), "content": ""}
            if name != "server_write_file":
                arguments["endpoint"] = "server:self"
            self.allowed(name, arguments)
            self.assertEqual(path.read_text(), "")

    def test_invalid_execution_options_have_no_side_effect(self):
        base = {"cwd": str(self.root), "argv": ["touch", "invalid-must-not-exist"]}
        for options in ({"wait_ms": True}, {"wait_ms": -1}, {"timeout_seconds": 0},
                        {"timeout_seconds": True}, {"argv": "touch invalid-must-not-exist"},
                        {"command": "touch invalid-must-not-exist"}):
            self.denied("server_run", {**base, **options})
            self.assertFalse((self.root / "invalid-must-not-exist").exists())
        self.denied("server_exec", {"cwd": str(self.root), "command": ""})
        job = self.command([sys.executable, "-c", "print('done')"])
        self.denied("server_job_poll", {"job_id": job["job_id"], "stdout_cursor": True})
        self.assert_activity("server_run", "DENY")


if __name__ == "__main__":
    unittest.main()
