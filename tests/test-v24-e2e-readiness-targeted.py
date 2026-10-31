#!/usr/bin/env python3
"""Targeted F003 and O005 deterministic regressions before live Full User E2E.

No installed product, credentials, live policies, or external test hosts are changed.
"""
from __future__ import annotations
import importlib.util
import socket
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import drlink_v24 as v24
import drlink_mgmt_sync as mgmt

spec = importlib.util.spec_from_file_location(
    "frp_egress_gateway_e2e_targeted", ROOT / "server/frp-egress-gateway.py"
)
assert spec and spec.loader
gateway = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gateway
spec.loader.exec_module(gateway)


class AgentStaleAckTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE agent_remote_services ("
            "name TEXT PRIMARY KEY, status TEXT, reason TEXT, runtime_verified INTEGER, "
            "pending_allocation INTEGER, endpoint_port INTEGER, delete_pending INTEGER, "
            "enabled INTEGER, updated_at TEXT, "
            "enrollment_seed INTEGER NOT NULL DEFAULT 0)"
        )
        self.db.execute(
            "INSERT INTO agent_remote_services VALUES ("
            "'owned-service','DEGRADED','Runtime activation pending.',0,1,NULL,0,1,'before',0)"
        )
        self.plane = SimpleNamespace(conn=self.db, root="/invalid-fixture", _batch_mode=False)

    def tearDown(self):
        self.db.close()

    def row(self):
        return self.db.execute(
            "SELECT status, runtime_verified, endpoint_port, pending_allocation "
            "FROM agent_remote_services WHERE name='owned-service'"
        ).fetchone()

    def test_stale_server_ack_cannot_overwrite_newer_local_verified_generation(self):
        stale_response = {
            "services": [{
                "name": "owned-service", "status": "DEGRADED",
                "reason": "Runtime activation pending.", "runtime_verified": False,
                "endpoint_port": None, "pending_allocation": 1,
            }]
        }

        def competing_verified_update(*, root, services):
            self.db.execute(
                "UPDATE agent_remote_services SET "
                "status='HEALTHY', reason='', runtime_verified=1, "
                "pending_allocation=0, endpoint_port=6091, updated_at='after' "
                "WHERE name='owned-service'"
            )
            return stale_response

        with mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True), \
             mock.patch.object(mgmt, "report_remote_service_status_on_server",
                               side_effect=competing_verified_update):
            v24._push_agent_remote_service_status(self.plane, root="/invalid-fixture")
        self.assertEqual(tuple(self.row()), ("HEALTHY", 1, 6091, 0),
                         "late signed response must not overwrite a newer Agent row")

    def test_matching_server_ack_can_update_a_stable_local_row(self):
        response = {
            "services": [{
                "name": "owned-service", "status": "HEALTHY", "reason": "",
                "runtime_verified": True, "endpoint_port": 6092,
                "pending_allocation": 0,
            }]
        }
        with mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True), \
             mock.patch.object(mgmt, "report_remote_service_status_on_server",
                               return_value=response):
            v24._push_agent_remote_service_status(self.plane, root="/invalid-fixture")
        self.assertEqual(tuple(self.row()), ("HEALTHY", 1, 6092, 0))


class BodyTimeoutTests(unittest.TestCase):
    def test_incomplete_allowed_post_timeout_is_a_protocol_error(self):
        class TimedOutBody:
            def __init__(self):
                self.timeout = None
            def settimeout(self, value):
                self.timeout = value
            def recv(self, _size):
                raise socket.timeout("bounded body timeout")
        client = TimedOutBody()
        with self.assertRaises(gateway.EG.EgressError):
            gateway._spool_exact_body(client, b"prefix", 1024*1024)
        self.assertEqual(client.timeout, gateway.CLIENT_BODY_TIMEOUT)

    def test_complete_small_post_remains_byte_exact(self):
        class FragmentBody:
            def __init__(self):
                self.chunks = [b"cde", b"f"]
            def settimeout(self, _value):
                pass
            def recv(self, _size):
                return self.chunks.pop(0)
        data = gateway._read_exact_body(FragmentBody(), b"ab", 6)
        self.assertEqual(data, b"abcdef")


if __name__ == "__main__":
    unittest.main()
