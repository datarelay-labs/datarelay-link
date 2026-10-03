#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import utc_now_iso
from drlink_control_plane import ControlPlane
from drlink_management_service import ManagementQueryService
from drlink_v30_live import (
    FIDELITY_EXACT,
    FIDELITY_UNKNOWN,
    default_live_snapshot_path,
    read_live_snapshot,
    sanitize_session,
    write_live_snapshot,
)


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class V30LiveAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-live-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        plane = ControlPlane(self.tmp)
        plane.close()
        self.query = ManagementQueryService(self.tmp)

    def tearDown(self):
        self.query.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def test_snapshot_is_secret_safe_and_exact(self):
        session = {
            "session_id": "sess-1",
            "connection_id": "conn-1",
            "source_ip": "198.51.100.10",
            "hostname": "example.com",
            "port": 443,
            "protocol": "https",
            "method": "CONNECT",
            "policy_generation": 7,
            "start_time": time.time() - 5,
            "authorized_candidates": ["93.184.216.34"],
            "payload": "do-not-expose",
            "token": "secret",
        }
        safe = sanitize_session(session, producer="internet-gateway")
        self.assertEqual(safe["session_id"], "sess-1")
        self.assertEqual(safe["status"], "ACTIVE")
        self.assertIn("started_at", safe)
        self.assertNotIn("authorized_candidates", safe)
        self.assertNotIn("payload", safe)
        self.assertNotIn("token", safe)

        path = default_live_snapshot_path("internet-gateway", self.tmp)
        written = write_live_snapshot(
            path,
            producer="internet-gateway",
            plane="internet",
            sessions=[session],
        )
        self.assertEqual(written["fidelity"], FIDELITY_EXACT)
        self.assertEqual(written["active_count"], 1)
        reread = read_live_snapshot(path)
        self.assertEqual(reread["observations"][0]["session_id"], "sess-1")

    def test_internet_requires_both_producers_for_plane_exactness(self):
        write_live_snapshot(
            default_live_snapshot_path("internet-gateway", self.tmp),
            producer="internet-gateway",
            plane="internet",
            sessions=[{"session_id": "sess-gw", "hostname": "example.com"}],
        )
        missing = self.query.live_access(plane="internet")
        self.assertEqual(missing["fidelity"], FIDELITY_UNKNOWN)
        self.assertEqual(missing["observations"], [])

        write_live_snapshot(
            default_live_snapshot_path("fixed-tcp", self.tmp),
            producer="fixed-tcp",
            plane="internet",
            sessions=[
                {
                    "session_id": "sess-tcp",
                    "relay_id": "relay-1",
                    "relay_name": "api",
                    "hostname": "api.example.com",
                }
            ],
        )
        exact = self.query.live_access(plane="internet")
        self.assertEqual(exact["fidelity"], FIDELITY_EXACT)
        self.assertEqual(exact["active_count"], 2)
        self.assertEqual(
            {item["producer"] for item in exact["observations"]},
            {"internet-gateway", "fixed-tcp"},
        )

    def test_resource_filter_is_exact_and_bounded(self):
        write_live_snapshot(
            default_live_snapshot_path("internet-gateway", self.tmp),
            producer="internet-gateway",
            plane="internet",
            sessions=[
                {"session_id": "sess-a", "hostname": "a.example.com"},
                {"session_id": "sess-b", "hostname": "b.example.com"},
            ],
        )
        write_live_snapshot(
            default_live_snapshot_path("fixed-tcp", self.tmp),
            producer="fixed-tcp",
            plane="internet",
            sessions=[],
        )
        result = self.query.live_access(
            plane="internet", resource_type="destination", resource="b.example.com"
        )
        self.assertEqual(result["fidelity"], FIDELITY_EXACT)
        self.assertEqual(result["active_count"], 1)
        self.assertEqual(result["observations"][0]["session_id"], "sess-b")

    def test_remote_truthfully_stays_unknown(self):
        result = self.query.live_access(plane="remote")
        self.assertEqual(result["fidelity"], FIDELITY_UNKNOWN)
        self.assertIsNone(result["active_count"])
        self.assertIn("official FRP", result["reason"])

    def test_internet_live_access_cursor_paginates_exact_sessions(self):
        now = time.time()
        write_live_snapshot(
            default_live_snapshot_path("internet-gateway", self.tmp),
            producer="internet-gateway",
            plane="internet",
            sessions=[
                {
                    "session_id": "sess-new",
                    "hostname": "new.example.com",
                    "start_time": now,
                },
                {
                    "session_id": "sess-old",
                    "hostname": "old.example.com",
                    "start_time": now - 10,
                },
            ],
        )
        write_live_snapshot(
            default_live_snapshot_path("fixed-tcp", self.tmp),
            producer="fixed-tcp",
            plane="internet",
            sessions=[],
        )
        first = self.query.live_access(plane="internet", limit=1)
        self.assertEqual(first["fidelity"], FIDELITY_EXACT)
        self.assertEqual(first["active_count"], 2)
        self.assertEqual(len(first["observations"]), 1)
        self.assertEqual(first["observations"][0]["session_id"], "sess-new")
        self.assertIsNotNone(first["next_cursor"])

        second = self.query.live_access(
            plane="internet", limit=1, cursor=first["next_cursor"]
        )
        self.assertEqual(second["active_count"], 2)
        self.assertEqual(
            [item["session_id"] for item in second["observations"]], ["sess-old"]
        )
        self.assertIsNone(second["next_cursor"])

    def test_ai_live_access_is_exact_for_queued_and_running_jobs(self):
        plane = ControlPlane(self.tmp)
        try:
            plane.set_ai_principal("agent-a", enabled=True)
            principal = plane.get_principal("agent-a")
            now = utc_now_iso()
            plane.conn.execute(
                "INSERT INTO ai_jobs("
                "id,principal_id,endpoint_object_id,capability,payload_json,status,"
                "created_at,updated_at,timeout_seconds,client_id,deadline_at,"
                "claim_token,attempt_id,claimed_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "job-queued",
                    principal["id"],
                    None,
                    "host-info",
                    "{}",
                    "queued",
                    now,
                    now,
                    30,
                    "client-a",
                    None,
                    None,
                    None,
                    None,
                ),
            )
            plane.conn.execute(
                "INSERT INTO ai_jobs("
                "id,principal_id,endpoint_object_id,capability,payload_json,status,"
                "created_at,updated_at,timeout_seconds,client_id,deadline_at,"
                "claim_token,attempt_id,claimed_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "job-running",
                    principal["id"],
                    None,
                    "process-read",
                    "{}",
                    "running",
                    now,
                    now,
                    30,
                    "client-a",
                    None,
                    "claim",
                    "attempt",
                    now,
                ),
            )
            plane.conn.execute(
                "INSERT INTO ai_jobs("
                "id,principal_id,endpoint_object_id,capability,payload_json,status,"
                "created_at,updated_at,timeout_seconds,client_id,deadline_at,"
                "claim_token,attempt_id,claimed_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "job-done",
                    principal["id"],
                    None,
                    "host-info",
                    "{}",
                    "done",
                    now,
                    now,
                    30,
                    "client-a",
                    None,
                    None,
                    None,
                    None,
                ),
            )
        finally:
            plane.close()

        first = self.query.live_access(plane="ai", limit=1)
        self.assertEqual(first["fidelity"], FIDELITY_EXACT)
        self.assertEqual(first["active_count"], 2)
        self.assertEqual(len(first["observations"]), 1)
        self.assertIsNotNone(first["next_cursor"])

        second = self.query.live_access(
            plane="ai", limit=1, cursor=first["next_cursor"]
        )
        self.assertEqual(second["active_count"], 2)
        self.assertEqual(len(second["observations"]), 1)
        self.assertNotEqual(
            first["observations"][0]["job_id"], second["observations"][0]["job_id"]
        )

        filtered = self.query.live_access(plane="ai", resource="agent-a")
        self.assertEqual(filtered["active_count"], 2)
        self.assertEqual(
            {item["status"] for item in filtered["observations"]},
            {"QUEUED", "RUNNING"},
        )

    def test_live_access_requires_explicit_plane(self):
        with self.assertRaises(Exception):
            self.query.live_access(plane="")

    def test_invalid_snapshot_schema_becomes_unknown(self):
        path = default_live_snapshot_path("internet-gateway", self.tmp)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema_version":99,"observations":[]}\n', encoding="utf-8")
        result = read_live_snapshot(path)
        self.assertEqual(result["fidelity"], FIDELITY_UNKNOWN)
        self.assertEqual(result["observations"], [])


if __name__ == "__main__":
    unittest.main()
