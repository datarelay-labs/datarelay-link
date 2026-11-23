#!/usr/bin/env python3
"""S-024: fail closed on malformed Agent installer URL hostnames."""
import importlib.machinery
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
module = importlib.machinery.SourceFileLoader(
    'drlink_test_installer_url', str(ROOT / 'tools/frp-set-client-installer-url')
).load_module()


class InstallerUrlHostnameValidation(unittest.TestCase):
    def test_malformed_dns_label_fails_before_config_mutation(self):
        invalid = (
            'https://bad..example/install-client.sh',
            'https://-bad.example/install-client.sh',
            'https://bad-.example/install-client.sh',
            'https://bad_name.example/install-client.sh',
            'https://192.168.0.999/install-client.sh',
            'https://bad.example./install-client.sh',
            'https://ex%61mple.com/install-client.sh',
        )
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(SystemExit):
                    module.validate_https_installer_url(url)

    def test_public_fqdn_private_ip_and_bracketed_ipv6_remain_supported(self):
        for url in (
            'https://bootstrap.example.com/agent/install.sh',
            'https://192.0.2.10:6099/agent/install.sh',
            'https://[2001:db8::1]:6099/agent/install.sh',
            'https://localhost:9443/agent/install.sh',
        ):
            with self.subTest(url=url):
                self.assertEqual(module.validate_https_installer_url(url), url)

if __name__ == '__main__':
    unittest.main(verbosity=2)
