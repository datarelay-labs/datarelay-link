#!/usr/bin/env python3
"""Supporting unit checks for the read-only E2E lab preflight (not user E2E)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import e2e_lab_readiness as lab  # noqa: E402

HASH_A = "a" * 40
HASH_B = "b" * 40


def host(alias="frp-e2e-server", role="server", **extra):
    return {"ssh_alias": alias, "role": role, "required": True, **extra}


def unix_response(installed="NO", source=None, paths=(), active=False):
    lines = ["HOST=test-vm", 'ID="ubuntu"', 'VERSION_ID="24.04"',
             f"DRLINK_INSTALLED={installed}"]
    if source:
        lines.append("Source HEAD: " + source)
    lines.extend("STATE_PATH_PRESENT=" + p for p in paths)
    lines.append("UNIT_drlink-client.service=" + ("active" if active else "inactive"))
    return subprocess.CompletedProcess([], 0, "\n".join(lines), "")


class LabReadinessSupportingTests(unittest.TestCase):
    def test_valid_assigned_host_set_and_invalid_alias_fails_closed(self):
        self.assertFalse(lab.verify_manifest({"hosts": [host()]}))
        for alias in ("frp-e2e-linux114", "frp-e2e-macos",
                      "frp-e2e-server; touch /tmp/unsafe", "unknown-host"):
            self.assertTrue(lab.verify_manifest({"hosts": [host(alias)]}))

    def test_preinstall_requires_absent_product_and_state(self):
        ready = lab.classify_host(host(), unix_response(), HASH_A)
        self.assertEqual(ready["status"], "PASS")
        for result in (unix_response(paths=["/var/lib/drlink"]),
                       unix_response(active=True),
                       unix_response("YES", HASH_A)):
            bad = lab.classify_host(host(), result, HASH_A)
            self.assertEqual(bad["status"], "NOT_READY", bad)

    def test_exact_installed_head_only_passes_postinstall_phase(self):
        ready = lab.classify_host(host(), unix_response("YES", HASH_A), HASH_A,
                                  "INSTALLED_CANDIDATE")
        self.assertEqual(ready["status"], "PASS")
        mismatch = lab.classify_host(host(), unix_response("YES", HASH_B), HASH_A,
                                     "INSTALLED_CANDIDATE")
        self.assertEqual(mismatch["reason"], "STALE_INSTALLED_SOURCE_HEAD")
        self.assertEqual(mismatch["status"], "NOT_READY")
        missing = lab.classify_host(host(), unix_response(), HASH_A, "INSTALLED_CANDIDATE")
        self.assertEqual(missing["status"], "NOT_READY")

    def test_os_identity_conflict_cannot_pass(self):
        row = lab.classify_host(host(expected_os_id="rocky"), unix_response(), HASH_A)
        self.assertEqual(row["status"], "NOT_READY")
        self.assertEqual(row["reason"], "Unexpected assigned native OS identity")

    def test_windows_route_failure_is_tooling_not_product_bug(self):
        result = subprocess.CompletedProcess([], 255, "",
                                              "ssh: connect to host 127.0.0.1 port 2223: Connection refused")
        row = lab.classify_host(host("frp-e2e-windows", "native-agent"), result, HASH_A)
        self.assertEqual(row["ssh_error_class"], "CONNECTION_REFUSED")
        self.assertEqual(row["status"], "NOT_READY")

    def test_windows_preinstall_native_cleanroom_can_be_proven_read_only(self):
        result = subprocess.CompletedProcess(
            [], 0,
            "HOST=WIN-E2E\nID=windows\nVERSION_ID=10.0.19045\n"
            "DRLINK_INSTALLED=NO\nUNIT_windows-frpc-process=inactive\n", "",
        )
        row = lab.classify_host(
            host("frp-e2e-windows", "native-agent"), result, HASH_A
        )
        self.assertEqual(row["status"], "PASS")
        self.assertEqual(row["installed"], "NO")
        self.assertEqual(row["os_id"], "windows")
        self.assertEqual(row["host"], "WIN-E2E")

    def test_windows_installed_content_requires_exact_source_head(self):
        body = ("HOST=WIN-E2E\nID=windows\nVERSION_ID=10.0.19045\n"
                "DRLINK_INSTALLED=YES\nSource HEAD: " + HASH_A + "\n"
                "UNIT_windows-frpc-process=active\n")
        row = lab.classify_host(
            host("frp-e2e-windows", "native-agent"),
            subprocess.CompletedProcess([], 0, body, ""),
            HASH_A, "INSTALLED_CANDIDATE",
        )
        self.assertEqual(row["status"], "PASS")
        row = lab.classify_host(
            host("frp-e2e-windows", "native-agent"),
            subprocess.CompletedProcess([], 0, body, ""),
            HASH_B, "INSTALLED_CANDIDATE",
        )
        self.assertEqual(row["status"], "NOT_READY")
        self.assertEqual(row["reason"], "STALE_INSTALLED_SOURCE_HEAD")

    def test_windows_stale_state_active_process_and_version_failure_block(self):
        clean = ("HOST=WIN-E2E\nID=windows\nVERSION_ID=10.0.19045\n"
                 "DRLINK_INSTALLED=NO\nUNIT_windows-frpc-process=inactive\n")
        for changed in (
            clean + "STATE_PATH_PRESENT=C:\\ProgramData\\drlink\n",
            clean.replace("=inactive", "=active"),
            clean.replace("ID=windows", "ID=linux"),
            clean.replace("DRLINK_INSTALLED=NO", "DRLINK_INSTALLED=YES"),
            clean + "DRLINK_VERSION_FAILED_RC=1\n",
            clean + "READ_ONLY_PROBE_ERROR=WINDOWS_SCHEDULED_TASK_QUERY_FAILED\n",
            clean + "UNIT_windows-product-service=registered\n",
            clean + "STATE_PATH_PRESENT=windows-product-scheduled-task\n",
        ):
            with self.subTest(changed=changed[-78:]):
                row = lab.classify_host(
                    host("frp-e2e-windows", "native-agent"),
                    subprocess.CompletedProcess([], 0, changed, ""),
                    HASH_A,
                )
                self.assertEqual(row["status"], "NOT_READY", row)

    def test_windows_assigned_read_only_probe_uses_documented_install_path(self):
        from unittest import mock
        output = ("HOST=WIN-E2E\nID=windows\nVERSION_ID=10.0.19045\n"
                  "DRLINK_INSTALLED=NO\nUNIT_windows-frpc-process=inactive\n")
        with mock.patch.object(
            lab.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 0, output, ""),
        ) as runner:
            row = lab.collect_host(host("frp-e2e-windows", "native-agent"),
                                   HASH_A)
        self.assertEqual(row["status"], "PASS")
        args, kwargs = runner.call_args
        self.assertEqual(args[0][0], "ssh")
        self.assertIn("BatchMode=yes", args[0])
        self.assertIn("StrictHostKeyChecking=yes", args[0])
        self.assertIn("frp-e2e-windows", args[0])
        command = args[0][-1]
        self.assertIn("powershell.exe -NoProfile -NonInteractive", command)
        self.assertIn("tools\\drlink.cmd", command)
        self.assertIn("& $cli system version", command)
        self.assertIn("Get-Process -Name frpc", command)
        self.assertIn("Get-Service -Name", command)
        self.assertIn("Get-ScheduledTask -ErrorAction Stop", command)
        for forbidden in ("install-client", "system uninstall",
                          "system update", "Set-Item", "Remove-Item",
                          "New-NetFirewallRule"):
            self.assertNotIn(forbidden, command)

    def test_run_evidence_uses_immutable_run_scoped_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "durable"
            report = {"run_id": "fixed-run-001", "status": "NOT_READY"}
            destination = lab.write_run_evidence(root, report, [
                {"ssh_alias": "frp-e2e-server", "role": "server", "ssh_rc": 0,
                 "installed": "YES", "status": "NOT_READY",
                 "reason": "STALE_INSTALLED_SOURCE_HEAD"},
            ])
            self.assertEqual(destination.name, "fixed-run-001")
            self.assertTrue((destination / "PREFLIGHT_STATUS.json").is_file())
            self.assertTrue((destination / "CLEANROOM_LEDGER.tsv").is_file())
            with self.assertRaises(FileExistsError):
                lab.write_run_evidence(root, report, [])
            self.assertEqual(json.loads(
                (destination / "PREFLIGHT_STATUS.json").read_text()
            )["status"], "NOT_READY")

    def test_two_server_manifest_rejects_unapproved_mcp_alias_and_hostname(self):
        manifest = {"hosts": [host()], "mcp_server": {
            "ssh_alias": "frp-release-server", "role": "mcp-server",
            "public_hostname": "mcp.example.test", "required": True}}
        self.assertEqual(lab.verify_manifest(manifest), [])
        split = {"roles_distinct": True, "MCP_DNS_SERVER": "mcp.example.test",
                 "FUNCTION_PERFORMANCE_SERVER": "198.51.100.2"}
        missing = {"hosts": [host()], "two_server_assignment": split}
        self.assertTrue(lab.verify_manifest(missing), "Cannot omit MCP Server from a split lab")
        manifest["two_server_assignment"] = split
        self.assertEqual(lab.verify_manifest(manifest), [])
        wrong_fqdn = json.loads(json.dumps(manifest))
        wrong_fqdn["two_server_assignment"]["MCP_DNS_SERVER"] = "another.example.test"
        self.assertTrue(lab.verify_manifest(wrong_fqdn))
        for alias in ("frp-e2e-server", "frp-e2e-linux114", "unknown",
                      "frp-release-server; rm -rf /"):
            bad = json.loads(json.dumps(manifest))
            bad["mcp_server"]["ssh_alias"] = alias
            self.assertTrue(lab.verify_manifest(bad), alias)
        for hostname in ("", "localhost", "*.example.test",
                         "mcp.example.test; command", "127.0.0.1"):
            bad = json.loads(json.dumps(manifest))
            bad["mcp_server"]["public_hostname"] = hostname
            self.assertTrue(lab.verify_manifest(bad), hostname)

    def test_mcp_read_only_host_needs_exact_content_single443_and_valid_cert(self):
        reply = ("MCP_HOST=test-mcp\nID=ubuntu\nVERSION_ID=24.04\nMCP_INSTALLED=YES\n"
                 "Source HEAD: " + HASH_A + "\n"
                 "MCP_CERT_STATUS_BEGIN\nURL:\n  https://mcp.example.test/mcp\n"
                 "TLS mode:\n  AUTO_ACME\n"
                 "Certificate:\n  VALID\n"
                 "MCP_DOCTOR_BEGIN\nDeployment mode : single443\n"
                 "mcp_tls_certificate     PASS — active certificate valid\n")
        entry = {"ssh_alias": "frp-release-server", "role": "mcp-server",
                 "public_hostname": "mcp.example.test", "expected_os_id": "ubuntu", "required": True}
        observed = lab.classify_mcp_server(
            entry, subprocess.CompletedProcess([], 0, reply, ""), HASH_A,
            "INSTALLED_CANDIDATE")
        self.assertEqual(observed["status"], "PASS", observed)
        self.assertEqual(observed["certificate"], "VALID")
        for changed in (reply.replace("ID=ubuntu", "ID=rocky"),
                        reply.replace(HASH_A, HASH_B),
                        reply.replace("AUTO_ACME", "PRIVATE_CA"),
                        reply.replace("single443", "direct"),
                        reply.replace("  VALID", "  ABSENT"),
                        reply.replace("mcp.example.test/mcp", "wrong.example.test/mcp"),
                        reply.replace("mcp_tls_certificate     PASS", "mcp_tls_certificate     FAIL"),
                        reply + "MCP_CERT_PROBE_FAILED=YES"):
            row = lab.classify_mcp_server(
                entry, subprocess.CompletedProcess([], 0, changed, ""), HASH_A,
                "INSTALLED_CANDIDATE")
            self.assertEqual(row["status"], "NOT_READY", row)

    def test_mcp_read_only_route_and_separate_go_gate(self):
        from unittest import mock
        entry = {"ssh_alias": "frp-release-server", "role": "mcp-server",
                 "public_hostname": "mcp.example.test", "required": True}
        reply = ("MCP_HOST=test\nMCP_INSTALLED=YES\nSource HEAD: " +
                 HASH_A + "\nMCP_CERT_STATUS_BEGIN\nURL:\n"
                 " https://mcp.example.test/mcp\nTLS mode:\n AUTO_ACME\n"
                 "Certificate:\n VALID\nMCP_DOCTOR_BEGIN\n"
                 "Deployment mode : single443\n"
                 "mcp_tls_certificate PASS — active certificate valid\n")
        with mock.patch.object(
            lab.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 0, reply, "")) as run:
            result = lab.collect_mcp_server(entry, HASH_A, "INSTALLED_CANDIDATE")
        self.assertEqual(result["status"], "PASS", result)
        argv = run.call_args.args[0]
        self.assertIn("frp-release-server", argv)
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("system certificate status", argv[-1])
        self.assertNotIn("system certificate preflight", argv[-1])
        self.assertNotIn("system certificate issue", argv[-1])
        self.assertNotIn("system uninstall", argv[-1])
        base = {"expected_provenance_head": HASH_A,
                "approvals": {"dedicated_disposable_lab": True,
                              "server_cleanup_B014_resolved": True,
                              "protected_backup_verified": True,
                              "qualified_immutable_bundle": True,
                              "trusted_mcp_tls_verified": False,
                              "actual_owner_oauth_ui_accepted": True,
                              "separate_ai_personas_ready": True,
                              "prospective_process_registry_ready": True,
                              "native_platform_security_denials_resolved": True}}
        function = {"ssh_alias": "frp-e2e-server", "required": True,
                    "status": "PASS", "reason": "match"}
        outcome = lab.evaluate(base, [function, result], HASH_A)
        self.assertEqual(outcome["status"], "NOT_READY")
        self.assertIn("MCP_PUBLIC_TLS", outcome["not_ready_gate_ids"])
        self.assertNotIn("HOST_FRP_RELEASE_SERVER", outcome["not_ready_gate_ids"])
        broken = dict(result, status="NOT_READY", reason="certificate ABSENT")
        outcome = lab.evaluate(base, [function, broken], HASH_A)
        self.assertIn("HOST_FRP_RELEASE_SERVER", outcome["not_ready_gate_ids"])

    def test_approval_gates_are_explicit_and_never_inferred(self):
        names = ["dedicated_disposable_lab", "server_cleanup_B014_resolved",
                 "protected_backup_verified", "qualified_immutable_bundle",
                 "trusted_mcp_tls_verified", "actual_owner_oauth_ui_accepted",
                 "separate_ai_personas_ready", "prospective_process_registry_ready",
                 "native_platform_security_denials_resolved"]
        base = {"expected_provenance_head": HASH_A,
                "approvals": {key: True for key in names}}
        ready = {"ssh_alias": "frp-e2e-server", "required": True, "status": "PASS",
                 "reason": "clean"}
        self.assertEqual(lab.evaluate(base, [ready], HASH_A)["status"], "GO")
        base["approvals"]["server_cleanup_B014_resolved"] = False
        outcome = lab.evaluate(base, [ready], HASH_A)
        self.assertEqual(outcome["status"], "NOT_READY")
        self.assertIn("SERVER_CLEANUP_B014", outcome["not_ready_gate_ids"])
        self.assertEqual(lab.evaluate(base, [ready], HASH_B)["status"], "NOT_READY")


if __name__ == "__main__":
    unittest.main()
