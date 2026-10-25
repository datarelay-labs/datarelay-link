#!/usr/bin/env python3
"""Agent Bundle preview resolves current Server dependencies without local writes."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_control_plane import ControlPlane, ControlPlaneError
import drlink_v24 as v24
from drlink_v24_bundle import prepare_v24_plan


class FreshCatalog(unittest.TestCase):
    def test_partial_patch_reads_current_catalog_and_rejects_deleted_dependency(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            'DRLINK_SKIP_ACTIVATION': '1', 'DRLINK_SERVER_REACHABLE': '0'}):
            cfg = Path(root, 'etc/frp'); cfg.mkdir(parents=True)
            (cfg / 'client-state.json').write_text(json.dumps({'machine_id':'a' * 32, 'hostname':'agent'}))
            (cfg / 'frpc.toml').write_text('[common]\n')
            plane = ControlPlane(root)
            try:
                v24.set_service_object(plane, 'fresh-service', type='tcp', port=18092, oneshot=True)
                v24.set_remote_service_agent(plane, 'publication', destination='this-host',
                    service='fresh-service', enabled=True, oneshot=True, root=root, server_reachable=False)
                plane.conn.execute("DELETE FROM service_objects WHERE name='fresh-service'")
                bundle = 'configurationBundle:\n  context: agent\n  remoteServices:\n    - name: publication\n      enabled: false\n'
                with patch('drlink_mgmt_sync.use_live_mgmt_path', return_value=True), \
                     patch.object(v24, 'detect_server_reachable', return_value=True), \
                     patch('drlink_mgmt_sync.fetch_server_catalog') as fetch:
                    fetch.return_value = {'serviceObjects':[{'id':'sobj-live', 'name':'fresh-service', 'type':'tcp', 'port':18092, 'generation':1}]}
                    self.assertFalse(prepare_v24_plan(plane, bundle).no_change)
                    self.assertEqual(plane.conn.execute('SELECT COUNT(*) FROM agent_object_catalog').fetchone()[0], 0)
                    fetch.return_value = {'serviceObjects':[]}
                    with self.assertRaises(ControlPlaneError):
                        prepare_v24_plan(plane, bundle)
            finally:
                plane.close()


if __name__ == '__main__':
    unittest.main()
