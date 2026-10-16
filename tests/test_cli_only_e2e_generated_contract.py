#!/usr/bin/env python3
"""Structural regression checks for the independent v2.4.0 CLI-only user E2E.

These tests guard the contract; they are not a substitute for real public-CLI
actions, live traffic, platform evidence, or 3,600-second soak qualification.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "docs/FULL_USER_E2E_SCENARIOS.md"
DERIVED = ROOT / "docs/CLI_ONLY_E2E_SCENARIOS.md"
FCS = ROOT / "docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md"
AUDIT = ROOT / "docs/CLI_ONLY_E2E_BLOCKER_AUDIT.md"
GENERATOR = ROOT / "tools/generate_cli_only_e2e_contract.py"

spec = importlib.util.spec_from_file_location("cli_only_contract_generator", GENERATOR)
assert spec and spec.loader
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class CLIOnlyGeneratedContractRegression(unittest.TestCase):
    def test_render_deterministic_and_parent_digest(self):
        raw = PARENT.read_bytes()
        actual = DERIVED.read_text()
        self.assertEqual(generator.render(), actual)
        self.assertIn(hashlib.sha256(raw).hexdigest(), actual)
        self.assertIn("v2.4.0", actual)
        self.assertIn("includes** AI Access and MCP Bridge", actual)

    def test_exact_original_id_preservation(self):
        parent = PARENT.read_text()
        derived = DERIVED.read_text()
        pattern = re.compile(r"^## ((?:U|O|A|S|C|P|X)-[0-9]{3})\s+[—:-]\s+(.+)$", re.M)
        source_ids = {m.group(1): m.group(2) for m in pattern.finditer(parent)}
        direct_ids = {m.group(1): m.group(2) for m in pattern.finditer(derived)}
        self.assertEqual(len(source_ids), 116)
        self.assertEqual(len(direct_ids), 100)
        self.assertEqual(set(source_ids) - set(direct_ids), generator.EXCLUDED)
        self.assertTrue(generator.MIXED.issubset(direct_ids))
        for sid, heading in direct_ids.items():
            if sid != "A-016":
                self.assertEqual(heading, source_ids[sid], sid)
        self.assertIn("Direct CLI workflow", direct_ids["A-016"])

    def test_no_ai_or_mcp_user_operations_leak(self):
        doc = DERIVED.read_text()
        scenarios = doc[doc.index("# 7. User scenarios"):doc.index("# 13. Platform matrix")]
        matrix = doc[doc.index("# 13. Platform matrix"):doc.index("# 15. CLI-only provenance")]
        forbidden = re.compile(
            r"\b(?:AI-assisted|AI Access|AI Identity|AI Adviser|AI mirror|"
            r"ChatGPT|Plugin|MCP|OAuth)\b", re.I
        )
        self.assertNotRegex(scenarios, forbidden)
        self.assertNotRegex(matrix, forbidden)
        self.assertNotRegex(matrix, re.compile(r"(?m)^(?:show|set|unset|test) (?:ai-|mcp-tls|permission-)"))
        for public_command in (
            "show remote-access", "show internet-access", "set remote-service",
            "system backup validate", "system restore", "system update product",
            "test internet-access", "system uninstall", "Tab completion",
            "ssh / scp / sftp", "curl", "wget", "git", "apt",
        ):
            self.assertIn(public_command, matrix)

    def test_no_shortcut_for_real_functional_or_performance(self):
        doc = DERIVED.read_text()
        for requirement in (
            "SSH", "SCP", "HTTPS", "Custom TCP", "Zero-Touch",
            "C-001", "C-015", "P-013", "P-019", "P-024",
            "WARMUP=60s", "STEADY_STATE_EACH_CASE=300s",
            "SOAK=3600s", "MEASURED_NOT_QUALIFIED",
            "EXCLUDED_AI_MCP", "EXECUTABLE_SCOPE_COMPLETE",
            "ALL_APPLICABLE_CLI_E2E_PASS", "BLOCKED_PLATFORM_DENIAL",
            "ACTUAL", "source-head",
        ):
            self.assertIn(requirement.lower(), doc.lower(), requirement)
        self.assertIn("8h/24h is optional until explicitly selected", doc)
        self.assertIn("There is no global LAB_GO", doc)
        self.assertIn("current denial remains binding", doc)

    def test_fcs_scopes_and_product_inclusion_still_separate(self):
        fcs = FCS.read_text()
        parent = PARENT.read_text()
        master = (ROOT / "docs/PRODUCT_MASTER.md").read_text()
        version = (ROOT / "docs/VERSION_POLICY.md").read_text()
        self.assertIn("FCS_CLI_ONLY", fcs)
        self.assertIn("FCS_FULL", fcs)
        self.assertIn("13/13", fcs)
        self.assertIn("FCS-007/008", fcs)
        self.assertIn("EXCLUDED_AI_MCP", fcs)
        self.assertIn("MCP Bridge", master)
        self.assertIn("MCP included in final 2.4.0 target", version)
        self.assertIn("MANDATORY for v2.4.0", parent)
        self.assertIn("CLI_ONLY_E2E_SCENARIOS.md", parent)
        self.assertTrue(AUDIT.is_file())
        for blocker_id in range(1, 29):
            self.assertRegex(AUDIT.read_text(), rf"\bB{blocker_id:02d}\b")


if __name__ == "__main__":
    unittest.main()
