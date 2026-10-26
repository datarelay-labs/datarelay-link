#!/usr/bin/env python3
"""Server rejects duplicate effective bindings before endpoint/state mutation."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_control_plane import ControlPlane
import drlink_v24 as v24
import drlink_mgmt_sync as mgmt

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['DRLINK_SKIP_ACTIVATION'] = '1'
        self.plane = ControlPlane(self.tmp.name)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_service_object(self.plane, 'ssh', type='tcp', port=22, oneshot=True)
        v24.set_service_object(self.plane, 'web', type='tcp', port=80, oneshot=True)
        self.owner = 'a' * 32
        self.plane.upsert_client(self.owner, label='agent-a', hostname='agent-a')
        self.auth = mgmt.MgmtAuthContext(self.owner, {}, 'nonce', 1)
    def tearDown(self):
        self.plane.close()
        self.tmp.cleanup()
    def put(self, name, destination='this-host', service='ssh', enabled=True, auth=None):
        return mgmt.server_upsert_remote_service(self.plane, auth or self.auth,
            dict(name=name, destination=destination, service=service, enabled=enabled))
    def test_alias_duplicate_rejected_without_writes(self):
        first = self.put('original')
        before = '\n'.join(self.plane.conn.iterdump())
        for destination in ('this-host', 'self', 'agent-a'):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(mgmt.MgmtSyncError, 'already uses.*original'):
                    self.put('duplicate', destination)
                self.assertEqual(before, '\n'.join(self.plane.conn.iterdump()))
        self.assertEqual(first['endpoint_port'], self.put('ORIGINAL', enabled=False)['endpoint_port'])
        with self.assertRaises(mgmt.MgmtSyncError):
            self.put('duplicate')  # Disabled desired services still reserve their binding.
    def test_rebind_rejected_and_distinct_owner_allowed(self):
        self.put('original')
        self.put('other', service='web')
        before = '\n'.join(self.plane.conn.iterdump())
        with self.assertRaises(mgmt.MgmtSyncError):
            self.put('other', service='ssh')
        self.assertEqual(before, '\n'.join(self.plane.conn.iterdump()))
        owner = 'b' * 32
        self.plane.upsert_client(owner, label='agent-b', hostname='agent-b')
        self.put('original', auth=mgmt.MgmtAuthContext(owner, {}, 'n', 2))

    def test_address_aliases_reject_before_endpoint_or_state_mutation(self):
        for kind, first, second in (
            ('ip', '192.0.2.40', '192.0.2.40'),
            ('ip', '2001:db8::40', '2001:0db8:0:0:0:0:0:40'),
            ('fqdn', 'Example.COM', 'example.com'),
        ):
            with self.subTest(kind=kind, address=first):
                suffix = str(len(list(self.plane.conn.execute('SELECT * FROM objects'))))
                a, b = 'target-a-' + suffix, 'target-b-' + suffix
                v24.set_network_object(self.plane, a, type=kind, value=first, oneshot=True)
                v24.set_network_object(self.plane, b, type=kind, value=second, oneshot=True)
                original = 'original-' + suffix
                self.put(original, destination=a, service='web')
                before = '\n'.join(self.plane.conn.iterdump())
                with self.assertRaisesRegex(mgmt.MgmtSyncError, 'already uses.*' + original):
                    self.put('duplicate-' + suffix, destination=b, service='web')
                self.assertEqual(before, '\n'.join(self.plane.conn.iterdump()))

    def test_alias_rebind_rejected_but_distinct_address_allowed(self):
        for name, value in (('a', '192.0.2.40'), ('alias-a', '192.0.2.40'), ('b', '192.0.2.41')):
            v24.set_network_object(self.plane, name, type='ip', value=value, oneshot=True)
        self.put('original', destination='a', service='web', enabled=False)
        other = self.put('other', destination='b', service='web')
        before = '\n'.join(self.plane.conn.iterdump())
        with self.assertRaisesRegex(mgmt.MgmtSyncError, 'already uses.*original'):
            self.put('other', destination='alias-a', service='web')
        self.assertEqual(before, '\n'.join(self.plane.conn.iterdump()))
        self.assertEqual(other['endpoint_port'], self.put('other', destination='b', service='web')['endpoint_port'])

    def test_explicit_ipv4_loopback_alias_cannot_duplicate_this_host(self):
        self.put('original')
        v24.set_network_object(self.plane, 'loopback-address', type='ip', value='127.0.0.1', oneshot=True)
        before = '\n'.join(self.plane.conn.iterdump())
        with self.assertRaisesRegex(mgmt.MgmtSyncError, 'already uses.*original'):
            self.put('duplicate', destination='loopback-address')
        self.assertEqual(before, '\n'.join(self.plane.conn.iterdump()))

    def test_binding_uses_current_object_value_not_stale_publication_target(self):
        for name, value in (('a', '192.0.2.40'), ('alias-new', '192.0.2.41')):
            v24.set_network_object(self.plane, name, type='ip', value=value, oneshot=True)
        self.put('original', destination='a', service='web')
        v24.set_network_object(self.plane, 'a', value='192.0.2.41', oneshot=True, confirm=True)
        before = '\n'.join(self.plane.conn.iterdump())
        with self.assertRaisesRegex(mgmt.MgmtSyncError, 'already uses.*original'):
            self.put('duplicate', destination='alias-new', service='web')
        self.assertEqual(before, '\n'.join(self.plane.conn.iterdump()))

if __name__ == '__main__': unittest.main()
