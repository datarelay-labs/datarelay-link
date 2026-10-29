#!/usr/bin/env python3
"""P0: ConfigurationBundle stale-plan / current-state safety.

Apply must re-diff and recalculate security impact against authoritative state
under a race-safe guard. Stale prepared plans must not:
  - return false NO_CHANGE after concurrent mutation
  - remove the now-last BLACKLIST blocker without current-state confirmation
"""
from __future__ import annotations

import os
import io
import sys
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ConcurrencyError, ConfirmationRequired, ControlPlane
import drlink_v24 as v24
import drlink_control_cli as cli
from drlink_v24_bundle import BundleError, apply_v24_plan, export_configuration_v24, prepare_v24_plan


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class BundleStalePlanSafety(unittest.TestCase):
    def test_agent_preview_allows_delete_then_replace_same_binding_without_rpc(self):
        v24.set_remote_service_agent(self.plane, 'old-name', destination='this-host',
                                    service='ssh', enabled=True, server_reachable=False, oneshot=True)
        before = self.plane.current_revision()
        raw = '''configurationBundle:
  context: agent
  remoteServices:
    - name: old-name
      state: absent
    - name: replacement
      destination: this-host
      service: ssh
      enabled: true
'''
        with mock.patch('drlink_mgmt_sync.delete_remote_service_on_server', side_effect=AssertionError('network write')):
            plan = prepare_v24_plan(self.plane, raw, role='agent')
        self.assertEqual(len(plan.mutating_changes), 2)
        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual([row['name'] for row in self.plane.conn.execute('SELECT name FROM agent_remote_services')], ['old-name'])

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

    def test_agent_bundle_rejects_existing_self_binding_alias_readonly(self):
        import json

        identity_dir = Path(self.tmp, "etc/frp")
        identity_dir.mkdir(parents=True, exist_ok=True)
        machine_id = "aabbccddeeff00112233445566778899"
        identity_dir.joinpath("client-state.json").write_text(
            json.dumps({"machine_id": machine_id, "hostname": "agent-c", "label": "agent-c"}) + "\n",
            encoding="utf-8",
        )
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_object_catalog(kind,name,payload,synced_at) "
            "VALUES ('managed-host','agent-c',?,?)",
            (json.dumps({"client_id": machine_id, "hostname": "agent-c", "label": "agent-c"}), "now"),
        )
        self.plane.conn.execute(
            "INSERT INTO agent_remote_services "
            "(name,destination,destination_client_id,service_object,enabled,status,endpoint_port,"
            "pending_allocation,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("existing", "agent-c", None, "ssh", 1, "HEALTHY", 6018, 0, "now"),
        )
        before_revision = self.plane.current_revision()

        raw = '''configurationBundle:
  context: agent
  remoteServices:
    - name: duplicate-alias
      destination: agent-c
      service: ssh
      enabled: true
'''
        with self.assertRaisesRegex(BundleError, "already exists for|already uses"):
            prepare_v24_plan(self.plane, raw, role="agent")

        self.assertEqual(self.plane.current_revision(), before_revision)
        rows = self.plane.conn.execute(
            "SELECT name, destination, destination_client_id, service_object "
            "FROM agent_remote_services ORDER BY name"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "existing")
        self.assertIsNone(rows[0]["destination_client_id"])

    def test_agent_bundle_rejects_cidr_literal_destination_before_planning(self):
        before = self.plane.current_revision()
        raw = '''configurationBundle:
  context: agent
  remoteServices:
    - name: cidr-destination
      destination: 10.39.163.1/32
      service: ssh
      enabled: true
'''

        with self.assertRaisesRegex(BundleError, "CIDR|single target"):
            prepare_v24_plan(self.plane, raw, role="agent")

        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT count(*) FROM agent_remote_services"
            ).fetchone()[0],
            0,
        )

    def test_agent_bundle_rejects_catalog_cidr_object_before_planning(self):
        import json

        self.plane.conn.execute(
            "INSERT INTO agent_object_catalog(kind, name, payload, synced_at) "
            "VALUES ('network-object', 'server-cidr', ?, '2026-10-29T00:00:00Z')",
            (json.dumps({"name": "server-cidr", "type": "cidr", "values": ["10.39.163.1/32"]}),),
        )
        before = self.plane.current_revision()
        raw = '''configurationBundle:
  context: agent
  remoteServices:
    - name: cidr-object-destination
      destination: server-cidr
      service: ssh
      enabled: true
'''

        with self.assertRaisesRegex(BundleError, "CIDR|single target"):
            prepare_v24_plan(self.plane, raw, role="agent")

        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT count(*) FROM agent_remote_services"
            ).fetchone()[0],
            0,
        )

    def test_agent_bundle_rejects_malformed_destination_before_planning(self):
        before = self.plane.current_revision()
        raw = '''configurationBundle:
  context: agent
  remoteServices:
    - name: malformed-destination
      destination: "not a valid host !"
      service: ssh
      enabled: true
'''

        with self.assertRaisesRegex(BundleError, "destination|host|target"):
            prepare_v24_plan(self.plane, raw, role="agent")

        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT count(*) FROM agent_remote_services"
            ).fetchone()[0],
            0,
        )

    def test_agent_bundle_rejects_unregistered_literal_destinations(self):
        import json

        v24.set_network_object(
            self.plane, "registered-db", type="fqdn", value="db.internal", oneshot=True
        )
        before = self.plane.current_revision()

        def bundle(name, destination):
            return '''configurationBundle:
  context: agent
  remoteServices:
    - name: %s
      destination: %s
      service: ssh
      enabled: true
''' % (json.dumps(name), json.dumps(destination))

        registered = bundle("registered-destination", "registered-db")
        plan = prepare_v24_plan(self.plane, registered, role="agent")
        self.assertEqual(len(plan.mutating_changes), 1)

        for destination in (
            "db.internal",
            "nonexistent.cli100.example.invalid",
            "203.0.113.77",
            "123.456.789.012",
        ):
            raw = bundle("unregistered-destination", destination)
            with self.subTest(destination=destination), self.assertRaisesRegex(
                BundleError, "destination|Network Object|single target"
            ):
                prepare_v24_plan(self.plane, raw, role="agent")

        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT count(*) FROM agent_remote_services"
            ).fetchone()[0],
            0,
        )

    def test_agent_bundle_can_edit_existing_destination_after_catalog_loss(self):
        import json

        identity_dir = Path(self.tmp, "etc/frp")
        identity_dir.mkdir(parents=True, exist_ok=True)
        identity_dir.joinpath("client-state.json").write_text(
            json.dumps({
                "machine_id": "aabbccddeeff00112233445566778899",
                "hostname": "agent-c",
                "label": "agent-c",
            }) + "\n",
            encoding="utf-8",
        )
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_object_catalog(kind,name,payload,synced_at) "
            "VALUES ('network-object','legacy-db',?,?)",
            (json.dumps({"type": "fqdn", "values": ["legacy.example"]}), "now"),
        )
        v24.set_remote_service_agent(
            self.plane,
            "legacy-service",
            destination="legacy-db",
            service="ssh",
            enabled=True,
            oneshot=True,
            root=self.tmp,
            server_reachable=False,
        )
        self.plane.conn.execute(
            "DELETE FROM agent_object_catalog WHERE kind='network-object' AND name='legacy-db'"
        )
        before_revision = self.plane.current_revision()

        plan = prepare_v24_plan(self.plane, '''configurationBundle:
  context: agent
  remoteServices:
    - name: legacy-service
      enabled: false
''', role="agent")

        self.assertEqual(len(plan.mutating_changes), 1)
        self.assertEqual(plan.mutating_changes[0]["item"]["destination"], "legacy-db")
        self.assertEqual(plan.mutating_changes[0]["item"]["service"], "ssh")
        self.assertEqual(self.plane.current_revision(), before_revision)
        row = self.plane.conn.execute(
            "SELECT destination, enabled FROM agent_remote_services WHERE name='legacy-service'"
        ).fetchone()
        self.assertEqual(row["destination"], "legacy-db")
        self.assertTrue(row["enabled"])

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
        before = self.plane.current_revision()
        for token in ("-1", "not-a-revision", "true", "false", "1.5", "1.0", "-0.5",
                      ".inf", ".nan", "[]", "{}", '"1.5"', '"1.0"'):
            with self.subTest(source_revision=token):
                raw = """configurationBundle:
  context: server
  sourceRevision: %s
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.10
""" % token
                with self.assertRaises(BundleError) as ctx:
                    prepare_v24_plan(self.plane, raw)
                self.assertIn("sourceRevision", str(ctx.exception))
                self.assertEqual(self.plane.current_revision(), before)
                self.assertIsNone(self.plane.get_object("office"))

    def test_source_revision_preserves_integer_and_quoted_integer_values(self):
        before = self.plane.current_revision()
        for token, expected in (("0", 0), ("1", 1), ("999999", 999999),
                                ('"0"', 0), ('"42"', 42)):
            with self.subTest(source_revision=token):
                plan = prepare_v24_plan(self.plane, "configurationBundle:\n  context: server\n"
                                        "  sourceRevision: %s\n" % token)
                self.assertEqual(plan.base_revision, expected)
                self.assertIs(type(plan.base_revision), int)
                self.assertEqual(self.plane.current_revision(), before)

    def test_public_test_and_diff_reject_invalid_source_revision_without_changes(self):
        before = self.plane.current_revision()
        for command in (("test", "configuration", "-"),
                        ("system", "diff", "configuration", "-")):
            for token in ("1.5", "1.0", "true", "-1"):
                with self.subTest(command=command, source_revision=token):
                    raw = "configurationBundle:\n  context: server\n  sourceRevision: %s\n" % token
                    out, err = io.StringIO(), io.StringIO()
                    with mock.patch("sys.stdin", io.StringIO(raw)), \
                         redirect_stdout(out), redirect_stderr(err):
                        with self.assertRaises(SystemExit) as ctx:
                            cli.dispatch(list(command), root=self.tmp, plane=self.plane)
                    self.assertIn("sourceRevision must be a non-negative integer", str(ctx.exception))
                    self.assertIn("No changes were applied", str(ctx.exception))
                    self.assertEqual(self.plane.current_revision(), before)

    def test_export_restore_preserves_legacy_multiple_source_selectors(self, mode="whitelist"):
        import yaml
        for name, kind, value in [('any4', 'cidr', '0.0.0.0/0'),
                                  ('any6', 'cidr', '::/0'),
                                  ('dst', 'ip', '192.0.2.42'),
                                  ('peer', 'ip', '192.0.2.43')]:
            v24.set_network_object(self.plane, name, type=kind, value=value, oneshot=True)
        v24.set_service_object(self.plane, 'ssh', type='tcp', port=22, oneshot=True)
        v24.set_access_rule(self.plane, 'remote', 'dual-stack', mode=mode,
                            source='any6', destination='dst', service='ssh',
                            enabled=True, oneshot=True)
        self.plane.set_rule_source('remote', 'dual-stack', 'any4')
        v24.set_network_group(self.plane, 'peer-group', members=['peer'], oneshot=True)
        self.plane.set_rule_destination('remote', 'dual-stack', 'peer-group')
        v24.set_service_object(self.plane, 'http', type='tcp', port=80, oneshot=True)
        v24.set_service_group(self.plane, 'http-group', members=['http'], oneshot=True)
        rule = self.plane._get_rule('remote', 'dual-stack')
        group = self.plane.conn.execute("SELECT id FROM service_groups WHERE name='http-group'").fetchone()
        self.plane.conn.execute("INSERT INTO rule_service_refs(rule_id, ref_kind, ref_id) "
                                "VALUES (?, 'service_group', ?)", (rule['id'], group['id']))
        self.plane.conn.commit()
        sources = ['198.51.100.111', '2001:db8::111']
        cases = [(ip, dst, port) for ip in sources for dst in ('192.0.2.42', '192.0.2.43') for port in (22, 80)]
        cases += [('198.51.100.111', '192.0.2.99', 22), ('198.51.100.111', '192.0.2.42', 443)]
        before = [self.plane.evaluate_remote_access(ip, dst, 'tcp', port)['action'] for ip, dst, port in cases]
        self.assertEqual(before, (['ALLOW'] * 8 + ['DENY', 'DENY']) if mode == 'whitelist'
                         else (['DENY'] * 8 + ['ALLOW', 'ALLOW']))
        revision = self.plane.current_revision()
        exported = yaml.safe_load(export_configuration_v24(self.plane))
        self.assertEqual(self.plane.current_revision(), revision)
        # An operator name colliding with the document-only group is preserved.
        union_name = exported['configurationBundle']['remoteAccess']['rules'][0]['source']
        v24.set_network_object(self.plane, union_name, type='ip', value='203.0.113.99', oneshot=True)
        exported = yaml.safe_load(export_configuration_v24(self.plane))
        self.assertNotEqual(exported['configurationBundle']['remoteAccess']['rules'][0]['source'], union_name)
        self.assertEqual(self.plane._object_values(self.plane.get_object(union_name)['id']), ['203.0.113.99'])
        # A clean restore has its own revision; preserve the exported policy
        # semantics while the ordinary exact-revision guard remains tested above.
        exported['configurationBundle'].pop('sourceRevision', None)
        with tempfile.TemporaryDirectory(prefix='drlink-export-restore-') as other:
            _server_root(other)
            restored = ControlPlane(other)
            try:
                plan = prepare_v24_plan(restored, yaml.safe_dump(exported), role='server')
                apply_v24_plan(restored, plan, confirm=True)
                after = [restored.evaluate_remote_access(ip, dst, 'tcp', port)['action'] for ip, dst, port in cases]
                self.assertEqual(after, before)
            finally:
                restored.close()
        # Applying the same portable document over an existing legacy rule
        # must replace all refs with the union, then become idempotent.
        raw = yaml.safe_dump(exported)
        apply_v24_plan(self.plane, prepare_v24_plan(self.plane, raw, role='server'), confirm=True)
        after = [self.plane.evaluate_remote_access(ip, dst, 'tcp', port)['action'] for ip, dst, port in cases]
        self.assertEqual(after, before)
        self.assertEqual(prepare_v24_plan(self.plane, raw, role='server').mutating_changes, [])

    def test_export_restore_preserves_legacy_blacklist_selector_union(self):
        self.test_export_restore_preserves_legacy_multiple_source_selectors(mode='blacklist')

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
