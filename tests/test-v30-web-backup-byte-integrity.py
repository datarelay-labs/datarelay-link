#!/usr/bin/env python3
"""PF-12 Link: native read-only bounded real-byte archive observation; NOT DR proof."""
from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_management_system import ManagementSystemService

PREFIX = "/var/lib/drlink/backups/"
CONTENT = b"\x00synthetic product backup bytes\x01\xff" * 31


class BackupByteIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pf12-link-bytes-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.backups = self.root / "var/lib/drlink/backups"
        self.backups.mkdir(parents=True)
        self.service = ManagementSystemService(self.tmp.name)
        self.archive = self.backups / "source.tar.gz"
        self.archive.write_bytes(CONTENT)

    def test_reads_actual_synthetic_bytes_and_compares_supplied_digest(self):
        expected = hashlib.sha256(CONTENT).hexdigest()
        report = self.service.backup_integrity(
            PREFIX + "source.tar.gz", expected_sha256=expected
        )
        self.assertEqual(report["path"], PREFIX + "source.tar.gz")
        self.assertEqual(report["sha256_observed"], expected)
        self.assertEqual(report["artifact_bytes"], len(CONTENT))
        self.assertTrue(report["matches_caller_supplied_sha256"])
        self.assertFalse(report["expected_digest_authenticated"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["authoritative_mutation"])
        self.assertFalse(report["restore_ready"])
        self.assertFalse(report["encryption_verified"])
        self.assertFalse(report["isolated_restore_drill_verified"])
        self.assertNotIn("synthetic product backup bytes", str(report))
        self.assertEqual(self.archive.read_bytes(), CONTENT)

    def test_mismatched_supplied_digest_is_explicit_not_restorable(self):
        report = self.service.backup_integrity(
            PREFIX + "source.tar.gz", expected_sha256="0" * 64
        )
        self.assertFalse(report["matches_caller_supplied_sha256"])
        self.assertFalse(report["restore_ready"])
        self.assertTrue(report["sha256_observed"])

    def test_no_expected_digest_never_claims_verified_provenance(self):
        report = self.service.backup_integrity(PREFIX + "source.tar.gz")
        self.assertIsNone(report["matches_caller_supplied_sha256"])
        self.assertFalse(report["expected_digest_authenticated"])
        self.assertFalse(report["restore_ready"])

    def test_invalid_expected_digests_are_rejected_before_file_open(self):
        for bad in ("x" * 64, "A" * 64, "123", "", "0" * 65, True, None):
            if bad is None:
                continue  # None explicitly means observation only.
            with self.subTest(digest=repr(bad)[:15]):
                with self.assertRaises(ControlPlaneError):
                    self.service.backup_integrity(
                        PREFIX + "source.tar.gz", expected_sha256=bad
                    )

    def test_missing_and_nonregular_sources_fail_without_checksum(self):
        with self.assertRaises(ControlPlaneError):
            self.service.backup_integrity(PREFIX + "missing.tar.gz")
        (self.backups / "directory.tar.gz").mkdir()
        with self.assertRaises(ControlPlaneError):
            self.service.backup_integrity(PREFIX + "directory.tar.gz")
        os.mkfifo(self.backups / "pipe.tar.gz")
        with self.assertRaises(ControlPlaneError):
            self.service.backup_integrity(PREFIX + "pipe.tar.gz")

    def test_symlinked_root_and_in_tree_alias_are_rejected(self):
        (self.backups / "alias.tar.gz").symlink_to(self.archive)
        with self.assertRaises(ControlPlaneError):
            self.service.backup_integrity(PREFIX + "alias.tar.gz")
        external = self.root / "elsewhere"
        external.mkdir()
        (external / "source.tar.gz").write_bytes(b"foreign fixture bytes")
        self.archive.unlink()
        (self.backups / "alias.tar.gz").unlink()
        self.backups.rmdir()
        self.backups.symlink_to(external, target_is_directory=True)
        with self.assertRaises(ControlPlaneError):
            self.service.backup_integrity(PREFIX + "source.tar.gz")

    def test_symlink_swap_after_path_preflight_still_fails_nofollow(self):
        original_preflight = self.service._backup_target
        foreign = self.root / "foreign-backup-data"
        foreign.write_bytes(b"foreign synthetic file")

        def swap_after_preflight(path):
            result = original_preflight(path)
            self.archive.unlink()
            self.archive.symlink_to(foreign)
            return result

        with mock.patch.object(
            self.service, "_backup_target", side_effect=swap_after_preflight,
        ):
            with self.assertRaises(ControlPlaneError):
                self.service.backup_integrity(PREFIX + "source.tar.gz")
        self.assertEqual(foreign.read_bytes(), b"foreign synthetic file")

    def test_multi_link_archive_rejected(self):
        outside = self.root / "foreign-inode"
        outside.write_bytes(b"not owned by archive namespace")
        os.link(outside, self.backups / "multiple.tar.gz")
        with self.assertRaises(ControlPlaneError):
            self.service.backup_integrity(PREFIX + "multiple.tar.gz")

    def test_maximum_size_rejected_without_reading_bytes(self):
        from drlink_management_system import MAX_BACKUP_OBSERVE_BYTES
        with self.archive.open("r+b") as handle:
            handle.truncate(MAX_BACKUP_OBSERVE_BYTES + 1)
        with mock.patch("drlink_management_system.os.read") as read:
            with self.assertRaisesRegex(ControlPlaneError, "limit|large|size"):
                self.service.backup_integrity(PREFIX + "source.tar.gz")
            read.assert_not_called()

    def test_mutated_archive_during_read_rejected(self):
        real_read = os.read
        mutated = False

        def tamper(fd, size):
            nonlocal mutated
            chunk = real_read(fd, size)
            if not mutated:
                mutated = True
                with self.archive.open("r+b") as stream:
                    stream.seek(0)
                    stream.write(b"replaced")
            return chunk

        with mock.patch("drlink_management_system.os.read", side_effect=tamper):
            with self.assertRaisesRegex(ControlPlaneError, "changed|unstable"):
                self.service.backup_integrity(PREFIX + "source.tar.gz")
        self.assertTrue(mutated)

    def test_archive_path_alias_rejected(self):
        for name in ("../source.tar.gz", "./source.tar.gz",
                     "subdir//source.tar.gz", "source.tar.gz/"):
            with self.subTest(name=name):
                with self.assertRaises(ControlPlaneError):
                    self.service.backup_integrity(PREFIX + name)


if __name__ == "__main__":
    unittest.main()
