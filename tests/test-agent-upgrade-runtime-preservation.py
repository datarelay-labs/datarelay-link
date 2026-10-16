#!/usr/bin/env python3
"""Canonical local Agent upgrade must exclude lifecycle runtime writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


def worker(root, mode=""):
    if mode == "inject":
        marker = root / "injected"
        if not marker.exists():
            state = root / "etc/frp/client-state.json"
            data = json.loads(state.read_text())
            data['hostname'] = 'concurrent-fixture-write'
            state.write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')
            marker.touch()
        return
    prepare = mode == "prepare"
    # The installer fixture executes the newly installed worker payload.
    sys.path.insert(0, str(REPO / "lib" if prepare else root / "usr/local/lib/drlink"))
    import drlink_agent_lifecycle as lifecycle
    import drlink_v24 as v24
    import drlink_v24_runtime as runtime
    from drlink_control_plane import ControlPlane
    state = root / "etc/frp/client-state.json"
    if prepare:
        plane = ControlPlane(str(root))
        try:
            v24.ensure_v2_schema(plane.conn)
            v24.project_enrolled_services_into_agent_catalog(plane, root=str(root))
            result = runtime.apply_agent_runtime(plane, root=str(root), force_reapply=True)
            assert result['ok'], result
            # A valid committed disable with a failed runtime apply: desired
            # state survives, while the prior rendered generation is restored.
            row = plane.conn.execute("SELECT * FROM agent_remote_services WHERE name='service01'").fetchone()
            with patch.dict(os.environ, {'DRLINK_FAULT_RUNTIME_CONFIG': '1'}):
                try:
                    v24.set_remote_service_agent(plane, 'service01', destination=row['destination'],
                        service=row['service_object'], enabled=False, root=str(root), server_reachable=False)
                except Exception as exc:
                    assert 'deactivation could not be verified' in str(exc), str(exc)
                else:
                    raise AssertionError('failed runtime apply must be reported')
            row = plane.conn.execute("SELECT * FROM agent_remote_services WHERE name='service01'").fetchone()
            assert not row['enabled'] and row['endpoint_port']==6202, dict(row)
            assert 'rs-service01' in runtime.load_client_state(str(root))['services']
        finally:
            plane.close()
        return
    before = json.loads(state.read_text())
    with patch.object(lifecycle, 'heartbeat_once', return_value={'reconcile_required': True}), \
         patch.object(v24, 'detect_server_reachable', return_value=True), \
         patch('drlink_mgmt_sync.use_live_mgmt_path', return_value=False), \
         patch.object(v24, '_push_agent_remote_service_status'):
        result = lifecycle.reconcile_once(str(root))
    after = json.loads(state.read_text())
    receipt = {'result': result,
        'removed_proxies': sorted(set(before['services'])-set(after['services'])),
        'added_proxies': sorted(set(after['services'])-set(before['services']))}
    (root / 'worker-receipt.json').write_text(json.dumps(receipt))


class UpgradeRuntimePreservationTests(unittest.TestCase):
    def test_pending_reconciliation_defers_until_canonical_upgrade_finishes(self):
        self._exercise_upgrade()

    def test_uncoordinated_state_change_still_refuses_and_rolls_back(self):
        self._exercise_upgrade(inject=True)

    def test_running_reconciliation_refuses_upgrade_before_mutation(self):
        self._exercise_upgrade(busy=True)

    def test_continuous_worker_finishes_pass_then_defers_for_upgrade(self):
        self._exercise_upgrade(continuous=True)

    def test_long_reconciliation_pass_hands_off_to_upgrade_without_state_loss(self):
        # The real Agent held its barrier beyond the old 30-second installer
        # deadline. The installer must wait for that pass, then exclude the
        # worker during its byte-preservation window.
        self._exercise_upgrade(continuous=True, delayed_release=32)

    def test_inner_lock_failure_is_not_reclassified_as_upgrade_deferral(self):
        sys.path.insert(0,str(REPO/'lib'))
        import drlink_agent_lifecycle as lifecycle
        from frp_control_locks import ExclusiveFileLock, LockTimeout
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            etc=root/'etc/frp'
            etc.mkdir(parents=True)
            (etc/'client-state.json').write_text('{}')
            with patch.object(lifecycle,'_reconcile_once',side_effect=LockTimeout('other lock')):
                with self.assertRaisesRegex(LockTimeout,'other lock'):
                    lifecycle.reconcile_once(tmp)
            # Failure must release the preservation barrier for the next call.
            with ExclusiveFileLock(etc/'client-software-upgrade.lock',timeout=0):
                pass

    def _exercise_upgrade(self, inject=False, busy=False, continuous=False,
                          delayed_release=0):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            etc = root / 'etc/frp'
            etc.mkdir(parents=True)
            (root / 'etc/drlink').mkdir()
            bindir = root / 'usr/local/bin'
            bindir.mkdir(parents=True)
            oldlib = root / 'usr/local/lib/drlink'
            oldlib.mkdir(parents=True)
            frpc = bindir / 'frpc'
            frpc.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo "frpc version 0.71.0"; fi\nexit 0\n')
            frpc.chmod(0o755)
            client = bindir / 'frp-client'
            client.write_text('#!/bin/sh\necho old-client\n')
            client.chmod(0o755)
            (oldlib / 'frp-client-common.sh').write_text('old\n')
            (oldlib / 'frp_mgmt_auth.py').write_text('old\n')
            state = dict(schema_version=1, allocator_url='https://fixture.invalid/enroll',
                frp_server='203.0.113.10',frp_server_port=443,hostname='upgrade-fixture',
                machine_id='aabbccddeeff00112233445566778899',host_id='upgrade-aabbccdd',
                services={'service%02d'%n: dict(id='service%02d'%n,name='Service %d'%n,
                    preset='custom',protocol='tcp',local_ip='127.0.0.1',local_port=8000+n,
                    remote_port=6202 if n==1 else 6000+n,enabled=True) for n in range(1,17)})
            (etc / 'client-state.json').write_text(json.dumps(state,indent=2,sort_keys=True)+'\n')
            (etc / 'client-state.json').chmod(0o600)
            (etc / 'frpc.toml').write_text('serverAddr = "203.0.113.10"\nserverPort = 443\nauth.method = "token"\nauth.token = "local-fixture-only"\n')
            (etc / 'frpc.toml').chmod(0o600)
            (etc / 'access-info.txt').write_text('fixture access\n')
            subprocess.run([sys.executable,str(REPO/'lib/frp_mgmt_auth.py'),'gen-key',
                str(etc/'client-identity.key'),str(etc/'client-identity.pub')],check=True,capture_output=True)
            (etc / 'client-identity.mac').write_text('a'*64+'\n')
            (etc / 'client-identity.mac').chmod(0o600)
            (root / 'etc/drlink/version').write_text('PROJECT_VERSION=2.4.0\nFRP_VERSION=0.71.0\nRELEASE_CHANNEL=development\nSOURCE_REF=55aa3042438481a20c77041e306feacba8140545\nSOURCE_HEAD=55aa3042438481a20c77041e306feacba8140545\nBUNDLE_SHA256='+'a'*64+'\n')
            env = {k:v for k,v in os.environ.items() if not k.startswith(('FRP_', 'DRLINK_'))}
            env.update(FRP_CLIENT_TEST_ROOT=str(root),FRP_SKIP_DOWNLOAD='1',
                FRP_CLIENT_SKIP_SERVER_VERSION_GATE='1',FRP_RELEASE_CHANNEL='development',
                FRP_EXPECTED_SOURCE_REF='e7639e7fdd20b7e071f0cd6a3da2950de6e41bf4',
                FRP_BUNDLE_SHA256='b'*64,FRP_MGMT_AUTH_PY=str(REPO/'lib/frp_mgmt_auth.py'))
            prepared=subprocess.run([sys.executable,__file__,'--worker',str(root),'prepare'],env=env,capture_output=True,text=True)
            self.assertEqual(prepared.returncode,0,prepared.stdout+prepared.stderr)
            files=[etc/name for name in ('client-state.json','frpc.toml','access-info.txt',
                'client-identity.key','client-identity.pub','client-identity.mac')]
            before={str(p):p.read_bytes() for p in files}
            mock=root/'systemctl'
            callback_mode=' inject' if inject else ''
            mock.write_text('#!/bin/sh\ncase "$1" in\n is-active) echo active;;\n is-enabled) echo enabled;;\n restart) if [ "$2" = drlink-lifecycle ]; then\n  "'+sys.executable+'" "'+str(Path(__file__).resolve())+'" --worker "'+str(root)+'"'+callback_mode+'\n fi;;\nesac\n')
            mock.chmod(0o755)
            env['FRP_SYSTEMCTL_BIN']=str(mock)
            command=[str(REPO/'install-client.sh'),'--upgrade','--source',str(REPO)]
            check=subprocess.run(command+['--check'],env=env,capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stdout+check.stderr)
            self.assertEqual({str(p):p.read_bytes() for p in files},before)
            if busy:
                import fcntl
                # Exercise the same fail-closed deadline without a 3-minute test.
                env['FRP_TEST_CLIENT_UPGRADE_LOCK_WAIT_SECONDS']='0.2'
                with (etc/'client-software-upgrade.lock').open('a') as held:
                    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    result=subprocess.run(command,env=env,capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('Agent lifecycle reconciliation is running',result.stderr)
                self.assertNotIn('Installing management files',result.stdout)
                self.assertEqual(client.read_text(),'#!/bin/sh\necho old-client\n')
                self.assertEqual({str(p):p.read_bytes() for p in files},before)
                return
            if continuous:
                # A real long-lived worker owns the barrier during a pass.
                # Hold the pass until the installer actually observes its busy
                # preservation lock, proving overlap without a timed release.
                script = root/'continuous-worker.py'
                script.write_text("import sys, pathlib, time\nsys.path.insert(0, sys.argv[1])\nimport drlink_agent_lifecycle as l\nroot=pathlib.Path(sys.argv[2])\ndef pass_once(_):\n (root/'pass-started').touch()\n while not (root/'finish-pass').exists(): time.sleep(.01)\n return {'status':'HEARTBEAT'}\nl._reconcile_once=pass_once\nl.worker(str(root))\n")
                process=subprocess.Popen([sys.executable,str(script),str(REPO/'lib'),str(root)],env=env)
                # Instrument only the installer's actual preservation flock:
                # release the in-flight pass after its first busy result.
                shim=root/'shim'; shim.mkdir()
                python=shim/'python3'
                python.write_text('#!'+sys.executable+'\nimport os, sys, pathlib, fcntl, threading\nargs=sys.argv[1:]\nif len(args)==2 and args[0]=="-" and args[1].isdigit():\n code=sys.stdin.read()\n real=fcntl.flock\n scheduled=False\n def observed(fd, flags):\n  global scheduled\n  try: return real(fd, flags)\n  except BlockingIOError:\n   if not scheduled:\n    scheduled=True\n    delay='+repr(delayed_release)+'\n    marker=pathlib.Path('+repr(str(root/'finish-pass'))+')\n    if delay: threading.Timer(delay, marker.touch).start()\n    else: marker.touch()\n   raise\n fcntl.flock=observed\n sys.argv=["-"]+args[1:]\n exec(compile(code,"<installer-preservation>","exec"))\nelse: os.execv('+repr(sys.executable)+', ['+repr(sys.executable)+']+args)\n')
                python.chmod(0o755)
                env['PATH']=str(shim)+os.pathsep+env['PATH']
                try:
                    deadline=time.monotonic()+10
                    while not (root/'pass-started').exists() and time.monotonic()<deadline:
                        time.sleep(.01)
                    self.assertTrue((root/'pass-started').exists(),'worker did not enter reconciliation')
                    result=subprocess.run(command,env=env,capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertIsNone(process.poll(),'continuous worker must remain running')
                finally:
                    process.terminate()
                    process.wait(timeout=10)
            else:
                result=subprocess.run(command,env=env,capture_output=True,text=True)
            if inject:
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('client-state.json changed during software upgrade',result.stderr)
                self.assertIn('UPGRADE_ROLLBACK=PASS',result.stdout)
                self.assertIn('FAILURE_CLASS=STATE_PRESERVATION_FAILED',result.stdout+result.stderr)
                self.assertEqual({str(p):p.read_bytes() for p in files},before)
                self.assertIn('SOURCE_HEAD=55aa3042438481a20c77041e306feacba8140545',(root/'etc/drlink/version').read_text())
                self.assertEqual(client.read_text(),'#!/bin/sh\necho old-client\n')
                return
            receipt=json.loads((root/'worker-receipt.json').read_text())
            self.assertEqual(result.returncode,0,result.stdout+result.stderr+'\nWORKER_RECEIPT='+json.dumps(receipt))
            self.assertIn('Management ID   : enrolled',result.stdout)
            self.assertEqual({str(p):p.read_bytes() for p in files},before)
            self.assertEqual(receipt['removed_proxies'],[])
            self.assertEqual(receipt['result']['status'],'DEFERRED')
            # Real worker retry after installer releases its barrier: apply the
            # pending disable, retaining every other publication and endpoint.
            subprocess.run([sys.executable,__file__,'--worker',str(root)],env=env,check=True,capture_output=True,text=True)
            receipt=json.loads((root/'worker-receipt.json').read_text())
            self.assertEqual(receipt['result']['status'],'SYNCHRONIZED')
            self.assertEqual(receipt['removed_proxies'],['rs-service01'])
            after=json.loads((etc/'client-state.json').read_text())
            self.assertEqual(set(after['services']),set(json.loads(before[str(etc/'client-state.json')])['services'])-{'rs-service01'})
            sys.path.insert(0,str(REPO/'lib'))
            from drlink_control_plane import ControlPlane
            plane=ControlPlane(str(root))
            try:
                row=plane.conn.execute("SELECT enabled,endpoint_port FROM agent_remote_services WHERE name='service01'").fetchone()
                self.assertFalse(row['enabled'])
                self.assertEqual(row['endpoint_port'],6202)
            finally:
                plane.close()


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        worker(Path(sys.argv[2]),sys.argv[3] if len(sys.argv)>3 else '')
    else:
        unittest.main()
