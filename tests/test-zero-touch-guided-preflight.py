#!/usr/bin/env python3
"""Public drlink Wizard: verify signed bootstrap before name/service prompts.

Real subprocess REPL, no dry-run dispatcher, no issuance and no live Server
mutation. Linux, Windows and macOS use the same side-effect-free gate.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import frp_pki


class GuidedPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-public-zt-preflight-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "etc/drlink").mkdir(parents=True)
        (self.root / "var/lib/drlink").mkdir(parents=True)
        self.config = {
            "enrollments_dir": "/var/lib/drlink/enrollments",
            "allocator_public_url": "https://127.0.0.1:49191/enroll",
            "client_installer_url": "https://127.0.0.1:49191/artifacts/agent/bootstrap-client.sh",
            "windows_client_installer_url": "https://127.0.0.1:49191/artifacts/agent/bootstrap-client.ps1",
            "tls_ca_cert": "/etc/drlink/pki/ca.crt",
            "tls_server_cert": "/etc/drlink/pki/server.crt",
            "public_ip": "127.0.0.1",
            "control_port": 443,
        }

    def invoke(self, platform: int, *, usable: bool):
        if usable:
            frp_pki.ensure_pki(self.root / "etc/drlink/pki", "127.0.0.1")
        (self.root / "etc/drlink/config.json").write_text(
            json.dumps(self.config) + "\n", encoding="utf-8"
        )
        # Choose Back after viewing the Managed Host options; do not issue a ticket.
        steps = ["set enrollment zero-touch", str(platform)]
        if usable:
            steps.extend(["escare", "", "4" if platform == 2 else "3"])
        steps.append("exit")
        env = dict(os.environ, FRP_CTL_TEST_ROOT=str(self.root),
                   FRP_CTL_TEST_INPUT="\n".join(steps) + "\n",
                   FRP_CTL_BIN_DIR=str(ROOT / "tools"),
                   FRP_CTL_FORCE_DRLINK="1", FRP_CTL_DRY_RUN="0",
                   FRP_SKIP_SYSTEMD="1", HOME=str(self.root))
        proc = subprocess.run(
            [str(ROOT / "tools/frpctl")], env=env, capture_output=True,
            text=True, timeout=30, check=False,
        )
        text = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, text[-450:])
        self.assertNotIn("DISPATCH frp-create-client", text)
        self.assertNotIn("Create this Agent setup?", text)
        self.assertFalse((self.root / "var/lib/drlink/enrollments").exists())
        self.assertFalse((self.root / "var/lib/drlink/bootstrap").exists())
        return text

    def test_missing_private_ca_fails_before_any_user_fields(self):
        for platform in (1, 2, 3):
            with self.subTest(platform=platform):
                text = self.invoke(platform, usable=False)
                self.assertIn("allocator CA SHA256 fingerprint is unavailable", text)
                self.assertNotIn("Managed Host details", text)
                self.assertNotIn("Configure services", text)

    def test_valid_dns_free_ip_private_ca_precedes_all_user_fields(self):
        for platform in (1, 2, 3):
            with self.subTest(platform=platform):
                text = self.invoke(platform, usable=True)
                self.assertIn("Zero-Touch prerequisites verified; no ticket was issued", text)
                self.assertIn("Managed Host details", text)
                self.assertLess(
                    text.index("Zero-Touch prerequisites verified"),
                    text.index("Managed Host details"),
                )
                self.assertIn("How do you want to configure this Managed Host?", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
