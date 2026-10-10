"""Actual Link 3.0 Web native TOTP uses the exact Foundation offline wheel."""
from __future__ import annotations

import hashlib
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_foundation_security as link_wheel  # noqa: E402
import datarelay_onprem_security as foundation  # noqa: E402
import drlink_web_auth as web_auth  # noqa: E402

SHA = "6c7c4c8b425fb181e0c10c61aa7ec4ea47c24121379db2c5230251a3bdbc40db"
SOURCE = "59b8199d6182e0bed2b25307736edb4dad32a246"
WHEEL_NAME = "datarelay_onprem_security-0.10.0.dev0-py3-none-any.whl"
RFC_SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


class LinkFoundationTotpTests(unittest.TestCase):
    def test_exact_wheel_and_true_zipimport(self):
        wheel = ROOT / "lib" / WHEEL_NAME
        self.assertEqual(wheel.stat().st_size, 36276)
        self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), SHA)
        self.assertEqual(link_wheel.FOUNDATION_WHEEL_SHA256, SHA)
        self.assertEqual(link_wheel.FOUNDATION_SOURCE_HEAD, SOURCE)
        self.assertEqual(link_wheel.FOUNDATION_VERSION, "0.10.0.dev0")
        self.assertTrue(str(foundation.__file__).startswith(str(wheel) + "/"))

    def test_link_totp_matches_rfc_vector_and_replay_counter(self):
        now = datetime.fromtimestamp(59, timezone.utc)
        code, counter = web_auth.totp_code(RFC_SEED, at=now)
        self.assertEqual((code, counter), ("287082", 1))
        self.assertEqual(web_auth.verify_totp(RFC_SEED, code, at=now), 1)
        self.assertIsNone(web_auth.verify_totp(RFC_SEED, code, at=now, last_counter=1))
        self.assertEqual(web_auth.verify_totp(RFC_SEED, code, at=now + timedelta(seconds=30),
                                              last_counter=0), 1)
        self.assertIsNone(web_auth.verify_totp(RFC_SEED, code, at=now + timedelta(seconds=90)))

    def test_enrollment_seed_and_product_otp_compatibility(self):
        key = web_auth.generate_totp_secret()
        self.assertEqual(len(key), 32)
        self.assertNotEqual(key, web_auth.generate_totp_secret())
        at = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
        code, counter = web_auth.totp_code(key, at=at)
        self.assertEqual(code, foundation.code_at(key, at.timestamp()))
        self.assertEqual(counter, web_auth.verify_totp(key, code, at=at))
        self.assertIsNone(web_auth.verify_totp(key, "００００００", at=at))
        self.assertIsNone(web_auth.verify_totp(key, "abcdef", at=at))

    def test_native_web_functions_call_shared_library(self):
        now = datetime.fromtimestamp(59, timezone.utc)
        with patch.object(web_auth, "foundation_totp_code_at", return_value="111111") as writer:
            code, counter = web_auth.totp_code(RFC_SEED, at=now)
            self.assertEqual((code, counter), ("111111", 1))
            writer.assert_called_once_with(RFC_SEED, now.timestamp())
        with patch.object(web_auth, "foundation_verify_totp", return_value=1) as verifier:
            self.assertEqual(web_auth.verify_totp(RFC_SEED, "123456", at=now), 1)
            verifier.assert_called_once_with(RFC_SEED, "123456",
                                              now=now.timestamp(), last_counter=None)
        with patch.object(web_auth, "foundation_new_totp_secret", return_value=RFC_SEED) as source:
            self.assertEqual(web_auth.generate_totp_secret(), RFC_SEED)
            source.assert_called_once()

    def test_wheel_tamper_fails_closed_before_import(self):
        with tempfile.TemporaryDirectory(prefix="drlink-foundation-totp-test-") as td:
            tmp = Path(td)
            helper = tmp / "drlink_foundation_security.py"
            wheel = tmp / WHEEL_NAME
            shutil.copyfile(ROOT / "lib/drlink_foundation_security.py", helper)
            data = (ROOT / "lib" / WHEEL_NAME).read_bytes()
            wheel.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            with self.assertRaisesRegex(RuntimeError, "DRLINK_FOUNDATION_SECURITY_WHEEL_UNAVAILABLE"):
                runpy.run_path(str(helper))

    def test_optional_web_manifest_and_uninstall_own_two_files(self):
        manifest = (ROOT / "lib/web-project-files.manifest").read_text(encoding="utf-8")
        uninstall = (ROOT / "uninstall-web.sh").read_text(encoding="utf-8")
        for name in ("drlink_foundation_security.py", "drlink_web_management_policy.py", "drlink_web_config_history.py", WHEEL_NAME):
            self.assertIn("lib/" + name, manifest)
            self.assertIn("usr/local/lib/drlink/" + name, manifest)
            self.assertIn("usr/local/lib/drlink/" + name, uninstall)
        server_manifest = (ROOT / "lib/server-project-files.manifest").read_text(encoding="utf-8")
        self.assertNotIn(WHEEL_NAME, server_manifest)
        self.assertNotIn("drlink_foundation_security.py", server_manifest)


if __name__ == "__main__":
    unittest.main()
