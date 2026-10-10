#!/usr/bin/env python3
"""PF-12 read-only, no false recovery-ready claim Web UI contract."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
BUNDLE = (ROOT / "web/dist/app.js").read_text(encoding="utf-8")


class BackupByteUiTests(unittest.TestCase):
    def test_admin_only_observation_without_authoritative_restore(self):
        panel = SOURCE.split("function SystemPanel(", 1)[1].split(
            "\nfunction AccessOperations(", 1,
        )[0]
        self.assertIn('async function inspectBackupIntegrity()', panel)
        self.assertIn('api("/api/v1/system/backup/integrity"', panel)
        self.assertIn('operator.role==="Admin"&&<button', panel)
        self.assertIn('onClick={inspectBackupIntegrity}', panel)
        self.assertIn('Observe archive SHA256', panel)
        self.assertIn('disabled={!backupPath}', panel)
        self.assertIn('setIntegrity(null)', panel)
        self.assertIn('integrity&&<pre', panel)

    def test_no_synthetic_hash_or_restoration_authority_claim(self):
        section = SOURCE.split("<h3>Backup</h3>", 1)[1].split(
            "<h3>Support Bundle</h3>", 1,
        )[0]
        for label in (
            "not publisher authentication",
            "not proof of encrypted backup",
            "not proof of an isolated restore drill",
            "maximum 128 MiB",
        ):
            with self.subTest(label=label):
                self.assertIn(label, section)
        self.assertNotIn("setValidation(integrity)", section)
        self.assertIn('validation?.valid', section)
        self.assertIn('restoreConfirmation!=="RESTORE"', section)

    def test_offline_production_bundle_has_observation_api_and_truthful_status(self):
        self.assertIn("/api/v1/system/backup/integrity", BUNDLE)
        self.assertIn("Observe archive SHA256", BUNDLE)
        self.assertIn("not publisher authentication", BUNDLE)
        self.assertIn("not proof of an isolated restore drill", BUNDLE)


if __name__ == "__main__":
    unittest.main()
