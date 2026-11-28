#!/usr/bin/env python3
"""Prevent CLI/AI normative docs from drifting away from the v2.4 FINAL Master."""
from __future__ import annotations

import unittest
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "docs" / "DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md"
IA = ROOT / "docs" / "Data Relay Link CLI Information Architecture.md"
PRODUCT = ROOT / "docs" / "PRODUCT_MASTER.md"

REQUIRED_SERVER_MENU = (
    "Managed Hosts",
    "Network Objects",
    "Service Objects",
    "Remote Access",
    "Internet Access",
    "AI Access",
    "System",
)

FORBIDDEN_AS_NORMATIVE_ROOT = (
    "1) Clients",
    "├── 1. Clients",
    "## Canonical Server menu\n\n```text\nClients",
)


class DocConsistencyV24(unittest.TestCase):
    def test_master_exists(self):
        self.assertTrue(MASTER.is_file())

    def test_ia_defers_to_master(self):
        text = IA.read_text(encoding="utf-8")
        self.assertIn("DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md", text)
        self.assertIn("the Master wins", text)
        for item in REQUIRED_SERVER_MENU:
            self.assertIn(item, text)
        for bad in FORBIDDEN_AS_NORMATIVE_ROOT:
            self.assertNotIn(bad, text)
        self.assertIn("AI Identity", text)
        self.assertIn("ConfigurationBundle", text)
        self.assertIn("Cancel produces", text)

    def test_product_master_cli_aligned(self):
        text = PRODUCT.read_text(encoding="utf-8")
        self.assertIn("DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md", text)
        for item in REQUIRED_SERVER_MENU:
            self.assertIn(item, text)
        self.assertIn("Fixed TCP is a Service Object subtype", text)
        self.assertIn("UDP Remote Service is not supported", text)
        self.assertIn("AI Identity", text)

    def test_agent_navigation_matches_master_and_current_menu(self):
        def roots(path, heading):
            text = path.read_text(encoding="utf-8").split(heading, 1)[1]
            block = text.split("```text", 1)[1].split("```", 1)[0]
            return re.findall(r"^[├└]── (\d+)\. (.+)$", block, re.MULTILINE)

        master = roots(MASTER, "# 51. Agent Host local menu")
        self.assertEqual(roots(IA, "## 6. Canonical Agent Host menu"), master)
        import sys
        sys.path.insert(0, str(ROOT / "lib"))
        import frp_cli_catalog as catalog
        actual = [(str(n), label) for n, _action, label, _hint
                  in catalog.guided_menu_entries("client")]
        self.assertEqual(actual, master)

    def test_current_architecture_and_release_schema_do_not_revive_retired_contracts(self):
        architecture = (ROOT / "docs" / "CONTROL_PLANE_ARCHITECTURE.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
        bundle = (ROOT / "docs" / "CONFIGURATION_BUNDLE.md").read_text(encoding="utf-8")
        for token in ("REMOTE_ACCESS_RULEBASE=ORDERED_FIRST_MATCH",
                      "INTERNET_ACCESS_RULEBASE=ORDERED_FIRST_MATCH",
                      "## 20. Intermediate Remote Access rulebase",
                      "## 21. Intermediate Internet Access rulebase"):
            self.assertNotIn(token, architecture)
        self.assertIn("REMOTE_ACCESS_MODE=BLACKLIST_OR_WHITELIST", architecture)
        self.assertIn("INTERNET_ACCESS_MODE=WHITELIST_ONLY", architecture)
        self.assertNotIn("apiVersion: drlink.datarelay.run/v1alpha1", checklist)
        self.assertIn("canonical `configurationBundle` mapping", checklist)
        self.assertNotIn("kind: ConfigurationBundle", bundle)

    def test_changelog_target_matches_current_policy_and_agent_menu(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        target = changelog.split("## 2.4.0 — development target", 1)[1].split("## Historical releases", 1)[0]
        self.assertIn("Internet Access and AI Access start DENY", target)
        self.assertIn("Remote Services / Agent / Configuration / System / Help / Exit", target)
        self.assertNotIn("ConfigurationBundle v1alpha1", target)
        self.assertNotIn("exec=false", target)

    def test_current_docs_have_no_retired_mcp_operator_commands(self):
        # This checks the explicitly approved target design, not runtime implementation.
        # Historical release evidence and third-party source are not current operator manuals.
        pattern = re.compile(
            r"(?m)^\s*(?:sudo drlink\s+|drlink>\s+)?"
            r"(?:set mcp-tls\b|unset mcp-tls\b|system credential "
            r"(?:approve-oauth|deny-oauth|rotate ai-identity|revoke ai-identity|configure ai-identity)\b)"
        )
        for path in sorted((ROOT / "docs").glob("*.md")):
            with self.subTest(path=path.name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))

    def test_current_mcp_nouns_and_navigation_match_implementation(self):
        import sys
        sys.path.insert(0, str(ROOT / "lib"))
        import frp_cli_catalog as catalog
        paths = [ROOT / "README.md", ROOT / "README.ko.md", *(ROOT / "docs").glob("*.md")]
        obsolete = re.compile(r"\bai-mcp\b|AI MCP Setup|Connect or manage AI service|MCP Bridge settings / diagnostics")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIsNone(obsolete.search(text))
                self.assertIsNone(re.search(r"(?m)^\s*set server mcp\s*$", text))
        expected = [entry[1] for entry in catalog.navigation_entries("server.ai") if entry[0] != "back"]
        for path in (MASTER, IA):
            tree = path.read_text(encoding="utf-8").split("├── 6. AI Access\n", 1)[1].split("├── 7. System", 1)[0]
            actual = re.findall(r"(?m)^│   [├└]── (.+)$", tree)
            self.assertEqual(actual, expected, path.name)
        self.assertIn("set mcp-server", catalog.domain_help("mcp-server", "server"))

    def test_restricted_plane_guidance_has_no_blacklist_allow_fallback(self):
        master = MASTER.read_text(encoding="utf-8")
        product = PRODUCT.read_text(encoding="utf-8")
        self.assertNotIn("BLACKLIST evaluation fails closed instead of falling through to unmatched ALLOW", master)
        self.assertNotIn("If a BLACKLIST rule's destination and service match but the observed proxy source", product)
        self.assertNotIn("**Security consequence:** In BLACKLIST mode", product)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        model = readme.split("## Current v2.4 public model", 1)[1].split("## Architecture", 1)[0]
        self.assertIn("Internet Access: WHITELIST only, deny-by-default", model)
        self.assertIn("AI Access: WHITELIST only, deny-by-default", model)
        self.assertNotIn("Initial policy state is No Policy / No Rules with effective access ALLOW", model)


if __name__ == "__main__":
    unittest.main()
