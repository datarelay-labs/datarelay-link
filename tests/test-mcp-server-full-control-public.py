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
            output = self.cli("system", "credential", "rotate", "ai-identity", name)
            self.tokens[key] = next(line.split(" ", 1)[1].strip()
                                    for line in output.splitlines() if line.startswith("Token: "))
        self.cli("set", "permission-object", "native-public-permissions", "permissions",
                 "host-info,process-read,file-read,file-write,file-upload,file-download,command-exec")
        for key, name in self.identities.items():
            self.cli("set", "ai-access", self.rule(key), "mode", "whitelist",
                     "source", name, "destination", "server:self", "permission",
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
            self.assertEqual(set(schema["required"]), {"cwd", field})
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
        self.allowed("server_job_stop", {"job_id": job["job_id"]})

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

