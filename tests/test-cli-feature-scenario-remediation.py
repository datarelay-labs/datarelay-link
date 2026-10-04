#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
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
        ):
            self.assertNotIn(retired, combined, retired)
        self.assertIn("sudo drlink show internet-access", surfaces["doctor"])
        self.assertIn("sudo drlink set enrollment manual", surfaces["agent"])
        self.assertIn("sudo drlink set enrollment manual", surfaces["retire"])
        self.assertIn("drlink unset enrollment", surfaces["enrollment-purge"])
        self.assertIn("drlink show enrollments", surfaces["enrollment-revoke"])

if __name__ == "__main__":
    unittest.main()
