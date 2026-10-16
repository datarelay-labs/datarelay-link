#!/usr/bin/env python3
"""Selector membership review is conservative, never a traffic-domain proof."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from drlink_control_plane import ControlPlane, ControlPlaneError, ConfirmationRequired
import drlink_v24 as v24
from drlink_v24_bundle import (prepare_v24_plan, apply_v24_plan, V24Plan,
                              aggregate_security_impacts, _raise_plan_confirmation)


class SelectorMembershipImpact(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='drlink-selector-review-')
        root = Path(self.tmp.name)
        (root / 'etc/drlink').mkdir(parents=True)
        (root / 'etc/drlink/config.json').write_text('{"role":"server"}\n')
        self.env = mock.patch.dict(os.environ, {
            'FRP_DEPLOY_TEST_ROOT': str(root), 'DRLINK_SKIP_ACTIVATION': '1',
            'DRLINK_CONFIRM': 'yes',
        })
        self.env.start()
        self.plane = ControlPlane(str(root))
        for prefix, base in [('src', '10.0.0.'), ('dst', '172.16.0.')]:
            for label, suffix in [('a', 1), ('alias', 1), ('b', 2), ('c', 3)]:
                v24.set_network_object(self.plane, prefix + '-' + label,
                                       type='ip', value=base + str(suffix), oneshot=True)
            for name, members in [('ab', ['a', 'b']), ('bc', ['b', 'c'])]:
                v24.set_network_group(self.plane, prefix + '-' + name,
                                       members=[prefix + '-' + x for x in members], oneshot=True)
            v24.set_network_object(self.plane, prefix + '-net', type='cidr',
                                   value=base + '0/24', oneshot=True)
        for name, port in [('a', 22), ('alias', 22), ('b', 80), ('c', 443)]:
            v24.set_service_object(self.plane, 'svc-' + name, type='tcp', port=port, oneshot=True)
        for name, members in [('ab', ['a', 'b']), ('bc', ['b', 'c'])]:
            v24.set_service_group(self.plane, 'svc-' + name,
                                  members=['svc-' + x for x in members], oneshot=True)
        for name in ['dns', 'dns-alias']:
            v24.set_network_object(self.plane, name, type='fqdn', value='example.com', oneshot=True)

    def tearDown(self):
        self.plane.close()
        self.env.stop()
        self.tmp.cleanup()

    def seed(self, name='review', **selectors):
        chosen = dict(source='src-ab', destination='dst-ab', service='svc-ab')
        chosen.update(selectors)
        v24.set_access_rule(self.plane, 'remote', name, mode='whitelist',
                            enabled=True, oneshot=True, **chosen)

    def snapshot(self):
        return tuple(self.plane.conn.iterdump())

    def assert_unknown(self, impact):
        self.assertIsNotNone(impact)
        self.assertIsNone(impact['access_broadened'])
        self.assertIsNone(impact['access_narrowed'])
        self.assertTrue(impact['traffic_direction_unknown'])
        self.assertTrue(impact['requires_confirmation'])
        rendered = self.plane._format_impact(impact)
        self.assertIn('Selector membership changes', rendered)
        self.assertIn('Access broadened: UNKNOWN', rendered)
        self.assertIn('Access narrowed: UNKNOWN', rendered)
        self.assertNotIn('expanded match set', rendered)

    def test_equivalent_aliases_are_not_claimed_as_traffic_changes(self):
        for field, prefix in [('source', 'src'), ('destination', 'dst'), ('service', 'svc')]:
            with self.subTest(field=field):
                name = 'alias-' + field
                self.seed(name, **{field: prefix + '-a'})
                before = self.snapshot()
                impact = v24.access_rule_update_security_impact(
                    self.plane, 'remote', name, **{field: prefix + '-alias'})
                self.assert_unknown(impact)
                self.assertEqual(self.snapshot(), before)

    def test_overlapping_groups_have_unknown_traffic_direction(self):
        for field, prefix in [('source', 'src'), ('destination', 'dst'), ('service', 'svc')]:
            with self.subTest(field=field):
                name = 'overlap-' + field
                self.seed(name)
                impact = v24.access_rule_update_security_impact(
                    self.plane, 'remote', name, **{field: prefix + '-bc'})
                self.assert_unknown(impact)
                self.assertIn(prefix + '-ab', impact['before'])
                self.assertIn(prefix + '-bc', impact['after'])

    def test_ip_cidr_overlap_and_equivalent_fqdn_names_are_not_compared_as_domains(self):
        for field, prefix in [('source', 'src'), ('destination', 'dst')]:
            name = 'cidr-' + field
            self.seed(name, **{field: prefix + '-net'})
            self.assert_unknown(v24.access_rule_update_security_impact(
                self.plane, 'remote', name, **{field: prefix + '-a'}))
        v24.set_access_rule(self.plane, 'internet', 'dns-review', mode='whitelist',
                            source='src-a', destination='dns', service='svc-c',
                            enabled=True, oneshot=True)
        self.assert_unknown(v24.access_rule_update_security_impact(
            self.plane, 'internet', 'dns-review', destination='dns-alias'))

    def test_proven_group_to_member_narrowing_needs_no_confirmation(self):
        for field, prefix in [('source', 'src'), ('destination', 'dst'), ('service', 'svc')]:
            with self.subTest(field=field):
                name = 'narrow-' + field
                self.seed(name)
                self.assertIsNone(v24.access_rule_update_security_impact(
                    self.plane, 'remote', name, **{field: prefix + '-a'}))
                revision = self.plane.current_revision()
                with mock.patch.dict(os.environ, {'DRLINK_CONFIRM': ''}):
                    v24.set_access_rule(self.plane, 'remote', name,
                                        oneshot=True, **{field: prefix + '-a'})
                self.assertEqual(self.plane.current_revision(), revision + 1)

    def test_bundle_proven_group_to_member_narrowing_needs_no_confirmation(self):
        self.seed()
        plan = prepare_v24_plan(self.plane, 'configurationBundle:\n  context: server\n  remoteAccess:\n    rules:\n      - name: review\n        source: src-a\n        destination: dst-a\n        service: svc-a\n        enabled: true\n')
        self.assertEqual(plan.security_impact, [])
        self.assertEqual(plan.structured_security_impact, [])
        with mock.patch.dict(os.environ, {'DRLINK_CONFIRM': ''}):
            apply_v24_plan(self.plane, plan, confirm=False)

    def test_membership_expansion_proves_non_narrowing_only(self):
        self.seed(source='src-a')
        impact = v24.access_rule_update_security_impact(
            self.plane, 'remote', 'review', source='src-ab')
        self.assertIsNone(impact['access_broadened'])
        self.assertIs(impact['access_narrowed'], False)
        self.assertTrue(impact['requires_confirmation'])
        self.assertIn('Access narrowed: NO', self.plane._format_impact(impact))

    def assert_mixed_traffic(self):
        for source, dest, port, decision in [
            ('10.0.0.1', '172.16.0.1', 22, 'DENY'),
            ('10.0.0.2', '172.16.0.2', 80, 'ALLOW'),
            ('10.0.0.3', '172.16.0.3', 443, 'ALLOW'),
        ]:
            self.assertEqual(self.plane.evaluate_remote_access(source, dest, 'tcp', port)['action'], decision)

    def test_direct_mixed_replacement_confirmation_rollback_and_enforcement(self):
        self.seed()
        change = dict(source='src-bc', destination='dst-bc', service='svc-bc', oneshot=True)
        before = self.snapshot()
        with mock.patch.dict(os.environ, {'DRLINK_CONFIRM': ''}):
            with self.assertRaises(ConfirmationRequired) as caught:
                v24.set_access_rule(self.plane, 'remote', 'review', **change)
        self.assert_unknown(caught.exception.impact)
        self.assertEqual(self.snapshot(), before)
        with mock.patch.object(self.plane, '_write_revision', side_effect=ControlPlaneError('controlled writer failure')):
            with self.assertRaisesRegex(ControlPlaneError, 'controlled writer failure'):
                v24.set_access_rule(self.plane, 'remote', 'review', confirm=True, **change)
        self.assertEqual(self.snapshot(), before)
        v24.set_access_rule(self.plane, 'remote', 'review', confirm=True, **change)
        self.assert_mixed_traffic()

    def test_bundle_mixed_replacement_confirmation_rollback_and_enforcement(self):
        self.seed()
        plan = prepare_v24_plan(self.plane, '''configurationBundle:
  context: server
  remoteAccess:
    rules:
      - name: review
        source: src-bc
        destination: dst-bc
        service: svc-bc
        enabled: true
''')
        self.assertTrue(any('Traffic direction: UNKNOWN' in text for text in plan.security_impact))
        before = self.snapshot()
        with mock.patch.dict(os.environ, {'DRLINK_CONFIRM': ''}):
            with self.assertRaises(ConfirmationRequired) as caught:
                apply_v24_plan(self.plane, plan, confirm=False)
        self.assertTrue(caught.exception.impact['traffic_direction_unknown'])
        self.assertIsNone(caught.exception.impact['access_broadened'])
        self.assertIsNone(caught.exception.impact['access_narrowed'])
        self.assertEqual(self.snapshot(), before)
        with mock.patch.object(self.plane, '_write_revision', side_effect=ControlPlaneError('controlled bundle failure')):
            with self.assertRaisesRegex(ControlPlaneError, 'controlled bundle failure'):
                apply_v24_plan(self.plane, plan, confirm=True)
        self.assertEqual(self.snapshot(), before)
        apply_v24_plan(self.plane, plan, confirm=True)
        self.assert_mixed_traffic()

    def test_structured_direction_precedence_and_confirmation_authority(self):
        for definite, unknown, expected in [(True, None, True), (False, None, None),
                                             (False, False, False)]:
            result = aggregate_security_impacts([
                {'access_broadened': definite, 'access_narrowed': unknown,
                 'requires_confirmation': False},
                {'access_broadened': unknown, 'access_narrowed': definite,
                 'requires_confirmation': True},
            ])
            self.assertIs(result['access_broadened'], expected)
            self.assertIs(result['access_narrowed'], expected)
            self.assertTrue(result['requires_confirmation'])
        self.assertFalse(aggregate_security_impacts([
            {'access_broadened': True, 'requires_confirmation': False}
        ])['requires_confirmation'])

    def test_warning_text_does_not_determine_direction_flags(self):
        for text in ['This change broadens access; DENY ALL', 'localized unrelated wording']:
            plan = V24Plan(context='server', security_impact=[text],
                           structured_security_impact=[{
                               'access_broadened': False, 'access_narrowed': None,
                               'requires_confirmation': True}])
            with self.assertRaises(ConfirmationRequired) as caught:
                _raise_plan_confirmation(plan)
            self.assertIs(caught.exception.impact['access_broadened'], False)
            self.assertIsNone(caught.exception.impact['access_narrowed'])

    def test_real_bundle_definite_impacts_dominate_unknown_independently(self):
        self.seed()
        v24.set_access_rule(self.plane, 'internet', 'web-enabled', mode='whitelist',
                            source='src-a', destination='dns', service='svc-c',
                            enabled=True, oneshot=True)
        v24.set_access_rule(self.plane, 'internet', 'web-disabled',
                            source='src-c', destination='dns', service='svc-c',
                            enabled=False, oneshot=True)
        unknown = {"name": "review", "source": "src-bc", "destination": "dst-bc",
                   "service": "svc-bc", "enabled": True}
        cases = [
            ({'remoteAccess': {'rules': [unknown]},
              'internetAccess': {'rules': [{'name': 'web-disabled', 'enabled': True}]}},
             True, None),
            ({'remoteAccess': {'rules': [unknown]},
              'internetAccess': {'enforcement': 'disabled'}}, None, True),
            ({'remoteAccess': {'enforcement': 'disabled', 'rules': [unknown]},
              'internetAccess': {'enforcement': 'disabled'}}, True, True),
        ]
        import yaml
        for sections, broad, narrow in cases:
            with self.subTest(broadened=broad, narrowed=narrow):
                plan = prepare_v24_plan(self.plane, yaml.safe_dump({
                    'configurationBundle': {'context': 'server', **sections}}))
                before = self.snapshot()
                self.assertTrue(any(x.get('access_broadened') is None
                                    for x in plan.structured_security_impact))
                with mock.patch.dict(os.environ, {'DRLINK_CONFIRM': ''}):
                    with self.assertRaises(ConfirmationRequired) as caught:
                        apply_v24_plan(self.plane, plan, confirm=False)
                impact = caught.exception.impact
                self.assertIs(impact['access_broadened'], broad)
                self.assertIs(impact['access_narrowed'], narrow)
                self.assertTrue(impact['requires_confirmation'])
                rendered = self.plane._format_impact(impact)
                if broad is True:
                    self.assertIn('Access broadened: YES', rendered)
                if narrow is True:
                    self.assertIn('Access narrowed: YES', rendered)
                self.assertEqual(self.snapshot(), before)

    def test_unchanged_selectors_still_need_no_confirmation(self):
        self.seed()
        self.assertIsNone(v24.access_rule_update_security_impact(
            self.plane, 'remote', 'review', source='src-ab', destination='dst-ab', service='svc-ab'))


if __name__ == '__main__':
    unittest.main()
