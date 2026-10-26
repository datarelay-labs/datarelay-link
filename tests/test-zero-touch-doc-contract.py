#!/usr/bin/env python3
"""Release blocker when Zero-Touch Master, user contract and regression oracle diverge."""
from __future__ import annotations
import hashlib
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID = 'ZT-P0-CONTRACT-20261026'
REQUIRED = (
    'docs/ZERO_TOUCH_REGRESSION_CONTROL.md',
    'docs/ZERO_TOUCH_SHORT_URL.md',
    'docs/PRODUCT_MASTER.md',
    'docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md',
    'docs/CLI_REFERENCE.md',
    'docs/CLI_EXHAUSTIVE_AUDIT.md',
)


class ZeroTouchDocContract(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding='utf-8')

    def test_nonnormative_legacy_fallback_cannot_be_current_default(self):
        for path in REQUIRED:
            with self.subTest(document=path):
                self.assertIn(ID, self.read(path))
        short = self.read('docs/ZERO_TOUCH_SHORT_URL.md')
        master = self.read('docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md')
        self.assertNotIn('Short URL mode is **opt-in** through `bootstrap_hostname`', short)
        self.assertNotIn('Without it, Linux/macOS and Windows Zero-Touch commands use the pinned-CA', master)
        self.assertIn('before', short.lower())
        self.assertIn('--long-bootstrap', short)

    def test_operator_and_real_user_contract_is_quantitative(self):
        short = self.read('docs/ZERO_TOUCH_REGRESSION_CONTROL.md')
        user = self.read('docs/FULL_USER_E2E_SCENARIOS.md')
        cli = self.read('docs/CLI_EXHAUSTIVE_AUDIT.md')
        for token in ('<= 200', '<= 500', '/i/invalid-qualification-probe',
                      'bootstrap unavailable', 'DERIVED_BUNDLE_STALE',
                      'signed', 'installed Source HEAD', 'no ticket'):
            with self.subTest(required=token):
                self.assertIn(token.lower(), short.lower())
        for token in ('U-009', 'O-002', 'A-018', 'short', 'long-bootstrap'):
            self.assertIn(token, user)
        self.assertIn(ID, cli)
        self.assertIn('no ticket', cli.lower())

    def test_cli_only_document_is_generated_from_current_full_e2e(self):
        source = self.read('docs/FULL_USER_E2E_SCENARIOS.md')
        generated = self.read('docs/CLI_ONLY_E2E_SCENARIOS.md')
        digest = hashlib.sha256(source.encode('utf-8')).hexdigest()
        self.assertIn('> **Canonical Full User E2E SHA256:** `' + digest + '`', generated)
        self.assertIn('## U-009', generated)
        # Generated CLI-only contract is intentionally unchanged: the immutable
        # 116-ID source/100-ID projection remains checksum-equivalent.
        run = subprocess.run(
            [sys.executable, str(ROOT / 'tools/generate_cli_only_e2e_contract.py'),
             '--check'],
            cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_fast_pr_does_not_hide_the_user_facing_oracle(self):
        fast = self.read('tests/run-fast-pr.sh')
        public_tests = self.read('tests/test-zero-touch-short-url.sh')
        for name in ('test-zero-touch-doc-contract.py',
                     'test-zero-touch-operator-command-bound.py',
                     'test-enrolled-routed-target-parity.py',
                     'test-cli-inventory-selection-journey.py',
                     'test-zero-touch-short-url.sh'):
            self.assertIn(name, fast)
        self.assertIn('DEFAULT_NO_SILENT_LONG_COMMAND', public_tests)
        self.assertIn('ZT1_EXPLICIT_ADVANCED_LONG_MODE', public_tests)
        self.assertNotIn('pass "ZT1_FALLBACK_ABSENT_HOSTNAME"', public_tests)


if __name__ == '__main__':
    unittest.main(verbosity=2)
