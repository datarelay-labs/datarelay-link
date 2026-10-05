#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_v24 as v24
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_core import (
    ManagementActor,
    ManagementAuthorizationError,
    ManagementCoreService,
    SURFACE_MCP,
    SURFACE_WEB,
)
from drlink_management_guided import GuidedChangeService
from drlink_web_auth import (
    ROLE_OPERATOR,
    ROLE_READ_ONLY,
    permissions_for_role,
)


class V30GuidedChangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-guided-")
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        plane = ControlPlane(self.tmp)
        plane.close()

    def tearDown(self):
        os.environ.pop("DRLINK_SKIP_ACTIVATION", None)

    def test_preview_is_zero_mutation_and_apply_creates_one_revision(self):
        with GuidedChangeService(self.tmp) as service:
            before = service.plane.current_revision()
            preview = service.preview_guided_change(
                actor_id="web:operator",
                change_type="network-object",
                payload={
                    "operation": "set",
                    "name": "office",
                    "type": "ip",
                    "value": "198.51.100.10",
                },
            )
            self.assertEqual(service.plane.current_revision(), before)
            self.assertIsNone(service.plane.get_object("office"))
            self.assertFalse(preview["no_change"])
            result = service.apply_guided_change(
                actor_id="web:operator",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
            self.assertEqual(result["status"], "APPLIED")
            self.assertEqual(result["revision"], before + 1)
            self.assertIsNotNone(service.plane.get_object("office"))

    def test_stale_revision_fails_without_target_mutation(self):
        with GuidedChangeService(self.tmp) as service:
            preview = service.preview_guided_change(
                actor_id="web:operator",
                change_type="network-object",
                payload={
                    "name": "target",
                    "type": "ip",
                    "value": "198.51.100.20",
                },
            )
            v24.set_network_object(
                service.plane,
                "other",
                type="ip",
                value="198.51.100.30",
                oneshot=True,
            )
            with self.assertRaises(ConcurrencyError):
                service.apply_guided_change(
                    actor_id="web:operator",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
            self.assertIsNone(service.plane.get_object("target"))

    def test_change_plan_is_actor_bound_and_single_use(self):
        with GuidedChangeService(self.tmp) as service:
            preview = service.preview_guided_change(
                actor_id="web:operator-a",
                change_type="service-object",
                payload={"name": "https", "type": "tcp", "port": 443},
            )
            with self.assertRaises(ControlPlaneError):
                service.apply_guided_change(
                    actor_id="web:operator-b",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
            service.apply_guided_change(
                actor_id="web:operator-a",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
            with self.assertRaises(ControlPlaneError):
                service.apply_guided_change(
                    actor_id="web:operator-a",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )

    def test_managed_host_metadata_is_atomic_single_revision(self):
        plane = ControlPlane(self.tmp)
        try:
            now = "2026-10-04T03:00:00Z"
            plane.conn.execute(
                "INSERT INTO clients("
                "id,label,hostname,status,trust_status,connected,last_seen,"
                "agent_heartbeat_at,agent_lifecycle_state,row_version,created_at,updated_at"
                ") VALUES ("
                "'host-a','host-a','host-a.example','active','trusted',1,NULL,?,"
                "'connected',1,?,?)",
                (now, now, now),
            )
        finally:
            plane.close()

        with GuidedChangeService(self.tmp) as service:
            before = service.plane.current_revision()
            preview = service.preview_guided_change(
                actor_id="web:operator",
                change_type="managed-host-metadata",
                payload={
                    "host": "host-a",
                    "label": "alpha-host",
                    "description": "managed from guided Core",
                    "tags": {"site": "lab", "owner": "secops"},
                },
            )
            row = service.plane.require_client("host-a")
            self.assertEqual(row["label"], "host-a")
            self.assertEqual(service.plane.current_revision(), before)
            applied = service.apply_guided_change(
                actor_id="web:operator",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
            self.assertEqual(applied["revision"], before + 1)
            row = service.plane.require_client("host-a")
            self.assertEqual(row["label"], "alpha-host")
            self.assertEqual(row["description"], "managed from guided Core")
            tags = {
                r["key"]: r["value"]
                for r in service.plane.conn.execute(
                    "SELECT key,value FROM client_tags WHERE client_id='host-a'"
                )
            }
            self.assertEqual(tags, {"site": "lab", "owner": "secops"})

    def test_group_preview_reuses_core_reference_validation(self):
        with GuidedChangeService(self.tmp) as service:
            with self.assertRaises(ControlPlaneError):
                service.preview_guided_change(
                    actor_id="web:operator",
                    change_type="network-group",
                    payload={"name": "missing-members", "members": ["does-not-exist"]},
                )
            self.assertIsNone(service.plane.get_object_group("missing-members"))

    def test_referenced_object_update_surfaces_security_impact(self):
        plane = ControlPlane(self.tmp)
        try:
            v24.set_network_object(
                plane, "src", type="ip", value="198.51.100.10", oneshot=True
            )
            v24.set_network_object(
                plane, "dst", type="ip", value="198.51.100.20", oneshot=True
            )
            v24.set_service_object(
                plane, "ssh", type="tcp", port=22, oneshot=True
            )
            v24.set_access_rule(
                plane,
                "remote",
                "allow-ssh",
                mode="whitelist",
                source="src",
                destination="dst",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
        finally:
            plane.close()

        with GuidedChangeService(self.tmp) as service:
            preview = service.preview_guided_change(
                actor_id="web:operator",
                change_type="network-object",
                payload={
                    "name": "src",
                    "type": "ip",
                    "value": "198.51.100.11",
                },
            )
            impact = preview["impact"]
            self.assertTrue(
                impact.get("access_broadened")
                or impact.get("access_narrowed")
                or impact.get("requires_confirmation")
            )
            self.assertEqual(
                service.plane._object_values(service.plane.get_object("src")["id"]),
                ["198.51.100.10"],
            )

    def test_web_operator_allowed_read_only_and_mcp_blocked(self):
        core = ManagementCoreService(self.tmp)
        operator = ManagementActor.authenticated(
            "web:operator", permissions_for_role(ROLE_OPERATOR)
        )
        read_only = ManagementActor.authenticated(
            "web:reader", permissions_for_role(ROLE_READ_ONLY)
        )
        preview = core.invoke(
            name="drlink_guided_change_preview",
            arguments={
                "change_type": "permission-object",
                "payload": {
                    "name": "read-info",
                    "permissions": ["host-info"],
                },
            },
            actor=operator,
            surface=SURFACE_WEB,
        )
        self.assertTrue(preview["change_plan_id"].startswith("cp_"))
        with self.assertRaises(ManagementAuthorizationError):
            core.invoke(
                name="drlink_guided_change_preview",
                arguments={
                    "change_type": "permission-object",
                    "payload": {
                        "name": "reader-denied",
                        "permissions": ["host-info"],
                    },
                },
                actor=read_only,
                surface=SURFACE_WEB,
            )
        with self.assertRaises(ManagementAuthorizationError):
            core.invoke(
                name="drlink_guided_change_preview",
                arguments={
                    "change_type": "permission-object",
                    "payload": {
                        "name": "mcp-denied",
                        "permissions": ["host-info"],
                    },
                },
                actor=operator,
                surface=SURFACE_MCP,
            )
        self.assertNotIn(
            "drlink_guided_change_preview",
            core.advertised_tool_names(actor=operator, surface=SURFACE_MCP),
        )

    def test_delete_preview_is_zero_mutation_and_requires_confirmation(self):
        plane = ControlPlane(self.tmp)
        try:
            v24.set_service_object(
                plane, "temp", type="tcp", port=8443, oneshot=True
            )
        finally:
            plane.close()
        with GuidedChangeService(self.tmp) as service:
            preview = service.preview_guided_change(
                actor_id="web:operator",
                change_type="service-object",
                payload={"operation": "delete", "name": "temp"},
            )
            self.assertTrue(preview["impact"]["destructive"])
            self.assertIsNotNone(v24.get_service_object(service.plane, "temp"))
            with self.assertRaises(ControlPlaneError):
                service.apply_guided_change(
                    actor_id="web:operator",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="NO",
                )


if __name__ == "__main__":
    unittest.main()
