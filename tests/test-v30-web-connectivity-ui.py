#!/usr/bin/env python3
"""Link PF11B native read-only connectivity Web card, not Browser FUE."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
BUNDLE = (ROOT / "web/dist/app.js").read_text(encoding="utf-8")


class ConnectivityUiTests(unittest.TestCase):
    def test_authorized_admin_card_uses_same_origin_product_api(self):
        block = SOURCE.split("function LinkConnectivityReadOnly(", 1)[1].split(
            "\nfunction SystemPanel(", 1,
        )[0]
        self.assertIn('operator.role!=="Admin"', block)
        self.assertIn('api("/api/v1/system/connectivity")', block)
        self.assertIn('return()=>{mounted=false}', block)
        self.assertIn('data-testid="drlink-link-connectivity"', block)
        self.assertNotIn('method:"POST"', block)

    def test_unverified_evidence_is_unknown_not_proclaimed_healthy(self):
        block = SOURCE.split("function LinkConnectivityReadOnly(", 1)[1].split(
            "\nfunction SystemPanel(", 1,
        )[0]
        for phrase in (
            "Connectivity health", "UNKNOWN", "DNS resolution",
            "NTP / clock", "Outbound proxy", "Enterprise CA",
            "TLS certificate", "Evidence unavailable",
            "Clock offset", "read-only", "no network settings",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)
        self.assertIn('report?.findings', block)
        self.assertIn('report?.status', block)
        self.assertNotIn("report?.hostname", block)
        self.assertNotIn("report?.url", block)

    def test_system_page_and_production_bundle_are_additive(self):
        branch = SOURCE.split('if(active==="system"&&data)return ', 1)[1].split(
            'if(active==="objects"', 1,
        )[0]
        self.assertIn("<LinkFoundationAdministration", branch)
        self.assertIn("<ManagementIngressReadOnly", branch)
        self.assertIn('<LinkConnectivityReadOnly operator={operator}/>', branch)
        self.assertIn("<SystemPanel", branch)
        for text in (
            "/api/v1/system/connectivity", "Connectivity health",
            "NTP / clock", "Enterprise CA", "Evidence unavailable",
        ):
            self.assertIn(text, BUNDLE)


if __name__ == "__main__":
    unittest.main()
