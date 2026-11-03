#!/usr/bin/env python3
"""A mismatched/failed runtime generation must be reconciled, never hidden.

Regression for the activation + rollback double fault found by S-009/S-021:
the generation was left in 'mismatch' (enforcement fail-closed) while
  1. re-applying the same configuration printed a false NO CHANGE,
  2. `show internet-access` still advertised Readiness READY.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_control_plane import ControlPlane, ControlPlaneError
import drlink_v24 as v24
from drlink_v24_bundle import prepare_v24_plan, apply_v24_plan

BUNDLE = '''configurationBundle:
  context: server
  networkObjects:
    - name: reconcile-object
      type: ip
      value: 192.0.2.90
'''


class RuntimeGenerationReconcile(unittest.TestCase):
    def _plane_with_applied_bundle(self, root):
        plane = ControlPlane(root)
        plane.compile_runtime()
        result = apply_v24_plan(plane, prepare_v24_plan(plane, BUNDLE), confirm=True)
        self.assertEqual(result['status'], 'APPLIED')
        return plane

    def test_same_state_reapply_without_mismatch_is_still_no_change(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'DRLINK_SKIP_ACTIVATION': '0'}):
            plane = self._plane_with_applied_bundle(root)
            try:
                rev = plane.current_revision()
                self.assertFalse(v24.runtime_generation_mismatch(plane))
                result = apply_v24_plan(plane, prepare_v24_plan(plane, BUNDLE), confirm=True)
                self.assertEqual(result['status'], 'NO_CHANGE')
                self.assertEqual(rev, plane.current_revision())
            finally:
                plane.close()

    def test_same_state_reapply_reconciles_a_mismatched_generation(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'DRLINK_SKIP_ACTIVATION': '0'}):
            plane = self._plane_with_applied_bundle(root)
            try:
                rev = plane.current_revision()
                plane._mark_generation_failed('activation failed; rollback incomplete')
                plane.conn.commit()
                self.assertTrue(plane.status()['mismatch'])
                self.assertTrue(v24.runtime_generation_mismatch(plane))

                result = apply_v24_plan(plane, prepare_v24_plan(plane, BUNDLE), confirm=True)

                self.assertEqual(result['status'], 'RECONCILED', result)
                self.assertEqual(rev, plane.current_revision(), 'reconcile must not invent a configuration revision')
                self.assertFalse(plane.status()['mismatch'])
                self.assertFalse(v24.runtime_generation_mismatch(plane))
                gens = plane.status()['generations']
                self.assertEqual(gens['internet']['status'], 'active')
                self.assertEqual(gens['internet']['generation'], rev)
                # And it is stable: the next identical apply is a true NO CHANGE.
                again = apply_v24_plan(plane, prepare_v24_plan(plane, BUNDLE), confirm=True)
                self.assertEqual(again['status'], 'NO_CHANGE')
            finally:
                plane.close()

    def test_failed_reconcile_stays_fail_closed_and_reports_truthfully(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'DRLINK_SKIP_ACTIVATION': '0'}):
            plane = self._plane_with_applied_bundle(root)
            try:
                plane._mark_generation_failed('activation failed; rollback incomplete')
                plane.conn.commit()
                with patch.object(plane, 'compile_runtime', side_effect=RuntimeError('controlled reconcile failure')):
                    with self.assertRaisesRegex(ControlPlaneError, 'Runtime reconciliation failed'):
                        apply_v24_plan(plane, prepare_v24_plan(plane, BUNDLE), confirm=True)
                self.assertTrue(plane.status()['mismatch'], 'a failed reconcile must not clear the mismatch')
                self.assertTrue(v24.runtime_generation_mismatch(plane))
            finally:
                plane.close()

    def test_readiness_is_never_ready_while_generation_is_mismatched(self):
        ready, recovery = v24.restricted_policy_readiness('internet', 'whitelist', 'enabled')
        self.assertEqual((ready, recovery), ('READY', None))
        for family in ('internet', 'ai'):
            bad, how = v24.restricted_policy_readiness(
                family, 'whitelist', 'enabled', generation_mismatch=True)
            self.assertTrue(bad.startswith('FAIL CLOSED'), bad)
            self.assertNotIn('READY', bad.replace('FAIL CLOSED', ''))
            self.assertIn('system apply configuration', how)

    def test_mismatch_probe_covers_failed_and_mismatch_but_not_healthy(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'DRLINK_SKIP_ACTIVATION': '0'}):
            plane = ControlPlane(root)
            try:
                plane.compile_runtime()
                self.assertFalse(v24.runtime_generation_mismatch(plane))
                plane.conn.execute("UPDATE runtime_generations SET status='failed' WHERE plane='internet'")
                self.assertTrue(v24.runtime_generation_mismatch(plane))
                plane.conn.execute("UPDATE runtime_generations SET status='active' WHERE plane='internet'")
                plane.conn.execute("UPDATE runtime_generations SET status='mismatch' WHERE plane='remote'")
                self.assertTrue(v24.runtime_generation_mismatch(plane))
            finally:
                plane.close()


if __name__ == '__main__':
    unittest.main()
