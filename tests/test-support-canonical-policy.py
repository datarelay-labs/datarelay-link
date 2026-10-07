#!/usr/bin/env python3
"""FULL2-P2-006: support policy evidence must come from read-only SQLite.

All state is an isolated fixture. This does not qualify a real-user scenario.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
import drlink_control_db as db
from drlink_control_plane import ControlPlane
import drlink_v24 as v24
from frp_support_bundle import BundleBuilder

class CanonicalSupportPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='support-policy-')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.root=self.base/'host'
        self.plane=ControlPlane(str(self.root))
        self.addCleanup(self.plane.close)
        v24.ensure_v2_schema(self.plane.conn)
        self.stage=self.base/'stage'; self.stage.mkdir()
        self.builder=BundleBuilder(self.root); self.builder.stage=self.stage; self.builder.role='server'

    def capture(self):
        self.builder._write_access_control()
        self.builder._write_egress_control()
        return json.loads((self.stage/'policy-summary.json').read_text())

    def seed_rules(self):
        for family in ('remote','internet'):
            for enabled in (0,1):
                key='%s-%s'%(family,enabled)
                self.plane.conn.execute('INSERT INTO policy_rules(id,plane,name,position,action,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(key,family,key,enabled,'allow',enabled,'2026-10-07','2026-10-07'))
        for enabled in (0,1):
            key='ai-%s'%enabled
            self.plane.conn.execute('INSERT INTO ai_policy_rules(id,name,enabled,created_at,updated_at) VALUES (?,?,?,?,?)',(key,key,enabled,'2026-10-07','2026-10-07'))
        self.plane.conn.execute("UPDATE access_policies SET mode='whitelist', enforcement='enabled'")

    def test_sqlite_only_server_is_available(self):
        result=self.capture()
        self.assertEqual(result['policy_status'],'AVAILABLE')
        self.assertEqual(result['source'],'canonical_sqlite')
        self.assertEqual(set(result['planes']),{'remote','internet','ai'})
        self.assertEqual(result['revision'],self.plane.current_revision())
        self.assertEqual(result['scope'],'server_policy')

    def test_counts_are_from_current_rules(self):
        self.seed_rules(); result=self.capture()
        for family in ('remote','internet','ai'):
            self.assertEqual(result['planes'][family]['rule_count'],2)
            self.assertEqual(result['planes'][family]['enabled_rule_count'],1)
            self.assertIn('unmatched DENY',result['planes'][family]['effective_posture'])

    def test_no_policy_defaults_distinguish_planes(self):
        result=self.capture()
        self.assertIn('ALLOW',result['planes']['remote']['effective_posture'])
        for family in ('internet','ai'):
            self.assertIn('DENY ALL',result['planes'][family]['effective_posture'])

    def test_disabled_posture_uses_shared_policy_semantics(self):
        self.seed_rules(); self.plane.conn.execute("UPDATE access_policies SET enforcement='disabled'")
        result=self.capture()
        self.assertIn('ALLOW ALL',result['planes']['remote']['effective_posture'])
        for family in ('internet','ai'):
            self.assertIn('DENY ALL',result['planes'][family]['effective_posture'])

    def test_stale_json_does_not_replace_sqlite_truth(self):
        for name in ('access-control.json','egress-control.json'):
            (self.root/'var/lib/drlink'/name).write_text(json.dumps({'secret':'legacy-marker-must-not-appear','access_lists':{'obsolete':{}}}))
        self.seed_rules(); result=self.capture()
        self.assertEqual(result['source'],'canonical_sqlite')
        for name in ('policy-summary.json','access-control-summary.json','egress-control-summary.json'):
            text=(self.stage/name).read_text()
            self.assertNotIn('legacy-marker-must-not-appear',text)
            self.assertNotIn('obsolete',text)
            self.assertNotIn('POLICY UNAVAILABLE',text)

    def test_read_only_collection_leaves_database_unchanged(self):
        self.seed_rules()
        before=list(self.plane.conn.iterdump())
        self.capture()
        self.assertEqual(before,list(self.plane.conn.iterdump()))
        self.assertFalse((self.stage/'drlink.db').exists())
        self.assertEqual(set(p.suffix for p in self.stage.iterdir()),{'.json'})

    def test_rule_names_descriptions_and_credentials_not_exported(self):
        self.seed_rules()
        secret='support-fixture-private-value-do-not-export'
        self.plane.conn.execute('UPDATE ai_policy_rules SET description=?',(secret,))
        self.plane.conn.execute('UPDATE policy_rules SET description=?',(secret,))
        self.capture()
        for p in self.stage.iterdir(): self.assertNotIn(secret,p.read_text())

    def test_busy_database_is_bounded_and_not_reported_as_no_policy(self):
        self.plane.conn.execute('PRAGMA journal_mode=DELETE')
        self.plane.conn.execute('BEGIN EXCLUSIVE')
        try:
            start=time.monotonic(); result=self.capture(); duration=time.monotonic()-start
        finally: self.plane.conn.rollback()
        self.assertLess(duration,2.0)
        self.assertEqual(result['policy_status'],'ACCESS ERROR')
        self.assertNotIn('planes',result)

    def test_unsupported_schema_fails_without_legacy_fallback(self):
        with mock.patch.object(db,'connect_read_only',side_effect=db.SchemaTooNewError(999,db.SCHEMA_VERSION)):
            result=self.capture()
        self.assertEqual(result['policy_status'],'ACCESS ERROR')
        self.assertNotIn('planes',result)

    def test_corrupt_database_fails_without_exposing_database_bytes(self):
        self.plane.close()
        path=self.root/'var/lib/drlink/drlink.db'
        path.write_bytes(b'not a database: private-value-must-not-appear')
        result=self.capture()
        self.assertEqual(result['policy_status'],'ACCESS ERROR')
        self.assertNotIn('private-value-must-not-appear',(self.stage/'policy-summary.json').read_text())

    def test_symlink_database_is_not_read(self):
        self.plane.close()
        path=self.root/'var/lib/drlink/drlink.db'; target=path.with_suffix('.original')
        path.rename(target);path.symlink_to(target)
        result=self.capture()
        self.assertEqual(result['policy_status'],'ACCESS ERROR')

    def test_agent_metadata_is_not_claimed_as_server_policy(self):
        self.builder.role='agent'
        result=self.capture()
        self.assertEqual(result['scope'],'local_policy_metadata')
        self.assertEqual(result['runtime_evaluation'],'not_evaluated')

    def test_policy_planes_share_one_snapshot(self):
        self.seed_rules()
        self.builder._write_access_control()
        self.plane.conn.execute("UPDATE access_policies SET enforcement='disabled'")
        self.builder._write_egress_control()
        result=json.loads((self.stage/'egress-control-summary.json').read_text())
        self.assertEqual(result['enforcement'],'ENABLED')
        self.assertIn('unmatched DENY',result['effective_posture'])

    def test_canonical_reader_is_opened_once(self):
        with mock.patch.object(db,'connect_read_only',wraps=db.connect_read_only) as reader:
            self.capture()
        self.assertEqual(reader.call_count,1)

    def test_symlink_parent_is_not_followed(self):
        self.plane.close()
        parent=self.root/'var/lib/drlink'; target=self.root/'relocated-state'
        parent.rename(target);parent.symlink_to(target,target_is_directory=True)
        result=self.capture()
        self.assertEqual(result['policy_status'],'ACCESS ERROR')

    def test_invalid_metadata_does_not_echo_untrusted_text(self):
        private='not-a-valid-enforcement-private-fixture'
        self.plane.conn.execute('UPDATE access_policies SET enforcement=?',(private,))
        result=self.capture()
        self.assertEqual(result['policy_status'],'ACCESS ERROR')
        self.assertNotIn(private,(self.stage/'policy-summary.json').read_text())

    def test_no_database_does_not_create_one(self):
        fresh=self.base/'uninstalled'; fresh.mkdir()
        self.builder.root=fresh; self.builder.role='uninstalled'
        self.builder._write_access_control()
        self.builder._write_egress_control()
        self.assertFalse((fresh/'var').exists())
        result=json.loads((self.stage/'access-control-summary.json').read_text())
        self.assertEqual(result['policy_status'],'POLICY UNAVAILABLE')

if __name__=='__main__': unittest.main()
