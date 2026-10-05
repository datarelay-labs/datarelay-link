#!/usr/bin/env python3
from __future__ import annotations

import io
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import ipaddress
import signal
import time
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
sys.path.insert(0, str(LIB))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24
import frp_ctl_grammar as grammar
import frp_cli_catalog as catalog


class CliFeatureScenarioRemediation(unittest.TestCase):
    def test_generated_enrollment_guidance_uses_agent_nouns(self):
        loader = importlib.machinery.SourceFileLoader(
            "enrollment_guidance_regression", str(ROOT / "tools/frp-create-client")
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        enrollment = importlib.util.module_from_spec(spec)
        loader.exec_module(enrollment)
        output = io.StringIO()
        with redirect_stdout(output):
            enrollment.print_manual(
                {}, {"id": "example", "secret": "example", "expires_at_iso": "example"},
                600, "203.0.113.10", 443, "https://203.0.113.10/enroll", "0" * 64,
                "https://203.0.113.10/artifacts/agent/bootstrap-client.sh",
            )
            enrollment.print_one_line(
                "example-ticket", 600, "", "203.0.113.10", 443,
                "https://203.0.113.10/enroll", "0" * 64,
                "https://203.0.113.10/artifacts/agent/bootstrap-client.sh",
                "", 22, legacy_env=True, cfg={},
            )
            enrollment.print_one_line_windows(
                "example-ticket", 600, "", "203.0.113.10", 443,
                "https://203.0.113.10/enroll", "0" * 64,
                "https://203.0.113.10/artifacts/agent/bootstrap-client.ps1", cfg={},
            )
        rendered = output.getvalue()
        self.assertIn("Agent install:", rendered)
        self.assertIn("Zero-touch Agent command", rendered)
        self.assertIn("Zero-touch Windows Agent command", rendered)
        self.assertNotRegex(rendered, r"(?i)\bclient (install|command|after enrollment)")
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            enrollment.require_onboarding_config({})
        self.assertIn("Agent onboarding", errors.getvalue())

    def _completion_payload(self, root_key="FRP_CTL_TEST_ROOT"):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("FRP_", "DRLINK_"))}
        env[root_key] = self.tmp
        result = subprocess.run(
            ["bash", str(ROOT / "tools/frpctl"), "--print-grammar-payload"],
            env=env, text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def test_completion_reads_authoritative_agent_names_without_mutation(self):
        root = Path(self.tmp)
        (root / "etc/drlink/config.json").unlink()
        state = root / "etc/frp/client-state.json"
        state.parent.mkdir(parents=True)
        state.write_text('{"services":{"stale-json-service":{}}}\n')
        v24.ensure_v2_schema(self.plane.conn)
        for name, enabled, deleted in (("http", 1, 0), ("disabled-service", 0, 0),
                                       ("pending-delete", 1, 1)):
            self.plane.conn.execute(
                "INSERT INTO agent_remote_services "
                "(name, destination, service_object, enabled, delete_pending, updated_at) "
                "VALUES (?, 'this-host', 'http', ?, ?, 'now')",
                (name, enabled, deleted),
            )
        before = self.plane.current_revision()
        payload = self._completion_payload("FRP_CLIENT_TEST_ROOT")
        self.assertEqual(payload["local_services"], ["disabled-service", "http"])
        self.assertFalse(payload["inventory_warning"])
        self.assertEqual(grammar.completion_candidates(
            "show remote-service h", "client", [], {}, payload["local_services"],
        ), ["http"])
        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual(self.plane.conn.execute(
            "SELECT count(*) FROM agent_remote_services").fetchone()[0], 3)

    def test_completion_reads_canonical_hosts_and_unambiguous_selectors(self):
        mids = ["12345678a" + "0" * 23, "12345678b" + "0" * 23]
        for mid, label in zip(mids, ("audit-rocky9", "audit-rocky8")):
            self.plane.upsert_client(mid, label=label, hostname="duplicate-hostname")
        before = self.plane.current_revision()
        payload = self._completion_payload()
        self.assertFalse(payload["inventory_warning"])
        self.assertIn("audit-rocky9", payload["names"])
        self.assertIn("audit-rocky8", payload["names"])
        self.assertIn("12345678a", payload["names"])
        self.assertIn("12345678b", payload["names"])
        self.assertNotIn("12345678", payload["names"])
        self.assertNotIn("duplicate-hostname", payload["names"])
        self.assertEqual(grammar.completion_candidates(
            "show managed-host audit-rocky9", "server", payload["names"], {}, [],
        ), ["audit-rocky9"])
        self.assertEqual(self.plane.current_revision(), before)

    def test_completion_empty_database_wins_over_stale_json_inventory(self):
        root = Path(self.tmp)
        state = root / "etc/frp/client-state.json"
        state.parent.mkdir(parents=True)
        state.write_text('{"services":{"stale-service":{}}}\n')
        v24.ensure_v2_schema(self.plane.conn)
        payload = self._completion_payload()
        self.assertEqual(payload["names"], [])
        self.assertEqual(payload["local_services"], [])
        self.assertFalse(payload["inventory_warning"])

    def test_completion_unreadable_database_does_not_use_stale_json(self):
        root = Path(self.tmp)
        state = root / "etc/frp/client-state.json"
        state.parent.mkdir(parents=True)
        state.write_text('{"services":{"stale-service":{}}}\n')
        self.plane.close()
        db = root / "var/lib/drlink/drlink.db"
        db.write_bytes(b"not a SQLite database")
        payload = self._completion_payload()
        self.assertEqual(payload["names"], [])
        self.assertEqual(payload["local_services"], [])
        self.assertTrue(payload["inventory_warning"])
        self.assertEqual(db.read_bytes(), b"not a SQLite database")

    def test_completion_does_not_create_a_missing_database(self):
        self.plane.close()
        db = Path(self.tmp) / "var/lib/drlink/drlink.db"
        db.unlink()
        self._completion_payload()
        self.assertFalse(db.exists())

    def test_private_inventory_rpc_is_not_a_public_frontend_root(self):
        env = dict(os.environ, FRP_CTL_TEST_ROOT=self.tmp)
        result = subprocess.run(
            ["bash", str(ROOT / "tools/drlink"), "--print-grammar-payload"],
            env=env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("help commands", result.stderr)
        self.assertNotIn('"inventory_warning"', result.stdout)
        self.assertIsInstance(self._completion_payload(), dict)

    def test_guided_menu_identifies_each_host_role(self):
        self.assertIn("DRLink Server", catalog.render_guided_menu("server"))
        self.assertIn("Agent Host", catalog.render_guided_menu("client"))
        for role, title in (("server", "DRLink Server"),
                            ("client", "Agent Host")):
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; frpctl_render_nav_menu "$2"',
                 "menu-renderer-test", str(ROOT / "tools/frpctl"), role],
                env=dict(os.environ, FRP_CTL_TEST_ROOT=self.tmp,
                         FRP_CTL_SOURCED="1"),
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Data Relay Link — " + title, result.stdout)

    def test_membership_help_does_not_claim_retirement_confirmation(self):
        tokens = ["unset", "managed-host", "audit-host", "group", "edge"]
        member = catalog.find(tokens)
        self.assertFalse(member["destructive"])
        self.assertEqual(member["risk"], "none")
        self.assertEqual(member["confirmation"], "none")
        text = grammar.context_help(tokens, "server")
        self.assertIn("explicit command", text)
        self.assertNotIn("Confirmation: y_n", text)
        retirement = catalog.find(tokens[:3])
        self.assertTrue(retirement["destructive"])
        self.assertEqual(retirement["risk"], "irreversible")
        self.assertEqual(retirement["confirmation"], "y_n")
        self.assertEqual(grammar.match(tokens, "server")["action"], "remove_group_member")

    def test_policy_selector_consumes_only_first_host(self):
        class Network:
            network_address = ipaddress.ip_address("198.51.100.0")

            def hosts(self):
                yield ipaddress.ip_address("198.51.100.1")
                raise AssertionError("policy tests must not enumerate the network")

        with patch.object(v24.ipaddress, "ip_network", return_value=Network()):
            self.assertEqual(v24._representative_ip_from_value("198.51.100.0/24"), "198.51.100.1")
        for value, expected in (("198.51.100.0/31", "198.51.100.0"),
                                ("198.51.100.1/32", "198.51.100.1"),
                                ("2001:db8::/127", "2001:db8::"),
                                ("2001:db8::1/128", "2001:db8::1")):
            self.assertEqual(v24._representative_ip_from_value(value), expected)

    def test_public_bundle_rejects_legacy_schema_before_any_effect(self):
        path = Path(self.tmp) / "legacy.yaml"
        path.write_text("apiVersion: drlink.datarelay.run/v1alpha1\nkind: ConfigurationBundle\nspec:\n  objects:\n    - name: legacy-input\n      type: Host\n      values: [198.51.100.3]\n")
        before = self.plane.conn.total_changes
        for tokens in (["test", "configuration"], ["system", "diff", "configuration"],
                       ["system", "apply", "configuration"]):
            with self.subTest(tokens=tokens):
                with self.assertRaises(SystemExit) as exc:
                    self._dispatch(tokens + [str(path)])
                self.assertIn("No changes were applied", str(exc.exception))
            self.assertIsNone(self.plane.get_object("legacy-input"))
        self.assertEqual(self.plane.conn.total_changes, before)

    def test_configuration_export_failure_does_not_emit_legacy_file(self):
        path = Path(self.tmp) / "export.yaml"
        with patch("drlink_v24_bundle.export_configuration_v24", side_effect=RuntimeError("export failed")):
            with self.assertRaises(RuntimeError):
                cli._configuration_export(self.plane, [str(path)])
        self.assertFalse(path.exists())

    def test_public_configuration_preview_keeps_authority_read_only(self):
        path = Path(self.tmp) / "canonical.yaml"
        path.write_text("configurationBundle:\n  context: server\n  networkObjects:\n    - name: preview-only\n      type: ip\n      value: 198.51.100.3\n")
        before = self.plane.current_revision()
        query = ControlPlane(self.tmp, read_only=True)
        try:
            original = query.conn
            for tokens in (["test", "configuration"], ["system", "diff", "configuration"]):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.dispatch(tokens + [str(path)], root=self.tmp, plane=query), 0)
                self.assertIs(query.conn, original)
                self.assertTrue(query._read_only)
                self.assertIsNone(query.get_object("preview-only"))
                self.assertEqual(query.current_revision(), before)
                self.assertEqual(query.conn.total_changes, 0)
        finally:
            query.close()

    def test_repl_interrupt_terminates_command_group_and_retains_prompt(self):
        import signal
        import frp_ctl_repl as repl
        backend = unittest.mock.Mock(pid=123456, returncode=-signal.SIGTERM)
        backend.wait.side_effect = [KeyboardInterrupt(), -signal.SIGTERM]
        err = io.StringIO()
        with patch.object(repl.subprocess, "Popen", return_value=backend) as launch, \
                patch.object(repl.os, "killpg") as terminate, \
                patch("builtins.input", side_effect=["show status", "exit"]), \
                patch.object(repl.LineEditor, "bind"), redirect_stderr(err):
            self.assertEqual(repl.run_repl("drlink", {"role": "server"}), 0)
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        self.assertEqual(terminate.call_args_list, [unittest.mock.call(backend.pid, signal.SIGTERM),
                                                    unittest.mock.call(backend.pid, signal.SIGKILL)])
        self.assertIn("Command interrupted", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn("No changes were applied", err.getvalue())

    def test_repl_interrupt_stops_real_backend_and_stubborn_descendant(self):
        backend = Path(self.tmp) / "blocking_backend.py"
        pids = Path(self.tmp) / "command_pids.json"
        backend.write_text('''import json, os, signal, sys, time
ready_read, ready_write = os.pipe()
child = os.fork()
if child == 0:
    os.close(ready_read)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.write(ready_write, b"1")
    os.close(ready_write)
    while True:
        time.sleep(1)
os.close(ready_write)
assert os.read(ready_read, 1) == b"1"
os.close(ready_read)
with open(sys.argv[1] + ".tmp", "w") as f:
    json.dump([os.getpid(), child], f)
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
while True:
    time.sleep(1)
''')
        runner = "import sys,os;sys.path.insert(0,sys.argv[1]);from frp_ctl_repl import _run_backend;assert _run_backend([sys.executable,sys.argv[2],sys.argv[3]],os.environ.copy()) is None;print('PROMPT_RECOVERED')"
        proc = subprocess.Popen([sys.executable, "-c", runner, str(LIB), str(backend), str(pids)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        owned = []
        try:
            deadline = time.monotonic() + 5
            while not pids.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(pids.exists(), "test backend did not start")
            owned = json.loads(pids.read_text())
            proc.send_signal(signal.SIGINT)
            out, err = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, err)
            self.assertIn("PROMPT_RECOVERED", out)
            self.assertIn("Command interrupted", err)
            self.assertNotIn("Traceback", err)
            def active(pid):
                status = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                                        text=True, capture_output=True)
                return status.returncode == 0 and bool(status.stdout.strip()) and not status.stdout.strip().startswith("Z")
            for pid in owned:
                deadline = time.monotonic() + 2
                while active(pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(active(pid), "command descendant survived")
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if owned:
                try:
                    os.killpg(owned[0], signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_doctor_checks_endpoint_against_its_own_pool(self):
        import frp_doctor as doctor
        cfg = {"port_start": 6000, "port_end": 6098}
        def registry(*services):
            return {"schema_version": 2, "clients": {"a" * 32: {
                "hostname": "agent", "services": {str(i): s for i, s in enumerate(services)}}}}
        fixed = {"remote_port": 6200, "pool_class": "fixed-tcp"}
        normal = {"remote_port": 6000, "pool_class": "normal"}
        self.assertEqual(doctor.validate_registry(registry(fixed, normal), cfg)[0], doctor.PASS)
        self.assertEqual(doctor.validate_registry(registry({**normal, "remote_port": 6200}), cfg)[0], doctor.WARN)
        self.assertEqual(doctor.validate_registry(registry({**fixed, "remote_port": 6000}), cfg)[0], doctor.WARN)
        cfg.update(tcp_relay_port_start=6300, tcp_relay_port_end=6399)
        self.assertEqual(doctor.validate_registry(registry(fixed), cfg)[0], doctor.WARN)
        self.assertEqual(doctor.validate_registry(registry({**fixed, "remote_port": 6300}), cfg)[0], doctor.PASS)
        self.assertEqual(doctor.validate_registry(registry(fixed, fixed), cfg)[0], doctor.FAIL)

    def test_update_leaves_disclose_outage_without_extra_confirmation(self):
        rows = {tuple(r["path"]): r for r in json.loads((LIB / "frp_cli_final_commands.json").read_text())}
        for target in ("product", "engine"):
            row = rows[("system", "update", target)]
            self.assertTrue(row["destructive"])
            self.assertEqual(row["risk"], "outage")
            self.assertEqual(row["confirmation"], "none")
            self.assertIn("restart", row["detail"])

    def test_remote_service_manage_opens_detail_and_cancel_is_read_only(self):
        item = next(r for r in catalog.NAVIGATION_TREE["client.remote_services"] if r[0] == "client_rs_manage")
        self.assertEqual(item[3:], ("workflow", "manage_remote_service"))
        script = '''source "$1"
frpctl_nav_prompt_id() { printf http; }
frpctl_read() { printf 3; }
frpctl_dispatch() { printf 'DISPATCH'; printf ' <%s>' "$@"; printf '\\n'; }
frpctl_nav_workflow manage_remote_service
'''
        env = dict(os.environ, FRP_CTL_SOURCED="1")
        proc = subprocess.run(["bash", "-c", script, "regression", str(ROOT / "tools/frpctl")], env=env, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("DISPATCH <show> <remote-service> <http>", proc.stdout)
        self.assertNotIn("DISPATCH <set>", proc.stdout)
        self.assertNotIn("DISPATCH <unset>", proc.stdout)

    def test_managed_host_selector_help_uses_current_noun(self):
        hosts = [{"id": "abcd1234", "label": "agent", "hostname": "agent"}]
        for text in (grammar.context_help(["unset", "managed-host"], "server", names=["abcd1234"], clients=hosts),
                     grammar.format_tab_candidates("unset managed-host ", ["abcd1234"], "server", clients=hosts)):
            self.assertIn("HOST ID", text)
            self.assertNotIn("CLIENT ID", text)

    def test_manage_host_menu_inspects_selected_host_without_mutating_on_back(self):
        item = next(r for r in catalog.NAVIGATION_TREE["server.hosts"] if r[0] == "server_hosts_manage")
        self.assertEqual(item[3:], ("workflow", "manage_host"))
        script = '''source "$1"
frpctl_nav_prompt_id() { printf audit-agent; }
frpctl_read() { local choice; read -r choice; printf '%s' "$choice"; }
frpctl_dispatch() { printf 'DISPATCH'; printf ' <%s>' "$@"; printf '\\n'; }
frpctl_nav_workflow manage_host
'''
        proc = subprocess.run(["bash", "-c", script, "regression", str(ROOT / "tools/frpctl")],
                              env=dict(os.environ, FRP_CTL_SOURCED="1"), input="1\n5\n",
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("DISPATCH <show> <managed-host> <audit-agent>", proc.stdout)
        self.assertIn("DISPATCH <show> <managed-host> <audit-agent> <agent>", proc.stdout)
        self.assertNotIn("DISPATCH <set>", proc.stdout)
        self.assertNotIn("DISPATCH <unset>", proc.stdout)

    def test_agent_outage_leaves_disclose_effect_and_invocation_approval(self):
        paths = [("system", "pause"), ("system", "restart"), ("system", "autostart", "disable"),
                 ("system", "synchronize"), ("set", "remote-service")]
        rows = {tuple(r["path"]): r for r in catalog.COMMANDS}
        for path in paths:
            with self.subTest(path=path):
                row = rows[path]
                self.assertTrue(row["destructive"])
                self.assertEqual(row["risk"], "outage")
                self.assertEqual(row["confirmation"], "none")
                self.assertIn("explicit", row["detail"].lower())
        self.assertFalse(rows[("system", "autostart")]["destructive"])
        self.assertEqual(rows[("system", "autostart")]["risk"], "none")

    def test_managed_host_remote_services_empty_state_names_agent_next_action(self):
        v24.ensure_v2_schema(self.plane.conn)
        self.plane.upsert_client("c" * 32, label="empty-agent", hostname="empty-agent")
        before = self.plane.current_revision()
        rc, out, err = self._dispatch(["show", "managed-host", "empty-agent", "remote-services"])
        self.assertEqual(rc, 0, err)
        self.assertIn("No Remote Services", out)
        self.assertIn("Agent Host", out)
        self.assertIn("show remote-services", out)
        self.assertEqual(self.plane.current_revision(), before)

    def test_calculated_policy_and_referenced_edit_confirmation_is_discoverable(self):
        rows = {tuple(r["path"]): r for r in catalog.COMMANDS}
        for res in ("remote-access", "internet-access", "ai-access", "network-object", "network-group",
                    "service-object", "service-group", "permission-object", "permission-group"):
            with self.subTest(resource=res):
                row = rows[("set", res)]
                self.assertTrue(row["destructive"])
                self.assertEqual(row["risk"], "security_change")
                self.assertEqual(row["confirmation"], "conditional_y_n")
                self.assertIn("calculated", row["detail"].lower())

    def test_agent_obsolete_client_error_names_server_owner(self):
        result = grammar.match(["client", "?"], "client")
        self.assertEqual(result["status"], "error")
        self.assertIn("DRLink Server", result["message"])

    def test_generated_enrollment_and_partial_role_use_agent_host_nouns(self):
        proc = subprocess.run(["bash", "-c", 'source "$1"; frp_ux_intro; frp_ux_enrollment_help',
                               "regression", str(LIB / "frp-client-common.sh")], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Agent Host", proc.stdout)
        self.assertNotIn("this client", proc.stdout)
        import frp_doctor as doctor
        self.assertIn("Managed Hosts", doctor.validate_registry({"schema_version": 2, "clients": {}})[1])
        partial = Path(self.tmp) / "partial-agent"
        (partial / "etc/frp").mkdir(parents=True)
        (partial / "etc/frp/client-state.json").write_text("{}")
        self.assertIn("Agent Host", doctor.detect_role(doctor.Paths(str(partial)))["label"])
        switch = (ROOT / "install-server.sh").read_text().split("frp_confirm_mode_switch() {", 1)[1].split("\n}", 1)[0]
        self.assertNotIn("client apply", switch)
        self.assertIn("DEPLOYMENT_MODES.md", switch)

    def test_installed_endpoint_fallback_reads_live_default_root(self):
        import frp_server_config as server_config
        import drlink_v24_cli as public_cli
        config = Path(self.tmp) / "etc/drlink/config.json"
        config.write_text(json.dumps({"public_ip": "203.0.113.10"}))
        def fixture_root(value):
            return Path(self.tmp) if str(value) == "/" else Path(value)
        with patch.object(server_config, "Path", side_effect=fixture_root), \
                patch.dict(os.environ, {"DRLINK_HOST": ""}):
            self.assertEqual(server_config.resolve_public_endpoint_host(root=None), "203.0.113.10")
            self.assertEqual(public_cli._public_endpoint_host(unittest.mock.Mock(root=None)), "203.0.113.10")
            config.write_text(json.dumps({"public_ip": "203.0.113.10", "public_hostname": "relay.example.test"}))
            self.assertEqual(server_config.resolve_public_endpoint_host(root=None), "relay.example.test")

    def test_partial_agent_doctor_enrollment_recovery_names_server_owner(self):
        partial = Path(self.tmp) / "partial-agent"
        (partial / "etc/frp").mkdir(parents=True)
        (partial / "etc/frp/client-state.json").write_text('{"schema_version": 1, "services": {}}')
        (partial / "etc/frp/client-identity.key").write_text("disposable-test-identity\n")
        env = dict(os.environ, FRP_CTL_TEST_ROOT=str(partial), FRP_CLIENT_TEST_ROOT=str(partial),
                   FRP_DEPLOY_TEST_ROOT=str(partial), FRP_SKIP_SYSTEMD="1", FRP_DOCTOR_SKIP_NETWORK="1")
        proc = subprocess.run([str(ROOT / "tools/drlink"), "system", "diagnostics", "--json"],
                              env=env, text=True, capture_output=True)
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        check = next(c for c in data["checks"] if c["id"] == "client_identity")
        self.assertIn("on the DRLink Server", check["recommendation"])
        self.assertIn("re-enroll this Agent Host", check["recommendation"])

    def test_update_fixture_copy_excludes_audit_evidence_before_reading(self):
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                source = Path(self.tmp) / ("source-fallback" if fallback else "source-rsync")
                dest = Path(self.tmp) / ("copy-fallback" if fallback else "copy-rsync")
                source.mkdir()
                (source / "release-manifest.json").write_text("{}")
                (source / "VERSION").write_text("VERSION=2.4.0\n")
                for name in (".git", "dist", "e2e-reports"):
                    (source / name).mkdir()
                    leaf = source / name / "excluded"
                    leaf.write_text("disposable audit artifact")
                    leaf.chmod(0)
                script = 'source "$1"\n'
                if fallback:
                    script += 'command() { if [[ "${1:-}" == "-v" && "${2:-}" == "rsync" ]]; then return 1; fi; builtin command "$@"; }\n'
                script += 'frp_test_copy_repo_tree "$2" "$3"'
                proc = subprocess.run(["bash", "-c", script, "regression",
                                       str(ROOT / "tests/lib/frp-test-safe-copy.sh"), str(source), str(dest)],
                                      text=True, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual((dest / "VERSION").read_text(), "VERSION=2.4.0\n")
                for name in (".git", "dist", "e2e-reports"):
                    self.assertFalse((dest / name).exists())

    def test_remote_service_edit_keeps_disabled_default_until_review(self):
        import drlink_v24_wizard as wizard
        self.plane.conn.execute("INSERT INTO agent_remote_services(name,destination,service_object,enabled,updated_at) VALUES ('http','this-host','http',0,'2026-10-05T00:00:00Z')")
        with patch.object(wizard, "_io"), patch.object(wizard, "_ask_text", return_value="this-host"), \
                patch.object(wizard, "_ask_choice", return_value="http"), \
                patch.object(wizard, "_ask_yes_no", return_value=False) as enabled, \
                patch.object(wizard, "_review_menu", return_value="cancel"), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(wizard.run_remote_service_wizard(self.plane, "http"), 0)
        self.assertFalse(enabled.call_args.kwargs["default"])
        self.assertEqual(self.plane.conn.execute("SELECT enabled FROM agent_remote_services WHERE name='http'").fetchone()[0], 0)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-cli-fcs-remediation-")
        root = Path(self.tmp)
        (root / "etc/drlink").mkdir(parents=True, exist_ok=True)
        (root / "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_SKIP_ACTIVATION", None)
        shutil.rmtree(self.tmp)

    def _dispatch(self, tokens, stdin_text=""):
        out, err = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli.dispatch(tokens, root=self.tmp, plane=self.plane)
        finally:
            sys.stdin = old_stdin
        return rc, out.getvalue(), err.getvalue()

    def _exists(self, table, name):
        return self.plane.conn.execute(
            "SELECT 1 FROM %s WHERE name = ?" % table, (name,)
        ).fetchone() is not None

    def _seed_destructive_resources(self):
        v24.set_network_object(
            self.plane, "netx", type="ip", value="198.51.100.10", oneshot=True
        )
        v24.set_network_object(
            self.plane, "net-member", type="ip", value="198.51.100.11", oneshot=True
        )
        v24.set_network_group(
            self.plane, "netgrp", members=["net-member"], oneshot=True
        )

        v24.set_service_object(
            self.plane, "svcx", type="tcp", port=2201, oneshot=True
        )
        v24.set_service_object(
            self.plane, "svc-member", type="tcp", port=2202, oneshot=True
        )
        v24.set_service_group(
            self.plane, "svcgrp", members=["svc-member"], oneshot=True
        )

        v24.set_permission_object(
            self.plane, "permx", permissions=["host-info"], oneshot=True
        )
        v24.set_permission_object(
            self.plane, "perm-member", permissions=["process-read"], oneshot=True
        )
        v24.set_permission_group(
            self.plane, "permgrp", members=["perm-member"], oneshot=True
        )
        self.plane.set_ai_principal("aix", enabled=True)

    def test_destructive_resource_unset_requires_confirmation(self):
        self._seed_destructive_resources()
        cases = [
            ("network-object", "netx", "objects"),
            ("network-group", "netgrp", "object_groups"),
            ("service-object", "svcx", "service_objects"),
            ("service-group", "svcgrp", "service_groups"),
            ("permission-object", "permx", "permission_objects"),
            ("permission-group", "permgrp", "permission_groups"),
            ("ai-identity", "aix", "ai_principals"),
        ]
        for resource, name, table in cases:
            with self.subTest(resource=resource, phase="cancel"):
                rc, out, err = self._dispatch(["unset", resource, name], "\n")
                self.assertNotEqual(rc, 0, out + err)
                self.assertTrue(self._exists(table, name))
                self.assertIn("Continue? [y/N]", out)
                self.assertIn("No changes were applied.", out)

            with self.subTest(resource=resource, phase="confirm"):
                rc, out, err = self._dispatch(["unset", resource, name], "y\n")
                self.assertEqual(rc, 0, out + err)
                self.assertFalse(self._exists(table, name))
                self.assertIn("deleted", out.lower())

    def test_catalog_has_leaf_accurate_destructive_metadata(self):
        rows = json.loads((LIB / "frp_cli_final_commands.json").read_text(encoding="utf-8"))
        by_path = {tuple(row["path"]): row for row in rows}

        for path in [
            ("unset", "enrollment"),
            ("unset", "network-object"),
            ("unset", "network-group"),
            ("unset", "service-object"),
            ("unset", "service-group"),
            ("unset", "permission-object"),
            ("unset", "permission-group"),
            ("unset", "managed-host"),
            ("unset", "ai-identity"),
        ]:
            row = by_path[path]
            self.assertTrue(row["destructive"], path)
            self.assertEqual(row["risk"], "irreversible", path)
            self.assertEqual(row["confirmation"], "y_n", path)

        for resource in ("remote-access", "internet-access", "ai-access"):
            rule = by_path[("unset", resource)]
            self.assertTrue(rule["destructive"])
            self.assertEqual(rule["risk"], "security_change")
            self.assertEqual(rule["confirmation"], "conditional_y_n")
            reset = by_path[("unset", resource, "policy")]
            self.assertTrue(reset["destructive"])
            expected_risk = "security_widening" if resource == "remote-access" else "security_change"
            self.assertEqual(reset["risk"], expected_risk)
            self.assertEqual(reset["confirmation"], "y_n")
            if resource in ("internet-access", "ai-access"):
                self.assertIn("DENY ALL", reset["detail"])

        for op in ("issue", "import", "renew"):
            row = by_path[("system", "certificate", op)]
            self.assertTrue(row["destructive"])
            self.assertEqual(row["risk"], "outage")
            self.assertEqual(row["confirmation"], "none")
        for op in ("status", "preflight"):
            row = by_path[("system", "certificate", op)]
            self.assertFalse(row["destructive"])
            self.assertEqual(row["risk"], "none")
            self.assertEqual(row["confirmation"], "none")

    def test_access_enforcement_child_metadata_matches_runtime_effects(self):
        rows = json.loads((LIB / "frp_cli_final_commands.json").read_text(encoding="utf-8"))
        by_path = {tuple(row["path"]): row for row in rows}
        expected = {
            ("set", "remote-access", "enabled"): ("security_change", "none", "saved mode and Rules"),
            ("set", "remote-access", "disabled"): ("security_widening", "conditional_y_n", "ALLOW ALL"),
            ("set", "internet-access", "enabled"): ("security_widening", "conditional_y_n", "may become ALLOW"),
            ("set", "internet-access", "disabled"): ("outage", "conditional_y_n", "DENY ALL"),
            ("set", "ai-access", "enabled"): ("security_widening", "conditional_y_n", "authorize AI operations"),
            ("set", "ai-access", "disabled"): ("outage", "conditional_y_n", "DENY ALL"),
        }
        for path, (risk, confirmation, marker) in expected.items():
            with self.subTest(path=path):
                row = by_path[path]
                self.assertEqual(row["risk"], risk)
                self.assertEqual(row["confirmation"], confirmation)
                self.assertIn(marker, row["detail"])
                help_result = grammar.match([*path, "?"], role="server")
                self.assertEqual(help_result.get("status"), "ok", help_result)
                text = str(help_result.get("message") or "")
                self.assertIn("Risk: %s" % risk, text)
                if confirmation != "none":
                    self.assertIn("Confirmation: %s" % confirmation, text)

    def test_ai_credential_and_oauth_leaf_risk_metadata_is_truthful(self):
        rows = json.loads((LIB / "frp_cli_final_commands.json").read_text(encoding="utf-8"))
        by_path = {tuple(row["path"]): row for row in rows}
        expected = {
            ("system", "credential", "rotate", "ai-identity"): (True, "security_change"),
            ("system", "credential", "revoke", "ai-identity"): (True, "outage"),
            ("system", "credential", "configure", "ai-identity"): (True, "security_change"),
            ("system", "credential", "approve-oauth"): (False, "security_widening"),
            ("system", "credential", "deny-oauth"): (False, "security_change"),
        }
        for path, (destructive, risk) in expected.items():
            with self.subTest(path=path):
                row = by_path[path]
                self.assertEqual(bool(row["destructive"]), destructive)
                self.assertEqual(row["risk"], risk)
                self.assertEqual(row["confirmation"], "none")
                self.assertIn("explicit", row["detail"].lower())
                help_result = grammar.match([*path, "?"], role="server")
                self.assertEqual(help_result.get("status"), "ok", help_result)
                self.assertIn("Risk: %s" % risk, str(help_result.get("message") or ""))

    def test_canonical_docs_cover_current_server_lifecycle_commands(self):
        master = (ROOT / "docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md").read_text(encoding="utf-8")
        reference = (ROOT / "docs/CLI_REFERENCE.md").read_text(encoding="utf-8")
        ai = (ROOT / "docs/AI_ACCESS_MCP.md").read_text(encoding="utf-8")
        required_server = (
            "system backup validate <FILE>",
            "system credential rotate ai-identity <IDENTITY>",
            "system credential revoke ai-identity <IDENTITY>",
            "system credential configure ai-identity <IDENTITY> authentication <static-bearer|oauth>",
            "system credential approve-oauth <PENDING-ID> [AI-IDENTITY]",
            "system credential deny-oauth <PENDING-ID>",
            "system update check-engine",
        )
        for command in required_server:
            self.assertIn(command, master, command)
            self.assertIn(command, reference, command)
        for command in required_server[1:6]:
            self.assertIn(command, ai, command)

    def test_restricted_plane_help_is_whitelist_only(self):
        internet = catalog.domain_help("internet-access", "server") or ""
        ai = catalog.domain_help("ai-access", "server") or ""
        self.assertIn("WHITELIST-only", internet)
        self.assertIn("deny-by-default", internet)
        self.assertNotIn("BLACKLIST / WHITELIST", internet)
        self.assertIn("WHITELIST-only", ai)
        self.assertIn("deny-by-default", ai)
        self.assertIn("mode whitelist", ai)
        self.assertNotIn("blacklist|whitelist", ai)

    def test_wrong_role_context_help_fails_with_ownership_guidance(self):
        cases = (
            (["test", "internet-access", "?"], "client", "DRLink Server"),
            (["set", "network-object", "?"], "client", "DRLink Server"),
            (["set", "remote-service", "?"], "server", "Agent Host"),
            (["system", "autostart", "?"], "server", "Agent Host"),
        )
        for tokens, role, marker in cases:
            with self.subTest(tokens=tokens, role=role):
                result = grammar.match(tokens, role=role)
                self.assertEqual(result.get("status"), "role", result)
                self.assertIn(marker, str(result.get("message") or ""))

    def test_wrong_role_context_help_public_cli_is_nonzero(self):
        def run_cli(root, tokens, *, client=False):
            env = os.environ.copy()
            env.update(
                {
                    "FRP_CTL_TEST_ROOT": str(root),
                    "FRP_CTL_FORCE_DRLINK": "1",
                    "FRP_CTL_CMD_NAME": "drlink",
                    "FRP_CTL_BIN_DIR": str(ROOT / "tools"),
                    "FRP_CLIENT_LIB": str(ROOT / "lib/frp-client-common.sh"),
                    "FRP_SKIP_SYSTEMD": "1",
                }
            )
            if client:
                env["FRP_CLIENT_TEST_ROOT"] = str(root)
                env.pop("FRP_DEPLOY_TEST_ROOT", None)
            else:
                env["FRP_DEPLOY_TEST_ROOT"] = str(root)
                env.pop("FRP_CLIENT_TEST_ROOT", None)
            return subprocess.run(
                [str(ROOT / "tools/frpctl"), *tokens],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        server = run_cli(self.tmp, ["set", "remote-service", "?"])
        self.assertEqual(server.returncode, 1, server.stdout + server.stderr)
        self.assertIn("Agent Host", server.stderr)

        client = Path(tempfile.mkdtemp(prefix="drlink-wrong-role-help-client-"))
        (client / "etc/frp").mkdir(parents=True, exist_ok=True)
        (client / "etc/frp/client-state.json").write_text(
            '{"client_id":"audit-agent","hostname":"audit-agent","services":{}}\n',
            encoding="utf-8",
        )
        agent = run_cli(client, ["test", "internet-access", "?"], client=True)
        self.assertEqual(agent.returncode, 1, agent.stdout + agent.stderr)
        self.assertIn("DRLink Server", agent.stderr)

        for scope in ("mcp", "control-plane"):
            scoped = run_cli(
                client, ["system", "diagnostics", scope, "?"], client=True
            )
            self.assertEqual(scoped.returncode, 1, scoped.stdout + scoped.stderr)
            self.assertIn("DRLink Server", scoped.stderr)

    def test_system_help_keeps_check_engine_server_only(self):
        server_help = catalog.domain_help("system", "server") or ""
        agent_help = catalog.domain_help("system", "client") or ""
        self.assertIn("system update check-engine", server_help)
        self.assertNotIn("system update check-engine", agent_help)

        server_update = grammar.context_help(["system", "update"], "server") or ""
        agent_update = grammar.context_help(["system", "update"], "client") or ""
        self.assertIn("check-engine", server_update)
        self.assertNotIn("check-engine", agent_update)

        server_topic = grammar.help_text(["update"], "server") or ""
        agent_topic = grammar.help_text(["update"], "client") or ""
        self.assertIn("system update check-engine", server_topic)
        self.assertNotIn("system update check-engine", agent_topic)

        server_redirect = grammar.context_help(["update"], "server") or ""
        agent_redirect = grammar.context_help(["update"], "client") or ""
        self.assertIn("system update check-engine", server_redirect)
        self.assertNotIn("system update check-engine", agent_redirect)

    def test_context_help_keeps_executable_parent_lifecycle_visible(self):
        cases = (
            (["unset", "remote-access", "?"], "unset remote-access <RULE>", "policy"),
            (["unset", "internet-access", "?"], "unset internet-access <RULE>", "policy"),
            (["unset", "ai-access", "?"], "unset ai-access <RULE>", "policy"),
            (["system", "diff", "?"], "system diff <REVISION_A> <REVISION_B>", "configuration"),
            (["system", "backup", "?"], "system backup [<path>]", "validate"),
        )
        for tokens, usage, child in cases:
            result = grammar.match(tokens, role="server")
            self.assertEqual(result.get("status"), "ok", (tokens, result))
            text = result.get("message") or ""
            self.assertIn(usage, text, (tokens, text))
            self.assertIn(child, text, (tokens, text))

        managed = grammar.match(
            ["unset", "managed-host", "?"], role="server", names=["host-a"]
        )
        self.assertEqual(managed.get("status"), "ok", managed)
        text = managed.get("message") or ""
        self.assertIn("unset managed-host", text)
        self.assertIn("Risk: irreversible", text)
        self.assertIn("Select a Managed Host", text)

        selected = grammar.match(
            ["unset", "managed-host", "host-a", "?"],
            role="server",
            names=["host-a"],
        )
        self.assertEqual(selected.get("status"), "ok", selected)
        selected_text = selected.get("message") or ""
        self.assertIn("unset managed-host", selected_text)
        self.assertIn("Risk: irreversible", selected_text)
        self.assertIn("Additional form", selected_text)
        self.assertIn("group", selected_text)

    def test_mcp_tls_purge_metadata_explains_interactive_only_contract(self):
        rows = json.loads((LIB / "frp_cli_final_commands.json").read_text(encoding="utf-8"))
        by_path = {tuple(row["path"]): row for row in rows}
        purge = by_path[("unset", "mcp-tls", "purge")]
        detail = str(purge.get("detail") or "").lower()
        self.assertTrue(purge["destructive"])
        self.assertEqual(purge["risk"], "irreversible")
        self.assertEqual(purge["confirmation"], "y_n")
        self.assertIn("interactive tty", detail)
        self.assertIn("non-interactive", detail)
        self.assertIn("fails closed", detail)

    def test_diagnostics_and_cli_reference_use_current_public_model(self):
        doctor = (LIB / "frp_doctor.py").read_text(encoding="utf-8")
        self.assertNotIn("published-service/presets are authoritative", doctor)
        self.assertIn(
            "Service Objects and Agent Remote Services are authoritative",
            doctor,
        )

        reference = (ROOT / "docs/CLI_REFERENCE.md").read_text(encoding="utf-8")
        server = reference.split("## 8. Server system commands", 1)[1].split(
            "## 9. Managed Host as Network Object", 1
        )[0]
        agent = reference.split("## 10. Agent Host commands", 1)[1]
        self.assertIn("system update check-engine", server)
        self.assertNotIn("system update check-engine", agent)
        self.assertIn("system synchronize", agent)

    def test_unset_enrollment_rejects_trailing_input(self):
        for tokens in (
            ["unset", "enrollment", "abc123", "extra"],
            ["unset", "enrollment", "abc123", "another", "value"],
        ):
            with self.subTest(tokens=tokens):
                result = grammar.match(tokens, "server")
                self.assertEqual(result.get("status"), "error", result)
                self.assertIn("unexpected argument", str(result.get("message") or "").lower())

    def test_certificate_internal_flags_do_not_leak_to_public_grammar(self):
        cases = [
            ["system", "certificate", "renew", "--force"],
            ["system", "certificate", "issue", "--directory", "https://example.test"],
            ["system", "certificate", "import", "--cert", "cert.pem", "--key", "key.pem"],
            ["system", "certificate", "status", "extra"],
        ]
        for tokens in cases:
            with self.subTest(tokens=tokens):
                result = grammar.match(tokens, "server")
                self.assertEqual(result.get("status"), "error", result)

    def test_audit_contract_covers_execution_races_and_exact_contract_identity(self):
        text = (ROOT / "docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "Single-run coordination — hard gate",
            "BLOCKED_CONCURRENT_AUDIT",
            "TEST_CONTRACT_FILE_SHA256=",
            "TEST_CONTRACT_DIRTY=YES|NO",
            "ledger/execution-lanes.tsv",
            "named logical audit lanes",
            "sudo -n drlink system version",
            "conditional_y_n",
            "Do **not** invent a universal TTY-only rule",
            "ChatGPT itself executes both sides of every AI-assisted lane",
            "<!-- CLI_FEATURE_SCENARIO_FINAL_START -->",
            "<!-- CLI_FEATURE_SCENARIO_FINAL_END -->",
        ):
            self.assertIn(required, text, required)

    def test_canonical_handler_failure_exit_code_is_preserved(self):
        root = Path(tempfile.mkdtemp(prefix="drlink-cli-no-install-"))
        (root / "etc/drlink").mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["FRP_CTL_TEST_ROOT"] = str(root)
        env["FRP_DEPLOY_TEST_ROOT"] = str(root)
        proc = subprocess.run(
            [str(ROOT / "tools/frpctl"), "show", "status"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ERROR:", proc.stderr)


    def test_agent_root_discovers_configuration_test(self):
        root_help = catalog.root_help("client")
        self.assertIn("\ntest\n", root_help)
        self.assertIn("Validate ConfigurationBundle without mutation", root_help)
        test_help = grammar.context_help(["test"], "client") or ""
        self.assertIn("configuration", test_help)

    def test_configuration_export_help_is_role_neutral(self):
        cmd = next(
            row
            for row in catalog.COMMANDS
            if tuple(row["path"]) == ("system", "export", "configuration")
        )
        text = catalog.command_help(cmd)
        self.assertNotIn("server-owned configuration", text)
        self.assertIn("this host role", text)

    def test_agent_diagnostics_hides_and_rejects_server_only_scopes(self):
        help_text = grammar.context_help(["system", "diagnostics"], "client") or ""
        self.assertIn("runtime", help_text)
        self.assertNotIn("mcp", help_text.lower())
        self.assertNotIn("control-plane", help_text.lower())

        runtime = grammar.match(["system", "diagnostics", "runtime"], "client")
        self.assertEqual(runtime.get("status"), "ok", runtime)
        for scope in ("mcp", "control-plane"):
            with self.subTest(scope=scope):
                result = grammar.match(["system", "diagnostics", scope], "client")
                self.assertEqual(result.get("status"), "role", result)
                self.assertIn("DRLink Server", str(result.get("message") or ""))

    def test_generated_recovery_guidance_uses_current_public_grammar(self):
        surfaces = {
            "doctor": (LIB / "frp_doctor.py").read_text(encoding="utf-8"),
            "agent": (ROOT / "tools/frp-client").read_text(encoding="utf-8"),
            "agent-common": (LIB / "frp-client-common.sh").read_text(encoding="utf-8"),
            "cli": (ROOT / "tools/frpctl").read_text(encoding="utf-8"),
            "installer": (ROOT / "install-client.sh").read_text(encoding="utf-8"),
            "catalog": (LIB / "frp_cli_final_commands.json").read_text(encoding="utf-8"),
            "retire": (ROOT / "tools/frp-revoke-client").read_text(encoding="utf-8"),
            "enrollment-purge": (ROOT / "tools/frp-enrollment-purge").read_text(encoding="utf-8"),
            "enrollment-revoke": (ROOT / "tools/frp-enrollment-revoke").read_text(encoding="utf-8"),
        }
        combined = "\n".join(surfaces.values())
        for retired in (
            "drlink egress tcp",
            "drlink show internet-profiles",
            "drlink enrollment create",
            "drlink enrollment revoke",
            "drlink enrollment list",
            "system services apply",
            "system services discard",
        ):
            self.assertNotIn(retired, combined, retired)
        self.assertNotIn("Published services", surfaces["installer"])
        self.assertNotIn("Published service reservations", surfaces["cli"])
        self.assertNotIn("Show local client connection information", surfaces["catalog"])
        self.assertIn("Data Relay Link Agent setup complete", surfaces["installer"])
        self.assertIn("Remote Services", surfaces["installer"])
        self.assertIn("system synchronize", surfaces["agent"])
        self.assertIn("sudo drlink show internet-access", surfaces["doctor"])
        self.assertIn("sudo drlink set enrollment manual", surfaces["agent"])
        self.assertIn("sudo drlink set enrollment manual", surfaces["retire"])
        self.assertIn("drlink unset enrollment", surfaces["enrollment-purge"])
        self.assertIn("drlink show enrollments", surfaces["enrollment-revoke"])

    def test_repl_history_uses_canonical_command_and_rejects_retired_roots(self):
        import frp_ctl_repl as repl

        calls = []

        def backend(argv, **kwargs):
            tokens = argv[1:]
            calls.append(tokens)
            result = grammar.match(tokens, "server")
            if tokens == ["system", "history"]:
                print("(no session history)")
            return subprocess.CompletedProcess(argv, result.get("exit_code", 0))

        out = io.StringIO()
        with patch("builtins.input", side_effect=[
            "show status", "set enrollment --auth-token TEST_SECRET_HISTORY",
            "system history", "history", "q", "quit",
            "exit extra", "system history", "exit",
        ]), patch.object(repl, "_run_backend", side_effect=backend), \
                patch.object(repl.LineEditor, "bind"), redirect_stdout(out):
            self.assertEqual(repl.run_repl("drlink", {"role": "server"}), 0)
        self.assertIn("  show status", out.getvalue())
        self.assertNotIn("(no session history)", out.getvalue())
        self.assertNotIn("TEST_SECRET_HISTORY", out.getvalue())
        self.assertNotIn(["system", "history"], calls)
        for tokens in (["history"], ["q"], ["quit"], ["exit", "extra"]):
            self.assertIn(tokens, calls)

    def test_unreadable_install_state_is_not_reported_as_wrong_role(self):
        env = os.environ.copy()
        preexec = None
        if os.geteuid() == 0:
            import pwd
            account = pwd.getpwnam("nobody")

            def drop_test_privilege():
                os.setgroups([])
                os.setgid(account.pw_gid)
                os.setuid(account.pw_uid)

            preexec = drop_test_privilege
        # Keep the public launcher traversable even when root CI runs from a
        # private home directory and the subprocess drops to nobody.
        with tempfile.TemporaryDirectory(prefix="drlink-unreadable-role-", dir="/tmp") as tmp:
            root = Path(tmp)
            root.chmod(0o755)
            (root / "tools").mkdir()
            for name in ("drlink", "frpctl"):
                shutil.copy2(ROOT / "tools" / name, root / "tools" / name)
            shutil.copytree(LIB, root / "lib")
            state = root / "etc/drlink"
            state.mkdir(parents=True)
            (state / "config.json").write_text('{"role":"server"}\n')
            state.chmod(0)
            env.update(FRP_CTL_TEST_ROOT=tmp, FRP_DEPLOY_TEST_ROOT=tmp, FRP_CTL_DRY_RUN="1")
            try:
                proc = subprocess.run(
                    ["bash", str(root / "tools/drlink"), "show", "managed-hosts"],
                    env=env, text=True, capture_output=True, preexec_fn=preexec,
                )
            finally:
                state.chmod(0o755)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot read the install state", proc.stderr)
        self.assertIn("sudo drlink", proc.stderr)
        self.assertNotIn("Run this command on the DRLink Server", proc.stderr)

    def test_terminal_enrollment_menu_dispatches_canonical_unset(self):
        script = '''source "$1"
frpctl_nav_prompt_id() { printf '%s' terminal-id; }
frpctl_dispatch() { printf '%s\\n' "$@"; }
frpctl_nav_workflow delete_enrollment
'''
        env = os.environ.copy()
        env["FRP_CTL_SOURCED"] = "1"
        proc = subprocess.run(
            ["bash", "-c", script, "audit-regression", str(ROOT / "tools/frpctl")],
            env=env, text=True, capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), ["unset", "enrollment", "terminal-id"])
        self.assertEqual(grammar.match(proc.stdout.splitlines(), "server")["status"], "ok")

    def test_installer_help_and_cutover_guidance_use_agent_model(self):
        proc = subprocess.run(
            ["bash", str(ROOT / "install-client.sh"), "--help"],
            text=True, capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Agent enrollment", proc.stdout)
        for phrase in ("First-time client", "existing client", "installed client"):
            self.assertNotIn(phrase, proc.stdout)
        deployment = (ROOT / "docs/DEPLOYMENT_MODES.md").read_text()
        current = deployment.split("Recommended sequence:", 1)[1].split("## Firewall notes", 1)[0]
        self.assertIn("sudo drlink system synchronize", current)
        self.assertIn("sudo drlink system uninstall", current)
        self.assertIn("sudo drlink set enrollment zero-touch", current)
        self.assertNotIn("On each client, Apply", current)
        self.assertIn("does not\nchange the configured connection transport", deployment)

    def test_readme_capability_table_keeps_restricted_planes_whitelist_only(self):
        for name in ("README.md", "README.ko.md"):
            text = (ROOT / name).read_text()
            row = next(line for line in text.splitlines() if "**Access Policy**" in line)
            for semantic in ("Remote", "Internet", "AI", "BLACKLIST", "WHITELIST-only", "deny-by-default"):
                self.assertIn(semantic, row, name)
            internet = text.split("### Internet Access", 1)[1].split("### AI Access", 1)[0]
            self.assertIn("WHITELIST-only deny-by-default policy enforcement", internet, name)
            self.assertNotIn("BLACKLIST", internet, name)

    def test_missing_grammar_recovery_names_current_update_command(self):
        script = '''source "$1"
frpctl_lib_candidate() { return 1; }
frpctl_grammar_py
'''
        env = os.environ.copy()
        env.update(FRP_CTL_SOURCED="1", FRP_CTL_CMD_NAME="drlink")
        proc = subprocess.run(
            ["bash", "-c", script, "audit-regression", str(ROOT / "tools/frpctl")],
            env=env, text=True, capture_output=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("drlink system update product", proc.stderr)
        self.assertNotIn("drlink update product", proc.stderr)


if __name__ == "__main__":
    unittest.main()
