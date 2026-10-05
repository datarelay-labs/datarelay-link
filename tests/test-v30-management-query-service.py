#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from drlink_management_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ManagementQueryService,
    supported_inventory_types,
)
import drlink_v24 as v24


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class V30ManagementQueryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-mgmt-query-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        plane = ControlPlane(self.tmp)
        plane.upsert_client("client-a", label="alpha", hostname="alpha.local", connected=True)
        plane.upsert_client("client-b", label="Beta", hostname="beta.local", connected=False)
        plane.upsert_client("client-c", label="gamma", hostname="gamma.local", connected=True)
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
        # Managed Host projection must not leak into Network Object inventory.
        now = __import__("drlink_control_db").utc_now_iso()
        plane.conn.execute(
            "INSERT INTO objects"
            "(id,name,type,origin,description,status,orphan_reason,row_version,created_at,updated_at) "
            "VALUES ('obj-managed','managed-projection','managed_endpoint','managed','','active',NULL,1,?,?)",
            (now, now),
        )
        self.revision_before = plane.current_revision()
        plane.close()
        self.service = ManagementQueryService.open_read_only(self.tmp)

    def tearDown(self):
        self.service.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_CONFIRM", None)

    def test_supported_inventory_types_use_product_nouns(self):
        kinds = supported_inventory_types()
        self.assertIn("managed-host", kinds)
        self.assertIn("remote-service", kinds)
        self.assertIn("network-object", kinds)
        self.assertIn("ai-identity", kinds)
        self.assertNotIn("clients", kinds)
        self.assertNotIn("published_services", kinds)

    def test_inventory_is_bounded_and_cursor_paginated(self):
        page1 = self.service.list_inventory("managed-host", limit=2)
        self.assertEqual([x["name"] for x in page1.items], ["alpha", "Beta"])
        self.assertIsNotNone(page1.next_cursor)
        page2 = self.service.list_inventory(
            "managed-host", limit=2, cursor=page1.next_cursor
        )
        self.assertEqual([x["name"] for x in page2.items], ["gamma"])
        self.assertIsNone(page2.next_cursor)

    def test_search_is_case_insensitive_and_server_side(self):
        page = self.service.list_inventory("managed-host", query="BETA", limit=10)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0]["id"], "client-b")

    def test_cursor_cannot_cross_resource_type(self):
        page = self.service.list_inventory("managed-host", limit=1)
        with self.assertRaises(ControlPlaneError):
            self.service.list_inventory(
                "network-object", limit=1, cursor=page.next_cursor
            )

    def test_invalid_cursor_fails_closed(self):
        with self.assertRaises(ControlPlaneError):
            self.service.list_inventory("managed-host", cursor="not-a-real-cursor")

    def test_limit_defaults_caps_and_rejects_zero(self):
        self.assertEqual(
            self.service.list_inventory("managed-host").limit,
            DEFAULT_PAGE_SIZE,
        )
        self.assertEqual(
            self.service.list_inventory("managed-host", limit=99999).limit,
            MAX_PAGE_SIZE,
        )
        with self.assertRaises(ControlPlaneError):
            self.service.list_inventory("managed-host", limit=0)

    def test_get_inventory_supports_id_and_name(self):
        by_id = self.service.get_inventory("managed-host", "client-a")
        by_name = self.service.get_inventory("managed-host", "alpha")
        self.assertEqual(by_id["id"], "client-a")
        self.assertEqual(by_name["id"], "client-a")

    def test_network_object_inventory_excludes_managed_host_projection(self):
        page = self.service.list_inventory("network-object")
        names = {x["name"] for x in page.items}
        self.assertIn("src", names)
        self.assertIn("dst", names)
        self.assertNotIn("managed-projection", names)

    def test_health_is_read_only_and_reports_schema3(self):
        health = self.service.health()
        self.assertTrue(health["read_only"])
        self.assertEqual(health["schema"], 3)
        self.assertEqual(health["clients"], 3)

    def test_policy_test_delegates_to_same_core_evaluator(self):
        result = self.service.policy_test(
            plane="remote",
            source="src",
            destination="dst",
            service="ssh",
        )
        self.assertEqual(result["result"], "ALLOW")
        self.assertEqual(result["matched_rules"], ["allow-ssh"])

    def test_connection_diagnosis_correlates_core_facts_without_probes(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.set_published_service(
                "client-a",
                "ssh-admin",
                service_type="ssh",
                target_mode="self",
                target_port=22,
                public_port=6001,
                enabled=True,
            )
            v24.set_access_rule(
                plane,
                "remote",
                "allow-alpha-ssh",
                mode="whitelist",
                source="src",
                destination="alpha",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
            plane.conn.execute(
                "INSERT OR REPLACE INTO runtime_generations"
                "(plane,db_revision,generation,status,artifact_path,activated_at,error) "
                "VALUES ('remote',?,1,'active','',?,NULL)",
                (plane.current_revision(), __import__("drlink_control_db").utc_now_iso()),
            )
            expected_revision = plane.current_revision()
        finally:
            plane.close()

        diagnosis = self.service.connection_diagnosis(
            plane="remote",
            source="src",
            destination="alpha",
            service="ssh",
        )
        by_layer = {item["layer"]: item for item in diagnosis["layers"]}
        self.assertEqual(by_layer["policy"]["status"], "HEALTHY")
        self.assertEqual(by_layer["managed_host"]["status"], "HEALTHY")
        self.assertEqual(by_layer["remote_service"]["status"], "HEALTHY")
        self.assertEqual(by_layer["runtime"]["status"], "HEALTHY")
        self.assertEqual(by_layer["target_reachability"]["status"], "UNKNOWN")
        self.assertEqual(by_layer["recent_activity"]["status"], "UNKNOWN")
        self.assertFalse(diagnosis["network_probe_performed"])
        self.assertTrue(diagnosis["side_effect_free"])
        self.assertEqual(diagnosis["overall"], "UNKNOWN")

        check = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(check.current_revision(), expected_revision)
        finally:
            check.close()

    def test_internet_diagnosis_never_launches_live_dns(self):
        plane = ControlPlane(self.tmp)
        try:
            v24.set_network_object(
                plane,
                "internet-src",
                type="ip",
                value="198.51.100.60",
                oneshot=True,
            )
            v24.set_network_object(
                plane,
                "internet-dst",
                type="fqdn",
                value="updates.example.test",
                oneshot=True,
            )
            v24.set_service_object(
                plane,
                "https",
                type="tcp",
                port=443,
                oneshot=True,
            )
            v24.set_access_rule(
                plane,
                "internet",
                "allow-updates",
                mode="whitelist",
                source="internet-src",
                destination="internet-dst",
                service="https",
                enabled=True,
                oneshot=True,
            )
            revision = plane.current_revision()
        finally:
            plane.close()

        diagnosis = self.service.connection_diagnosis(
            plane="internet",
            source="internet-src",
            destination="internet-dst",
            service="https",
        )
        policy = next(item for item in diagnosis["layers"] if item["layer"] == "policy")
        dns = next(item for item in diagnosis["layers"] if item["layer"] == "dns")
        self.assertEqual(policy["status"], "UNKNOWN")
        self.assertEqual(dns["status"], "UNKNOWN")
        self.assertIn("live DNS", policy["summary"])
        self.assertFalse(diagnosis["network_probe_performed"])
        check = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(check.current_revision(), revision)
        finally:
            check.close()

    def test_ai_file_diagnosis_marks_missing_path_context_unknown(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.set_ai_principal("diag-bot", enabled=True)
            plane.conn.execute(
                "UPDATE ai_principals SET credential_status='verified' "
                "WHERE name='diag-bot'"
            )
            v24.set_permission_object(
                plane,
                "diag-file-read",
                permissions=["file-read"],
                oneshot=True,
            )
            v24.set_ai_access_rule(
                plane,
                "diag-file-rule",
                mode="whitelist",
                source="diag-bot",
                destination="alpha",
                permission="diag-file-read",
                paths=["/srv/**"],
                enabled=True,
                oneshot=True,
            )
        finally:
            plane.close()

        diagnosis = self.service.connection_diagnosis(
            plane="ai",
            source="diag-bot",
            destination="alpha",
            permission="diag-file-read",
        )
        policy = next(item for item in diagnosis["layers"] if item["layer"] == "policy")
        self.assertEqual(policy["status"], "UNKNOWN")
        self.assertTrue(policy["evidence"]["trace"]["path_required"])
        self.assertIn("path context", policy["summary"])
        self.assertFalse(diagnosis["network_probe_performed"])

    def test_cutoff_attention_and_diagnosis_reflect_active_override(self):
        plane = ControlPlane(self.tmp)
        try:
            now = __import__("drlink_control_db").utc_now_iso()
            plane.conn.execute(
                "INSERT INTO emergency_cutoffs("
                "id,plane,scope_kind,scope_ref,active,reason,row_version,created_at,updated_at"
                ") VALUES ('cut-test','remote','plane','',1,'incident',1,?,?)",
                (now, now),
            )
        finally:
            plane.close()

        attention = self.service.attention_summary()
        item = next(x for x in attention["items"] if x["kind"] == "emergency-cutoff")
        self.assertEqual(item["severity"], "critical")
        self.assertEqual(item["count"], 1)

        diagnosis = self.service.connection_diagnosis(
            plane="remote",
            source="src",
            destination="dst",
            service="ssh",
        )
        cutoff = next(x for x in diagnosis["layers"] if x["layer"] == "emergency_cutoff")
        self.assertEqual(cutoff["status"], "FAILED")
        self.assertFalse(cutoff["evidence"]["active_sessions_terminated"])
        self.assertEqual(diagnosis["overall"], "FAILED")

    def test_live_access_is_truthfully_unknown_until_adapter_exists(self):
        result = self.service.live_access(plane="remote", resource="alpha")
        self.assertEqual(result["fidelity"], "UNKNOWN")
        self.assertEqual(result["observations"], [])
        self.assertIn("official FRP", result["reason"])

    def test_read_side_is_query_only_and_does_not_advance_revision(self):
        with self.assertRaises(Exception):
            self.service.conn.execute("DELETE FROM clients")
        plane = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(plane.current_revision(), self.revision_before)
        finally:
            plane.close()

    def test_only_implemented_management_tools_are_ready(self):
        names = {d["name"] for d in self.service.ready_mcp_descriptors()}
        self.assertEqual(
            names,
            {
                "drlink_inventory_list",
                "drlink_inventory_get",
                "drlink_health",
                "drlink_diagnose_connection",
                "drlink_policy_test",
                "drlink_audit_query",
                "drlink_live_access",
                "drlink_job_list",
                "drlink_job_get",
            },
        )


if __name__ == "__main__":
    unittest.main()
