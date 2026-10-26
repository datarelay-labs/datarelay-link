#!/usr/bin/env python3
"""Healthy policy updates must never publish a half-activated generation."""
import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_control_plane import ControlPlane
import drlink_v24 as v24
import drlink_runtime_policy as policy
from drlink_v24_bundle import prepare_v24_plan, apply_v24_plan


class GenerationAtomicity(unittest.TestCase):
    def test_failed_bundle_compile_restores_runtime_without_publishing_revision(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'DRLINK_SKIP_ACTIVATION': '0'}):
            plane = ControlPlane(root)
            observer = ControlPlane(root, read_only=True)
            try:
                plane.compile_runtime()
                revision = plane.current_revision()
                artifacts = plane._runtime_activation_snapshot()
                plan = prepare_v24_plan(plane, '''configurationBundle:
  context: server
  networkObjects:
    - name: failed-bundle-object
      type: ip
      value: 192.0.2.81
''')
                def fail_after_partial_artifact():
                    self.assertFalse(observer.status()['mismatch'])
                    (plane.runtime / 'remote-access.json').write_bytes(b'partial failed compile')
                    raise RuntimeError('controlled compile failure')
                with patch.object(plane, 'compile_runtime', side_effect=fail_after_partial_artifact):
                    with self.assertRaisesRegex(Exception, 'Previous configuration was restored'):
                        apply_v24_plan(plane, plan, confirm=True)
                self.assertEqual(revision, plane.current_revision())
                self.assertIsNone(plane.get_object('failed-bundle-object'))
                self.assertEqual(artifacts, plane._runtime_activation_snapshot())
                self.assertFalse(observer.status()['mismatch'])
            finally:
                observer.close()
                plane.close()

    def test_bundle_commit_keeps_generation_coherent_for_live_readers(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'DRLINK_SKIP_ACTIVATION': '0'}):
            plane = ControlPlane(root)
            observer = ControlPlane(root, read_only=True)
            try:
                plane.compile_runtime()
                plan = prepare_v24_plan(plane, '''configurationBundle:
  context: server
  networkObjects:
    - name: unrelated-catalog-object
      type: ip
      value: 192.0.2.80
''')
                states = []
                original = plane._commit_open_transaction
                def observe_commit():
                    original()
                    states.append(observer.status())
                plane._commit_open_transaction = observe_commit
                apply_v24_plan(plane, plan, confirm=True)
                self.assertTrue(states)
                self.assertTrue(all(s['db_healthy'] and not s['mismatch'] for s in states), states)
            finally:
                observer.close()
                plane.close()

    def test_status_is_pinned_across_a_concurrent_healthy_commit(self):
        with tempfile.TemporaryDirectory() as root:
            writer = ControlPlane(root)
            writer.compile_runtime()
            reader = ControlPlane(root, read_only=True)
            original = reader.current_revision
            raced = []
            def concurrent_commit():
                revision = original()
                if not raced:
                    raced.append(True)
                    v24.set_network_object(writer, 'racing-source', type='ip', value='192.0.2.9', oneshot=True)
                return revision
            reader.current_revision = concurrent_commit
            try:
                status = reader.status()
                self.assertFalse(status['mismatch'], status)
                self.assertFalse(reader.conn.in_transaction)
                self.assertLess(status['revision'], writer.current_revision())
            finally:
                reader.close()
                writer.close()

    def test_isolated_request_validates_commit_after_cache_reload(self):
        with tempfile.TemporaryDirectory() as root:
            writer = ControlPlane(root)
            writer.compile_runtime()
            cfg = Path(root, 'etc/drlink/config.json')
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(json.dumps({'control_plane_root': root}))
            cache = policy.ControlPlaneCache(cfg)
            original = cache.reload
            def commit_after_reload(*args, **kwargs):
                original(*args, **kwargs)
                v24.set_network_object(writer, 'fresh-source', type='ip', value='192.0.2.10', oneshot=True)
            cache.reload = commit_after_reload
            isolated = None
            try:
                isolated, error, _cfg = cache.open_isolated()
                self.assertIsNone(error)
                self.assertEqual(isolated._validated_revision, writer.current_revision())
                self.assertTrue(policy.generation_status(
                    isolated, 'internet', validated_revision=isolated._validated_revision)['healthy'])
                # An actual failed generation is still rejected on a fresh read.
                isolated.close()
                isolated = None
                cache.reload = original
                writer.force_generation_mismatch('internet')
                isolated, error, _cfg = cache.open_isolated()
                self.assertIsNone(isolated)
                self.assertIsNotNone(error)
            finally:
                if isolated:
                    isolated.close()
                cache._close_cached_plane()
                writer.close()

    def test_mutation_commits_policy_and_generation_together(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'FRP_DEPLOY_TEST_ROOT': ''}):
            plane = ControlPlane(root)
            observer = ControlPlane(root, read_only=True)
            try:
                plane.compile_runtime()
                states = []
                original = plane._commit_open_transaction
                def observe_commit():
                    original()
                    states.append(observer.status())
                plane._commit_open_transaction = observe_commit
                v24.set_network_object(plane, 'new-source', type='ip', value='192.0.2.8', oneshot=True)
                self.assertTrue(states)
                self.assertTrue(all(s['db_healthy'] and not s['mismatch'] for s in states), states)
            finally:
                observer.close()
                plane.close()


if __name__ == '__main__':
    unittest.main()
