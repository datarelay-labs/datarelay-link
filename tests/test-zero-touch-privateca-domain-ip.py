#!/usr/bin/env python3
"""Regression: DNS and numeric IP must use a single verified bootstrap authority."""
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
        self.pki_dir = Path(self.tmp.name) / "pki"
        pki = frp_pki.ensure_pki(
            self.pki_dir, "221.139.249.109",
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

    def ip_cfg(self):
        return dict(self.cfg, public_url_host="221.139.249.109",
                    allocator_public_url="https://221.139.249.109/enroll")

    def plan(self):
        return client.private_ca_ip_bootstrap_plan(self.cfg, self.ca)

    def test_authority_cannot_change_mid_enrollment(self):
        self.assertIsNone(self.plan())  # DNS selected: IP-only stage 0 is unsafe.
        ip_cfg = self.ip_cfg()
        plan = client.private_ca_ip_bootstrap_plan(ip_cfg, self.ca)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["authority"], "221.139.249.109")
        self.assertEqual(plan["allocator"], "https://221.139.249.109/enroll")
        self.assertEqual(self.cfg["allocator_public_url"], "https://remote.isoc.ooo/enroll")

    def test_preflight_prefers_pinned_dns_after_public_tls_failure(self):
        installer = "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh"
        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""), \
             mock.patch.object(client, "preflight_installer_url", return_value=None), \
             mock.patch.object(client, "_pinned_ca_public_endpoint_verified", return_value=True):
            host, plan = client.validate_zero_touch_prerequisites(
                self.cfg, "linux", installer, self.ca
            )
        self.assertEqual(host, "")
        self.assertEqual(plan["mode"], "private_ca_dns")
        self.assertEqual(plan["allocator"], "https://remote.isoc.ooo/enroll")

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
        self.cfg = self.ip_cfg()
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
        self.cfg = self.ip_cfg()
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
        base = self.ip_cfg()
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


    def test_pinned_private_ca_dns_uses_configured_hostname(self):
        import frp_zero_touch as zt
        plan = client.private_ca_dns_bootstrap_plan(self.cfg, self.ca)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["mode"], "private_ca_dns")
        self.assertEqual(plan["authority"], "remote.isoc.ooo")
        self.assertEqual(plan["allocator"], "https://remote.isoc.ooo/enroll")
        self.assertEqual(
            zt.private_ca_dns_endpoint(self.cfg["allocator_public_url"]),
            ("remote.isoc.ooo", "remote.isoc.ooo", 443),
        )
        # Public-trust negative is distinct from a pinned Private CA positive.
        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""), \
             mock.patch.object(client, "preflight_installer_url", return_value=None), \
             mock.patch.object(client, "_pinned_ca_public_endpoint_verified", return_value=True):
            host, selected = client.validate_zero_touch_prerequisites(
                self.cfg, "linux",
                "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh",
                self.ca,
            )
        self.assertEqual(host, "")
        self.assertEqual(selected, plan)

    def test_pinned_private_ca_dns_linux_and_windows_preserve_hostname(self):
        import frp_zero_touch as zt
        plan = client.private_ca_dns_bootstrap_plan(self.cfg, self.ca)
        self.assertIsNotNone(plan)
        command = zt.private_ca_dns_linux_command(
            plan["allocator"], self.ca, "A" * 22
        )
        self.assertIn("https://remote.isoc.ooo/i/", command)
        self.assertIn("-servername remote.isoc.ooo", command)
        self.assertIn(self.ca, command)
        self.assertNotIn("--insecure", command)
        self.assertLessEqual(len(command), 900)

        win = zt.private_ca_dns_windows_command(
            plan["allocator"], self.ca, "a" * 64, "A" * 22
        )
        self.assertIn("https://remote.isoc.ooo/i/", win)
        self.assertIn(self.ca, win)
        self.assertIn("a" * 64, win)
        self.assertLessEqual(len(win), 1500)

        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""):
            linux_output = io.StringIO()
            with contextlib.redirect_stdout(linux_output):
                client.print_one_line(
                    "bt1.example.secret", 3600, "", "221.139.249.109", 443,
                    self.cfg["allocator_public_url"], self.ca,
                    "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh",
                    "", 22, client_name="test-agent", cfg=self.cfg,
                    short_handle="A" * 22, private_ip_plan=plan, require_compact=True,
                )
            windows_output = io.StringIO()
            with contextlib.redirect_stdout(windows_output):
                client.print_one_line_windows(
                    "bt1.example.secret", 3600, "", "221.139.249.109", 443,
                    self.cfg["allocator_public_url"], self.ca,
                    "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.ps1",
                    client_name="test-agent", cfg=self.cfg, short_handle="A" * 22,
                    stage1_sha256="a" * 64, private_ip_plan=plan, require_compact=True,
                )
        self.assertIn("https://remote.isoc.ooo/i/", linux_output.getvalue())
        self.assertIn("https://remote.isoc.ooo/i/", windows_output.getvalue())
        self.assertNotIn("zt1.", linux_output.getvalue())
        self.assertNotIn("zt1.", windows_output.getvalue())

    def test_pinned_private_ca_dns_enforces_identity_ca_and_san(self):
        import frp_zero_touch as zt
        base = dict(self.cfg)
        self.assertIsNotNone(client.private_ca_dns_bootstrap_plan(base, self.ca))
        for changes in (
            {"public_url_host": "other.isoc.ooo"},
            {"public_url_host": "221.139.249.109"},
            {"allocator_public_url": "https://other.isoc.ooo/enroll"},
            {"allocator_public_url": "http://remote.isoc.ooo/enroll"},
            {"allocator_public_url": "https://user:pass@remote.isoc.ooo/enroll"},
            {"allocator_public_url": "https://remote.isoc.ooo/enroll#fragment"},
            {"bootstrap_hostname": "remote.isoc.ooo"},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(
                    client.private_ca_dns_bootstrap_plan(dict(base, **changes), self.ca)
                )
        self.assertIsNone(client.private_ca_dns_bootstrap_plan(base, "f" * 64))
        self.assertIsNone(zt.private_ca_dns_endpoint("https://127.0.0.1/enroll"))
        self.assertIsNone(zt.private_ca_dns_endpoint("https://remote.isoc.ooo.local/enroll"))
        self.assertIsNone(zt.private_ca_dns_endpoint("https://user:pass@remote.isoc.ooo/enroll"))
        self.assertIsNone(zt.private_ca_dns_endpoint("https://remote.isoc.ooo/enroll?x=y"))
        other_pki = frp_pki.ensure_pki(
            Path(self.tmp.name) / "missing-dns-san", "221.139.249.109"
        )
        bad = dict(base, tls_ca_cert=other_pki["ca_crt"],
                   tls_server_cert=other_pki["server_crt"])
        self.assertIsNone(
            client.private_ca_dns_bootstrap_plan(bad, other_pki["fingerprint"])
        )


    def test_preflight_never_issues_mixed_dns_ip_authority(self):
        installer = "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh"
        seen = []
        def proof(url, ca):
            seen.append(url)
            return url == "https://221.139.249.109/enroll"
        err = io.StringIO()
        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""), \
             mock.patch.object(client, "preflight_installer_url", return_value=None), \
             mock.patch.object(client, "_pinned_ca_public_endpoint_verified", side_effect=proof), \
             contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit):
                client.validate_zero_touch_prerequisites(
                    self.cfg, "linux", installer, self.ca
                )
        self.assertEqual(seen, ["https://remote.isoc.ooo/enroll"])
        self.assertIn("No enrollment ticket was issued", err.getvalue())


    def test_rejects_every_unreachable_bootstrap_before_ticket(self):
        installer = "https://remote.isoc.ooo/artifacts/agent/bootstrap-client.sh"
        with mock.patch.object(client, "short_url_host_for_cfg", return_value=""), \
             mock.patch.object(client, "preflight_installer_url", return_value=None), \
             mock.patch.object(client, "_pinned_ca_public_endpoint_verified", return_value=False):
            messages = io.StringIO()
            with contextlib.redirect_stderr(messages), self.assertRaises(SystemExit):
                client.validate_zero_touch_prerequisites(
                    self.cfg, "linux", installer, self.ca
                )
        self.assertIn("No enrollment ticket was issued", messages.getvalue())


    def test_real_https_probe_pins_ca_san_and_allocator_signature(self):
        """A real TLS socket exercises positive and negative trust paths."""
        import http.server
        import ssl
        import threading

        tls = frp_pki.ensure_pki(
            Path(self.tmp.name) / "tls-listener", "127.0.0.1"
        )
        class Handler(http.server.BaseHTTPRequestHandler):
            response_body = b"bootstrap unavailable"
            response_code = 404
            def do_GET(self):
                if self.path != "/i/invalid-qualification-probe":
                    self.send_error(404)
                    return
                self.send_response(type(self).response_code)
                self.end_headers()
                self.wfile.write(type(self).response_body)
            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.load_cert_chain(tls["server_crt"], tls["server_key"])
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "https://127.0.0.1:%s/enroll" % server.server_port
            self.assertTrue(
                client._pinned_ca_public_endpoint_verified(url, tls["ca_crt"])
            )
            # A valid self-signed CA for a different leaf is not trust.
            self.assertFalse(
                client._pinned_ca_public_endpoint_verified(
                    url, str(self.pki_dir / "ca.crt")
                )
            )
            Handler.response_body = b"<html>generic proxy 404</html>"
            self.assertFalse(
                client._pinned_ca_public_endpoint_verified(url, tls["ca_crt"])
            )
            Handler.response_body = b"bootstrap unavailable"
            Handler.response_code = 302
            self.assertFalse(
                client._pinned_ca_public_endpoint_verified(url, tls["ca_crt"])
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
