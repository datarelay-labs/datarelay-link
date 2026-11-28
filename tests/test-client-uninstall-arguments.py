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

    def test_explicit_empty_test_root_fails_before_uninstall(self):
        # Execute only the actual argument/early-root-check prefix. Never
        # execute the destructive tail, even if the guard regresses while
        # this test is run by root on an installed development server.
        for role, variables in (
            ("server", ("FRP_UNINSTALL_TEST_ROOT",)),
            ("client", ("FRP_UNINSTALL_TEST_ROOT", "FRP_CLIENT_TEST_ROOT")),
        ):
            source = (ROOT / ("uninstall-" + role + ".sh")).read_text()
            boundary = "# Resolve the directory of this script when executed as a real file."
            self.assertEqual(source.count(boundary), 1)
            prefix = source.split(boundary, 1)[0]
            for variable in variables:
                with self.subTest(role=role, variable=variable):
                    env = os.environ.copy()
                    for name in ("FRP_UNINSTALL_TEST_ROOT", "FRP_CLIENT_TEST_ROOT"):
                        env.pop(name, None)
                    env[variable] = ""
                    result = subprocess.run(
                        ["bash", "-c", prefix + "\necho UNINSTALL_PREFIX_FELL_THROUGH\n"],
                        env=env, capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("FAILURE_CLASS=PATH_DELETION_REFUSED", result.stderr)
                    self.assertNotIn("UNINSTALL_PREFIX_FELL_THROUGH", result.stdout)

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
