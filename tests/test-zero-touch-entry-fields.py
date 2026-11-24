#!/usr/bin/env python3
"""Pure entry-field regression. Does not issue tickets or install agents."""
import sys
import unittest
from pathlib import Path
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

    def test_candidate_generation_skips_reserved(self):
        with patch.object(zt.secrets, "choice", side_effect=list("enrollA3xK9m")):
            self.assertEqual(zt.new_bootstrap_locator(), "A3xK9m")
        self.assertTrue(all(zt.is_bootstrap_locator(zt.new_bootstrap_locator())
                            for _ in range(100)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
