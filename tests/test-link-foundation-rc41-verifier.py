#!/usr/bin/env python3
"""Native Link tests for the source-pinned private Foundation handoff gate."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "verify-link-foundation-rc41.py"
spec = importlib.util.spec_from_file_location("link_foundation_gate", TOOL)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class PrivateFoundationCandidateTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="drlink-pf-private-gate-")
        self.addCleanup(self.workspace.cleanup)
        self.bundle = Path(self.workspace.name) / "synthetic-private.tar.gz"
        self.head = "a" * 40
        self.version = "0.1.0-rc.41"
        self.package_bytes = {
            name: ("package-" + name).encode() for name in gate.PACKAGE_SHA256
        }
        self.wheel = b"synthetic wheel bytes"
        self.prefix = self.head + "/"

    @staticmethod
    def digest(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def _write_tar(self, *, omit=None, extra=None):
        with tarfile.open(self.bundle, "w:gz") as archive:
            # Actual RC41 contains explicit top-level directory entries.
            # Python tarfile normalizes their names without trailing slashes.
            for dirname in (self.prefix, self.prefix + "archives/"):
                entry = tarfile.TarInfo(dirname)
                entry.type = tarfile.DIRTYPE
                archive.addfile(entry)
            for name, raw in self.package_bytes.items():
                path = (
                    self.prefix + "archives/datarelay-labs-" + name + "-" +
                    self.version + ".tgz"
                )
                if omit == path:
                    continue
                self._regular(archive, path, raw)
            self._regular(archive, self.prefix + gate.WHEEL_NAME, self.wheel)
            for filename in sorted(gate.METADATA):
                self._regular(archive, self.prefix + filename, b"private metadata")
            if extra:
                name, kind = extra
                if kind == "symlink":
                    info = tarfile.TarInfo(name)
                    info.type = tarfile.SYMTYPE
                    info.linkname = "/etc/passwd"
                    archive.addfile(info)
                else:
                    self._regular(archive, name, b"unexpected")
        return self._expected()

    @staticmethod
    def _regular(archive, name, data):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))

    def _expected(self):
        return {
            "source_head": self.head,
            "version": self.version,
            "expected_sha256": gate.digest_file(self.bundle),
            "expected_size": self.bundle.stat().st_size,
            "package_hashes": {
                name: self.digest(raw) for name, raw in self.package_bytes.items()
            },
            "wheel_sha256": self.digest(self.wheel),
        }

    def test_accepts_only_complete_pinned_private_family(self):
        args = self._write_tar()
        before = self.bundle.read_bytes()
        self.assertEqual(gate.verify_bundle(self.bundle, **args), 10)
        self.assertEqual(self.bundle.read_bytes(), before)

    def test_outer_digest_and_length_are_independent_gate(self):
        args = self._write_tar()
        self.bundle.write_bytes(self.bundle.read_bytes() + b"corrupt")
        with self.assertRaisesRegex(gate.CandidateError, "byte length"):
            gate.verify_bundle(self.bundle, **args)
        args["expected_size"] += 7
        with self.assertRaisesRegex(gate.CandidateError, "SHA256"):
            gate.verify_bundle(self.bundle, **args)

    def test_wrong_package_digest_fails_even_with_matching_outer_digest(self):
        args = self._write_tar()
        args["package_hashes"]["foundation"] = self.digest(b"wrong source")
        with self.assertRaisesRegex(gate.CandidateError, "Package or Wheel"):
            gate.verify_bundle(self.bundle, **args)

    def test_wrong_wheel_digest_fails_even_with_matching_outer_digest(self):
        args = self._write_tar()
        args["wheel_sha256"] = self.digest(b"another wheel")
        with self.assertRaisesRegex(gate.CandidateError, "Package or Wheel"):
            gate.verify_bundle(self.bundle, **args)

    def test_missing_package_is_never_accepted(self):
        missing = self.prefix + "archives/datarelay-labs-foundation-" + self.version + ".tgz"
        args = self._write_tar(omit=missing)
        with self.assertRaisesRegex(gate.CandidateError, "missing required"):
            gate.verify_bundle(self.bundle, **args)

    def test_symlink_member_is_rejected_without_extraction(self):
        args = self._write_tar(extra=(self.prefix + "escape", "symlink"))
        with self.assertRaisesRegex(gate.CandidateError, "unsafe member"):
            gate.verify_bundle(self.bundle, **args)

    def test_path_traversal_is_rejected_without_extraction(self):
        args = self._write_tar(extra=(self.prefix + "../escape", "file"))
        with self.assertRaisesRegex(gate.CandidateError, "unsafe member"):
            gate.verify_bundle(self.bundle, **args)

    def test_unpinned_cli_never_accepts_synthetic_archive(self):
        self._write_tar()
        result = subprocess.run(
            [sys.executable, str(TOOL), "--bundle", str(self.bundle)],
            capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PRIVATE_FOUNDATION_RC41=FAIL", result.stdout)

    def test_missing_bundle_fails_without_dangerous_side_effects(self):
        with self.assertRaisesRegex(gate.CandidateError, "regular non-symlink"):
            gate.verify_bundle(Path(self.workspace.name) / "not-supplied.tar.gz")


if __name__ == "__main__":
    unittest.main()
