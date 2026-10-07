#!/usr/bin/env python3
"""Public terminal catalog reads announce waits without changing failure safety."""
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import drlink_mgmt_sync as mgmt

class Terminal(io.StringIO):
    def isatty(self): return True

class CatalogProgressTests(unittest.TestCase):
    def test_terminal_sees_progress_before_request_and_unchanged_auth_failure(self):
        output = Terminal()
        error = mgmt.MgmtAuthError('identity rejected')
        def request(*args, **kwargs):
            self.assertIn('Checking Server catalog', output.getvalue())
            self.assertEqual(kwargs['timeout'], 8.0)
            raise error
        with mock.patch.object(mgmt, 'resolve_mgmt_base_url', return_value='https://example.test'), \
             mock.patch.object(mgmt, '_request_json', side_effect=request), \
             mock.patch.object(mgmt.sys, 'stderr', output):
            with self.assertRaises(mgmt.MgmtAuthError) as caught: mgmt.fetch_server_catalog('/fixture')
        self.assertIs(caught.exception, error)
        self.assertIn('request failed', output.getvalue())
        self.assertNotIn('received', output.getvalue())

    def test_nonterminal_machine_output_remains_quiet(self):
        output = io.StringIO(); payload = {'serviceObjects': []}
        with mock.patch.object(mgmt, 'resolve_mgmt_base_url', return_value='https://example.test'), \
             mock.patch.object(mgmt, '_request_json', return_value=payload), \
             mock.patch.object(mgmt.sys, 'stderr', output):
            self.assertIs(mgmt.fetch_server_catalog('/fixture'), payload)
        self.assertEqual(output.getvalue(), '')


class RemoteServiceProgressTests(unittest.TestCase):
    def test_offline_set_announces_before_reachability_and_runtime(self):
        import drlink_v24_cli as cli
        output = Terminal(); plane = mock.Mock(root='/fixture')
        def reachable(*args):
            self.assertIn('Updating Remote Service', output.getvalue())
            return False
        def apply(*args, **kwargs):
            self.assertIn('Updating Remote Service', output.getvalue())
            self.assertFalse(kwargs['server_reachable'])
            return {'view': {'name': 'web', 'destination': 'this-host', 'service': 'http', 'status': 'DISABLED', 'endpoint': '203.0.113.1:6000'}}
        with mock.patch.object(cli, '_require_agent'), \
             mock.patch.object(cli.v24, 'detect_server_reachable', side_effect=reachable), \
             mock.patch.object(cli.v24, 'set_remote_service_agent', side_effect=apply), \
             mock.patch.object(cli.sys, 'stderr', output), mock.patch.object(cli.sys, 'stdout', io.StringIO()):
            self.assertEqual(cli.handle_set(plane, ['remote-service', 'web', 'destination', 'this-host', 'service', 'http', 'disabled']), 0)

    def test_cancelled_delete_does_not_announce_or_start_work(self):
        import drlink_v24_cli as cli
        import drlink_control_cli as control
        output = Terminal(); plane = mock.Mock(root='/fixture')
        with mock.patch.object(cli, '_require_agent'), mock.patch.object(control, '_stdin_is_interactive', return_value=True), \
             mock.patch.object(control, '_confirm_from_stdin', return_value=False), \
             mock.patch.object(cli.v24, 'detect_server_reachable') as reachable, \
             mock.patch.object(cli.sys, 'stderr', output), mock.patch.object(cli.sys, 'stdout', io.StringIO()):
            self.assertEqual(cli.handle_unset(plane, ['remote-service', 'web']), 1)
        reachable.assert_not_called(); self.assertEqual(output.getvalue(), '')

    def test_confirmed_delete_announces_before_reachability(self):
        import drlink_v24_cli as cli
        import drlink_control_cli as control
        output = Terminal(); plane = mock.Mock(root='/fixture')
        def reachable(*args):
            self.assertIn('Removing Remote Service', output.getvalue())
            return False
        with mock.patch.object(cli, '_require_agent'), mock.patch.object(control, '_stdin_is_interactive', return_value=True), \
             mock.patch.object(control, '_confirm_from_stdin', return_value=True), \
             mock.patch.object(cli.v24, 'detect_server_reachable', side_effect=reachable), \
             mock.patch.object(cli.v24, 'unset_remote_service_agent') as remove, \
             mock.patch.object(cli.sys, 'stderr', output), mock.patch.object(cli.sys, 'stdout', io.StringIO()):
            self.assertEqual(cli.handle_unset(plane, ['remote-service', 'web']), 0)
        remove.assert_called_once_with(plane, 'web', root='/fixture', server_reachable=False)

    def test_nonterminal_set_preserves_normal_result_output(self):
        import drlink_v24_cli as cli
        error_output = io.StringIO(); result_output = io.StringIO(); plane = mock.Mock(root='/fixture')
        view = {'name': 'web', 'destination': 'this-host', 'service': 'http',
                'status': 'DISABLED', 'endpoint': '203.0.113.1:6000'}
        with mock.patch.object(cli, '_require_agent'), \
             mock.patch.object(cli.v24, 'detect_server_reachable', return_value=False), \
             mock.patch.object(cli.v24, 'set_remote_service_agent', return_value={'view': view}), \
             mock.patch.object(cli.sys, 'stderr', error_output), mock.patch.object(cli.sys, 'stdout', result_output):
            self.assertEqual(cli.handle_set(plane, ['remote-service', 'web', 'destination', 'this-host', 'service', 'http', 'disabled']), 0)
        self.assertEqual(error_output.getvalue(), '')
        self.assertEqual(result_output.getvalue(), cli.v24.format_remote_service_view(view))

if __name__ == '__main__': unittest.main()
