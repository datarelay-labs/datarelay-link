#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "drlink_build_web_bundle", ROOT / "scripts/build-web-bundle.py"
)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)

class V30WebBundleTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_matches_declared_files(self):
        tmp = Path(tempfile.mkdtemp(prefix="drlink-web-bundle-"))
        first = tmp / "one.tar.gz"
        second = tmp / "two.tar.gz"
        MOD.build(first)
        MOD.build(second)
        self.assertEqual(
            hashlib.sha256(first.read_bytes()).hexdigest(),
            hashlib.sha256(second.read_bytes()).hexdigest(),
        )
        with tarfile.open(first, "r:gz") as tf:
            names = set(tf.getnames())
        self.assertEqual(names, {"data-relay-link-web/" + name for name in MOD.FILES})

    def test_vendored_foundation_archive_digest_and_reject_tampering(self):
        with tempfile.TemporaryDirectory(prefix="drlink-foundation-verify-") as folder:
            root = Path(folder)
            bundles = root / "web/.foundation/packs"
            bundles.mkdir(parents=True)
            lock_src = ROOT / "web/foundation.lock.json"
            (root / "web/foundation.lock.json").write_bytes(lock_src.read_bytes())
            lock = json.loads(lock_src.read_text())
            for entry in lock["packages"]:
                path = "datarelay-labs-%s-%s.tgz" % (entry["path"], lock["version"])
                shutil.copyfile(ROOT / "web/.foundation/packs" / path, bundles / path)
            paths = MOD.foundation_pack_sources(root)
            self.assertEqual(len(paths), 10)
            self.assertEqual(
                len({entry["path"] for entry in lock["packages"]}), 10,
                "the lock must identify ten distinct Foundation packages",
            )
            # Every independently pinned package must fail closed if even one
            # archive byte changes. Do not test tokens alone and extrapolate.
            for entry in lock["packages"]:
                name = entry["path"]
                archive = bundles / (
                    "datarelay-labs-%s-%s.tgz" % (name, lock["version"])
                )
                original = archive.read_bytes()
                with self.subTest(tampered_package=name):
                    try:
                        archive.write_bytes(original + b"tamper")
                        with self.assertRaisesRegex(
                            SystemExit, "foundation-archive-sha-mismatch:" + name
                        ):
                            MOD.foundation_pack_sources(root)
                    finally:
                        archive.write_bytes(original)
                with self.subTest(missing_digest=name):
                    package = next(
                        row for row in lock["packages"] if row["path"] == name
                    )
                    sha256 = package.pop("archive_sha256")
                    try:
                        (root / "web/foundation.lock.json").write_text(
                            json.dumps(lock), encoding="utf-8"
                        )
                        with self.assertRaisesRegex(
                            SystemExit, "invalid Foundation package entry"
                        ):
                            MOD.foundation_pack_sources(root)
                    finally:
                        package["archive_sha256"] = sha256
                        (root / "web/foundation.lock.json").write_text(
                            json.dumps(lock), encoding="utf-8"
                        )

    def test_vendored_foundation_symlink_cannot_pass_digest_validation(self):
        # Matching hashes must not make an out-of-tree symlink an approved
        # vendored release archive. Packaging would otherwise copy a link.
        with tempfile.TemporaryDirectory(prefix="drlink-foundation-link-") as folder:
            root = Path(folder)
            packs = root / "web/.foundation/packs"
            packs.mkdir(parents=True)
            lock_src = ROOT / "web/foundation.lock.json"
            (root / "web/foundation.lock.json").write_bytes(lock_src.read_bytes())
            lock = json.loads(lock_src.read_text())
            for entry in lock["packages"]:
                name = "datarelay-labs-%s-%s.tgz" % (
                    entry["path"], lock["version"]
                )
                original = ROOT / "web/.foundation/packs" / name
                current = packs / name
                if entry["path"] == "tokens":
                    current.symlink_to(original)
                else:
                    shutil.copyfile(original, current)
            with self.assertRaisesRegex(
                SystemExit, "foundation-archive-unsafe:tokens"
            ):
                MOD.foundation_pack_sources(root)

    def test_foundation_external_hardlink_and_symlinked_parent_fail_closed(self):
        lock_src = ROOT / "web/foundation.lock.json"
        for variant in ("external-hardlink", "symlinked-parent"):
            with self.subTest(variant=variant):
                with tempfile.TemporaryDirectory(
                    prefix="drlink-foundation-indirection-"
                ) as folder:
                    root = Path(folder)
                    foundation = root / "web/.foundation"
                    foundation.mkdir(parents=True)
                    (root / "web/foundation.lock.json").write_bytes(
                        lock_src.read_bytes()
                    )
                    lock = json.loads(lock_src.read_text())
                    packs = foundation / "packs"
                    if variant == "symlinked-parent":
                        real_packs = root / "external-packs"
                        real_packs.mkdir()
                        packs.symlink_to(real_packs, target_is_directory=True)
                    else:
                        packs.mkdir()
                    for entry in lock["packages"]:
                        name = "datarelay-labs-%s-%s.tgz" % (
                            entry["path"], lock["version"]
                        )
                        original = ROOT / "web/.foundation/packs" / name
                        current = packs / name
                        if variant == "external-hardlink" and entry["path"] == "tokens":
                            outside = root / "outside-package.tgz"
                            shutil.copyfile(original, outside)
                            os.link(outside, current)
                        else:
                            shutil.copyfile(original, current)
                    with self.assertRaisesRegex(
                        SystemExit, "foundation-archive-unsafe:tokens"
                    ):
                        MOD.foundation_pack_sources(root)

    def test_bundle_contains_compiled_static_assets_only_for_runtime_ui(self):
        tmp = Path(tempfile.mkdtemp(prefix="drlink-web-static-"))
        bundle = MOD.build(tmp / "web.tar.gz")
        with tarfile.open(bundle, "r:gz") as tf:
            names = set(tf.getnames())
        self.assertIn("data-relay-link-web/web/dist/index.html", names)
        self.assertIn("data-relay-link-web/web/dist/app.js", names)
        self.assertIn("data-relay-link-web/web/dist/styles.css", names)
        self.assertIn("data-relay-link-web/web/dist/foundation.css", names)
        self.assertIn("data-relay-link-web/web/foundation.lock.json", names)
        # Rebuilding the offline Web UI must not lose its Link-owned
        # Administration projection source after extraction.
        self.assertIn("data-relay-link-web/web/src/foundation-administration.ts", names)
        self.assertIn("data-relay-link-web/web/.foundation/packs/datarelay-labs-foundation-0.1.0-pf5b.1.tgz", names)
        self.assertNotIn("data-relay-link-web/var/lib/drlink/drlink.db", names)

if __name__ == "__main__":
    unittest.main()
