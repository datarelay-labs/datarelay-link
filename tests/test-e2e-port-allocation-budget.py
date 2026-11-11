#!/usr/bin/env python3
"""Deterministic guard and canonical-contract regression for E2E port cap."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools/e2e_port_allocation_budget.py"


class TestPortBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "budget.json"

    def run_guard(self, action, owner=None):
        cmd = [sys.executable, str(GUARD), "--ledger", str(self.ledger), action]
        if owner is not None:
            cmd.extend(["--owner", owner])
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)

    def test_30_live_then_denies_31st(self):
        for i in range(30):
            code, state = self.run_guard("reserve", "e2e:S-013:%02d" % i)
            self.assertEqual(code, 0)
            self.assertEqual(state["live_reserved"], i + 1)
        code, state = self.run_guard("reserve", "e2e:S-013:30")
        self.assertEqual(code, 2)
        self.assertEqual(state["result"], "DENY")
        self.assertEqual(self.run_guard("status")[1]["live_reserved"], 30)

    def test_parallel_lanes_cannot_exceed_30(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda i: self.run_guard("reserve", "concurrent:C-003:%02d" % i),
                range(40),
            ))
        self.assertEqual(sum(code == 0 for code, _ in results), 30)
        self.assertEqual(sum(code == 2 for code, _ in results), 10)
        self.assertEqual(self.run_guard("status")[1]["live_reserved"], 30)

    def test_release_reuses_capacity(self):
        for i in range(30):
            self.assertEqual(self.run_guard("reserve", "test:%d" % i)[0], 0)
        self.assertEqual(self.run_guard("release", "test:0")[0], 0)
        self.assertEqual(self.run_guard("reserve", "test:replacement")[0], 0)
        self.assertEqual(self.run_guard("status")[1]["live_reserved"], 30)

    def test_duplicate_and_missing_owner_fail_closed(self):
        self.assertEqual(self.run_guard("reserve", "test:one")[0], 0)
        self.assertEqual(self.run_guard("reserve", "test:one")[0], 2)
        self.assertEqual(self.run_guard("release", "test:unknown")[0], 2)
        self.assertEqual(self.run_guard("status")[1]["live_reserved"], 1)

    def test_invalid_ledger_fails_closed(self):
        self.ledger.write_text('{"schema": 1, "owners": ["duplicate", "duplicate"]}')
        self.assertEqual(self.run_guard("reserve", "test:two")[0], 2)

    def test_canonical_contract_cap_and_isolation(self):
        for doc in ["docs/FULL_USER_E2E_SCENARIOS.md",
                    "docs/CLI_ONLY_E2E_SCENARIOS.md"]:
            text = (ROOT / doc).read_text()
            self.assertIn("30 simultaneously reserved", text, doc)
            self.assertIn("POOL_EXHAUSTION=NOT_TESTED_BUDGET_LIMIT", text, doc)
            self.assertIn("e2e_port_allocation_budget.py", text, doc)
            self.assertIn("S-013", text, doc)
            self.assertIn("S-020", text, doc)
            self.assertIn("at most 29", text, doc)
            self.assertIn("independent out-of-band/console recovery", text, doc)
            self.assertIn("authentic prior-stable artifact", text, doc)


if __name__ == "__main__":
    unittest.main()
