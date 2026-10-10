#!/usr/bin/env python3
"""PF-12A Link admin-only count-only history UI, deterministic source/bundle contract."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
BUNDLE = (ROOT / "web/dist/app.js").read_text(encoding="utf-8")


class ConfigHistoryUiTests(unittest.TestCase):
    def panel(self):
        return SOURCE.split("function LinkConfigHistoryReadOnly(", 1)[1].split(
            "\nfunction SystemPanel(", 1,
        )[0]

    def test_admin_only_and_safe_same_origin_history_endpoint(self):
        card = self.panel()
        self.assertIn('operator.role!=="Admin"', card)
        self.assertIn('/api/v1/system/configuration/history?', card)
        self.assertIn('data-testid="drlink-config-history-counts"', card)
        self.assertIn("Compare revisions", card)
        self.assertNotIn('method:"POST"', card)
        self.assertNotIn("configurationBundle", card)
        self.assertNotIn("rollbackApply", card)

    def test_no_false_full_semantic_equality_or_rollback_claim(self):
        card = self.panel()
        for phrase in (
            "Count-only", "read-only", "not a full semantic diff",
            "No settings are changed", "Rollback blocked",
            "No actual rollback", "Compare revisions",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, card)
        self.assertIn("rollback_preview?.blockers", card)
        self.assertIn("report?.changes", card)
        self.assertIn('setReport(null)', card)

    def test_existing_system_navigation_preserved_and_compiled(self):
        branch = SOURCE.split('if(active==="system"&&data)return ', 1)[1].split(
            'if(active==="objects"', 1,
        )[0]
        self.assertIn("<LinkFoundationAdministration", branch)
        self.assertIn("<ManagementIngressReadOnly", branch)
        self.assertIn('<LinkConfigHistoryReadOnly operator={operator}/>', branch)
        self.assertIn("<SystemPanel", branch)
        for phrase in (
            "/api/v1/system/configuration/history?", "Compare revisions",
            "Rollback blocked", "not a full semantic diff",
        ):
            self.assertIn(phrase, BUNDLE)


if __name__ == "__main__":
    unittest.main()
