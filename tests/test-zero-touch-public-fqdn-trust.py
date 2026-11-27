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
    def verify(self, authority, code=404, body=b'bootstrap unavailable', *, request_ok=False):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            ca=Path(temp)/"ca.crt"; ca.write_text("fixture")
            cfg={"allocator_public_url":"https://"+authority+"/enroll","tls_ca_cert":str(ca)}
            opener=mock.Mock()
            if request_ok:
                opener.open.return_value=mock.MagicMock()
            else:
                opener.open.side_effect=urllib.error.HTTPError(
                    "https://"+authority+"/ZT000000",code,"fixture",{},io.BytesIO(body))
            with mock.patch.object(CLI,"_test_root",return_value=""), \
                 mock.patch.object(CLI,"fingerprint_from_cert",return_value="a"*64), \
                 mock.patch.object(CLI,"preflight_installer_url") as downstream, \
                 mock.patch("urllib.request.build_opener",return_value=opener) as factory, \
                 mock.patch("ssl._create_unverified_context") as entry:
                result=CLI.validate_zero_touch_prerequisites(cfg,"linux",
                    "https://"+authority+"/fixture/bootstrap-client.sh","a"*64)
            entry.assert_called_once_with()
            self.assertTrue(any(type(arg).__name__=="NoRedirect" for arg in factory.call_args.args))
            opener.open.assert_called_once_with("https://"+authority+"/ZT000000",timeout=5)
            self.assertTrue(downstream.call_args.kwargs["strict_https"])
            self.assertEqual(downstream.call_args.kwargs["ca_file"],ca)
            return result

    def test_public_private_authorities_share_route_probe(self):
        for authority in ("remote.example.test","192.0.2.20:6099","private.example.test"):
            self.assertEqual(self.verify(authority),authority)

    def test_wrong_route_and_redirect_fail_closed(self):
        for code,body in ((404,b"<html>wrong</html>"),(403,b""),(302,b""),(503,b"")):
            with self.subTest(code=code), self.assertRaises(SystemExit):
                self.verify("remote.example.test",code,body)
        with self.assertRaises(SystemExit):
            self.verify("remote.example.test",request_ok=True)

    def test_fqdn_installer_preflight_requires_trusted_https_200_before_ticket(self):
        url = 'https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh'
        with self.assertRaises(SystemExit):
            CLI.preflight_installer_url('http://remote.isoc.ooo/a', strict_https=True)
        with self.assertRaises(SystemExit):
            CLI.preflight_installer_url('https://user:pass@remote.isoc.ooo/a', strict_https=True)
        for failure in (OSError('untrusted certificate'),
                        urllib.error.HTTPError(url, 404, 'not found', {}, io.BytesIO(b'')),
                        urllib.error.HTTPError(url, 302, 'redirect', {}, io.BytesIO(b'')),
                        urllib.error.HTTPError(url, 503, 'failure', {}, io.BytesIO(b''))):
            with self.subTest(failure=str(failure)):
                opener = mock.Mock()
                opener.open.side_effect = failure
                with mock.patch('urllib.request.build_opener', return_value=opener) as factory:
                    with self.assertRaises(SystemExit):
                        CLI.preflight_installer_url(url, strict_https=True)
                self.assertTrue(any(type(v).__name__ == 'NoRedirect' for v in factory.call_args.args))
                self.assertTrue(any(type(v).__name__ == 'ProxyHandler' for v in factory.call_args.args))
        opener = mock.Mock()
        opener.open.return_value = mock.MagicMock()
        opener.open.return_value.__enter__.return_value.status = 200
        with mock.patch('urllib.request.build_opener', return_value=opener):
            self.assertIsNone(CLI.preflight_installer_url(url, strict_https=True))
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'HEAD')
        self.assertEqual(request.full_url, url)

    def test_same_fixed_command_for_both_tls_modes(self):
        import frp_zero_touch as zt
        for host in ("remote.example.test","private.example.test","192.0.2.20:6099"):
            self.assertEqual(zt.render_entry_command(host,"A3xK9mP2","linux"),
                             "curl -kfsS https://"+host+"/A3xK9mP2|sudo bash")

if __name__ == '__main__':
    unittest.main(verbosity=2)
