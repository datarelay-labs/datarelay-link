#!/usr/bin/env python3
"""Regression: the Windows Real E2E harness must see a pre-existing legacy Agent.

Observed defect (harness, not product): ``04-client-uninstall`` probed only the
canonical ``C:\\ProgramData\\drlink`` root and reported ``NO_INSTALL`` for a host
that still carried an enrolled v2.3.x Agent under the legacy
``C:\\ProgramData\\frp-auto-deploy`` root.  The next step then failed inside the
product's fail-closed identity guard with no pointer to the real cause.

The harness must instead fail closed with ``LEGACY_INSTALL_PRESENT`` before it
enrolls, and must never uninstall state it did not create.  A second latent
defect is covered here too: the identity check kept the CR that Windows OpenSSH
appends to ``hostname`` output, so an explicit expected hostname could never
match.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "lib"))
import real_e2e_windows_command as helper  # noqa: E402

PROBE = ROOT / "tests" / "lib" / "real_e2e_windows_preinstall_probe.ps1"
HARNESS = ROOT / "tests" / "run-real-e2e.sh"
PWSH = shutil.which("pwsh")


def run_probe(program_data: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, ProgramData=str(program_data))
    return subprocess.run(
        [PWSH, "-NoProfile", "-File", str(PROBE)],
        env=env, capture_output=True, text=True, timeout=60,
    )


def make_enrolled(root: Path) -> None:
    for rel in ("state/client-state.json", "config/frpc.toml", "state/client-identity.pub"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


class PreinstallProbeTests(unittest.TestCase):
    def test_probe_file_exists(self):
        self.assertTrue(PROBE.is_file(), "probe script must be a shared, testable file")

    @unittest.skipUnless(PWSH, "pwsh is required to execute the probe")
    def test_clean_host_reports_no_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_probe(Path(tmp))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "NO_INSTALL")

    @unittest.skipUnless(PWSH, "pwsh is required to execute the probe")
    def test_enrolled_legacy_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_enrolled(Path(tmp) / "frp-auto-deploy")
            result = run_probe(Path(tmp))
            # The probe must not modify or remove the pre-existing state.
            still_there = (Path(tmp) / "frp-auto-deploy" / "state" / "client-state.json").exists()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("LEGACY_INSTALL_PRESENT", result.stdout)
        self.assertTrue(still_there, "the probe must never delete pre-existing legacy state")

    @unittest.skipUnless(PWSH, "pwsh is required to execute the probe")
    def test_partial_legacy_root_is_not_an_enrolled_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "frp-auto-deploy" / "tools").mkdir(parents=True)
            result = run_probe(Path(tmp))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "NO_INSTALL")

    def test_encoder_round_trips_the_probe_script(self):
        encoded = helper.encode_script_file(PROBE)
        decoded = base64.b64decode(encoded).decode("utf-16le")
        self.assertEqual(decoded, PROBE.read_text(encoding="utf-8"))


class HarnessWiringTests(unittest.TestCase):
    def setUp(self):
        self.text = HARNESS.read_text(encoding="utf-8")

    def test_uninstall_step_uses_the_shared_probe(self):
        self.assertIn("real_e2e_windows_preinstall_probe.ps1", self.text)
        step = re.search(r"run_client 04-client-uninstall .*", self.text)
        self.assertIsNotNone(step)
        self.assertNotIn("NO_INSTALL", step.group(0), "no inline canonical-only probe")

    def test_identity_check_ignores_transport_cr(self):
        match = re.search(r"^assert_host_identity\(\) \{.*?^\}", self.text, re.S | re.M)
        self.assertIsNotNone(match)
        script = "\n".join([
            "set -uo pipefail",
            "SSH_OPTS=()",
            "CONTROLLER_HOST=''; FORBIDDEN_HOST='forbidden'; EXCLUDED_SERVER_HOST=''",
            "ssh() { printf 'DESKTOP-X\\r\\n'; }",
            "note() { :; }",
            "record() { echo \"RECORD $*\"; }",
            match.group(0),
            "assert_host_identity win DESKTOP-X client; echo \"rc=$?\"",
        ])
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
        self.assertIn("RECORD identity-client PASS", result.stdout, result.stdout + result.stderr)
        self.assertIn("rc=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
