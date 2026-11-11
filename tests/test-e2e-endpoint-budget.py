#!/usr/bin/env python3
"""Regression for the owner-imposed E2E endpoint allocation ceiling."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools/e2e_endpoint_budget.py"
spec = importlib.util.spec_from_file_location("e2e_endpoint_budget", GUARD)
assert spec and spec.loader
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


class EndpointBudgetTest(unittest.TestCase):
    def evaluate(self, own: int, other: int, planned: int, **extra):
        return budget.evaluate(
            active_owned=own, other_e2e_owned=other, planned_new=planned,
            expect_full_pool=extra.get("expect_full_pool", False),
            pool_capacity=extra.get("pool_capacity"),
            pool_active_after_plan=extra.get("pool_active_after_plan"),
        )

    def test_30_total_is_allowed(self):
        self.assertEqual(self.evaluate(29, 0, 1)["status"], "ALLOW")
        self.assertEqual(self.evaluate(12, 11, 7)["status"], "ALLOW")

    def test_31st_slot_denied_including_parallel_lanes(self):
        self.assertEqual(self.evaluate(30, 0, 1)["status"], "DENY")
        self.assertEqual(self.evaluate(20, 10, 1)["status"], "DENY")
        self.assertEqual(self.evaluate(0, 0, 100)["status"], "DENY")

    def test_full_pool_rejects_unrelated_owner_capacity(self):
        self.assertEqual(self.evaluate(
            0, 0, 0, expect_full_pool=True, pool_capacity=30,
            pool_active_after_plan=30)["reason"], "POOL_CAPACITY_NOT_OWNED_BY_E2E_LANES")

    def test_canonical_and_generated_contract_keep_30_cap(self):
        full = (ROOT / "docs/FULL_USER_E2E_SCENARIOS.md").read_text()
        cli = (ROOT / "docs/CLI_ONLY_E2E_SCENARIOS.md").read_text()
        for contract in (full, cli):
            self.assertIn("tools/e2e_endpoint_budget.py", contract)
            self.assertIn("30", contract)
            self.assertIn("NATIVE_POOL_EXHAUSTION=NOT_PROVEN_BUDGET_LIMIT", contract)
            self.assertIn("## S-013", contract)
            self.assertIn("## S-020", contract)

    def test_no_negative_or_missing_live_counts(self):
        with self.assertRaises(ValueError):
            self.evaluate(-1, 0, 1)
        p = subprocess.run([sys.executable, str(GUARD), "--active-owned", "0",
                            "--planned-new", "3"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--other-e2e-owned", p.stderr)

    def test_native_exhaustion_requires_controlled_pool(self):
        self.assertEqual(self.evaluate(
            30, 0, 0, expect_full_pool=True, pool_capacity=100,
            pool_active_after_plan=30)["status"], "DENY")
        self.assertEqual(self.evaluate(
            29, 0, 0, expect_full_pool=True, pool_capacity=30,
            pool_active_after_plan=29)["status"], "DENY")
        self.assertEqual(self.evaluate(
            30, 0, 0, expect_full_pool=True, pool_capacity=30,
            pool_active_after_plan=30)["status"], "ALLOW")
        self.assertEqual(self.evaluate(
            12, 0, 0, expect_full_pool=True, pool_capacity=12,
            pool_active_after_plan=12)["status"], "ALLOW")

    def test_cli_json_and_exit_code(self):
        args = [sys.executable, str(GUARD), "--active-owned", "20",
                "--other-e2e-owned", "10", "--planned-new", "1"]
        p = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        result = json.loads(p.stdout)
        self.assertEqual(result["projected_total"], 31)
        self.assertEqual(result["budget"], 30)
        self.assertEqual(result["status"], "DENY")


if __name__ == "__main__":
    unittest.main()
