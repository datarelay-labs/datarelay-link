#!/usr/bin/env python3
"""Windows Zero-Touch one-liner must pin the allocator CA, then use it."""
from __future__ import annotations

import re
import os
import ssl
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_zero_touch as zt


class WindowsPinnedCaCommandTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('pwsh'), 'isolated PowerShell interpreter unavailable')
    def test_qualified_metadata_precedes_legacy_installer_execution(self):
        origin = 'https://owned.test'
        installer = origin + '/artifacts/agent/bootstrap-client.ps1'
        snippet = zt._qualified_windows_shell(installer, origin + '/enroll', '$g', '$w')
        manifest = dict(qualification_status='PASS', channel='development', source_head='b'*40,
                        artifacts=[dict(relative_path='agent/bootstrap-client.ps1', source_head='b'*40, sha256='a'*64)])
        setup = ('$ErrorActionPreference="Stop";$g="%s";$w="%s";'
                 '$script:fixtureManifest=%s;$wc=[pscustomobject]@{};'
                 '$wc|Add-Member -MemberType ScriptMethod -Name DownloadString '
                 '-Value {param($url) return $script:fixtureManifest};') % (
                     'a'*64, 'a'*64, zt.powershell_quote(json.dumps(manifest)))
        good = subprocess.run(['pwsh', '-NoProfile', '-Command', setup + snippet +
                               'if($env:FRP_EXPECTED_SOURCE_HEAD -cne "%s"){throw "wrong identity"};'
                               'Write-Output SENTINEL_EXECUTED;' % ('b'*40)], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn('SENTINEL_EXECUTED', good.stdout)
        bad = subprocess.run(['pwsh', '-NoProfile', '-Command', setup + '$g="%s";' % ('c'*64) +
                              snippet + 'Write-Output SENTINEL_EXECUTED;'], capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertNotIn('SENTINEL_EXECUTED', bad.stdout)
        for name, value in (('FRP_EXPECTED_SOURCE_HEAD', 'c'*40), ('FRP_EXPECTED_RELEASE_CHANNEL', 'stable')):
            mismatched = subprocess.run(['pwsh', '-NoProfile', '-Command', setup +
                '$env:%s=%s;' % (name, zt.powershell_quote(value)) + snippet +
                'Write-Output SENTINEL_EXECUTED;'], capture_output=True, text=True)
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertNotIn('SENTINEL_EXECUTED', mismatched.stdout)
        for rendered in (zt.render_short_url_windows_bootstrap_script(origin + '/enroll', 'a'*64, 'A'*22, installer),):
            self.assertLess(rendered.index('qualified Windows bootstrap provenance mismatch'), rendered.index('& powershell.exe'))




    def test_short_stage1_pins_private_allocator_before_download(self):
        allocator = "https://203.0.113.10:6099/enroll"
        script = zt.render_short_url_windows_bootstrap_script(
            allocator,
            "ab" * 32,
            "bt1." + ("b" * 16) + "." + ("c" * 64),
            "https://203.0.113.10:6099/artifacts/agent/bootstrap-client.ps1",
        )
        self.assertIn("https://203.0.113.10:6099/ca.crt", script)
        self.assertIn("CA fingerprint mismatch", script)
        self.assertIn("ServerCertificateValidationCallback", script)
        self.assertEqual(script.count("--insecure"), 1)
        self.assertLess(
            script.index("ServerCertificateValidationCallback"),
            script.index("DownloadFile"),
        )
        self.assertIn("AllowUnknownCertificateAuthority", script)
        self.assertIn("203.0.113.10", script)

        public_script = zt.render_short_url_windows_bootstrap_script(
            allocator,
            "ab" * 32,
            "bt1." + ("d" * 16) + "." + ("e" * 64),
            "https://downloads.example.test/bootstrap-client.ps1",
        )
        self.assertNotIn("--insecure", public_script)
        self.assertNotIn("ServerCertificateValidationCallback", public_script)

    @unittest.skipUnless(shutil.which('pwsh') and shutil.which('openssl'),
                         'isolated PowerShell and OpenSSL are required')
    def test_pinned_private_ca_rejects_hostname_mismatch_without_losing_ca_trust(self):
        """Execute the actual generated TLS callback against a valid wrong-SAN leaf."""
        with tempfile.TemporaryDirectory(prefix='drlink-zt-hostname-') as tmp:
            d = Path(tmp)
            def openssl(*args):
                proc = subprocess.run(['openssl', *map(str,args)], cwd=d,
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
            openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                    '-subj','/CN=DRLink Audit CA','-addext',
                    'basicConstraints=critical,CA:TRUE','-addext',
                    'keyUsage=critical,keyCertSign,cRLSign',
                    '-keyout','ca.key','-out','ca.crt')
            openssl('req','-newkey','rsa:2048','-nodes',
                    '-subj','/CN=wrong.example.test',
                    '-keyout','leaf.key','-out','leaf.csr')
            (d/'leaf.ext').write_text('subjectAltName=DNS:wrong.example.test\n'
                    'extendedKeyUsage=serverAuth\n'
                    'basicConstraints=critical,CA:FALSE\n')
            openssl('x509','-req','-in','leaf.csr','-CA','ca.crt',
                    '-CAkey','ca.key','-CAcreateserial','-out','leaf.crt',
                    '-days','1','-extfile','leaf.ext')
            script = zt.render_short_url_windows_bootstrap_script(
                'https://127.0.0.1/enroll', 'a'*64,
                'bt1.'+'b'*16+'.'+'c'*64,
                'https://127.0.0.1/artifacts/agent/bootstrap-client.ps1')
            start = script.index('  [Net.ServicePointManager]::ServerCertificateValidationCallback = {')
            end = script.index('  $wc = New-Object Net.WebClient',start)
            callback = script[start:end]
            test = ("$ErrorActionPreference='Stop'\n"
                "$script:drlinkCaCert = New-Object Security.Cryptography.X509Certificates.X509Certificate2('%s')\n"
                "$script:drlinkCaThumb = $script:drlinkCaCert.Thumbprint\n"
                "$script:drlinkPinHost = '127.0.0.1'\n%s\n"
                "$leaf = New-Object Security.Cryptography.X509Certificates.X509Certificate2('%s')\n"
                "$sender = [pscustomobject]@{RequestUri=[uri]'https://127.0.0.1/artifacts/agent/bootstrap-client.ps1'}\n"
                "foreach($case in @(@('name_mismatch',2,$false),@('cert_missing',1,$false),"
                "@('name_and_chain',6,$false),@('only_private_ca_chain',4,$true))){\n"
                " $chain=New-Object Security.Cryptography.X509Certificates.X509Chain;"
                " $result=[bool][Net.ServicePointManager]::ServerCertificateValidationCallback.Invoke($sender,$leaf,$chain,[Net.Security.SslPolicyErrors]$case[1]);"
                " if($result -ne $case[2]){throw ('TLS_CASE_FAIL '+$case[0]+' '+$result)};"
                " Write-Output ('TLS_CASE_PASS '+$case[0]);"
                "}\n") % (str(d/'ca.crt'),callback,str(d/'leaf.crt'))
            (d/'test.ps1').write_text(test)
            proc = subprocess.run(['pwsh','-NoProfile','-File',str(d/'test.ps1')],
                     capture_output=True,text=True,timeout=25)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            for case in ('name_mismatch','cert_missing','name_and_chain','only_private_ca_chain'):
                self.assertIn('TLS_CASE_PASS '+case,proc.stdout)

    def test_rendered_entry_private_tls(self):
        """Real HTTPS and generated Stage-1; downloaded installer is inert."""
        requested = os.environ.get('DRLINK_STAGE_TEST_POWERSHELL')
        parent = shutil.which(requested or 'pwsh')
        if requested:
            self.assertIsNotNone(parent, 'requested native PowerShell unavailable')
        elif not parent or (os.name != 'nt' and not shutil.which('openssl')):
            self.skipTest('PowerShell and fixture PKI tools unavailable')
        with tempfile.TemporaryDirectory(prefix='drlink-entry-tls-') as tmp:
            root = Path(tmp)
            if os.name == 'nt':
                for name in ('good', 'other'):
                    subprocess.run([sys.executable, str(ROOT/'tests/windows/gen_frp_smoke_certs.py'),
                                    '--out-dir', str(root/name)], check=True, timeout=30)
                cert = root/'good/leaf.pem'
                key = root/'good/leaf.key'
                ca = (root/'good/ca.pem').read_text()
                fp = hashlib.sha256((root/'good/ca.crt').read_bytes()).hexdigest()
                wrong_ca = (root/'other/ca.pem').read_text()
                wrong_fp = hashlib.sha256((root/'other/ca.crt').read_bytes()).hexdigest()
            else:
                import frp_pki
                pki = frp_pki.ensure_pki(root/'good', '127.0.0.1')
                other = frp_pki.ensure_pki(root/'other', '127.0.0.1')
                cert, key = pki['server_crt'], pki['server_key']
                ca, fp = Path(pki['ca_crt']).read_text(), pki['fingerprint']
                wrong_ca, wrong_fp = Path(other['ca_crt']).read_text(), other['fingerprint']
            env = dict(os.environ, TEMP=tmp)
            if os.name != 'nt':
                launcher = root/'powershell.exe'
                launcher.write_text('#!/bin/sh\nexec '+__import__('shlex').quote(parent)+' "$@"\n')
                launcher.chmod(0o755)
                env['PATH'] = tmp + os.pathsep + env['PATH']
            env['FRP_WINDOWS_ROOT'] = str(root/'agent-root')
            # Do not execute a real product installer or alter OS trust.
            installer = (
                "param([switch]$ZeroTouch)\n"
                "if (-not $ZeroTouch -or $env:FRP_BOOTSTRAP_LOCATOR -ne 'A3xK9mP2' "
                "-or -not (Test-Path -LiteralPath $env:FRP_ALLOCATOR_CA_FILE)) { exit 19 }\n"
                "if ($env:OS -eq 'Windows_NT') { Get-Acl -LiteralPath $env:TEMP -ErrorAction Stop | Out-Null }\n"
                "$tools = Join-Path $env:FRP_WINDOWS_ROOT 'tools'\n"
                "$state = Join-Path $env:FRP_WINDOWS_ROOT 'state'\n"
                "New-Item -ItemType Directory -Force -Path $tools,$state | Out-Null\n"
                "Set-Content -LiteralPath (Join-Path $tools 'drlink.cmd') -Value '@rem DRLINK-PRODUCT-SHIM'\n"
                "Set-Content -LiteralPath (Join-Path $state 'path-shim.json') -Value '{}'\n"
                "Write-Output 'INERT_INSTALLER_EXECUTED'\n"
            ).encode('ascii')
            state = {'mode': 'good'}
            paths = []
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass
                def do_GET(self):
                    paths.append(self.path)
                    if self.path == '/fixture/SHA256SUMS':
                        body = (hashlib.sha256(installer).hexdigest() + '  bootstrap-client.ps1\n').encode()
                    elif self.path == '/fixture/bootstrap-client.ps1':
                        body = installer if state['mode'] != 'tampered' else b"Write-Output 'TAMPERED_EXECUTED'\n"
                        if state['mode'] == 'redirect':
                            self.send_response(302)
                            self.send_header('Location', 'http://127.0.0.1:1/forbidden')
                            self.end_headers()
                            return
                    else:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, key)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                origin = 'https://127.0.0.1:%d' % server.server_port
                wrapper = root/'run-stage.ps1'
                wrapper.write_text(
                    "$ErrorActionPreference='Stop'\n"
                    "$env:FRP_ZERO_TOUCH='audit-original'\n"
                    "$env:FRP_BOOTSTRAP_LOCATOR='audit-previous'\n"
                    "$modulePath=$env:PSModulePath\n"
                    "$protocol=[Net.ServicePointManager]::SecurityProtocol\n"
                    "$beforePath=$env:Path\n"
                    "$failed=$false\n"
                    "try { Invoke-Expression (Get-Content -LiteralPath $env:TEST_STAGE -Raw) } "
                    "catch { $failed=$true; Write-Output ('STAGE_FAILURE='+$_.Exception.Message) }\n"
                    "if ($env:FRP_ZERO_TOUCH -ne 'audit-original' -or "
                    "$env:FRP_BOOTSTRAP_LOCATOR -ne 'audit-previous' -or "
                    "$env:PSModulePath -cne $modulePath -or "
                    "[Net.ServicePointManager]::SecurityProtocol -ne $protocol) { throw 'parent state changed' }\n"
                    "$expectedPath=$beforePath; if (-not $failed) { $expectedPath = (@($beforePath,(Join-Path $env:FRP_WINDOWS_ROOT 'tools')) | Where-Object { $_ }) -join ';' }\n"
                    "if ($env:Path -cne $expectedPath) { throw 'caller PATH refresh mismatch' }\n"
                    "Write-Output 'PARENT_STATE_RESTORED'\n"
                    "if ($failed) { exit 17 }; exit 0\n",
                    encoding='ascii')
                for name, pem, digest, mode, expected in (
                    ('valid', ca, fp, 'good', 0),
                    ('wrong_ca', wrong_ca, wrong_fp, 'good', 17),
                    ('tampered', ca, fp, 'tampered', 17),
                    ('insecure_redirect', ca, fp, 'redirect', 17),
                ):
                    with self.subTest(case=name):
                        state['mode'] = mode
                        paths.clear()
                        stage = root/'entry.ps1'
                        stage.write_text(zt.render_short_url_windows_bootstrap_script(
                            origin+'/enroll', digest, None, origin+'/fixture/bootstrap-client.ps1',
                            entry_locator='A3xK9mP2', ca_pem=pem), encoding='ascii')
                        proc = subprocess.run([parent, '-NoProfile', '-NonInteractive',
                            '-ExecutionPolicy', 'Bypass', '-File', str(wrapper)],
                            env=dict(env, TEST_STAGE=str(stage)), capture_output=True,
                            text=True, timeout=60)
                        self.assertEqual(proc.returncode, expected, proc.stdout+proc.stderr)
                        self.assertIn('PARENT_STATE_RESTORED', proc.stdout)
                        self.assertEqual('INERT_INSTALLER_EXECUTED' in proc.stdout, expected == 0,
                                         proc.stdout+proc.stderr)
                        self.assertNotIn('TAMPERED_EXECUTED', proc.stdout)
                        if name == 'wrong_ca':
                            self.assertEqual(paths, [], 'untrusted peer received HTTP request')
                        else:
                            self.assertEqual(paths, ['/fixture/SHA256SUMS', '/fixture/bootstrap-client.ps1'])
                        self.assertEqual(list(root.glob('frp-bs-*')), [], 'temporary artifacts remain')
                        print('ENTRY_WINDOWS_REAL_TLS_'+name.upper()+'=PASS')
            finally:
                server.shutdown()
                worker.join(timeout=5)
                server.server_close()

    def test_current_shell_path_refresh(self):
        parent = shutil.which(os.environ.get('DRLINK_STAGE_TEST_POWERSHELL') or 'pwsh')
        if not parent:
            self.skipTest('PowerShell unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'tools').mkdir()
            (root/'state').mkdir()
            (root/'tools/drlink.cmd').write_text('@rem DRLINK-PRODUCT-SHIM')
            (root/'state/path-shim.json').write_text('{}')
            # In an isolated shell retain the pre-existing PATH entries.
            # Invoke the very snippet included in the real bootstrap.
            snippet = zt.windows_current_path_refresh()
            script = "$ErrorActionPreference='Stop'\n$env:Path='preserve-first;preserve-second'\n"
            script += snippet + '\n' + snippet + '\n'
            script += """if ($env:Path -cne ('preserve-first;preserve-second;' + (Join-Path $env:FRP_WINDOWS_ROOT 'tools'))) { throw ('bad PATH: '+$env:Path) }
Write-Output PATH_REFRESH_IDEMPOTENT=PASS
"""
            proc = subprocess.run([parent,'-NoProfile','-Command',script],
                env=dict(os.environ, FRP_WINDOWS_ROOT=tmp), capture_output=True,
                text=True, timeout=30)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            self.assertIn('PATH_REFRESH_IDEMPOTENT=PASS',proc.stdout)

    def test_current_entry_and_downstream_hash_before_execute(self):
        command=zt.render_entry_command("remote.xdr.ooo","A3xK9mP2","windows")
        self.assertEqual(command,"iex(curl.exe -kfsS https://remote.xdr.ooo/A3xK9mP2|Out-String)")
        stage=zt.render_short_url_windows_bootstrap_script(
            "https://192.0.2.20/enroll","ab"*32,None,
            "https://192.0.2.20/artifacts/agent/bootstrap-client.ps1",
            entry_locator="A3xK9mP2",ca_pem="fixture certificate")
        self.assertLess(stage.index("CA fingerprint mismatch"),stage.index("DownloadFile"))
        self.assertLess(stage.index("Get-FileHash"),stage.index("-File $installer"))
        self.assertNotIn("--insecure",stage)
        self.assertNotIn("bt1.",stage)


if __name__ == "__main__":
    unittest.main()
