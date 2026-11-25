#!/usr/bin/env python3
"""Exercise the actual generated online transport without touching host state."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import select
import time
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REF = '0123456789abcdef0123456789abcdef01234567'
ONLINE = ROOT / 'dist/bootstrap-server-online.sh'
OFFLINE = ROOT / 'dist/bootstrap-server.sh'

class OnlineBootstrap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        mock = self.path / 'bin'
        mock.mkdir()
        def script(name, body):
            f = mock / name
            f.write_text(body)
            f.chmod(0o755)
        script('curl', """#!/usr/bin/python3
import os, pathlib, shutil, sys
args=sys.argv[1:]
assert args[0]=='--disable'
for opt in ('--connect-timeout','--max-time','--speed-time','--speed-limit','--progress-bar','--max-filesize','--proto','--proto-redir'):
    assert opt in args, opt
assert args[args.index('--proto')+1]=='=https'
assert args[args.index('--proto-redir')+1]=='=https'
prefix='https://raw.githubusercontent.com/datarelay-labs/datarelay-link/'+os.environ['TEST_REF']+'/'
assert args[-1].startswith(prefix)
rel=args[-1][len(prefix):]
with open(os.environ['TEST_LOG'],'a') as out: out.write(rel+'\\n')
if os.environ.get('TEST_FAIL')==rel: sys.exit(28)
dest=pathlib.Path(args[args.index('--output')+1])
shutil.copyfile(pathlib.Path(os.environ['TEST_REPO'])/rel,dest)
if os.environ.get('TEST_CORRUPT')==rel:
    with dest.open('r+b') as out:
        old=out.read(1)
        out.seek(0)
        out.write(bytes([old[0]^1]))
""")
        script('uname', '#!/bin/sh\ncase "$1" in -s) echo Linux;; -m) echo "$TEST_ARCH";; *) exit 1;; esac\n')
        script('bash', """#!/bin/sh
set -eu
test "$FRP_EXPECTED_SOURCE_REF" = "$TEST_REF"
test "$FRP_BUNDLE_SHA256" = "$(sha256sum "$TEST_REPO/dist/bootstrap-server.sh" | cut -d' ' -f1)"
cmp "$1" "$TEST_REPO/dist/bootstrap-server.sh"
shift
printf '%s\\n' "$@" > "$TEST_INSTALL"
echo EXACT_OFFLINE_BUNDLE_EXECUTION=PASS
""")
        self.log = self.path / 'downloads'
        self.marker = self.path / 'installed'
        self.env = dict(os.environ, PATH=str(mock)+':'+os.environ['PATH'],
                        TEST_REPO=str(ROOT), TEST_REF=REF, TEST_LOG=str(self.log),
                        TEST_INSTALL=str(self.marker), TEST_ARCH='x86_64',
                        FRP_SERVER_TEST_ROOT=str(self.path / 'isolated'))
        for key in ('FRP_EXPECTED_SOURCE_REF','FRP_EXPECTED_SOURCE_HEAD','FRP_BUNDLE_SHA256'):
            self.env.pop(key, None)
    def run_installer(self, ref=REF, arch='x86_64', input_text=None, **env):
        values = dict(self.env, TEST_ARCH=arch, **env)
        cmd = ['/bin/bash', str(ONLINE), ref, '--upgrade', '--check']
        if input_text is not None:
            cmd = ['/bin/bash', '-s', '--', ref, '--upgrade', '--check']
        return subprocess.run(cmd, input=input_text, env=values, text=True,
                              capture_output=True, timeout=60)
    def test_offline_stream_heartbeat_and_truncated_payload(self):
        # Feed only the initial commands, leaving Bash blocked reading stdin.
        # No installed files or services are touched.
        temp = self.path / 'staging'
        temp.mkdir()
        prefix = OFFLINE.read_text().split('base64 -d >"$TMP/VERSION"',1)[0]
        proc = subprocess.Popen(['/bin/bash'], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=dict(os.environ, TMPDIR=str(temp)))
        try:
            proc.stdin.write(prefix.encode())
            proc.stdin.flush()
            data = b''
            deadline = time.monotonic() + 12
            while b'Still receiving/restoring installer files' not in data and time.monotonic() < deadline:
                if select.select([proc.stdout], [], [], 1)[0]:
                    chunk = os.read(proc.stdout.fileno(), 8192)
                    if not chunk:
                        break
                    data += chunk
            self.assertIn(b'Still receiving/restoring installer files', data)
            proc.stdin.close()
            proc.stdin = None
            tail, _ = proc.communicate(timeout=12)
            self.assertNotEqual(proc.returncode, 0, data+tail)
            self.assertIn(b'Installation has not started', tail)
            self.assertNotIn(b'Installing Data Relay Link Server', data+tail)
            self.assertEqual(list(temp.iterdir()), [])
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.communicate(timeout=12)

    def test_small_entry_and_transfer_reduction(self):
        self.assertLess(ONLINE.stat().st_size, 8192)
        core = ROOT / 'dist/bootstrap-server-core.tar.gz'
        assets = list((ROOT/'third_party/frp').glob('*/binaries/*'))
        self.assertEqual(len(assets), 4)
        self.assertLess(ONLINE.stat().st_size+core.stat().st_size+sum(x.stat().st_size for x in assets),
                        OFFLINE.stat().st_size*0.8)
    def assert_success(self, arch, native):
        result = self.run_installer(arch=arch)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('EXACT_OFFLINE_BUNDLE_EXECUTION=PASS',result.stdout)
        requests=self.log.read_text().splitlines()
        self.assertEqual(len(requests),5)
        self.assertEqual(requests[0],'dist/bootstrap-server-core.tar.gz')
        self.assertTrue(requests[1].endswith(native),requests)
        self.assertEqual(len(set(requests)),5)
        self.assertEqual(self.marker.read_text().splitlines(),['--upgrade','--check'])
    def test_amd64(self):
        self.assert_success('x86_64','linux_amd64.tar.gz')
    def test_arm64(self):
        self.assert_success('aarch64','linux_arm64.tar.gz')
    def test_corrupted_core_never_executes(self):
        result=self.run_installer(TEST_CORRUPT='dist/bootstrap-server-core.tar.gz')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('SHA256 mismatch',result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertEqual(len(self.log.read_text().splitlines()),1)
    def test_timeout_never_executes(self):
        result=self.run_installer(TEST_FAIL='dist/bootstrap-server-core.tar.gz')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Download failed or timed out',result.stderr)
        self.assertFalse(self.marker.exists())
    def test_invalid_ref_arch_and_truncated_script(self):
        for result in (self.run_installer(ref='main'),self.run_installer(arch='riscv64'),
                       self.run_installer(input_text=ONLINE.read_text().rsplit('drlink_online_install "$@"',1)[0])):
            self.assertNotIn('EXACT_OFFLINE_BUNDLE_EXECUTION',result.stdout)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.marker.exists())

if __name__=='__main__':
    unittest.main(verbosity=2)
