#!/usr/bin/env python3
"""Server Peer optional deployment never modifies primary DRLink services."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("server_peer_operator",
                                               ROOT / "tools/operator-server-peer.py")
assert SPEC and SPEC.loader
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


class PeerOperatorTests(unittest.TestCase):
    def test_unit_uses_isolated_root_no_agent_shell(self):
        body = operator.unit_text(Path("/opt/drlink-server-peer/releases/example"))
        self.assertIn("ExecStart=/usr/bin/python3 /opt/drlink-server-peer/releases/example/lib/drlink_server_peer.py", body)
        self.assertIn("Environment=DRLINK_SERVER_PEER_ENABLED=1", body)
        self.assertIn("DRLINK_SERVER_PEER_READ_ENABLED=0", body)
        self.assertIn("NoNewPrivileges=true", body)
        self.assertIn("ProtectSystem=strict", body)
        self.assertNotIn("install-client", body)
        self.assertNotIn("DRLINK_MGMT_INSECURE", body)
        self.assertNotIn("drlink-mcp-native-preview", body)

    def test_apply_requires_root_even_when_identity_valid(self):
        with patch.object(operator.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(RuntimeError, "root operator"):
                operator.apply(operator.source_head())

    def test_missing_enrolled_identity_refuses_apply_without_unit(self):
        with tempfile.TemporaryDirectory(prefix="drlink-peer-op-") as tmp:
            with patch.object(operator.os, "geteuid", return_value=0), \
                 patch.object(operator, "code_matches_head"), \
                 patch.object(operator, "check_identity", side_effect=RuntimeError("not enrolled")), \
                 patch.object(operator, "UNIT", Path(tmp) / "service") as unit, \
                 patch.object(operator, "snapshot") as stage:
                with self.assertRaisesRegex(RuntimeError, "not enrolled"):
                    operator.apply("0" * 40)
                stage.assert_not_called()

    def test_rollback_refuses_unmanaged_unit(self):
        with tempfile.TemporaryDirectory(prefix="drlink-peer-op-") as tmp:
            unit = Path(tmp) / "service"
            unit.write_text("[Service]\nExecStart=/bin/true\n")
            with patch.object(operator.os, "geteuid", return_value=0), \
                 patch.object(operator, "UNIT", unit):
                with self.assertRaisesRegex(RuntimeError, "unmanaged"):
                    operator.rollback()

    def test_root_install_git_scope_matches_exact_worktree(self):
        with patch.object(operator, "command",
                          return_value=subprocess.CompletedProcess(
                              args=[], returncode=0, stdout="f" * 40 + "\n"
                          )) as run:
            self.assertEqual(operator.source_head(), "f" * 40)
        run.assert_called_once_with(
            ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT),
             "rev-parse", "HEAD"]
        )

    def test_verify_binds_to_installed_sha_not_moving_source_head(self):
        with tempfile.TemporaryDirectory(prefix="drlink-peer-unit-") as tmp:
            releases = Path(tmp) / "releases"
            unit = Path(tmp) / "peer.service"
            with patch.object(operator, "RELEASES", releases):
                installed_sha = operator.source_head()
                installed = operator.snapshot(installed_sha)
                unit.write_text(operator.unit_text(installed), encoding="utf-8")
                with (
                    patch.object(operator, "UNIT", unit),
                    patch.object(operator, "check_identity"),
                    patch.object(operator, "_root_owned", return_value=True),
                    patch.object(operator.os, "geteuid", return_value=0),
                    patch.object(operator, "source_head", return_value="f" * 40) as moved,
                    patch.object(operator, "remote_probe") as probe,
                    patch.object(operator, "command", return_value=subprocess.CompletedProcess(
                        args=[], returncode=0, stdout=""
                    )),
                ):
                    operator.verify()
                    moved.assert_not_called()
                    probe.assert_called_once_with(installed)

    def test_verify_rejects_modified_immutable_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="drlink-peer-snapshot-") as tmp:
            releases = Path(tmp) / "releases"
            unit = Path(tmp) / "peer.service"
            with patch.object(operator, "RELEASES", releases):
                installed_sha = operator.source_head()
                installed = operator.snapshot(installed_sha)
                unit.write_text(operator.unit_text(installed), encoding="utf-8")
                (installed / "lib/drlink_server_peer.py").write_text("tampered\n")
                with (
                    patch.object(operator, "UNIT", unit),
                    patch.object(operator, "_root_owned", return_value=True),
                ):
                    with self.assertRaisesRegex(RuntimeError, "installed file differs"):
                        operator.installed_release()

    def test_package_contains_server_peer(self):
        manifest = (ROOT / "lib/server-project-files.manifest").read_text()
        self.assertIn("lib/drlink_server_peer.py python", manifest)
        self.assertIn("lib/drlink_server_peer_enroll.py python", manifest)


if __name__ == "__main__":
    unittest.main()
