#!/usr/bin/env python3
"""Zero-Touch stage 1 must be served for the installer URL the CLI derived.

The CLI accepts a Server without a configured client_installer_url because it
derives the Server-local qualified installer URL from allocator_public_url and
issues a ticket. The allocator's short-URL endpoint used to read only the
configured value and answered HTTP 503 for every such ticket. Isolated
fixtures only; no Server, network or installed artifact is touched.
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
sys.path.insert(0, str(ROOT / 'lib'))

spec = importlib.util.spec_from_file_location(
    'frp_port_allocator', ROOT / 'server' / 'frp-port-allocator.py')
MOD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MOD)

FAILED = 0
ALLOCATOR_URL = 'https://203.0.113.10:6099/enroll'
DERIVED_LINUX = 'https://203.0.113.10:6099/artifacts/agent/bootstrap-client.sh'


def pass_(name):
    print('PASS', name)


def fail(name, detail=''):
    global FAILED
    FAILED += 1
    print('FAIL', name, detail)

class BaseQA:
    class ArtifactError(Exception):
        pass

    @staticmethod
    def installed_root():
        return Path('/nonexistent-qualified-root')

    @staticmethod
    def lookup_installed(root, kind, plat, arch):
        return {'sha256': 'b' * 64, 'source_head': 'a' * 40}

    @staticmethod
    def load_manifest(root):
        return {'qualification_status': 'PASS', 'source_head': 'a' * 40,
                'immutable_source_ref': 'a' * 40, 'channel': 'development'}

    @staticmethod
    def is_forbidden_public_installer_url(url):
        return False


class Env:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / 'registry.json'
        self.token = self.root / 'server_token'
        self.enrollments = self.root / 'enrollments'
        self.enrollments.mkdir()
        self.token.write_text('test-frp-token-do-not-use\n')
        self.token.chmod(0o600)
        self.ca = self.root / 'ca.crt'
        self.ca.write_text('not-a-cert\n')
        self.cfg = self.root / 'config.json'
        self.cfg.write_text(json.dumps({
            'public_host': '203.0.113.10', 'public_ip': '203.0.113.10',
            'frp_control_public_port': 8443, 'control_port': 443,
            'port_start': 19000, 'port_end': 19020,
            'listen_host': '127.0.0.1', 'listen_port': 6099,
            'registry_file': str(self.registry),
            'enrollments_dir': str(self.enrollments),
            'token_file': str(self.token),
            'allocator_public_url': ALLOCATOR_URL,
            'tls_ca_cert': str(self.ca),
        }, indent=2) + '\n')
        MOD.atomic_write_json(self.registry, MOD.empty_registry())
        self.allocator = MOD.Allocator(str(self.cfg))
        MOD.port_is_available = lambda port: True

    def handle(self):
        services = MOD.normalize_services([{
            'id': 'ssh', 'name': 'SSH', 'protocol': 'tcp',
            'local_ip': '127.0.0.1', 'local_port': 22,
            'preset': 'ssh', 'ssh_user': 'aella'}])
        _ticket, _enroll, record = self.allocator.issue_bootstrap_ticket(
            services, 600, 'fixture')
        return str(record.get('_short_handle') or '')

    def build(self, handle, platform='linux'):
        original = MOD.PKI.fingerprint_from_cert_file
        MOD.PKI.fingerprint_from_cert_file = lambda path: 'cd' * 32
        try:
            return self.allocator.build_short_url_script(handle, platform)
        finally:
            MOD.PKI.fingerprint_from_cert_file = original

    def cleanup(self):
        self.tmp.cleanup()


def test_unconfigured_installer_is_derived_like_the_cli():
    env = Env()
    try:
        if env.allocator.cfg.get('client_installer_url'):
            fail('fixture must not configure client_installer_url')
            return
        original = MOD.QA
        calls = []

        class FakeQA(BaseQA):
            @staticmethod
            def agent_installer_url(allocator_url, platform='linux'):
                calls.append((allocator_url, platform))
                return DERIVED_LINUX

            @staticmethod
            def is_forbidden_public_installer_url(url):
                return 'github' in url

        MOD.QA = FakeQA
        try:
            script = env.build(env.handle(), 'linux')
        finally:
            MOD.QA = original
        if not script:
            fail('derived installer: stage 1 not served (HTTP 503 regression)')
            return
        if DERIVED_LINUX not in script and 'zt1.' not in script:
            fail('derived installer: script does not reference the derived installer')
            return
        if calls != [(ALLOCATOR_URL, 'linux')]:
            fail('derived installer: unexpected derivation calls', calls)
            return
        pass_('UNCONFIGURED_INSTALLER_DERIVED')
    finally:
        env.cleanup()


def test_configured_installer_wins_over_derivation():
    env = Env()
    try:
        env.allocator.cfg['client_installer_url'] = 'https://remote.example/bootstrap-client.sh'
        original = MOD.QA

        class FakeQA(BaseQA):
            @staticmethod
            def agent_installer_url(allocator_url, platform='linux'):
                raise AssertionError('derivation must not run when configured')

            @staticmethod
            def is_forbidden_public_installer_url(url):
                return False

        MOD.QA = FakeQA
        try:
            script = env.build(env.handle(), 'linux')
        finally:
            MOD.QA = original
        if not script:
            fail('configured installer: stage 1 not served')
            return
        pass_('CONFIGURED_INSTALLER_UNCHANGED')
    finally:
        env.cleanup()


def test_derivation_failure_and_forbidden_url_fail_closed():
    env = Env()
    try:
        original = MOD.QA

        class BrokenQA(BaseQA):
            @staticmethod
            def agent_installer_url(allocator_url, platform='linux'):
                raise RuntimeError('artifact root missing')

            @staticmethod
            def is_forbidden_public_installer_url(url):
                return False

        class PublicQA(BaseQA):
            @staticmethod
            def agent_installer_url(allocator_url, platform='linux'):
                return 'https://raw.githubusercontent.com/datarelay-labs/x/bootstrap-client.sh'

            @staticmethod
            def is_forbidden_public_installer_url(url):
                return 'githubusercontent' in url

        handle = env.handle()
        for name, fake in (('derivation error', BrokenQA), ('forbidden public URL', PublicQA)):
            MOD.QA = fake
            try:
                if env.build(handle, 'linux') is not None:
                    fail('%s must fail closed' % name)
                    return
            finally:
                MOD.QA = original
        MOD.QA = None
        try:
            if env.build(handle, 'linux') is not None:
                fail('missing QA module must fail closed')
                return
        finally:
            MOD.QA = original
        pass_('DERIVATION_FAILS_CLOSED')
    finally:
        env.cleanup()


def test_non_https_allocator_never_derives():
    env = Env()
    try:
        env.allocator.cfg['allocator_public_url'] = 'http://203.0.113.10:6099/enroll'
        original = MOD.QA

        class FakeQA(BaseQA):
            @staticmethod
            def agent_installer_url(allocator_url, platform='linux'):
                raise AssertionError('must not derive for a non-HTTPS allocator')

            @staticmethod
            def is_forbidden_public_installer_url(url):
                return False

        MOD.QA = FakeQA
        try:
            if env.build(env.handle(), 'linux') is not None:
                fail('non-HTTPS allocator must fail closed')
                return
        finally:
            MOD.QA = original
        pass_('NON_HTTPS_ALLOCATOR_FAILS_CLOSED')
    finally:
        env.cleanup()


if __name__ == '__main__':
    test_unconfigured_installer_is_derived_like_the_cli()
    test_configured_installer_wins_over_derivation()
    test_derivation_failure_and_forbidden_url_fail_closed()
    test_non_https_allocator_never_derives()
    sys.exit(1 if FAILED else 0)
