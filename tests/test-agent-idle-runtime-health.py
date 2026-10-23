#!/usr/bin/env python3
"""Management-only Agents may idle; desired relay failures must remain visible."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_plane import ControlPlane
from drlink_agent_lifecycle import set_lifecycle_intent
import drlink_v24 as v24
import drlink_v24_runtime as runtime
import frp_doctor as doctor


class AgentIdleRuntimeHealth(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-idle-health-")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.plane = ControlPlane(self.root)
        self.addCleanup(self.plane.close)
        v24.ensure_v2_schema(self.plane.conn)
        self.plane.conn.commit()
        self.base = Path(self.root, "etc/frp")
        self.base.mkdir(parents=True, exist_ok=True)
        self.state = {"schema_version": 1, "host_id": "fixture-host",
                      "machine_id": "a" * 32, "hostname": "fixture", "services": {}}
        self.write_state()

    def write_state(self):
        (self.base / "client-state.json").write_text(json.dumps(self.state))
        (self.base / "frpc.toml").write_text(runtime.render_frpc_toml_text(
            server="203.0.113.10", server_port=443, token="fixture-only",
            host_id="fixture-host", services={}))

    def desired(self, enabled=1, delete_pending=0):
        self.plane.conn.execute(
            "INSERT INTO agent_remote_services "
            "(name,destination,service_object,enabled,status,endpoint_host,"
            "endpoint_port,pending_allocation,delete_pending,pool_class,"
            "reason,updated_at,runtime_verified,enrollment_seed) "
            "VALUES ('http','this-host','http',?,'DEGRADED','203.0.113.10',"
            "6000,0,?,'normal','','2026-10-20T00:00:00Z',0,0)",
            (enabled, delete_pending))
        self.plane.conn.commit()

    def probe(self, unit="inactive"):
        with patch.dict(os.environ, {"DRLINK_TEST_RUNTIME_UNIT": unit}):
            return v24.probe_agent_runtime_unit(root=self.root)

    def diagnostic(self, unit="inactive"):
        report = doctor.Report()
        report.role = "client"
        doctor.check_client(report, doctor.Paths(self.root), {
            "systemd_usable": True, "units": {"frpc": {"active": unit}}}, True)
        return next(c for c in report.checks if c["id"] == "frpc_service")["status"]

    def test_empty_inventory_is_explicit_expected_idle(self):
        result = self.probe()
        self.assertEqual(result["level"], "Healthy")
        self.assertIs(result.get("runtime_required"), False)
        self.assertIn("no enabled relay services", result["detail"])
        self.assertEqual(self.diagnostic(), doctor.PASS)

    def test_disabled_inventory_is_expected_idle(self):
        self.desired(enabled=0)
        self.state["services"]["rs-http"] = {"enabled": False}
        self.write_state()
        self.assertIs(self.probe().get("runtime_required"), False)
        self.assertEqual(self.diagnostic(), doctor.PASS)

    def test_enabled_unrendered_intent_stays_failed(self):
        self.desired()
        self.assertEqual(self.probe()["level"], "Critical")
        self.assertEqual(self.diagnostic(), doctor.FAIL)

    def test_pending_deletion_is_not_expected_idle(self):
        self.desired(enabled=0, delete_pending=1)
        self.assertEqual(self.probe()["level"], "Critical")
        self.assertEqual(self.diagnostic(), doctor.FAIL)

    def test_enabled_legacy_rendered_service_stays_required(self):
        self.state["services"]["legacy-http"] = {"enabled": True}
        self.write_state()
        self.assertEqual(self.probe()["level"], "Critical")
        self.assertEqual(self.diagnostic(), doctor.FAIL)

    def test_failed_unit_is_never_exempt(self):
        self.assertEqual(self.probe("failed:start-limit-hit")["level"], "Critical")
        self.assertEqual(self.diagnostic("failed"), doctor.FAIL)

    def test_unknown_inventory_stays_conservative(self):
        for services in (None, [], {"bad": None}):
            with self.subTest(services=services):
                self.state["services"] = services
                self.write_state()
                self.assertEqual(self.probe()["level"], "Critical")
                self.assertEqual(self.diagnostic(), doctor.FAIL)

    def test_missing_or_unreadable_database_stays_conservative(self):
        self.plane.close()
        db = Path(self.root, "var/lib/drlink/drlink.db")
        db.unlink()
        self.assertEqual(self.probe()["level"], "Critical")
        self.assertEqual(self.diagnostic(), doctor.FAIL)
        self.assertFalse(db.exists(), "read-only diagnostics must not create a DB")
        db.write_text("invalid sqlite")
        self.assertEqual(self.probe()["level"], "Critical")
        self.assertEqual(self.diagnostic(), doctor.FAIL)

    def test_paused_intent_keeps_precedence(self):
        set_lifecycle_intent("paused", root=self.root)
        self.assertEqual(self.probe()["level"], "Paused")
        self.assertEqual(self.probe("active")["level"], "Warning")

    def test_status_explains_idle_without_claiming_relay_connectivity(self):
        with patch.dict(os.environ, {"DRLINK_TEST_RUNTIME_UNIT": "inactive"}), \
                patch.object(v24, "detect_cli_role", return_value="agent"), \
                patch.object(v24, "detect_server_reachable", return_value=True):
            text = self.plane.format_status()
        self.assertIn("no enabled relay services", text)
        self.assertIn("Management connected; no enabled relay services", text)
        self.assertNotIn("Agent transport unverified", text)


if __name__ == "__main__":
    unittest.main()
