#!/usr/bin/env python3
"""Non-privileged contract tests for the optional Server Native MCP rollout."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/operator-native-mcp-preview.py"
spec = importlib.util.spec_from_file_location("drlink_native_preview", SOURCE)
assert spec and spec.loader
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


class NativePreviewRolloutTests(unittest.TestCase):
    def test_systemd_preview_does_not_replace_existing_units(self):
        text = rollout.unit_content(Path("/opt/drlink-native-mcp-preview/releases/example"))
        self.assertIn("127.0.0.1 --port 16106", text)
        self.assertIn("DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0", text)
        self.assertIn("DRLINK_MCP_SERVER_SELF_ENABLED=1", text)
        self.assertIn("DRLINK_MCP_PUBLIC_URL=https://access.xdr.ooo/mcp", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertNotIn("ExecStart=/usr/local/lib/drlink/", text)
        self.assertNotIn("Environment=DRLINK_MCP_SERVER_EXEC_USER=", text)

    def test_candidate_snapshot_is_tracked_and_readable(self):
        with tempfile.TemporaryDirectory(prefix="drlink-preview-archive-") as directory:
            with patch.object(rollout, "ROOT_INSTALL", Path(directory)):
                candidate = rollout.immutable_snapshot(rollout.source_head())
                self.assertTrue((candidate / "lib/drlink_mcp_bridge.py").is_file())
                self.assertTrue((candidate / "lib/drlink_mcp_server_executor.py").is_file())
                self.assertFalse((candidate / ".git").exists())
                self.assertFalse((candidate / ".ssh").exists())
                self.assertEqual((candidate / "lib/drlink_mcp_bridge.py").stat().st_mode & 0o777, 0o644)

    def test_apply_requires_operator_root(self):
        with patch.object(rollout.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(RuntimeError, "operator root"):
                rollout.apply(rollout.source_head())

    def test_v24_schema_preflight_uses_migration_ledger(self):
        import sys
        sys.path.insert(0, str(ROOT / "lib"))
        from drlink_control_plane import ControlPlane
        with tempfile.TemporaryDirectory(prefix="drlink-preview-schema-") as directory:
            plane = ControlPlane(directory)
            db = Path(directory) / "var/lib/drlink/drlink.db"
            with (
                patch.object(rollout, "DB", db),
                patch.object(rollout, "UNIT", Path(directory) / "unit"),
                patch.object(rollout, "source_integrity"),
                patch.object(rollout, "port_available", return_value=True),
                patch.object(rollout, "public_tls_status", return_value="URLError"),
                patch.object(rollout, "command"),
                patch.object(rollout.os, "geteuid", return_value=0),
            ):
                rollout.preflight("0" * 40)
            plane.close()

    def test_public_port_is_not_used_by_local_preview(self):
        self.assertEqual(rollout.PORT, 16106)
        self.assertEqual(rollout.PUBLIC, "https://access.xdr.ooo/mcp")
        self.assertNotEqual(rollout.SERVICE, "drlink-mcp-bridge.service")
        self.assertNotEqual(rollout.SERVICE, "drlink-mcp-bridge-176.service")


if __name__ == "__main__":
    unittest.main()
