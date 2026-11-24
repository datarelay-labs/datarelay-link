#!/usr/bin/env python3
"""Pure entry-field regression. Does not issue tickets or install agents."""
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import frp_zero_touch as zt


class EntryFields(unittest.TestCase):
    def test_templates(self):
        for authority in ("remote.xdr.ooo", "192.0.2.20", "192.0.2.20:6099",
                          "private.example:8443"):
            url = "https://" + authority + "/A3xK9m"
            for os_name in ("linux", "macos"):
                self.assertEqual(zt.render_entry_command(authority, "A3xK9m", os_name),
                                 "curl -kfsS " + url + "|sudo bash")
            self.assertEqual(zt.render_entry_command(authority, "A3xK9m", "windows"),
                             "iex(curl.exe -kfsS " + url + "|Out-String)")

    def test_ipv6_authority_syntax_only(self):
        # Native shell execution of the unquoted IPv6 template remains a
        # separate platform qualification requirement.
        self.assertEqual(zt.entry_authority("[2001:db8::1]:6099"),
                         "[2001:db8::1]:6099")
        for value in ("[not-ip]", "[2001:::1]", "[::1]:99999",
                      "2001:db8::1", "[::1]extra"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                zt.entry_authority(value)

    def test_locator_not_credential(self):
        self.assertTrue(zt.is_bootstrap_locator("A3xK9m"))
        self.assertFalse(zt.accepted_bootstrap_credential("A3xK9m"))
        self.assertEqual(zt.bootstrap_record_id("A3xK9m"), "")
        for value in ("", "abcde", "abcdefg", "enroll", "ENROLL", "a/bcde",
                      "abcde?", "x" * 22, " abcde", "abcde\n"):
            with self.subTest(value=value):
                self.assertFalse(zt.is_bootstrap_locator(value))
                with self.assertRaises(ValueError):
                    zt.render_entry_command("remote.xdr.ooo", value, "linux")

    def test_authority_rejects_injection(self):
        for authority in ("", "https://host.test", "host.test/path",
                          "user@host.test", "host.test:0", "host.test:65536",
                          "host.test?foo=1", "host.test#frag", "host.test;id",
                          "host.test\n", "host.test:abc", "host.test:",
                          "host.test|id", "host.test$HOME", "1.2.3.999",
                          "host.test:0443", "host.test.", "-host.test"):
            with self.subTest(authority=authority), self.assertRaises(ValueError):
                zt.render_entry_command(authority, "A3xK9m", "linux")

    def test_platform_selected_at_issuance(self):
        for platform in ("", "auto", "powershell", "LINUX"):
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                zt.render_entry_command("remote.xdr.ooo", "A3xK9m", platform)

    @unittest.skipUnless(os.name == 'posix' and all(shutil.which(x) for x in
                         ('curl', 'bash', 'openssl')), 'local TLS shell tools unavailable')
    def test_loopback_entry_transport(self):
        # Controlled inert response, no installation or enrollment. This
        # tests actual native curl/Bash (and Linux pwsh if available), not
        # downstream TLS security or installed-product qualification.
        import frp_pki
        with tempfile.TemporaryDirectory(prefix='drlink-entry-transport-') as temp:
            root = Path(temp)
            pki = frp_pki.ensure_pki(root / 'pki', '127.0.0.1')
            paths = []

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def do_GET(self):
                    paths.append(self.path)
                    payloads = {
                        '/A3xK9m': b"printf 'ENTRY_BASH_OK\n'\n",
                        '/W3xK9m': b"Write-Output 'ENTRY_PWSH_OK'\n",
                    }
                    body = payloads.get(self.path)
                    if body is None:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            server = HTTPServer(('127.0.0.1', 0), Handler)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(pki['server_crt'], pki['server_key'])
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            (root / 'sudo').write_text('#!/bin/sh\nexec "$@"\n')
            (root / 'sudo').chmod(0o755)
            (root / 'curl.exe').symlink_to(shutil.which('curl'))
            env = dict(os.environ, PATH=temp + os.pathsep + os.environ['PATH'])
            authority = '127.0.0.1:%d' % server.server_port
            try:
                for os_name in ('linux', 'macos'):
                    cmd = zt.render_entry_command(authority, 'A3xK9m', os_name)
                    result = subprocess.run(['bash', '-c', cmd], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), 'ENTRY_BASH_OK')
                self.assertEqual(paths, ['/A3xK9m', '/A3xK9m'])
                cmd = zt.render_entry_command(authority, 'BAD999', 'linux')
                result = subprocess.run(['bash', '-c', cmd], env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotIn('ENTRY_BASH_OK', result.stdout)
                self.assertIn('404', result.stderr)
                # Pipeline exit alone is not evidence of installation.
                if shutil.which('pwsh'):
                    cmd = zt.render_entry_command(authority, 'W3xK9m', 'windows')
                    result = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive',
                                             '-Command', cmd], env=env,
                                            capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), 'ENTRY_PWSH_OK')
                    self.assertEqual(paths[-1], '/W3xK9m')
                    print('LOOPBACK_LINUX_PWSH=PASS')
                else:
                    print('LOOPBACK_LINUX_PWSH=NOT_RUN')
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)

    def test_candidate_generation_skips_reserved(self):
        with patch.object(zt.secrets, "choice", side_effect=list("enrollA3xK9m")):
            self.assertEqual(zt.new_bootstrap_locator(), "A3xK9m")
        self.assertTrue(all(zt.is_bootstrap_locator(zt.new_bootstrap_locator())
                            for _ in range(100)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
