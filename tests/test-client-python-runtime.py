#!/usr/bin/env python3
"""EL8 maintenance selects an installed supported Python without OS changes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ClientPythonRuntime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        binaries = self.root / 'bin'
        binaries.mkdir()
        old = binaries / 'python3'
        old.write_text('#!/bin/sh\necho "platform Python 3.6 cannot load product modules" >&2\nexit 1\n')
        old.chmod(0o755)
        self.supported = binaries / 'python3.12'
        self.supported.symlink_to(sys.executable)
        self.env = os.environ.copy()
        self.env.update(PATH=str(binaries) + ':' + self.env['PATH'],
                        FRP_CLIENT_TEST_ROOT=str(self.root), FRP_CTL_TEST_ROOT=str(self.root),
                        FRP_SKIP_SYSTEMD='1', FRP_CLIENT_TEST_RUNTIME='active')
        self.env.pop('FRP_PYTHON', None)
        tools = self.root / 'usr/local/bin'
        tools.mkdir(parents=True)
        (tools / 'frp-client').symlink_to(ROOT / 'tools/frp-client')
        self.env['FRP_CTL_BIN_DIR'] = str(tools)
        self.env['FRP_CLIENT_LIB'] = str(ROOT / 'lib/frp-client-common.sh')
        etc = self.root / 'etc/frp'
        etc.mkdir(parents=True)
        (etc / 'client-state.json').write_text(json.dumps({'machine_id': 'a' * 32, 'services': {}}))
        (etc / 'frpc.toml').write_text('serverAddr = "127.0.0.1"\n')

    def test_public_pause_uses_supported_python_for_lifecycle_state(self):
        proc = subprocess.run(['bash', str(ROOT / 'tools/drlink'), 'system', 'pause'],
                              env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn('platform Python', proc.stderr)
        intent = json.loads((self.root / 'var/lib/drlink/agent-lifecycle.json').read_text())
        self.assertEqual(intent['intent'], 'paused')

    def test_worker_units_pin_the_supported_interpreter_and_converge(self):
        script = '''
set -e
. "$1/lib/frp-client-common.sh"
frp_client_install_ai_agent_unit "$1"
frp_client_install_lifecycle_unit "$1"
if frp_client_unit_file_needs_converge "$1" drlink-lifecycle.service; then exit 9; fi
'''
        proc = subprocess.run(['bash', '-c', script, 'test', str(ROOT)], env=self.env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ('drlink-lifecycle.service', 'drlink-ai-agent.service'):
            text = (self.root / 'etc/systemd/system' / name).read_text()
            self.assertIn('ExecStart=' + str(self.supported) + ' ', text)
            self.assertNotIn('ExecStart=/usr/bin/python3 ', text)
        self.assertFalse((self.root / 'usr/local/bin/python3').exists())

    def test_supported_path_python_is_pinned_instead_of_distribution_python(self):
        # EL8 may already have a supported /usr/local/bin/python3 ahead of
        # /usr/bin/python3. Selection must still bind service ExecStart.
        selected = self.root / 'bin/python3'
        selected.unlink()
        selected.symlink_to(sys.executable)
        script = '''
set -e
. "$1/lib/frp-client-common.sh"
mkdir -p "$FRP_CLIENT_TEST_ROOT/etc/systemd/system"
cp "$1/client/drlink-lifecycle.service" "$FRP_CLIENT_TEST_ROOT/etc/systemd/system/"
frp_client_unit_file_needs_converge "$1" drlink-lifecycle.service
frp_client_install_ai_agent_unit "$1"
frp_client_install_lifecycle_unit "$1"
if frp_client_unit_file_needs_converge "$1" drlink-lifecycle.service; then exit 9; fi
'''
        proc = subprocess.run(['bash', '-c', script, 'test', str(ROOT)], env=self.env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ('drlink-lifecycle.service', 'drlink-ai-agent.service'):
            unit = (self.root / 'etc/systemd/system' / name).read_text()
            self.assertIn('ExecStart=' + str(selected) + ' ', unit)
            self.assertNotIn('ExecStart=/usr/bin/python3 ', unit)
        # Interpreter selection must not rewrite the host's Python executable.
        self.assertTrue(selected.is_symlink())


if __name__ == '__main__':
    unittest.main()
