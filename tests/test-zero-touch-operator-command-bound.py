#!/usr/bin/env python3
"""Zero-Touch operator command bound for Linux, macOS, and Windows.

These fixtures contain fake credentials and do not create enrollment tickets.
"""
from __future__ import annotations
import importlib.machinery
import hashlib
import io
import os
import shutil
import ssl
import threading
import json
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import frp_zero_touch as zt

cli = importlib.machinery.SourceFileLoader(
    "frp_create_client_compact_contract", str(ROOT / "tools/frp-create-client")
).load_module()
HOST = "remote.xdr.ooo"
TICKET = "bt1." + ("a" * 16) + "." + ("b" * 64)
HANDLE = "x" * 22
HASH = "c" * 64


class CompactZeroTouchContract(unittest.TestCase):
    def test_linux_and_macos_default_install_commands_have_bounded_length(self):
        self.assertEqual(
            cli.short_url_host_for_cfg({"bootstrap_hostname": HOST}), HOST
        )
        for platform in ("linux", "macos"):
            self.assertEqual(
                cli.parse_args(["--one-line", "--platform", platform]).platform,
                platform,
            )
            line = zt.short_url_command(HOST, HANDLE)
            self.assertLessEqual(len(line), 200, (platform, len(line)))
            self.assertIn("/i/", line)
            self.assertIn("curl -fsSL https://", line)
            self.assertNotIn("--insecure", line)
            self.assertNotIn(" -k", line)
            self.assertNotIn("zt1.", line)

    @unittest.skipUnless(shutil.which('shasum') and shutil.which('awk'),
                         'native shasum/awk unavailable')
    def test_macos_stage1_installer_sha256_without_gnu_sha256sum(self):
        """Stock macOS has shasum, not the GNU sha256sum command."""
        ticket = 'bt1.' + ('a' * 16) + '.' + ('b' * 64)
        script = zt.render_short_url_bootstrap_script(
            'https://192.0.2.20:6099/enroll', 'c' * 64, ticket,
            'https://192.0.2.20:6099/artifacts/agent/bootstrap-client.sh',
        )
        self.assertIn('shasum -a 256 "$INSTALLER_FILE"', script)
        self.assertIn('if [[ "$GOT" != "$WANT" ]]; then', script)
        start = script.index('if command -v sha256sum')
        end = script.index('if [[ "$GOT" != "$WANT" ]]', start)
        hash_shell = 'set -euo pipefail\n' + script[start:end] + 'printf "%s" "$GOT"\n'
        with tempfile.TemporaryDirectory(prefix='drlink-macos-sha-') as temp:
            base = Path(temp)
            payload = base / 'installer.sh'
            payload.write_bytes(b'#!/bin/bash\nprintf MACOS_NATIVE\n')
            expected = hashlib.sha256(payload.read_bytes()).hexdigest()
            bin_dir = base / 'bin'
            bin_dir.mkdir()
            for name in ('shasum', 'awk'):
                (bin_dir / name).symlink_to(shutil.which(name))
            # PATH deliberately excludes sha256sum, the stock macOS baseline.
            env = dict(os.environ, PATH=str(bin_dir), INSTALLER_FILE=str(payload))
            good = subprocess.run(['/bin/bash', '-c', hash_shell], env=env,
                                  text=True, capture_output=True, timeout=9)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(good.stdout, expected)
            (bin_dir / 'shasum').unlink()
            missing = subprocess.run(['/bin/bash', '-c', hash_shell], env=env,
                                     text=True, capture_output=True, timeout=9)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('SHA256 verifier unavailable', missing.stderr)

    def test_windows_hash_first_within_single_copy_command(self):
        line = zt.windows_strict_launcher(HOST, HANDLE, HASH)
        self.assertLessEqual(len(line), 500, len(line))
        self.assertIn("Get-FileHash", line)
        self.assertIn(HASH, line)
        self.assertIn("powershell.exe -NoProfile", line)
        self.assertNotIn(" -k", line)
        self.assertNotIn("--insecure", line)

    def test_private_ca_not_silently_treated_as_trusted_public_tls(self):
        # A configuration value or FQDN alone is never a trust proof.
        with mock.patch.object(cli, "_test_root", return_value="/tmp/drlink-test"):
            self.assertEqual(
                cli.short_url_host_for_cfg({"public_url_host": HOST}), ""
            )
        self.assertEqual(cli.short_url_host_for_cfg({"bootstrap_hostname": HOST}), HOST)
        self.assertEqual(zt.short_url_for_ticket(HOST, TICKET).count("/i/"), 1)

    def test_public_https_probe_requires_real_allocator_fail_closed_signature(self):
        import io
        import urllib.error

        class FakeOpener:
            def __init__(self, content):
                self.content = content
            def open(self, url, timeout=0):
                raise urllib.error.HTTPError(
                    url, 404, "Not Found", {}, io.BytesIO(self.content)
                )

        with mock.patch.object(cli, "_test_root", return_value=""):
            with mock.patch("urllib.request.build_opener", return_value=FakeOpener(
                b"bootstrap unavailable\n"
            )):
                self.assertEqual(
                    cli.short_url_host_for_cfg({"public_hostname": HOST}), HOST
                )
            with mock.patch("urllib.request.build_opener", return_value=FakeOpener(
                b"<html>generic nginx 404</html>\n"
            )):
                self.assertEqual(
                    cli.short_url_host_for_cfg({"public_hostname": HOST}), ""
                )

    def test_private_ca_numeric_ip_has_compact_verified_command(self):
        import frp_pki
        with tempfile.TemporaryDirectory(prefix="drlink-ip-bootstrap-") as tmp:
            data = frp_pki.ensure_pki(Path(tmp) / "pki", "192.0.2.20")
            cfg = {
                "allocator_public_url": "https://192.0.2.20:6099/enroll",
                "tls_ca_cert": data["ca_crt"],
                "tls_server_cert": data["server_crt"],
            }
            plan = cli.private_ca_ip_bootstrap_plan(cfg, data["fingerprint"])
            self.assertEqual(plan["mode"], "private_ca_ip")
            self.assertEqual(plan["authority"], "192.0.2.20:6099")
            command = zt.private_ca_ip_linux_command(
                cfg["allocator_public_url"], data["fingerprint"], HANDLE
            )
            self.assertLessEqual(len(command), 900, len(command))
            self.assertIn("openssl s_client", command)
            self.assertIn("--cacert", command)
            self.assertIn("/i/", command)
            self.assertNotIn("--insecure", command)
            self.assertNotIn("curl -k", command)
            self.assertNotIn("zt1.", command)
            self.assertIsNone(cli.private_ca_ip_bootstrap_plan(cfg, "0" * 64))
            cfg["allocator_public_url"] = "https://192.0.2.21:6099/enroll"
            self.assertIsNone(cli.private_ca_ip_bootstrap_plan(cfg, data["fingerprint"]))

    def test_default_ip_only_linux_mints_short_issuer_command(self):
        import frp_pki
        with tempfile.TemporaryDirectory(prefix='drlink-ip-command-') as td:
            root = Path(td)
            issued = frp_pki.ensure_pki(root / 'pki', '192.0.2.20')
            cfg = {
                'enrollments_dir': str(root / 'enrollments'),
                'allocator_public_url': 'https://192.0.2.20:6099/enroll',
                'tls_ca_cert': issued['ca_crt'],
                'tls_server_cert': issued['server_crt'],
                'client_installer_url': 'https://example.test/installer.sh',
            }
            (root / 'config.json').write_text(json.dumps(cfg))
            class FakeAllocator:
                ServiceValidationError = ValueError
                @staticmethod
                def normalize_services(items):
                    return items
                @staticmethod
                def issue_bootstrap_ticket(*args, **kwargs):
                    return TICKET, {}, {'id': 'f' * 16, '_short_handle': HANDLE}
            output = io.StringIO()
            with mock.patch.object(cli, 'CONFIG', str(root / 'config.json')), \
                 mock.patch.object(cli, 'require_onboarding_config'), \
                 mock.patch.object(cli, 'resolve_configured_installer_url', return_value=cfg['client_installer_url']), \
                 mock.patch.object(cli, 'preflight_installer_url'), \
                 mock.patch.object(cli, 'load_allocator', return_value=FakeAllocator), \
                 mock.patch.object(cli, 'run_enrollment_retention_cleanup'), \
                 mock.patch.object(cli, 'short_url_host_for_cfg', return_value=''), \
                 mock.patch.object(cli, 'is_interactive_stdin', return_value=False), \
                 redirect_stdout(output):
                result = cli.main(['--one-line', '--client-name', 'escare'])
            self.assertEqual(result, 0)
            lines = output.getvalue().splitlines()
            commands = [x for x in lines if x.startswith('bash -c ')]
            self.assertEqual(len(commands), 1)
            self.assertLessEqual(len(commands[0]), 900)
            self.assertIn('/i/', commands[0])
            self.assertNotIn('zt1.', commands[0])

    def test_private_ca_real_https_ip_command_pins_before_stage_execution(self):
        # Real local TLS, real curl/openssl, simulated sudo only. A typical
        # Python HTTPS listener omits close_notify on close. The unauthenticated
        # public CA read must not fail merely on TLS shutdown; the strict
        # verified handle request and SHA pin must remain mandatory.
        import frp_pki
        with tempfile.TemporaryDirectory(prefix='drlink-ip-real-tls-') as td:
            root = Path(td)
            pki = frp_pki.ensure_pki(root / 'pki', '127.0.0.1')
            marker = root / 'executed'
            paths = []
            handle = HANDLE

            class TestEndpoint(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    return

                def do_GET(self):
                    paths.append(self.path)
                    if self.path == '/ca.crt':
                        data = Path(pki['ca_crt']).read_bytes()
                    elif self.path == '/i/' + handle:
                        data = ('#!/bin/sh\nprintf PASS > ' + str(marker) + '\n').encode()
                    else:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

            endpoint = HTTPServer(('127.0.0.1', 0), TestEndpoint)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(pki['server_crt'], pki['server_key'])
            endpoint.socket = ctx.wrap_socket(endpoint.socket, server_side=True)
            thread = threading.Thread(target=endpoint.serve_forever, daemon=True)
            thread.start()
            stub = root / 'sudo'
            stub.write_text('#!/bin/sh\nexec "$@"\n')
            stub.chmod(0o755)
            env = dict(os.environ, PATH=td + os.pathsep + os.environ['PATH'])
            origin = 'https://127.0.0.1:%s/enroll' % endpoint.server_port
            try:
                for name, pin, should_execute in (
                    ('good', pki['fingerprint'], True),
                    ('wrong-pin', '0' * 64, False),
                ):
                    with self.subTest(name=name):
                        marker.unlink(missing_ok=True)
                        paths.clear()
                        cmd = zt.private_ca_ip_linux_command(origin, pin, handle)
                        result = subprocess.run(['bash', '-c', cmd], capture_output=True,
                                                text=True, env=env, timeout=12)
                        self.assertEqual(marker.exists(), should_execute, result.stderr)
                        self.assertEqual(result.returncode, 0 if should_execute else 1)
                        self.assertIn('/ca.crt', paths)
                        self.assertEqual('/i/' + handle in paths, should_execute)
            finally:
                endpoint.shutdown()
                endpoint.server_close()
                thread.join(timeout=3)

    def test_private_ca_windows_does_not_send_handle_before_ca_pin(self):
        fp, digest = 'a' * 64, 'b' * 64
        command = zt.private_ca_ip_windows_command(
            'https://192.0.2.20:6099/enroll', fp, digest, HANDLE
        )
        self.assertLessEqual(len(command), 1500)
        self.assertIn('--insecure -o $ca', command)  # public cert only
        self.assertIn('--cacert $ca -o $st', command)  # credential protected
        self.assertEqual(command.count('--insecure'), 1)
        self.assertLess(command.index("CA fingerprint mismatch"), command.index('/i/'))
        self.assertLess(command.index('--cacert'), command.index('Get-FileHash'))
        self.assertLess(command.index('Get-FileHash'), command.index('& powershell.exe'))
        self.assertIn('stage-1 hash mismatch', command)
        self.assertIn('WriteAllText', command)  # only one normalized public CA
        self.assertIn('--max-redirs 0', command)  # no credential redirects
        self.assertIn('finally{Remove-Item', command)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell parser unavailable')
    def test_private_ca_windows_stage_never_executes_before_both_pins(self):
        import frp_pki
        with tempfile.TemporaryDirectory(prefix='drlink-pwsh-ip-') as td:
            root = Path(td)
            ca_data = frp_pki.ensure_pki(root / 'pki', '192.0.2.20')
            ca = Path(ca_data['ca_crt'])
            stage = root / 'stage.ps1'
            stage.write_text('Write-Output verified-stage\n')
            digest = hashlib.sha256(stage.read_bytes()).hexdigest()
            (root / 'curl.exe').write_text(
                '#!/bin/sh\n'
                'dest=;kind=\n'
                'for a in "$@"; do\n'
                ' case "$a" in /ca.crt|*/ca.crt) kind=ca;; *"/i/"*) kind=stage;; esac\n'
                'done\n'
                'while [ "$#" -gt 0 ];do if [ "$1" = -o ];then shift;dest="$1";fi;shift;done\n'
                '[ -n "$dest" ] || exit 11\n'
                'if [ "$kind" = ca ];then cp "$CASE_ROOT/pki/ca.crt" "$dest";exit 0;fi\n'
                'if [ "$kind" = stage ];then cp "$CASE_ROOT/stage.ps1" "$dest";exit 0;fi\n'
                'exit 12\n'
            )
            (root / 'powershell.exe').write_text(
                '#!/bin/sh\n: > "$CASE_ROOT/stage-executed"\nexit 0\n'
            )
            for tool in ('curl.exe', 'powershell.exe'):
                (root / tool).chmod(0o755)
            env = dict(os.environ, TEMP=td, CASE_ROOT=td,
                       PATH=td + os.pathsep + os.environ['PATH'])
            for label, ca_pin, stage_pin, should_run in (
                ('ok', ca_data['fingerprint'], digest, True),
                ('bad-ca', '0' * 64, digest, False),
                ('bad-stage', ca_data['fingerprint'], '0' * 64, False),
            ):
                with self.subTest(label=label):
                    marker = root / 'stage-executed'
                    marker.unlink(missing_ok=True)
                    command = zt.private_ca_ip_windows_command(
                        'https://192.0.2.20:6099/enroll', ca_pin, stage_pin, HANDLE
                    )
                    result = subprocess.run(
                        ['pwsh', '-NoProfile', '-NonInteractive', '-Command', command],
                        env=env, capture_output=True, text=True, timeout=18,
                    )
                    self.assertEqual(marker.exists(), should_run, result.stderr[-250:])
                    if should_run:
                        self.assertEqual(result.returncode, 0, result.stderr[-250:])
                    else:
                        self.assertNotEqual(result.returncode, 0)

    def test_ip_bootstrap_rejects_dns_and_invalid_url_authority(self):
        for u in (
            "https://example.test/enroll", "http://192.0.2.20/enroll",
            "https://user:pass@192.0.2.20/enroll", "https://192.0.2.20:99999/enroll",
            "https://192.0.2.20/enroll?token=leak",
        ):
            with self.subTest(url=u):
                self.assertIsNone(zt.private_ca_ip_endpoint(u))
        self.assertEqual(
            zt.private_ca_ip_endpoint("https://[2001:db8::1]:6099/enroll"),
            ("[2001:db8::1]:6099", "[2001:db8::1]", 6099),
        )

    def test_missing_compact_bootstrap_fails_before_guided_confirmation(self):
        # Previously the operator entered every service and confirmed Y,
        # only then discovering the HTTPS prerequisite was absent.
        with tempfile.TemporaryDirectory() as root:
            tmp = Path(root)
            config = {
                "enrollments_dir": str(tmp / "enrollments"),
                "allocator_public_url": "https://192.0.2.20:6099/enroll",
                "tls_ca_cert": str(tmp / "ca.crt"),
                "client_installer_url": "https://example.test/installer.sh",
            }
            (tmp / "config.json").write_text(json.dumps(config))
            (tmp / "ca.crt").write_text("test-public-ca")
            with mock.patch.object(cli, "CONFIG", str(tmp / "config.json")), \
                 mock.patch.object(cli, "require_onboarding_config"), \
                 mock.patch.object(cli, "fingerprint_from_cert", return_value="a" * 64), \
                 mock.patch.object(cli, "short_url_host_for_cfg", return_value=""), \
                 mock.patch.object(cli, "resolve_configured_installer_url", return_value="https://example.test/installer.sh"), \
                 mock.patch.object(cli, "is_interactive_stdin", return_value=True), \
                 mock.patch.object(cli, "read_prompt", side_effect=AssertionError("unexpected prompt")):
                with self.assertRaises(SystemExit) as caught:
                    cli.main(["--one-line", "--client-name", "escare"])
                self.assertNotEqual(caught.exception.code, 0)
                self.assertEqual(list((tmp / "enrollments").iterdir()), [])

    def test_linux_missing_compact_renderer_does_not_fall_back_to_long_command(self):
        import io
        import contextlib

        output = io.StringIO()
        with mock.patch.object(cli, "_zt", return_value=None):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit):
                    cli.print_one_line(
                        TICKET, 600, "", HOST, 7000, "https://server.example",
                        "c" * 64, "https://example.test/artifacts/agent/bootstrap-client.sh",
                        "", 22, cfg={"bootstrap_hostname": HOST},
                        short_handle=HANDLE, require_compact=True,
                    )
        self.assertNotIn("FRP_BOOTSTRAP_TICKET=", output.getvalue())
        self.assertNotIn("zt1.", output.getvalue())
        self.assertNotIn("Zero-touch Agent command", output.getvalue())

    def test_windows_missing_hash_does_not_fall_back_to_long_command(self):
        import io
        import contextlib

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit):
                cli.print_one_line_windows(
                    TICKET, 600, "", HOST, 7000, "https://server.example",
                    "c" * 64, "https://example.test/artifacts/agent/bootstrap-client.ps1",
                    cfg={"bootstrap_hostname": HOST}, short_handle=HANDLE,
                    stage1_sha256="", require_compact=True,
                )
        self.assertNotIn("FRP_BOOTSTRAP_TICKET=", output.getvalue())
        self.assertNotIn("Zero-touch Agent command", output.getvalue())

    def test_long_private_ca_is_explicit_advanced_opt_in(self):
        self.assertFalse(cli.parse_args(["--one-line"]).long_bootstrap)
        self.assertTrue(
            cli.parse_args(["--one-line", "--long-bootstrap"]).long_bootstrap
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
