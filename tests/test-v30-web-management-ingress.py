#!/usr/bin/env python3
"""PF-9 actual loopback Web ingress guard, using one pinned Foundation ACL engine."""
from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_foundation_security import (
    FoundationAllowEntry, FoundationManagementPolicy, FoundationSurfacePolicy,
)
from drlink_web_service import create_server


def enabled(*sources: str) -> FoundationManagementPolicy:
    return FoundationManagementPolicy(
        web=FoundationSurfacePolicy(
            enabled=True,
            sources=tuple(FoundationAllowEntry(cidr) for cidr in sources),
            revision="test-web-1",
        ),
    )


_UNSET = object()


class LinkWebIngressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-pf9-web-ingress-")
        self.server = None
        self.thread = None
        os.environ["DRLINK_WEB_QUIET"] = "1"
        Path(self.temp.name, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.temp.name, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8",
        )
        Path(self.temp.name, "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\n", encoding="utf-8",
        )

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join(timeout=3)
            self.server.server_close()
        os.environ.pop("DRLINK_WEB_QUIET", None)
        self.temp.cleanup()

    def start(self, *, policy=_UNSET, proxies=()):
        kwargs = {}
        if policy is not _UNSET:
            kwargs["management_acl"] = policy
        if proxies:
            kwargs["trusted_proxy_cidrs"] = proxies
        self.server = create_server(
            root=self.temp.name, listen="127.0.0.1", port=0,
            static_root=str(ROOT / "web/dist"), **kwargs,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
        )
        self.thread.start()

    def request(self, method, path, *, headers=None, body=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5,
        )
        req_headers = {"Accept": "application/json"}
        req_headers.update(headers or {})
        raw = None
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        conn.request(method, path, raw, headers=req_headers)
        resp = conn.getresponse()
        payload = resp.read()
        headers_out = {k.lower(): v for k, v in resp.getheaders()}
        status = resp.status
        conn.close()
        return status, headers_out, payload

    def test_default_disabled_preserves_http_login_and_public_routes(self):
        self.start()
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        self.assertEqual(self.request("GET", "/")[0], 200)
        status, headers, _ = self.request(
            "POST", "/api/v1/auth/login/start", body={},
        )
        self.assertEqual(status, 401)
        self.assertNotIn("set-cookie", headers)

    def test_disabled_allowlist_does_not_change_duplicate_header_legacy_behavior(self):
        # Default-OFF mode must not introduce a surprise HTTP 403 when
        # a proxy supplies more than one harmless forwarded header.
        self.start()
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5,
        )
        conn.putrequest("GET", "/healthz")
        conn.putheader("X-Forwarded-For", "198.51.100.10")
        conn.putheader("X-Forwarded-For", "198.51.100.11")
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        conn.close()

    def test_explicit_missing_policy_fails_closed_across_every_route(self):
        self.start(policy=None)
        for method, path in (
            ("GET", "/healthz"), ("GET", "/"),
            ("GET", "/api/v1/health"),
            # B4 diagnostics is behind source ACL before its own role check.
            ("GET", "/api/v1/system/connectivity"),
            ("POST", "/api/v1/auth/login/start"),
            ("POST", "/api/v1/auth/login/cancel"),
        ):
            with self.subTest(method=method, path=path):
                status, headers, body = self.request(method, path)
                self.assertEqual(status, 403)
                self.assertNotIn("set-cookie", headers)
                self.assertNotIn(b"session", body.lower())

    def test_enabled_direct_peer_rejects_all_web_and_api_requests(self):
        self.start(policy=enabled("203.0.113.8/32"))
        for method, path in (
            ("GET", "/healthz"), ("GET", "/"),
            ("GET", "/api/v1/health"),
            ("GET", "/api/v1/system/connectivity"),
            ("POST", "/api/v1/auth/login/start"),
            ("POST", "/api/automation/v1/jobs"),
        ):
            with self.subTest(method=method, path=path):
                status, headers, _ = self.request(method, path)
                self.assertEqual(status, 403)
                self.assertNotIn("set-cookie", headers)

    def test_allowed_loopback_source_preserves_native_route_authority(self):
        self.start(policy=enabled("127.0.0.1/32"))
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/health")[0], 401)
        self.assertEqual(self.request("GET", "/api/v1/system/connectivity")[0], 401)
        self.assertEqual(self.request("POST", "/api/v1/auth/login/start", body={})[0], 401)
        self.assertTrue(
            self.server.app.authorize_web_ingress("::ffff:127.0.0.1").allowed
        )

    def test_trusted_proxy_requires_valid_forwarded_chain(self):
        self.start(
            policy=enabled("203.0.113.8/32"),
            proxies=("127.0.0.1/32",),
        )
        self.assertEqual(self.request(
            "GET", "/healthz", headers={"X-Forwarded-For": "203.0.113.8"},
        )[0], 200)
        # Two independent forwarded-chain headers are ambiguous and denied.
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5,
        )
        conn.putrequest("GET", "/healthz")
        conn.putheader("X-Forwarded-For", "203.0.113.8")
        conn.putheader("X-Forwarded-For", "203.0.113.8")
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        conn.close()
        for spoof in (None, "garbage", "203.0.113.8, garbage", "127.0.0.1"):
            with self.subTest(header=spoof):
                hdr = {} if spoof is None else {"X-Forwarded-For": spoof}
                self.assertEqual(self.request("GET", "/healthz", headers=hdr)[0], 403)

    def test_untrusted_forwarded_header_never_substitutes_direct_peer(self):
        self.start(policy=enabled("203.0.113.8/32"))
        self.assertEqual(self.request(
            "GET", "/healthz", headers={"X-Forwarded-For": "203.0.113.8"},
        )[0], 403)
        self.assertFalse(self.server.app.authorize_web_ingress(
            "198.51.100.2", "203.0.113.8",
        ).allowed)

    def test_invalid_policy_or_proxy_trust_fails_at_initialization(self):
        with self.assertRaises(ValueError):
            self.start(policy="not-a-policy")
        with self.assertRaises(ValueError):
            self.start(
                policy=enabled("127.0.0.1/32"),
                proxies=("0.0.0.0/0",),
            )


if __name__ == "__main__":
    unittest.main()
