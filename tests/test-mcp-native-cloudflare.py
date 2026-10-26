#!/usr/bin/env python3
"""Native MCP custom-host Cloudflare connector is local and credential-safe."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "native_mcp_cloudflare", ROOT / "tools/operator-native-mcp-cloudflare.py")
assert SPEC and SPEC.loader
cf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cf)


class NativeCloudflareTests(unittest.TestCase):
    def test_custom_hostname_and_no_other_machine(self):
        self.assertEqual(cf.DOMAIN, "mcp.link.xdr.ooo")
        self.assertEqual(cf.RESOURCE, "https://mcp.link.xdr.ooo/mcp")
        self.assertEqual(cf.ISSUER, "https://mcp.link.xdr.ooo")
        self.assertEqual(cf.LOCAL, "http://127.0.0.1:16106")
        self.assertNotIn("15.164.238.140", cf.unit())
        self.assertNotIn("mcp.xdr.ooo/access", cf.unit())
        self.assertNotIn("mcp.link.datarelay.run", cf.unit())

    def test_tunnel_credential_is_read_from_private_file(self):
        service = cf.unit()
        self.assertIn("--token-file /home/aella/.config/drlink-native-mcp-cloudflare/tunnel-token", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("--protocol http2", service)
        self.assertNotIn(" --token eyJ", service)
        self.assertNotIn("frps", service)
        self.assertNotIn("ExecStart=/usr/bin/sudo", service)
        self.assertNotIn("User=root", service)

    def test_staging_refuses_overwrite_of_unrelated_systemd_unit(self):
        with tempfile.TemporaryDirectory(prefix="cf-native-test-") as root:
            base = Path(root)
            staged = base / "native.service"
            staged.write_text("[Service]\nExecStart=/bin/false\n")
            with (
                patch.object(cf, "UNIT", staged),
                patch.object(cf, "DIR", base / "restricted"),
                patch.object(cf, "TOKEN", base / "restricted/token"),
                patch.object(cf, "owner"),
                patch.object(cf, "CLOUDFLARED", Path("/bin/true")),
            ):
                with self.assertRaisesRegex(RuntimeError, "unrelated"):
                    cf.secure_staging()

    def test_invalid_local_mcp_cannot_pass_check(self):
        with patch.object(cf, "_http", return_value=(200, {}, b"{}")):
            with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                cf.local_check()

    def test_token_storage_never_contains_command_flags(self):
        with tempfile.TemporaryDirectory(prefix="cf-token-") as root:
            f = Path(root) / "code"
            cf._atomic(f, b"fake-private-token\n")
            self.assertEqual(f.read_bytes(), b"fake-private-token\n")
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)

    def test_privileged_user_is_denied(self):
        with patch.object(cf.os, "getuid", return_value=0), \
             patch.object(cf.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "without sudo"):
                cf.owner()


if __name__ == "__main__":
    unittest.main()
