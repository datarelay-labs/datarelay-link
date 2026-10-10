#!/usr/bin/env python3
"""PF-12C native consumer: actual offline bytes, no installer/host effects."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_offline_upgrade_preflight import OfflinePreflightError, preflight_offline_release


class OfflineReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-pf12c-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "etc/drlink").mkdir(parents=True)
        (self.root / "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\nSOURCE_HEAD=" + "a" * 40 + "\n"
            "RELEASE_CHANNEL=development\n", encoding="utf-8"
        )
        self.stage = self.root / "staging"
        self.stage.mkdir()
        self.artifact = self.stage / "upgrade.tar.gz"
        self.artifact.write_bytes(b"DRLINK SYNTHETIC OFFLINE RELEASE\x00" * 121)
        self.manifest = self.stage / "manifest.json"
        self.payload = {
            "schema_version": 1,
            "product_ref": "drlink",
            "release_ref": "drlink-3.1.0",
            "version": "3.1.0",
            "kind": "product_release",
            "artifact_sha256": hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
            "artifact_bytes": self.artifact.stat().st_size,
            "publisher_key_ref": "drlink-release-2026",
        }
        self.store_manifest()

    def store_manifest(self):
        self.manifest.write_text(
            json.dumps(self.payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        self.manifest_hash = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def qualify(self, *, artifact=None, manifest=None, sha=None):
        return preflight_offline_release(
            root=self.root,
            artifact_path=artifact or self.artifact,
            manifest_path=manifest or self.manifest,
            expected_manifest_sha256=sha or self.manifest_hash,
        )

    def test_real_bytes_match_but_signature_and_recovery_never_claim_ready(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        result = self.qualify()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["installed_version"], "3.0.0")
        self.assertEqual(result["target_version"], "3.1.0")
        self.assertEqual(result["product_ref"], "drlink")
        self.assertTrue(result["artifact_bytes_verified"])
        self.assertTrue(result["manifest_bytes_verified"])
        self.assertFalse(result["publisher_signature_verified"])
        self.assertFalse(result["publisher_trust_verified"])
        self.assertFalse(result["may_submit_to_installer"])
        self.assertFalse(result["upgrade_authorized"])
        self.assertIn("signature_unverified", result["blockers"])
        self.assertIn("backup_unverified", result["blockers"])
        self.assertIn("offline_recovery_required", result["blockers"])
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_actual_archive_tamper_fails_without_leaking_bytes(self):
        self.artifact.write_bytes(b"malicious" + self.artifact.read_bytes()[9:])
        result = self.qualify()
        self.assertFalse(result["artifact_bytes_verified"])
        self.assertIn("artifact_integrity_missing", result["blockers"])
        self.assertNotIn("malicious", json.dumps(result))

    def test_manifest_hash_must_be_pinned_out_of_band(self):
        with self.assertRaisesRegex(OfflinePreflightError, "manifest_integrity"):
            self.qualify(sha="0" * 64)

    def test_rejects_forged_verification_flags_and_duplicate_json_keys(self):
        self.payload["publisher_trust_verified"] = True
        self.store_manifest()
        with self.assertRaises(OfflinePreflightError):
            self.qualify()
        self.manifest.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        h = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with self.assertRaises(OfflinePreflightError):
            self.qualify(sha=h)

    def test_rejects_symlink_file_and_parent_components(self):
        alias = self.stage / "alias.tgz"
        alias.symlink_to(self.artifact)
        with self.assertRaises(OfflinePreflightError):
            self.qualify(artifact=alias)
        alias_dir = self.root / "symlinked-staging"
        alias_dir.symlink_to(self.stage, target_is_directory=True)
        with self.assertRaises(OfflinePreflightError):
            self.qualify(artifact=alias_dir / self.artifact.name)

    def test_rejects_hardlinks_and_oversized_sparse_file(self):
        link = self.stage / "second-link"
        os.link(self.artifact, link)
        with self.assertRaises(OfflinePreflightError):
            self.qualify()
        link.unlink()
        with self.artifact.open("wb") as fp:
            fp.truncate(2 * 1024 * 1024 * 1024 + 1)
        with self.assertRaises(OfflinePreflightError):
            self.qualify()

    def test_rejects_unknown_installed_identity_and_nonrelease_artifact(self):
        (self.root / "etc/drlink/version").write_text("PROJECT_VERSION=unknown\n")
        with self.assertRaises(OfflinePreflightError):
            self.qualify()
        (self.root / "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\nSOURCE_HEAD=" + "a" * 40 + "\n"
        )
        self.payload["kind"] = "platform_os_upgrade"
        self.store_manifest()
        result = self.qualify()
        self.assertIn("wrong_kind", result["blockers"])
        self.assertFalse(result["upgrade_authorized"])

    def test_cli_reports_only_blocked_metadata_and_does_not_mutate(self):
        command = [
            sys.executable, str(ROOT / "tools/drlink-offline-upgrade-preflight"),
            "--root", str(self.root), "--artifact", str(self.artifact),
            "--manifest", str(self.manifest),
            "--manifest-sha256", self.manifest_hash,
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["upgrade_authorized"])
        self.assertNotIn(str(self.stage), result.stdout)
        self.assertFalse((self.root / "var/lib/drlink").exists())


if __name__ == "__main__":
    unittest.main()
