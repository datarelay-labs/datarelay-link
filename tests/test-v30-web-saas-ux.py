#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web/dist/styles.css").read_text(encoding="utf-8")
UX = (ROOT / "docs/WEB_SAAS_UX_SYSTEM.md").read_text(encoding="utf-8")


class V30WebSaasUxContractTests(unittest.TestCase):
    def test_dr_control_semantic_token_parity_is_frozen(self):
        required = {
            "--dr-font-family-ui": 'Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
            "--dr-layout-sidebar-expanded": "260px",
            "--dr-layout-sidebar-collapsed": "57px",
            "--dr-layout-content-max": "1440px",
            "--dr-radius-control": "8px",
            "--dr-radius-card": "8px",
            "--dr-brand-mark": "#00d084",
            "--dr-brand-relay": "#007e4f",
            "--dr-surface-page": "oklch(98.75% 0 0)",
            "--dr-surface-panel": "#fff",
            "--dr-action-primary": "oklch(54.6% .245 262.881)",
            "--dr-status-success": "#047857",
            "--dr-status-warning": "#92400e",
            "--dr-status-critical": "#b42318",
            "--dr-focus-ring": "#1473e6",
        }
        compact = CSS.replace(" ", "")
        for key, value in required.items():
            self.assertIn("%s:%s" % (key, value.replace(" ", "")), compact)
        for dark in (
            "--dr-surface-page:oklch(10% 0 0)",
            "--dr-surface-panel:oklch(17% 0 0)",
            "--dr-status-success:#34d399",
            "--dr-status-warning:#f59e0b",
            "--dr-status-critical:#f87171",
        ):
            self.assertIn(dark.replace(" ", ""), compact)
        for global_marker in (
            "text-rendering:optimizeLegibility",
            "scrollbar-width:thin",
            "::selection",
            "box-shadow:0 1px 2px rgba(0,0,0,.05)",
        ):
            self.assertIn(global_marker, CSS)

    def test_navigation_is_bounded_and_utilities_are_contextual(self):
        block = re.search(r"const navGroups=\[(.*?)\] as const;", SOURCE, re.S)
        self.assertIsNotNone(block)
        text = block.group(1)
        groups = re.findall(r'id:"([^"]+)",label:"([^"]+)"', text)
        self.assertEqual(
            groups,
            [
                ("infrastructure", "Infrastructure"),
                ("access", "Access Control"),
                ("operations", "Operations"),
                ("observability", "Observability"),
                ("administration", "Administration"),
            ],
        )
        for utility in ('["search","Search"]', '["views","Saved Views"]', '["doctor","Doctor"]', '["enrollments","Connect Agent"]', '["drafts","Draft Workspace"]'):
            self.assertNotIn(utility, text)
        for contextual in (
            'Search hosts, services, policies, identities',
            'Saved Views',
            'Connect Agent',
            'Draft change',
            'Troubleshoot',
        ):
            self.assertIn(contextual, SOURCE)

    def test_shell_command_center_and_resource_workspaces_exist(self):
        for marker in (
            "drlink_web_sidebar_collapsed",
            "drlink_web_theme",
            "dr-topbar",
            "dr-command-palette",
            "Command Center",
            "Recent Activity",
            "Recent Changes",
            "dr-detail-drawer",
            "Access Workspace",
            "Policy Simulator",
            "Filter hosts",
            "Filter services",
            "Filter objects and groups",
            "Filter policies",
            "Skip to content",
            "drlink-main-content",
            "dr-page-skeleton",
            "dr-sidebar-signout",
        ):
            self.assertTrue(marker in SOURCE or marker in CSS, marker)

    def test_owner_review_pages_use_spacious_structured_workspaces(self):
        for source_marker in (
            "dr-fleet-card",
            "Target scope",
            "Group membership",
            "dr-audit-filter-grid",
            "Audit Retention",
            "HealthWorkspace",
            "Advanced · raw health payload",
            "temporary setup key is not active until you verify",
            "/api/v1/auth/mfa/enroll/cancel",
            "Show key",
            "Recovery codes are issued only after verification succeeds",
        ):
            self.assertIn(source_marker, SOURCE)
        for style_marker in (
            ".dr-form-grid.two",
            ".dr-audit-filter-grid",
            ".dr-health-summary",
            ".dr-mfa-secret-row",
        ):
            self.assertIn(style_marker, CSS)

    def test_responsive_and_keyboard_contract_is_present(self):
        for marker in (
            "@media(max-width:850px)",
            "@media(max-width:560px)",
            ".dr-skip-link",
            ".dr-detail-drawer:focus-visible",
        ):
            self.assertIn(marker, CSS)
        self.assertIn('(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"', SOURCE)
        self.assertIn('if(e.key==="Escape")onClose()', SOURCE)
        self.assertIn('tabIndex={-1} autoFocus', SOURCE)

    def test_normative_ux_doc_binds_control_reference_and_competitive_sources(self):
        self.assertIn("DRL3-7A", UX)
        self.assertIn("41a561b769fb589f081e84ec5014de6f48881985", UX)
        self.assertIn("frontend/src/foundation-semantic-tokens.css", UX)
        self.assertIn("frontend/src/components/layout/sidebar.tsx", UX)
        self.assertIn("frontend/src/components/layout/top-header.tsx", UX)
        for product in (
            "Cloudflare One",
            "Palo Alto Strata Cloud Manager",
            "NetBird",
            "Twingate",
            "Tailscale",
            "Teleport",
            "HashiCorp Boundary",
            "Netskope",
            "NordLayer",
        ):
            self.assertIn(product, UX)


if __name__ == "__main__":
    unittest.main()
