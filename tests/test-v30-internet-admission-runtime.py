#!/usr/bin/env python3
"""Internet Access runtime must deny non-approved Managed Host sources."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_runtime_policy as runtime

SOURCE_IP = "10.20.30.41"
UNRELATED_IP = "10.20.30.42"
PUBLIC_IP = "8.8.8.8"


class InternetAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-internet-admission-")
        self.plane = ControlPlane(self.tmp.name)
        self.plane.upsert_client(
            "host-internet", hostname="host-internet",
            addresses=[{"address": SOURCE_IP, "active": True}],
        )

    def tearDown(self):
        self.plane.close()
        self.tmp.cleanup()

    def _evaluate(self, source=SOURCE_IP):
        return self.plane.evaluate_internet_access(
            source, "api.example", 443, "https", candidate_ips=[PUBLIC_IP]
        )

    def test_approved_host_follows_existing_policy(self):
        approved = self._evaluate()
        self.assertEqual(approved["action"], "ALLOW")
        self.assertEqual(approved["authorized_candidates"], [PUBLIC_IP])

    def test_pending_and_quarantined_host_denied_even_without_policy(self):
        for state in ("PENDING_APPROVAL", "QUARANTINED"):
            self.plane.conn.execute(
                "UPDATE clients SET admission_state=? WHERE id='host-internet'",
                (state,),
            )
            result = self._evaluate()
            self.assertEqual(result["action"], "DENY")
            self.assertEqual(result["authorized_candidates"], [])
            self.assertEqual(result["candidate_results"][0]["action"], "DENY")
            self.assertIn("admission", result["reason"].lower())
            with mock.patch.object(runtime, "generation_status", return_value={
                "healthy": True, "revision": self.plane.current_revision(),
                "generation": self.plane.current_revision(), "mismatch": False,
            }):
                enforced = runtime.authorize_internet(
                    self.plane, source_ip=SOURCE_IP, hostname="api.example",
                    port=443, protocol="https", candidate_ips=[PUBLIC_IP],
                )
            self.assertEqual(enforced["decision"], "DENY")
            self.assertEqual(enforced["authorized_candidates"], [])
            self.assertIn("admission", enforced["reason"].lower())
        self.plane.conn.execute(
            "UPDATE clients SET admission_state='APPROVED' WHERE id='host-internet'"
        )
        self.assertEqual(self._evaluate()["action"], "ALLOW")

    def test_quarantine_does_not_impact_different_source(self):
        self.plane.conn.execute(
            "UPDATE clients SET admission_state='QUARANTINED' WHERE id='host-internet'"
        )
        self.assertEqual(self._evaluate(UNRELATED_IP)["action"], "ALLOW")


if __name__ == "__main__":
    unittest.main()
