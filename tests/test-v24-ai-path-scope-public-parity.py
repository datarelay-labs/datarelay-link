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
        v24.set_network_object(
            self.plane, "ubuntu-prod", type="ip", value="198.51.100.10", oneshot=True
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
