#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

class V30ContractFreezeTests(unittest.TestCase):
    def test_cross_document_contract_gate(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check-v30-contract-freeze.py")],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRL3_0_CONTRACT_FREEZE=PASS", result.stdout)
        self.assertIn("SSO_IDP_DEPENDENCY=NO", result.stdout)

if __name__ == "__main__":
    unittest.main()
