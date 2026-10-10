#!/usr/bin/env python3
"""Auditor-only static guard: E2E operator procedure cannot weaken the contract."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "docs" / "FULL_USER_E2E_SCENARIOS.md"
PROCEDURE = ROOT / "docs" / "E2E_EXECUTION_PROCEDURE.md"
ROADMAP = ROOT / "docs" / "E2E_LAB_READINESS_ROADMAP.md"


class E2EProcedureGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = CANONICAL.read_text(encoding="utf-8")
        cls.procedure = PROCEDURE.read_text(encoding="utf-8")
        cls.roadmap = ROADMAP.read_text(encoding="utf-8")

    def test_canonical_points_to_owner_fix_first_procedure(self):
        self.assertIn("Current owner-ordered preparation gate", self.canonical)
        self.assertIn("docs/E2E_EXECUTION_PROCEDURE.md", self.canonical)
        self.assertIn("ChatGPT", self.canonical)
        self.assertIn("this entire canonical document", self.canonical)
        self.assertIn("previously denied security effects remain binding", self.canonical)

    def test_roadmap_priority_first_bugs_then_method_then_clean_lab(self):
        bug = self.roadmap.index("Immediate first:")
        sop = self.roadmap.index("**Next:** CHATGPT_CHAT repairs the method")
        lab = self.roadmap.index("**Only after those two gates:**")
        self.assertLess(bug, sop)
        self.assertLess(sop, lab)
        self.assertLess(lab, self.roadmap.index("### LAB-P0-01"))
        self.assertIn("F001 and F007 remain open", self.roadmap)

    def test_procedure_retains_full_e2e_and_codex_test_only(self):
        required = (
            "FULL_USER_E2E_SCENARIOS.md",
            "116 scenario", "3,600-second soak",
            "two same-HEAD PASS", "Codex TEST-ONLY",
            "F001", "F004", "F005", "F006", "F007", "D001",
            "No new full E2E", "15-FCS audit",
            "first AI answer", "AI_FIRST_ANSWERS.tsv",
            "PROCESS_REGISTRY.tsv", "CLEANROOM_LEDGER.tsv",
            "status",  # diagnostics and status reports remain explicit
            "MCP", "OAuth", "B014",
            "WARMUP=60s", "STEADY_STATE_EACH_CASE=300s", "SOAK=3600s",
            "NOT_READY", "PASS1=0/PASS2=0",
            "FRP",
            "No Cursor", "not a persona",
        )
        text = self.procedure
        absent = [p for p in required if p not in text]
        self.assertEqual(absent, [], absent)

    def test_open_runtime_continuity_findings_are_not_prematurely_closed(self):
        decision = (ROOT / "docs" / "F001_F007_RUNTIME_CONTINUITY_REMEDIATION.md"
                    ).read_text(encoding="utf-8")
        self.assertIn("F001=PARTIALLY_MITIGATED", decision)
        self.assertIn("F007=PARTIALLY_MITIGATED_FOR_METADATA_ONLY", decision)
        self.assertIn("DOES NOT close F001 or F007", decision)
        self.assertIn("PASS1=0", decision)
        self.assertIn("PASS2=0", decision)
        self.assertIn("RELEASE=HOLD", decision)

    def test_both_documents_require_prospective_isolation_and_lifetime_evidence(self):
        for token in ("natural-language mission", "prospective", "server", "baseline"):
            self.assertIn(token.lower(), self.procedure.lower())
        self.assertIn("outside `/tmp`", self.procedure.replace("outside /tmp", "outside `/tmp`"))
        self.assertIn("artifacts", self.canonical.lower())
        self.assertIn("SOAK=3600s", self.canonical)
        self.assertIn("FULL_USER_E2E", self.canonical)


if __name__ == "__main__":
    unittest.main()
