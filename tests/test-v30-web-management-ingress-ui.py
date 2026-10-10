#!/usr/bin/env python3
"""Source/bundle checks for read-only Link PF-9 System status (not browser E2E)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web/src/main.tsx"
BUNDLE = ROOT / "web/dist/app.js"


class WebIngressStatusUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.bundle = BUNDLE.read_text(encoding="utf-8")

    @classmethod
    def panel(cls):
        return cls.source.split("function ManagementIngressReadOnly(", 1)[1].split(
            "\nfunction SystemPanel(", 1,
        )[0]

    def test_admin_only_component_fetches_authoritative_endpoint(self):
        panel = self.panel()
        self.assertIn('operator.role!=="Admin"', panel)
        self.assertIn('api("/api/v1/admin/management-ingress/status")', panel)
        self.assertIn("return()=>{mounted=false}", panel)
        self.assertIn('data-testid="drlink-management-ingress-status"', panel)

    def test_status_fail_unavailable_and_no_false_ssh_enforcement(self):
        panel = self.panel()
        for label in (
            "Unavailable", "Disabled (not enforced)", "Enabled for Web",
            "SSH host", "Not available", "Read-only", "Policy revision",
        ):
            with self.subTest(label=label):
                self.assertIn(label, panel)
        self.assertIn("report?.web?.status", panel)
        self.assertIn("report?.web?.source_count", panel)
        self.assertIn("report?.web?.trusted_proxy_count", panel)
        self.assertNotIn("management_acl_file", panel)
        self.assertNotIn("source.cidr", panel)
        self.assertNotIn('method:"POST"', panel)

    def test_system_page_integrates_without_new_route_or_new_authority(self):
        marker = 'if(active==="system"&&data)return '
        branch = self.source.split(marker, 1)[1].split(
            'if(active==="objects"', 1,
        )[0]
        self.assertIn("<LinkFoundationAdministration", branch)
        self.assertIn('<ManagementIngressReadOnly operator={operator}/>', branch)
        self.assertIn("<SystemPanel", branch)
        self.assertEqual(self.source.count('<ManagementIngressReadOnly operator={operator}/>'), 1)

    def test_production_bundle_contains_only_read_only_status_ui_contract(self):
        for term in (
            "/api/v1/admin/management-ingress/status",
            "Management access status", "Disabled (not enforced)",
            "SSH host", "Read-only",
        ):
            with self.subTest(term=term):
                self.assertIn(term, self.bundle)


if __name__ == "__main__":
    unittest.main()
