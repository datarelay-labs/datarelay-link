#!/usr/bin/env python3
"""DRL3 Host admission denial in runtime Remote Access: no rule mutation."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_runtime_policy as policy


class AdmissionRemoteRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-admission-runtime-")
        self.plane = ControlPlane(self.tmp.name)
        self.plane.upsert_client("host-a", hostname="host-a")
        self.before = self.plane.current_revision()
        self.proxy = {
            "owned-proxy": {
                "client_id": "host-a",
                "client_label": "host-a",
                "service_id": "ssh",
                "public_port": 6005,
                "enabled": True,
                "has_remote_meta": False,
                "target_mode": "self",
                "target_port": 22,
            }
        }

    def tearDown(self):
        self.plane.close()
        self.tmp.cleanup()

    def _authorize(self):
        with mock.patch.object(
            policy, "generation_status",
            return_value={
                "healthy": True, "revision": self.before,
                "generation": self.before, "mismatch": False,
            },
        ), mock.patch.object(policy, "build_proxy_map", return_value=self.proxy), \
             mock.patch.object(policy, "_destination_for_service", return_value="host-a"), \
             mock.patch.object(self.plane, "evaluate_remote_access",
                 return_value={"action": "ALLOW", "reason": "TEST_POLICY_ALLOW"}) as evaluator:
            result = policy.authorize_remote(
                self.plane, proxy_name="owned-proxy", source_ip="203.0.113.9"
            )
            return result, evaluator.call_count

    def test_quarantine_overrides_permissive_policy_without_changing_connectivity(self):
        original, calls = self._authorize()
        self.assertEqual(original["decision"], "ALLOW")
        self.assertEqual(calls, 1)
        for state in ("PENDING_APPROVAL", "QUARANTINED"):
            self.plane.conn.execute(
                "UPDATE clients SET admission_state=? WHERE id='host-a'",
                (state,),
            )
            result, calls = self._authorize()
            self.assertEqual(result["decision"], "DENY")
            self.assertEqual(result["reason"], "HOST_ADMISSION_NOT_APPROVED")
            self.assertEqual(calls, 0)
            row = self.plane.require_client("host-a")
            self.assertEqual(row["trust_status"], "trusted")
            self.assertEqual(row["connected"], 1)
            self.assertEqual(self.plane.current_revision(), self.before)

        self.plane.conn.execute(
            "UPDATE clients SET admission_state='APPROVED' WHERE id='host-a'"
        )
        permitted, calls = self._authorize()
        self.assertEqual(permitted["decision"], "ALLOW")
        self.assertEqual(calls, 1)

    def test_revoked_host_and_missing_owner_deny_even_with_permissive_rule(self):
        self.plane.conn.execute(
            "UPDATE clients SET trust_status='revoked' WHERE id='host-a'"
        )
        denied, calls = self._authorize()
        self.assertEqual((denied["decision"], calls), ("DENY", 0))
        # Exercise an orphaned proxy mapping without violating the real
        # inventory foreign-key invariant or deleting a managed Host.
        self.proxy["owned-proxy"]["client_id"] = "host-missing"
        missing, calls = self._authorize()
        self.assertEqual((missing["decision"], calls), ("DENY", 0))


if __name__ == "__main__":
    unittest.main()
