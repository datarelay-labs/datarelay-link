#!/usr/bin/env python3
"""A protected live install is an operator permission failure, not a crash."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import frp_doctor as doctor

class PermissionGuidanceTests(unittest.TestCase):
    def test_protected_install_has_actionable_failure_without_claiming_health(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(doctor, 'run_doctor', side_effect=PermissionError(13, 'Permission denied', '/etc/frp/server_token')), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = doctor.main(['--skip-network'])
        self.assertEqual(rc, 1)
        self.assertEqual(stdout.getvalue(), '')
        self.assertIn('sudo drlink system diagnostics', stderr.getvalue())
        self.assertNotIn('internal error', stderr.getvalue())
        self.assertNotIn('PASS', stderr.getvalue())

    def test_unrelated_internal_failure_is_not_relabelled_as_permissions(self):
        stderr = io.StringIO()
        with mock.patch.object(doctor, 'run_doctor', side_effect=ValueError('broken fixture')), contextlib.redirect_stderr(stderr):
            rc = doctor.main(['--skip-network'])
        self.assertEqual(rc, 2)
        self.assertIn('internal error', stderr.getvalue())
        self.assertNotIn('sudo drlink', stderr.getvalue())

if __name__ == '__main__': unittest.main()
