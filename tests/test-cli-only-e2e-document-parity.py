#!/usr/bin/env python3
"""Regression for direct-only DRLink 2.4.0 canonical E2E derivation and scope."""
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/FULL_USER_E2E_SCENARIOS.md"
CLI = ROOT / "docs/CLI_ONLY_E2E_SCENARIOS.md"
FCS = ROOT / "docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md"
MASTER = ROOT / "docs/PRODUCT_MASTER.md"
GEN = ROOT / "tools/generate_cli_only_e2e_contract.py"
PATTERN = re.compile(r"^## ((?:U|O|A|S|C|P|X)-\d{3})\s+[—:-]", re.M)
EXCLUDED = {"U-007","U-011","O-013","O-014","A-006","C-006","P-011",
            "X-001","X-002","X-003","X-004","X-005","X-007","X-008","X-009","X-010"}

def module():
    spec=importlib.util.spec_from_file_location("generate_cli_only_e2e_contract",GEN)
    value=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(value)
    return value

class CLIDerivationContractTest(unittest.TestCase):
    def test_original_116_preserved_and_direct_100(self):
        parent=PATTERN.findall(SOURCE.read_text(encoding="utf-8"))
        direct=PATTERN.findall(CLI.read_text(encoding="utf-8"))
        self.assertEqual(len(parent),116)
        self.assertEqual(len(set(parent)),116)
        self.assertEqual(len(direct),100)
        self.assertEqual(len(set(direct)),100)
        self.assertEqual(set(parent)-set(direct),EXCLUDED)
        self.assertEqual(set(direct),set(parent)-EXCLUDED)

    def test_generated_file_matches_current_full_source_exactly(self):
        m=module()
        self.assertEqual(CLI.read_text(encoding="utf-8"),m.render())

    def test_mixed_exclusions_without_wholesale_parent_drops(self):
        m=module()
        direct=CLI.read_text(encoding="utf-8")
        for item in m.MIXED:
            self.assertRegex(direct,re.compile(r"^## "+re.escape(item)+r" — ",re.M))
        self.assertNotIn("AI_ASSISTED_RESULT/EVIDENCE",direct)
        self.assertNotIn("system diagnostics mcp",direct)
        self.assertNotIn("system credential approve-oauth",direct)

    def test_referenced_shared_rules_are_standalone(self):
        s=CLI.read_text(encoding="utf-8")
        for token in ("### 1.3.2 Mandatory repetition",
                      "### 1.3.3 Manual-free operator",
                      "### 1.4.1 Scenario prerequisites",
                      "MANDATORY_REPEAT_COVERAGE=100%",
                      "FAIL_PRECONDITION",
                      "WARMUP=60s","STEADY_STATE_EACH_CASE=300s","SOAK=3600s",
                      "EXTENDED_SOAK=8h","ENDURANCE_SOAK=24h"):
            self.assertIn(token,s)

    def test_mcp_is_in_v240_product_but_not_direct_scope(self):
        m=MASTER.read_text(encoding="utf-8")
        c=CLI.read_text(encoding="utf-8")
        self.assertIn("For the v2.4.0 target, the server-side MCP Bridge is included",m)
        self.assertIn("EXCLUDED_AI_MCP",c)
        self.assertIn("FULL_USER_E2E_PASS",c)
        self.assertNotIn("## U-007 —",c)

    def test_fcs_scope_separation_and_current_implementer(self):
        f=FCS.read_text(encoding="utf-8")
        a=(ROOT/"AGENTS.md").read_text(encoding="utf-8")
        for x in ("FCS_CLI_ONLY", "FCS_FULL", "13", "EXCLUDED_AI_MCP"):
            self.assertIn(x,f)
        self.assertIn("CHATGPT_CHAT",a)
        self.assertIn("current",a.lower())
        self.assertIn("CURRENT",f.upper())

    def test_real_denial_never_weakened(self):
        s=CLI.read_text(encoding="utf-8")
        self.assertIn("An actual current denial remains binding",s)
        self.assertIn("do not bypass",s)
        self.assertIn("same authorized tool/target",s)
        self.assertIn("not a permanent ban",s)

if __name__=="__main__":
    unittest.main()
