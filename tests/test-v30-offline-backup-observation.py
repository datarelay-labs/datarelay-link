#!/usr/bin/env python3
"""PF-12B offline-only archive observation >128 MiB: no real restore or trust proof."""
from __future__ import annotations

import hashlib
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
from drlink_control_db import ControlPlaneError
from drlink_management_system import ManagementSystemService, MAX_BACKUP_OBSERVE_BYTES

ARCHIVE = "/var/lib/drlink/backups/synthetic.tar.gz"
CHUNK = b"\x00" * (1024 * 1024)


class OfflineBackupObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="link-pf12b-offline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backup_dir = self.root / "var/lib/drlink/backups"
        self.backup_dir.mkdir(parents=True)
        self.path = self.backup_dir / "synthetic.tar.gz"
        self.path.write_bytes(b"fixture")

    def test_real_129_mib_stream_web_remains_restricted(self):
        # A genuinely >128MiB file, read in bounded chunks; its sparse bytes
        # are not treated as an integrity proof without an external signature.
        length = 129 * len(CHUNK) + 113
        with self.path.open("wb") as f:
            f.truncate(length)
        service = ManagementSystemService(str(self.root))
        with self.assertRaisesRegex(ControlPlaneError, "limit"):
            service.backup_integrity(ARCHIVE)
        expected = hashlib.sha256()
        for _ in range(129):
            expected.update(CHUNK)
        expected.update(b"\x00" * 113)
        report = service.backup_integrity_offline(ARCHIVE, expected_sha256=expected.hexdigest())
        self.assertEqual(report["sha256_observed"], expected.hexdigest())
        self.assertEqual(report["artifact_bytes"], length)
        self.assertTrue(report["matches_caller_supplied_sha256"])
        for field in ("expected_digest_authenticated", "encryption_verified",
                      "isolated_restore_drill_verified", "restore_ready", "authoritative_mutation"):
            self.assertIs(report[field], False, field)
        self.assertTrue(report["read_only"])
        self.assertEqual(self.path.stat().st_size, length)

    def test_offline_limit_rejected_prior_to_read(self):
        from drlink_management_system import MAX_BACKUP_OFFLINE_OBSERVE_BYTES
        with self.path.open("r+b") as stream:
            stream.truncate(MAX_BACKUP_OFFLINE_OBSERVE_BYTES + 1)
        with mock.patch("drlink_management_system.os.read") as reader:
            with self.assertRaisesRegex(ControlPlaneError, "limit"):
                ManagementSystemService(str(self.root)).backup_integrity_offline(ARCHIVE)
            reader.assert_not_called()

    def test_symlink_rejected_for_offline_mode(self):
        link = self.backup_dir / "alias.tar.gz"
        link.symlink_to(self.path)
        with self.assertRaises(ControlPlaneError):
            ManagementSystemService(str(self.root)).backup_integrity_offline(
                "/var/lib/drlink/backups/alias.tar.gz"
            )

    def test_offline_cli_reports_blocked_not_restore_ready(self):
        program = ROOT / "tools/drlink-backup-offline-observe"
        proc = subprocess.run([
            sys.executable, str(program), "--root", str(self.root),
            "--archive", ARCHIVE,
        ], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["restore_authorized"])
        self.assertFalse(result["observation"]["restore_ready"])
        self.assertEqual(result["observation"]["sha256_observed"],
                         hashlib.sha256(b"fixture").hexdigest())
        self.assertNotIn("fixture", proc.stdout)

    def test_bad_cli_archive_never_echoes_private_path(self):
        program = ROOT / "tools/drlink-backup-offline-observe"
        proc = subprocess.run([
            sys.executable, str(program), "--root", str(self.root),
            "--archive", "/var/lib/drlink/backups/missing-secret-name.tar.gz",
        ], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 3)
        self.assertNotIn("missing-secret-name", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
