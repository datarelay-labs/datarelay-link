#!/usr/bin/env python3
"""Regressions from live U-013 and S-024 operator mistake E2E."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


def installer_module():
    spec = importlib.util.spec_from_file_location("installer_config", ROOT / "tools/frp-set-client-installer-url")
    # The executable does not have a .py suffix, so provide an explicit loader.
    from importlib.machinery import SourceFileLoader
    spec = importlib.util.spec_from_loader("installer_config", SourceFileLoader("installer_config", str(ROOT / "tools/frp-set-client-installer-url")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InstallerUrlValidation(unittest.TestCase):
    def test_malformed_hostname_fails_before_state_change(self):
        mod = installer_module()
        for value in (
            "https://bad..example/install-client.sh",
            "https://-bad.example/install-client.sh",
            "https://bad-.example/install-client.sh",
            "https://bad_example/install-client.sh",
            "https://host.example:/install-client.sh",
            "https://foo%2ebar.example/install-client.sh",
            "https://user@host.example/install-client.sh",
        ):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                mod.validate_https_installer_url(value)

    def test_valid_endpoints_preserved(self):
        mod = installer_module()
        for value in (
            "https://installer.example.com/agent/install.sh",
            "https://221.139.249.113:6099/artifacts/agent/bootstrap-client.sh",
            "https://[2001:db8::1]:6099/artifacts/bootstrap-client.sh",
        ):
            with self.subTest(value=value):
                self.assertEqual(mod.validate_https_installer_url(value), value)


class ZeroTouchUsernameValidation(unittest.TestCase):
    def validate(self, user):
        src = (ROOT / "tools/frpctl").read_text(encoding="utf-8")
        start = src.index("frpctl_zt_validate_field() {")
        end = src.index("\n}\n", start) + len("\n}\n")
        fn = src[start:end]
        return subprocess.run(["bash", "-c", fn + "\nfrpctl_zt_validate_field ssh_user \"$1\"", "--", user], capture_output=True, text=True)

    def test_blank_ssh_username_is_optional(self):
        result = self.validate("")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "\n")

    def test_invalid_ssh_username_is_rejected(self):
        for value in ("invalid user", "a" * 33, "root;id"):
            with self.subTest(value=value):
                self.assertNotEqual(self.validate(value).returncode, 0)


if __name__ == "__main__":
    unittest.main()
