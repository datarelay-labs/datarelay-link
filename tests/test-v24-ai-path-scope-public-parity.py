#!/usr/bin/env python3
"""P1 Finding AA: public AI file path-scope configuration parity.

Expose existing ai_policy_path_scopes through public v2.4 CLI / Wizard /
ConfigurationBundle / test ai-access without weakening fail-closed runtime.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24
from drlink_v24_bundle import apply_v24_plan, export_configuration_v24, prepare_v24_plan
from drlink_v24_wizard import ScriptedIO, set_wizard_io


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


def _verify(plane: ControlPlane, name: str) -> None:
    plane.conn.execute(
        "UPDATE ai_principals SET credential_status = 'verified', enabled = 1 WHERE name = ?",
        (name,),
    )
    plane.conn.commit()


class AiPathScopePublicParity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-ai-paths-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)
        self.vendor = Path(self.tmp) / "var" / "lib" / "vendor"
        self.vendor.mkdir(parents=True, exist_ok=True)
        (self.vendor / "app.log").write_text("payload\n", encoding="utf-8")
        self.etc = Path(self.tmp) / "etc"
        self.etc.mkdir(parents=True, exist_ok=True)
        (self.etc / "config.yaml").write_text("secret: 1\n", encoding="utf-8")
        self.vendor_glob = str(self.vendor / "**")
        self._seed()

    def tearDown(self):
        set_wizard_io(None)
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def _seed(self) -> None:
        self.plane.set_ai_principal("bot", enabled=True)
        _verify(self.plane, "bot")
        self.plane.upsert_client(
            "a" * 32, label="ubuntu-prod", hostname="ubuntu-prod", connected=True
        )
        v24.set_permission_object(
            self.plane,
            "read-only",
            permissions=["host-info", "file-read"],
            oneshot=True,
        )
        v24.set_permission_object(
            self.plane, "info-only", permissions=["host-info"], oneshot=True
        )

    def _run(self, *tokens):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(list(tokens), root=self.tmp, plane=self.plane)
        return rc, out.getvalue(), err.getvalue()

    def _auth(self, capability: str, *, operand: str | None = None) -> dict:
        return v24.authorize_ai_capability_v24(
            self.plane,
            identity="bot",
            destination="ubuntu-prod",
            capability=capability,
            operand=operand,
        )

    def test_windows_native_path_scope_is_bound_to_signed_executor_dialect(self):
        from drlink_control_plane import windows_absolute_path, windows_path_allowed
        self.assertEqual(windows_absolute_path(r"c:\Data\report.txt"), "C:/Data/report.txt")
        for invalid in (r"C:relative", r"\\server\share\file", r"\\?\C:\Data\file", "C:/Data/../file", "C:/Data/file:stream", "C:/Data/NUL.txt", "C:/Data/COM1.log", "C:/Data/CONIN$", "C:/Data/report.", "C:/Data/report ", "C:/Data/%2e%2e/file", "C:/Data/SHORT~1", "C:/Data//file", "C:/Data/*.txt"):
            self.assertIsNone(windows_absolute_path(invalid), invalid)
            self.assertFalse(windows_path_allowed(invalid, ["/**"]), invalid)
        self.assertTrue(windows_path_allowed("C:/Data/report.txt", ["C:/Data/**"]))
        self.assertFalse(windows_path_allowed("C:/Data-other/report.txt", ["C:/Data/**"]))
        self.assertFalse(windows_path_allowed("C:/data/report.txt", ["C:/Data/**"]))
        self.assertFalse(windows_path_allowed("C:/Data/report.txt", ["/Data/**"]))
        self.assertTrue(windows_path_allowed("C:/Data/report.txt", ["/**"]))
        v24.set_ai_access_rule(self.plane, "native-path", source="bot", destination="ubuntu-prod", permission="read-only", paths=["C:/Data/**"], enabled=True, oneshot=True)
        self.assertEqual(self._auth("read_file", operand="C:/Data/report.txt")["action"], "DENY")
        self.plane.record_ai_executor_platform("a" * 32, "windows")
        self.assertEqual(self._auth("read_file", operand="C:/Data/report.txt")["action"], "ALLOW")
        self.assertEqual(self._auth("read_file", operand="C:/Elsewhere/report.txt")["action"], "DENY")
        self.assertEqual(self._auth("read_file", operand="/Data/report.txt")["action"], "DENY")
        self.plane.record_ai_executor_platform("a" * 32, "posix")
        self.assertEqual(self._auth("read_file", operand="C:/Data/report.txt")["action"], "DENY")

    def test_native_rule_wizard_reviews_default_and_additional_accounts(self):
        from unittest.mock import patch
        v24.set_permission_object(self.plane, "ops", permissions=["host-info","command-exec","file-read"], oneshot=True)
        script = ScriptedIO(["bot", "server:self", "ops", self.vendor_glob,
                             "aella", "y", "y", "1"])
        set_wizard_io(script)
        with patch.object(self.plane, "native_mcp_local_accounts", return_value=["aella","root"]):
            rc, out, err = self._run("set","ai-access","native-wizard")
        self.assertEqual(rc, 0, err)
        row = self.plane.conn.execute("SELECT * FROM ai_policy_rules WHERE name='native-wizard'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(v24.ai_rule_execution(row), {"default":"aella","accounts":["aella","root"]})
        self.assertIn("Default execution account", "".join(script.out))

    def test_managed_hosts_keep_central_policy_without_account_binding(self):
        v24.set_permission_object(self.plane,"ops",permissions=["host-info","command-exec"],oneshot=True)
        rc,out,err=self._run("set","ai-access","managed-ops","source","bot",
            "destination","ubuntu-prod","permission","ops","enabled")
        self.assertEqual(rc,0,err)
        self.assertEqual(self._auth("exec")["action"],"ALLOW")
        revision=self.plane.current_revision()
        rc,out,err=self._run("set","ai-access","managed-ops","accounts","root","default-account","root")
        self.assertNotEqual(rc,0)
        self.assertEqual(self.plane.current_revision(),revision)
        self.assertEqual(self._auth("exec")["action"],"ALLOW")
        import yaml
        doc={"configurationBundle":{"context":"server","aiAccess":{"rules":[{
            "name":"managed-ops","execution":{"default":"root","accounts":["root"]}}]}}}
        with self.assertRaises(v24.ControlPlaneError):
            prepare_v24_plan(self.plane,yaml.safe_dump(doc),role="server")
        self.assertEqual(self.plane.current_revision(),revision)
        with self.assertRaises(v24.ControlPlaneError):
            v24.set_ai_access_rule(self.plane,"group-ops",source="bot",
                destination=v24.TRUSTED_MANAGED_HOSTS_TARGET,permission="ops",
                execution={"default":"root","accounts":["root"]},enabled=True,confirm=True)
        v24.set_ai_access_rule(self.plane,"native-ops",source="bot",destination="server:self",
            permission="ops",execution={"default":"root","accounts":["root"]},enabled=True,confirm=True)
        with self.assertRaises(v24.ControlPlaneError):
            v24.set_ai_access_rule(self.plane,"native-ops",destination="ubuntu-prod",confirm=True)
        row=self.plane.conn.execute("SELECT * FROM ai_policy_rules WHERE name='native-ops'").fetchone()
        self.assertEqual(row["destination_ref_kind"],"server")
        self.assertEqual(v24.ai_rule_execution(row),{"default":"root","accounts":["root"]})

    def test_execution_binding_cli_bundle_roundtrip_and_omitted_edit(self):
        import yaml
        v24.set_permission_object(self.plane, "ops", permissions=["host-info", "command-exec"], oneshot=True)
        rc, out, err = self._run("set", "ai-access", "multi-user", "source", "bot",
            "destination", "server:self", "permission", "ops", "paths", self.vendor_glob,
            "accounts", "aella,root", "default-account", "aella", "enabled")
        self.assertEqual(rc, 0, err)
        binding = {"accounts":["aella","root"],"default":"aella"}
        def stored():
            row = self.plane.conn.execute("SELECT * FROM ai_policy_rules WHERE name='multi-user'").fetchone()
            return v24.ai_rule_execution(row)
        self.assertEqual(stored(), binding)
        rc, out, err = self._run("show", "ai-access", "multi-user")
        self.assertEqual(rc, 0, err)
        self.assertIn("Default account: aella", out)
        self.assertIn("aella, root", out)
        revision = self.plane.current_revision()
        rc, out, err = self._run("set", "ai-access", "multi-user", "accounts", "root")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.plane.current_revision(), revision)
        self.assertEqual(stored(), binding)
        data = yaml.safe_load(export_configuration_v24(self.plane))
        rule = next(item for item in data["configurationBundle"]["aiAccess"]["rules"] if item["name"]=="multi-user")
        self.assertEqual(rule["execution"], binding)
        doc = {"configurationBundle":{"context":"server","aiAccess":{"rules":[{"name":"multi-user",
             "execution":{"accounts":["root"],"default":"root"}}]}}}
        plan = prepare_v24_plan(self.plane, yaml.safe_dump(doc), role="server")
        apply_v24_plan(self.plane, plan, confirm=True)
        self.assertEqual(stored(), {"accounts":["root"],"default":"root"})
        doc["configurationBundle"]["aiAccess"]["rules"][0] = {"name":"multi-user","paths":[self.vendor_glob]}
        plan = prepare_v24_plan(self.plane, yaml.safe_dump(doc), role="server")
        apply_v24_plan(self.plane, plan, confirm=True)
        self.assertEqual(stored(), {"accounts":["root"],"default":"root"})
        doc["configurationBundle"]["aiAccess"]["rules"][0]["execution"] = {"accounts":["aella"],"default":"root"}
        with self.assertRaises(Exception):
            prepare_v24_plan(self.plane, yaml.safe_dump(doc), role="server")
        self.assertEqual(stored(), {"accounts":["root"],"default":"root"})

    def test_cli_can_configure_path_scopes_for_file_rule(self):
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-read",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
            "paths",
            self.vendor_glob,
            "enabled",
        )
        self.assertEqual(rc, 0, err)
        self.assertEqual(
            v24.list_ai_policy_path_scopes(self.plane, "allow-read"),
            [self.vendor_glob],
        )
        rc, out, err = self._run("show", "ai-access", "allow-read")
        self.assertEqual(rc, 0, err)
        self.assertIn(self.vendor_glob, out)
        self.assertIn("Paths", out)

    def test_missing_path_scope_remains_fail_closed(self):
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-read",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
            "enabled",
        )
        self.assertEqual(rc, 0, err)
        denied = self._auth("read_file", operand=str(self.vendor / "app.log"))
        self.assertEqual(denied["action"], "DENY")
        self.assertIn("path scope", denied["reason"])

    def test_in_scope_allow_out_of_scope_deny(self):
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-read",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
            "paths",
            "%s,/opt/other/**" % self.vendor_glob,
            "enabled",
        )
        self.assertEqual(rc, 0, err)
        allowed = self._auth("read_file", operand=str(self.vendor / "app.log"))
        self.assertEqual(allowed["action"], "ALLOW")
        outside = self._auth("read_file", operand=str(self.etc / "config.yaml"))
        self.assertEqual(outside["action"], "DENY")
        self.assertIn("outside allowed scope", outside["reason"])

    def test_non_file_permission_does_not_require_paths(self):
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-info",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "info-only",
            "enabled",
        )
        self.assertEqual(rc, 0, err)
        self.assertEqual(v24.list_ai_policy_path_scopes(self.plane, "allow-info"), [])
        self.assertEqual(self._auth("get_system_info")["action"], "ALLOW")
        rc, out, err = self._run(
            "test",
            "ai-access",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "info-only",
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("ALLOW", out)
        self.assertNotIn("path context", out.lower())

    def test_partial_edit_preserves_omitted_paths_and_explicit_clear(self):
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-read",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
            "paths",
            self.vendor_glob,
            "enabled",
        )
        self.assertEqual(rc, 0, err)
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-read",
            "destination",
            "ubuntu-prod",
        )
        self.assertEqual(rc, 0, err)
        self.assertEqual(
            v24.list_ai_policy_path_scopes(self.plane, "allow-read"),
            [self.vendor_glob],
        )
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-read",
            "paths",
            "-",
        )
        self.assertEqual(rc, 0, err)
        self.assertEqual(v24.list_ai_policy_path_scopes(self.plane, "allow-read"), [])

    def test_bundle_cli_parity_export_reapply_no_change(self):
        yaml_text = """
