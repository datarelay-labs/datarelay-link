#!/usr/bin/env python3
"""PF-9: isolated opt-in ACL policy file parsing and actual Web HTTP boundary."""
from __future__ import annotations

import http.client
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_web_management_policy import load_management_ingress
from drlink_web_service import create_server


def config(*, enabled=True, source="127.0.0.1/32", proxies=()):
    return {
        "schema_version": 1,
        "web": {
            "enabled": enabled, "revision": "test-revision-1",
            "sources": [{"cidr": source}] if enabled else [],
        },
        "trusted_proxy_cidrs": list(proxies),
    }


class WebIngressConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-pf9-acl-config-")
        self.root = Path(self.tmp.name)
        (self.root / "etc/drlink").mkdir(parents=True, exist_ok=True)
        (self.root / "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        (self.root / "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\n", encoding="utf-8"
        )
        self.file = self.root / "web-acl-policy.json"
        self.server = None
        self.thread = None
        os.environ["DRLINK_WEB_QUIET"] = "1"

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join(timeout=2)
            self.server.server_close()
        os.environ.pop("DRLINK_WEB_QUIET", None)
        self.tmp.cleanup()

    def save(self, value):
        raw = value if isinstance(value, str) else json.dumps(value)
        self.file.write_bytes(raw.encode("utf-8"))
        self.file.chmod(0o600)
        return str(self.file)

    def start(self, path):
        self.server = create_server(
            root=str(self.root), listen="127.0.0.1", port=0,
            static_root=str(ROOT / "web/dist"),
            management_acl_file=path,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()

    def request(self, method, path, *, headers=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        conn.request(method, path, headers=headers or {})
        resp = conn.getresponse()
        raw = resp.read()
        code = resp.status
        info = {key.lower(): val for key, val in resp.getheaders()}
        conn.close()
        return code, info, raw

    def test_valid_strict_schema_and_immutable_policy(self):
        f = self.save(config())
        before = self.file.read_bytes()
        parsed = load_management_ingress(f)
        self.assertTrue(parsed.policy.web.enabled)
        self.assertEqual(parsed.policy.web.revision, "test-revision-1")
        self.assertEqual(parsed.policy.web.sources[0].cidr, "127.0.0.1/32")
        self.assertEqual(parsed.trusted_proxy_cidrs, ())
        self.assertEqual(self.file.read_bytes(), before)

    def test_opt_in_policy_file_guards_static_login_api_and_health(self):
        self.start(self.save(config(source="203.0.113.24/32")))
        for method, path in (
            ("GET", "/healthz"), ("GET", "/"),
            ("GET", "/api/v1/health"), ("POST", "/api/v1/auth/login/start"),
        ):
            with self.subTest(path=path):
                status, headers, _ = self.request(method, path)
                self.assertEqual(status, 403)
                self.assertNotIn("set-cookie", headers)

    def test_explicit_allowed_file_preserves_auth_and_static_behavior(self):
        self.start(self.save(config()))
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/health")[0], 401)

    def test_configured_trusted_proxy_uses_real_peer_and_header(self):
        self.start(self.save(config(
            source="203.0.113.8/32", proxies=("127.0.0.1/32",),
        )))
        self.assertEqual(self.request(
            "GET", "/healthz", headers={"X-Forwarded-For": "203.0.113.8"}
        )[0], 200)
        self.assertEqual(self.request("GET", "/healthz")[0], 403)
        self.assertEqual(self.request(
            "GET", "/healthz", headers={"X-Forwarded-For": "192.0.2.25"}
        )[0], 403)

    def test_explicit_disabled_config_retains_default_access(self):
        self.start(self.save(config(enabled=False)))
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/health")[0], 401)

    def test_invalid_json_duplicate_keys_and_unknown_fields_fail_closed(self):
        data = config()
        cases = [
            "{", "null", "[]", '{"schema_version":1,"schema_version":1}',
            '{"schema_version":1,"web":{},"web":{}}',
            {**data, "ssh": {"enabled": True}},
            {**data, "additional": False},
            {**data, "schema_version": 0},
            {**data, "schema_version": True},
            {**data, "web": {**data["web"], "secret": "no"}},
            {**data, "web": {**data["web"], "revision": ""}},
            {**data, "web": {**data["web"], "sources": [{"cidr": "0.0.0.0/0"}]}},
            {**data, "web": {**data["web"], "sources": [{"cidr": "127.0.0.1/32", "password": "no"}]}},
            {**data, "trusted_proxy_cidrs": ["0.0.0.0/0"]},
            {**data, "trusted_proxy_cidrs": ["127.0.0.1/32", "127.0.0.1/32"]},
        ]
        for item in cases:
            with self.subTest(item=str(item)[:65]):
                with self.assertRaises(ValueError):
                    load_management_ingress(self.save(item))

    def test_missing_symlink_and_untrusted_file_permissions_rejected(self):
        with self.assertRaises(ValueError):
            load_management_ingress(str(self.root / "missing.json"))
        self.save(config())
        self.file.chmod(0o644)
        with self.assertRaises(ValueError):
            load_management_ingress(str(self.file))
        self.file.chmod(0o600)
        link = self.root / "policy-link.json"
        link.symlink_to(self.file)
        with self.assertRaises(ValueError):
            load_management_ingress(str(link))
        hardlink = self.root / "policy-hard.json"
        os.link(self.file, hardlink)
        with self.assertRaises(ValueError):
            load_management_ingress(str(self.file))
        with self.assertRaises(ValueError):
            load_management_ingress(str(self.root))

    def test_relative_and_oversized_file_rejected(self):
        with self.assertRaises(ValueError):
            load_management_ingress("local-policy.json")
        self.save(" " * 16_500)
        with self.assertRaises(ValueError):
            load_management_ingress(str(self.file))

    def test_cli_flag_passes_selected_file_without_activating_service(self):
        from unittest.mock import patch
        import drlink_web_service

        selected = self.save(config(enabled=False))
        calls = {}
        class FakeServer:
            def serve_forever(self, *, poll_interval):
                calls["poll_interval"] = poll_interval
            def server_close(self):
                calls["closed"] = True

        def make_server(**kwargs):
            calls["kwargs"] = kwargs
            return FakeServer()

        with patch.object(drlink_web_service, "create_server", side_effect=make_server):
            self.assertEqual(drlink_web_service.main([
                "--root", str(self.root),
                "--listen", "127.0.0.1", "--port", "0",
                "--management-acl-file", selected,
            ]), 0)
        self.assertEqual(calls["kwargs"]["management_acl_file"], selected)
        self.assertEqual(calls["poll_interval"], 0.5)
        self.assertTrue(calls["closed"])

    def test_non_utf8_and_broken_source_metadata_fail_closed(self):
        self.file.write_bytes(bytes((255, 254)))
        self.file.chmod(0o600)
        with self.assertRaises(ValueError):
            load_management_ingress(str(self.file))
        source = config()
        source["web"]["sources"] = [{"cidr": "127.0.0.1", "expires_at": True}]
        with self.assertRaises(ValueError):
            load_management_ingress(self.save(source))
        source["web"]["sources"] = [{"cidr": "127.0.0.1", "name": 12}]
        with self.assertRaises(ValueError):
            load_management_ingress(self.save(source))

    def test_actual_loaded_status_is_explicit_and_redacted(self):
        self.start(self.save(config(
            source="127.0.0.1/32", proxies=("198.51.100.2/32",),
        )))
        report = self.server.app.management_ingress_status()
        self.assertEqual(report["web"]["status"], "ENABLED")
        self.assertEqual(report["web"]["policy_revision"], "test-revision-1")
        self.assertEqual(report["web"]["source_count"], 1)
        self.assertEqual(report["web"]["trusted_proxy_count"], 1)
        self.assertEqual(report["ssh_host"]["status"], "UNAVAILABLE")
        self.assertFalse(report["apply_available"])
        self.assertFalse(report["configuration_mutation_supported"])
        encoded = json.dumps(report)
        self.assertNotIn("127.0.0.1/32", encoded)
        self.assertNotIn("198.51.100.2", encoded)

    def test_explicit_missing_policy_status_is_unavailable_not_healthy(self):
        self.server = create_server(
            root=str(self.root), listen="127.0.0.1", port=0,
            management_acl=None,
        )
        report = self.server.app.management_ingress_status()
        self.assertEqual(report["web"]["status"], "UNAVAILABLE")
        self.assertIsNone(report["web"]["policy_revision"])
        self.assertFalse(report["apply_available"])
        self.assertEqual(report["ssh_host"]["status"], "UNAVAILABLE")
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
        )
        self.thread.start()
        self.assertEqual(self.request("GET", "/healthz")[0], 403)

    def test_file_and_direct_policy_cannot_be_combined(self):
        from drlink_foundation_security import FoundationManagementPolicy
        f = self.save(config())
        with self.assertRaises(ValueError):
            create_server(
                root=str(self.root), listen="127.0.0.1", port=0,
                management_acl_file=f, trusted_proxy_cidrs=("127.0.0.1/32",),
            )
        with self.assertRaises(ValueError):
            create_server(
                root=str(self.root), listen="127.0.0.1", port=0,
                management_acl_file=f, management_acl=None,
            )


if __name__ == "__main__":
    unittest.main()
