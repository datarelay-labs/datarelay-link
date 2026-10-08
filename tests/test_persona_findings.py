#!/usr/bin/env python3
"""Regression-contract tests for user-observed E2E finding backstops."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/persona_findings.py"
spec = importlib.util.spec_from_file_location("persona_findings", SCRIPT)
assert spec and spec.loader
feedback = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = feedback
spec.loader.exec_module(feedback)

HEADER = "FINDING_ID\tSEVERITY\tUSER_BLOCKING\tSTATUS\tCLASSIFICATION\tSURFACE\tEVIDENCE\n"


class PersonaFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="drlink-persona-feedback-")
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        (self.root / "tests").mkdir()
        (self.root / "tests/real_test.py").write_text(
            "class RealChecks:\n"
            "    def test_wrong_command(self):\n"
            "        assert True\n", encoding="utf-8",
        )
        self.row = {
            "run_id": "audit-123",
            "source_head": "a" * 40,
            "contract_sha256": "b" * 64,
            "finding_id": "P2-001",
            "scenario_id": "FCS-015",
            "user_goal": "A first-time operator discovers a documented command",
            "observation": "Hidden parser accepted retired path",
            "regression_file": "tests/real_test.py",
            "regression_case": "RealChecks.test_wrong_command",
        }
        self.registry([self.row])
        self.ledger(HEADER + "P2-001\tP2\tYES\tOPEN\tDISCOVERY_GAP\tCLI help\tproof.txt\n")

    def registry(self, rows):
        (self.root / "tests/persona-regression-links.json").write_text(
            json.dumps({"version": 1, "findings": rows}), encoding="utf-8",
        )

    def ledger(self, content):
        ledger_dir = self.root / "ledger"
        ledger_dir.mkdir(exist_ok=True)
        self.ledger_path = ledger_dir / "findings.tsv"
        self.ledger_path.write_text(content, encoding="utf-8")
        (self.root / "run.env").write_text(
            "RUN_ID=audit-123\n"
            "PRODUCT_SOURCE_HEAD=" + "a" * 40 + "\n"
            "TEST_CONTRACT_FILE_SHA256=" + "b" * 64 + "\n",
            encoding="utf-8",
        )

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), *args],
            capture_output=True, text=True, check=False, timeout=15,
        )

    def test_registry_has_exact_existing_case_not_just_file(self):
        linked = feedback.load_registry(self.root, "tests/persona-regression-links.json")
        self.assertEqual(linked[("audit-123", "P2-001")]["scenario_id"], "FCS-015")
        wrong = dict(self.row, regression_case="RealChecks.test_nonexistent")
        self.registry([wrong])
        with self.assertRaisesRegex(ValueError, "test case not found"):
            feedback.load_registry(self.root, "tests/persona-regression-links.json")

    def test_reports_link_only_never_user_pass(self):
        output = feedback.audit(self.root, "tests/persona-regression-links.json",
                                self.ledger_path, "audit-123")
        self.assertEqual(output["linked_open_findings"], 1)
        self.assertEqual(output["open_findings"], 1)
        self.assertEqual(output["unlinked_findings"], [])
        self.assertEqual(output["user_gate_result"], "NOT_EVALUATED")
        self.assertEqual(output["release_authorization"], "NONE")

    def test_reports_real_unlinked_findings_without_hiding_them(self):
        self.ledger(HEADER +
                    "P2-001\tP2\tYES\tOPEN\tDISCOVERY_GAP\tCLI help\tproof.txt\n" +
                    "P1-009\tP1\tYES\tFAIL\tRUNTIME_DRIFT\tServer\tproof2.txt\n")
        run = self.command("--ledger", str(self.ledger_path),
                           "--run-id", "audit-123", "--strict-findings")
        self.assertEqual(run.returncode, 1, run.stderr)
        data = json.loads(run.stdout)
        self.assertEqual(data["linked_open_findings"], 1)
        self.assertEqual(data["unlinked_findings"][0]["finding_id"], "P1-009")
        self.assertEqual(data["user_gate_result"], "NOT_EVALUATED")

    def test_closed_history_does_not_demand_new_regression(self):
        self.ledger(HEADER + "P1-009\tP1\tYES\tCLOSED\tRUNTIME_DRIFT\tServer\tproof2.txt\n")
        run = self.command("--ledger", str(self.ledger_path),
                           "--run-id", "audit-123", "--strict-findings")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["open_findings"], 0)

    def test_rejects_path_escape_and_symlink(self):
        wrong = dict(self.row, regression_file="../outside.py")
        self.registry([wrong])
        with self.assertRaisesRegex(ValueError, "unsafe"):
            feedback.load_registry(self.root, "tests/persona-regression-links.json")
        target = self.root / "not-repo.py"
        target.write_text("def test_wrong_command(): pass\n", encoding="utf-8")
        (self.root / "tests/alias.py").symlink_to(target)
        wrong["regression_file"] = "tests/alias.py"
        # Reject symlinks even when their targets happen to stay in the checkout.
        wrong["regression_case"] = "RealChecks.test_wrong_command"
        self.registry([wrong])
        with self.assertRaisesRegex(ValueError, "unsafe symlink"):
            feedback.load_registry(self.root, "tests/persona-regression-links.json")

    def test_invalid_ledger_and_duplicate_finding_rejected(self):
        self.ledger("FINDING_ID\tSTATUS\nP2-001\tOPEN\n")
        with self.assertRaisesRegex(ValueError, "columns"):
            feedback.read_ledger(self.ledger_path)
        self.registry([self.row, self.row])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            feedback.load_registry(self.root, "tests/persona-regression-links.json")

    def test_registry_requires_human_goal_and_observation(self):
        bad = dict(self.row, user_goal="")
        self.registry([bad])
        with self.assertRaisesRegex(ValueError, "missing fields"):
            feedback.load_registry(self.root, "tests/persona-regression-links.json")

    def test_repository_sample_links_all_point_to_existing_tests(self):
        linked = feedback.load_registry(ROOT, "tests/persona-regression-links.json")
        self.assertEqual(len(linked), 9)
        self.assertEqual(len({k[1] for k in linked}), 9)
        self.assertTrue(all(row["user_goal"] for row in linked.values()))


if __name__ == "__main__":
    unittest.main()
