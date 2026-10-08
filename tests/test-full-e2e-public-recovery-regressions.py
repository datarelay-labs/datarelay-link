#!/usr/bin/env python3
"""Isolated public dispatch/error and reconnect regressions from Full E2E."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))

def shell_function(name):
    source = (ROOT / 'tools/frpctl').read_text()
    return name + '() {' + source.split(name + '() {', 1)[1].split('\n}\n', 1)[0] + '\n}\n'

class PublicRecoveryTests(unittest.TestCase):
    def test_fixed_tcp_wizard_describes_separate_destination_and_public_ports(self):
        import drlink_v24_wizard as wizard
        output=[]
        io=wizard.ScriptedIO(['c'],out=output)
        with mock.patch.object(wizard,'_io',return_value=io), mock.patch.object(wizard.v24,'get_service_object',return_value=None):
            self.assertEqual(wizard.run_service_object_wizard(mock.Mock(),'cancelled-probe'),0)
        message='\n'.join(output)
        self.assertIn('destination service port',message)
        self.assertIn('public port from the Fixed TCP pool',message)
        self.assertNotIn('equal to the service port',message)

    def test_every_named_create_menu_acquires_name_and_empty_cancels(self):
        for resource in ('network-object', 'network-group', 'service-object', 'service-group', 'permission-object', 'permission-group', 'remote-access', 'internet-access', 'ai-access', 'ai-identity'):
            for name in ('owned name with spaces', ''):
                script = 'frpctl_read() { printf "%s" "$ANSWER"; }; frpctl_dispatch() { printf "ARG:<%s>\\n" "$@"; };\n' + shell_function('frpctl_nav_dispatch_command') + '\nfrpctl_nav_dispatch_command "$COMMAND"'
                result = subprocess.run(['bash', '-c', script], env=dict(os.environ, ANSWER=name, COMMAND='set '+resource), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                if name:
                    self.assertIn('ARG:<'+name+'>', result.stdout)
                    self.assertEqual(result.stdout.count('ARG:'), 3)
                else:
                    self.assertIn('No changes were applied', result.stdout)
                    self.assertNotIn('ARG:', result.stdout)

    def test_invalid_archive_preflight_fails_before_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)/'invalid.tar.gz'
            manifest = Path(tmp)/'manifest.json'
            manifest.write_text(json.dumps({'project_version':'2.4.0','format':'invalid-fixture','files':[]}))
            with tarfile.open(archive, 'w:gz') as tar: tar.add(manifest, arcname='manifest.json')
            script = shell_function('frpctl_restore_preflight')+'\nfrpctl_restore_preflight "$ARCHIVE"'
            result = subprocess.run(['bash', '-c', script], env=dict(os.environ, ARCHIVE=str(archive), _FRPCTL_DIR=str(ROOT/'tools'), FRP_DEPLOY_TEST_ROOT=tmp), capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
            self.assertIn('restore preflight failed', result.stderr)
            self.assertNotIn('Continue with restore?', result.stdout+result.stderr)

    def test_rule_create_menu_never_dispatches_enforcement_names(self):
        for resource in ('remote-access','internet-access','ai-access'):
            for name in ('enabled','disabled','ENABLED',' disabled '):
                script='frpctl_read() { printf "%s" "$ANSWER"; }; frpctl_dispatch() { printf "DISPATCHED"; };\n'+shell_function('frpctl_nav_dispatch_command')+'\nfrpctl_nav_dispatch_command "$COMMAND"'
                result=subprocess.run(['bash','-c',script],env=dict(os.environ,ANSWER=name,COMMAND='set '+resource),capture_output=True,text=True)
                self.assertEqual(result.returncode,1)
                self.assertNotIn('DISPATCHED',result.stdout)
                self.assertIn('No changes were applied',result.stderr)

    def test_agent_bad_scope_advertises_only_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'etc/frp';p.mkdir(parents=True);(p/'client-state.json').write_text('{}');(p/'frpc.toml').write_text('')
            script='source "$DOCTOR"; frp_doctor_main targets'
            result=subprocess.run(['bash','-c',script],env=dict(os.environ,DOCTOR=str(ROOT/'lib/frp-doctor-common.sh'),FRP_ROLE_TEST_ROOT=tmp,FRP_CTL_TEST_ROOT=tmp),capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertIn('Scopes: runtime',result.stderr)
            self.assertNotIn('Scopes: control-plane',result.stderr)

    def test_lifecycle_passes_server_reconnect_requirement_to_runtime(self):
        import drlink_agent_lifecycle as lifecycle
        import drlink_control_plane as cp
        import drlink_v24 as v24
        for force in (False,True):
            with mock.patch.object(lifecycle,'load_lifecycle_intent',return_value='running'), mock.patch.object(lifecycle,'heartbeat_once',return_value={'reconcile_required':force}), mock.patch.object(lifecycle,'reconciliation_needed',return_value=True), mock.patch.object(cp,'ControlPlane') as plane, mock.patch.object(v24,'ensure_v2_schema'), mock.patch.object(v24,'synchronize_agent_remote_services',return_value={'status':'SYNCHRONIZED'}) as sync:
                lifecycle.reconcile_once('/fixture')
                sync.assert_called_once_with(plane.return_value,root='/fixture',force_runtime=force)

if __name__ == '__main__':unittest.main()
