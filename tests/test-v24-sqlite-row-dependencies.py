#!/usr/bin/env python3
"""Reconnect dependency checks accept the ControlPlane's native SQLite rows."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_control_plane import ControlPlane
import drlink_v24 as v24


class NativeRowDependencies(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'DRLINK_SKIP_ACTIVATION': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plane = ControlPlane(self.tmp.name)
        self.addCleanup(self.plane.close)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_network_object(self.plane, 'lan', type='ip', value='192.0.2.10', oneshot=True)
        v24.set_network_object(self.plane, 'subnet', type='cidr', value='192.0.2.0/24', oneshot=True)
        self.client_id = 'a' * 32
        self.plane.upsert_client(self.client_id, label='agent-one', hostname='agent-one')

    def test_ip_destination_remains_valid_without_database_mutation(self):
        before = list(self.plane.conn.iterdump())
        self.assertIsNone(v24._destination_dependency_status(self.plane, 'lan', root=self.tmp.name))
        self.assertEqual(before, list(self.plane.conn.iterdump()))

    def test_cidr_destination_is_rejected_with_clear_reason(self):
        reason = v24._destination_dependency_status(self.plane, 'subnet', root=self.tmp.name)
        self.assertIn('CIDR', reason)
        self.assertIn('not a valid single target', reason)

    def test_managed_host_resolves_immutable_id_from_endpoint_link(self):
        self.assertEqual(self.client_id, v24._managed_host_client_id_from_name(self.plane, 'agent-one'))

    def test_missing_destination_stays_fail_closed(self):
        reason = v24._destination_dependency_status(self.plane, 'removed', root=self.tmp.name)
        self.assertIn('missing or invalid', reason)
        self.assertIsNone(v24._managed_host_client_id_from_name(self.plane, 'removed'))


if __name__ == '__main__':
    unittest.main()
