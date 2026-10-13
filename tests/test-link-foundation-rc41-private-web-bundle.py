#!/usr/bin/env python3
"""No-private-package tests for Link's private RC41 Web bundle builder."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "build-private-link-foundation-rc41-web.py"
spec = importlib.util.spec_from_file_location("link_rc41_web_packager", TOOL)
assert spec and spec.loader
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class RC41PrivateWebPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rc41-link-bundle-native-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private_root = self.root / "private"
        self.private_root.mkdir(mode=0o700)
        self.output = self.private_root / "artifacts"
        self.link_head = "a" * 40
        self.pkg = self.private_root / "link-web.tar.gz"
        self.files = {
            "foundation": b"tiny-original-pinned-foundation",
            "system-admin-ui": b"tiny-original-pinned-admin",
        }
        self.hashes = {
            key: hashlib.sha256(value).hexdigest()
            for key, value in self.files.items()
        }

    def _tar(self, *, drop: str | None = None, corrupt: str | None = None):
        with tarfile.open(self.pkg, "w:gz") as tf:
            for short, value in self.files.items():
                if drop == short:
                    continue
                name = (
                    "data-relay-link-web/web/.foundation/packs/datarelay-labs-"
                    + short + "-0.1.0-rc.41.tgz"
                )
                data = value + (b"tampered" if corrupt == short else b"")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            for static in ("index.html", "app.js", "styles.css",
                           "foundation.css", "favicon.svg"):
                name = "data-relay-link-web/web/dist/" + static
                raw = ("ok " + static).encode()
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                tf.addfile(info, io.BytesIO(raw))

    def test_private_output_is_owner_only_and_outside_public_link_git(self):
        self.assertEqual(
            packager.validate_output(self.private_root, self.output),
            self.output,
        )
        self.assertEqual(self.output.stat().st_mode & 0o077, 0)
        with self.assertRaisesRegex(packager.PrivateBundleError, "empty"):
            (self.output / "existing").write_text("occupied")
            packager.validate_output(self.private_root, self.output)
        with self.assertRaisesRegex(packager.PrivateBundleError, "inside"):
            packager.validate_output(self.private_root, self.root / "elsewhere")
        with self.assertRaisesRegex(packager.PrivateBundleError, "absolute"):
            packager.validate_output(self.private_root, Path("relative"))

    def test_all_private_foundation_tarballs_have_correct_embedded_digest(self):
        self._tar()
        with mock.patch.object(packager.stage.gate, "PACKAGE_SHA256", self.hashes):
            self.assertEqual(
                packager._qualify_tar(self.pkg, self.link_head, self.root), 2
            )

    def test_distribution_fails_closed_for_missing_or_tampered_foundation_package(self):
        with mock.patch.object(packager.stage.gate, "PACKAGE_SHA256", self.hashes):
            self._tar(drop="foundation")
            with self.assertRaises(packager.PrivateBundleError):
                packager._qualify_tar(self.pkg, self.link_head, self.root)
            self._tar(corrupt="system-admin-ui")
            with self.assertRaisesRegex(
                packager.PrivateBundleError, "SHA256 mismatch"
            ):
                packager._qualify_tar(self.pkg, self.link_head, self.root)

    def test_public_checkout_dirtiness_prevents_artifact_build(self):
        with mock.patch.object(packager, "_git") as fake_git:
            fake_git.side_effect = [self.link_head, " M web/package.json"]
            with self.assertRaisesRegex(packager.PrivateBundleError, "clean"):
                packager.build_private_candidate(
                    self.private_root, self.private_root,
                    self.private_root / "release-manifest.json",
                    self.private_root, self.output,
                )
        self.assertFalse(self.output.exists())

    def test_native_full_suite_always_includes_private_package_gate(self):
        text = (ROOT / "tests" / "run-all.sh").read_text(encoding="utf-8")
        self.assertEqual(
            text.count("python3 tests/test-link-foundation-rc41-private-web-bundle.py -q"),
            1,
        )

    def test_no_live_host_or_public_release_subprocess_exists(self):
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("DRLINK_WEB_INSTALL_ROOT", source)
        self.assertIn("DRLINK_WEB_INSTALL_SKIP_SYSTEMD", source)
        self.assertNotIn("npm publish", source)
        self.assertNotIn("systemctl ", source)
        self.assertNotIn("sudo ", source)


if __name__ == "__main__":
    unittest.main()
