#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli


class EmptyStateCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-empty-state-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()

    def dispatch(self, tokens):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(tokens, root=self.tmp, plane=self.plane)
        return rc, out.getvalue(), err.getvalue()
    def test_major_empty_lists_are_explicit(self):
        cases = (
            (["show", "enrollments"], "No Enrollments"),
            (["show", "managed-hosts"], "No Managed Hosts"),
            (["show", "network-objects"], "No Network Objects"),
            (["show", "network-groups"], "No Network Groups"),
            (["show", "service-groups"], "No Service Groups"),
            (["show", "permission-objects"], "No Permission Objects"),
            (["show", "permission-groups"], "No Permission Groups"),
            (["show", "ai-identities"], "No AI Identities"),
            (["system", "revisions"], "No Revisions"),
        )
        for tokens, marker in cases:
            with self.subTest(tokens=tokens):
                rc, out, err = self.dispatch(list(tokens))
                self.assertEqual(rc, 0, err)
                self.assertTrue(out.strip(), tokens)
                self.assertIn(marker, out)
                self.assertEqual(err, "")

    def test_missing_managed_host_uses_public_terminology(self):
        rc, out, err = self.dispatch(["show", "managed-host", "missing-host"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertIn("Managed Host not found: missing-host", err)
        self.assertNotIn("client not found", err.lower())

    def test_policy_and_ai_log_empty_states_are_explicit(self):
        self.plane.conn.execute(
            "UPDATE access_policies SET mode = 'blacklist', enforcement = 'enabled' "
            "WHERE plane IN ('remote', 'internet')"
        )
        self.plane.conn.commit()
        cases = (
            (["show", "remote-access"], "No rules configured."),
            (["show", "internet-access"], "No rules configured."),
            (["show", "ai-access"], "No rules configured."),
            (["show", "ai-access-log"], "No AI Access Log entries found."),
        )
        for tokens, marker in cases:
            with self.subTest(tokens=tokens):
                rc, out, err = self.dispatch(list(tokens))
                self.assertEqual(rc, 0, err)
                self.assertIn(marker, out)
                self.assertEqual(err, "")

    def test_agent_system_info_empty_remote_services_is_explicit(self):
        tmp = Path(tempfile.mkdtemp(prefix="drlink-agent-info-empty-"))
        (tmp / "etc/frp").mkdir(parents=True, exist_ok=True)
        (tmp / "etc/drlink").mkdir(parents=True, exist_ok=True)
        (tmp / "etc/frp/client-state.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "allocator_url": "https://127.0.0.1:9/enroll",
                    "frp_server": "203.0.113.10",
                    "frp_server_port": 443,
                    "hostname": "audit-agent",
                    "machine_id": "00112233445566778899aabbccddeeff",
                    "host_id": "audit-agent-00112233",
                    "services": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (tmp / "etc/drlink/version").write_text(
            "PROJECT_VERSION=2.4.0\nFRP_VERSION=0.71.0\n", encoding="utf-8"
        )
        env = os.environ.copy()
        env.update(
            {
                "FRP_CTL_TEST_ROOT": str(tmp),
                "FRP_CLIENT_TEST_ROOT": str(tmp),
                "FRP_CTL_FORCE_DRLINK": "1",
                "FRP_CTL_CMD_NAME": "drlink",
                "FRP_CTL_BIN_DIR": str(ROOT / "tools"),
                "FRP_CLIENT_LIB": str(ROOT / "lib/frp-client-common.sh"),
                "FRP_SKIP_SYSTEMD": "1",
            }
        )
        proc = subprocess.run(
            [str(ROOT / "tools/frpctl"), "system", "info"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Remote Services:", proc.stdout)
        self.assertIn("No Remote Services configured.", proc.stdout)

    def test_agent_remote_services_empty_state_is_explicit(self):
        tmp = tempfile.mkdtemp(prefix="drlink-agent-empty-state-")
        Path(tmp, "etc/frp").mkdir(parents=True, exist_ok=True)
        Path(tmp, "etc/frp/client-state.json").write_text(
            '{"client_id":"audit-agent","hostname":"audit-agent"}\n',
            encoding="utf-8",
        )
        plane = ControlPlane(tmp)
        out = io.StringIO()
        err = io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli.dispatch(["show", "remote-services"], root=tmp, plane=plane)
        finally:
            plane.close()
        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(out.getvalue(), "No Remote Services configured.\n")
        self.assertEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
