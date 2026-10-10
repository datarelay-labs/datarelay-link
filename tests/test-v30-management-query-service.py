#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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

    def test_cursor_shapes_are_fail_closed_across_read_surfaces(self):
        invalid = base64.urlsafe_b64encode(json.dumps([]).encode()).decode().rstrip("=")
        methods = (
            ("inventory", lambda c: self.service.list_inventory("managed-host", cursor=c)),
            ("audit", lambda c: self.service.audit_query(cursor=c)),
            ("jobs", lambda c: self.service.job_list(cursor=c)),
            ("live", lambda c: self.service.live_access(plane="remote", cursor=c)),
            ("revisions", lambda c: self.service.revision_list(cursor=c)),
        )
        for name, invoke in methods:
            with self.subTest(surface=name, case="non-object"):
                with self.assertRaises(ControlPlaneError):
                    invoke(invalid)
            with self.subTest(surface=name, case="oversized-before-base64"):
                with patch("drlink_management_service.base64.urlsafe_b64decode") as decode:
                    with self.assertRaises(ControlPlaneError):
                        invoke("A" * 8192)
                    decode.assert_not_called()

    def test_invalid_job_cursor_is_rejected_before_deadline_reconciliation(self):
        with patch.object(self.service, "_reconcile_management_job_deadlines") as reconcile:
            with self.assertRaises(ControlPlaneError):
                self.service.job_list(cursor="not-a-valid-cursor")
            reconcile.assert_not_called()

    def test_numeric_cursor_keys_reject_bool_or_text_and_non_string_inputs(self):
        def encoded(payload):
            return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

        for row_id in (True, False, "1", 1.5, None):
            with self.subTest(surface="audit", row_id=repr(row_id)):
                with self.assertRaises(ControlPlaneError):
                    self.service.audit_query(cursor=encoded({
                        "v": 1, "resource": "audit", "time": "2026-10-10T00:00:00Z",
                        "id": row_id,
                    }))
            with self.subTest(surface="revision", row_id=repr(row_id)):
                with self.assertRaises(ControlPlaneError):
                    self.service.revision_list(cursor=encoded({
                        "v": 1, "resource": "revision", "revision": row_id,
                    }))
        for invalid in (True, 0, b"abc", [], {}):
            with self.subTest(case="invalid-cursor-input-type", input=repr(invalid)):
                with self.assertRaises(ControlPlaneError):
                    self.service.list_inventory("managed-host", cursor=invalid)

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

    def test_limit_rejects_boolean_fractional_and_text_coercion(self):
        for raw in (True, False, 1.5, "10", b"10"):
            with self.subTest(limit=repr(raw)):
                with self.assertRaises(ControlPlaneError):
                    self.service.list_inventory("managed-host", limit=raw)

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
            published = plane.conn.execute(
                "SELECT id FROM published_services WHERE client_id='client-a' "
                "AND name='ssh-admin'"
            ).fetchone()
            plane.conn.execute(
                "INSERT OR REPLACE INTO remote_service_meta("
                "service_id,status,pool_class,pending_allocation,delete_pending,"
                "reason,runtime_verified"
                ") VALUES (?,'HEALTHY','normal',0,0,'',1)",
                (published["id"],),
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
        self.assertEqual(by_layer["target_reachability"]["status"], "HEALTHY")
        self.assertEqual(by_layer["recent_activity"]["status"], "UNKNOWN")
        self.assertFalse(diagnosis["network_probe_performed"])
        self.assertTrue(diagnosis["side_effect_free"])
        self.assertEqual(diagnosis["overall"], "UNKNOWN")

        check = ControlPlane(self.tmp, read_only=True)
        try:
            self.assertEqual(check.current_revision(), expected_revision)
        finally:
            check.close()

    def test_remote_service_degraded_runtime_is_failed_without_probe(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.set_published_service(
                "client-a",
                "ssh-degraded",
                service_type="ssh",
                target_mode="self",
                target_port=22,
                public_port=6002,
                enabled=True,
            )
            published = plane.conn.execute(
                "SELECT id FROM published_services WHERE client_id='client-a' "
                "AND name='ssh-degraded'"
            ).fetchone()
            plane.conn.execute(
                "INSERT OR REPLACE INTO remote_service_meta("
                "service_id,status,pool_class,pending_allocation,delete_pending,"
                "reason,runtime_verified"
                ") VALUES (?,'DEGRADED','normal',0,0,'target refused connection',0)",
                (published["id"],),
            )
            v24.set_access_rule(
                plane,
                "remote",
                "allow-alpha-ssh-degraded",
                mode="whitelist",
                source="src",
                destination="alpha",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
        finally:
            plane.close()

        diagnosis = self.service.connection_diagnosis(
            plane="remote",
            source="src",
            destination="alpha",
            service="ssh-degraded",
        )
        by_layer = {item["layer"]: item for item in diagnosis["layers"]}
        self.assertEqual(by_layer["remote_service"]["status"], "FAILED")
        self.assertEqual(by_layer["target_reachability"]["status"], "FAILED")
        self.assertIn("target refused", by_layer["target_reachability"]["summary"])
        self.assertFalse(diagnosis["network_probe_performed"])
        self.assertEqual(diagnosis["overall"], "FAILED")

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

    def test_attention_center_derives_required_local_signals_without_spool_creation(self):
        from drlink_control_db import utc_now_iso
        from drlink_v30_audit import default_access_spool_root

        remote_spool = default_access_spool_root("remote", self.tmp)
        internet_spool = default_access_spool_root("internet", self.tmp)
        self.assertFalse(remote_spool.exists())
        self.assertFalse(internet_spool.exists())

        plane = ControlPlane(self.tmp)
        try:
            plane.set_published_service(
                "client-a",
                "attention-ssh",
                service_type="ssh",
                target_mode="self",
                target_port=22,
                public_port=6003,
                enabled=True,
            )
            published = plane.conn.execute(
                "SELECT id FROM published_services WHERE client_id='client-a' "
                "AND name='attention-ssh'"
            ).fetchone()
            plane.conn.execute(
                "INSERT OR REPLACE INTO remote_service_meta("
                "service_id,status,pool_class,pending_allocation,delete_pending,"
                "reason,runtime_verified"
                ") VALUES (?,'DEGRADED','normal',0,0,'runtime degraded',0)",
                (published["id"],),
            )
            current = plane.current_revision()
            plane.conn.execute(
                "INSERT OR REPLACE INTO runtime_generations"
                "(plane,db_revision,generation,status,artifact_path,activated_at,error) "
                "VALUES ('internet',?,?, 'active','',?,NULL)",
                (current, max(current - 1, 0), utc_now_iso()),
            )
            expiry = (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            plane.conn.execute(
                "UPDATE policy_rules SET expires_at=? "
                "WHERE plane='remote' AND name='allow-ssh'",
                (expiry,),
            )
            occurred = datetime.now(timezone.utc).replace(
                microsecond=0
            ).isoformat().replace("+00:00", "Z")
            for index in range(3):
                plane.conn.execute(
                    "INSERT INTO audit_events("
                    "timestamp,revision,actor,action,entity_type,entity_id,operation,"
                    "result,category,occurred_at,source"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        occurred,
                        None,
                        "runtime",
                        "authorize",
                        "access",
                        "deny-%s" % index,
                        "authorize",
                        "DENY",
                        "ACCESS_DECISION",
                        occurred,
                        "remote-access",
                    ),
                )
        finally:
            plane.close()

        attention = self.service.attention_summary()
        kinds = {item["kind"] for item in attention["items"]}
        self.assertIn("degraded-remote-services", kinds)
        self.assertIn("runtime-mismatch", kinds)
        self.assertIn("repeated-policy-denies", kinds)
        self.assertIn("temporary-access-expiring", kinds)
        self.assertEqual(
            attention["signals"]["denies"]["threshold"], 3
        )
        self.assertEqual(
            attention["signals"]["temporary_access"]["expiring_count"], 1
        )
        self.assertFalse(remote_spool.exists())
        self.assertFalse(internet_spool.exists())
        self.assertFalse(attention["authoritative"])

    def test_attention_reports_existing_audit_spool_degradation_read_only(self):
        from drlink_v30_audit import default_access_spool_root

        spool_root = default_access_spool_root("remote", self.tmp)
        spool_root.mkdir(parents=True, exist_ok=True)
        state_path = spool_root / "state.json"
        state_path.write_text(
            '{"next_sequence":2,"enqueue_failures":1,'
            '"dropped_deny_count":0,"last_error_at":"2026-10-05T00:00:00Z"}\n',
            encoding="utf-8",
        )
        before = state_path.read_bytes()
        attention = self.service.attention_summary()
        item = next(
            row for row in attention["items"] if row["kind"] == "audit-spool"
        )
        self.assertEqual(item["severity"], "critical")
        self.assertEqual(
            attention["signals"]["audit_spool"]["degraded_count"], 1
        )
        self.assertEqual(state_path.read_bytes(), before)

    def test_management_job_target_resolution_is_bounded_and_stable(self):
        one = self.service.resolve_management_job_targets(
            resource_type="managed-host",
            resource="alpha",
        )
        self.assertEqual(one["targets"], ["client-a"])
        self.assertEqual(one["target_count"], 1)
        self.assertEqual(one["resource_ref"], "client-a")

        all_hosts = self.service.resolve_management_job_targets(
            resource_type="managed-host",
            resource="",
        )
        self.assertEqual(
            set(all_hosts["targets"]), {"client-a", "client-b", "client-c"}
        )
        self.assertEqual(all_hosts["target_count"], 3)
        self.assertEqual(all_hosts["resource_ref"], "all")

    def test_management_job_target_resolution_supports_managed_host_group(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.set_client_group("ops")
            plane.set_client_group_member("ops", "client-a")
            plane.set_client_group_member("ops", "client-c")
        finally:
            plane.close()
        grouped = self.service.resolve_management_job_targets(
            resource_type="managed-host-group",
            resource="ops",
        )
        self.assertEqual(set(grouped["targets"]), {"client-a", "client-c"})
        self.assertEqual(grouped["target_count"], 2)
        self.assertEqual(grouped["resource_display"], "ops")

    def test_management_job_target_resolution_rejects_untrusted_host(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.conn.execute(
                "UPDATE clients SET trust_status='revoked' WHERE id='client-b'"
            )
        finally:
            plane.close()
        with self.assertRaisesRegex(ControlPlaneError, "not trusted"):
            self.service.resolve_management_job_targets(
                resource_type="managed-host",
                resource="Beta",
            )

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
                "drlink_access_hygiene",
            },
        )


if __name__ == "__main__":
    unittest.main()
