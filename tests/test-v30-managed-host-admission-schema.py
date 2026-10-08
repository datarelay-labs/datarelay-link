#!/usr/bin/env python3
"""Additive host admission data contract; no premature enforcement is enabled."""
from __future__ import annotations

import sqlite3
import io
from contextlib import redirect_stdout
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_plane import ControlPlane
from drlink_control_db import ensure_v30_schema, ControlPlaneError
from drlink_management_service import ManagementQueryService


class HostAdmissionStateTests(unittest.TestCase):
    def test_first_enrollment_initial_state_is_explicit_and_never_overwrites_existing(self):
        with tempfile.TemporaryDirectory(prefix="drlink-admission-create-") as root:
            plane = ControlPlane(root)
            try:
                plane.upsert_client(
                    "new-pending", hostname="new-pending",
                    initial_admission_state="PENDING_APPROVAL",
                )
                row = plane.require_client("new-pending")
                self.assertEqual(row["admission_state"], "PENDING_APPROVAL")
                # Reconnects and registry reconciliation are not permission changes.
                plane.upsert_client(
                    "new-pending", hostname="renamed",
                    initial_admission_state="APPROVED",
                )
                self.assertEqual(
                    plane.require_client("new-pending")["admission_state"],
                    "PENDING_APPROVAL",
                )
                plane.upsert_client("legacy-compat", hostname="legacy-compat")
                self.assertEqual(
                    plane.require_client("legacy-compat")["admission_state"],
                    "APPROVED",
                )
                with self.assertRaises(ControlPlaneError):
                    plane.upsert_client(
                        "invalid-state", hostname="invalid-state",
                        initial_admission_state="QUARANTINED",
                    )
                self.assertIsNone(plane.get_client("invalid-state"))
            finally:
                plane.close()

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

    def test_cli_admission_view_separates_approval_trust_and_connectivity(self):
        from drlink_control_cli import dispatch
        from frp_ctl_grammar import match

        with tempfile.TemporaryDirectory(prefix="drlink-host-admission-cli-") as root:
            plane = ControlPlane(root)
            try:
                plane.upsert_client("host-a", hostname="agent-a", connected=True)
                revision = plane.current_revision()
                for admission_state in ("PENDING_APPROVAL", "QUARANTINED", "APPROVED"):
                    plane.conn.execute(
                        "UPDATE clients SET admission_state=?,admission_actor=?,"
                        "admission_changed_at=? WHERE id='host-a'",
                        (admission_state, "ops-admin", "2026-10-08T00:00:00Z"),
                    )
                    plane.conn.commit()
                    cmd = ["show", "managed-host", "host-a", "admission"]
                    self.assertEqual(match(cmd, role="server")["status"], "ok")
                    stream = io.StringIO()
                    with redirect_stdout(stream):
                        self.assertEqual(dispatch(cmd, root=root), 0)
                    output = stream.getvalue()
                    self.assertIn("Admission state: %s" % admission_state, output)
                    self.assertIn("Management trust: trusted", output)
                    self.assertIn("Connectivity: connected", output)
                    self.assertIn("Changed by: ops-admin", output)
                    self.assertEqual(plane.current_revision(), revision)
            finally:
                plane.close()

    def test_admission_read_models_show_pending_and_quarantined_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix="drlink-admission-attention-") as root:
            plane = ControlPlane(root)
            try:
                for host, state in (
                    ("pending-a", "PENDING_APPROVAL"),
                    ("quarantined-b", "QUARANTINED"),
                    ("approved-c", "APPROVED"),
                ):
                    plane.upsert_client(host, hostname=host)
                    plane.conn.execute(
                        "UPDATE clients SET admission_state=? WHERE id=?",
                        (state, host),
                    )
                plane.conn.commit()
                before = plane.current_revision()
            finally:
                plane.close()

            with ManagementQueryService.open_read_only(root) as query:
                counts = query.overview_summary()["managed_hosts"]
                attention = query.attention_summary()
            self.assertEqual(counts["pending_approval"], 1)
            self.assertEqual(counts["quarantined"], 1)
            self.assertEqual(counts["approved"], 1)
            first_kinds = [item["kind"] for item in attention["items"][:2]]
            self.assertEqual(
                first_kinds, ["pending-host-approval", "quarantined-hosts"]
            )
            self.assertEqual(attention["signals"]["host_admission"], {
                "pending_approval": 1, "quarantined": 1, "approved": 1,
            })
            plane = ControlPlane(root)
            try:
                self.assertEqual(plane.current_revision(), before)
            finally:
                plane.close()

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
