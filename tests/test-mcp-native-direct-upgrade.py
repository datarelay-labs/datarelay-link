#!/usr/bin/env python3
"""Native MCP Preview exact pinned upgrade, local-only contract tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/operator-native-mcp-upgrade.py"
SPEC = importlib.util.spec_from_file_location("mcp_native_upgrade", SOURCE)
assert SPEC and SPEC.loader
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)


class NativeDirectUpgradeTests(unittest.TestCase):
    def test_exact_unit_sha_and_native_url_without_changing_executor_flag(self):
        pinned = Path("/opt/drlink-native-mcp-preview/releases") / ("a" * 40)
        old = upgrade.preview.unit_content(pinned)
        self.assertEqual(upgrade._unit_sha(old), "a" * 40)
        current = upgrade._upgraded_unit(pinned)
        self.assertIn("DRLINK_MCP_NATIVE_PUBLIC_URL=https://mcp.xdr.ooo/access/mcp", current)
        self.assertIn("DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0", current)
        self.assertIn("127.0.0.1 --port 16106", current)
        self.assertNotIn("127.0.0.1 --port 6103", current)
        self.assertEqual(upgrade._unit_sha(current), "a" * 40)
        self.assertNotEqual(current, old)

    def test_refuses_unrecognized_service_unit(self):
        for content in (
            "ExecStart=/usr/bin/python3 /tmp/untrusted.py --listen 0.0.0.0 --port 16106",
            "ExecStart=/usr/bin/python3 /opt/drlink-native-mcp-preview/releases/garbage/lib/drlink_mcp_bridge.py --listen 127.0.0.1 --port 16106",
            "",
        ):
            with self.assertRaisesRegex(RuntimeError, "not pinned"):
                upgrade._unit_sha(content)

    def test_validates_expected_unit_root_ownership(self):
        with tempfile.TemporaryDirectory(prefix="drlink-preview-upgrade-") as t:
            unit = Path(t) / "preview.service"
            root = Path(t) / "releases"
            (root / ("a" * 40)).mkdir(parents=True)
            unit.write_text(upgrade.preview.unit_content(root / ("a" * 40)))
            with (
                patch.object(upgrade.preview, "UNIT", unit),
                patch.object(upgrade.preview, "ROOT_INSTALL", root),
                patch.object(upgrade.preview, "root_owned", return_value=True),
            ):
                text, sha = upgrade._current_unit()
                self.assertEqual(sha, "a" * 40)
                self.assertIn("SERVER_LOCAL_EXEC_ENABLED=0", text)

    def test_public_resource_identity_is_dedicated_to_access(self):
        self.assertEqual(upgrade.PUBLIC_RESOURCE, "https://mcp.xdr.ooo/access/mcp")
        self.assertEqual(upgrade.PUBLIC_ISSUER, "https://mcp.xdr.ooo/access")
        self.assertNotEqual(upgrade.PUBLIC_RESOURCE, "https://mcp.xdr.ooo/mcp")

    def test_snapshot_hash_check_and_backup_contents(self):
        with tempfile.TemporaryDirectory(prefix="drlink-upgrade-save-") as t:
            path = Path(t) / "service"
            original = b"pinned native unit\n"
            upgrade._save(path, original, 0o600)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(upgrade._hash(original)), 64)


if __name__ == "__main__":
    unittest.main()
