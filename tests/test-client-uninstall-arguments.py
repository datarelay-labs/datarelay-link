#!/usr/bin/env python3
"""Uninstall discovery and invalid argv must never delete Agent state."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ClientUninstallArguments(unittest.TestCase):
    def invoke(self, args):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            identity = root / 'etc/frp/client-id'
            identity.parent.mkdir(parents=True)
            identity.write_text('argument-regression-sentinel\n')
            env = os.environ.copy()
            env.update(FRP_UNINSTALL_TEST_ROOT=work,
                       FRP_UNINSTALL_HOOK_SKIP_SYSTEMD='1')
            result = subprocess.run(
                ['bash', str(ROOT / 'uninstall-client.sh'), *args],
                env=env, capture_output=True, text=True, timeout=15,
            )
            self.assertTrue(identity.exists(), 'argument handling removed Agent identity')
            self.assertEqual(identity.read_text(), 'argument-regression-sentinel\n')
            return result

    def test_long_help_preserves_state(self):
        result = self.invoke(['--help'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Usage:', result.stdout)

    def test_short_help_preserves_state(self):
        result = self.invoke(['-h'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Usage:', result.stdout)

    def test_unknown_option_fails_before_mutation(self):
        result = self.invoke(['--preserve'])
        self.assertEqual(result.returncode, 2)
        self.assertIn('unknown option', result.stderr)

    def test_unexpected_operand_fails_before_mutation(self):
        result = self.invoke(['unexpected'])
        self.assertEqual(result.returncode, 2)
        self.assertIn('unknown option', result.stderr)


if __name__ == '__main__':
    unittest.main()
