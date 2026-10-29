#!/usr/bin/env python3
"""Native full-control runtime acceptance in disposable, unprivileged fixtures.

No public service configuration, real remote repository, system package or
credential is changed. Commands run as the existing test account only.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import drlink_mcp_full_control as full
from drlink_control_plane import path_allowed


class FullControlRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-full-control-")
        self.root = Path(self.temp.name)
        self.account = pwd.getpwuid(os.geteuid())
        self.flags = patch.dict(os.environ, {
            "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
            "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1",
            "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED": "1",
            "DRLINK_MCP_SERVER_EXEC_USER": self.account.pw_name,
            "DRLINK_MCP_SERVER_ALLOWED_ROOTS": str(self.root),
            "DRLINK_MCP_SERVER_ADMIN_ENABLED": "1" if os.geteuid() == 0 else "0",
            "DRLINK_TEST_DO_NOT_INHERIT": "fixture-not-a-real-secret",
        })
        self.flags.start()
        self.runtime = full.FullControlRuntime()
        self.owner = "isolated-fixture-identity"
        self.patterns = [str(self.root) + "/**"]

    def tearDown(self):
        self.runtime.close()
        self.flags.stop()
        self.temp.cleanup()

    def run_command(self, argv=None, command=None, **options):
        arguments = {"cwd": str(self.root), "wait_ms": 1000, **options}
        if argv is not None:
            arguments["argv"] = argv
        if command is not None:
            arguments["command"] = command
        return self.runtime.start(self.owner, arguments, self.patterns)

    def completed(self, result):
        deadline = time.monotonic() + 8
        while result["state"] != "completed" and time.monotonic() < deadline:
            result = self.runtime.poll(self.owner, result["job_id"], wait_ms=100)
        self.assertEqual(result["state"], "completed", result)
        return result

    def test_default_gate_and_account_are_required(self):
        for flag in ("DRLINK_MCP_SERVER_SELF_ENABLED", "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED",
                     "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED"):
            with patch.dict(os.environ, {flag: "0"}):
                with self.assertRaises(full.FullControlDenied):
                    self.run_command([sys.executable, "-c", "print('unused')"])
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_EXEC_USER": ""}):
            with self.assertRaises(full.FullControlDenied):
                full.configured_account()

    def test_root_account_requires_independent_operator_opt_in(self):
        with patch.dict(os.environ, {
            "DRLINK_MCP_SERVER_EXEC_USER": "root",
            "DRLINK_MCP_SERVER_ADMIN_ENABLED": "0",
        }):
            with self.assertRaisesRegex(full.FullControlDenied, "opt-in"):
                full.configured_account()

    def test_general_command_uses_current_account_and_scrubbed_environment(self):
        result = self.completed(self.run_command([
            sys.executable, "-c",
            "import os,json; print(json.dumps({'uid':os.geteuid(),'cwd':os.getcwd(),"
            "'inherited':os.environ.get('DRLINK_TEST_DO_NOT_INHERIT')}))",
        ]))
        self.assertEqual(result["exit_status"], 0, result)
        data = json.loads(result["stdout"]["text"])
        self.assertEqual(data["uid"], os.geteuid())
        self.assertEqual(data["cwd"], str(self.root))
        self.assertIsNone(data["inherited"])
        self.assertEqual(result["execution_user"], self.account.pw_name)

    def test_shell_pipeline_creates_modifies_and_deletes_fixture(self):
        result = self.completed(self.run_command(command=(
            "printf '%s\\n' first > fixture.txt && "
            "printf '%s\\n' second >> fixture.txt && cat fixture.txt && rm fixture.txt"
        )))
        self.assertEqual(result["exit_status"], 0, result)
        self.assertEqual(result["stdout"]["text"], "first\nsecond\n")
        self.assertFalse((self.root / "fixture.txt").exists())

    def test_real_git_add_commit_push_and_clone_local_bare_repository(self):
        def git(*argv, cwd=None):
            result = self.runtime.start(self.owner, {
                "cwd": str(cwd or self.root), "argv": ["git", *argv], "wait_ms": 1000,
            }, self.patterns, git=True)
            result = self.completed(result)
            self.assertEqual(result["exit_status"], 0, result)
            return result
        bare = self.root / "remote.git"
        work = self.root / "work"
        git("init", "--bare", str(bare))
        git("init", "-b", "main", str(work))
        (work / "fixture.txt").write_text("native MCP fixture\n")
        git("add", "fixture.txt", cwd=work)
        git("-c", "user.name=Native Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-m", "isolated runtime fixture", cwd=work)
        git("remote", "add", "origin", str(bare), cwd=work)
        git("push", "-u", "origin", "main", cwd=work)
        clone = self.root / "clone"
        git("clone", "-b", "main", str(bare), str(clone))
        self.assertEqual((clone / "fixture.txt").read_text(), "native MCP fixture\n")

    def test_short_prompt_is_visible_before_process_exit_and_accepts_input(self):
        result = self.run_command([
            sys.executable, "-u", "-c",
            "import sys; sys.stdout.write('READY>'); sys.stdout.flush(); "
            "line=sys.stdin.readline(); print('GOT:'+line.strip())",
        ], wait_ms=0)
        deadline = time.monotonic() + 2
        while "READY>" not in result["stdout"]["text"] and time.monotonic() < deadline:
            result = self.runtime.poll(self.owner, result["job_id"], wait_ms=25)
        self.assertEqual(result["state"], "running", result)
        self.assertIn("READY>", result["stdout"]["text"])
        sent = self.runtime.send(self.owner, result["job_id"], "fixture\n", eof=True)
        self.assertEqual(sent["accepted_bytes"], len(b"fixture\n"))
        self.assertTrue(sent["input_closed"])
        final = self.completed(result)
        self.assertEqual(final["exit_status"], 0, final)
        self.assertIn("GOT:fixture", final["stdout"]["text"])

    def test_job_ownership_and_profile_change_are_enforced(self):
        result = self.run_command([sys.executable, "-c", "import time; time.sleep(10)"], wait_ms=0)
        job_id = result["job_id"]
        for method in (lambda: self.runtime.poll("another-identity", job_id),
                       lambda: self.runtime.send("another-identity", job_id, "x"),
                       lambda: self.runtime.stop("another-identity", job_id)):
            with self.assertRaises(full.FullControlDenied):
                method()
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED": "0"}):
            with self.assertRaises(full.FullControlDenied):
                self.runtime.poll(self.owner, job_id)
        stopped = self.runtime.stop(self.owner, job_id)
        self.assertEqual(stopped["state"], "completed", stopped)
        self.assertNotEqual(stopped["exit_status"], 0)

    def test_timeout_terminates_job(self):
        result = self.run_command([sys.executable, "-c", "import time; time.sleep(10)"],
                                  timeout_seconds=1, wait_ms=0)
        final = self.completed(result)
        self.assertTrue(final["timed_out"])
        self.assertLess(final["exit_status"], 0)

    def test_file_worker_roundtrip_and_out_of_scope_denial(self):
        file = self.root / "new.txt"
        full.execute_file_action("write_file", {"path": str(file), "content": "first"}, self.patterns)
        full.execute_file_action("write_file", {"path": str(file), "content": "changed"}, self.patterns)
        payload = full.execute_file_action("read_file", {"path": str(file)}, self.patterns)
        self.assertEqual(base64.b64decode(payload["content_b64"]), b"changed")
        full.execute_file_action("delete_file", {"path": str(file)}, self.patterns)
        self.assertFalse(file.exists())
        with self.assertRaises(full.FullControlDenied):
            full.execute_file_action("read_file", {"path": "/etc/passwd"}, self.patterns)

    def test_completed_history_does_not_block_subsequent_commands(self):
        with patch.object(full, "MAX_JOBS", 2):
            first = self.completed(self.run_command([sys.executable, "-c", "print('one')"]))
            second = self.completed(self.run_command([sys.executable, "-c", "print('two')"]))
            third = self.completed(self.run_command([sys.executable, "-c", "print('three')"]))
            self.assertEqual(third["exit_status"], 0, third)
            self.assertEqual(len(self.runtime.jobs), 2)
            self.assertNotIn(first["job_id"], self.runtime.jobs)
            self.assertIn(second["job_id"], self.runtime.jobs)

    def test_active_job_limit_stays_enforced(self):
        with patch.object(full, "MAX_JOBS", 1):
            active = self.run_command([sys.executable, "-c", "import time; time.sleep(10)"], wait_ms=0)
            with self.assertRaisesRegex(full.FullControlDenied, "process limit"):
                self.run_command([sys.executable, "-c", "print('not-started')"])
            self.assertIn(active["job_id"], self.runtime.jobs)
            self.runtime.stop(self.owner, active["job_id"])

    def test_output_pagination_is_bounded_and_reports_eviction(self):
        result = self.completed(self.run_command([
            sys.executable, "-c", "import sys; sys.stdout.write('x' * 1200000)",
        ]))
        self.assertEqual(result["exit_status"], 0)
        first = result["stdout"]
        self.assertEqual(first["total_bytes"], 1200000)
        self.assertEqual(first["truncated_before"], 1200000 - full.WINDOW)
        self.assertTrue(first["cursor_was_evicted"])
        self.assertEqual(len(first["text"]), full.PAGE)
        second = self.runtime.poll(self.owner, result["job_id"], stdout_cursor=first["next_cursor"])
        self.assertEqual(second["stdout"]["next_cursor"], first["next_cursor"] + full.PAGE)
        self.assertFalse(second["stdout"]["cursor_was_evicted"])

    def test_output_pages_preserve_exact_utf8_bytes(self):
        data = ("가🙂" * 30000).encode("utf-8")
        result = self.completed(self.run_command([
            sys.executable, "-c", "import sys; sys.stdout.write('가🙂' * 30000)",
        ]))
        recovered = bytearray()
        page = result["stdout"]
        while True:
            recovered.extend(base64.b64decode(page["data_b64"]))
            if page["next_cursor"] == page["total_bytes"]:
                break
            page = self.runtime.poll(self.owner, result["job_id"],
                                     stdout_cursor=page["next_cursor"])["stdout"]
        self.assertEqual(bytes(recovered), data)
        self.assertTrue(result["output_complete"])

    def test_history_reclamation_preserves_active_job_and_recent_output(self):
        with patch.object(full, "MAX_JOBS", 3):
            active = self.run_command([sys.executable, "-c", "import time; time.sleep(10)"], wait_ms=0)
            oldest = self.completed(self.run_command(["printf", "old"]))
            recent = self.completed(self.run_command(["printf", "recent"]))
            newest = self.completed(self.run_command(["printf", "new"]))
            self.assertEqual(len(self.runtime.jobs), 3)
            self.assertNotIn(oldest["job_id"], self.runtime.jobs)
            self.assertIn(newest["job_id"], self.runtime.jobs)
            self.assertEqual(self.runtime.poll(self.owner, active["job_id"])["state"], "running")
            self.assertEqual(self.runtime.poll(self.owner, recent["job_id"])["stdout"]["text"], "recent")
            self.runtime.stop(self.owner, active["job_id"])

    def test_concurrent_history_reclamation_preserves_execution_receipt(self):
        import threading
        paused, release, replied = threading.Event(), threading.Event(), threading.Event()
        outcome = {}
        original_poll = self.runtime.poll

        def guarded_poll(*args, **kwargs):
            if threading.current_thread().name == "first-native-client":
                paused.set()
                release.wait(5)
            return original_poll(*args, **kwargs)

        def first_client():
            try:
                outcome["result"] = self.run_command(command="printf 'first\\n' >> effects")
            except Exception as exc:
                outcome["error"] = exc
            finally:
                replied.set()

        worker = threading.Thread(target=first_client, name="first-native-client")
        with patch.object(full, "MAX_JOBS", 1), patch.object(self.runtime, "poll", guarded_poll):
            try:
                worker.start()
                deadline = time.monotonic() + 3
                while not (paused.is_set() or replied.is_set()) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(paused.is_set() or replied.is_set())
                first_job = next(iter(self.runtime.jobs.values()))
                self.assertTrue(first_job.done.wait(3))
                second = self.completed(self.run_command(command="printf 'second\\n' >> effects"))
                release.set()
                worker.join(3)
                self.assertFalse(worker.is_alive())
                self.assertNotIn("error", outcome)
                self.assertEqual(outcome["result"]["exit_status"], 0)
                self.assertEqual(second["exit_status"], 0)
                self.assertEqual((self.root / "effects").read_text(), "first\nsecond\n")
            finally:
                release.set()
                worker.join(5)

    def test_exited_leader_cleans_up_same_group_child(self):
        import signal
        child_pid = None
        try:
            result = self.completed(self.run_command([
                sys.executable, "-u", "-c",
                "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(30)']); print(p.pid,flush=True)",
            ]))
            child_pid = int(result["stdout"]["text"].strip())
            state = Path("/proc") / str(child_pid) / "stat"
            if state.exists():
                self.assertEqual(state.read_text().split(") ", 1)[1][0], "Z",
                                 "child still runs after its job completed")
            with patch.object(full.os, "killpg", wraps=full.os.killpg) as kill:
                self.runtime.stop(self.owner, result["job_id"])
                kill.assert_not_called()
        finally:
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_partial_input_preserves_utf8_character_boundaries(self):
        import hashlib
        data = ("가🙂" * 8000).encode("utf-8")
        gate = self.root / "read-input"
        result = self.run_command([
            sys.executable, "-u", "-c",
            "import sys,time,pathlib,hashlib; p=pathlib.Path(sys.argv[1]); "
            "exec('while not p.exists(): time.sleep(0.01)'); "
            "data=sys.stdin.buffer.read(); print(hashlib.sha256(data).hexdigest())",
            str(gate),
        ], wait_ms=0)
        import fcntl
        fcntl.fcntl(self.runtime.jobs[result["job_id"]].process.stdin.fileno(),
                    fcntl.F_SETPIPE_SZ, 4096)
        remaining = data
        try:
            first = self.runtime.send(self.owner, result["job_id"], remaining.decode(), eof=True)
            remaining = remaining[first["accepted_bytes"]:]
            remaining.decode("utf-8")
            gate.touch()
            deadline = time.monotonic() + 5
            while remaining and time.monotonic() < deadline:
                sent = self.runtime.send(self.owner, result["job_id"], remaining.decode(), eof=True)
                remaining = remaining[sent["accepted_bytes"]:]
                remaining.decode("utf-8")
                if not sent["accepted_bytes"]:
                    time.sleep(0.01)
            self.assertFalse(remaining, "process stdin did not drain")
            final = self.completed(result)
            self.assertEqual(final["stdout"]["text"].strip(), hashlib.sha256(data).hexdigest())
        finally:
            gate.touch()

    def test_initial_directory_scope_and_request_shape(self):
        with self.assertRaises(full.FullControlDenied):
            self.runtime.start(self.owner, {"cwd": "/", "argv": ["true"]}, self.patterns)
        with self.assertRaises(full.FullControlDenied):
            self.run_command(argv=["true"], command="true")
        with self.assertRaises(full.FullControlDenied):
            self.run_command(argv=["true"], timeout_seconds=True)
        with self.assertRaises(full.FullControlDenied):
            self.runtime.start("", {"cwd": str(self.root), "argv": ["true"]}, self.patterns)
        self.assertTrue(path_allowed(str(self.root / "fixture.txt"), ["/**"]))
        self.assertFalse(path_allowed(str(self.root / "fixture.txt"), []))


class FullControlBridgeAuthorizationTests(unittest.TestCase):
    """Exercise public Bridge dispatch against an isolated real policy DB.

    These fixtures complement the public HTTP suite and do not replace
    installed-server acceptance through the genuine MCP connection.
    """
    def setUp(self):
        import contextlib
        import io
        from drlink_control_cli import dispatch
        from drlink_control_plane import ControlPlane
        from drlink_mcp_bridge import MCPBridge
        self.contextlib, self.io, self.dispatch = contextlib, io, dispatch
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-full-policy-")
        self.root = Path(self.temp.name)
        account = pwd.getpwuid(os.geteuid())
        self.environment = patch.dict(os.environ, {
            "DRLINK_TEST_ROOT": str(self.root), "DRLINK_CONFIRM": "yes",
            "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
            "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1",
            "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED": "1",
            "DRLINK_MCP_SERVER_EXEC_USER": account.pw_name,
            "DRLINK_MCP_SERVER_ALLOWED_ROOTS": str(self.root),
            "DRLINK_MCP_SERVER_DEFAULT_CWD": str(self.root),
            "DRLINK_MCP_SERVER_ADMIN_ENABLED": "1" if os.geteuid() == 0 else "0",
        })
        self.environment.start()
        self.plane = ControlPlane(str(self.root))
        self.bridge = MCPBridge(root=str(self.root), plane=self.plane)
        self.principal = {"name": "native-full-fixture", "id": "fixture-identity"}
        self.plane.set_ai_principal(self.principal["name"], enabled=True)
        self.cli("system", "credential", "rotate", "ai-identity", self.principal["name"])

    def tearDown(self):
        self.bridge.close()
        self.plane.close()
        self.environment.stop()
        self.temp.cleanup()

    def cli(self, *args):
        out, err = self.io.StringIO(), self.io.StringIO()
        with self.contextlib.redirect_stdout(out), self.contextlib.redirect_stderr(err):
            result = self.dispatch(list(args), root=str(self.root))
        self.assertEqual(result, 0, out.getvalue() + err.getvalue())

    def authorize(self):
        self.cli("set", "permission-object", "fixture-all", "permissions",
                 "host-info,process-read,file-read,file-write,file-upload,file-download,command-exec")
        self.cli("set", "ai-access", "fixture-server", "mode", "whitelist", "source",
                 self.principal["name"], "destination", "server:self", "permission",
                 "fixture-all", "paths", str(self.root) + "/**", "enabled")

    def test_unauthorized_call_has_no_side_effect(self):
        dest = self.root / "must-not-exist"
        result = self.bridge.call_tool(self.principal, "server_run", {
            "cwd": str(self.root), "argv": ["touch", str(dest)],
        })
        self.assertTrue(result.get("isError"), result)
        self.assertFalse(dest.exists())

    def test_authorized_general_argv_and_existing_exec_alias(self):
        self.authorize()
        result = self.bridge.call_tool(self.principal, "server_run", {
            "cwd": str(self.root), "argv": [sys.executable, "-c", "print('GENERAL_ARGV_OK')"],
        })
        self.assertFalse(result.get("isError"), result)
        self.assertIn("GENERAL_ARGV_OK", result["structuredContent"]["stdout"]["text"])
        shell = self.bridge.call_tool(self.principal, "exec", {
            "endpoint": "server:self", "command": "printf SHELL_ALIAS_OK",
        })
        self.assertFalse(shell.get("isError"), shell)
        self.assertEqual(shell["structuredContent"]["stdout"]["text"], "SHELL_ALIAS_OK")

    def test_authorized_file_roundtrip_and_process_read(self):
        self.authorize()
        path = str(self.root / "bridge-fixture.txt")
        written = self.bridge.call_tool(self.principal, "server_write_file", {
            "path": path, "content": "bridge fixture",
        })
        self.assertFalse(written.get("isError"), written)
        read = self.bridge.call_tool(self.principal, "server_read_file", {"path": path})
        self.assertEqual(base64.b64decode(read["structuredContent"]["content_b64"]), b"bridge fixture")
        removed = self.bridge.call_tool(self.principal, "server_delete_file", {"path": path})
        self.assertFalse(removed.get("isError"), removed)
        self.assertFalse(Path(path).exists())
        process = self.bridge.call_tool(self.principal, "list_processes", {"endpoint": "server:self"})
        self.assertFalse(process.get("isError"), process)
        self.assertGreater(process["structuredContent"]["count"], 0)

    def test_each_public_job_operation_rechecks_current_path_authorization(self):
        import drlink_v24 as v24
        self.authorize()
        response = self.bridge.call_tool(self.principal, "server_run", {
            "cwd": str(self.root), "argv": [sys.executable, "-c", "import time; time.sleep(10)"],
            "wait_ms": 0,
        })
        self.assertFalse(response.get("isError"), response)
        job = response["structuredContent"]["job_id"]
        v24.set_ai_policy_path_scopes(self.plane, "fixture-server", [])
        for name in ("server_job_poll", "server_job_input", "server_job_stop"):
            arguments = {"job_id": job}
            if name == "server_job_input":
                arguments["data"] = ""
            result = self.bridge.call_tool(self.principal, name, arguments)
            self.assertTrue(result.get("isError"), (name, result))
            self.assertIn("AI Access", result["content"][0]["text"])

    def test_disabling_identity_denies_new_commands(self):
        self.authorize()
        self.plane.set_ai_principal(self.principal["name"], enabled=False)
        response = self.bridge.call_tool(self.principal, "server_run", {
            "cwd": str(self.root), "argv": ["touch", str(self.root / "no-create")],
        })
        self.assertTrue(response.get("isError"), response)
        self.assertFalse((self.root / "no-create").exists())


if __name__ == "__main__":
    unittest.main()
