#!/usr/bin/env python3
"""Additive host admission data contract; no premature enforcement is enabled."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_plane import ControlPlane
from drlink_control_db import ensure_v30_schema
from drlink_management_service import ManagementQueryService


class HostAdmissionStateTests(unittest.TestCase):
    def test_existing_hosts_remain_approved_after_repeat_migration(self):
        with tempfile.TemporaryDirectory(prefix="drlink-host-admission-") as root:
            plane = ControlPlane(root)
            try:
                plane.upsert_client("host-legacy", hostname="host-legacy")
                before = plane.current_revision()
                for _ in range(2):
                    ensure_v30_schema(plane.conn)
                row = plane.conn.execute(
                    "SELECT admission_state,admission_actor,admission_changed_at,"
                    "trust_status,connected FROM clients WHERE id=?",
                    ("host-legacy",),
                ).fetchone()
                self.assertEqual(row["admission_state"], "APPROVED")
                self.assertIsNone(row["admission_actor"])
                self.assertIsNone(row["admission_changed_at"])
                self.assertEqual(row["trust_status"], "trusted")
                self.assertEqual(plane.current_revision(), before)
                with self.assertRaises(sqlite3.IntegrityError):
                    plane.conn.execute(
                        "UPDATE clients SET admission_state='INVALID' WHERE id='host-legacy'"
                    )
            finally:
                plane.close()
            with ManagementQueryService(root) as reader:
                row = reader.get_inventory("managed-host", "host-legacy")
                self.assertEqual(row["admission_state"], "APPROVED")
                self.assertIsNone(row["admission_changed_at"])
                paged = reader.list_inventory("managed-host")
                self.assertEqual(paged.items[0]["admission_state"], "APPROVED")

    def test_unapproved_host_cannot_issue_or_use_ai_credentials_or_enqueue_jobs(self):
        from drlink_control_db import ControlPlaneError
        with tempfile.TemporaryDirectory(prefix="drlink-host-ai-admission-") as root:
            plane = ControlPlane(root)
            try:
                plane.upsert_client("host-a", hostname="host-a")
                token = plane.issue_agent_credential("host-a")
                self.assertIsNotNone(token)
                self.assertEqual(plane.authenticate_agent(token), "host-a")
                for state in ("PENDING_APPROVAL", "QUARANTINED"):
                    plane.conn.execute(
                        "UPDATE clients SET admission_state=? WHERE id='host-a'", (state,)
                    )
                    self.assertIsNone(plane.issue_agent_credential("host-a", rotate=True))
                    self.assertIsNone(plane.authenticate_agent(token))
                    with self.assertRaisesRegex(ControlPlaneError, "admission"):
                        plane.assert_ai_job_claimant("host-a")
                    with self.assertRaisesRegex(ControlPlaneError, "admission"):
                        plane.enqueue_ai_job(
                            principal_id=None, endpoint_object_id="endpoint-test",
                            client_id="host-a", capability="host-info", arguments={},
                            patterns=[], timeout=30,
                        )
                    client = plane.require_client("host-a")
                    self.assertEqual(client["trust_status"], "trusted")
                    self.assertTrue(bool(client["connected"]))
                    self.assertEqual(plane.managed_host_connectivity(client), "connected")
                plane.conn.execute(
                    "UPDATE clients SET admission_state='APPROVED' WHERE id='host-a'"
                )
                self.assertEqual(plane.authenticate_agent(token), "host-a")
                plane.assert_ai_job_claimant("host-a")
            finally:
                plane.close()


if __name__ == "__main__":
    unittest.main()
