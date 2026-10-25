#!/usr/bin/env python3
"""Validate v2.3 archives before staging canonical v2.4 recovery state."""
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
RESTORE = runpy.run_path(str(ROOT / 'tools/frp-restore'))
from drlink_control_plane import ControlPlane

MID = 'aabbccddeeff00112233445566778899'


def legacy_files():
    files = {
        'etc/frp-auto-deploy/config.json': json.dumps({'role':'server', 'deployment_mode':'direct',
            'public_ip':'203.0.113.10', 'port_start':6000, 'port_end':6098,
            'registry_file':'/var/lib/frp-auto-deploy/registry.json'}),
        'etc/frp-auto-deploy/version':'PROJECT_VERSION=2.3.0\nFRP_VERSION=0.71.0\n',
        'etc/frp/frps.toml':'bindPort=443\ntransport.tls.certFile="/etc/frp-auto-deploy/pki/server.crt"\n',
        'etc/frp/server_token':'preserved-token',
        'var/lib/frp-auto-deploy/registry.json':json.dumps({'schema_version':2, 'reserved':[6003],
            'clients':{MID:{'hostname':'prior-agent', 'label':'prior-agent', 'services':{
                'ssh':{'id':'ssh', 'preset':'ssh', 'local_ip':'127.0.0.1', 'local_port':22, 'remote_port':6003, 'enabled':True}}}}}),
        'var/lib/frp-auto-deploy/access-control.json':json.dumps({'schema_version':1,
            'access_lists':{'acl_001122334455':{'id':'acl_001122334455', 'name':'office',
                'entries':[{'id':'ace_001122334455', 'cidr':'198.51.100.10/32'}]}},
            'service_access':{MID:{'ssh':{'access_mode':'ALLOWLIST','access_list_id':'acl_001122334455'}}}}),
        'var/lib/frp-auto-deploy/service-profiles.json':'{"schema_version":1,"profiles":{}}',
    }
    for name in ('ca.crt', 'ca.key', 'server.crt', 'server.key'):
        files['etc/frp-auto-deploy/pki/' + name] = 'preserved-fixture-' + name
    return {key:value.encode() for key,value in files.items()}


def archive(path, files, *, corrupt=None):
    entries = [dict(path=key, sha256=hashlib.sha256(value).hexdigest(), mode=0o600)
               for key,value in sorted(files.items())]
    manifest = dict(format='frp-auto-deploy-server-backup', schema_version=1,
                    created_at='2026-10-25T00:00:00Z', project_version='2.3.0', files=entries)
    sums = ''.join(item['sha256'] + '  payload/' + item['path'] + '\n' for item in entries)
    contents = dict(files)
    if corrupt:
        contents[corrupt] = b'corrupted-after-checksum'
    with tarfile.open(path, 'w:gz') as output:
        for key,value in {'manifest.json':json.dumps(manifest).encode(),
                          'checksums.sha256':sums.encode(),
                          **{'payload/' + key:value for key,value in contents.items()}}.items():
            info = tarfile.TarInfo(key); info.size = len(value)
            output.addfile(info, io.BytesIO(value))


class LegacyBackup(unittest.TestCase):
    def test_staged_policy_identity_ports_and_installed_version_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'prior.tar.gz'
            files = legacy_files(); archive(source, files)
            before = source.read_bytes()
            staged = root / 'staged'; staged.mkdir()
            manifest = RESTORE['extract_and_validate'](source, staged)
            RESTORE['validate_staged_control_payload'](staged)
            self.assertEqual(source.read_bytes(), before)
            plane = ControlPlane(str(staged / 'payload'))
            try:
                self.assertEqual(plane.conn.execute('SELECT public_port FROM published_services').fetchone()[0], 6003)
                self.assertEqual(plane.conn.execute('SELECT id FROM clients').fetchone()[0], MID)
                self.assertTrue(plane.list_rules('remote'))
                self.assertFalse(plane.status()['mismatch'])
            finally:
                plane.close()
            target = root / 'live'; version = target / 'etc/drlink/version'
            version.parent.mkdir(parents=True)
            version.write_text('PROJECT_VERSION=2.4.0\nSOURCE_HEAD=' + 'a' * 40 + '\n')
            identity = version.read_bytes()
            RESTORE['assert_same_version_restore'](target, manifest)
            RESTORE['apply_payload'](target, staged)
            self.assertEqual(version.read_bytes(), identity)
            self.assertEqual((target / 'etc/drlink/pki/ca.key').read_bytes(), files['etc/frp-auto-deploy/pki/ca.key'])
            version.write_text('PROJECT_VERSION=2.1.0\n')
            with self.assertRaises(RESTORE['RestoreError']):
                RESTORE['assert_same_version_restore'](target, manifest)

    def test_invalid_legacy_archives_fail_before_migration(self):
        for mode in ('checksum', 'traversal', 'mixed', 'missing-registry'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); files = legacy_files()
                if mode == 'traversal': files['../../outside'] = b'unsafe'
                if mode == 'mixed': files['etc/drlink/config.json'] = b'{}'
                if mode == 'missing-registry': files.pop('var/lib/frp-auto-deploy/registry.json')
                archive(root / 'bad.tar.gz', files,
                        corrupt='etc/frp/server_token' if mode == 'checksum' else None)
                with self.assertRaises(RESTORE['RestoreError']):
                    RESTORE['extract_and_validate'](root / 'bad.tar.gz', root / 'stage')


if __name__ == '__main__':
    unittest.main()
