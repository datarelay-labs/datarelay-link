#!/usr/bin/env python3
"""Native consent regression checks: real input, temporary fixtures, inert effects."""
import json
import os
import pty
import re
import select
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'lib'
sys.path.insert(0, str(LIB))
import drlink_control_plane as backend


def native_function(source, name):
    start = re.search(r'^' + re.escape(name) + r'\(\) \{\n', source, re.M)
    if not start:
        raise AssertionError('Native function missing: ' + name)
    end = source.find('\n}\n', start.end())
    if end < 0:
        raise AssertionError('Native function terminator missing: ' + name)
    return source[start.start():end + 3]


class NativePublicConsent(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='drlink-native-consent-')
        self.addCleanup(self.temp.cleanup)
        self.fixture = Path(self.temp.name)
        self.source = (ROOT / 'tools/frpctl').read_text()
        self.env = dict(os.environ, TMPDIR=str(self.fixture), FRP_CTL_TEST_INPUT='yes\n',
                        DRLINK_CONFIRM='yes', DRLINK_EXPECTED_REVISION='42')
        self.read_helpers = '\n'.join(native_function(self.source, name) for name in (
            'frpctl_input_init', 'frpctl_try_read', 'frpctl_read'))
        # No installed tool, database, archive, uninstaller or product writer is called.
        self.stubs = '''
frpctl_require_server() { return 0; }
frpctl_load_passthrough() { _frpctl_pt=(); }
frpctl_is_client() { return 1; }
frpctl_find_uninstaller() { printf '%s' '/inert/uninstaller-never-executed'; }
frpctl_run_uninstaller() { echo STUB_EFFECT_UNINSTALL; }
frpctl_invoke() {
  if [[ "$1" == frp-enrollments ]]; then printf ACTIVE; return 0; fi
  echo "STUB_EFFECT_TOOL:$*"
}
frpctl_json_get() { python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2], ""))' "$1" "$2"; }
'''

    def shell_script(self, name):
        if name == 'group':
            arm = re.search(r'^    delete_group\)\n(.*?)^      ;;', self.source, re.M | re.S)
            self.assertIsNotNone(arm)
            body = 'native_group() {\nlocal result=\'{"group":"fixture"}\'\n' + arm.group(1) + '\n}\nnative_group\n'
        else:
            function = {'enrollment': 'frpctl_unset_enrollment',
                        'agent': 'frpctl_client_uninstall_flow',
                        'server': 'frpctl_server_uninstall_flow'}[name]
            body = native_function(self.source, function) + '\n' + function
            if name == 'enrollment':
                body += ' fixture-nonsecret-id'
            body += '\n'
        return self.read_helpers + '\n' + self.stubs + '\n' + body

    def run_pipe(self, name, answer):
        env = dict(self.env, TMPDIR=tempfile.mkdtemp(dir=self.fixture))
        return subprocess.run(['bash', '-c', self.shell_script(name)], input=answer,
                              env=env, capture_output=True, text=True, timeout=10)

    def run_tty(self, name, answer):
        master, slave = pty.openpty()
        env = dict(self.env, TMPDIR=tempfile.mkdtemp(dir=self.fixture))
        proc = subprocess.Popen(['bash', '-c', self.shell_script(name)],
                                stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        output = bytearray()
        deadline = time.monotonic() + 8
        sent = False
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                    if b'[y/N]: ' in output and not sent:
                        self.assertNotIn(b'STUB_EFFECT', output)
                        os.write(master, answer.encode())
                        sent = True
                elif proc.poll() is not None:
                    break
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.fail('Native consent did not finish: ' + output.decode(errors='replace'))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            os.close(master)
        return sent, output.decode(errors='replace')

    def test_group_non_tty_requires_terminal_even_with_inherited_fixture_input(self):
        for answer in ('', 'yes\n', 'no\n'):
            with self.subTest(answer=answer):
                proc = self.run_pipe('group', answer)
                output = proc.stdout + proc.stderr
                self.assertNotIn('STUB_EFFECT', output)
                self.assertIn('interactive confirmation', output)

    def test_group_tty_real_answers_override_fixture_input(self):
        for answer in ('yes\n', 'no\n', '\n'):
            with self.subTest(answer=answer):
                prompted, output = self.run_tty('group', answer)
                self.assertTrue(prompted, output)
                self.assertEqual('STUB_EFFECT_TOOL' in output, answer == 'yes\n', output)

    def test_enrollment_normal_stdin_controls_consent(self):
        for answer in ('', 'no\n', '\n', 'y\n', 'yes\n'):
            with self.subTest(answer=answer):
                proc = self.run_pipe('enrollment', answer)
                output = proc.stdout + proc.stderr
                self.assertEqual('STUB_EFFECT_TOOL' in output, answer in ('y\n', 'yes\n'), output)
                if answer not in ('y\n', 'yes\n'):
                    self.assertNotEqual(proc.returncode, 0, output)

    def test_enrollment_tty_real_answers_override_fixture_input(self):
        for answer in ('yes\n', 'no\n', '\n'):
            with self.subTest(answer=answer):
                prompted, output = self.run_tty('enrollment', answer)
                self.assertTrue(prompted, output)
                self.assertEqual('STUB_EFFECT_TOOL' in output, answer == 'yes\n', output)

    def test_uninstall_non_tty_fixture_input_cannot_approve(self):
        for role in ('agent', 'server'):
            for answer in ('', 'yes\n', 'no\n'):
                with self.subTest(role=role, answer=answer):
                    proc = self.run_pipe(role, answer)
                    output = proc.stdout + proc.stderr
                    self.assertNotIn('STUB_EFFECT', output)
                    self.assertNotEqual(proc.returncode, 0, output)

    def test_uninstall_tty_real_answers_override_fixture_input(self):
        for role in ('agent', 'server'):
            for answer in ('yes\n', 'no\n', '\n'):
                with self.subTest(role=role, answer=answer):
                    prompted, output = self.run_tty(role, answer)
                    self.assertTrue(prompted, output)
                    self.assertEqual('STUB_EFFECT_UNINSTALL' in output, answer == 'yes\n', output)

    def control_boundary(self, answer, conditional=False, safe=False):
        # The fake entry calls actual consent helpers with an inert callback; no plane DB exists.
        fake = self.fixture / 'drlink_control_cli.py'
        fake.write_text('''
import os, runpy, sys
sys.path.insert(0, ''' + repr(str(LIB)) + ''')
native = runpy.run_path(''' + repr(str(LIB / 'drlink_control_cli.py')) + ''')
from drlink_control_plane import _confirm_requested, ConfirmationRequired
def main(tokens):
    print('REVISION_GUARD=' + os.environ.get('DRLINK_EXPECTED_REVISION', ''))
    def inert_effect(confirm=None):
        needs_consent = tokens[1] != 'conditional-safe'
        if needs_consent and not _confirm_requested(confirm):
            raise ConfirmationRequired('Required approval [y/N]:', {'security_widening': True})
        print('STUB_EFFECT_CONFIRMED')
        return {'ok': True}
    native['_run'](inert_effect)
    return 0
''')
        setup = 'frpctl_lib_candidate() { printf %s ' + shlex.quote(str(fake)) + '; }\n'
        script = native_function(self.source, 'frpctl_control_plane_dispatch') + '\n' + setup
        scenario = 'conditional-safe' if safe else ('conditional-required' if conditional else 'required')
        script += 'frpctl_control_plane_dispatch ' + shlex.quote(json.dumps({'tokens': ['fixture', scenario]}))
        return subprocess.run(['bash', '-c', script], env=self.env, input=answer,
                              capture_output=True, text=True, timeout=10)

    def test_public_control_boundary_ignores_ambient_approval(self):
        for conditional in (False, True):
            for answer in ('', '\n', 'no\n'):
                with self.subTest(conditional=conditional, answer=answer):
                    proc = self.control_boundary(answer, conditional)
                    output = proc.stdout + proc.stderr
                    self.assertEqual(proc.returncode, 0, output)
                    self.assertNotIn('STUB_EFFECT_CONFIRMED', output)
                    self.assertIn('Cancelled', output)
                    self.assertIn('REVISION_GUARD=42', output)

    def test_public_control_boundary_still_accepts_operator_stdin(self):
        for answer in ('y\n', 'yes\n'):
            with self.subTest(answer=answer):
                proc = self.control_boundary(answer)
                output = proc.stdout + proc.stderr
                self.assertEqual(proc.returncode, 0, output)
                self.assertIn('STUB_EFFECT_CONFIRMED', output)
                self.assertIn('REVISION_GUARD=42', output)

    def test_internal_backend_confirmation_compatibility_is_preserved(self):
        with patch.dict(os.environ, {'DRLINK_CONFIRM': 'yes'}):
            self.assertTrue(backend._confirm_requested(None))
            self.assertTrue(backend._confirm_requested(True))
            self.assertTrue(backend._confirm_requested(False))
        with patch.dict(os.environ, {'DRLINK_CONFIRM': ''}):
            self.assertFalse(backend._confirm_requested(None))
            self.assertFalse(backend._confirm_requested(False))

    def test_safe_conditional_path_does_not_add_confirmation(self):
        proc = self.control_boundary('', conditional=True, safe=True)
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output)
        self.assertIn('STUB_EFFECT_CONFIRMED', output)
        self.assertNotIn('Required approval', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
