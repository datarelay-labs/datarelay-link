#!/usr/bin/env python3
"""Foundation RC41 default: source-only fail-closed consumer/security contract."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / "tools/verify-link-foundation-rc41.py"
spec = importlib.util.spec_from_file_location("link_rc41_pin", PIN_PATH)
assert spec and spec.loader
pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin)
FOUNDATION_NAMES = {"@datarelay-labs/" + key for key in pin.PACKAGE_SHA256}


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class LinkFoundationDefaultRC41(unittest.TestCase):
    def test_all_ten_defaults_are_exact_private_registry_versions(self):
        deps = load("web/package.json")["dependencies"]
        self.assertEqual({key for key in deps if key.startswith("@datarelay-labs/")}, FOUNDATION_NAMES)
        for name in FOUNDATION_NAMES:
            self.assertEqual(deps[name], pin.VERSION)
            self.assertNotIn("file:", deps[name])

    def test_manifest_trust_anchor_and_ten_sha256s(self):
        lock = load("web/foundation.lock.json")
        self.assertEqual(lock["version"], pin.VERSION)
        self.assertEqual(lock["source_head"], pin.SOURCE)
        self.assertEqual(lock["commit"], pin.SOURCE)
        self.assertEqual(lock["registry"]["url"], "https://npm.pkg.github.com")
        self.assertEqual({row["path"]: row["archive_sha256"] for row in lock["packages"]}, pin.PACKAGE_SHA256)
        self.assertEqual({row["name"] for row in lock["packages"]}, FOUNDATION_NAMES)
        for row in lock["packages"]:
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")

    def test_npm_lock_exact_versions_and_tar_integrity(self):
        pkg = load("web/package.json")
        lock = load("web/package-lock.json")
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(lock["packages"][""]["dependencies"], pkg["dependencies"])
        for name in FOUNDATION_NAMES:
            row = lock["packages"]["node_modules/" + name]
            self.assertEqual(row["version"], pin.VERSION)
            self.assertRegex(row["integrity"], r"^sha512-[A-Za-z0-9+/]+={0,2}$")
            self.assertFalse(row.get("resolved", "").startswith("file:"))
            self.assertNotIn("localhost", row.get("resolved", ""))
            self.assertNotIn("_authToken", row.get("resolved", ""))

    def test_explicit_previous_version_rollback_snapshots(self):
        prefix = "web/rollback/pf8.4/"
        old_pkg = load(prefix + "package.json")
        old_lock = load(prefix + "package-lock.json")
        old_pin = load(prefix + "foundation.lock.json")
        self.assertEqual(old_pin["version"], "0.1.0-pf8.4")
        self.assertEqual(old_lock["packages"][""]["dependencies"], old_pkg["dependencies"])
        self.assertEqual({key for key in old_pkg["dependencies"] if key.startswith("@datarelay-labs/")}, FOUNDATION_NAMES)
        for name in FOUNDATION_NAMES:
            self.assertIn("pf8.4.tgz", old_pkg["dependencies"][name])
            self.assertEqual(old_lock["packages"]["node_modules/" + name]["version"], "0.1.0-pf8.4")

    def test_rollback_archive_integrity_against_preserved_public_lock(self):
        import hashlib
        rollback = load("web/rollback/pf8.4/foundation.lock.json")
        self.assertEqual(len(rollback["packages"]), 10)
        for entry in rollback["packages"]:
            archive = ROOT / "web/.foundation/packs" / (
                f'datarelay-labs-{entry["path"]}-{rollback["version"]}.tgz'
            )
            self.assertTrue(archive.is_file(), str(archive))
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),
                             entry["archive_sha256"])

    def test_no_private_archives_or_credentials_in_tracked_rc41_paths(self):
        active = load("web/package.json")
        for name in FOUNDATION_NAMES:
            self.assertNotIn("file:", active["dependencies"][name])
        for path in ("web/package.json", "web/package-lock.json", "web/foundation.lock.json"):
            source = (ROOT / path).read_text()
            self.assertNotIn("_authToken", source)
            self.assertNotIn("FOUNDATION_READ_TOKEN", source)
            self.assertNotIn("0.1.0-rc.41.tgz", source)
        # Private archives may be transiently present on a trusted CI runner;
        # they must never be tracked or distributed from this public repository.
        import subprocess
        for key in pin.PACKAGE_SHA256:
            relative = f"web/.foundation/packs/datarelay-labs-{key}-{pin.VERSION}.tgz"
            tracked = subprocess.run(
                ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            self.assertNotEqual(tracked.returncode, 0, relative)

    def test_foundation_registry_ci_secret_exposure_boundary(self):
        flow = (ROOT / ".github/workflows/foundation-rc41-consumer.yml").read_text()
        self.assertIn("pull_request:", flow)
        self.assertNotIn("pull_request_target", flow)
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", flow)
        self.assertIn("github.event.pull_request.head.ref == 'feat/drl3-ux-saved-admission-pfci'", flow)
        self.assertIn("contents: read", flow)
        self.assertNotIn("packages: write", flow)
        self.assertNotIn("upload-artifact", flow)
        self.assertNotIn("npm publish", flow)
        self.assertEqual(flow.count("secrets.FOUNDATION_READ_TOKEN"), 1)
        self.assertIn("npm ci --ignore-scripts", flow)
        self.assertIn("npm pack", flow)
        self.assertIn("FOUNDATION_RC41_CONSUMER=PASS", flow)
        self.assertIn("umask 077", flow)

    def test_native_suite_registers_contract_once(self):
        runner = (ROOT / "tests/run-all.sh").read_text()
        self.assertEqual(runner.count("python3 tests/test-link-foundation-rc41-default.py -q"), 1)


if __name__ == "__main__":
    unittest.main()
