#!/usr/bin/env python3
"""F004/F017: Doctor reports stale HEALTHY catalog rows missing from real FRP configuration.

No product state is changed; all sqlite activity is confined to throwaway roots.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_v24 as v24
import drlink_v24_runtime as runtime
import frp_doctor as doctor


class AgentProjectionDiagnostics(unittest.TestCase):
    def _checks(self, *, healthy=True, rendered=False, matching_port=True,
                legacy_seed=False, old_schema=False):
        with tempfile.TemporaryDirectory(prefix="drlink-doctor-runtime-") as temp:
            base = Path(temp, "etc/frp")
            base.mkdir(parents=True)
            services = {}
            if rendered:
                sid = "ssh" if legacy_seed else "rs-ssh"
                services[sid] = {
                    "id": sid, "name": "SSH" if legacy_seed else "ssh",
                    "local_ip": "127.0.0.1", "local_port": 22,
                    "remote_port": 6001 if matching_port else 6088,
                    "enabled": True, "v24_remote_service": not legacy_seed,
                }
            data = {
                "schema_version": 1,
                "host_id": "fixture-host",
                "machine_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "hostname": "fixture",
                "services": services,
            }
            (base / "client-state.json").write_text(json.dumps(data))
            (base / "frpc.toml").write_text(
                runtime.render_frpc_toml_text(
                    server="203.0.113.10", server_port=443,
                    token="fixture-only", host_id="fixture-host",
                    services=services,
                )
            )
            if old_schema:
                import sqlite3
                db = Path(temp, "var/lib/drlink/drlink.db")
                db.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(db))
                conn.execute("CREATE TABLE legacy_fixture (id INTEGER)")
                conn.commit()
                conn.close()
            else:
                plane = ControlPlane(temp)
                try:
                    v24.ensure_v2_schema(plane.conn)
                    plane.conn.execute(
                        "INSERT INTO agent_remote_services "
                        "(name,destination,service_object,enabled,status,endpoint_host,"
                        "endpoint_port,pending_allocation,delete_pending,pool_class,"
                        "reason,updated_at,runtime_verified,enrollment_seed) "
                        "VALUES ('ssh','this-host','ssh',1,?,'203.0.113.10',6001,"
                        "0,0,'normal','', '2026-10-09T00:00:00Z',?,?)",
                        ("HEALTHY" if healthy else "DEGRADED", 1 if healthy else 0,
                         1 if legacy_seed else 0),
                    )
                    plane.conn.commit()
                finally:
                    plane.close()
            report = doctor.Report()
            report.role = "client"
            doctor.check_client(report, doctor.Paths(temp), {}, True)
            return {c["id"]: c for c in report.checks}

    def test_false_healthy_missing_rendered_proxy_is_fail(self):
        checks = self._checks(healthy=True, rendered=False)
        self.assertIn("agent_runtime_projection", checks)
        self.assertEqual(checks["agent_runtime_projection"]["status"], doctor.FAIL)
        self.assertIn("ssh", checks["agent_runtime_projection"]["detail"])

    def test_false_healthy_wrong_port_is_fail(self):
        checks = self._checks(healthy=True, rendered=True, matching_port=False)
        self.assertEqual(checks["agent_runtime_projection"]["status"], doctor.FAIL)

    def test_healthy_rendered_proxy_produces_no_new_diagnostic(self):
        checks = self._checks(healthy=True, rendered=True)
        self.assertNotIn("agent_runtime_projection", checks)

    def test_degraded_missing_dependency_does_not_claim_false_healthy(self):
        checks = self._checks(healthy=False, rendered=False)
        self.assertNotIn("agent_runtime_projection", checks)

    def test_enrollment_seed_legacy_proxy_id_is_legitimate(self):
        # Fresh bootstrap can initially retain the seed proxy id, even
        # though the canonical v2.4 catalog row shares the public name.
        checks = self._checks(healthy=True, rendered=True, legacy_seed=True)
        self.assertNotIn("agent_runtime_projection", checks)

    def test_older_database_without_v24_table_is_not_new_failure(self):
        checks = self._checks(old_schema=True)
        self.assertNotIn("agent_runtime_projection", checks)


if __name__ == "__main__":
    unittest.main()
