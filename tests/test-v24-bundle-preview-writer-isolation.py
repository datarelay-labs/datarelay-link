#!/usr/bin/env python3
"""Planning a Bundle must not contend for the authoritative DB writer slot."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_control_plane import ControlPlane
from drlink_v24_bundle import prepare_v24_plan, apply_v24_plan

BUNDLE = '''configurationBundle:
  context: server
  networkObjects:
    - name: preview-source
      type: ip
      value: 192.0.2.7
'''


class BundlePreviewWriterIsolation(unittest.TestCase):
    def test_plan_during_another_writer_then_apply(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
                'FRP_DEPLOY_TEST_ROOT': root, 'DRLINK_SKIP_ACTIVATION': '1'}):
            plane = ControlPlane(root)
            writer = ControlPlane(root)
            try:
                revision = plane.current_revision()
                plane.conn.execute('PRAGMA busy_timeout=50')
                writer.conn.execute('BEGIN IMMEDIATE')
                try:
                    plan = prepare_v24_plan(plane, BUNDLE)
                    self.assertFalse(plan.no_change)
                    self.assertIsNone(plane.get_object('preview-source'))
                    self.assertEqual(plane.current_revision(), revision)
                    self.assertFalse(plane.conn.in_transaction)
                finally:
                    writer.conn.rollback()
                self.assertEqual(apply_v24_plan(plane, plan)['status'], 'APPLIED')
                self.assertIsNotNone(plane.get_object('preview-source'))
            finally:
                writer.close()
                plane.close()


if __name__ == '__main__':
    unittest.main()