configurationBundle:
  context: server
  permissionObjects:
    - name: read-only
      permissions: [host-info, file-read]
  aiAccess:
    mode: whitelist
    enforcement: enabled
    rules:
      - name: allow-read
        source: bot
        destination: ubuntu-prod
        permission: read-only
        paths:
          - %s
        enabled: true
""" % self.vendor_glob
        plan = prepare_v24_plan(self.plane, yaml_text)
        apply_v24_plan(self.plane, plan)
        self.assertEqual(
            v24.list_ai_policy_path_scopes(self.plane, "allow-read"),
            [self.vendor_glob],
        )
        exported = export_configuration_v24(self.plane)
        self.assertIn("paths:", exported)
        self.assertIn(self.vendor_glob, exported)
        plan2 = prepare_v24_plan(self.plane, exported)
        kinds = {(c.get("op"), c.get("kind"), c.get("name")) for c in plan2.changes}
        self.assertIn(("NO_CHANGE", "ai-access-rule", "allow-read"), kinds)

        # Omit paths on edit preserves scopes.
        omit_yaml = """
configurationBundle:
  context: server
  aiAccess:
    mode: whitelist
    enforcement: enabled
    rules:
      - name: allow-read
        source: bot
        destination: ubuntu-prod
        permission: read-only
        enabled: true
