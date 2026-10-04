#!/usr/bin/env python3
"""Slice A public CLI contracts: confirmation, internet parity, diagnostics scopes, restore preflight."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_cli as cli
import drlink_v24 as v24
import frp_ctl_grammar as grammar
import frp_doctor
from drlink_control_plane import ControlPlane


BUNDLE = """configurationBundle:
  context: server
  networkObjects:
    - name: uxverify-confirm
      type: ip
      value: 192.0.2.254
"""


class _Tty(io.StringIO):
    def isatty(self):
        return True


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text(
        json.dumps({"role": "server", "egress_listen_addr": "127.0.0.1", "egress_listen_port": 6102})
        + "\n",
        encoding="utf-8",
    )


def _agent_root(tmp: str) -> None:
    state = Path(tmp, "etc/frp")
    state.mkdir(parents=True, exist_ok=True)
    Path(state, "client-state.json").write_text(
        json.dumps(
            {
                "machine_id": "aabbccddeeff00112233445566778899",
                "hostname": "slice-a-agent",
                "label": "slice-a-agent",
            }
        )
        + "\n",
        encoding="utf-8",
    )


class SliceAGrammarTests(unittest.TestCase):
    def test_show_and_test_internet_use_control_plane(self):
        show = grammar.match(["show", "internet-access"], "server")
        self.assertEqual(show.get("status"), "ok")
        self.assertEqual(show.get("action"), "control_plane")
        self.assertEqual(show.get("tokens"), ["show", "internet-access"])
        self.assertNotEqual(show.get("action"), "egress_cmd")

        test = grammar.match(
            ["test", "internet-access", "10.10.20.25", "archive.ubuntu.com", "443", "https"],
            "server",
        )
        self.assertEqual(test.get("status"), "ok")
        self.assertEqual(test.get("action"), "control_plane")
        self.assertEqual(test.get("tokens")[0:2], ["test", "internet-access"])

    def test_diagnostics_scopes_stay_on_doctor_action(self):
        for scope in ("control-plane", "runtime", "mcp"):
            result = grammar.match(["system", "diagnostics", scope], "server")
            self.assertEqual(result.get("status"), "ok", ("server", scope, result))
            self.assertEqual(result.get("action"), "doctor")
            self.assertEqual(list(result.get("passthrough") or []), [scope])

        result = grammar.match(["system", "diagnostics", "runtime"], "client")
        self.assertEqual(result.get("status"), "ok", ("client", "runtime", result))
        self.assertEqual(result.get("action"), "doctor")
        self.assertEqual(list(result.get("passthrough") or []), ["runtime"])

        for scope in ("control-plane", "mcp"):
            result = grammar.match(["system", "diagnostics", scope], "client")
            self.assertEqual(result.get("status"), "role", ("client", scope, result))
            self.assertEqual(result.get("need"), "server")
            self.assertEqual(result.get("command"), f"system diagnostics {scope}")
            self.assertIn("managed on the DRLink Server", result.get("message", ""))
            self.assertIn("No changes were applied", result.get("message", ""))


class SliceAConfigurationConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-slice-a-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ.pop("DRLINK_CONFIRM", None)
        self.plane = ControlPlane(self.tmp)
        self.path = Path(self.tmp, "bundle.yaml")
        self.path.write_text(BUNDLE, encoding="utf-8")
        self._stdin = sys.stdin

    def tearDown(self):
        sys.stdin = self._stdin
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM", "DRLINK_SKIP_ACTIVATION"):
            os.environ.pop(key, None)

    def _apply(self, args=None):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(
                list(args or ["system", "apply", "configuration", str(self.path)]),
                root=self.tmp,
                plane=self.plane,
            )
        return rc, out.getvalue(), err.getvalue()

    def test_non_tty_real_change_fails_closed(self):
        from drlink_v24_bundle import prepare_v24_plan

        plan = prepare_v24_plan(self.plane, self.path.read_text(encoding="utf-8"))
        self.assertFalse(plan.no_change)
        self.assertTrue(plan.mutating_changes)
        self.assertFalse(plan.security_impact)
        sys.stdin = io.StringIO("")
        rev = self.plane.current_revision()
        rc, out, err = self._apply()
        self.assertEqual(rc, 1)
        self.assertIn("requires confirmation", err)
        self.assertNotIn("APPLIED", out)
        self.assertEqual(self.plane.current_revision(), rev)
        self.assertIsNone(self.plane.get_object("uxverify-confirm"))

    def test_non_tty_stdin_bundle_fails_closed(self):
        sys.stdin = io.StringIO(BUNDLE + ":end\n")
        rc, out, err = self._apply(["system", "apply", "configuration", "-"])
        self.assertEqual(rc, 1)
        self.assertIn("requires confirmation", err)
        self.assertNotIn("APPLIED", out)
        self.assertIsNone(self.plane.get_object("uxverify-confirm"))

    def test_tty_no_cancels(self):
        sys.stdin = _Tty("n\n")
        rc, out, err = self._apply()
        self.assertEqual(rc, 0, err)
        self.assertIn("Cancelled", out)
        self.assertIsNone(self.plane.get_object("uxverify-confirm"))

    def test_tty_yes_applies(self):
        sys.stdin = _Tty("y\n")
        rc, out, err = self._apply()
        self.assertEqual(rc, 0, err + out)
        self.assertIn("APPLIED", out)
        self.assertIsNotNone(self.plane.get_object("uxverify-confirm"))

    def test_no_change_does_not_require_confirmation(self):
        sys.stdin = _Tty("y\n")
        rc, out, err = self._apply()
        self.assertEqual(rc, 0, err + out)
        self.assertIn("APPLIED", out)
        sys.stdin = io.StringIO("")
        rc, out, err = self._apply()
        self.assertEqual(rc, 0, err + out)
        self.assertIn("NO CHANGE", out)
        self.assertNotIn("requires confirmation", err)


class SliceARemoteServiceConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-slice-a-agent-")
        _agent_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_remote_service_agent(
            self.plane,
            "confirm-delete",
            destination="this-host",
            service="ssh",
            enabled=True,
            oneshot=True,
            root=self.tmp,
            server_reachable=False,
        )
        self._stdin = sys.stdin

    def tearDown(self):
        sys.stdin = self._stdin
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_SKIP_ACTIVATION"):
            os.environ.pop(key, None)

    def _delete_pending(self):
        row = self.plane.conn.execute(
            "SELECT delete_pending FROM agent_remote_services WHERE name = ?",
            ("confirm-delete",),
        ).fetchone()
        self.assertIsNotNone(row)
        return int(row["delete_pending"] or 0)

    def _unset(self, stdin):
        sys.stdin = stdin
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(
                ["unset", "remote-service", "confirm-delete"],
                root=self.tmp,
                plane=self.plane,
            )
        return rc, out.getvalue(), err.getvalue()

    def test_remote_service_delete_tty_no_cancels_without_mutation(self):
        self.assertEqual(self._delete_pending(), 0)
        rc, out, err = self._unset(_Tty("n\n"))
        self.assertEqual(rc, 1, err + out)
        self.assertIn("Cancelled", out)
        self.assertIn("No changes were applied", out)
        self.assertEqual(self._delete_pending(), 0)

    def test_remote_service_delete_non_tty_fails_closed_without_mutation(self):
        self.assertEqual(self._delete_pending(), 0)
        rc, out, err = self._unset(io.StringIO(""))
        self.assertEqual(rc, 1, err + out)
        self.assertIn("requires interactive confirmation", err)
        self.assertIn("No changes were applied", err)
        self.assertNotIn("Remote Service deleted", out)
        self.assertEqual(self._delete_pending(), 0)

    def test_remote_service_delete_tty_yes_applies(self):
        self.assertEqual(self._delete_pending(), 0)
        rc, out, err = self._unset(_Tty("y\n"))
        self.assertEqual(rc, 0, err + out)
        self.assertIn("Remote Service local configuration deleted", out)
        self.assertEqual(self._delete_pending(), 1)


class SliceAInternetCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-slice-a-inet-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_SKIP_ACTIVATION"):
            os.environ.pop(key, None)

    def _run(self, args):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(list(args), root=self.tmp, plane=self.plane)
        return rc, out.getvalue(), err.getvalue()

    def test_show_internet_status_without_egress_tool(self):
        rc, out, err = self._run(["show", "internet-access"])
        self.assertEqual(rc, 0, err)
        self.assertIn("Internet Access", out)
        self.assertIn("Mode        : No Policy", out)
        self.assertIn("Unmatched   : DENY", out)
        self.assertNotIn("frp-egress", out + err)

    def test_test_internet_evaluates_policy_and_dns_without_connection(self):
        real_getaddrinfo = __import__("socket").getaddrinfo

        def _fake_getaddrinfo(host, port, *args, **kwargs):
            if host == "archive.ubuntu.com":
                return [(2, 1, 6, "", ("1.2.3.4", 0))]
            return real_getaddrinfo(host, port, *args, **kwargs)

        import socket

        socket.getaddrinfo = _fake_getaddrinfo
        try:
            rc, out, err = self._run(
                ["test", "internet-access", "10.10.20.25", "archive.ubuntu.com", "443", "https"]
            )
        finally:
            socket.getaddrinfo = real_getaddrinfo
        self.assertEqual(rc, 0, err + out)
        self.assertIn("Internet Access Policy Evaluation", out)
        self.assertIn("Resolution: not executed (explain only)", out)
        self.assertIn("server-side DNS required at runtime", out)
        self.assertIn("DENY", out)
        self.assertIn("No Policy (DENY)", out)
        self.assertNotIn("frp-egress", out + err)


class SliceADiagnosticsScopeTests(unittest.TestCase):
    def test_scope_filter_partitions_checks(self):
        mcp = {"id": "mcp_tls_mode", "section": "security"}
        runtime = {"id": "unit_frps", "section": "runtime"}
        control = {"id": "server_config", "section": "installation"}
        self.assertTrue(frp_doctor.public_scope_keeps(mcp, "mcp"))
        self.assertFalse(frp_doctor.public_scope_keeps(mcp, "control-plane"))
        self.assertTrue(frp_doctor.public_scope_keeps(runtime, "runtime"))
        self.assertFalse(frp_doctor.public_scope_keeps(runtime, "mcp"))
        self.assertTrue(frp_doctor.public_scope_keeps(control, "control-plane"))
        self.assertFalse(frp_doctor.public_scope_keeps(control, "runtime"))

    def _assert_scopes(self, root: str):
        for scope in ("control-plane", "runtime", "mcp"):
            out = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = frp_doctor.main(["--root", root, "--scope", scope, "--skip-network"])
            text = out.getvalue() + err.getvalue()
            self.assertNotIn("unrecognized arguments", text)
            self.assertNotIn("unknown doctor option", text)
            self.assertNotIn("Traceback", text)
            self.assertIn("Scope           : %s" % scope, text)
            self.assertNotEqual(rc, 2, text)
            _text, _code, report = frp_doctor.run_doctor(
                root, {}, skip_network=True, scope=scope
            )
            ids = [c.get("id") for c in report.checks]
            self.assertTrue(ids, (root, scope))
            self.assertNotIn("scope_empty", ids)

    def test_python_scope_does_not_emit_argparse_usage(self):
        server = tempfile.mkdtemp(prefix="drlink-slice-a-doc-")
        _server_root(server)
        self._assert_scopes(server)

    def test_scopes_execute_on_agent_host(self):
        agent = tempfile.mkdtemp(prefix="drlink-slice-a-agent-")
        Path(agent, "etc/frp").mkdir(parents=True)
        Path(agent, "etc/frp/client-state.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "machine_id": "aabbccddeeff00112233445566778899",
                    "hostname": "agent-1",
                    "services": {},
                }
            ),
            encoding="utf-8",
        )
        Path(agent, "etc/frp/frpc.toml").write_text("[common]\nserver_addr = 127.0.0.1\n", encoding="utf-8")
        Path(agent, "etc/frp/client-identity.key").write_text("x", encoding="utf-8")
        self._assert_scopes(agent)

    def test_agent_scopes_are_public_diagnostics(self):
        tmp = tempfile.mkdtemp(prefix="drlink-slice-a-agent-")
        state = Path(tmp, "etc/frp")
        state.mkdir(parents=True)
        (state / "client-state.json").write_text(
            json.dumps({"schema_version": 1, "services": []}) + "\n",
            encoding="utf-8",
        )
        for scope in ("control-plane", "runtime", "mcp"):
            out = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = frp_doctor.main(["--root", tmp, "--scope", scope, "--skip-network"])
            text = out.getvalue() + err.getvalue()
            self.assertNotIn("Traceback", text)
            self.assertNotIn("unknown doctor option", text)
            self.assertNotIn("unrecognized arguments", text)
            self.assertIn("Scope           : %s" % scope, text)
            self.assertNotEqual(rc, 2, text)

    def test_shell_unknown_scope_is_not_internal_usage(self):
        proc = subprocess.run(
            [
                "bash",
                "-c",
                "source lib/frp-doctor-common.sh; frp_doctor_main not-a-scope",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown diagnostics scope", proc.stderr)
        self.assertNotIn("Usage: drlink doctor", proc.stderr)
        self.assertNotIn("unknown doctor option", proc.stderr)


class SliceARestorePreflightTests(unittest.TestCase):
    def _seed_server_and_broadening_backup(self):
        tmp = Path(tempfile.mkdtemp(prefix="drlink-slice-a-restore-"))
        root = tmp / "root"
        archive = tmp / "permissive.tar.gz"
        for rel in (
            "etc/drlink/pki",
            "etc/frp",
            "var/lib/drlink/enrollments",
            "var/lib/drlink/bootstrap",
            "var/lib/drlink/backups",
            "var/log/drlink",
        ):
            (root / rel).mkdir(parents=True, exist_ok=True)
        (root / "etc/drlink/config.json").write_text(
            json.dumps({"role": "server", "public_hostname": "dr.example.test"}) + "\n",
            encoding="utf-8",
        )
        (root / "etc/drlink/version").write_text(
            "PROJECT_VERSION=2.4.0\nRELEASE_CHANNEL=dev\nSOURCE_REF=test\n",
            encoding="utf-8",
        )
        for name in ("ca.key", "ca.crt", "server.key", "server.crt"):
            (root / "etc/drlink/pki" / name).write_text(name + "\n", encoding="utf-8")
        (root / "etc/frp/frps.toml").write_text("bindPort = 443\n", encoding="utf-8")
        (root / "etc/frp/server_token").write_text("token\n", encoding="utf-8")

        env = os.environ.copy()
        env["FRP_DEPLOY_TEST_ROOT"] = str(root)
        env["FRP_BACKUP_ALREADY_LOCKED"] = "1"
        env["DRLINK_SKIP_ACTIVATION"] = "1"

        old_root = os.environ.get("FRP_DEPLOY_TEST_ROOT")
        old_skip = os.environ.get("DRLINK_SKIP_ACTIVATION")
        try:
            os.environ["FRP_DEPLOY_TEST_ROOT"] = str(root)
            os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
            plane = ControlPlane(str(root))
            v24.ensure_v2_schema(plane.conn)
            plane.compile_runtime()
            plane.close()

            backup = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "frp-backup"), str(archive)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(backup.returncode, 0, backup.stdout + backup.stderr)

            plane = ControlPlane(str(root))
            v24.ensure_v2_schema(plane.conn)
            v24.set_network_object(plane, "src", type="ip", value="198.51.100.10", oneshot=True)
            v24.set_network_object(plane, "dst", type="ip", value="198.51.100.20", oneshot=True)
            v24.set_service_object(plane, "ssh", type="tcp", port=22, oneshot=True)
            v24.set_access_rule(
                plane,
                "remote",
                "allow-ssh",
                mode="whitelist",
                source="src",
                destination="dst",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
            plane.close()
        finally:
            if old_root is None:
                os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
            else:
                os.environ["FRP_DEPLOY_TEST_ROOT"] = old_root
            if old_skip is None:
                os.environ.pop("DRLINK_SKIP_ACTIVATION", None)
            else:
                os.environ["DRLINK_SKIP_ACTIVATION"] = old_skip
        return tmp, root, archive, env

    def test_valid_archive_reaches_confirmation_without_loader_traceback(self):
        _tmp, root, archive, env = self._seed_server_and_broadening_backup()
        env["DRLINK_CONFIRM"] = "yes"
        env["FRP_RESTORE_YES"] = "1"
        env["FRP_CTL_TEST_INPUT"] = "1"
        proc = subprocess.run(
            ["bash", str(ROOT / "tools" / "drlink"), "system", "restore", str(archive)],
            cwd=str(ROOT),
            input="n\n",
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        combined = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", combined)
        self.assertNotIn("AttributeError", combined)
        self.assertIn("Restore Data Relay Link", proc.stdout)
        self.assertIn("broaden", combined.lower())
        self.assertIn("Cancelled", combined)
        # User-declined restore is a clean cancellation in the public frpctl
        # workflow; safety is proven by preserved authoritative state below.
        self.assertEqual(proc.returncode, 0)

        old_root = os.environ.get("FRP_DEPLOY_TEST_ROOT")
        try:
            os.environ["FRP_DEPLOY_TEST_ROOT"] = str(root)
            plane = ControlPlane(str(root))
            self.assertEqual(v24.get_access_policy(plane, "remote")["mode"], "whitelist")
            plane.close()
        finally:
            if old_root is None:
                os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
            else:
                os.environ["FRP_DEPLOY_TEST_ROOT"] = old_root

    def test_public_restore_rejects_undocumented_yes_option(self):
        tmp = tempfile.mkdtemp(prefix="drlink-slice-a-restore-grammar-")
        _server_root(tmp)
        archive = Path(tmp) / "backup.tar.gz"
        archive.write_bytes(b"not-used-because-grammar-must-reject-first")
        env = os.environ.copy()
        env["FRP_DEPLOY_TEST_ROOT"] = tmp
        proc = subprocess.run(
            [
                "bash",
                str(ROOT / "tools" / "drlink"),
                "system",
                "restore",
                str(archive),
                "--yes",
            ],
            cwd=str(ROOT),
            input="",
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        combined = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(
            "do not use --options" in combined.lower()
            or "unexpected arguments" in combined.lower()
            or "usage: system restore <path>" in combined.lower(),
            combined,
        )
        self.assertNotIn("Traceback", combined)


if __name__ == "__main__":
    unittest.main()
