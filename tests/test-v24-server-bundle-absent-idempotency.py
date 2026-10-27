#!/usr/bin/env python3
"""F020: repeated Server desired absence converges without a delete or revision."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from drlink_control_plane import ControlPlane, ControlPlaneError
import drlink_v24 as v24
from drlink_v24_bundle import apply_v24_plan, prepare_v24_plan

ABSENT = '''configurationBundle:
  context: server
  networkObjects:
  - {name: missing-network, state: absent}
  networkGroups:
  - {name: missing-network-group, state: absent}
  serviceObjects:
  - {name: missing-service, state: absent}
  serviceGroups:
  - {name: missing-service-group, state: absent}
  permissionObjects:
  - {name: missing-permission, state: absent}
  permissionGroups:
  - {name: missing-permission-group, state: absent}
'''

class ServerAbsenceIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='drlink-server-absence-')
        root = Path(self.tmp.name)
        (root/'etc/drlink').mkdir(parents=True)
        (root/'etc/drlink/config.json').write_text('{"role":"server"}\n')
        self.env = patch.dict(os.environ, {'FRP_DEPLOY_TEST_ROOT': str(root),
            'DRLINK_CONFIRM': 'yes', 'DRLINK_SKIP_ACTIVATION': '1'})
        self.env.start()
        self.plane = ControlPlane(str(root))
        v24.ensure_v2_schema(self.plane.conn)
    def tearDown(self):
        self.plane.close(); self.env.stop(); self.tmp.cleanup()
    def test_missing_resources_converge_without_mutation(self):
        before = self.plane.current_revision()
        plan = prepare_v24_plan(self.plane, ABSENT, role='server')
        self.assertTrue(plan.no_change, plan.changes)
        self.assertEqual(apply_v24_plan(self.plane, plan)['status'], 'NO_CHANGE')
        self.assertEqual(self.plane.current_revision(), before)
    def test_group_dependencies_deleted_before_objects_then_casefold_no_change(self):
        v24.set_service_object(self.plane, 'missing-service', type='tcp', port=18081, oneshot=True)
        v24.set_service_group(self.plane, 'missing-service-group', members=['missing-service'], oneshot=True)
        plan = prepare_v24_plan(self.plane, ABSENT, role='server')
        self.assertEqual(apply_v24_plan(self.plane, plan)['status'], 'APPLIED')
        again = prepare_v24_plan(self.plane, ABSENT.replace('missing-', 'MISSING-'), role='server')
        self.assertTrue(again.no_change)

    def test_direct_unset_retains_unknown_resource_error(self):
        with self.assertRaises(ControlPlaneError):
            v24.unset_service_group(self.plane, 'missing-service-group')

    def test_existing_object_deleted_once_then_absence_is_no_change(self):
        v24.set_service_object(self.plane, 'missing-service', type='tcp', port=18081, oneshot=True)
        plan = prepare_v24_plan(self.plane, ABSENT, role='server')
        self.assertEqual(apply_v24_plan(self.plane, plan)['status'], 'APPLIED')
        before = self.plane.current_revision()
        again = prepare_v24_plan(self.plane, ABSENT, role='server')
        self.assertTrue(again.no_change, again.changes)
        self.assertEqual(apply_v24_plan(self.plane, again)['status'], 'NO_CHANGE')
        self.assertEqual(self.plane.current_revision(), before)

if __name__ == '__main__': unittest.main()
