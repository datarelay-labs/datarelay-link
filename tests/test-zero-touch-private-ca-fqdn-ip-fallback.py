#!/usr/bin/env python3
"""No-public-CA FQDN may bootstrap via the *configured* IP only after CA+SAN proof.

Hermetic, no tickets/credentials/Server configuration/network writes.
"""
import importlib.machinery
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))

loader = importlib.machinery.SourceFileLoader('zt_ip_fallback_cli', str(ROOT / 'tools/frp-create-client'))
spec = importlib.util.spec_from_loader(loader.name, loader)
CLI = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = CLI
loader.exec_module(CLI)
import frp_zero_touch as ZT

FQDN = 'remote.isoc.ooo'
IP = '221.139.249.109'
CA_FP = 'a' * 64
LEAF_FP = 'b' * 64
INSTALLER = 'https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh'


class PrivateCAFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ca = Path(self.tmp.name) / 'ca.crt'
        self.leaf = Path(self.tmp.name) / 'leaf.crt'
        self.ca.write_text('fixture public CA\n')
        self.leaf.write_text('fixture public leaf\n')
        self.cfg = {
            'public_hostname': FQDN,
            'public_ip': IP,
            'allocator_public_url': 'https://remote.isoc.ooo/enroll',
            'tls_ca_cert': str(self.ca),
            'tls_server_cert': str(self.leaf),
        }
        self.pki = mock.Mock()
        self.pki.fingerprint_from_cert_file.side_effect = lambda path: (
            CA_FP if Path(path) == self.ca else LEAF_FP)
        self.pki.verify_cert_signed_by_ca.return_value = None
        self.pki.cert_covers_identities.return_value = True
        patches = [
            mock.patch.object(CLI, 'load_zero_touch', return_value=ZT),
            mock.patch.object(CLI, 'load_frp_pki', return_value=self.pki),
            mock.patch.object(CLI, 'remap', side_effect=lambda x: Path(x)),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def plan(self, cfg=None, fp=CA_FP):
        return CLI.private_ca_ip_bootstrap_plan(self.cfg if cfg is None else cfg, fp)

    def test_private_ca_fqdn_uses_configured_numeric_ip_with_both_sans(self):
        plan = self.plan()
        self.assertEqual(plan['allocator'], 'https://221.139.249.109/enroll')
        self.assertEqual(plan['authority'], IP)
        self.assertEqual(plan['leaf_sha256'], LEAF_FP)
        self.pki.verify_cert_signed_by_ca.assert_called_once_with(self.ca, self.leaf)
        self.pki.cert_covers_identities.assert_called_once_with(
            self.leaf, [FQDN], [IP])

    def test_untrusted_fqdn_selects_pinned_ip_before_issuance(self):
        with mock.patch.object(CLI, 'short_url_host_for_cfg', return_value=''), \
             mock.patch.object(CLI, 'preflight_installer_url') as preflight:
            name, plan = CLI.validate_zero_touch_prerequisites(
                self.cfg, 'linux', INSTALLER, CA_FP)
        self.assertEqual(name, '')
        self.assertEqual(plan['allocator'], 'https://221.139.249.109/enroll')
        preflight.assert_called_once_with(
            INSTALLER, label='Agent installer URL', strict_https=True, ca_file=self.ca)

    def test_trusted_fqdn_keeps_short_stock_trust_flow(self):
        with mock.patch.object(CLI, 'short_url_host_for_cfg', return_value=FQDN), \
             mock.patch.object(CLI, 'preflight_installer_url') as preflight, \
             mock.patch.object(CLI, 'private_ca_ip_bootstrap_plan') as fallback:
            name, plan = CLI.validate_zero_touch_prerequisites(
                self.cfg, 'linux', INSTALLER, CA_FP)
        self.assertEqual(name, FQDN)
        self.assertIsNone(plan)
        fallback.assert_not_called()
        preflight.assert_called_once_with(
            INSTALLER, label='Agent installer URL', strict_https=True, ca_file=None)

    def test_untrusted_fqdn_never_sends_credential_using_original_dns(self):
        fake = mock.Mock()
        fake.private_ca_ip_linux_command.return_value = 'bash -c protected'
        with mock.patch.object(CLI, 'short_url_host_for_cfg', return_value=''), \
             mock.patch.object(CLI, '_zt', return_value=fake), \
             mock.patch('sys.stdout', new_callable=io.StringIO) as output:
            CLI.print_one_line(
                'ticket-not-displayed', 600, '', IP, 443,
                self.cfg['allocator_public_url'], CA_FP, INSTALLER, 22,
                cfg=self.cfg, short_handle='A' * 22, private_ip_plan=self.plan(),
            )
        fake.private_ca_ip_linux_command.assert_called_once_with(
            'https://221.139.249.109/enroll', CA_FP, 'A'*22)
        self.assertIn('bash -c protected', output.getvalue())
        self.assertNotIn('ticket-not-displayed', output.getvalue())

    def test_windows_pins_same_numeric_ip(self):
        fake = mock.Mock()
        fake.private_ca_ip_windows_command.return_value = 'powershell -NoProfile'
        with mock.patch.object(CLI, 'short_url_host_for_cfg', return_value=''), \
             mock.patch.object(CLI, '_zt', return_value=fake), \
             mock.patch('sys.stdout', new_callable=io.StringIO):
            CLI.print_one_line_windows(
                'ticket-not-displayed', 600, '', IP, 443,
                self.cfg['allocator_public_url'], CA_FP, INSTALLER,
                cfg=self.cfg, short_handle='A' * 22,
                stage1_sha256='d'*64, private_ip_plan=self.plan(),
            )
        fake.private_ca_ip_windows_command.assert_called_once_with(
            'https://221.139.249.109/enroll', CA_FP, 'd'*64, 'A'*22)

    def test_missing_or_invalid_public_ip_does_not_bypass_fqdn_trust(self):
        for bad in ('', 'remote.isoc.ooo', '0.0.0.0', '224.0.0.1'):
            with self.subTest(bad=bad):
                cfg = dict(self.cfg, public_ip=bad)
                self.assertIsNone(self.plan(cfg))
        for invalid in (
            'https://evil@remote.isoc.ooo/enroll',
            'http://remote.isoc.ooo/enroll',
            'https://remote.isoc.ooo/enroll?token=foo',
            'https://remote.isoc.ooo/other',
        ):
            with self.subTest(allocator=invalid):
                self.assertIsNone(self.plan(dict(
                    self.cfg, allocator_public_url=invalid)))

    def test_ca_or_leaf_mismatch_fails_closed(self):
        self.assertIsNone(self.plan(fp='c' * 64))
        self.pki.verify_cert_signed_by_ca.side_effect = ValueError('bad signature')
        self.assertIsNone(self.plan())
        self.pki.verify_cert_signed_by_ca.side_effect = None
        self.pki.cert_covers_identities.return_value = False
        self.assertIsNone(self.plan())
        with mock.patch.object(CLI, 'short_url_host_for_cfg', return_value=''):
            with self.assertRaises(SystemExit):
                CLI.validate_zero_touch_prerequisites(
                    self.cfg, 'linux', INSTALLER, CA_FP)

    def test_pinned_ca_preflight_head_501_falls_back_to_strict_get(self):
        import urllib.error
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = b'#'
        head_error = urllib.error.HTTPError(
            INSTALLER, 501, 'HEAD unsupported', {}, io.BytesIO(b''))
        opener = mock.Mock()
        opener.open.side_effect = [head_error, response]
        with mock.patch('ssl.create_default_context') as context, \
             mock.patch('urllib.request.build_opener', return_value=opener):
            self.assertIsNone(CLI.preflight_installer_url(
                INSTALLER, strict_https=True, ca_file=self.ca))
        context.assert_called_once_with(cafile=str(self.ca))
        self.assertEqual(opener.open.call_count, 2)
        methods = [call.args[0].get_method()
                   for call in opener.open.call_args_list]
        self.assertEqual(methods, ['HEAD', 'GET'])
        response.__enter__.return_value.read.assert_called_once_with(1)

    def test_head_501_get_404_and_redirect_fail_closed(self):
        import urllib.error
        for get_code in (302, 404, 503):
            with self.subTest(get_code=get_code):
                opener = mock.Mock()
                opener.open.side_effect = [
                    urllib.error.HTTPError(
                        INSTALLER, 501, 'HEAD unsupported', {}, io.BytesIO(b'')),
                    urllib.error.HTTPError(
                        INSTALLER, get_code, 'GET failure', {}, io.BytesIO(b'')),
                ]
                with mock.patch('urllib.request.build_opener', return_value=opener):
                    with self.assertRaises(SystemExit):
                        CLI.preflight_installer_url(
                            INSTALLER, strict_https=True, ca_file=self.ca)

    def test_invalid_pinned_ca_preflight_refuses_before_network(self):
        import ssl
        with mock.patch('ssl.create_default_context',
                        side_effect=ssl.SSLError('bad CA')), \
             mock.patch('urllib.request.build_opener') as opener:
            with self.assertRaises(SystemExit):
                CLI.preflight_installer_url(
                    INSTALLER, strict_https=True, ca_file=self.ca)
        opener.assert_not_called()

    def test_existing_numeric_ip_mode_is_unchanged(self):
        cfg = dict(self.cfg, allocator_public_url='https://221.139.249.109/enroll')
        plan = self.plan(cfg)
        self.assertEqual(plan['allocator'], cfg['allocator_public_url'])
        self.pki.cert_covers_identities.assert_called_with(
            self.leaf, [], [IP])


if __name__ == '__main__':
    unittest.main(verbosity=2)
