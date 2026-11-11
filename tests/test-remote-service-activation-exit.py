#!/usr/bin/env python3
"""S-009: failed online Agent activation cannot return CLI success."""
from __future__ import annotations
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import drlink_v24_cli as cli
import drlink_v24 as v24


class ActivationExitSemantics(unittest.TestCase):
    def test_online_activation_failed_exit_nonzero(self):
        plane = mock.Mock(root="/disposable")
        result = {"activation_failed": True, "view": {
            "name": "ssh", "destination": "this-host", "service": "ssh",
            "status": "DEGRADED", "endpoint": "127.0.0.1:6001",
            "reason": "RECOVERY_REQUIRED: runtime restart failed",
        }}
        with mock.patch.object(cli, "_require_agent"), \
             mock.patch.object(cli.v24, "detect_server_reachable", return_value=True), \
             mock.patch.object(cli.v24, "set_remote_service_agent", return_value=result), \
             mock.patch.object(cli.sys, "stdout", io.StringIO()) as out:
            code = cli.handle_set(plane, ["remote-service", "ssh", "destination", "this-host", "service", "ssh", "enabled"])
            self.assertEqual(code, 1)
            self.assertIn("RECOVERY_REQUIRED", out.getvalue())

    def test_paused_or_offline_saved_intent_retains_zero_exit(self):
        plane = mock.Mock(root="/disposable")
        for reason in ("Agent runtime is intentionally paused.", "Server temporarily unreachable"):
            result = {"activation_failed": False, "view": {
                "name": "ssh", "destination": "this-host", "service": "ssh",
                "status": "DEGRADED", "endpoint": "Pending allocation", "reason": reason,
            }}
            with self.subTest(reason=reason), mock.patch.object(cli, "_require_agent"), \
                 mock.patch.object(cli.v24, "detect_server_reachable", return_value=False), \
                 mock.patch.object(cli.v24, "set_remote_service_agent", return_value=result), \
                 mock.patch.object(cli.sys, "stdout", io.StringIO()):
                self.assertEqual(cli.handle_set(plane, ["remote-service", "ssh", "enabled"]), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
