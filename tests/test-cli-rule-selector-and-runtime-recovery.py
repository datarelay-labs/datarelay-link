#!/usr/bin/env python3
"""Fresh CLI rule selectors and connected-host verification recovery regressions."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import sys
import socket
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import drlink_control_cli as cli
from drlink_control_plane import ControlPlane
import drlink_mgmt_sync as mgmt
import drlink_v24 as v24


class RuleSelectorAndRuntimeRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='drlink-rule-runtime-recovery-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = self.root / 'etc/drlink/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"role":"server"}\n')
        self.env = mock.patch.dict(os.environ, {
            'FRP_DEPLOY_TEST_ROOT': str(self.root), 'DRLINK_SKIP_ACTIVATION': '1',
            'DRLINK_CONFIRM': 'yes',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.plane = ControlPlane(str(self.root))
        self.addCleanup(self.plane.close)
        v24.ensure_v2_schema(self.plane.conn)

    def dispatch(self, tokens):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(tokens, root=str(self.root), plane=self.plane)
        return rc, out.getvalue(), err.getvalue()

    def test_rule_detail_preserves_service_selector_for_show_to_test(self):
        v24.set_network_object(self.plane, 'source', type='ip', value='198.51.100.10', oneshot=True)
        v24.set_network_object(self.plane, 'destination', type='fqdn', value='example.test', oneshot=True)
        # Same protocol/port cannot identify the original named selector.
        for name in ('chosen-service', 'same-port-other-service'):
            v24.set_service_object(self.plane, name, type='tcp', port=443, oneshot=True)
        v24.set_service_group(self.plane, 'chosen-group', members=['chosen-service'], oneshot=True)
        for family, mode in [('remote', 'blacklist'), ('internet', 'whitelist')]:
            for selector in ('chosen-service', 'chosen-group'):
                with self.subTest(family=family, selector=selector):
                    name = family + '-' + selector
                    v24.set_access_rule(self.plane, family, name, mode=mode,
                                        source='source', destination='destination',
                                        service=selector, enabled=True, oneshot=True)
                    revision = self.plane.current_revision()
                    rc, out, err = self.dispatch(['show', family+'-access', name])
                    self.assertEqual(rc, 0, err)
                    self.assertIn('Service: '+selector+'\n', out)
                    self.assertIn('Service details: tcp/443\n', out)
                    # Resolve only the isolated fixture hostname; no network dependency.
                    with mock.patch('socket.getaddrinfo', return_value=[
                        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0))
                    ]):
                        rc, result, err = self.dispatch(['test', family+'-access',
                            'source', 'source', 'destination', 'destination', 'service', selector])
                    self.assertEqual(rc, 0, err)
                    self.assertIn('DENY' if family == 'remote' else 'ALLOW', result)
                    self.assertEqual(self.plane.current_revision(), revision)

    def test_fresh_presence_retries_missing_server_runtime_verification(self):
        machine = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        self.plane.upsert_client(machine, label='fixture-agent', hostname='fixture-agent')
        auth = mgmt.MgmtAuthContext(machine, {}, 'fixture-nonce', 0)
        mgmt.server_report_agent_lifecycle(self.plane, auth, {'state': 'connected'})
        self.plane.set_published_service(machine, 'fixture-service', service_type='tcp',
            target_mode='self', target_host='127.0.0.1', target_port=22,
            enabled=True, public_port=6022)
        service = self.plane.conn.execute('SELECT id FROM published_services WHERE name=?',
                                         ('fixture-service',)).fetchone()['id']
        self.plane.conn.execute('INSERT OR REPLACE INTO remote_service_meta '
            '(service_id,status,pool_class,destination_name,destination_client_id,'
            'pending_allocation,delete_pending,reason,runtime_verified) '
            "VALUES (?,'DEGRADED','normal','this-host',?,0,0,'Runtime verification is missing.',0)",
            (service, machine))
        self.plane.conn.commit()
        revision = self.plane.current_revision()
        for _ in range(2):
            result = mgmt.server_report_agent_lifecycle(self.plane, auth, {'state':'connected'})
            self.assertTrue(result['reconcile_required'])
            meta = self.plane.conn.execute('SELECT runtime_verified,status FROM remote_service_meta '
                                          'WHERE service_id=?', (service,)).fetchone()
            self.assertEqual(meta['runtime_verified'], 0)
            self.assertEqual(meta['status'], 'DEGRADED')
            self.assertEqual(self.plane.current_revision(), revision)
        # Only a separate verified runtime report clears the retry requirement.
        self.plane.conn.execute("UPDATE remote_service_meta SET runtime_verified=1,status='HEALTHY' "
                                'WHERE service_id=?', (service,))
        self.plane.conn.commit()
        self.assertFalse(mgmt.server_report_agent_lifecycle(self.plane, auth,
                                                           {'state':'connected'})['reconcile_required'])
        # A disabled service must not trigger repeated activation.
        self.plane.conn.execute('UPDATE published_services SET enabled=0 WHERE id=?', (service,))
        self.plane.conn.execute("UPDATE remote_service_meta SET runtime_verified=0,status='DISABLED' "
                                'WHERE service_id=?', (service,))
        self.plane.conn.commit()
        self.assertFalse(mgmt.server_report_agent_lifecycle(self.plane, auth,
                                                           {'state':'connected'})['reconcile_required'])

    def test_repeated_identical_signed_status_reports_do_not_write_new_config_revisions(self):
        """Heartbeat status replay must not flood sourceRevision or audit history."""
        machine = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        self.plane.upsert_client(machine, label='fixture-agent', hostname='fixture-agent')
        auth = mgmt.MgmtAuthContext(machine, {}, 'fixture-nonce', 0)
        self.plane.set_published_service(machine, 'fixture-stable', service_type='tcp',
            target_mode='self', target_host='127.0.0.1', target_port=22,
            enabled=False, public_port=6022)
        service = self.plane.conn.execute('SELECT id FROM published_services WHERE name=?',
                                          ('fixture-stable',)).fetchone()['id']
        self.plane.conn.execute('INSERT OR REPLACE INTO remote_service_meta '
            '(service_id,status,pool_class,destination_name,destination_client_id,'
            'pending_allocation,delete_pending,reason,runtime_verified) '
            "VALUES (?,'DISABLED','normal','this-host',?,0,0,'',0)",
            (service, machine))
        self.plane.conn.commit()
        payload = {'services': [{'name':'fixture-stable','status':'DISABLED',
                   'runtime_verified':False, 'endpoint_port':6022,'reason':''}]}
        first = mgmt.server_report_remote_service_status(self.plane, auth, payload)
        after_first = self.plane.current_revision()
        second = mgmt.server_report_remote_service_status(self.plane, auth, payload)
        self.assertEqual(second['services'], first['services'])
        self.assertEqual(self.plane.current_revision(), after_first,
                         'identical status heartbeat must not create a config revision')
        row = self.plane.conn.execute('SELECT status,runtime_verified FROM remote_service_meta '
                                      'WHERE service_id=?',(service,)).fetchone()
        self.assertEqual((row['status'],row['runtime_verified']), ('DISABLED',0))
        # A real mismatch must still repair the Server and create one revision.
        self.plane.conn.execute('UPDATE remote_service_meta SET status=?, reason=? '
                                'WHERE service_id=?', ('DEGRADED','stale report',service))
        self.plane.conn.commit()
        before_repair = self.plane.current_revision()
        repaired = mgmt.server_report_remote_service_status(self.plane, auth, payload)
        self.assertGreater(self.plane.current_revision(), before_repair)
        self.assertEqual(repaired['services'][0]['status'], 'DISABLED')
        self.assertEqual(self.plane.conn.execute('SELECT status FROM remote_service_meta '
                        'WHERE service_id=?',(service,)).fetchone()['status'], 'DISABLED')


if __name__ == '__main__':
    unittest.main()
