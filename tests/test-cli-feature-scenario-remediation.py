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
            self.assertEqual(reset["risk"], "security_widening")
            self.assertEqual(reset["confirmation"], "y_n")

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


if __name__ == "__main__":
    unittest.main()
