#!/usr/bin/env python3
"""Unit-only private RC41 Link Web staging tests; no genuine private archive."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "stage-link-foundation-rc41.py"
spec = importlib.util.spec_from_file_location("drlink_rc41_staging", TOOL)
assert spec and spec.loader
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class RC41OfflineStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-rc41-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.fake_repo = self.base / "fake-link"
        self.web = self.fake_repo / "web"
        self.web.mkdir(parents=True)
        self.pkg = {
            "name": "data-relay-link-web",
            "dependencies": {
                "@datarelay-labs/foundation": "file:.foundation/packs/old-foundation.tgz",
                "@datarelay-labs/ui": "file:.foundation/packs/old-ui.tgz",
                "react": "19.3.0",
            },
            "scripts": {"build": "echo ok"},
        }
        (self.web / "package.json").write_text(json.dumps(self.pkg), encoding="utf-8")
        (self.web / "package-lock.json").write_text("old lock", encoding="utf-8")
        (self.web / "foundation.lock.json").write_text("old pinned foundation", encoding="utf-8")
        (self.web / "src").mkdir()
        (self.web / "src" / "main.tsx").write_text("src", encoding="utf-8")
        (self.web / ".foundation" / "packs").mkdir(parents=True)
        (self.web / ".foundation" / "packs" / "old-private.tgz").write_bytes(b"old")
        (self.web / "node_modules").mkdir()
        (self.web / "node_modules" / "old").write_text("old")
        (self.web / "dist").mkdir()
        (self.web / "dist" / "app.js").write_text("compiled")
        self.secret_root = self.base / "private"
        self.secret_root.mkdir(mode=0o700)
        self.source = "b" * 40
        self.raw_packages = {"foundation": b"rc41-foundation", "ui": b"rc41-ui"}
        self.hashes = {name: hashlib.sha256(raw).hexdigest()
                       for name, raw in self.raw_packages.items()}
        self.bundle = self.base / "candidate.tar.gz"

    def _create_synthetic_archive(self):
        manifest = {
            "schema_version": 1,
            "source_head": self.source,
            "commit": self.source,
            "version": "0.1.0-rc.41",
            "packages": [{
                "name": "@datarelay-labs/" + name,
                "archive_sha256": self.hashes[name],
            } for name in self.raw_packages],
        }
        with tarfile.open(self.bundle, "w:gz") as tar:
            for name, raw in self.raw_packages.items():
                self._entry(tar, self.source + "/archives/datarelay-labs-"
                            + name + "-0.1.0-rc.41.tgz", raw)
            self._entry(tar, self.source + "/foundation.lock.json",
                        json.dumps(manifest).encode())

    @staticmethod
    def _entry(tar, name, raw):
        entry = tarfile.TarInfo(name)
        entry.size = len(raw)
        tar.addfile(entry, io.BytesIO(raw))

    def _patch_literal_pins(self):
        return (
            mock.patch.object(stage.gate, "SOURCE", self.source),
            mock.patch.object(stage.gate, "PACKAGE_SHA256", self.hashes),
            mock.patch.object(stage, "REPO", self.fake_repo),
        )

    def test_dependency_projection_is_rc41_only_and_preserves_react(self):
        with mock.patch.object(stage.gate, "PACKAGE_SHA256", self.hashes):
            updated = stage.pinned_web_dependencies(self.pkg)
        self.assertEqual(updated["dependencies"]["react"], "19.3.0")
        self.assertEqual(
            updated["dependencies"]["@datarelay-labs/foundation"],
            "file:.foundation/packs/datarelay-labs-foundation-0.1.0-rc.41.tgz",
        )
        self.assertEqual(
            self.pkg["dependencies"]["@datarelay-labs/foundation"],
            "file:.foundation/packs/old-foundation.tgz",
        )

    def test_disallows_nonfile_and_extra_public_dependencies(self):
        with mock.patch.object(stage.gate, "PACKAGE_SHA256", self.hashes):
            altered = json.loads(json.dumps(self.pkg))
            altered["dependencies"]["@datarelay-labs/ui"] = "^0.1.0"
            with self.assertRaises(stage.StageError):
                stage.pinned_web_dependencies(altered)
            altered["dependencies"]["@datarelay-labs/ui"] = "file:original.tgz"
            altered["dependencies"]["@datarelay-labs/extraneous"] = "1.0"
            with self.assertRaises(stage.StageError):
                stage.pinned_web_dependencies(altered)

    def test_manifest_must_match_exact_original_source_and_archive_digests(self):
        locked = {
            "schema_version": 1,
            "source_head": self.source,
            "commit": self.source,
            "version": "0.1.0-rc.41",
            "packages": [{
                "name": "@datarelay-labs/" + name,
                "archive_sha256": sha,
            } for name, sha in self.hashes.items()],
        }
        with mock.patch.object(stage.gate, "SOURCE", self.source), mock.patch.object(
                stage.gate, "PACKAGE_SHA256", self.hashes):
            self.assertEqual(stage.source_head_from_lock(locked), self.source)
            locked["packages"][0]["archive_sha256"] = "0" * 64
            with self.assertRaises(stage.StageError):
                stage.source_head_from_lock(locked)
            locked["packages"][0]["archive_sha256"] = next(iter(self.hashes.values()))
            locked["source_head"] = "a" * 40
            with self.assertRaises(stage.StageError):
                stage.source_head_from_lock(locked)

    def test_private_root_must_not_be_repository_or_world_readable(self):
        with mock.patch.object(stage, "REPO", self.fake_repo):
            self.assertEqual(stage.private_scratch_root(self.secret_root), self.secret_root)
            with self.assertRaises(stage.StageError):
                stage.private_scratch_root(self.web)
            with self.assertRaises(stage.StageError):
                stage.private_scratch_root(self.base)
            with self.assertRaises(stage.StageError):
                stage.private_scratch_root(Path("relative-path"))

    def test_copy_does_not_reuse_pf8_archives_lock_or_build_outputs(self):
        staged = self.base / "isolated-web"
        stage.prepare_copy(self.web, staged)
        self.assertTrue((staged / "package.json").is_file())
        self.assertTrue((staged / "src" / "main.tsx").is_file())
        for old in (".foundation", "node_modules", "dist", "package-lock.json"):
            self.assertFalse((staged / old).exists(), old)
        self.assertTrue((self.web / ".foundation" / "packs" / "old-private.tgz").is_file())

    def test_verified_staging_executes_offline_only_and_preserves_public_checkout(self):
        self._create_synthetic_archive()
        before = {name: (self.web / name).read_bytes()
                  for name in ("package.json", "package-lock.json", "foundation.lock.json")}
        commands = []
        def fake_npm(command, **kwargs):
            commands.append(command)
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["env"]["npm_config_offline"], "true")
            self.assertTrue(str(kwargs["cwd"]).startswith(str(self.secret_root)))
            if command[1] == "install":
                self.assertIn("--offline", command)
                self.assertIn("--ignore-scripts", command)
                self.assertIn("--package-lock=false", command)
                for name in self.hashes:
                    dest = (Path(kwargs["cwd"]) / "node_modules" /
                            "@datarelay-labs" / name)
                    dest.mkdir(parents=True)
                    (dest / "package.json").write_text(json.dumps({
                        "name": "@datarelay-labs/" + name,
                        "version": "0.1.0-rc.41",
                    }), encoding="utf-8")
            return None
        with self._patch_literal_pins()[0], self._patch_literal_pins()[1], self._patch_literal_pins()[2], mock.patch.object(stage.gate, "verify_bundle", return_value=2) as verifier:
            stage.run_private_compatibility(self.bundle, self.secret_root, self.web, run=fake_npm)
            verifier.assert_called_once_with(self.bundle)
        self.assertEqual([x[1] for x in commands], ["install", "run", "run", "run"])
        self.assertEqual([x[-1] for x in commands[1:]], ["build", "test:administration", "test:journey"])
        for name, content in before.items():
            self.assertEqual((self.web / name).read_bytes(), content)
        self.assertEqual(list(self.secret_root.iterdir()), [])

    def test_native_ci_runs_private_staging_contract_without_private_packages(self):
        source = (REPO / "tests" / "run-all.sh").read_text(encoding="utf-8")
        self.assertEqual(source.count("python3 tests/test-link-foundation-rc41-staging.py -q"), 1)

    def test_actual_entrypoint_rejects_absent_private_bundle_without_writing(self):
        import subprocess
        result = subprocess.run([
            sys.executable, str(TOOL),
            "--bundle", str(self.base / "not-found.tar.gz"),
            "--private-root", str(self.secret_root),
        ], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FOUNDATION_RC41_LINK_COMPATIBILITY=BLOCKED", result.stdout)
        self.assertEqual(list(self.secret_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
