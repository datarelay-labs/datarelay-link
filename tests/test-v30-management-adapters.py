#!/usr/bin/env python3
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_automation_api import AutomationApi
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from drlink_management_catalog import MANAGEMENT_PERMISSION_NAMES, PLUGIN_NO, management_tool
from drlink_management_core import (
    ManagementActor,
    ManagementAuthorizationError,
    implemented_management_tool_names,
)
from drlink_management_mcp_adapter import ManagementMcpAdapter
from drlink_management_web_adapter import ManagementWebApiAdapter, WEB_API_NAMESPACE
import drlink_v24 as v24


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


def _future(hours: int = 2) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class V30ManagementAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-adapters-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        plane = ControlPlane(self.tmp)
        try:
            plane.upsert_client("host-a", label="alpha", hostname="alpha.example")
            v24.set_network_object(
                plane, "src", type="ip", value="198.51.100.10", oneshot=True
            )
            v24.set_network_object(
                plane, "dst", type="ip", value="198.51.100.20", oneshot=True
            )
            v24.set_service_object(plane, "ssh", type="tcp", port=22, oneshot=True)
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
            plane.set_ai_principal("bot", enabled=True)
            plane.conn.execute(
                "UPDATE ai_principals SET credential_status='verified' WHERE name='bot'"
            )
            v24.set_permission_object(
                plane, "mgmt-read", permissions=["management-read"], oneshot=True
            )
            v24.set_ai_access_rule(
                plane,
                "allow-mgmt-read",
                mode="whitelist",
                source="bot",
                destination="dst",
                permission="mgmt-read",
                enabled=True,
                oneshot=True,
            )
        finally:
            plane.close()
        os.environ.pop("DRLINK_CONFIRM", None)
        self.actor = ManagementActor.authenticated(
            "operator:shared", MANAGEMENT_PERMISSION_NAMES
        )
        self.mcp = ManagementMcpAdapter(self.tmp)
        self.web = ManagementWebApiAdapter(self.tmp)

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_CONFIRM", None)

    def test_advertisement_is_catalog_driven_and_contract_only_tools_stay_hidden(self):
        ready = set(implemented_management_tool_names())
        mcp_expected = {
            name
            for name in ready
            if management_tool(name) is not None
            and management_tool(name).plugin_exposure != PLUGIN_NO
        }
        mcp_names = {item["name"] for item in self.mcp.list_tools(actor=self.actor)}
        web_names = set(self.web.capability_names(actor=self.actor))
        self.assertEqual(mcp_names, mcp_expected)
        self.assertEqual(web_names, ready)
        self.assertNotIn(
            "drlink_agent_update_rollout_start", web_names,
            "Unqualified Agent Rollout Apply must not be advertised as ready",
        )
        self.assertNotIn("drlink_guided_change_preview", mcp_names)
        self.assertIn("drlink_guided_change_preview", web_names)
        self.assertIn("drlink_diagnose_connection", ready)
        self.assertIn("drlink_diagnostic_job_start", ready)
        self.assertIn("drlink_diagnostic_job_start", mcp_names)
        self.assertIn("drlink_diagnostic_job_start", web_names)

        mcp_source = inspect.getsource(
            __import__("drlink_management_mcp_adapter")
        )
        self.assertNotIn("drlink_management_web_adapter", mcp_source)
        self.assertNotIn("ManagementWebApiAdapter", mcp_source)
        self.assertEqual(WEB_API_NAMESPACE, "/api/v1")

    def test_management_permissions_are_ai_access_authorized_but_not_target_capabilities(self):
        self.assertNotIn("management-read", v24.PERMISSIONS)
        self.assertNotIn("management-read", set(v24.CAP_TO_PERMISSION.values()))
        actor = self.mcp.actor_from_ai_access(identity="bot", destination="dst")
        self.assertEqual(actor.permissions, frozenset({"management-read"}))
        names = {item["name"] for item in self.mcp.list_tools(actor=actor)}
        self.assertIn("drlink_inventory_list", names)
        self.assertIn("drlink_live_access", names)
        self.assertNotIn("drlink_policy_test", names)
        self.assertNotIn("drlink_temporary_access_apply", names)

    def test_permission_and_schema_checks_are_shared_core_boundary(self):
        read_actor = ManagementActor.authenticated("reader", {"management-read"})
        names = {item["name"] for item in self.mcp.list_tools(actor=read_actor)}
        self.assertIn("drlink_inventory_list", names)
        self.assertNotIn("drlink_temporary_access_preview", names)

        with self.assertRaises(ManagementAuthorizationError):
            self.mcp.call_tool(
                name="drlink_temporary_access_preview",
                arguments={
                    "plane": "remote",
                    "rule": "allow-ssh",
                    "operation": "set",
                    "expires_at": _future(),
                },
                actor=read_actor,
            )
        with self.assertRaises(ControlPlaneError):
            self.web.invoke(
                operation="drlink_inventory_list",
                payload={"query": "alpha"},
                actor=self.actor,
            )
        with self.assertRaises(ControlPlaneError):
            self.mcp.call_tool(
                name="drlink_inventory_list",
                arguments={"resource_type": "managed-host", "unexpected": "x"},
                actor=self.actor,
            )
        with self.assertRaises(ManagementAuthorizationError):
            self.mcp.call_tool(
                name="drlink_diagnostic_job_start",
                arguments={"job_type": "doctor"},
                actor=read_actor,
            )
        with self.assertRaises(ControlPlaneError):
            self.mcp.call_tool(
                name="drlink_diagnostic_job_start",
                arguments={"job_type": "remote-service-delete"},
                actor=self.actor,
            )

    def test_rollout_pause_resume_cancel_need_update_permission_not_only_job_run(self):
        from drlink_v30_jobs import ManagementJobEngine

        with ManagementJobEngine(self.tmp) as engine:
            rollout = engine.enqueue_rollout(
                targets=("host-a",), requested_by="admin",
                artifact={"version":"3.0.0-rc.1","source_ref":"a"*40,"sha256":"b"*64},
                wave_size=1,
            )
            ordinary = engine.enqueue(
                targets=("host-a",), job_type="doctor", requested_by="operator",
            )

        limited = ManagementActor.authenticated(
            "web:limited", {"management-job-run"}, role="Admin",
        )
        unauthorized_role = ManagementActor.authenticated(
            "web:operator", {"management-job-run", "management-update"}, role="Operator",
        )
        authorized = ManagementActor.authenticated(
            "web:admin", {"management-job-run", "management-update"}, role="Admin",
        )
        for actor in (limited, unauthorized_role):
            with self.subTest(actor=actor.actor_id):
                with self.assertRaises(ManagementAuthorizationError):
                    self.web.rollout_control(
                        rollout["id"], actor=actor, action="pause",
                    )
                with self.assertRaises(ManagementAuthorizationError):
                    self.web.job_cancel(rollout["id"], actor=actor)

        # Ordinary diagnostics remain cancellable by the original Operator.
        self.assertEqual(
            self.web.job_cancel(ordinary["id"], actor=limited)["status"], "CANCELLED"
        )
        paused = self.web.rollout_control(
            rollout["id"], actor=authorized, action="pause",
        )
        self.assertTrue(paused["payload"]["operator_paused"])
        resumed = self.web.rollout_control(
            rollout["id"], actor=authorized, action="resume",
        )
        self.assertFalse(resumed["payload"]["operator_paused"])
        cancelled = self.web.job_cancel(rollout["id"], actor=authorized)
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_web_and_mcp_read_projection_return_same_core_semantics(self):
        args = {"resource_type": "managed-host", "query": "alpha", "limit": 10}
        via_mcp = self.mcp.call_tool(
            name="drlink_inventory_list", arguments=args, actor=self.actor
        )
        via_web = self.web.invoke(
            operation="drlink_inventory_list", payload=args, actor=self.actor
        )
        self.assertEqual(via_mcp, via_web)
        self.assertEqual(via_mcp["resource_type"], "managed-host")
        self.assertEqual(via_mcp["items"][0]["id"], "host-a")

        live_mcp = self.mcp.call_tool(
            name="drlink_live_access",
            arguments={"plane": "remote"},
            actor=self.actor,
        )
        live_web = self.web.invoke(
            operation="drlink_live_access",
            payload={"plane": "remote"},
            actor=self.actor,
        )
        self.assertEqual(live_mcp, live_web)
        self.assertEqual(live_mcp["fidelity"], "UNKNOWN")

        diagnosis_args = {
            "plane": "remote",
            "source": "src",
            "destination": "dst",
            "service": "ssh",
        }
        diagnosis_mcp = self.mcp.call_tool(
            name="drlink_diagnose_connection",
            arguments=diagnosis_args,
            actor=self.actor,
        )
        diagnosis_web = self.web.invoke(
            operation="drlink_diagnose_connection",
            payload=diagnosis_args,
            actor=self.actor,
        )
        self.assertEqual(diagnosis_mcp, diagnosis_web)
        self.assertTrue(diagnosis_mcp["side_effect_free"])
        self.assertFalse(diagnosis_mcp["network_probe_performed"])

    def test_service_account_can_preview_but_cannot_apply_temporary_access(self):
        # Real Core rule state: the Automation projection may issue only an
        # actor-scoped Change Plan. It cannot reuse Web/MCP apply authority.
        plane = ControlPlane(self.tmp)
        try:
            revision_before = plane.current_revision()
            rule_before = plane.conn.execute(
                "SELECT expires_at FROM policy_rules WHERE plane='remote' "
                "AND name='allow-ssh'"
            ).fetchone()["expires_at"]
        finally:
            plane.close()
        with AutomationApi(self.tmp) as automation:
            limited = automation.accounts.create(
                "ci-reader", ["management-read"]
            )["credential"]
            owner = automation.accounts.create(
                "ci-temporary-owner", ["management-temporary-access"]
            )
            other = automation.accounts.create(
                "ci-temporary-other", ["management-temporary-access"]
            )
            route = "/api/automation/v1/drlink_temporary_access_preview"
            args = {
                "plane": "remote", "rule": "allow-ssh",
                "operation": "set", "expires_at": _future(),
            }
            with self.assertRaises(ControlPlaneError):
                automation.invoke(route, limited, args)
            preview = automation.invoke(route, owner["credential"], args)
            self.assertTrue(preview["change_plan_id"].startswith("cp_"))
            self.assertEqual(preview["expected_revision"], revision_before)
            self.assertEqual(preview["resource_ref"], "allow-ssh")
            with self.assertRaises(ControlPlaneError):
                automation.invoke(
                    "/api/automation/v1/drlink_temporary_access_apply",
                    owner["credential"],
                    {"change_plan_id": preview["change_plan_id"],
                     "confirmation": "APPLY"},
                )
            with self.assertRaises(ControlPlaneError):
                self.web.invoke(
                    operation="drlink_temporary_access_apply",
                    payload={"change_plan_id": preview["change_plan_id"],
                             "confirmation": "APPLY"},
                    actor=ManagementActor.authenticated(
                        other["id"], {"management-temporary-access"}
                    ),
                )
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), revision_before)
            rule_after = plane.conn.execute(
                "SELECT expires_at FROM policy_rules WHERE plane='remote' "
                "AND name='allow-ssh'"
            ).fetchone()["expires_at"]
            self.assertEqual(rule_after, rule_before)
        finally:
            plane.close()

    def test_change_plan_can_cross_adapters_without_semantic_fork(self):
        expiry = _future()
        preview = self.mcp.call_tool(
            name="drlink_temporary_access_preview",
            arguments={
                "plane": "remote",
                "rule": "allow-ssh",
                "operation": "set",
                "expires_at": expiry,
            },
            actor=self.actor,
        )
        result = self.web.invoke(
            operation="drlink_temporary_access_apply",
            payload={
                "change_plan_id": preview["change_plan_id"],
                "confirmation": "APPLY",
            },
            actor=self.actor,
        )
        self.assertEqual(result["status"], "APPLIED")
        plane = ControlPlane(self.tmp)
        try:
            row = plane.conn.execute(
                "SELECT expires_at FROM policy_rules WHERE plane='remote' AND name='allow-ssh'"
            ).fetchone()
            self.assertEqual(row["expires_at"], expiry)
        finally:
            plane.close()

    def test_emergency_apply_and_clear_tools_bind_to_plan_operation(self):
        apply_plan = self.mcp.call_tool(
            name="drlink_emergency_cutoff_preview",
            arguments={
                "plane": "remote",
                "scope_kind": "plane",
                "scope_ref": "",
                "operation": "apply",
                "reason": "adapter-test",
            },
            actor=self.actor,
        )
        with self.assertRaises(ControlPlaneError):
            self.web.invoke(
                operation="drlink_emergency_cutoff_clear",
                payload={
                    "change_plan_id": apply_plan["change_plan_id"],
                    "confirmation": "CONFIRM CUTOFF",
                },
                actor=self.actor,
            )
        applied = self.web.invoke(
            operation="drlink_emergency_cutoff_apply",
            payload={
                "change_plan_id": apply_plan["change_plan_id"],
                "confirmation": "CONFIRM CUTOFF",
            },
            actor=self.actor,
        )
        self.assertTrue(applied["active"])

        clear_plan = self.web.invoke(
            operation="drlink_emergency_cutoff_preview",
            payload={
                "plane": "remote",
                "scope_kind": "plane",
                "scope_ref": "",
                "operation": "clear",
            },
            actor=self.actor,
        )
        cleared = self.mcp.call_tool(
            name="drlink_emergency_cutoff_clear",
            arguments={
                "change_plan_id": clear_plan["change_plan_id"],
                "confirmation": "CONFIRM CUTOFF",
            },
            actor=self.actor,
        )
        self.assertFalse(cleared["active"])


if __name__ == "__main__":
    unittest.main()
