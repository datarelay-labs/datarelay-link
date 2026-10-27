#!/usr/bin/env python3
"""Execute the printed shell command with failing/successful download tools."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from frp_zero_touch import short_url_command


class CommandExit(unittest.TestCase):
    def run_command(self, download_exit, payload):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'payload').write_text(payload)
            (root / 'curl').write_text('#!/bin/sh\ncat "$CASE_ROOT/payload"\nexit "$DOWNLOAD_EXIT"\n')
            (root / 'sudo').write_text('#!/bin/sh\ntouch "$CASE_ROOT/installer-started"\nexec "$@"\n')
            for name in ('curl', 'sudo'):
                (root / name).chmod(0o755)
            env = dict(os.environ, PATH=tmp + ':' + os.environ['PATH'],
                       CASE_ROOT=tmp, DOWNLOAD_EXIT=str(download_exit))
            result = subprocess.run(['sh', '-c', short_url_command('bootstrap.example.com', 'A' * 22)],
                                    env=env, capture_output=True, text=True)
            return result.returncode, (root / 'installer-started').exists()

    def test_dns_failure_propagates(self):
        self.assertEqual(self.run_command(6, ''), (6, False))

    def test_partial_failed_fetch_never_starts_installer(self):
        self.assertEqual(self.run_command(18, 'exit 0\n'), (18, False))

    def test_installer_failure_propagates(self):
        self.assertEqual(self.run_command(0, 'exit 42\n'), (42, True))

    def test_success(self):
        self.assertEqual(self.run_command(0, 'exit 0\n'), (0, True))


if __name__ == '__main__':
    unittest.main()
