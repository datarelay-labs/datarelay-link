#!/usr/bin/env python3
"""BUG-02: a policy commit must not masquerade as live activation."""
import io
import sys
import unittest
import subprocess
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import drlink_v24_cli as cli


class ActivationAcknowledgementTests(unittest.TestCase):
    def test_server_remote_plugin_frozen_is_saved_but_not_activated(self):
        with mock.patch('drlink_v24_cli._verify_access_rule_runtime', return_value='access plugin /healthz failed'):
            result = cli._access_rule_activation_result(None, 'remote-access', 'test-remote')
        self.assertEqual(result, 1)

    def test_server_internet_egress_stopped_is_saved_but_not_activated(self):
        with mock.patch('drlink_v24_cli._verify_access_rule_runtime', return_value='drlink-egress is inactive'):
            result = cli._access_rule_activation_result(None, 'internet-access', 'test-internet')
        self.assertEqual(result, 1)

    def test_live_remote_sigstop_healthz_fails_closed(self):
        plane = type('Live', (), {'root': None})()
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.read_text', return_value='{"access_plugin_addr":"127.0.0.1:6101"}'), \
             mock.patch('urllib.request.urlopen', side_effect=TimeoutError('frozen')):
            self.assertIn('/healthz failed', cli._verify_access_rule_runtime(plane, 'remote-access'))

    def test_live_egress_both_units_stopped_fails_closed(self):
        plane = type('Live', (), {'root': None})()
        inactive = subprocess.CompletedProcess(['systemctl'], 3, stdout='inactive\n', stderr='')
        with mock.patch('subprocess.run', return_value=inactive):
            self.assertIn('inactive', cli._verify_access_rule_runtime(plane, 'internet-access'))

    def test_no_false_claim_for_non_live_test_root(self):
        plane = type('Test', (), {'root': '/tmp/fixture'})()
        with mock.patch('subprocess.run') as runner:
            self.assertIsNone(cli._verify_access_rule_runtime(plane, 'internet-access'))
            runner.assert_not_called()

    def test_active_runtime_returns_zero(self):
        with mock.patch('drlink_v24_cli._verify_access_rule_runtime', return_value=None):
            self.assertEqual(cli._access_rule_activation_result(None, 'remote-access', 'a'), 0)
            self.assertEqual(cli._access_rule_activation_result(None, 'internet-access', 'b'), 0)


if __name__ == '__main__':
    unittest.main()
