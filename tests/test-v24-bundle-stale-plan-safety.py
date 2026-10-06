#!/usr/bin/env python3
"""P0: ConfigurationBundle stale-plan / current-state safety.

Apply must re-diff and recalculate security impact against authoritative state
under a race-safe guard. Stale prepared plans must not:
  - return false NO_CHANGE after concurrent mutation
  - remove the now-last BLACKLIST blocker without current-state confirmation
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ConcurrencyError, ConfirmationRequired, ControlPlane
import drlink_v24 as v24
from drlink_v24_bundle import BundleError, apply_v24_plan, export_configuration_v24, prepare_v24_plan


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class BundleStalePlanSafety(unittest.TestCase):
    def test_concurrent_same_name_create_returns_reviewable_conflict(self):
        barrier = threading.Barrier(2)
        mutate = ControlPlane._mutate
        def synchronized(plane, command, *args, **kwargs):
            if command == 'set network-object race':
                barrier.wait(timeout=10)
            return mutate(plane, command, *args, **kwargs)
        def create(value):
            plane = ControlPlane(self.tmp)
            try:
                return v24.set_network_object(plane, 'race', type='ip', value=value, oneshot=True)
            except Exception as exc:
                return exc
            finally:
                plane.close()
        with mock.patch.object(ControlPlane, '_mutate', synchronized), ThreadPoolExecutor(2) as pool:
            results = list(pool.map(create, ('192.0.2.51', '192.0.2.52')))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1, results)
        error = next(result for result in results if isinstance(result, Exception))
        self.assertIsInstance(error, ConcurrencyError)
        self.assertIn('Review current state and retry', str(error))
        self.assertNotIn('UNIQUE constraint', str(error))
        self.assertEqual(len(self.plane._object_values(self.plane.get_object('race')['id'])), 1)

    def test_conflicting_duplicate_names_reject_before_any_change(self):
        before = self.plane.current_revision()
        with self.assertRaisesRegex(BundleError, 'Duplicate'):
            prepare_v24_plan(self.plane, '''configurationBundle:
  context: server
  networkObjects:
    - name: conflict
      type: ip
      value: 192.0.2.51
    - name: conflict
      type: ip
      value: 192.0.2.52
''')
        self.assertIsNone(self.plane.get_object('conflict'))
        self.assertEqual(self.plane.current_revision(), before)

    def test_agent_test_rejects_missing_service_and_duplicate_binding_readonly(self):
        before = self.plane.current_revision()
        for services in (
            [{'name': 'first', 'destination': 'this-host', 'service': 'ssh', 'enabled': True},
             {'name': 'last', 'destination': 'this-host', 'service': 'missing-service', 'enabled': True}],
            [{'name': 'first', 'destination': 'this-host', 'service': 'ssh', 'enabled': True},
             {'name': 'last', 'destination': 'this-host', 'service': 'ssh', 'enabled': True}],
        ):
            import json
            with self.subTest(services=services), self.assertRaises(BundleError):
                prepare_v24_plan(self.plane, 'configurationBundle: ' + json.dumps({'context': 'agent', 'remoteServices': services}), role='agent')
            self.assertEqual(self.plane.current_revision(), before)
            self.assertEqual(self.plane.conn.execute('SELECT count(*) FROM agent_remote_services').fetchone()[0], 0)

    def test_agent_preview_readonly_never_contacts_server_or_activates(self):
        before = self.plane.current_revision()
        before_audit = self.plane.conn.execute('SELECT count(*) FROM audit_events').fetchone()[0]
        raw = '''configurationBundle:
  context: agent
  remoteServices:
    - name: preview
      destination: this-host
      service: ssh
      enabled: true
'''
        with mock.patch('drlink_v24.detect_server_reachable', side_effect=AssertionError('network probe')), \
             mock.patch('drlink_mgmt_sync.fetch_server_catalog', side_effect=AssertionError('network read')), \
             mock.patch('drlink_mgmt_sync.upsert_remote_service_on_server', side_effect=AssertionError('network write')), \
             mock.patch('drlink_v24_runtime.apply_agent_runtime', side_effect=AssertionError('activation')):
            for readonly in (False, True):
                plane = ControlPlane(self.tmp, read_only=True) if readonly else self.plane
                try:
                    plan = prepare_v24_plan(plane, raw, role='agent')
                    self.assertEqual(len(plan.mutating_changes), 1)
                    self.assertEqual(plane.conn.execute('SELECT count(*) FROM agent_remote_services').fetchone()[0], 0)
                    self.assertEqual(plane.current_revision(), before)
                finally:
                    if readonly:
                        plane.close()
        self.assertEqual(self.plane.conn.execute('SELECT count(*) FROM audit_events').fetchone()[0], before_audit)

    def test_case_insensitive_duplicate_rule_and_resource_rejected(self):
        for section in ('networkObjects', 'remoteServices'):
            context = 'agent' if section == 'remoteServices' else 'server'
            fields = 'destination: this-host\n      service: ssh' if context == 'agent' else 'type: ip\n      value: 192.0.2.51'
            raw = 'configurationBundle:\n  context: %s\n  %s:\n    - name: repeated\n      %s\n    - name: REPEATED\n      %s\n' % (context, section, fields, fields)
            with self.subTest(section=section), self.assertRaisesRegex(BundleError, 'Duplicate'):
                prepare_v24_plan(self.plane, raw, role=context)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-stale-plan-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ.pop("DRLINK_CONFIRM", None)
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def test_stale_no_change_plan_is_rejected_without_overwrite(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        prepared_rev = self.plane.current_revision()
        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.10
""",
        )
        self.assertTrue(plan.no_change)
        self.assertEqual(plan.base_revision, prepared_rev)

        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.20", oneshot=True
        )
        concurrent_rev = self.plane.current_revision()
        self.assertGreater(concurrent_rev, prepared_rev)

        with self.assertRaises(ConcurrencyError) as ctx:
            apply_v24_plan(self.plane, plan)
        self.assertIn("REVISION_CONFLICT", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), concurrent_rev)
        self.assertEqual(
            self.plane._object_values(self.plane.get_object("office")["id"])[:1],
            ["198.51.100.20"],
        )

    def test_true_no_change_remains_idempotent(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        yaml_text = """configurationBundle:
  context: server
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.10
"""
        plan = prepare_v24_plan(self.plane, yaml_text)
        self.assertTrue(plan.no_change)
        rev_before = self.plane.current_revision()
        result = apply_v24_plan(self.plane, plan)
        self.assertEqual(result["status"], "NO_CHANGE")
        self.assertEqual(result["revision"], rev_before)
        self.assertEqual(self.plane.current_revision(), rev_before)

    def test_normal_apply_still_applied(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.30
""",
        )
        self.assertFalse(plan.no_change)
        result = apply_v24_plan(self.plane, plan)
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(
            self.plane._object_values(self.plane.get_object("office")["id"])[:1],
            ["198.51.100.30"],
        )

    def test_exported_bundle_pins_source_revision_and_rejects_stale_apply(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        exported_rev = self.plane.current_revision()
        exported = export_configuration_v24(self.plane)
        self.assertIn("sourceRevision: %s" % exported_rev, exported)

        edited = exported.replace("198.51.100.10", "198.51.100.30", 1)
        plan = prepare_v24_plan(self.plane, edited)
        self.assertEqual(plan.base_revision, exported_rev)
        self.assertFalse(plan.no_change)

        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.20", oneshot=True
        )
        concurrent_rev = self.plane.current_revision()

        with self.assertRaises(ConcurrencyError) as ctx:
            apply_v24_plan(self.plane, plan, confirm=True)
        self.assertIn("REVISION_CONFLICT", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), concurrent_rev)
        self.assertEqual(
            self.plane._object_values(self.plane.get_object("office")["id"])[:1],
            ["198.51.100.20"],
        )

    def test_source_revision_validation_fails_closed(self):
        for token in ("-1", "not-a-revision", "true"):
            with self.subTest(source_revision=token):
                raw = """configurationBundle:
  context: server
  sourceRevision: %s
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.10
""" % token
                with self.assertRaises(Exception) as ctx:
                    prepare_v24_plan(self.plane, raw)
                self.assertIn("sourceRevision", str(ctx.exception))

    def test_stale_plan_cannot_bypass_last_blacklist_confirmation(self):
        v24.set_network_object(self.plane, "src", type="ip", value="198.51.100.1", oneshot=True)
        v24.set_network_object(self.plane, "dst", type="ip", value="198.51.100.2", oneshot=True)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        for name in ("deny1", "deny2"):
            v24.set_access_rule(
                self.plane,
                "remote",
                name,
                mode="blacklist",
                source="src",
                destination="dst",
                service="ssh",
                enabled=True,
                oneshot=True,
            )

        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  remoteAccess:
    mode: blacklist
    enforcement: enabled
    rules:
      - name: deny1
        source: src
        destination: dst
        service: ssh
        enabled: false
      - name: deny2
        source: src
        destination: dst
        service: ssh
        enabled: true
""",
        )
        self.assertFalse(plan.no_change)
        self.assertEqual(plan.security_impact, [])

        # Concurrent writer disables deny2 with confirmation → deny1 is now last blocker.
        v24.set_access_rule(
            self.plane, "remote", "deny2", enabled=False, oneshot=True, confirm=True
        )
        self.assertTrue(bool(self.plane._get_rule("remote", "deny1")["enabled"]))
        self.assertFalse(bool(self.plane._get_rule("remote", "deny2")["enabled"]))

        rev_before = self.plane.current_revision()
        with self.assertRaises(ConcurrencyError) as ctx:
            apply_v24_plan(self.plane, plan, confirm=False)
        self.assertIn("REVISION_CONFLICT", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), rev_before)
        self.assertTrue(bool(self.plane._get_rule("remote", "deny1")["enabled"]))
        self.assertFalse(bool(self.plane._get_rule("remote", "deny2")["enabled"]))

        # The operator must re-review current state. The fresh plan now exposes
        # the broadened-access confirmation that the stale plan could not bypass.
        fresh = prepare_v24_plan(self.plane, plan.source_text)
        with self.assertRaises(ConfirmationRequired) as fresh_ctx:
            apply_v24_plan(self.plane, fresh, confirm=False)
        self.assertTrue(fresh_ctx.exception.impact.get("access_broadened"))
        result = apply_v24_plan(self.plane, fresh, confirm=True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertFalse(bool(self.plane._get_rule("remote", "deny1")["enabled"]))

    def test_confirmation_cancel_leaves_state_unchanged(self):
        v24.set_network_object(self.plane, "src", type="ip", value="198.51.100.1", oneshot=True)
        v24.set_network_object(self.plane, "dst", type="ip", value="198.51.100.2", oneshot=True)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_access_rule(
            self.plane,
            "remote",
            "deny1",
            mode="blacklist",
            source="src",
            destination="dst",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  remoteAccess:
    mode: blacklist
    enforcement: enabled
    rules:
      - name: deny1
        source: src
        destination: dst
        service: ssh
        enabled: false
""",
        )
        self.assertTrue(plan.security_impact)
        rev_before = self.plane.current_revision()
        with self.assertRaises(ConfirmationRequired):
            apply_v24_plan(self.plane, plan, confirm=False)
        self.assertEqual(self.plane.current_revision(), rev_before)
        self.assertTrue(bool(self.plane._get_rule("remote", "deny1")["enabled"]))


if __name__ == "__main__":
    unittest.main()
