#!/usr/bin/env python3
"""Synthetic private RC41 dev install selection tests; no private package assets."""
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
TOOL = ROOT / "tools/activate-private-link-foundation-rc41.py"
spec = importlib.util.spec_from_file_location("private_link_foundation_activation", TOOL)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FoundationPrivateDevActivation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="link-rc41-activation-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "private"
        self.root.mkdir(mode=0o700)
        self.candidate = self.root / "dev-installed-verified"
        self.web = self.candidate / "usr/local/share/drlink-web"
        self.web.mkdir(parents=True)
        self.packages = {"foundation": b"strict original package", "ui": b"pinned original UI"}
        self.source = "b" * 40
        self.link_head = "c" * 40
        self.data = {
            "index.html": b"<html><body>Link</body></html>",
            "app.js": b"compiled-app",
            "styles.css": b"body{}",
            "foundation.css": b":root{--color:black}",
            "favicon.svg": b"<svg/>",
        }
        for name, data in self.data.items():
            (self.web / name).write_bytes(data)
        self.artifacts = self.root / "approved-artifact"
        self.artifacts.mkdir(mode=0o700)
        self.pkg = self.artifacts / "source-locked.private.tar.gz"
        self.marker = self.web / "build.json"
        self.receipt = self.artifacts / "private-build-receipt.json"
        self._make_bundle()
        self._write_receipt()

    def _make_bundle(self, missing: str | None = None):
        with tarfile.open(self.pkg, "w:gz") as tf:
            for name, raw in self.data.items():
                self._entry(tf, "data-relay-link-web/web/dist/" + name, raw)
            for name, raw in self.packages.items():
                if name == missing:
                    continue
                self._entry(
                    tf, "data-relay-link-web/web/.foundation/packs/"
                        + "datarelay-labs-" + name + "-0.1.0-rc.41.tgz", raw,
                )

    @staticmethod
    def _entry(tf: tarfile.TarFile, name: str, data: bytes):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    def _write_receipt(self, *, overrides=None):
        digest = sha(self.pkg.read_bytes())
        self.marker.write_text(json.dumps({
            "source_head": self.link_head, "bundle_sha256": digest,
        }))
        doc = {
            "private_unpublished": True,
            "publisher_authenticated": False,
            "live_product_installed": False,
            "user_e2e_pass": False,
            "source_head": self.link_head,
            "foundation_head": self.source,
            "foundation_version": "0.1.0-rc.41",
            "foundation_package_count": len(self.packages),
            "bundle_sha256": digest,
            "bundle_file": self.pkg.name,
            "disposable_install": "PASS",
            "web_suites": "PASS",
        }
        doc.update(overrides or {})
        self.receipt.write_text(json.dumps(doc))

    def _patched(self):
        return (
            mock.patch.object(gate.pin, "SOURCE", self.source),
            mock.patch.object(gate.pin, "PACKAGE_SHA256", {
                k: sha(v) for k, v in self.packages.items()
            }),
        )

    def _verify(self, **kwargs):
        with self._patched()[0], self._patched()[1]:
            return gate.select_development_candidate(
                self.root, self.candidate, self.receipt, **kwargs,
            )

    def test_accepts_qualified_rc41_install_without_public_side_effects(self):
        result = self._verify()
        self.assertEqual(result["link_head"], self.link_head)
        self.assertEqual(result["static_count"], 5)
        self.assertEqual(result["private_package_count"], 2)
        self.assertFalse(result["is_active"])
        self.assertEqual(result["selection"], "READ_ONLY_VERIFIED")
        self.assertFalse((self.root / "dev-installed-current").exists())

    def test_atomic_idempotent_private_rc41_activation(self):
        first = self._verify(activate=True)
        self.assertTrue(first["is_active"])
        active = self.root / "dev-installed-current"
        self.assertTrue(active.is_symlink())
        self.assertEqual(active.resolve(), self.candidate)
        second = self._verify(activate=True, expected_active_name=self.candidate.name)
        self.assertEqual(second["selection"], "APPLIED")
        self.assertEqual(active.resolve(), self.candidate)

    def test_rejects_corrupt_archive_and_never_selects_it(self):
        self.pkg.write_bytes(self.pkg.read_bytes() + b"tamper")
        with self.assertRaisesRegex(gate.SelectionError, "digest mismatch"):
            self._verify(activate=True)
        self.assertFalse((self.root / "dev-installed-current").is_symlink())

    def test_rejects_installed_asset_tampering(self):
        (self.web / "app.js").write_bytes(b"unexpected compiled asset")
        with self.assertRaisesRegex(gate.SelectionError, "file differs"):
            self._verify()

    def test_rejects_missing_rc41_archive_from_package(self):
        self._make_bundle(missing="ui")
        self._write_receipt()
        with self.assertRaisesRegex(gate.SelectionError, "archive is missing"):
            self._verify()

    def test_rejects_fake_publisher_or_wrong_source_provenance(self):
        self._write_receipt(overrides={"publisher_authenticated": True})
        with self.assertRaisesRegex(gate.SelectionError, "not pinned"):
            self._verify()
        self._write_receipt(overrides={"foundation_head": "z" * 40})
        with self.assertRaisesRegex(gate.SelectionError, "not pinned"):
            self._verify()

    def test_rejects_world_accessible_or_outside_private_root(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(gate.SelectionError, "owner-only"):
            self._verify()
        self.root.chmod(0o700)
        with self.assertRaisesRegex(gate.SelectionError, "inside private root"):
            with self._patched()[0], self._patched()[1]:
                gate.verify_development_install(self.root, self.base, self.receipt)

    def test_existing_pointer_to_outside_namespace_is_denied(self):
        pointer = self.root / "dev-installed-current"
        pointer.symlink_to(self.base)
        with self.assertRaisesRegex(gate.SelectionError, "points outside"):
            self._verify(activate=True)

    def test_replacement_requires_exact_previous_active_name(self):
        prior = self.root / "previous-dev-installed"
        prior.mkdir()
        pointer = self.root / "dev-installed-current"
        pointer.symlink_to(prior.name)
        with self.assertRaisesRegex(gate.SelectionError, "Expected current"):
            self._verify(activate=True)
        with self.assertRaisesRegex(gate.SelectionError, "changed"):
            self._verify(activate=True, expected_active_name="someone-else")
        result = self._verify(activate=True, expected_active_name=prior.name)
        self.assertTrue(result["is_active"])
        self.assertEqual(pointer.resolve(), self.candidate)

    def test_native_full_suite_executes_private_activation_contract(self):
        runner = (ROOT / "tests/run-all.sh").read_text(encoding="utf-8")
        self.assertEqual(
            runner.count("python3 tests/test-link-foundation-rc41-activation.py -q"), 1
        )


if __name__ == "__main__":
    unittest.main()
