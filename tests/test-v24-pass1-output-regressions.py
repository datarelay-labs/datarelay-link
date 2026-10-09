#!/usr/bin/env python3
"""Targeted regressions for user-visible v2.4 PASS1 defects.

These tests operate on temporary user state and never touch a live install.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lib"))

import drlink_v24_cli as cli


class OutputRegressions(unittest.TestCase):
    def test_ai_log_destination_uses_persisted_endpoint_name(self):
        class Plane:
            def list_ai_activity(self, principal=None, endpoint=None):
                self.arguments = (principal, endpoint)
                return [{
                    "timestamp": "2026-10-09T03:00:00Z",
                    "principal_name": "automation-ai",
                    "endpoint_name": "ubuntu-prod",
                    "capability": "read_file",
                    "result": "ALLOW",
                }]

        plane = Plane()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(
                cli._show_ai_log(
                    plane, ["identity", "automation-ai", "destination", "ubuntu-prod"]
                ), 0
            )
        self.assertEqual(plane.arguments, ("automation-ai", "ubuntu-prod"))
        self.assertIn("ubuntu-prod", out.getvalue())
        self.assertNotIn("No AI Access Log", out.getvalue())

    def _bash(self, script, *args, env_extra=None):
        env = os.environ.copy()
        env.update(FRP_TEST_UNAME_S="Darwin", FRP_TEST_UNAME_M="arm64")
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["bash", "-c", '. "$1/lib/frp-client-common.sh"; ' + script,
             "test", str(REPO), *map(str, args)],
            env=env, text=True, capture_output=True, timeout=15,
        )

    def test_macos_installer_guidance_uses_launchd_and_real_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "services.json"
            state.write_text(json.dumps([{
                "id": "ssh", "name": "SSH", "preset": "ssh",
                "local_ip": "127.0.0.1", "local_port": 22,
            }]))
            proc = self._bash(
                'frp_ux_intro; frp_ux_print_install_summary "$2" "0.71.0"',
                state,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("this macOS system", proc.stdout)
            self.assertIn("com.datarelay.drlink.frpc launchd daemon", proc.stdout)
            self.assertIn("/Library/Application Support/drlink/frpc.toml", proc.stdout)
            self.assertNotIn("systemd service", proc.stdout)

    def test_internal_rs_id_not_leaked_as_connection_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "services.json"
            dest = Path(tmp) / "access-info.txt"
            state.write_text(json.dumps({"services": {
                "rs-ssh": {
                    "id": "rs-ssh", "name": "ssh", "preset": "ssh",
                    "local_ip": "127.0.0.1", "local_port": 22,
                    "remote_port": 6000, "enabled": True,
                }
            }}))
            proc = self._bash(
                'render_access_info "$2" 203.0.113.10 "$3"',
                dest, state,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = dest.read_text()
            self.assertIn("\nssh\n", data)
            self.assertNotIn("rs-ssh", data)

    def test_macos_autostart_uses_launchctl_true_false_not_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            script_file = Path(tmp) / "launchctl"
            script_file.write_text(
                '#!/bin/sh\ncat "$MOCK_LAUNCHCTL_FILE"\n'
            )
            script_file.chmod(0o755)
            state = Path(tmp) / "disabled.txt"
            env = {
                "PATH": tmp + ":" + os.environ["PATH"],
                "MOCK_LAUNCHCTL_FILE": str(state),
                "FRP_CLIENT_TEST_ROOT": "",  # force the real read-only launchctl branch
                "FRP_SKIP_SYSTEMD": "0",
            }
            for response, expected in [
                ('"com.datarelay.drlink.frpc" => true', False),
                ('"com.datarelay.drlink.frpc" => false', True),
                ('"unrelated.agent" => false', False),
                ('garbage', False),
            ]:
                with self.subTest(response=response):
                    state.write_text("disabled services = {\n " + response + "\n}\n")
                    proc = self._bash(
                        'frp_client_autostart_enabled && echo ENABLED || echo DISABLED',
                        env_extra=env,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(
                        proc.stdout.strip() == "ENABLED", expected,
                        proc.stdout + proc.stderr,
                    )


if __name__ == "__main__":
    unittest.main()
