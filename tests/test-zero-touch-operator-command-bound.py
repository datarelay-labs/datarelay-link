#!/usr/bin/env python3
"""Zero-Touch operator command bound for Linux, macOS, and Windows.

These fixtures contain fake credentials and do not create enrollment tickets.
"""
from __future__ import annotations
import importlib.machinery
import sys
import unittest
from pathlib import Path
from unittest import mock

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
