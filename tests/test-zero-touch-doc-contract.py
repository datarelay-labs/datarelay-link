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

    def test_help_and_real_e2e_cannot_reassert_automatic_long_fallback(self):
        # These public surfaces previously contradicted the compact-default
        # contract while the focused short-URL test was already green.
        help_text = self.read('lib/frp_ctl_grammar.py').lower()
        catalog = self.read('lib/frp_cli_final_commands.json').lower()
        config = self.read('lib/frp_server_config.py').lower()
        real_e2e = self.read('tests/run-short-url-e2e.sh')
        self.assertNotIn('bootstrap-hostname falls back to zt1', help_text)
        self.assertNotIn('bootstrap-hostname falls back to zt1', catalog)
        self.assertNotIn('short url mode is opt-in.', config)
        self.assertNotIn('callers must use the pinned-ca zt1 fallback', config)
        self.assertIn('DEFAULT_NO_SILENT_LONG_AFTER_UNSET', real_e2e)
        self.assertNotIn('ZT1_FALLBACK_AFTER_CERT_PATH', real_e2e)

    def test_ip_private_ca_is_a_documented_default_without_dns(self):
        contract = self.read('docs/ZERO_TOUCH_REGRESSION_CONTROL.md')
        master = self.read('docs/PRODUCT_MASTER.md')
        cli = self.read('docs/CLI_REFERENCE.md')
        short = self.read('docs/ZERO_TOUCH_SHORT_URL.md')
        for text in (contract, master, cli, short):
            self.assertIn('numeric IP', text)
            self.assertIn('CA', text)
        self.assertIn('before collecting services', contract)
        self.assertIn('only', contract)
        self.assertIn('--cacert', short)
        self.assertIn('without any credential', contract)

    def test_operator_and_real_user_contract_is_quantitative(self):
        short = self.read('docs/ZERO_TOUCH_REGRESSION_CONTROL.md')
        user = self.read('docs/FULL_USER_E2E_SCENARIOS.md')
        cli = self.read('docs/CLI_EXHAUSTIVE_AUDIT.md')
        for token in ('<= 200', '<= 500', '/i/invalid-qualification-probe',
                      'bootstrap unavailable', 'DERIVED_BUNDLE_STALE',
                      'signed', 'installed Source HEAD', 'no ticket'):
            with self.subTest(required=token):
                self.assertIn(token.lower(), short.lower())
        for token in ('U-009', 'O-002', 'A-018', 'short'):
            self.assertTrue(token in user, 'missing Full User scenario: ' + token)
        # Older 116-ID E2E and its generated 100-ID profile intentionally
        # retain scenario IDs and checksum parity; this focused policy lives
        # in the new normative regression contract until next full gate revision.
        self.assertIn('long-bootstrap', short)
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

    def test_release_manifest_runs_zero_touch_gate_as_a_product_contract(self):
        native = self.read('.engineering/tests.yaml')
        self.assertIn('DRLINK-ZERO-TOUCH-UX-CONTRACT-001', native)
        section = native.split(
            '  - id: DRLINK-ZERO-TOUCH-UX-CONTRACT-001', 1
        )[1].split('\n  - id: ', 1)[0]
        for test in (
            'test-zero-touch-doc-contract.py',
            'test-zero-touch-operator-command-bound.py',
            'test-enrolled-routed-target-parity.py',
            'test-zero-touch-short-url.sh',
        ):
            self.assertIn(test, section)
        for required in (
            'release_gate: true',
            'ZT-P0-CONTRACT-20261026',
            'U-009, O-002, A-018',
            'multi-kilobyte zt1',
            'same exact installed Source HEAD',
        ):
            self.assertIn(required, section)

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
