#!/usr/bin/env python3
"""Regression: a DNS-selected Private CA Server can issue pinned-IP compact Zero-Touch."""
import contextlib
import importlib.machinery
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import frp_pki

client = importlib.machinery.SourceFileLoader(
    "zt_privateca_domain_ip_test", str(ROOT / "tools/frp-create-client")
).load_module()


class PrivateCADomainIPFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="zt-domain-ip-")
        self.addCleanup(self.tmp.cleanup)
        pki = frp_pki.ensure_pki(
            Path(self.tmp.name) / "pki", "221.139.249.109",
            extra_hosts=["remote.isoc.ooo"],
        )
        self.ca = pki["fingerprint"]
        self.cfg = {
            "public_ip": "221.139.249.109",
            "public_hostname": "remote.isoc.ooo",
            "public_url_host": "remote.isoc.ooo",
            "deployment_mode": "single443",
            "allocator_public_url": "https://remote.isoc.ooo/enroll",
            "tls_ca_cert": pki["ca_crt"],
            "tls_server_cert": pki["server_crt"],
        }

    def plan(self):
        return client.private_ca_ip_bootstrap_plan(self.cfg, self.ca)

    def test_domain_private_ca_uses_ip_only_for_bootstrap(self):
        plan = self.plan()
        self.assertIsNotNone(plan)
        self.assertEqual(plan["authority"], "221.139.249.109")
        self.assertEqual(plan["allocator"], "https://221.139.249.109/enroll")
        self.assertEqual(self.cfg["allocator_public_url"], "https://remote.isoc.ooo/enroll")

    def test_preflight_selects_pinned_ip_when_public_tls_fails(self):
        installer = "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh"
        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""), \
             mock.patch.object(client, "preflight_installer_url", return_value=None):
            host, plan = client.validate_zero_touch_prerequisites(
                self.cfg, "linux", installer, self.ca
            )
        self.assertEqual(host, "")
        self.assertEqual(plan["allocator"], "https://221.139.249.109/enroll")

    def test_publicly_qualified_hostname_remains_preferred(self):
        installer = "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh"
        with mock.patch.object(client, "short_url_host_for_cfg", return_value="remote.isoc.ooo"), \
             mock.patch.object(client, "preflight_installer_url", return_value=None):
            host, plan = client.validate_zero_touch_prerequisites(
                self.cfg, "linux", installer, self.ca
            )
        self.assertEqual(host, "remote.isoc.ooo")
        self.assertIsNone(plan)

    def test_linux_renderer_uses_numeric_ip_with_pin_and_no_insecure(self):
        plan = self.plan()
        self.assertIsNotNone(plan)
        command = client.load_zero_touch().private_ca_ip_linux_command(
            plan["allocator"], self.ca, "A" * 22
        )
        self.assertIn("https://221.139.249.109/i/", command)
        self.assertIn(self.ca, command)
        self.assertNotIn("--insecure", command)
        self.assertLessEqual(len(command), 900)
        output = io.StringIO()
        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""), \
             contextlib.redirect_stdout(output):
            client.print_one_line(
                "bt1.example.secret", 3600, "", "221.139.249.109", 443,
                self.cfg["allocator_public_url"], self.ca,
                "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh",
                "", 22, client_name="test-agent", cfg=self.cfg,
                short_handle="A" * 22, private_ip_plan=plan, require_compact=True,
            )
        self.assertIn("https://221.139.249.109/i/", output.getvalue())
        self.assertNotIn("zt1.", output.getvalue())

    def test_windows_renderer_uses_numeric_ip_with_pin_and_digest(self):
        plan = self.plan()
        self.assertIsNotNone(plan)
        command = client.load_zero_touch().private_ca_ip_windows_command(
            plan["allocator"], self.ca, "a" * 64, "A" * 22
        )
        self.assertIn("https://221.139.249.109/i/", command)
        self.assertIn(self.ca, command)
        self.assertIn("a" * 64, command)
        self.assertLessEqual(len(command), 1500)
        output = io.StringIO()
        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""), \
             contextlib.redirect_stdout(output):
            client.print_one_line_windows(
                "bt1.example.secret", 3600, "", "221.139.249.109", 443,
                self.cfg["allocator_public_url"], self.ca,
                "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.ps1",
                client_name="test-agent", cfg=self.cfg, short_handle="A" * 22,
                stage1_sha256="a" * 64, private_ip_plan=plan, require_compact=True,
            )
        self.assertIn("https://221.139.249.109/i/", output.getvalue())
        self.assertNotIn("zt1.", output.getvalue())

    def test_untrusted_identity_or_missing_ip_san_fails_closed(self):
        base = dict(self.cfg)
        invalid_cases = (
            {"public_ip": "221.139.249.110"},
            {"public_ip": "0.0.0.0"},
            {"public_ip": ""},
            {"public_ip": "not-an-ip"},
            {"public_url_host": "other.isoc.ooo"},
            {"allocator_public_url": "https://other.isoc.ooo/enroll"},
            {"allocator_public_url": "http://remote.isoc.ooo/enroll"},
            {"allocator_public_url": "https://user:pass@remote.isoc.ooo/enroll"},
            {"allocator_public_url": "https://remote.isoc.ooo/enroll?secret=x"},
        )
        for changes in invalid_cases:
            with self.subTest(changes=changes):
                self.cfg = dict(base, **changes)
                self.assertIsNone(self.plan())
        self.cfg = base
        self.assertIsNone(client.private_ca_ip_bootstrap_plan(self.cfg, "f" * 64))


if __name__ == "__main__":
    unittest.main(verbosity=2)
