#!/usr/bin/env python3
"""B3 offline Web management ACL admission simulation; never changes policy."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_web_management_policy import preview_management_ingress


class ManagementIngressPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-web-acl-preview-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "policy-private.json"

    def save(self, *, sources=("192.0.2.6/32",), enabled=True, proxies=()):
        self.path.write_text(json.dumps({
            "schema_version": 1, "web": {
                "enabled": enabled, "revision": "fixture-v1",
                "sources": [{"cidr": cidr} for cidr in sources],
            },
            "trusted_proxy_cidrs": list(proxies),
        }), encoding="utf-8")
        self.path.chmod(0o600)
        return str(self.path)

    def preview(self, source="192.0.2.6", **kwargs):
        return preview_management_ingress(
            policy_file=str(self.path), source_peer=source,
            now=1_782_000_000, **kwargs
        )

    def test_direct_allowed_source_still_never_authorizes_rollout(self):
        original = Path(self.save()).read_bytes()
        with mock.patch("socket.create_connection", side_effect=AssertionError("network")), \
             mock.patch("subprocess.run", side_effect=AssertionError("shell")):
            report = self.preview()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["policy_revision"], "fixture-v1")
        self.assertEqual(report["management_source_simulation"], "ALLOW")
        self.assertTrue(report["policy_enabled"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["authoritative_peer_observed"])
        self.assertFalse(report["safe_to_activate"])
        self.assertFalse(report["ssh_host_enforced"])
        self.assertFalse(report["rollback_verified"])
        self.assertIn("observed_management_path_unverified", report["blockers"])
        self.assertIn("rollback_unverified", report["blockers"])
        self.assertEqual(Path(self.path).read_bytes(), original)
        self.assertFalse(any(x in json.dumps(report) for x in (
            "192.0.2.6", "policy-private", self.tmp.name, "192.0.2.6/32"
        )))

    def test_denied_source_and_unrecognized_header_are_never_ready(self):
        self.save()
        for source, headers in [
            ("192.0.2.7", None),
            ("127.0.0.1", "192.0.2.6"),
            (None, None),
            ("not-an-ip", None),
        ]:
            with self.subTest(source=source):
                report = self.preview(source, forwarded_for=headers)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(report["management_source_simulation"], "DENY")
                self.assertIn("simulation_did_not_allow_source", report["blockers"])

    def test_explicit_disabled_policy_does_not_claim_allowlist_coverage(self):
        self.save(enabled=False, sources=())
        report = self.preview()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["management_source_simulation"], "NOT_ENFORCED")
        self.assertIn("web_policy_disabled", report["blockers"])
        self.assertFalse(report["safe_to_activate"])

    def test_trusted_proxy_chain_is_only_source_simulation(self):
        self.save(proxies=("127.0.0.1/32",))
        allowed = self.preview("127.0.0.1", forwarded_for="192.0.2.6")
        self.assertEqual(allowed["management_source_simulation"], "ALLOW")
        self.assertFalse(allowed["authoritative_peer_observed"])
        for forwarded in (None, "bad.example.test", "192.0.2.7"):
            with self.subTest(forwarded=forwarded):
                denied = self.preview("127.0.0.1", forwarded_for=forwarded)
                self.assertEqual(denied["management_source_simulation"], "DENY")

    def test_expired_source_never_qualifies_even_if_cidr_matches(self):
        self.save()
        stored = json.loads(self.path.read_text())
        stored["web"]["sources"][0]["expires_at"] = 1_000_000
        self.path.write_text(json.dumps(stored))
        self.path.chmod(0o600)
        report = self.preview()
        self.assertEqual(report["management_source_simulation"], "DENY")

    def test_cli_return_codes_are_blocked_or_invalid_and_redacted(self):
        self.save()
        cli = ROOT / "tools/drlink-web-acl-preflight"
        valid = subprocess.run([
            sys.executable, str(cli), "--policy-file", str(self.path),
            "--source-peer", "192.0.2.6",
        ], capture_output=True, text=True, timeout=12, check=False)
        self.assertEqual(valid.returncode, 2, valid.stderr)
        result = json.loads(valid.stdout)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["management_source_simulation"], "ALLOW")
        self.assertNotIn("192.0.2.6", valid.stdout)
        self.assertNotIn(str(self.root), valid.stdout)
        invalid = subprocess.run([
            sys.executable, str(cli), "--policy-file", str(self.root / "secret-file"),
            "--source-peer", "192.0.2.6",
        ], capture_output=True, text=True, timeout=12, check=False)
        self.assertEqual(invalid.returncode, 3)
        self.assertNotIn("secret-file", invalid.stdout + invalid.stderr)
        self.assertFalse(json.loads(invalid.stdout)["safe_to_activate"])


if __name__ == "__main__":
    unittest.main()
