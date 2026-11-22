#!/usr/bin/env python3
"""Public FQDN short bootstrap cannot bypass OS TLS or allocator identity proof."""
import importlib.machinery
import importlib.util
import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
_loader = importlib.machinery.SourceFileLoader('zt_public_fqdn_trust', str(ROOT / 'tools/frp-create-client'))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
CLI = importlib.util.module_from_spec(_spec)
sys.modules[_loader.name] = CLI
_loader.exec_module(CLI)

class PublicFQDNTrustTests(unittest.TestCase):
    def verify(self, cfg, code=404, body=b'bootstrap unavailable', *, request_ok=False):
        opener = mock.Mock()
        if request_ok:
            opener.open.return_value = mock.MagicMock()
            opener.open.return_value.__enter__.return_value.status = 200
        else:
            opener.open.side_effect = urllib.error.HTTPError(
                'https://remote.isoc.ooo/i/invalid-qualification-probe',
                code, 'test', {}, io.BytesIO(body)
            )
        with mock.patch.object(CLI, '_test_root', return_value=False), \
             mock.patch('urllib.request.build_opener', return_value=opener) as factory, \
             mock.patch('ssl.create_default_context') as ctx:
            host = CLI.short_url_host_for_cfg(cfg)
        self.assertTrue(factory.called)
        ctx.assert_called_once_with()  # No cafile/insecure override allowed.
        args = factory.call_args.args
        self.assertTrue(any(type(arg).__name__ == 'NoRedirect' for arg in args))
        opener.open.assert_called_once()
        self.assertIn('/i/invalid-qualification-probe', opener.open.call_args.args[0])
        return host

    def test_explicit_and_inferred_hostnames_share_real_tls_qualification(self):
        self.assertEqual(self.verify({'bootstrap_hostname':'remote.isoc.ooo'}), 'remote.isoc.ooo')
        self.assertEqual(self.verify({'public_hostname':'remote.isoc.ooo'}), 'remote.isoc.ooo')
        self.assertEqual(self.verify({'public_url_host':'remote.isoc.ooo'}), 'remote.isoc.ooo')

    def test_negative_https_handler_responses_are_not_qualified(self):
        for cfg in ({'bootstrap_hostname':'remote.isoc.ooo'}, {'public_hostname':'remote.isoc.ooo'}):
            with self.subTest(cfg=cfg):
                self.assertEqual(self.verify(cfg, code=404, body=b'<html>not found</html>'), '')
                self.assertEqual(self.verify(cfg, code=403), '')
                self.assertEqual(self.verify(cfg, request_ok=True), '')

    def test_transport_failure_and_invalid_hostname_fail_closed(self):
        for cfg in ({'bootstrap_hostname':'localhost'}, {'bootstrap_hostname':'remote.isoc.ooo.local'},
                    {'bootstrap_hostname':'bad name'}, {'public_hostname':'127.0.0.1'}):
            with self.subTest(cfg=cfg):
                with mock.patch.object(CLI, '_test_root', return_value=False):
                    self.assertEqual(CLI.short_url_host_for_cfg(cfg), '')
        with mock.patch.object(CLI, '_test_root', return_value=False), \
             mock.patch('urllib.request.build_opener') as f:
            f.return_value.open.side_effect = OSError('connection refused')
            self.assertEqual(CLI.short_url_host_for_cfg({'public_hostname':'remote.isoc.ooo'}), '')

    def test_simplest_stock_ca_short_command_not_replaced_by_private_ca_shell(self):
        import frp_zero_touch as zt
        cmd = zt.short_url_command('remote.isoc.ooo', 'A'*22)
        self.assertIn('curl -fsSL https://remote.isoc.ooo/i/', cmd)
        self.assertIn('printf', cmd)
        self.assertNotIn('openssl s_client', cmd)
        self.assertNotIn('--insecure', cmd)
        self.assertLessEqual(len(cmd), 200)

if __name__ == '__main__':
    unittest.main(verbosity=2)
