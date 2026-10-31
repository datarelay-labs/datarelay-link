#!/usr/bin/env python3
"""Contract tests for a read-only batch-fix full-sweep gate."""
from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from cli_only_e2e_inventory import CANONICAL, FIELDS, scopes  # noqa: E402
from cli_only_e2e_round_gate import load_ledger, audit, compare  # noqa: E402

A = "a" * 40
B = "b" * 40


def make_ledger(path: Path, head: str, overrides=None):
    overrides = overrides or {}
    rows = []
    for item in scopes(CANONICAL.read_text(encoding="utf-8")):
        sid = item["SCENARIO_ID"]
        excluded = item["SCOPE"] == "EXCLUDED_AI_MCP"
        rows.append({
            **{k: "" for k in FIELDS}, **item,
            "RUN_ID": path.parent.name,
            "SOURCE_HEAD": head,
            "RESULT": "EXCLUDED_AI_MCP" if excluded else "PASS",
            "INSTALLED_HEAD": "" if excluded else head,
            "ACTUAL_COMMAND": "" if excluded else "sudo drlink show status",
            "EVIDENCE": "" if excluded else "receipts/public-cli.txt",
            **overrides.get(sid, {}),
        })
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


class RoundGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def file(self, name, head=A, overrides=None):
        path = self.root / name
        make_ledger(path, head, overrides)
        return path

    def test_valid_complete_round_only_moves_to_batch_fix(self):
        data = load_ledger(self.file("one.tsv", overrides={
            "U-009": {"RESULT": "FAIL"},
            "P-024": {"RESULT": "PARTIAL", "INSTALLED_HEAD": ""},
        }))
        report = audit(data)
        self.assertEqual(report["phase"], "FREEZE_THEN_BATCH_FIX")
        self.assertTrue(report["full_sweep_dispositioned"])
        self.assertFalse(report["all_applicable_cli_e2e_pass"])
        self.assertEqual(report["fail_ids"], ["U-009"])
        self.assertEqual(report["partial_ids"], ["P-024"])

    def test_missing_mandatory_scenario_requires_full_sweep(self):
        data = load_ledger(self.file("two.tsv", overrides={
            "A-020": {"RESULT": "NOT_RUN"},
            "P-019": {"RESULT": "OPTIONAL_NOT_SELECTED"},
        }))
        self.assertEqual(audit(data)["phase"], "FINISH_FULL_SWEEP")
        self.assertEqual(audit(data)["mandatory_not_run_or_in_progress"], ["A-020"])

    def test_missing_native_proof_is_not_qualified(self):
        data = load_ledger(self.file("three.tsv", overrides={
            "U-001": {"INSTALLED_HEAD": ""},
            "U-002": {"ACTUAL_COMMAND": ""},
        }))
        report = audit(data)
        self.assertFalse(report["all_applicable_cli_e2e_pass"])
        self.assertEqual(report["pass_without_exact_native_minimum_receipts"], ["U-001", "U-002"])

    def test_compare_counts_real_promotions_and_regressions(self):
        old = load_ledger(self.file("before.tsv", overrides={
            "U-009": {"RESULT": "FAIL"},
            "P-002": {"RESULT": "PARTIAL"},
        }))
        new = load_ledger(self.file("after.tsv", head=B, overrides={
            "P-002": {"RESULT": "PASS", "INSTALLED_HEAD": ""},
            "U-001": {"RESULT": "FAIL"},
        }))
        diff = compare(old, new)
        self.assertEqual(diff["new_pass_with_minimum_exact_native_receipts"], ["U-009"])
        self.assertEqual(diff["pass_promotions_missing_exact_native_receipts"], ["P-002"])
        self.assertEqual(diff["regressed_from_pass"], ["U-001"])

    def test_mixed_source_and_excluded_promotion_rejected(self):
        p = self.file("wrong.tsv", overrides={"U-001": {"SOURCE_HEAD": B}})
        with self.assertRaisesRegex(ValueError, "mixed candidate"):
            load_ledger(p)
        q = self.file("wrong-exclusion.tsv", overrides={"X-001": {"RESULT": "PASS"}})
        with self.assertRaisesRegex(ValueError, "exclusion"):
            load_ledger(q)

    def test_optional_only_p019_and_unique_ids(self):
        p = self.file("wrong-opt.tsv", overrides={"U-001": {"RESULT": "OPTIONAL_NOT_SELECTED"}})
        with self.assertRaisesRegex(ValueError, "only P-019"):
            load_ledger(p)
        q = self.file("wrong-dup.tsv")
        content = q.read_text()
        header, a, *other = content.splitlines()
        other[0] = a
        q.write_text("\n".join([header, a] + other) + "\n")
        with self.assertRaisesRegex(ValueError, "116 unique"):
            load_ledger(q)


if __name__ == "__main__":
    unittest.main()
