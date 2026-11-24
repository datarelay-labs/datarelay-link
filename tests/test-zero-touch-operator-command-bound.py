#!/usr/bin/env python3
"""Zero-Touch operator command bound for Linux, macOS, and Windows.

These fixtures contain fake credentials and do not create enrollment tickets.
"""
from __future__ import annotations
import importlib.machinery
import importlib.util
import hashlib
import base64
import re
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

_loader = importlib.machinery.SourceFileLoader(
    "frp_create_client_compact_contract", str(ROOT / "tools/frp-create-client")
)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
cli = importlib.util.module_from_spec(_spec)
sys.modules[_loader.name] = cli
_loader.exec_module(cli)
HOST = "remote.xdr.ooo"
TICKET = "bt1." + ("a" * 16) + "." + ("b" * 64)
HANDLE = "x" * 22
HASH = "c" * 64


class CompactZeroTouchContract(unittest.TestCase):
    def assert_short_only(self, command, *, windows=False, authority=HOST,
                          ca=None, stage=None):
        """Target fields only: fixed OS invocation, HTTPS authority, locator.

        ca/stage are inputs to the existing renderer fixtures, never allowed
        customer command fields. A failure is a runtime migration finding.
        """
        url = re.escape("https://" + authority + "/") + r"[A-Za-z0-9_-]{6}"
        if windows:
            pattern = r"iex\(curl\.exe -kfsS " + url + r"\|Out-String\)"
        else:
            pattern = r"curl -kfsS " + url + r"\|sudo bash"
        self.assertIsNotNone(re.fullmatch(pattern, command),
                             "command does not match the required entry fields")

    def test_short_only_template_rejects_extra_information(self):
        for authority in (HOST, "192.0.2.20:6099"):
            for windows in (False, True):
                url = "https://" + authority + "/A3xK9m"
                cmd = ("iex(curl.exe -kfsS " + url + "|Out-String)" if windows else
                       "curl -kfsS " + url + "|sudo bash")
                self.assert_short_only(cmd, windows=windows, authority=authority)
                for extra in (" --enrollment-id 123", " --name agent",
                              " --installer-url https://example.test/a", " --sha256 " + HASH,
                              " --platform linux", "; echo ok", "?port=22", " " + HANDLE):
                    with self.subTest(extra=extra), self.assertRaises(AssertionError):
                        self.assert_short_only(cmd + extra, windows=windows, authority=authority)
                for bad in ("A3xK9", "A3xK9mm", "i/A3xK9m", "A3xK9?", HANDLE):
                    with self.subTest(locator=bad), self.assertRaises(AssertionError):
                        self.assert_short_only(cmd.replace("A3xK9m", bad), windows=windows,
                                               authority=authority)



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
        self.assertIn("Get-FileHash", line)
        self.assertIn(HASH, line)
        self.assertIn("powershell.exe -NoProfile", line)
        self.assertNotIn(" -k", line)
        self.assertNotIn("--insecure", line)







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
        self.assertIn('--insecure -o $ca', command)  # public cert only
        self.assertIn('--cacert $ca --ssl-revoke-best-effort -o $st', command)  # credential protected
        self.assertEqual(command.count('--insecure'), 1)
        self.assertLess(command.index("CA fingerprint mismatch"), command.index('/i/'))
        self.assertLess(command.index('--cacert'), command.index('Get-FileHash'))
        self.assertLess(command.index('Get-FileHash'), command.index('& powershell.exe'))
        self.assertIn('stage-1 hash mismatch', command)
        self.assertIn('WriteAllText', command)  # only one normalized public CA
        self.assertIn('--max-redirs 0', command)  # no credential redirects
        self.assertIn('finally{Remove-Item', command)

    def test_private_ca_windows_stage1_tolerates_unreachable_revocation_endpoint(self):
        # BUG-05: Schannel cannot reach CRL/OCSP for the private pinned CA, so
        # curl.exe exits 60 (CERT_TRUST_REVOCATION_STATUS_UNKNOWN). Only the
        # pinned --cacert stage-1 fetch may use best-effort revocation; global
        # --ssl-no-revoke and any widening of the --insecure CA fetch are
        # forbidden, and every other verification step must remain.
        command = zt.private_ca_ip_windows_command(
            'https://192.0.2.20:6099/enroll', 'a' * 64, 'b' * 64, HANDLE
        )
        self.assertEqual(command.count('--ssl-revoke-best-effort'), 1)
        self.assertNotIn('--ssl-no-revoke', command)
        self.assertEqual(command.count('--insecure'), 1)
        self.assertLess(command.index('--insecure -o $ca'), command.index('--ssl-revoke-best-effort'))
        self.assertLess(command.index('--cacert $ca'), command.index('--ssl-revoke-best-effort'))
        self.assertLess(command.index('--ssl-revoke-best-effort'), command.index('-o $st'))
        self.assertIn("--proto '=https'", command)
        self.assertLess(command.index('CA fingerprint mismatch'), command.index('--ssl-revoke-best-effort'))
        self.assertLess(command.index('--ssl-revoke-best-effort'), command.index('stage-1 hash mismatch'))

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





    def test_all_platforms_and_authorities_use_exact_public_issuer(self):
        for authority in (HOST, "192.0.2.20:6099", "private.example:8443"):
            for platform in ("linux", "macos", "windows"):
                with self.subTest(authority=authority, platform=platform):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        cli.print_entry_command(authority, "A3xK9m", platform, 600, "a"*16)
                    commands = [line for line in output.getvalue().splitlines()
                                if line.startswith(("curl ", "iex("))]
                    self.assertEqual(len(commands), 1)
                    self.assert_short_only(commands[0], windows=platform=="windows", authority=authority)
                    self.assertNotIn("bt1.", output.getvalue())
                    self.assertNotIn("/i/", output.getvalue())
                    self.assertIn("set enrollment approve", output.getvalue())
                    self.assertEqual(cli.parse_args(["--one-line","--platform",platform]).platform, platform)

    def test_missing_renderer_or_invalid_locator_does_not_emit_fallback(self):
        for platform in ("linux","macos","windows"):
            for locator in ("a"*22, "bad/path", ""):
                out = io.StringIO()
                with self.subTest(platform=platform, locator=locator), redirect_stdout(out), self.assertRaises(SystemExit):
                    cli.print_entry_command(HOST, locator, platform, 600, "a"*16)
                self.assertNotIn("Zero-touch Agent command", out.getvalue())
            with mock.patch.object(cli, "_zt", return_value=None), self.assertRaises(SystemExit):
                cli.print_entry_command(HOST, "A3xK9m", platform, 600, "a"*16)

    def test_new_stage_download_integrity_and_separate_credentials(self):
        ca = "fixture certificate"
        origin = "https://192.0.2.20:6099"
        for platform in ("linux","macos","windows"):
            if platform == "windows":
                script = zt.render_short_url_windows_bootstrap_script(origin+"/enroll", HASH, None,
                    origin+"/fixture/bootstrap-client.ps1", entry_locator="A3xK9m", ca_pem=ca)
                self.assertLess(script.index("CA fingerprint mismatch"),script.index(".DownloadFile"))
                self.assertLess(script.index("Get-FileHash"),script.index("-File $installer"))
            else:
                script = zt.render_short_url_bootstrap_script(origin+"/enroll", HASH, None,
                    origin+"/fixture/bootstrap-client.sh", entry_locator="A3xK9m", ca_pem=ca)
                self.assertLess(script.index("CA fingerprint mismatch"),script.index("curl -fsSL"))
                self.assertLess(script.index("installer SHA256 mismatch"),script.index('bash "$INSTALLER_FILE"'))
            self.assertIn("FRP_BOOTSTRAP_LOCATOR",script)
            self.assertNotIn("bt1.",script)
            self.assertNotIn(HANDLE,script)
            self.assertNotIn("--insecure",script)

    def test_legacy_zero_touch_code_cannot_be_reintroduced(self):
        """No alternate long creator, decoder or bootstrap argv compatibility."""
        forbidden_by_source = {
            "tools/frp-create-client": (
                "--long-bootstrap", "legacy_env", "encode_zero_touch_package",
                "decode_zero_touch_package", "pinned_ca_linux_command",
                "pinned_ca_windows_command",
            ),
            "tools/frp-enroll-bulk": (
                "encode_zero_touch_package", "pinned_ca_linux_command",
                "pinned_ca_manual_linux_command",
            ),
            "lib/frp_zero_touch.py": (
                "def encode_zero_touch_package(", "def decode_zero_touch_package(",
                "def pinned_ca_linux_command(", "def pinned_ca_windows_command(",
                "def pinned_ca_windows_inner(", "def short_url_windows_command(",
            ),
            "install-client.sh": ("zt1.*)", "frp_zero_touch_apply_package"),
            "lib/frp-client-common.sh": ("frp_zero_touch_apply_package() {",),
        }
        for path, markers in forbidden_by_source.items():
            contents = (ROOT / path).read_text(encoding="utf-8")
            for marker in markers:
                with self.subTest(file=path, obsolete=marker):
                    self.assertNotIn(marker, contents)
        for path in ("docs/CLI_REFERENCE.md", "docs/ZERO_TOUCH_SHORT_URL.md",
                     "docs/ZERO_TOUCH_REGRESSION_CONTROL.md", "docs/PRODUCT_MASTER.md"):
            with self.subTest(doc=path):
                self.assertNotIn("--long-bootstrap", (ROOT / path).read_text())

    def test_removed_legacy_long_bootstrap_option_is_rejected(self):
        self.assertFalse(hasattr(cli.parse_args(["--one-line"]), "long_bootstrap"))
        with self.assertRaises(SystemExit):
            cli.parse_args(["--one-line", "--long-bootstrap"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
