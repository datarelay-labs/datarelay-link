#!/usr/bin/env python3
"""Auditor-only static guard: E2E operator procedure cannot weaken the contract."""
from pathlib import Path
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
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



class CodexDualRoleEvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import validate_codex_dual_role_pairs as paircheck
        cls.validator = paircheck

    def _fixture(self, evidence_root):
        h = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
        pairs = []
        for n in range(1, 16):
            key = f"{n:03d}"
            for suffix in ("direct", "ai-first", "ai-user"):
                (evidence_root / f"{key}-{suffix}.txt").write_text(
                    f"Supporting fixture output for {key}:{suffix}. Never real user E2E.\n"
                )
            goal = h("Neutral first-time operator mission")
            baseline = h("Equivalent isolated demo source baseline")
            pairs.append({
                "PAIR_ID": "PAIR-" + key, "SCENARIO_ID": "FCS-" + key,
                "FEATURE_ID": "FEATURE-CLI" if n % 2 else "FEATURE-AI",
                "ROLE": "Operator",
                "AUDITOR_CODEX_THREAD": "auditor",
                "DIRECT_CODEX_THREAD": "direct-" + key,
                "AI_OPERATOR_CODEX_THREAD": "ai-operator-" + key,
                "AI_ADVISER_CODEX_THREAD": "ai-adviser-" + key,
                "DIRECT_GOAL_SHA256": goal, "AI_GOAL_SHA256": goal,
                "DIRECT_BASELINE_SHA256": baseline,
                "AI_BASELINE_SHA256": baseline,
                "DIRECT_SOURCE_HEAD": "a" * 40, "AI_SOURCE_HEAD": "a" * 40,
                "DIRECT_RESULT": "PASS", "AI_RESULT": "PASS",
                "FINAL_RESULT": "PASS",
                "DIRECT_EVIDENCE": key + "-direct.txt",
                "AI_FIRST_ANSWER_EVIDENCE": key + "-ai-first.txt",
                "AI_FIRST_ANSWER_SHA256": hashlib.sha256(
                    (evidence_root / (key + "-ai-first.txt")).read_bytes()
                ).hexdigest(),
                "AI_OPERATOR_EVIDENCE": key + "-ai-user.txt",
                "BLOCK_REASON": "",
            })
        return pairs

    def _check(self, rows, root):
        return self.validator.evaluate(
            rows, evidence_root=root,
            expected_ids={f"FCS-{i:03d}" for i in range(1, 16)},
            expected_features={"FEATURE-CLI", "FEATURE-AI"},
            expected_head="a" * 40,
        )

    def test_codex_direct_and_ai_same_scenario_fixture_structure_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self._check(self._fixture(root), root)
            self.assertEqual(result["EVIDENCE_SCHEMA"], "PASS", result["ERRORS"])
            self.assertEqual(result["SCENARIO_COVERAGE"], 15)
            self.assertEqual(result["FEATURE_COVERAGE"], 2)
            self.assertTrue(result["ALL_PAIRS_STRUCTURALLY_PASS"])
            # A valid synthetic ledger is NOT evidence of a genuine Codex E2E.
            self.assertFalse(result["ACTUAL_CODEX_ROLE_EXECUTION_VERIFIED"])
            self.assertFalse(result["PRODUCT_E2E_PASS_PROVEN"])

    def test_codex_missing_ai_or_inherited_thread_cannot_claim_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = self._fixture(root)
            for key, value in (
                ("AI_RESULT", "NOT_RUN"),
                ("AI_ADVISER_CODEX_THREAD", good[0]["DIRECT_CODEX_THREAD"]),
                ("AI_GOAL_SHA256", "b" * 64),
                ("AI_BASELINE_SHA256", "b" * 64),
                ("AI_SOURCE_HEAD", "b" * 40),
                ("AI_FIRST_ANSWER_SHA256", "b" * 64),
                ("AI_FIRST_ANSWER_EVIDENCE", "../not-a-public-actor.txt"),
            ):
                with self.subTest(key=key):
                    rows = [dict(r) for r in good]
                    rows[0][key] = value
                    result = self._check(rows, root)
                    self.assertEqual(result["EVIDENCE_SCHEMA"], "FAIL", key)
                    self.assertFalse(result["ALL_PAIRS_STRUCTURALLY_PASS"])

    def test_cli_validator_rejects_fabricated_ai_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            pairs = root / "pairs.tsv"
            features = root / "features.tsv"
            with features.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["FEATURE_ID", "SUPPORTED"],
                                        delimiter="\t")
                writer.writeheader()
                writer.writerow({"FEATURE_ID": "FEATURE-CLI", "SUPPORTED": "YES"})
                writer.writerow({"FEATURE_ID": "FEATURE-AI", "SUPPORTED": "YES"})
            def invoke():
                with pairs.open("w", newline="") as f:
                    writer = csv.DictWriter(
                        f, fieldnames=self.validator.FIELDS, delimiter="\t")
                    writer.writeheader()
                    writer.writerows(rows)
                return subprocess.run([
                    sys.executable, str(ROOT / "tools" /
                                        "validate_codex_dual_role_pairs.py"),
                    "--mode", "fcs", "--pairs", str(pairs),
                    "--evidence-root", str(root),
                    "--feature-inventory", str(features),
                    "--expected-head", "a" * 40,
                ], capture_output=True, text=True, timeout=8)
            positive = invoke()
            self.assertEqual(positive.returncode, 0, positive.stderr)
            result = json.loads(positive.stdout)
            self.assertTrue(result["ALL_PAIRS_STRUCTURALLY_PASS"])
            self.assertFalse(result["PRODUCT_E2E_PASS_PROVEN"])
            rows[0]["AI_RESULT"] = "NOT_RUN"
            false_pass = invoke()
            self.assertEqual(false_pass.returncode, 2)
            self.assertIn("FINAL PASS requires both", false_pass.stdout)

    def test_no_missing_fcs_or_feature_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            dropped = [r for r in rows if r["SCENARIO_ID"] != "FCS-015"]
            report = self._check(dropped, root)
            self.assertIn("missing scenario FCS-015", report["ERRORS"])
            dropped = [r for r in rows if r["FEATURE_ID"] == "FEATURE-CLI"]
            report = self._check(dropped, root)
            self.assertIn("missing feature FEATURE-AI", report["ERRORS"])

    def test_canonical_documents_select_codex_both_roles_and_do_not_run_yet(self):
        fcs = (ROOT / "docs" / "CLI_FEATURE_SCENARIO_RECONCILIATION.md"
               ).read_text(encoding="utf-8")
        full = CANONICAL.read_text(encoding="utf-8")
        plan = (ROOT / "docs" / "CODEX_DUAL_ROLE_TEST_PROTOCOL.md"
                ).read_text(encoding="utf-8")
        for text in (fcs, full, plan):
            self.assertIn("CODEX", text.upper())
        self.assertIn("docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md", fcs)
        self.assertIn("docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md", full)
        self.assertIn("ISSUE_165_PRIMARY_PERSONA_EXECUTOR=CODEX", fcs)
        self.assertIn("AI-assisted user role for the SAME feature", fcs)
        self.assertIn("same business goal", plan)
        self.assertIn("different fresh", plan.lower())
        self.assertIn("NOT_READY", plan)
        self.assertIn("TEST ONLY", plan)


if __name__ == "__main__":
    unittest.main()
