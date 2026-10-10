#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_v24 as v24
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_remote_service import ManagementRemoteServiceService
from drlink_v30_jobs import ManagementJobEngine, QUEUED


class V30RemoteServiceManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-rs-management-")
        plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(plane.conn)
        v24.set_service_object(plane, "ssh", type="tcp", port=22, oneshot=True)
        plane.upsert_client("host-a", label="alpha", hostname="alpha.example")
        plane.close()

    def test_preview_zero_mutation_and_apply_only_queues_target_bound_job(self):
        service = ManagementRemoteServiceService(self.tmp)
        try:
            before = service.plane.current_revision()
            preview = service.preview(
                actor_id="web:operator",
                owner="host-a",
                name="ssh-access",
                operation="set",
                destination="this-host",
                service="ssh",
                enabled=True,
            )
            self.assertEqual(service.plane.current_revision(), before)
            self.assertEqual(preview["owner"]["id"], "host-a")
            self.assertEqual(preview["owner"]["connectivity"], "connected")
            self.assertTrue(preview["change_plan_id"].startswith("cp_"))

            queued = service.apply(
                actor_id="web:operator",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
            self.assertEqual(queued["status"], "QUEUED")
            self.assertEqual(service.plane.current_revision(), before)
            self.assertIsNone(
                service.plane.conn.execute(
                    "SELECT id FROM published_services WHERE name='ssh-access'"
                ).fetchone()
            )
        finally:
            service.close()

        engine = ManagementJobEngine(self.tmp)
        try:
            job = engine.get(queued["job_id"])
            self.assertEqual(job["status"], QUEUED)
            self.assertEqual(job["targets"][0]["target_id"], "host-a")
            self.assertEqual(job["job_type"], "remote-service-set")
            self.assertEqual(job["payload"]["name"], "ssh-access")
        finally:
            engine.close()

    def test_disconnected_owner_never_queues_false_success(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.refresh_agent_lifecycle("host-a", "disconnected")
        finally:
            plane.close()
        service = ManagementRemoteServiceService(self.tmp)
        try:
            preview = service.preview(
                actor_id="web:operator",
                owner="host-a",
                name="ssh-access",
                operation="set",
                destination="this-host",
                service="ssh",
                enabled=True,
            )
            with self.assertRaisesRegex(ControlPlaneError, "disconnected"):
                service.apply(
                    actor_id="web:operator",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
        finally:
            service.close()
        engine = ManagementJobEngine(self.tmp)
        try:
            self.assertEqual(engine.summary()["active_jobs"], 0)
        finally:
            engine.close()

    def test_stale_revision_and_cross_actor_fail_closed(self):
        service = ManagementRemoteServiceService(self.tmp)
        try:
            preview = service.preview(
                actor_id="web:alice",
                owner="host-a",
                name="ssh-access",
                operation="set",
                destination="this-host",
                service="ssh",
                enabled=True,
            )
            with self.assertRaises(ControlPlaneError):
                service.apply(
                    actor_id="web:bob",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
            v24.set_network_object(
                service.plane,
                "revision-bump",
                type="ip",
                value="198.51.100.9",
                oneshot=True,
            )
            with self.assertRaises(ConcurrencyError):
                service.apply(
                    actor_id="web:alice",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
        finally:
            service.close()

    def test_delete_preview_is_destructive_and_queues_delete_job(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.set_published_service(
                "host-a",
                "old-service",
                service_type="tcp",
                target_mode="self",
                target_host="127.0.0.1",
                target_port=22,
                enabled=True,
                public_port=25001,
            )
        finally:
            plane.close()
        service = ManagementRemoteServiceService(self.tmp)
        try:
            preview = service.preview(
                actor_id="web:admin",
                owner="host-a",
                name="old-service",
                operation="delete",
            )
            self.assertTrue(preview["impact"]["destructive"])
            queued = service.apply(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
            self.assertEqual(queued["operation"], "delete")
        finally:
            service.close()
        engine = ManagementJobEngine(self.tmp)
        try:
            self.assertEqual(engine.get(queued["job_id"])["job_type"], "remote-service-delete")
        finally:
            engine.close()

    def test_change_plan_payload_cannot_change_approved_operation_or_target(self):
        service = ManagementRemoteServiceService(self.tmp)
        try:
            for field, changed_value in (
                ("operation", "delete"),
                ("name", "unapproved-target"),
            ):
                with self.subTest(field=field):
                    preview = service.preview(
                        actor_id="web:operator",
                        owner="host-a",
                        name="ssh-access",
                        operation="set",
                        destination="this-host",
                        service="ssh",
                        enabled=True,
                    )
                    plan = service.plane.conn.execute(
                        "SELECT token_hash,payload_json FROM management_change_plans "
                        "WHERE operation='remote-service.set' AND status='pending' "
                        "ORDER BY created_at DESC,rowid DESC LIMIT 1"
                    ).fetchone()
                    payload = json.loads(str(plan["payload_json"]))
                    payload[field] = changed_value
                    service.plane.conn.execute(
                        "UPDATE management_change_plans SET payload_json=? WHERE token_hash=?",
                        (json.dumps(payload), str(plan["token_hash"])),
                    )
                    with self.assertRaisesRegex(ControlPlaneError, "binding"):
                        service.apply(
                            actor_id="web:operator",
                            change_plan_id=preview["change_plan_id"],
                            confirmation="APPLY",
                        )
        finally:
            service.close()
        engine = ManagementJobEngine(self.tmp)
        try:
            self.assertEqual(engine.summary()["active_jobs"], 0)
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
