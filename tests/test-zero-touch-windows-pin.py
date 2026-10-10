#!/usr/bin/env python3
"""Windows Zero-Touch one-liner must pin the allocator CA, then use it."""
from __future__ import annotations

import re
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
        for rendered in (zt.pinned_ca_windows_inner(installer, origin + '/enroll', 'a'*64, 'A'*22, origin + '/artifacts/SHA256SUMS'),
                         zt.render_short_url_windows_bootstrap_script(origin + '/enroll', 'a'*64, 'A'*22, installer)):
            self.assertLess(rendered.index('qualified Windows bootstrap provenance mismatch'), rendered.index('& powershell.exe'))

    def test_post_pin_curl_uses_cacert_and_skips_schannel_revocation(self):
        inner = zt.pinned_ca_windows_inner(
            installer_url="https://203.0.113.10:6099/artifacts/agent/bootstrap-client.ps1",
            allocator_url="https://203.0.113.10:6099/enroll",
            ca_sha256="a" * 64,
            ticket="bt1." + ("b" * 16) + "." + ("c" * 64),
            sums_url="https://203.0.113.10:6099/artifacts/SHA256SUMS",
        )
        self.assertIn("--insecure -o $ca", inner)
        self.assertEqual(inner.count("--insecure"), 1)
        self.assertNotIn("--ssl-no-revoke", inner)
        self.assertNotIn("--cacert", inner)
        self.assertIn("CA fingerprint mismatch", inner)
        self.assertIn("ServerCertificateValidationCallback", inner)
        self.assertIn("AllowUnknownCertificateAuthority", inner)
        self.assertIn("203.0.113.10", inner)
        self.assertIn("SHA256SUMS download failed", inner)
        self.assertIn("bootstrap-client.ps1 download failed", inner)
        self.assertNotIn("fatedier", inner.lower())
        self.assertNotIn("raw.githubusercontent.com", inner)
        cmd = zt.pinned_ca_windows_command(
            installer_url="https://203.0.113.10:6099/artifacts/agent/bootstrap-client.ps1",
            allocator_url="https://203.0.113.10:6099/enroll",
            ca_sha256="a" * 64,
            ticket="bt1." + ("b" * 16) + "." + ("c" * 64),
            sums_url="https://203.0.113.10:6099/artifacts/SHA256SUMS",
        )
        self.assertTrue(cmd.startswith("powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand "))
        self.assertIsNone(re.search(r'(^|[^a-z0-9])(irm|iex)([^a-z0-9]|$)', cmd.lower()))
        import base64
        inner = base64.b64decode(cmd.split()[-1]).decode('utf-16le')
        self.assertIn('qualified Windows bootstrap provenance mismatch', inner)
        self.assertIn('agent/bootstrap-client.ps1', inner)
        self.assertIn('& powershell.exe -NoProfile -ExecutionPolicy Bypass -File', inner)
        self.assertLess(len(cmd), 32767)  # Windows command-line limit

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell parser unavailable')
    def test_encoded_launcher_survives_native_shell_parsing(self):
        import base64
        command = zt.pinned_ca_windows_command(
            installer_url='https://owned.test/artifacts/agent/bootstrap-client.ps1',
            allocator_url='https://owned.test/enroll',
            ca_sha256='a' * 64,
            ticket='bt1.' + 'b' * 16 + '.' + 'c' * 64,
            sums_url='https://owned.test/artifacts/SHA256SUMS',
        )
        inner = base64.b64decode(command.split()[-1]).decode('utf-16le')
        # Verify both the generated script AST and the actual argv decoding.
        parser = subprocess.run(
            ['pwsh', '-NoProfile', '-Command',
             '$s=[Console]::In.ReadToEnd();$t=$null;$e=$null;'
             '[void][System.Management.Automation.Language.Parser]::ParseInput($s,[ref]$t,[ref]$e);'
             'if($e.Count){$e|ForEach-Object {Write-Error $_.Message};exit 1};'
             'Write-Output PARSER_OK'],
            input=inner, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(parser.returncode, 0, parser.stderr)
        self.assertIn('PARSER_OK', parser.stdout)
        probe = zt.windows_encoded_command("Write-Output 'EXECUTION_OK'")
        result = subprocess.run(
            ['pwsh', '-NoProfile', '-EncodedCommand', probe.split()[-1]],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('EXECUTION_OK', result.stdout)

    def test_compact_windows_path_never_uses_irm_iex(self):
        compact = "A" * 22
        cmd = zt.short_url_windows_command("remote.xdr.ooo", compact)
        script = zt.render_short_url_windows_bootstrap_script(
            "https://203.0.113.10/enroll",
            "ab" * 32,
            compact,
            "https://example.test/artifacts/agent/bootstrap-client.ps1",
        )
        pinned = zt.pinned_ca_windows_command(
            "https://203.0.113.10:6099/artifacts/agent/bootstrap-client.ps1",
            "https://203.0.113.10:6099/enroll",
            "a" * 64,
            compact,
            "https://203.0.113.10:6099/artifacts/SHA256SUMS",
        )
        import base64
        decoded_pinned = base64.b64decode(pinned.split()[-1]).decode('utf-16le')
        for text in (cmd, script, decoded_pinned):
            lowered = text.lower()
            self.assertIsNone(re.search(r'(^|[^a-z0-9])(irm|iex)([^a-z0-9]|$)', lowered))
            self.assertNotIn("invoke-restmethod", lowered)
            self.assertNotIn("invoke-expression", lowered)
            self.assertIn("powershell.exe", lowered)
            self.assertIn("-file", lowered)
        self.assertIn("DownloadFile", cmd)
        self.assertIn("SHA256", script)
        self.assertIn("DownloadFile", script)
        self.assertIn(compact, cmd)
        linux = zt.short_url_command("remote.xdr.ooo", compact)
        self.assertIn("-fsSL", linux)
        self.assertIn("https://", linux)
        self.assertIn("/i/", linux)
        self.assertTrue(linux.endswith("|sudo bash"))

    def test_strict_launcher_is_420_and_hash_before_execute(self):
        digest = "ab" * 32
        command = zt.windows_strict_launcher("remote.xdr.ooo", "A" * 22, digest)
        self.assertEqual(len(command), 420)
        self.assertIn("curl.exe -fsSLo", command)
        self.assertIn("Get-FileHash", command)
        self.assertIn(digest, command)
        self.assertIn("powershell.exe -NoProfile -ExecutionPolicy Bypass -File", command)
        self.assertNotIn("-Command", command)
        self.assertNotIn("Invoke-Expression", command)
        self.assertIsNone(re.search(r'(^|[^a-z0-9])(irm|iex)([^a-z0-9]|$)', command.lower()))


if __name__ == "__main__":
    unittest.main()
