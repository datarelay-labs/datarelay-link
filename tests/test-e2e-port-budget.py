#!/usr/bin/env python3
"""Regression for the owner-directed maximum 30 E2E public endpoint allocations."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/e2e_port_budget.py"
FULL = ROOT / "docs/FULL_USER_E2E_SCENARIOS.md"
CLI = ROOT / "docs/CLI_ONLY_E2E_SCENARIOS.md"
HEAD = "a" * 40


class E2EEndpointBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_root = Path(self.tmp.name)
        self.run_root.chmod(0o700)
        self.call("init", expect=0)

    def call(self, *args: str, expect: int = 0, head: str = HEAD) -> subprocess.CompletedProcess:
        p = subprocess.run(
            [sys.executable, str(TOOL), "--run-root", str(self.run_root), "--source-head", head, *args],
            capture_output=True, text=True, timeout=12,
        )
        self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        return p

    def test_hard_cap_shared_across_pools_and_lanes(self) -> None:
        pairs = [(str(i), "normal" if i % 2 else "fixed") for i in range(30)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda item: self.call("reserve", "--resource-id", "p" + item[0], "--pool", item[1]),
                pairs,
            ))
        self.assertEqual(len(results), 30)
        denied = self.call("reserve", "--resource-id", "p30", "--pool", "normal", expect=2)
        self.assertIn("E2E_ENDPOINT_BUDGET_EXCEEDED", denied.stderr)
        status = json.loads(self.call("status").stdout)
        self.assertEqual(status["active"], 30)
        self.assertEqual(status["max_active_and_distinct"], 30)

    def test_distinct_port_cap_and_reuse_after_verified_cleanup(self) -> None:
        for i in range(30):
            self.call("reserve", "--resource-id", f"p{i}", "--pool", "normal")
            self.call("confirm", "--resource-id", f"p{i}", "--public-port", str(6000 + i))
        receipt = self.run_root / "cleanup-evidence.txt"
        receipt.write_text("Public CLI delete and independent inventory: confirmed\n")
        self.call("release", "--resource-id", "p0", "--receipt", str(receipt))
        self.call("reserve", "--resource-id", "replacement", "--pool", "fixed")
        denied = self.call("confirm", "--resource-id", "replacement", "--public-port", "7000", expect=2)
        self.assertIn("E2E_DISTINCT_ENDPOINT_BUDGET_EXCEEDED", denied.stderr)
        self.call("confirm", "--resource-id", "replacement", "--public-port", "6000")
        self.assertEqual(json.loads(self.call("status").stdout)["distinct_ports"], 30)

    def test_fail_closed_on_duplicate_port_and_wrong_candidate(self) -> None:
        self.call("reserve", "--resource-id", "one", "--pool", "normal")
        self.call("confirm", "--resource-id", "one", "--public-port", "6010")
        self.call("reserve", "--resource-id", "two", "--pool", "fixed")
        p = self.call("confirm", "--resource-id", "two", "--public-port", "6010", expect=2)
        self.assertIn("duplicate live", p.stderr)
        p = self.call("reserve", "--resource-id", "other", "--pool", "normal", head="b" * 40, expect=2)
        self.assertIn("candidate HEAD/budget mismatch", p.stderr)
        self.assertEqual(json.loads(self.call("status").stdout)["confirmed_active"], 1)

    def test_release_requires_owned_evidence_and_init_never_resets(self) -> None:
        self.call("reserve", "--resource-id", "one", "--pool", "normal")
        self.call("init")
        self.assertEqual(json.loads(self.call("status").stdout)["active"], 1)
        self.call("release", "--resource-id", "one", "--receipt", str(self.run_root / "missing"), expect=2)
        receipt = self.run_root / "proof.txt"
        receipt.write_text("Real operator CLI state verified\n")
        self.call("release", "--resource-id", "one", "--receipt", str(receipt))
        self.assertEqual(json.loads(self.call("status").stdout)["active"], 0)
        import hashlib
        ledger = json.loads((self.run_root / "endpoint-allocation-budget.json").read_text())
        self.assertEqual(ledger["events"][-1]["cleanup_receipt_sha256"], hashlib.sha256(receipt.read_bytes()).hexdigest())

    def test_canonical_and_derived_contract_keep_all_scenarios(self) -> None:
        canonical = FULL.read_text()
        derived = CLI.read_text()
        for text in (canonical, derived):
            self.assertIn("maximum-30", text)
            self.assertIn("tools/e2e_port_budget.py", text)
            self.assertIn("S-013", text)
            self.assertIn("S-020", text)
        pattern = re.compile(r"^## ((?:U|O|A|S|C|P|X)-\d{3})\s+[—:-]", re.M)
        original = pattern.findall(canonical)
        cli_only = pattern.findall(derived)
        self.assertEqual(len(original), 116)
        self.assertEqual(len(set(original)), 116)
        self.assertEqual(len(cli_only), 100)
        self.assertEqual(len(set(cli_only)), 100)


if __name__ == "__main__":
    unittest.main()
