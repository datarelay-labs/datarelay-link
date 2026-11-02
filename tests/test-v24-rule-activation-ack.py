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

    def test_live_egress_active_unit_with_unhealthy_effective_policy_fails(self):
        plane = type('Live', (), {'root': None})()
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.read_text', return_value='{"policy_healthy":false,"healthy":false,"listeners":[]}'):
            reason = cli._verify_access_rule_runtime(plane, 'internet-access')
        self.assertIsNotNone(reason)
        self.assertIn('unhealthy', reason.lower())

    def test_live_fixed_tcp_busy_port_missing_effective_listener_fails(self):
        from types import SimpleNamespace
        plane = SimpleNamespace(root=None, conn=mock.MagicMock())
        plane.conn.execute.return_value = [
            {'id':'relay1','name':'busy','enabled':1,'listen_port':6155,
             'dest_host':'127.0.0.1','dest_port':22},
        ]
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        def effective(path, **_kwargs):
            if 'tcp-egress' in str(path):
                return '{"healthy":true,"listeners":[],"policy_generation":3}'
            return '{"policy_healthy":true,"listen_port":6100,"policy_generation":3}'
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.read_text', autospec=True, side_effect=effective):
            reason = cli._verify_access_rule_runtime(plane, 'internet-access')
        self.assertIsNotNone(reason)
        self.assertIn('relay1', reason.lower())

    def test_fixed_tcp_relay_bind_collision_keeps_worker_alive_without_listener(self):
        # Real loopback bind collision, not a simulated socket error: the
        # sync loop catches the failure while its supervisor remains active.
        import importlib.util
        import socket
        from types import SimpleNamespace
        root = Path(__file__).resolve().parents[1]
        module_path = root / 'server/drlink-tcp-egress.py'
        spec = importlib.util.spec_from_file_location('drlink_tcp_egress_activation_test', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen(1)
            port = occupied.getsockname()[1]
            state = SimpleNamespace(_servers={}, cache=mock.MagicMock())
            state.cache.snapshot.return_value = (None, None, None, None)
            with mock.patch.object(module, '_desired_enabled_relays',
                                   return_value={'relay1':('127.0.0.1', port)}), \
                 mock.patch('sys.stderr', new_callable=io.StringIO) as err:
                module.sync_listeners(state)
            self.assertEqual(state._servers, {})
            self.assertIn('failed to bind tcp relay relay1', err.getvalue())
        # The same port can bind again after the competing listener exits.
        with socket.socket() as recovered:
            recovered.bind(('127.0.0.1', port))
            recovered.listen(1)

    def test_live_egress_effective_listener_matching_desired_is_verified(self):
        from types import SimpleNamespace
        plane = SimpleNamespace(root=None, conn=mock.MagicMock())
        plane.conn.execute.return_value = [
            {'id':'relay1','name':'ready','enabled':1,'listen_port':6156,
             'dest_host':'127.0.0.1','dest_port':22},
        ]
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        def effective(path, **_kwargs):
            if 'tcp-egress' in str(path):
                return '{"healthy":true,"listeners":[{"relay_id":"relay1","listen":"0.0.0.0:6156"}],"policy_generation":4}'
            return '{"policy_healthy":true,"listen_port":6100,"policy_generation":4}'
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.read_text', autospec=True, side_effect=effective):
            self.assertIsNone(cli._verify_access_rule_runtime(plane, 'internet-access'))

    def test_live_egress_active_unit_with_missing_snapshot_fails_closed(self):
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        plane = type('Live', (), {'root': None})()
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.read_text', side_effect=FileNotFoundError):
            self.assertIn('unreadable', cli._verify_access_rule_runtime(plane, 'internet-access'))

    def test_live_egress_stale_effective_snapshot_after_commit_fails_closed(self):
        from types import SimpleNamespace
        plane = SimpleNamespace(root=None, conn=mock.MagicMock())
        plane.conn.execute.return_value = []
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.stat',
                        return_value=SimpleNamespace(st_mtime=1000.0)):
            reason = cli._verify_access_rule_runtime(
                plane, 'internet-access', after=2000.0, max_freshness_wait_seconds=0
            )
        self.assertIsNotNone(reason)
        self.assertIn('refreshed', reason.lower())

    def test_live_egress_fresh_effective_snapshot_after_commit_accepts(self):
        from types import SimpleNamespace
        plane = SimpleNamespace(root=None, conn=mock.MagicMock())
        plane.conn.execute.return_value = []
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        def effective(path, **_kwargs):
            if 'tcp-egress' in str(path):
                return '{"healthy":true,"listeners":[],"policy_generation":3}'
            return '{"policy_healthy":true,"listen_port":6100,"policy_generation":3}'
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.read_text', autospec=True, side_effect=effective), \
             mock.patch('pathlib.Path.stat',
                        return_value=SimpleNamespace(st_mtime=2001.0)):
            self.assertIsNone(cli._verify_access_rule_runtime(
                plane, 'internet-access', after=2000.0, max_freshness_wait_seconds=0
            ))

    def test_live_egress_bounded_post_commit_refresh_then_success(self):
        from types import SimpleNamespace
        plane = SimpleNamespace(root=None, conn=mock.MagicMock())
        plane.conn.execute.return_value = []
        active = subprocess.CompletedProcess(['systemctl'], 0, stdout='active\n', stderr='')
        calls = [0]
        def stat(_path):
            calls[0] += 1
            return SimpleNamespace(st_mtime=1000.0 if calls[0] == 1 else 2001.0)
        def effective(path, **_kwargs):
            if 'tcp-egress' in str(path):
                return '{"healthy":true,"listeners":[],"policy_generation":3}'
            return '{"policy_healthy":true,"listen_port":6100,"policy_generation":3}'
        with mock.patch('subprocess.run', return_value=active), \
             mock.patch('pathlib.Path.read_text', autospec=True, side_effect=effective), \
             mock.patch('pathlib.Path.stat', autospec=True, side_effect=stat), \
             mock.patch('time.sleep') as sleeper:
            reason = cli._verify_access_rule_runtime(
                plane, 'internet-access', after=2000.0,
                max_freshness_wait_seconds=1
            )
        self.assertIsNone(reason)
        self.assertGreaterEqual(calls[0], 3)
        sleeper.assert_called_once_with(0.25)

    def test_live_skip_activation_is_not_success(self):
        plane = type('Live', (), {'root': None})()
        with mock.patch.dict('os.environ', {'DRLINK_SKIP_ACTIVATION': 'true'}), \
             mock.patch('subprocess.run') as runner:
            self.assertIn('explicitly skipped', cli._verify_access_rule_runtime(plane, 'remote-access'))
            runner.assert_not_called()

    def test_no_false_claim_for_non_live_test_root(self):
        plane = type('Test', (), {'root': '/tmp/fixture'})()
        with mock.patch('subprocess.run') as runner:
            self.assertIsNone(cli._verify_access_rule_runtime(plane, 'internet-access'))
            runner.assert_not_called()

    def test_active_runtime_returns_zero(self):
        with mock.patch('drlink_v24_cli._verify_access_rule_runtime', return_value=None) as check:
            self.assertEqual(cli._access_rule_activation_result(None, 'remote-access', 'a'), 0)
            self.assertEqual(cli._access_rule_activation_result(None, 'internet-access', 'b'), 0)
        # The barrier is computed after the mutation and passed to the verifier.
        self.assertGreater(check.call_args.kwargs['after'], 0)


if __name__ == '__main__':
    unittest.main()