"""
        plan3 = prepare_v24_plan(self.plane, omit_yaml)
        apply_v24_plan(self.plane, plan3)
        self.assertEqual(
            v24.list_ai_policy_path_scopes(self.plane, "allow-read"),
            [self.vendor_glob],
        )

        # Explicit empty paths clears.
        clear_yaml = """
configurationBundle:
  context: server
  aiAccess:
    mode: whitelist
    enforcement: enabled
    rules:
      - name: allow-read
        source: bot
        destination: ubuntu-prod
        permission: read-only
        paths: []
        enabled: true
"""
        plan4 = prepare_v24_plan(self.plane, clear_yaml)
        apply_v24_plan(self.plane, plan4)
        self.assertEqual(v24.list_ai_policy_path_scopes(self.plane, "allow-read"), [])

    def test_test_ai_access_path_aware_and_mcp_agree(self):
        rc, _out, err = self._run(
            "set",
            "ai-access",
            "allow-read",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
            "paths",
            self.vendor_glob,
            "enabled",
        )
        self.assertEqual(rc, 0, err)

        # Without path: must not claim unconditional ALLOW.
        rc, out, err = self._run(
            "test",
            "ai-access",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("DENY", out)
        self.assertIn("path context", out.lower())

        in_path = str(self.vendor / "app.log")
        out_path = str(self.etc / "config.yaml")
        rc, out, err = self._run(
            "test",
            "ai-access",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
            "path",
            in_path,
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("ALLOW", out)
        self.assertEqual(self._auth("read_file", operand=in_path)["action"], "ALLOW")

        rc, out, err = self._run(
            "test",
            "ai-access",
            "source",
            "bot",
            "destination",
            "ubuntu-prod",
            "permission",
            "read-only",
            "path",
            out_path,
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("DENY", out)
        self.assertEqual(self._auth("read_file", operand=out_path)["action"], "DENY")

    def test_noninteractive_bare_rule_cannot_create_old_policy(self):
        before = self.plane.current_revision()
        set_wizard_io(None)
        rc, _, err = self._run("set", "ai-access", "bare")
        self.assertNotEqual(rc, 0)
        self.assertIn("TTY", err)
        self.assertEqual(self.plane.conn.execute("SELECT COUNT(*) FROM ai_access_rules").fetchone()[0], 0)
        self.assertEqual(self.plane.conn.execute("SELECT COUNT(*) FROM ai_policy_rules").fetchone()[0], 0)
        self.assertEqual(self.plane.current_revision(), before)

    def test_first_mode_free_rule_and_retired_mode_rejected(self):
        before = self.plane.current_revision()
        rc, _, err = self._run("set", "ai-access", "bad", "mode", "whitelist",
                               "source", "bot", "destination", "ubuntu-prod",
                               "permission", "info-only", "enabled")
        self.assertNotEqual(rc, 0)
        self.assertIn("mode", err)
        self.assertEqual(self.plane.current_revision(), before)
        self.assertIsNone(v24.get_access_policy(self.plane, "ai")["mode"])
        rc, _, err = self._run("set", "ai-access", "good", "source", "bot",
                               "destination", "ubuntu-prod", "permission", "info-only", "enabled")
        self.assertEqual(rc, 0, err)
        self.assertEqual(v24.get_access_policy(self.plane, "ai")["mode"], "whitelist")

    def test_named_free_profile_review_cancel_then_apply(self):
        before = self.plane.current_revision()
        answers = ["profile-rule", "bot", "ubuntu-prod", "Read-only profile",
                   self.vendor_glob, "y"]
        set_wizard_io(ScriptedIO(answers + ["0"]))
        rc, _, err = self._run("set", "ai-access")
        self.assertEqual(rc, 0, err)
        self.assertIsNone(v24.get_permission_object(self.plane, "profile-read-only"))
        self.assertEqual(self.plane.current_revision(), before)
        set_wizard_io(ScriptedIO(answers + ["1"]))
        rc, _, err = self._run("set", "ai-access")
        self.assertEqual(rc, 0, err)
        self.assertEqual(v24.expand_permissions(self.plane, "profile-read-only"),
                         {"host-info", "process-read", "file-read"})
        self.assertEqual(v24.list_ai_policy_path_scopes(self.plane, "profile-rule"), [self.vendor_glob])
        self.assertEqual(self._auth("read_file", operand=str(self.vendor / "app.log"))["action"], "ALLOW")
        self.assertEqual(self._auth("read_file", operand=str(self.etc / "config.yaml"))["action"], "DENY")
        self.assertEqual(self._auth("exec", operand="id")["action"], "DENY")

    def test_builtin_profile_collision_does_not_rewrite_existing_permission(self):
        v24.set_permission_object(self.plane, "profile-read-only", permissions=["host-info"], oneshot=True)
        before = self.plane.current_revision()
        set_wizard_io(ScriptedIO(["bot", "ubuntu-prod", "Read-only profile"]))
        rc, _, err = self._run("set", "ai-access", "collision")
        self.assertNotEqual(rc, 0)
        self.assertIn("conflicts", err)
        self.assertEqual(v24.expand_permissions(self.plane, "profile-read-only"), {"host-info"})
        self.assertEqual(self.plane.current_revision(), before)

    def test_wizard_examples_and_identity_rule_view(self):
        scripted = ScriptedIO(["1", "1", "2", "*", "?", "/**", "y", "1"])
        set_wizard_io(scripted)
        rc, _, err = self._run("set", "ai-access", "wizard-all")
        self.assertEqual(rc, 0, err)
        messages = "".join(scripted.out)
        self.assertIn("All files: /**", messages)
        self.assertIn("/home/**,/opt/**", messages)
        self.assertIn("not a valid absolute path", messages)
        self.assertEqual(v24.list_ai_policy_path_scopes(self.plane, "wizard-all"), ["/**"])
        rc, out, err = self._run("show", "ai-identity", "bot")
        self.assertEqual(rc, 0, err)
        self.assertIn("wizard-all", out)
        self.assertIn("ubuntu-prod", out)
        self.assertIn("read-only", out)
        self.assertIn("/**", out)

    def test_policy_reset_cancel_is_success_without_mutation(self):
        from unittest.mock import patch
        self._run("set", "ai-access", "one", "source", "bot", "destination",
                  "ubuntu-prod", "permission", "info-only", "enabled")
        before = self.plane.current_revision()
        os.environ.pop("DRLINK_CONFIRM", None)
        with patch("sys.stdin", io.StringIO("n\n")):
            rc, out, err = self._run("unset", "ai-access", "policy")
        self.assertEqual(rc, 0, err)
        self.assertIn("Reset ALL AI Access Rules", out)
        self.assertIn("Cancelled", out)
        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual(v24.get_access_policy(self.plane, "ai")["mode"], "whitelist")
        self.assertIsNotNone(self.plane.conn.execute(
            "SELECT 1 FROM ai_policy_rules WHERE name='one'").fetchone())
        rc, _, _ = self._run("unset", "ai-access", "policy", "unexpected")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.plane.current_revision(), before)

    def test_tty_invalid_utf8_reprompts_without_accepting_corrupted_input(self):
        from unittest.mock import patch
        from drlink_v24_wizard import TtyIO
        invalid = UnicodeDecodeError("utf-8", b"\xc3", 0, 1, "invalid continuation byte")
        with patch("builtins.input", side_effect=[invalid, "\udcc3", "/**"]) as read:
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(TtyIO().ask("Path: "), "/**")
        self.assertEqual(read.call_count, 3)
        self.assertIn("Invalid UTF-8 input", out.getvalue())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux PTY regression")
    def test_tty_pty_backspace_and_invalid_utf8_recovery(self):
        import pty
        import select
        import subprocess
        import termios
        import time

        for invalid in (False, True):
            with self.subTest(invalid=invalid):
                master, slave = pty.openpty()
                attrs = termios.tcgetattr(slave)
                attrs[6][termios.VERASE] = b"\x7f"
                termios.tcsetattr(slave, termios.TCSANOW, attrs)
                proc = subprocess.Popen(
                    [sys.executable, "-c",
                     "from drlink_v24_wizard import TtyIO; print('VALUE='+TtyIO().ask('Path: '))"],
                    stdin=slave, stdout=slave, stderr=slave,
                    env=dict(os.environ, PYTHONPATH=str(ROOT / "lib"), PYTHONUTF8="1"),
                )
                os.close(slave)
                output = bytearray()

                def read_until(token):
                    deadline = time.monotonic() + 5
                    while token not in output:
                        remaining = deadline - time.monotonic()
                        self.assertGreater(remaining, 0, repr(output))
                        if select.select([master], [], [], remaining)[0]:
                            chunk = os.read(master, 4096)
                            self.assertTrue(chunk, repr(output))
                            output.extend(chunk)

                try:
                    read_until(b"Path: ")
                    if invalid:
                        os.write(master, b"\xc3\n")
                        read_until(b"Invalid UTF-8 input")
                        os.write(master, b"/**\n")
                    else:
                        os.write(master, b"wrong" + b"\x7f" * 5 + b"/**\n")
                    read_until(b"VALUE=/**")
                    self.assertEqual(proc.wait(timeout=5), 0)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
                    os.close(master)

    def test_wizard_binds_paths_for_file_permission(self):
        # AI Access is WHITELIST-only; wizard does not ask for policy mode.
        # Choices: identity bot, dest ubuntu-prod, permission read-only
        # (info-only=1, read-only=2), paths, enabled, apply.
        set_wizard_io(
            ScriptedIO(
                [
                    "1",
                    "1",
                    "2",
                    self.vendor_glob,
                    "y",
                    "1",
                ]
            )
        )
        rc, _out, err = self._run("set", "ai-access", "wizard-read")
        self.assertEqual(rc, 0, err)
        self.assertEqual(
            v24.list_ai_policy_path_scopes(self.plane, "wizard-read"),
            [self.vendor_glob],
        )


if __name__ == "__main__":
    unittest.main()
