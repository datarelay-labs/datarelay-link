#!/usr/bin/env python3
"""Audit filter validation against the native handler in disposable roots."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AuditTailValidation(unittest.TestCase):
    def run_tail(self, value, populated):
        source = (ROOT / 'tools/frpctl').read_text()
        function = 'frpctl_audit_tail() {' + source.split('frpctl_audit_tail() {', 1)[1].split('\n}\n', 1)[0] + '\n}\n'
        with tempfile.TemporaryDirectory(prefix='drlink-audit-tail-') as tmp:
            if populated:
                log = Path(tmp) / 'var/log/drlink/audit.jsonl'
                log.parent.mkdir(parents=True)
                log.write_text(json.dumps({'event': 'fixture.event'}) + '\n')
            script = 'frpctl_lib_candidate() { return 1; }\n' + function + '\nfrpctl_audit_tail last "$1"\n'
            import os
            return subprocess.run(['bash', '-c', script, 'audit-test', value],
                                  env=dict(os.environ, FRP_DEPLOY_TEST_ROOT=tmp),
                                  capture_output=True, text=True, timeout=10)

    def test_nonpositive_rejected_with_existing_log(self):
        for value in ('0', '-1', '-500'):
            with self.subTest(value=value):
                result = self.run_tail(value, True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('requires a positive integer', result.stderr)
                self.assertEqual(result.stdout, '')

    def test_invalid_rejected_without_log(self):
        for value in ('0', '-1', 'invalid'):
            with self.subTest(value=value):
                result = self.run_tail(value, False)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('requires a positive integer', result.stderr)

    def test_positive_empty_log(self):
        result = self.run_tail('1', False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('(no audit log)', result.stdout)

    def test_positive_existing_log(self):
        result = self.run_tail('1', True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('fixture.event', result.stdout)


if __name__ == '__main__':
    unittest.main()
