#!/usr/bin/env python3
"""Native MCP custom domain stays on the dev Server and preserves FRP."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "native_domain", ROOT / "tools/operator-native-mcp-domain.py")
assert SPEC and SPEC.loader
domain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(domain)


class NativeDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-mcp-domain-")
        self.base = Path(self.temp.name)
        self.releases = self.base / "releases"
        self.release = self.releases / ("e" * 40)
        self.release.mkdir(parents=True)
        self.unit = self.base / "preview.service"

    def tearDown(self):
        self.temp.cleanup()

    def test_target_hostname_not_foreign_host_or_relay(self):
        self.assertEqual(domain.RESOURCE, "https://mcp.link.xdr.ooo/mcp")
        self.assertEqual(domain.ISSUER, "https://mcp.link.xdr.ooo")
        self.assertEqual(domain.HOST, "mcp.link.xdr.ooo")
        self.assertNotIn("mcp.xdr.ooo/access", domain.RESOURCE)

    def test_changes_only_native_public_identity(self):
        old = domain.old_unit(self.release)
        new = domain.target_unit(self.release)
        self.assertIn(domain.ENV_PREFIX + domain.PREVIOUS_RESOURCE, old)
        self.assertIn(domain.ENV_PREFIX + domain.RESOURCE, new)
        self.assertEqual(new.replace(domain.RESOURCE, domain.PREVIOUS_RESOURCE), old)
        self.assertIn("DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0", new)
        self.assertIn("127.0.0.1 --port 16106", new)
        self.assertNotIn("ExecStart=/usr/bin/frps", new)

    def test_accepts_only_pinned_managed_root_owned_unit(self):
        self.unit.write_text(domain.old_unit(self.release))
        with (patch.object(domain.preview, "UNIT", self.unit),
              patch.object(domain.preview, "ROOT_INSTALL", self.releases),
              patch.object(domain.preview, "root_owned", return_value=True)):
            release, text = domain.read_live_unit()
            self.assertEqual(release.name, "e" * 40)
            self.assertEqual(text, domain.old_unit(self.release))
            self.unit.write_text(domain.target_unit(self.release))
            release, text = domain.read_live_unit()
            self.assertEqual(text, domain.target_unit(self.release))
            self.unit.write_text("ExecStart=/usr/bin/frps\n")
            with self.assertRaisesRegex(RuntimeError, "Unexpected Native MCP Preview executable"):
                domain.read_live_unit()

    def test_rejects_privileged_executor_and_unknown_edits(self):
        self.unit.write_text(domain.old_unit(self.release).replace(
            "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0",
            "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=1"))
        with (patch.object(domain.preview, "UNIT", self.unit),
              patch.object(domain.preview, "ROOT_INSTALL", self.releases),
              patch.object(domain.preview, "root_owned", return_value=True)):
            with self.assertRaisesRegex(RuntimeError, "unexpected Native MCP service"):
                domain.read_live_unit()

    def test_backup_hash_is_content_addressed(self):
        original = b"exact root-owned Native Preview service\n"
        with patch.object(domain, "BACKUP_ROOT", self.base):
            f = self.base / "immutable-backup.service"
            domain.atomic(f, original)
            self.assertEqual(f.read_bytes(), original)
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(domain.sha(original)), 64)

    def test_nonroot_apply_denied(self):
        with patch.object(domain.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(RuntimeError, "root SSH operator"):
                domain.apply()


if __name__ == "__main__":
    unittest.main()
