#!/usr/bin/env python3
"""Non-privileged contract tests for the optional Server Native MCP rollout."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import urllib.error
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

    def test_preview_startup_waits_for_local_listener(self):
        transient = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        with (
            patch.object(rollout, "local_probe", side_effect=[transient, transient, None]) as probe,
            patch.object(rollout.time, "sleep") as pause,
        ):
            rollout.wait_ready(timeout_seconds=2)
        self.assertEqual(probe.call_count, 3)
        self.assertEqual(pause.call_count, 2)

    def test_preview_startup_does_not_retry_auth_or_metadata_failures(self):
        with patch.object(rollout, "local_probe",
                          side_effect=RuntimeError("Unexpected MCP status: 200")) as probe:
            with self.assertRaisesRegex(RuntimeError, "Unexpected MCP status"):
                rollout.wait_ready(timeout_seconds=2)
        probe.assert_called_once()

    def test_preview_timeout_reports_transport_failure(self):
        with (
            patch.object(rollout, "local_probe",
                         side_effect=urllib.error.URLError("connection refused")),
            patch.object(rollout.time, "monotonic", side_effect=[0.0, 2.0]),
        ):
            with self.assertRaisesRegex(RuntimeError, "listener did not become ready"):
                rollout.wait_ready(timeout_seconds=1)

    def test_resume_requires_root_and_cannot_reinstall(self):
        with patch.object(rollout.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(RuntimeError, "--resume requires direct operator root"):
                rollout.resume(rollout.source_head())

    def test_resume_reuses_verified_snapshot_without_reinstalling(self):
        with tempfile.TemporaryDirectory(prefix="drlink-preview-resume-") as directory:
            releases = Path(directory) / "releases"
            releases.mkdir()
            with patch.object(rollout, "ROOT_INSTALL", releases):
                pinned = rollout.source_head()
                snapshot = rollout.immutable_snapshot(pinned)
                unit = Path(directory) / "preview.service"
                unit.write_text(rollout.unit_content(snapshot), encoding="utf-8")
                calls = []

                def fake_command(argv, *, check=True, capture=True):
                    calls.append(list(argv))
                    if argv == ["systemctl", "is-active", "--quiet", rollout.SERVICE]:
                        active = sum(
                            c == ["systemctl", "is-active", "--quiet", rollout.SERVICE]
                            for c in calls
                        )
                        return subprocess.CompletedProcess(argv, 3 if active == 1 else 0)
                    return subprocess.CompletedProcess(argv, 0)

                with (
                    patch.object(rollout, "UNIT", unit),
                    patch.object(rollout.os, "geteuid", return_value=0),
                    patch.object(rollout, "root_owned", return_value=True),
                    patch.object(rollout, "command", side_effect=fake_command),
                    patch.object(rollout, "port_available", return_value=True),
                    patch.object(rollout, "wait_ready") as ready,
                    patch.object(rollout, "backup_db") as backup,
                    patch.object(rollout, "immutable_snapshot") as reinstall,
                ):
                    rollout.resume(pinned)
                    ready.assert_called_once()
                    backup.assert_not_called()
                    reinstall.assert_not_called()
                self.assertIn(["systemctl", "start", rollout.SERVICE], calls)

    def test_resume_rejects_changed_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="drlink-preview-tamper-") as directory:
            releases = Path(directory) / "releases"
            releases.mkdir()
            with patch.object(rollout, "ROOT_INSTALL", releases):
                pinned = rollout.source_head()
                snapshot = rollout.immutable_snapshot(pinned)
                unit = Path(directory) / "preview.service"
                unit.write_text(rollout.unit_content(snapshot), encoding="utf-8")
                (snapshot / "lib/drlink_mcp_bridge.py").write_text("tampered\n")
                with (
                    patch.object(rollout, "UNIT", unit),
                    patch.object(rollout.os, "geteuid", return_value=0),
                    patch.object(rollout, "root_owned", return_value=True),
                    patch.object(rollout, "command") as command,
                ):
                    with self.assertRaisesRegex(RuntimeError, "snapshot mismatch"):
                        rollout.resume(pinned)
                    command.assert_not_called()

    def test_public_port_is_not_used_by_local_preview(self):
        self.assertEqual(rollout.PORT, 16106)
        self.assertEqual(rollout.PUBLIC, "https://access.xdr.ooo/mcp")
        self.assertNotEqual(rollout.SERVICE, "drlink-mcp-bridge.service")
        self.assertNotEqual(rollout.SERVICE, "drlink-mcp-bridge-176.service")


if __name__ == "__main__":
    unittest.main()
