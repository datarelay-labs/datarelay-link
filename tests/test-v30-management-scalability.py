#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import open_control_db
from drlink_control_plane import ControlPlane
from drlink_management_catalog import MANAGEMENT_TOOLS
from drlink_management_core import ManagementCoreService, implemented_management_tool_names
from drlink_management_service import ManagementQueryService
from drlink_v30_capability import CORE_CONTRACT_ONLY, CORE_READY, capability_parity_ledger
from drlink_v30_jobs import ManagementJobEngine
from drlink_v30_readmodels import overview_summary


class V30ManagementScalabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-scale-")
        self.conn = open_control_db(self.tmp)
        self.now = datetime(2026, 10, 4, 2, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.conn.close()

    def _insert_client(
        self,
        ident: str,
        *,
        lifecycle: str = "connected",
        connected: int = 1,
        heartbeat: str | None = "2026-10-04T01:59:30Z",
        platform: str | None = "linux",
        version: str | None = "3.0.0",
    ):
        self.conn.execute(
            "INSERT INTO clients("
            "id,label,hostname,status,trust_status,connected,last_seen,agent_heartbeat_at,"
            "agent_lifecycle_state,agent_platform,agent_version,row_version,created_at,updated_at"
            ") VALUES (?,?,?,'active','trusted',?,NULL,?,?,?,?,1,?,?)",
            (
                ident,
                ident,
                ident + ".example",
                connected,
                heartbeat,
                lifecycle,
                platform,
                version,
                "2026-10-04T00:00:00Z",
                "2026-10-04T00:00:00Z",
            ),
        )

    def test_capability_ledger_is_generated_from_catalog_and_ready_registries(self):
        ledger = capability_parity_ledger()
        catalog_names = [tool.name for tool in MANAGEMENT_TOOLS]
        rows = ledger["capabilities"]
        self.assertEqual([row["name"] for row in rows], catalog_names)
        self.assertEqual(ledger["capability_count"], len(MANAGEMENT_TOOLS))
        self.assertTrue(ledger["machine_generated"])
        self.assertFalse(ledger["authoritative"])
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["drlink_inventory_list"]["core_status"], CORE_READY)
        self.assertEqual(by_name["drlink_temporary_access_apply"]["core_status"], CORE_READY)
        registered = implemented_management_tool_names()
        ready_names = {row["name"] for row in rows if row["core_status"] == CORE_READY}
        self.assertEqual(ready_names, set(registered))
        self.assertEqual(ledger["core_ready_count"], len(registered))
        self.assertEqual(ledger["contract_only_count"], len(MANAGEMENT_TOOLS) - len(registered))
        for name in (
            "drlink_guided_change_preview", "drlink_guided_change_apply",
            "drlink_remote_service_preview", "drlink_remote_service_apply",
            "drlink_diagnostic_job_start",
        ):
            with self.subTest(name=name):
                self.assertEqual(by_name[name]["core_status"], CORE_READY)
                self.assertTrue(callable(getattr(ManagementCoreService, "_invoke_" + name, None)))
        self.assertEqual(
            by_name["drlink_diagnostic_job_start"]["plugin_target"],
            next(t.plugin_exposure for t in MANAGEMENT_TOOLS if t.name == "drlink_diagnostic_job_start"),
        )

    def test_capability_inventory_uses_same_readiness_as_core_dispatch(self):
        with ManagementQueryService(self.tmp) as query:
            ledger = query.capability_inventory()
        names = {row["name"] for row in ledger["capabilities"] if row["core_status"] == CORE_READY}
        self.assertEqual(names, set(implemented_management_tool_names()))

    def test_explicit_partial_registry_does_not_promote_contract_only_tools(self):
        for ready in (set(), {"drlink_inventory_list"}):
            with self.subTest(ready=ready):
                ledger = capability_parity_ledger(ready_tool_names=ready)
                self.assertEqual(ledger["core_ready_count"], len(ready))
                self.assertEqual(ledger["contract_only_count"], len(MANAGEMENT_TOOLS) - len(ready))
                for row in ledger["capabilities"]:
                    self.assertEqual(row["core_status"], CORE_READY if row["name"] in ready else CORE_CONTRACT_ONLY)

    def test_capability_inventory_import_order_is_safe(self):
        for first in ("drlink_management_service", "drlink_management_core", "drlink_v30_capability"):
            code = (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "__import__(sys.argv[2]); "
                "from drlink_v30_capability import capability_parity_ledger; "
                "from drlink_management_core import implemented_management_tool_names; "
                "ledger = capability_parity_ledger(); "
                "assert ledger['core_ready_count'] == len(implemented_management_tool_names())"
            )
            with self.subTest(first=first):
                result = subprocess.run([sys.executable, "-c", code, str(ROOT / "lib"), first],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_capability_ledger_rejects_implementation_not_in_catalog(self):
        with self.assertRaises(ValueError):
            capability_parity_ledger(ready_tool_names={"not_a_catalog_tool"})

    def test_overview_is_derived_bounded_summary_with_version_inventory(self):
        self._insert_client("host-connected")
        self._insert_client(
            "host-stale",
            heartbeat="2026-10-04T01:50:00Z",
            platform="linux",
            version="2.4.0",
        )
        self._insert_client(
            "host-down",
            lifecycle="disconnected",
            connected=0,
            heartbeat=None,
            platform="win32",
            version=None,
        )
        self.conn.execute(
            "INSERT INTO published_services("
            "id,client_id,name,service_type,target_mode,target_host,target_port,public_port,"
            "enabled,released,row_version,created_at,updated_at"
            ") VALUES ('svc-a','host-connected','ssh','tcp','self','127.0.0.1',22,6001,1,0,1,?,?)",
            ("2026-10-04T00:00:00Z", "2026-10-04T00:00:00Z"),
        )
        self.conn.execute(
            "INSERT INTO policy_rules("
            "id,plane,name,position,action,enabled,row_version,created_at,updated_at"
            ") VALUES ('rule-a','remote','allow-ssh',1,'allow',1,1,?,?)",
            ("2026-10-04T00:00:00Z", "2026-10-04T00:00:00Z"),
        )
        self.conn.commit()

        summary = overview_summary(self.conn, now=self.now)
        self.assertEqual(summary["state_class"], "DERIVED")
        self.assertFalse(summary["authoritative"])
        self.assertTrue(summary["rebuildable"])
        self.assertEqual(summary["managed_hosts"]["total"], 3)
        self.assertEqual(summary["managed_hosts"]["connected"], 1)
        self.assertEqual(summary["managed_hosts"]["stale"], 1)
        self.assertEqual(summary["managed_hosts"]["disconnected"], 1)
        self.assertEqual(summary["managed_hosts"]["version_unknown"], 1)
        self.assertEqual(summary["remote_services"]["enabled"], 1)
        self.assertEqual(summary["policies"]["remote"]["enabled"], 1)
        versions = {(row["platform"], row["version"]): row["hosts"] for row in summary["agent_versions"]}
        self.assertEqual(versions[("linux", "3.0.0")], 1)
        self.assertEqual(versions[("win32", "unknown")], 1)

    def test_query_service_read_models_do_not_need_writer_slot(self):
        self._insert_client("host-a")
        self.conn.commit()
        query = ManagementQueryService(self.tmp)
        writer = open_control_db(self.tmp)
        try:
            before = writer.execute(
                "SELECT value FROM system_meta WHERE key='revision'"
            ).fetchone()
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                "INSERT OR REPLACE INTO system_meta(key,value) VALUES ('scale_probe','held')"
            )
            summary = query.overview_summary()
            ledger = query.capability_inventory()
            self.assertEqual(summary["managed_hosts"]["total"], 1)
            self.assertEqual(ledger["source"], "drlink_management_catalog.MANAGEMENT_TOOLS")
            writer.execute("ROLLBACK")
            after = writer.execute(
                "SELECT value FROM system_meta WHERE key='revision'"
            ).fetchone()
            self.assertEqual(
                None if before is None else before[0],
                None if after is None else after[0],
            )
        finally:
            query.close()
            writer.close()

    def test_agent_inventory_heartbeat_is_operational_not_configuration_revision(self):
        self._insert_client("host-a", lifecycle="disconnected", connected=0, heartbeat=None, platform=None, version=None)
        self.conn.commit()
        self.conn.close()
        plane = ControlPlane(self.tmp)
        try:
            before = plane.current_revision()
            self.assertTrue(
                plane.refresh_agent_lifecycle(
                    "host-a",
                    "connected",
                    agent_platform="Linux",
                    agent_version="3.0.0-rc.1",
                )
            )
            row = plane.conn.execute(
                "SELECT agent_platform,agent_version,agent_lifecycle_state FROM clients WHERE id='host-a'"
            ).fetchone()
            self.assertEqual(row["agent_platform"], "linux")
            self.assertEqual(row["agent_version"], "3.0.0-rc.1")
            self.assertEqual(row["agent_lifecycle_state"], "connected")
            self.assertEqual(plane.current_revision(), before)
        finally:
            plane.close()
        self.conn = open_control_db(self.tmp)

    def test_macos_mapped_version_path_and_windows_payload_contract(self):
        import drlink_mgmt_sync as mgmt

        mac_root = tempfile.mkdtemp(prefix="drlink-v30-mac-inventory-")
        version_path = Path(mac_root, "Library/Application Support/drlink/version")
        version_path.parent.mkdir(parents=True, exist_ok=True)
        version_path.write_text("PROJECT_VERSION=3.0.0-mac\n", encoding="utf-8")
        inventory = mgmt._local_agent_inventory(mac_root)
        self.assertEqual(inventory["agent_version"], "3.0.0-mac")

        windows = (ROOT / "windows/lib/FrpBootstrap.ps1").read_text(encoding="utf-8")
        self.assertIn("$bodyObject.agent_platform = 'windows'", windows)
        self.assertIn("$bodyObject.agent_version = (Get-FrpProjectVersion)", windows)
        self.assertIn("Get-FrpCanonicalJson -Object $bodyObject", windows)

    def test_common_100_host_query_shapes_use_reviewed_indexes(self):
        plans = {
            "host_status": (
                "idx_v30_clients_status",
                "SELECT id FROM clients WHERE status=? ORDER BY id LIMIT 51",
                ("active",),
            ),
            "host_version": (
                "idx_v30_clients_agent_version",
                "SELECT id FROM clients WHERE agent_version=? ORDER BY id LIMIT 51",
                ("3.0.0",),
            ),
            "service_state": (
                "idx_v30_services_state",
                "SELECT id FROM published_services WHERE enabled=? AND released=? ORDER BY id LIMIT 51",
                (1, 0),
            ),
            "policy_state": (
                "idx_v30_policy_plane_enabled_pos",
                "SELECT id FROM policy_rules WHERE plane=? AND enabled=? ORDER BY position,id LIMIT 51",
                ("remote", 1),
            ),
            "audit_category": (
                "idx_v30_audit_category_time",
                "SELECT id FROM audit_events WHERE category=? ORDER BY occurred_at DESC,id DESC LIMIT 51",
                ("CONTROL",),
            ),
            "job_status": (
                "idx_management_jobs_status_time",
                "SELECT id FROM management_jobs WHERE status=? ORDER BY created_at DESC,id DESC LIMIT 51",
                ("QUEUED",),
            ),
        }
        for name, (index_name, sql, args) in plans.items():
            with self.subTest(name=name):
                details = " ".join(
                    str(row["detail"])
                    for row in self.conn.execute(
                        "EXPLAIN QUERY PLAN " + sql, args
                    ).fetchall()
                )
                self.assertIn(index_name, details, details)

    def test_job_summary_is_part_of_overview_and_remains_derived(self):
        self.conn.close()
        engine = ManagementJobEngine(self.tmp, max_active_jobs=1)
        try:
            engine.enqueue(
                job_type="doctor",
                targets=["host-a"],
                requested_by="operator",
                now=self.now,
            )
        finally:
            engine.close()
        self.conn = open_control_db(self.tmp)
        summary = overview_summary(self.conn, now=self.now)
        self.assertEqual(summary["management_jobs"]["queued_jobs"], 1)
        self.assertEqual(summary["management_jobs"]["active_jobs"], 1)
        self.assertFalse(summary["management_jobs"]["saturated"])


if __name__ == "__main__":
    unittest.main()
