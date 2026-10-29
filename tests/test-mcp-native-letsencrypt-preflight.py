#!/usr/bin/env python3
"""Native LE readiness: DNS is not certificate or public MCP verification."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "native_mcp_le_preflight", ROOT / "tools/native-mcp-letsencrypt-preflight.py")
assert SPEC and SPEC.loader
pre = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pre)


class NativeLetsEncryptPreflightTests(unittest.TestCase):
    def scenario(self, *, cert: str, public: bool, resource: str):
        with (
            patch.object(pre, "resolved_ipv4", return_value={"203.0.113.10"}),
            patch.object(pre, "local_global_ipv4", return_value={"203.0.113.10"}),
            patch.object(pre, "listening_ports", return_value={443, 16106}),
            patch.object(pre.drlink_mcp_tls, "acme_runtime_status",
                         return_value={"ok": True, "implementation": "python3-acme"}),
            patch.object(pre, "public_certificate_status", return_value=cert),
            patch.object(pre, "local_mcp_status", return_value=(True, resource)),
            patch.object(pre, "public_mcp_status", return_value=public) as real,
        ):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                status = pre.preflight()
            return status, buffer.getvalue(), real

    def test_dns_and_local_mcp_cannot_claim_chatgpt_public_ready(self):
        status, output, real = self.scenario(
            cert="UNTRUSTED_CERT", public=True,
            resource="https://mcp.xdr.ooo/access/mcp",
        )
        self.assertEqual(status, 0)
        self.assertIn("DNS_TO_DEVELOPMENT_SERVER=PASS", output)
        self.assertIn("PUBLIC_LETS_ENCRYPT_CERTIFICATE=UNTRUSTED_CERT", output)
        self.assertIn("PUBLIC_NATIVE_MCP_READY=NO", output)
        self.assertIn("PUBLIC_443_PORT=OCCUPIED_BY_EXISTING_SERVICE", output)
        real.assert_not_called()

    def test_public_certificate_alone_never_substitutes_mcp_401_and_oauth(self):
        status, output, probe = self.scenario(
            cert="PASS", public=False, resource="https://mcp.link.xdr.ooo/mcp")
        self.assertEqual(status, 0)
        probe.assert_called_once()
        self.assertIn("PUBLIC_NATIVE_MCP_TLS_OAUTH_HTTP401=NOT_READY", output)
        self.assertIn("PUBLIC_NATIVE_MCP_READY=NO", output)

    def test_full_public_requires_real_tls_mcp_oauth_and_correct_resource(self):
        status, output, probe = self.scenario(
            cert="PASS", public=True, resource="https://mcp.link.xdr.ooo/mcp")
        self.assertEqual(status, 0)
        probe.assert_called_once()
        self.assertIn("PUBLIC_NATIVE_MCP_READY=PASS", output)
        self.assertIn("CONFIG_CHANGE_PERFORMED=NO", output)

    def test_real_public_verifier_requires_ca_trust_and_correct_mcp(self):
        scenarios = (
            (False, "PASS", True, "NO"),
            (True, "UNTRUSTED_CERT", True, "NO"),
            (True, "PASS", False, "NO"),
            (True, "PASS", True, "PASS"),
        )
        for dns, cert, tool, result in scenarios:
            addresses = {"203.0.113.10"} if dns else {"198.51.100.20"}
            with (
                patch.object(pre, "resolved_ipv4", return_value=addresses),
                patch.object(pre, "local_global_ipv4", return_value={"203.0.113.10"}),
                patch.object(pre, "public_certificate_status", return_value=cert),
                patch.object(pre, "public_mcp_status", return_value=tool) as actual,
            ):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    code = pre.verify_public()
                output = buffer.getvalue()
                self.assertEqual(code, 0 if result == "PASS" else 1, output)
                self.assertIn("CHATGPT_NATIVE_MCP_PUBLIC_READY=" + result, output)
                self.assertIn("CHATGPT_OWNER_OAUTH_AND_TOOL_E2E=NOT_YET_VALIDATED", output)
                if not dns or cert != "PASS":
                    actual.assert_not_called()
                else:
                    actual.assert_called_once()

    def test_single443_operator_is_backup_first_and_never_disables_tls(self):
        script = (ROOT / "tools/operator-native-mcp-single443.sh").read_text()
        self.assertIn("FRP_DEPLOYMENT_MODE=single443", script)
        self.assertIn("FRP_CONFIRM_MODE_SWITCH=yes", script)
        self.assertIn("read -r -p \"Type SWITCH", script)
        self.assertIn("tools/frp-backup", script)
        self.assertIn("tools/frp-restore", script)
        self.assertLess(script.index("tools/frp-restore"), script.index("systemctl stop nginx.service"))
        self.assertLess(script.index("systemctl disable nginx.service"), script.index("bash ./install-server.sh"))
        self.assertIn('FRP_EXPECTED_SOURCE_REF="$(git_scoped rev-parse HEAD)"', script)
        self.assertIn("if ! (cd \"$ROOT\" && bash ./install-server.sh </dev/null); then", script)
        self.assertIn("PREEXISTING_NGINX_RESTORED_AFTER_FAILED_SWITCH=PASS", script)
        self.assertLess(script.index("if ! (cd \"$ROOT\" && bash ./install-server.sh"),
                        script.index("  issue_certificate\n}\n\ncase "))
        self.assertIn('[[ "$(mode_now)" == "direct" ]]', script)
        self.assertIn("nginx_was_enabled", script)
        self.assertIn("nginx_was_active", script)
        self.assertIn("set mcp-tls hostname", script)
        self.assertIn("set mcp-tls mode auto-acme", script)
        self.assertIn("system certificate issue", script)
        self.assertIn("DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0", script)
        self.assertNotIn("cloudflared", script)
        self.assertNotIn("curl -k", script)
        self.assertNotIn("certbot --standalone", script)

    def test_local_global_ip_from_kernel_interfaces(self):
        fake = subprocess.CompletedProcess(
            [], 0, stdout=(
                "2: eth0 inet 203.0.113.10/24 brd 203.0.113.255 scope global eth0\n"
                "3: eth1 inet 198.51.100.30/25 brd 198.51.100.127 scope global eth1\n"
            )
        )
        with patch.object(pre.subprocess, "run", return_value=fake) as called:
            self.assertEqual(pre.local_global_ipv4(),
                             {"203.0.113.10", "198.51.100.30"})
            called.assert_called_once()
            self.assertEqual(called.call_args.args[0],
                             ["ip", "-o", "-4", "addr", "show", "scope", "global"])

    def test_ss_port_parser_no_mutations(self):
        fake = subprocess.CompletedProcess(
            [], 0, stdout=(
                "LISTEN 0 4096 *:443 *:*\n"
                "LISTEN 0 256 127.0.0.1:16106 0.0.0.0:*\n"
                "LISTEN 0 5 127.0.0.1:80 *:*\n"
            ))
        with patch.object(pre.subprocess, "run", return_value=fake) as called:
            self.assertEqual(pre.listening_ports(), {80, 443, 16106})
            called.assert_called_once()
            self.assertEqual(called.call_args.args[0], ["ss", "-H", "-lnt"])


if __name__ == "__main__":
    unittest.main()
