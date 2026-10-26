#!/usr/bin/env python3
"""Nginx Native MCP public relay overlay contract (no root or network needed)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/operator-native-mcp-relay.py"
SPEC = importlib.util.spec_from_file_location("native_mcp_relay", PATH)
assert SPEC and SPEC.loader
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)


class NativeRelayTests(unittest.TestCase):
    def setUp(self):
        self.example = b"""http {
    server {
        listen 443 ssl;
        server_name 15.164.238.140;
        ssl_certificate /etc/drlink/private-ca.pem;
        location / { return 404; }
    }
    # MCP public TLS (SNI)
    server {
        listen 443 ssl;
        server_name mcp.xdr.ooo;

        ssl_certificate /var/lib/drlink/tls/mcp/active/fullchain.pem;
        ssl_certificate_key /var/lib/drlink/tls/mcp/active/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_prefer_server_ciphers off;

        location = /mcp {
            proxy_pass http://127.0.0.1:6103;
        }
        location / { return 404; }
    }
}
"""

    def test_routed_paths_are_scoped_and_do_not_change_existing_mcp(self):
        candidate = relay.candidate(self.example).decode()
        self.assertEqual(candidate.count(relay.MARKER), 1)
        self.assertIn("proxy_pass http://127.0.0.1:6103", candidate)
        self.assertIn("ssl_certificate /var/lib/drlink/tls/mcp/active/fullchain.pem", candidate)
        self.assertEqual(candidate.count("server_name mcp.xdr.ooo"), 1)
        snippet = relay.fragment().decode()
        self.assertIn("location = /access/mcp", snippet)
        self.assertIn("proxy_pass http://127.0.0.1:16107/mcp;", snippet)
        self.assertIn("location = /.well-known/oauth-protected-resource/access/mcp", snippet)
        self.assertIn("location = /access/.well-known/oauth-protected-resource", snippet)
        self.assertIn("location = /.well-known/oauth-authorization-server/access", snippet)
        self.assertIn("location = /access/oauth/token", snippet)
        self.assertIn("location = /access/oauth/authorize", snippet)
        self.assertIn("location = /access/oauth/register", snippet)
        self.assertNotIn("location = /mcp {", snippet)
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", snippet)
        self.assertNotIn("proxy_ssl_verify off", snippet)

    def test_refuses_double_install_and_unexpected_public_config(self):
        once = relay.candidate(self.example)
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            relay.candidate(once)
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            relay.candidate(self.example.replace(b"mcp.xdr.ooo;", b"other.xdr.ooo;"))
        with self.assertRaisesRegex(RuntimeError, "differs"):
            relay.candidate(self.example.replace(
                b"active/fullchain.pem", b"wrong.pem"
            ))

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "new.conf"
            relay._atomic(path, b"new contents\n", 0o600)
            self.assertEqual(path.read_bytes(), b"new contents\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
