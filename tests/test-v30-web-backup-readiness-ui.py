#!/usr/bin/env python3
"""PF-12B Link UI: backup tooling is not operational restore proof."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
BUNDLE = (ROOT / "web/dist/app.js").read_text(encoding="utf-8")


class BackupReadinessUiTests(unittest.TestCase):
    def test_system_card_never_promotes_installed_tools_to_backup_readiness(self):
        block = SOURCE.split("function SystemPanel(", 1)[1].split(
            "\nfunction AccessOperations(", 1
        )[0]
        self.assertIn('label="Backup tools"', block)
        self.assertNotIn('label="Backup Ready"', block)
        self.assertIn("backup.create_available&&backup.validate_available", block)
        self.assertIn('"Available":"Unavailable"', block)

    def test_operator_message_explains_missing_recovery_evidence(self):
        block = SOURCE.split("<h3>Backup</h3>", 1)[1].split(
            "<h3>Support Bundle</h3>", 1
        )[0]
        for phrase in (
            "not evidence of a recent verified backup",
            "encrypted-at-rest", "isolated restore drill",
            "read-only", "RESTORE",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)
        self.assertIn("validation?.valid", block)
        self.assertIn('restoreConfirmation!=="RESTORE"', block)

    def test_production_bundle_keeps_explicit_unverified_language(self):
        self.assertIn("Backup tools", BUNDLE)
        self.assertNotIn("Backup Ready", BUNDLE)
        self.assertIn("isolated restore drill", BUNDLE)
        self.assertIn("not evidence of a recent verified backup", BUNDLE)


if __name__ == "__main__":
    unittest.main()
