#!/usr/bin/env python3
"""Public dispatcher regression coverage for read-only selector syntax."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module
workflow = import_module('test-v24-cli-workflow-semantic-parity')


class SelectorOperands(workflow._Base):
    def setUp(self):
        super().setUp()
        workflow.v24.set_network_object(self.plane, 'office', type='ip', value='198.51.100.10', oneshot=True)
        workflow.v24.set_network_group(self.plane, 'admins', members=['office'], oneshot=True)
        workflow.v24.set_service_group(self.plane, 'shell', members=['ssh'], oneshot=True)
        self.plane.upsert_client('host-1', label='host-one', hostname='host-one', connected=True)

    def test_trailing_operands_are_rejected(self):
        selectors = [('managed-host', 'host-one', view) for view in ('remote-services', 'agent', 'addresses')]
        selectors += [(resource, name, 'references') for resource, name in (
            ('network-object', 'office'), ('network-group', 'admins'),
            ('service-object', 'ssh'), ('service-group', 'shell'))]
        for selector in selectors:
            with self.subTest(selector=selector):
                rc, out, err = self._run('show', *selector, 'EXTRA')
                self.assertNotEqual(rc, 0)
                self.assertIn('show ' + selector[0], err)
                self.assertEqual(out, '')

    def test_syntax_precedes_missing_target_lookup(self):
        for resource, view in [('managed-host', 'addresses'), ('network-object', 'references'),
                               ('network-group', 'references'), ('service-object', 'references'),
                               ('service-group', 'references')]:
            with self.subTest(resource=resource):
                rc, out, err = self._run('show', resource, 'missing', view, 'EXTRA')
                self.assertNotEqual(rc, 0)
                self.assertIn('show ' + resource, err)
                self.assertNotIn('not found', err.lower())

    def test_supported_views_remain_valid(self):
        for selector in [('managed-host', 'host-one'), ('managed-host', 'host-one', 'agent'),
                         ('managed-host', 'host-one', 'remote-services'), ('managed-host', 'host-one', 'addresses'),
                         ('network-object', 'office'), ('network-object', 'office', 'references'),
                         ('network-group', 'admins', 'references'), ('service-object', 'ssh', 'references'),
                         ('service-group', 'shell', 'references')]:
            with self.subTest(selector=selector):
                rc, out, err = self._run('show', *selector)
                self.assertEqual(rc, 0, err)

    def test_ai_log_missing_filter_values(self):
        for key in ('identity', 'destination', 'permission'):
            with self.subTest(key=key):
                with mock.patch.object(self.plane, 'list_ai_activity') as query:
                    rc, out, err = self._run('show', 'ai-access-log', key)
                self.assertNotEqual(rc, 0)
                self.assertIn('show ai-access-log', err)
                self.assertIn(key, err)
                query.assert_not_called()

    def test_ai_log_valid_optional_filters_and_empty_list(self):
        for args in [(), ('identity', 'alice'), ('destination', 'office'), ('permission', 'ssh'),
                     ('identity', 'alice', 'destination', 'office', 'permission', 'ssh')]:
            with self.subTest(args=args):
                rc, out, err = self._run('show', 'ai-access-log', *args)
                self.assertEqual(rc, 0, err)
                self.assertIn('No AI Access Log entries found.', out)

    def test_managed_host_dependency_recovery(self):
        rc, out, err = self._run('show', 'managed-host', 'host-one', 'references')
        self.assertNotEqual(rc, 0)
        self.assertIn('show network-object', err)
        docs = (workflow.ROOT / 'docs/CLI_REFERENCE.md').read_text()
        self.assertNotIn('show managed-host <HOST> references', docs)
        self.assertIn('show network-object <NAME> references', docs)
        help_text = workflow.catalog.domain_help('managed-hosts', 'server')
        self.assertIn('show network-object <NAME> references', help_text)


if __name__ == '__main__':
    unittest.main()
