#!/usr/bin/env python3
"""F008: MCP TLS FQDN must be the OAuth issuer without a Server public-hostname.

Loopback HTTP simulates the private bridge behind single443 nginx; no owner
OAuth credentials, network DNS or certificate material are touched.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_plane import ControlPlane
from drlink_mcp_bridge import MCPBridge, ThreadingHTTPServer, make_handler
import drlink_mcp_tls


class McpIssuerOriginTests(unittest.TestCase):
    def test_tls_fqdn_wins_over_default_ip_for_all_discovery_routes(self):
        with tempfile.TemporaryDirectory(prefix="drlink-f008-") as td:
            cfg = Path(td) / "etc/drlink/config.json"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(json.dumps({
                "role": "server",
                "deployment_mode": "single443",
                "public_host": "203.0.113.10",
                "frp_control_public_port": 443,
                # No Server public_hostname or public_url_host is required.
            }) + "\n")
            plane = ControlPlane(td)
            drlink_mcp_tls.configure_intent(
                plane, hostname="mcp.example.test", mode="user-certificate"
            )
            bridge = MCPBridge(root=td, plane=plane)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bridge))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:%s" % server.server_address[1]
                def fetch(path):
                    request = Request(base + path, headers={"Host": "untrusted.invalid"})
                    with urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        return json.load(response)
                auth = fetch("/.well-known/oauth-authorization-server")
                protected = fetch("/.well-known/oauth-protected-resource/mcp")
                want = "https://mcp.example.test"
                self.assertEqual(auth["issuer"], want)
                for field, suffix in (
                    ("registration_endpoint", "/oauth/register"),
                    ("token_endpoint", "/oauth/token"),
                    ("authorization_endpoint", "/oauth/authorize"),
                    ("revocation_endpoint", "/oauth/revoke"),
                ):
                    self.assertEqual(auth[field], want + suffix)
                self.assertEqual(protected["resource"], want + "/mcp")
                self.assertEqual(protected["authorization_servers"], [want])
                self.assertNotIn("203.0.113.10", json.dumps(auth) + json.dumps(protected))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                bridge.close()
                plane.close()


if __name__ == "__main__":
    unittest.main()
