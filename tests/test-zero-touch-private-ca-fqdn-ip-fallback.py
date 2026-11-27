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

    def test_configured_authority_is_not_replaced_by_ip_fallback(self):
        self.assertEqual(CLI.entry_authority_for_cfg(self.cfg),FQDN)
        self.assertEqual(CLI.entry_authority_for_cfg(dict(self.cfg,bootstrap_hostname="private.example")), "private.example")
        self.assertEqual(CLI.entry_authority_for_cfg(dict(self.cfg,allocator_public_url="https://"+IP+"/enroll")),IP)

    def test_bad_authority_rejected_instead_of_fallback(self):
        for host in ("bad host","https://example.test","host/path","user@host"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                CLI.entry_authority_for_cfg(dict(self.cfg,bootstrap_hostname=host))

    def test_ca_mismatch_denies_before_probe_or_issuance(self):
        with mock.patch.object(CLI,"fingerprint_from_cert",return_value="c"*64), \
             mock.patch("urllib.request.build_opener") as opener:
            with self.assertRaises(SystemExit):
                CLI.validate_zero_touch_prerequisites(self.cfg,"linux",INSTALLER,CA_FP)
            opener.assert_not_called()

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

if __name__ == '__main__':
    unittest.main(verbosity=2)
