#!/usr/bin/env python3
"""PF-12B Link product-native backup source confinement (temporary root only)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_management_system import ManagementSystemService

PREFIX = "/var/lib/drlink/backups/"


class BackupSourceConfinementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pf12-link-backup-path-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.backups = self.base / "var/lib/drlink/backups"
        self.backups.mkdir(parents=True)
        self.service = ManagementSystemService(self.temp.name)

    def test_ordinary_canonical_backup_stays_in_product_owned_tree(self):
        target = self.backups / "archive-1.tar.gz"
        target.write_bytes(b"synthetic-test-content")
        requested, resolved = self.service._backup_target(PREFIX + "archive-1.tar.gz")
        self.assertEqual(requested, PREFIX + "archive-1.tar.gz")
        self.assertEqual(resolved, target)

    def test_canonical_missing_backup_can_be_reported_invalid_by_validator(self):
        requested, resolved = self.service._backup_target(PREFIX + "missing.tar.gz")
        self.assertEqual(requested, PREFIX + "missing.tar.gz")
        self.assertEqual(resolved, self.backups / "missing.tar.gz")

    def test_backup_root_symlink_outside_storage_is_rejected(self):
        external = self.base / "foreign-archive"
        external.mkdir()
        (external / "restorable.tar.gz").write_bytes(b"forged")
        self.backups.rmdir()
        self.backups.symlink_to(external, target_is_directory=True)
        with patch("drlink_management_system.subprocess.run") as run:
            with self.assertRaisesRegex(ControlPlaneError, "symlink"):
                self.service.backup_validate(PREFIX + "restorable.tar.gz")
            run.assert_not_called()

    def test_nested_symlink_alias_within_backup_root_rejected(self):
        real = self.backups / "completed"
        real.mkdir()
        (real / "archive.tar.gz").write_bytes(b"legitimate-test-archive")
        (self.backups / "alias").symlink_to(real, target_is_directory=True)
        with patch("drlink_management_system.subprocess.run") as run:
            with self.assertRaisesRegex(ControlPlaneError, "symlink"):
                self.service.backup_validate(PREFIX + "alias/archive.tar.gz")
            run.assert_not_called()

    def test_final_file_symlink_is_rejected_even_if_target_inside_backup_root(self):
        artifact = self.backups / "actual.tar.gz"
        artifact.write_bytes(b"test")
        (self.backups / "other.tar.gz").symlink_to(artifact)
        with self.assertRaisesRegex(ControlPlaneError, "symlink"):
            self.service._backup_target(PREFIX + "other.tar.gz")

    def test_dangling_symlink_is_rejected(self):
        (self.backups / "missing-link.tar.gz").symlink_to(self.backups / "none.tar.gz")
        with self.assertRaisesRegex(ControlPlaneError, "symlink"):
            self.service._backup_target(PREFIX + "missing-link.tar.gz")

    def test_backup_parent_symlink_outside_storage_rejected(self):
        external = self.base / "foreign-var"
        external.mkdir()
        self.backups.rmdir()
        (self.base / "var/lib/drlink").rmdir()
        (self.base / "var/lib").rmdir()
        (self.base / "var").rmdir()
        (self.base / "var").symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ControlPlaneError, "symlink"):
            self.service._backup_target(PREFIX + "backup.tar.gz")

    def test_hard_link_to_foreign_file_rejected(self):
        external = self.base / "sensitive-catalog-data"
        external.write_bytes(b"synthetic-not-a-real-customer-secret")
        os.link(external, self.backups / "hard-linked.tar.gz")
        with patch("drlink_management_system.subprocess.run") as run:
            with self.assertRaisesRegex(ControlPlaneError, "archive|link"):
                self.service.backup_validate(PREFIX + "hard-linked.tar.gz")
            run.assert_not_called()

    def test_nonregular_existing_backup_rejected(self):
        (self.backups / "directory.tar.gz").mkdir()
        with self.assertRaisesRegex(ControlPlaneError, "archive|regular"):
            self.service._backup_target(PREFIX + "directory.tar.gz")
        fifo = self.backups / "pipe.tar.gz"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ControlPlaneError, "archive|regular"):
            self.service._backup_target(PREFIX + "pipe.tar.gz")

    def test_normalized_dots_and_empty_components_are_rejected(self):
        for name in (
            "archive/../backup.tar.gz", "./backup.tar.gz", "archives//backup.tar.gz",
            "backup.tar.gz/", "backups/./backup.tar.gz",
            "backup\\subdir.tar.gz", "bad\x00name.tar.gz",
        ):
            with self.subTest(name=repr(name)):
                with self.assertRaises(ControlPlaneError):
                    self.service._backup_target(PREFIX + name)

    def test_regular_nested_file_is_valid_and_validator_receives_actual_path(self):
        inner = self.backups / "daily"
        inner.mkdir()
        archive = inner / "known-good.tar.gz"
        archive.write_bytes(b"temporary-fixture-not-a-customer-backup")
        from subprocess import CompletedProcess
        completed = CompletedProcess([], 0, "Backup valid.\n", "")
        with patch("drlink_management_system.subprocess.run", return_value=completed) as run:
            report = self.service.backup_validate(PREFIX + "daily/known-good.tar.gz")
            self.assertTrue(report["valid"])
            self.assertFalse(report["authoritative_mutation"])
            self.assertEqual(report["path"], PREFIX + "daily/known-good.tar.gz")
            self.assertEqual(run.call_args.args[0][-1], str(archive))
            self.assertIn("--validate", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
