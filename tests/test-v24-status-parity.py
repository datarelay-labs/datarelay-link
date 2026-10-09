#!/usr/bin/env python3
"""Agent DEGRADED / runtime failure must converge on Server inventory."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_mgmt_sync as mgmt
import drlink_upgrade_reconcile as UR
import drlink_v24 as v24
import frp_mgmt_auth as MGMT

MACHINE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _write_identity(root: Path, machine_id: str, hostname: str):
    frp = root / "etc/frp"
    frp.mkdir(parents=True, exist_ok=True)
    (frp / "client-state.json").write_text(
        json.dumps(
            {"machine_id": machine_id, "hostname": hostname, "label": hostname},
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    (frp / "frpc.toml").write_text("[common]\n", encoding="utf-8")
    key = frp / "client-identity.key"
    pub = frp / "client-identity.pub"
    MGMT.generate_keypair(key, pub)
    os.chmod(key, 0o600)
    mac = MGMT.new_mac_key()
    mac_path = frp / "client-identity.mac"
    mac_path.write_text(mac, encoding="utf-8")
    os.chmod(mac_path, 0o600)
    return key, pub.read_text(encoding="utf-8"), mac


class StatusParityTests(unittest.TestCase):
    def setUp(self):
        self.server_tmp = tempfile.mkdtemp(prefix="drlink-status-srv-")
        self.agent_tmp = tempfile.mkdtemp(prefix="drlink-status-agt-")
        Path(self.server_tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.server_tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_CONFIRM"] = "yes"
        os.environ.pop("DRLINK_MGMT_TOKEN", None)
        self.server = ControlPlane(self.server_tmp)
        v24.ensure_v2_schema(self.server.conn)
        v24.set_service_object(self.server, "ssh", type="tcp", port=22, oneshot=True)
        self.key, self.pub, self.mac = _write_identity(Path(self.agent_tmp), MACHINE, "agent-a")
        self.server.upsert_client(MACHINE, label="agent-a", hostname="agent-a")
        self.verifier = mgmt.InMemoryMgmtVerifier()
        self.verifier.enroll(MACHINE, self.pub, mac_key=self.mac, hostname="agent-a")
        self.httpd, self.base, _ = mgmt.start_mgmt_server(self.server, verifier=self.verifier)
        os.environ["DRLINK_MGMT_URL"] = self.base
        Path(self.agent_tmp, "etc/frp/server-endpoint.json").write_text(
            '{"mgmt_url":"%s"}\n' % self.base, encoding="utf-8"
        )
        self.agent = ControlPlane(self.agent_tmp)
        v24.ensure_v2_schema(self.agent.conn)

    def tearDown(self):
        mgmt.stop_mgmt_server(self.httpd)
        self.server.close()
        self.agent.close()
        for key in ("DRLINK_SKIP_ACTIVATION", "DRLINK_CONFIRM", "DRLINK_MGMT_URL"):
            os.environ.pop(key, None)

    def _server_status(self, name: str):
        return self.server.conn.execute(
            "SELECT m.status, m.reason, s.public_port FROM published_services s "
            "JOIN remote_service_meta m ON m.service_id = s.id WHERE s.name = ?",
            (name,),
        ).fetchone()

    def test_SERVER_ACK_REFRESHES_VERIFIED_FLAG_WITHOUT_STATUS_TEXT_CHANGE(self):
        # F018: a real runtime generation can be acknowledged while the
        # already-HEALTHY status text is unchanged. Never leave the old
        # verification bit stale; conversely an unverified Server ACK must
        # not preserve an earlier verified bit.
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, updated_at, runtime_verified) "
            "VALUES ('keepalive-ssh', 'this-host', 'ssh', 1, 'HEALTHY', 'example.test', 6020, "
            "0, 0, 'normal', '', '2026-10-09T00:00:00Z', 0)"
        )
        self.agent.conn.commit()
        response = {
            "services": [{
                "name": "keepalive-ssh", "status": "HEALTHY",
                "runtime_verified": True, "endpoint_port": 6020,
                "reason": "",
            }]
        }
        self.assertEqual(v24._reconcile_agent_from_server_status(self.agent, response), 1)
        state = self.agent.conn.execute(
            "SELECT status, runtime_verified FROM agent_remote_services WHERE name='keepalive-ssh'"
        ).fetchone()
        self.assertEqual((state['status'], state['runtime_verified']), ('HEALTHY', 1))
        # Same status, but no verified generation -- must clear the bit.
        response['services'][0]['runtime_verified'] = False
        self.assertEqual(v24._reconcile_agent_from_server_status(self.agent, response), 1)
        state = self.agent.conn.execute(
            "SELECT status, runtime_verified FROM agent_remote_services WHERE name='keepalive-ssh'"
        ).fetchone()
        self.assertEqual((state['status'], state['runtime_verified']), ('HEALTHY', 0))

    def test_verified_status_report_ack_preserves_local_runtime_verification(self):
        # A signed Server ACK reflects the Server's validated effective state.
        # Losing the verified field in that ACK falsely marks an actual
        # currently-active proxy DEGRADED in the Agent's public CLI.
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        self.assertEqual(created["status"], "HEALTHY")
        port = int(self._server_status("ssh-access")["public_port"])
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, "
            "endpoint_port, pending_allocation, delete_pending, pool_class, reason, "
            "updated_at, runtime_verified) "
            "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'HEALTHY', 'example.test', "
            "?, 0, 0, 'normal', '', '2026-10-09T00:00:00Z', 1)",
            (port,),
        )
        self.agent.conn.commit()

        returned = mgmt.report_remote_service_status_on_server(
            root=self.agent_tmp,
            services=[{
                "name": "ssh-access", "status": "HEALTHY",
                "runtime_verified": True, "endpoint_port": port, "reason": "",
            }],
        )
        self.assertEqual(returned["count"], 1)
        self.assertTrue(returned["services"][0]["runtime_verified"], returned)
        self.assertEqual(v24._push_agent_remote_service_status(
            self.agent, root=self.agent_tmp,
        ), 0)
        row = self.agent.conn.execute(
            "SELECT status, runtime_verified FROM agent_remote_services "
            "WHERE name='ssh-access'"
        ).fetchone()
        self.assertEqual((row["status"], row["runtime_verified"]), ("HEALTHY", 1))

        unverified = mgmt.report_remote_service_status_on_server(
            root=self.agent_tmp,
            services=[{
                "name": "ssh-access", "status": "HEALTHY",
                "runtime_verified": False, "endpoint_port": port, "reason": "",
            }],
        )
        self.assertEqual(unverified["services"][0]["status"], "DEGRADED")
        self.assertFalse(unverified["services"][0]["runtime_verified"])
        v24._reconcile_agent_from_server_status(self.agent, unverified)
        row = self.agent.conn.execute(
            "SELECT status, runtime_verified FROM agent_remote_services "
            "WHERE name='ssh-access'"
        ).fetchone()
        self.assertEqual((row["status"], row["runtime_verified"]), ("DEGRADED", 0))

    def test_F019_transient_missing_service_object_rechecks_authoritative_catalog(self):
        # A previous Agent cache refresh can miss a concurrently committed
        # Server Fixed TCP Service Object. If it is still present in the
        # authoritative Server, synchronize must not demote a live publication
        # for a transient incomplete local snapshot.
        from unittest import mock

        service_object = "f019-capacity-fixed"
        name = "f019-live"
        v24.set_service_object(
            self.server, service_object,
            type="fixed-tcp", port=20087, oneshot=True,
        )
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services "
            "(name, destination, destination_client_id, service_object, enabled, status, "
            "endpoint_host, endpoint_port, pending_allocation, delete_pending, pool_class, "
            "reason, updated_at) "
            "VALUES (?, 'this-host', ?, ?, 1, 'HEALTHY', '203.0.113.10', 6287, "
            "0, 0, 'fixed-tcp', '', '2026-10-09T00:00:00Z')",
            (name, MACHINE, service_object),
        )
        self.agent.conn.commit()

        real_sync = v24.sync_agent_catalog_from_server
        fetches = []

        def first_snapshot_incomplete(plane, server_plane=None, *, root=None):
            count = real_sync(plane, server_plane, root=root)
            fetches.append(1)
            if len(fetches) == 1:
                plane.conn.execute(
                    "DELETE FROM agent_object_catalog "
                    "WHERE kind='service-object' AND name=?", (service_object,),
                )
                plane.conn.commit()
            return count

        os.environ["DRLINK_SERVER_REACHABLE"] = "1"
        try:
            with mock.patch.object(v24, "sync_agent_catalog_from_server",
                                   side_effect=first_snapshot_incomplete):
                result = v24.synchronize_agent_remote_services(
                    self.agent, root=self.agent_tmp,
                )
        finally:
            os.environ.pop("DRLINK_SERVER_REACHABLE", None)
        self.assertGreaterEqual(len(fetches), 2, fetches)
        row = self.agent.conn.execute(
            "SELECT status, endpoint_port, reason FROM agent_remote_services "
            "WHERE name=?", (name,),
        ).fetchone()
        self.assertNotIn("missing or invalid", str(row["reason"]).lower(), result)
        self.assertEqual(int(row["endpoint_port"] or 0), 6287)
        self.assertIn(result.get("status"), ("SYNCHRONIZED", "DEGRADED"))

    def test_F019_permanently_missing_fixed_tcp_dependency_stays_degraded(self):
        # The authoritative retry must never invent a removed Service Object
        # or make a missing dependency HEALTHY.
        from unittest import mock
        name = "f019-gone"
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services "
            "(name, destination, destination_client_id, service_object, enabled, status, "
            "endpoint_host, endpoint_port, pending_allocation, delete_pending, pool_class, "
            "reason, updated_at) "
            "VALUES (?, 'this-host', ?, 'f019-no-such-service', 1, 'HEALTHY', "
            "'203.0.113.10', 6288, 0, 0, 'fixed-tcp', '', '2026-10-09T00:00:00Z')",
            (name, MACHINE),
        )
        self.agent.conn.commit()
        os.environ["DRLINK_SERVER_REACHABLE"] = "1"
        try:
            with mock.patch.object(
                v24, "set_remote_service_agent", side_effect=AssertionError(
                    "missing dependency must never activate a Remote Service"
                )
            ):
                result = v24.synchronize_agent_remote_services(
                    self.agent, root=self.agent_tmp
                )
        finally:
            os.environ.pop("DRLINK_SERVER_REACHABLE", None)
        row = self.agent.conn.execute(
            "SELECT status, reason FROM agent_remote_services WHERE name=?", (name,)
        ).fetchone()
        self.assertEqual(row["status"], "DEGRADED", result)
        self.assertIn("missing or invalid", row["reason"])
        self.assertEqual(result["status"], "DEGRADED")

    def test_F024_stale_sync_snapshot_cannot_recreate_deleted_service(self):
        # F024 race: synchronizer snapshots an Agent row, a public operator
        # deletes that row, then the synchronizer blindly replays its old
        # definition. Reconciliation must be update-only, not implicit create.
        from unittest import mock

        name = "f024-deleted"
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services"
            "(name, destination, destination_client_id, service_object, enabled, status, "
            "endpoint_host, endpoint_port, pending_allocation, delete_pending, pool_class, "
            "reason, updated_at) VALUES (?, 'this-host', ?, 'ssh', 1, 'DEGRADED', "
            "'example.test', 6030, 0, 0, 'normal', 'Runtime activation pending.', "
            "'2026-10-09T00:00:00Z')",
            (name, MACHINE),
        )
        self.agent.conn.commit()
        original_set = v24.set_remote_service_agent
        seen = []

        def deleted_before_replay(plane, svc_name, **kwargs):
            seen.append(svc_name)
            if svc_name == name:
                self.agent.conn.execute(
                    "DELETE FROM agent_remote_services WHERE name=?", (name,)
                )
                self.agent.conn.commit()
            return original_set(plane, svc_name, **kwargs)

        os.environ["DRLINK_SERVER_REACHABLE"] = "1"
        try:
            with mock.patch.object(v24, "set_remote_service_agent",
                                   side_effect=deleted_before_replay):
                result = v24.synchronize_agent_remote_services(
                    self.agent, root=self.agent_tmp,
                )
        finally:
            os.environ.pop("DRLINK_SERVER_REACHABLE", None)

        self.assertIn(name, seen)
        self.assertIsNone(self.agent.conn.execute(
            "SELECT 1 FROM agent_remote_services WHERE name=?", (name,)
        ).fetchone(), result)
        self.assertIsNone(self.server.conn.execute(
            "SELECT 1 FROM published_services WHERE name=? AND released=0", (name,)
        ).fetchone(), result)

    def test_F024_catalog_refresh_delete_race_skips_but_explicit_create_is_allowed(self):
        # A signed Server catalog read may race user deletion inside the same
        # sync operation. An update-only replay must not re-publish the name,
        # but an independent new public set operation is permitted.
        from unittest import mock
        name = "f024-between-reads"
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services"
            "(name, destination, destination_client_id, service_object, enabled, status, "
            "endpoint_host, endpoint_port, pending_allocation, delete_pending, pool_class, "
            "reason, updated_at) VALUES (?, 'this-host', ?, 'ssh', 1, 'DEGRADED', "
            "'example.test', 6031, 0, 0, 'normal', 'Runtime activation pending.', "
            "'2026-10-09T00:00:00Z')",
            (name, MACHINE),
        )
        self.agent.conn.commit()

        def delete_during_catalog_refresh(_plane, server_plane=None, *, root=None):
            self.agent.conn.execute(
                "DELETE FROM agent_remote_services WHERE name=?", (name,)
            )
            self.agent.conn.commit()
            return 0

        with mock.patch.object(v24, "sync_agent_catalog_from_server",
                               side_effect=delete_during_catalog_refresh):
            response = v24.set_remote_service_agent(
                self.agent, name, destination="this-host", service="ssh",
                enabled=True, oneshot=True, root=self.agent_tmp,
                server_reachable=True, reconcile_existing=True,
            )
        self.assertTrue(response.get("skipped"), response)
        self.assertIsNone(self.server.conn.execute(
            "SELECT 1 FROM published_services WHERE name=? AND released=0", (name,)
        ).fetchone())

        # Explicit re-creation has different authority from internal sync.
        created = v24.set_remote_service_agent(
            self.agent, name, destination="this-host", service="ssh",
            enabled=True, oneshot=True, root=self.agent_tmp,
            server_reachable=True,
        )
        self.assertFalse(created.get("skipped", False))
        self.assertIsNotNone(self.agent.conn.execute(
            "SELECT 1 FROM agent_remote_services WHERE name=?", (name,)
        ).fetchone())

    def test_AGENT_DEGRADED_PROPAGATES_TO_SERVER(self):
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        self.assertEqual(created["status"], "HEALTHY")
        reported = mgmt.report_remote_service_status_on_server(
            root=self.agent_tmp,
            services=[
                {
                    "name": "ssh-access",
                    "status": "DEGRADED",
                    "reason": "Required Network Object / Managed Host destination 'db-prod' is missing or invalid after reconnect.",
                    "runtime_verified": False,
                }
            ],
        )
        self.assertEqual(reported["count"], 1)
        row = self._server_status("ssh-access")
        self.assertEqual(row["status"], "DEGRADED")
        self.assertIn("db-prod", row["reason"])

    def test_AGENT_RUNTIME_FAILURE_PROPAGATES_TO_SERVER(self):
        mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        mgmt.report_remote_service_status_on_server(
            root=self.agent_tmp,
            services=[
                {
                    "name": "ssh-access",
                    "status": "DEGRADED",
                    "reason": "Runtime activation failed",
                    "runtime_verified": False,
                    "runtime_generation": 4,
                }
            ],
        )
        row = self._server_status("ssh-access")
        self.assertEqual(row["status"], "DEGRADED")
        self.assertIn("Runtime activation failed", row["reason"])

    def test_SERVER_NEVER_HEALTHY_WITH_MISSING_RUNTIME(self):
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=False,
        )
        self.assertEqual(created["status"], "DEGRADED")
        # A bare HEALTHY claim without runtime_verified must not be accepted.
        mgmt.report_remote_service_status_on_server(
            root=self.agent_tmp,
            services=[
                {
                    "name": "ssh-access",
                    "status": "HEALTHY",
                    "reason": "",
                    "runtime_verified": False,
                }
            ],
        )
        row = self._server_status("ssh-access")
        self.assertNotEqual(row["status"], "HEALTHY")

    def test_SERVER_AGENT_STATUS_CONVERGENCE_AFTER_SYNC(self):
        mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        now = "2026-09-18T00:00:00Z"
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, updated_at) "
            "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'DEGRADED', 'drlink.local', 6012, 0, 0, 'normal', "
            "'Required Service Object is missing or invalid after reconnect.', ?)",
            (now,),
        )
        self.agent.conn.commit()
        v24._push_agent_remote_service_status(self.agent, root=self.agent_tmp)
        row = self._server_status("ssh-access")
        self.assertEqual(row["status"], "DEGRADED")

    def test_DEPENDENCY_RESTORED_RECOVERS_TO_HEALTHY(self):
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        mgmt.report_remote_service_status_on_server(
            root=self.agent_tmp,
            services=[
                {
                    "name": "ssh-access",
                    "status": "DEGRADED",
                    "reason": "Runtime activation failed",
                    "runtime_verified": False,
                }
            ],
        )
        self.assertEqual(self._server_status("ssh-access")["status"], "DEGRADED")
        acked = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            preserve_endpoint_port=created["endpoint_port"],
            runtime_verified=True,
        )
        self.assertEqual(acked["status"], "HEALTHY")
        self.assertEqual(acked["endpoint_port"], created["endpoint_port"])
        self.assertEqual(self._server_status("ssh-access")["status"], "HEALTHY")


ROCKY8 = "ddddddddddddddddddddddddddddddd1"


class StaleEndpointTruthTests(unittest.TestCase):
    def setUp(self):
        self.server_tmp = tempfile.mkdtemp(prefix="drlink-stale-srv-")
        self.agent_tmp = tempfile.mkdtemp(prefix="drlink-stale-agt-")
        Path(self.server_tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.server_tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_CONFIRM"] = "yes"
        os.environ.pop("DRLINK_MGMT_TOKEN", None)
        self.server = ControlPlane(self.server_tmp)
        v24.ensure_v2_schema(self.server.conn)
        v24.set_service_object(self.server, "ssh", type="tcp", port=22, oneshot=True)
        self.key, self.pub, self.mac = _write_identity(Path(self.agent_tmp), MACHINE, "agent-a")
        self.server.upsert_client(MACHINE, label="agent-a", hostname="agent-a")
        self.verifier = mgmt.InMemoryMgmtVerifier()
        self.verifier.enroll(MACHINE, self.pub, mac_key=self.mac, hostname="agent-a")
        self.httpd, self.base, _ = mgmt.start_mgmt_server(self.server, verifier=self.verifier)
        os.environ["DRLINK_MGMT_URL"] = self.base
        Path(self.agent_tmp, "etc/frp/server-endpoint.json").write_text(
            '{"mgmt_url":"%s"}\n' % self.base, encoding="utf-8"
        )
        self.agent = ControlPlane(self.agent_tmp)
        v24.ensure_v2_schema(self.agent.conn)

    def tearDown(self):
        mgmt.stop_mgmt_server(self.httpd)
        self.server.close()
        self.agent.close()
        for key in ("DRLINK_SKIP_ACTIVATION", "DRLINK_CONFIRM", "DRLINK_MGMT_URL"):
            os.environ.pop(key, None)

    def _write_registry(self, clients: dict, reserved=None):
        path = Path(self.server_tmp) / "var/lib/drlink/runtime/client-inventory.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "clients": clients,
                    "reserved": list(reserved or []),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _seed_server_service(self, name, destination, port, status="DEGRADED"):
        now = "2026-09-18T00:00:00Z"
        self.server.set_published_service(
            MACHINE,
            name,
            service_type="tcp",
            target_mode="routed" if destination not in ("this-host", "this_host", "self") else "self",
            target_host="127.0.0.1",
            target_port=22,
            enabled=True,
            public_port=port,
        )
        pub = self.server.conn.execute(
            "SELECT id FROM published_services WHERE client_id = ? AND name = ?",
            (MACHINE, name),
        ).fetchone()
        self.server.conn.execute(
            "INSERT OR REPLACE INTO remote_service_meta"
            "(service_id, status, pool_class, service_object_id, destination_name, pending_allocation, delete_pending, reason) "
            "VALUES (?, ?, 'normal', ?, ?, 0, 0, ?)",
            (
                pub["id"],
                status,
                v24.get_service_object(self.server, "ssh")["id"],
                destination,
                "stale endpoint" if status == "DEGRADED" else "",
            ),
        )
        self.server.conn.execute(
            "INSERT OR REPLACE INTO port_reservations"
            "(public_port, client_id, service_id, service_name, released, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (port, MACHINE, pub["id"], name, now),
        )
        self.server.conn.commit()
        return pub

    def _seed_agent_service(self, name, destination, port, status="DEGRADED", pending=0):
        now = "2026-09-18T00:00:00Z"
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, updated_at) "
            "VALUES (?, ?, 'ssh', 1, ?, 'drlink.local', ?, ?, 0, 'normal', ?, ?)",
            (name, destination, status, port, pending, "stale endpoint retained locally", now),
        )
        self.agent.conn.commit()

    def _server_row(self, name):
        return self.server.conn.execute(
            "SELECT s.public_port, m.status, m.pending_allocation, m.reason FROM published_services s "
            "JOIN remote_service_meta m ON m.service_id = s.id WHERE s.name = ? AND s.released = 0",
            (name,),
        ).fetchone()

    def _agent_row(self, name):
        return self.agent.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name = ?", (name,)
        ).fetchone()

    def _show_agent(self, name):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.dispatch(
                ["show", "remote-service", name], root=self.agent_tmp, plane=self.agent
            )
        self.assertEqual(rc, 0, buf.getvalue())
        return buf.getvalue()

    def test_unverified_runtime_degraded_has_actionable_public_reason(self):
        # A stored HEALTHY flag without a verifiable current runtime generation
        # is deliberately DEGRADED. The public show output must explain that
        # distinction instead of presenting an unexplained contradiction.
        from unittest import mock

        self._seed_agent_service("e2e-runtime", "this-host", 6001, status="HEALTHY")
        self.agent.conn.execute(
            "UPDATE agent_remote_services SET runtime_verified=1, reason='' "
            "WHERE name='e2e-runtime'"
        )
        self.agent.conn.commit()
        with mock.patch("drlink_v24_cli._agent_runtime_level", return_value="Warning"):
            shown = self._show_agent("e2e-runtime")
        self.assertIn("Status: DEGRADED", shown)
        self.assertIn("Reason: Current Agent runtime verification", shown)
        self.assertIn("system diagnostics", shown)
        self.assertIn("system synchronize", shown)
        self.assertIn("show remote-service e2e-runtime", shown)

    def test_STALE_ENDPOINT_SERVER_RELEASE_AND_AGENT_CLEAR(self):
        self._write_registry(
            {
                ROCKY8: {
                    "hostname": "real-e2e-rocky8",
                    "label": "real-e2e-rocky8",
                    "services": {
                        "ssh": {
                            "id": "ssh",
                            "preset": "ssh",
                            "remote_port": 6001,
                            "local_ip": "127.0.0.1",
                            "local_port": 22,
                            "enabled": True,
                        }
                    },
                }
            },
            reserved=[6001],
        )
        self._seed_server_service("e2e-net", "db-prod", 6001)
        self._seed_agent_service("e2e-net", "db-prod", 6001)
        before_ports = {
            r[0]
            for r in self.server.conn.execute(
                "SELECT public_port FROM port_reservations WHERE released = 0"
            )
        }
        v24._push_agent_remote_service_status(self.agent, root=self.agent_tmp)
        server = self._server_row("e2e-net")
        self.assertEqual(server["status"], "DEGRADED")
        self.assertIsNone(server["public_port"])
        self.assertEqual(int(server["pending_allocation"]), 1)
        agent = self._agent_row("e2e-net")
        self.assertEqual(agent["status"], "DEGRADED")
        self.assertIsNone(agent["endpoint_port"])
        self.assertEqual(int(agent["pending_allocation"]), 1)
        shown = self._show_agent("e2e-net")
        self.assertIn("DEGRADED", shown)
        self.assertIn("Pending allocation", shown)
        self.assertNotIn("drlink.local:6001", shown)
        after_claimed = {
            r[0]
            for r in self.server.conn.execute(
                "SELECT public_port FROM published_services WHERE released = 0 AND public_port IS NOT NULL"
            )
        }
        self.assertNotIn(6001, after_claimed)
        # Status sync must not mint a replacement while the destination is invalid.
        self.assertIsNone(self._server_row("e2e-net")["public_port"])
        self.assertEqual(before_ports, {6001})

    def test_VALID_ENDPOINT_AGENT_PRESERVE(self):
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        port = int(created["endpoint_port"])
        self._write_registry(
            {
                MACHINE: {
                    "hostname": "agent-a",
                    "label": "agent-a",
                    "services": {
                        "ssh-access": {
                            "name": "ssh-access",
                            "remote_port": port,
                            "enabled": True,
                            "v24_remote_service": True,
                        }
                    },
                }
            },
            reserved=[port],
        )
        self._seed_agent_service("ssh-access", "this-host", port, status="HEALTHY", pending=0)
        v24._push_agent_remote_service_status(self.agent, root=self.agent_tmp)
        server = self._server_row("ssh-access")
        self.assertEqual(int(server["public_port"]), port)
        agent = self._agent_row("ssh-access")
        self.assertEqual(int(agent["endpoint_port"]), port)
        self.assertEqual(int(agent["pending_allocation"]), 0)
        shown = self._show_agent("ssh-access")
        # Port preservation is the contract under test; host display follows
        # resolve_public_endpoint_host and must not require invented drlink.local.
        self.assertIn(":%s" % port, shown)
        self.assertNotIn("Pending allocation", shown)

    def test_DEPENDENCY_INVALID_NO_REALLOCATION(self):
        self._write_registry(
            {
                ROCKY8: {
                    "hostname": "real-e2e-rocky8",
                    "services": {
                        "ssh": {"remote_port": 6001, "enabled": True, "local_port": 22}
                    },
                }
            },
            reserved=[6001],
        )
        self._seed_server_service("e2e-net", "db-prod", 6001)
        self._seed_agent_service("e2e-net", "db-prod", 6001)
        os.environ["DRLINK_SERVER_REACHABLE"] = "1"
        v24.synchronize_agent_remote_services(self.agent, root=self.agent_tmp)
        server = self._server_row("e2e-net")
        self.assertEqual(server["status"], "DEGRADED")
        self.assertIsNone(server["public_port"])
        agent = self._agent_row("e2e-net")
        self.assertIsNone(agent["endpoint_port"])
        self.assertEqual(int(agent["pending_allocation"]), 1)
        claimed = list(
            self.server.conn.execute(
                "SELECT public_port FROM published_services WHERE name = 'e2e-net' "
                "AND released = 0 AND public_port IS NOT NULL"
            )
        )
        self.assertEqual(claimed, [])
        os.environ.pop("DRLINK_SERVER_REACHABLE", None)

    def test_STATUS_RECOVERY_ENDPOINT_SYNC(self):
        self._write_registry(
            {
                ROCKY8: {
                    "hostname": "real-e2e-rocky8",
                    "services": {
                        "ssh": {"remote_port": 6001, "enabled": True, "local_port": 22}
                    },
                }
            },
            reserved=[6001],
        )
        self._seed_server_service("e2e-net", "db-prod", 6001)
        self._seed_agent_service("e2e-net", "db-prod", 6001)
        os.environ["DRLINK_SERVER_REACHABLE"] = "1"
        v24.synchronize_agent_remote_services(self.agent, root=self.agent_tmp)
        self.assertIsNone(self._agent_row("e2e-net")["endpoint_port"])
        v24.set_network_object(
            self.server, "db-prod", type="ip", value="198.51.100.20", oneshot=True
        )
        v24.synchronize_agent_remote_services(self.agent, root=self.agent_tmp)
        agent = self._agent_row("e2e-net")
        self.assertIsNotNone(agent["endpoint_port"])
        self.assertNotEqual(int(agent["endpoint_port"]), 6001)
        self.assertEqual(int(agent["pending_allocation"]), 0)
        # Restored Network Object is a routed destination that is not listening.
        # Proxy registration success must not be reported as HEALTHY.
        self.assertEqual(agent["status"], "DEGRADED")
        self.assertIn("unreachable", (agent["reason"] or "").lower())
        server = self._server_row("e2e-net")
        self.assertEqual(int(server["public_port"]), int(agent["endpoint_port"]))
        self.assertEqual(server["status"], "DEGRADED")
        shown = self._show_agent("e2e-net")
        self.assertIn("DEGRADED", shown)
        endpoint_host = str(agent["endpoint_host"] or "").strip()
        self.assertTrue(endpoint_host)
        self.assertNotEqual(endpoint_host, "drlink.local")
        self.assertIn("%s:%s" % (endpoint_host, agent["endpoint_port"]), shown)
        os.environ.pop("DRLINK_SERVER_REACHABLE", None)

    def test_AGENT_STATUS_COUNTS_LOCAL_REMOTE_SERVICES(self):
        v24.ensure_v2_schema(self.agent.conn)
        self.agent.conn.execute(
            "INSERT INTO agent_remote_services("
            "name, destination, service_object, enabled, status, pending_allocation, "
            "delete_pending, pool_class, reason, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "ssh-access",
                "this-host",
                "ssh",
                1,
                "HEALTHY",
                0,
                0,
                "normal",
                "",
                "2026-09-19T00:00:00Z",
            ),
        )
        self.agent.conn.commit()
        out = self.agent.format_status()
        self.assertIn("Role: Agent Host", out)
        # Agent-role status uses single-space alignment for this longer label.
        self.assertIn("Remote Services : 1", out)
        self.assertNotIn("Role: Unknown", out)


class MacosRoleDetectionTests(unittest.TestCase):
    def test_macos_application_support_layout_is_agent(self):
        tmp = tempfile.mkdtemp(prefix="drlink-macos-role-")
        state = Path(tmp) / "Library/Application Support/drlink"
        state.mkdir(parents=True)
        (state / "client-state.json").write_text(
            '{"machine_id":"%s","hostname":"mac-agent"}\n' % MACHINE,
            encoding="utf-8",
        )
        (state / "frpc.toml").write_text("[common]\n", encoding="utf-8")
        self.assertEqual(v24.detect_cli_role(tmp), "agent")
        self.assertEqual(v24.role_label(v24.detect_cli_role(tmp)), "Agent Host")
        from drlink_control_db import deploy_root_from_db_path, select_live_control_db

        prev = os.environ.pop("FRP_MACOS_STATE_ROOT", None)
        try:
            db = select_live_control_db(Path(tmp))
        finally:
            if prev is not None:
                os.environ["FRP_MACOS_STATE_ROOT"] = prev
        self.assertEqual(
            db,
            Path(tmp) / "Library/Application Support/drlink/state/drlink.db",
        )
        self.assertEqual(deploy_root_from_db_path(db), tmp)
        self.assertEqual(v24.role_label("unknown"), "Unknown")
        self.assertNotEqual(v24.role_label(v24.detect_cli_role(tmp)), "Unknown")

    def test_macos_env_state_root_is_agent(self):
        tmp = tempfile.mkdtemp(prefix="drlink-macos-env-")
        state = Path(tmp) / "drlink-state"
        state.mkdir(parents=True)
        (state / "client-state.json").write_text("{}\n", encoding="utf-8")
        prev = os.environ.get("FRP_MACOS_STATE_ROOT")
        os.environ["FRP_MACOS_STATE_ROOT"] = str(state)
        try:
            self.assertEqual(v24.detect_cli_role("/nonexistent-root"), "agent")
        finally:
            if prev is None:
                os.environ.pop("FRP_MACOS_STATE_ROOT", None)
            else:
                os.environ["FRP_MACOS_STATE_ROOT"] = prev

    def test_macos_flat_state_resolves_server_endpoint_and_mgmt_url(self):
        tmp = tempfile.mkdtemp(prefix="drlink-macos-ep-")
        state = Path(tmp) / "drlink-state"
        state.mkdir(parents=True)
        (state / "client-state.json").write_text(
            json.dumps(
                {
                    "machine_id": MACHINE,
                    "hostname": "mac-agent",
                    "allocator_url": "https://221.139.249.113:6099/enroll",
                    "frp_server": "221.139.249.113",
                    "frp_server_port": 443,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (state / "frpc.toml").write_text(
            'serverAddr = "221.139.249.113"\nserverPort = 443\n', encoding="utf-8"
        )
        (state / "allocator-ca.crt").write_text("dummy-ca\n", encoding="utf-8")
        (state / "client-identity.key").write_text("dummy-key\n", encoding="utf-8")
        (state / "client-identity.mac").write_text("dummy-mac\n", encoding="utf-8")
        prev = os.environ.get("FRP_MACOS_STATE_ROOT")
        os.environ["FRP_MACOS_STATE_ROOT"] = str(state)
        try:
            self.assertEqual(
                v24.load_agent_server_endpoint("/nonexistent-root"),
                ("221.139.249.113", 6099),
            )
            self.assertEqual(
                mgmt.resolve_mgmt_base_url("/nonexistent-root"),
                "https://221.139.249.113:6099",
            )
            self.assertEqual(
                mgmt.allocator_ca_path("/nonexistent-root"),
                state / "allocator-ca.crt",
            )
            ident = v24.load_agent_identity("/nonexistent-root")
            self.assertEqual(ident.get("machine_id"), MACHINE)
            self.assertEqual(
                v24.agent_identity_key_path("/nonexistent-root"),
                state / "client-identity.key",
            )
            self.assertEqual(
                v24.agent_identity_mac_path("/nonexistent-root"),
                state / "client-identity.mac",
            )
            import drlink_v24_runtime as runtime

            loaded = runtime.load_client_state("/nonexistent-root")
            self.assertEqual(loaded.get("machine_id"), MACHINE)
            self.assertEqual(runtime._frpc_toml_path("/nonexistent-root"), state / "frpc.toml")
        finally:
            if prev is None:
                os.environ.pop("FRP_MACOS_STATE_ROOT", None)
            else:
                os.environ["FRP_MACOS_STATE_ROOT"] = prev


class FalseHealthyFailClosedTests(unittest.TestCase):
    """P0-B: Server HEALTHY requires current verified runtime evidence."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-false-healthy-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server","public_ip":"203.0.113.10"}\n', encoding="utf-8"
        )
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        self.plane.upsert_client(MACHINE, label="agent-a", hostname="agent-a", connected=True)

    def tearDown(self):
        self.plane.close()
        for key in ("DRLINK_SKIP_ACTIVATION", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def _seed_stored_healthy(self, *, port: int = 6012, connected: bool = True):
        self.plane.upsert_client(
            MACHINE, label="agent-a", hostname="agent-a", connected=connected
        )
        self.plane.set_published_service(
            MACHINE,
            "ssh-access",
            service_type="tcp",
            target_mode="self",
            target_host="127.0.0.1",
            target_port=22,
            enabled=True,
            public_port=port,
        )
        pub = self.plane.conn.execute(
            "SELECT * FROM published_services WHERE name = 'ssh-access'"
        ).fetchone()
        sobj = v24.get_service_object(self.plane, "ssh")
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO remote_service_meta"
            "(service_id, status, pool_class, service_object_id, destination_name, "
            "pending_allocation, delete_pending, reason) "
            "VALUES (?, 'HEALTHY', 'normal', ?, 'this-host', 0, 0, '')",
            (pub["id"], sobj["id"]),
        )
        self.plane.conn.commit()
        meta = self.plane.conn.execute(
            "SELECT * FROM remote_service_meta WHERE service_id = ?", (pub["id"],)
        ).fetchone()
        return pub, meta

    def test_stored_healthy_without_runtime_is_degraded(self):
        pub, meta = self._seed_stored_healthy()
        status, reason, stale = UR.effective_remote_service_status(
            self.plane, pub, meta, {}, registry_available=False
        )
        self.assertEqual(status, "DEGRADED")
        self.assertIn("verification", reason.lower())
        self.assertFalse(stale)

    def test_reboot_reconnect_without_verified_runtime_not_healthy(self):
        # Simulate reboot: prior HEALTHY remains stored while the host reconnects,
        # before any current verified runtime report arrives.
        pub, meta = self._seed_stored_healthy(connected=False)
        status, reason, _ = UR.effective_remote_service_status(
            self.plane, pub, meta, {}, registry_available=False
        )
        self.assertEqual(status, "DEGRADED")
        self.assertIn("offline", reason.lower())

        self.plane.upsert_client(MACHINE, label="agent-a", hostname="agent-a", connected=True)
        pub = self.plane.conn.execute(
            "SELECT * FROM published_services WHERE name = 'ssh-access'"
        ).fetchone()
        meta = self.plane.conn.execute(
            "SELECT * FROM remote_service_meta WHERE service_id = ?", (pub["id"],)
        ).fetchone()
        status, reason, _ = UR.effective_remote_service_status(
            self.plane, pub, meta, {}, registry_available=False
        )
        self.assertEqual(status, "DEGRADED")
        self.assertIn("verification", reason.lower())
        self.assertNotEqual(status, "HEALTHY")

    def test_previously_verified_bit_cleared_on_disconnect_reconnect(self):
        # Audit #41 re-audit at 19cca2c: seed runtime_verified=1, disconnect,
        # reconnect with no fresh Agent report — operator display must stay
        # non-HEALTHY and the persisted verification bit must not survive.
        pub, _meta = self._seed_stored_healthy(connected=True)
        self.plane.conn.execute(
            "UPDATE remote_service_meta SET runtime_verified = 1, status = 'HEALTHY', "
            "reason = '' WHERE service_id = ?",
            (pub["id"],),
        )
        self.plane.conn.commit()
        client = self.plane.conn.execute(
            "SELECT * FROM clients WHERE id = ?", (MACHINE,)
        ).fetchone()
        meta = self.plane.conn.execute(
            "SELECT * FROM remote_service_meta WHERE service_id = ?", (pub["id"],)
        ).fetchone()
        self.assertEqual(int(meta["runtime_verified"] or 0), 1)
        self.assertEqual(
            v24.inventory_remote_service_status(
                self.plane,
                client,
                enabled=True,
                stored_status=meta["status"],
                runtime_verified=bool(meta["runtime_verified"]),
            ),
            "HEALTHY",
        )

        self.plane.upsert_client(MACHINE, label="agent-a", hostname="agent-a", connected=False)
        meta = self.plane.conn.execute(
            "SELECT * FROM remote_service_meta WHERE service_id = ?", (pub["id"],)
        ).fetchone()
        self.assertEqual(int(meta["runtime_verified"] or 0), 0)
        client = self.plane.conn.execute(
            "SELECT * FROM clients WHERE id = ?", (MACHINE,)
        ).fetchone()
        self.assertNotEqual(
            v24.inventory_remote_service_status(
                self.plane,
                client,
                enabled=True,
                stored_status=meta["status"],
                runtime_verified=bool(meta["runtime_verified"]),
            ),
            "HEALTHY",
        )

        self.plane.upsert_client(MACHINE, label="agent-a", hostname="agent-a", connected=True)
        meta = self.plane.conn.execute(
            "SELECT * FROM remote_service_meta WHERE service_id = ?", (pub["id"],)
        ).fetchone()
        self.assertEqual(int(meta["runtime_verified"] or 0), 0)
        client = self.plane.conn.execute(
            "SELECT * FROM clients WHERE id = ?", (MACHINE,)
        ).fetchone()
        shown = v24.inventory_remote_service_status(
            self.plane,
            client,
            enabled=True,
            stored_status=meta["status"],
            runtime_verified=bool(meta["runtime_verified"]),
        )
        self.assertEqual(shown, "DEGRADED")
        self.assertNotEqual(shown, "HEALTHY")
        status, reason, _ = UR.effective_remote_service_status(
            self.plane, pub, meta, {}, registry_available=False
        )
        self.assertEqual(status, "DEGRADED")
        self.assertIn("verification", reason.lower())

    def test_listener_delay_unverified_healthy_claim_is_degraded(self):
        pub, meta = self._seed_stored_healthy()
        status, reason, _ = UR.effective_remote_service_status(
            self.plane,
            pub,
            meta,
            {},
            agent_runtime={
                "status": "HEALTHY",
                "runtime_verified": False,
                "reason": "",
            },
            registry_available=False,
        )
        self.assertEqual(status, "DEGRADED")
        self.assertIn("verification", reason.lower())

    def test_stale_runtime_evidence_without_current_report_is_degraded(self):
        pub, meta = self._seed_stored_healthy()
        # First a current verified report may produce HEALTHY.
        status, reason, _ = UR.effective_remote_service_status(
            self.plane,
            pub,
            meta,
            {},
            agent_runtime={
                "status": "HEALTHY",
                "runtime_verified": True,
                "reason": "",
            },
            registry_available=False,
        )
        self.assertEqual(status, "HEALTHY")
        self.assertEqual(reason, "")

        # Later evaluation without a current verified report must not keep HEALTHY
        # from stored meta alone (no invented verification TTL).
        status, reason, _ = UR.effective_remote_service_status(
            self.plane, pub, meta, {}, registry_available=False
        )
        self.assertEqual(status, "DEGRADED")
        self.assertIn("verification", reason.lower())

    def test_verified_runtime_report_may_be_healthy(self):
        pub, meta = self._seed_stored_healthy()
        # Verified HEALTHY still requires an endpoint reservation.
        self.plane.conn.execute(
            "UPDATE published_services SET public_port = NULL WHERE name = 'ssh-access'"
        )
        self.plane.conn.commit()
        pub = self.plane.conn.execute(
            "SELECT * FROM published_services WHERE name = 'ssh-access'"
        ).fetchone()
        meta = self.plane.conn.execute(
            "SELECT * FROM remote_service_meta WHERE service_id = ?", (pub["id"],)
        ).fetchone()
        status, reason, _ = UR.effective_remote_service_status(
            self.plane,
            pub,
            meta,
            {},
            agent_runtime={
                "status": "HEALTHY",
                "runtime_verified": True,
                "reason": "",
            },
            registry_available=False,
        )
        self.assertEqual(status, "DEGRADED")
        self.assertTrue(reason)

        pub, meta = self._seed_stored_healthy(port=6015)
        status, reason, _ = UR.effective_remote_service_status(
            self.plane,
            pub,
            meta,
            {},
            agent_runtime={
                "status": "HEALTHY",
                "runtime_verified": True,
                "reason": "",
            },
            registry_available=False,
        )
        self.assertEqual(status, "HEALTHY")
        self.assertEqual(reason, "")

    def test_target_outage_without_agent_report_does_not_invent_target_health(self):
        # Without a configured target health_check, Server has no target-health
        # signal. Re-evaluation without an Agent runtime report must fail closed
        # for missing runtime verification, not invent a target-health verdict.
        pub, meta = self._seed_stored_healthy()
        status, reason, _ = UR.effective_remote_service_status(
            self.plane, pub, meta, {}, registry_available=False
        )
        self.assertEqual(status, "DEGRADED")
        self.assertIn("verification", reason.lower())
        self.assertNotIn("target", reason.lower())
        self.assertNotIn("health_check", reason.lower())

    def test_inventory_connected_stored_healthy_without_verification_not_healthy(self):
        # Comment 5883033202: show managed-host remote-services uses inventory,
        # not effective_remote_service_status. Stored HEALTHY + connected alone
        # must not display HEALTHY without current runtime verification.
        pub, meta = self._seed_stored_healthy()
        client = self.plane.conn.execute(
            "SELECT * FROM clients WHERE id = ?", (MACHINE,)
        ).fetchone()
        self.assertEqual(self.plane.managed_host_connectivity(client), "connected")
        shown = v24.inventory_remote_service_status(
            self.plane,
            client,
            enabled=True,
            stored_status="HEALTHY",
            runtime_verified=False,
        )
        self.assertNotEqual(shown, "HEALTHY")
        self.assertEqual(shown, "DEGRADED")
        # Verified evidence may display HEALTHY.
        self.assertEqual(
            v24.inventory_remote_service_status(
                self.plane,
                client,
                enabled=True,
                stored_status="HEALTHY",
                runtime_verified=True,
            ),
            "HEALTHY",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.dispatch(
                ["show", "managed-host", "agent-a", "remote-services"],
                root=self.tmp,
                plane=self.plane,
            )
        self.assertEqual(rc, 0, buf.getvalue())
        listing = buf.getvalue()
        self.assertIn("ssh-access", listing)
        self.assertNotIn("HEALTHY", listing)
        self.assertIn("DEGRADED", listing)


class AgentPushFalseHealthyTests(unittest.TestCase):
    """P0-B: Agent status push must not manufacture runtime_verified from HEALTHY."""

    def setUp(self):
        self.server_tmp = tempfile.mkdtemp(prefix="drlink-push-srv-")
        self.agent_tmp = tempfile.mkdtemp(prefix="drlink-push-agt-")
        Path(self.server_tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.server_tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_CONFIRM"] = "yes"
        os.environ.pop("DRLINK_MGMT_TOKEN", None)
        self.server = ControlPlane(self.server_tmp)
        v24.ensure_v2_schema(self.server.conn)
        v24.set_service_object(self.server, "ssh", type="tcp", port=22, oneshot=True)
        self.key, self.pub, self.mac = _write_identity(Path(self.agent_tmp), MACHINE, "agent-a")
        self.server.upsert_client(MACHINE, label="agent-a", hostname="agent-a")
        self.verifier = mgmt.InMemoryMgmtVerifier()
        self.verifier.enroll(MACHINE, self.pub, mac_key=self.mac, hostname="agent-a")
        self.httpd, self.base, _ = mgmt.start_mgmt_server(self.server, verifier=self.verifier)
        os.environ["DRLINK_MGMT_URL"] = self.base
        Path(self.agent_tmp, "etc/frp/server-endpoint.json").write_text(
            '{"mgmt_url":"%s"}\n' % self.base, encoding="utf-8"
        )
        self.agent = ControlPlane(self.agent_tmp)
        v24.ensure_v2_schema(self.agent.conn)

    def tearDown(self):
        mgmt.stop_mgmt_server(self.httpd)
        self.server.close()
        self.agent.close()
        for key in ("DRLINK_SKIP_ACTIVATION", "DRLINK_CONFIRM", "DRLINK_MGMT_URL"):
            os.environ.pop(key, None)

    def _server_status(self, name: str):
        return self.server.conn.execute(
            "SELECT m.status, m.reason, m.runtime_verified, s.public_port FROM published_services s "
            "JOIN remote_service_meta m ON m.service_id = s.id WHERE s.name = ?",
            (name,),
        ).fetchone()

    def test_push_persisted_healthy_without_verification_cannot_make_server_healthy(self):
        # Comment 5883013721: preserve Agent local HEALTHY text but remove current
        # runtime verification evidence; status push must not promote Server HEALTHY.
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        self.assertEqual(created["status"], "HEALTHY")
        port = int(created["endpoint_port"])
        now = "2026-09-18T00:00:00Z"
        self.agent.conn.execute(
            "INSERT OR REPLACE INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, runtime_verified, updated_at) "
            "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'HEALTHY', 'drlink.local', ?, 0, 0, "
            "'normal', '', 0, ?)",
            (port, now),
        )
        self.agent.conn.commit()
        row = self.agent.conn.execute(
            "SELECT status, runtime_verified FROM agent_remote_services WHERE name = 'ssh-access'"
        ).fetchone()
        self.assertEqual(row["status"], "HEALTHY")
        self.assertEqual(int(row["runtime_verified"] or 0), 0)

        pushed = v24._push_agent_remote_service_status(self.agent, root=self.agent_tmp)
        self.assertGreaterEqual(pushed, 1)
        server = self._server_status("ssh-access")
        self.assertNotEqual(server["status"], "HEALTHY")
        self.assertEqual(server["status"], "DEGRADED")
        self.assertEqual(int(server["runtime_verified"] or 0), 0)

        client = self.server.conn.execute(
            "SELECT * FROM clients WHERE id = ?", (MACHINE,)
        ).fetchone()
        shown = v24.inventory_remote_service_status(
            self.server,
            client,
            enabled=True,
            stored_status=server["status"],
            runtime_verified=bool(server["runtime_verified"]),
        )
        self.assertNotEqual(shown, "HEALTHY")

    def test_push_after_real_verification_may_keep_healthy(self):
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        port = int(created["endpoint_port"])
        now = "2026-09-18T00:00:00Z"
        self.agent.conn.execute(
            "INSERT OR REPLACE INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, runtime_verified, updated_at) "
            "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'HEALTHY', 'drlink.local', ?, 0, 0, "
            "'normal', '', 1, ?)",
            (port, now),
        )
        self.agent.conn.commit()
        v24._push_agent_remote_service_status(self.agent, root=self.agent_tmp)
        server = self._server_status("ssh-access")
        self.assertEqual(server["status"], "HEALTHY")
        self.assertEqual(int(server["runtime_verified"] or 0), 1)

    def test_synchronize_clears_verification_before_pre_apply_push(self):
        # Audit #41: synchronize must not replay persisted runtime_verified=1
        # on the pre-apply status push before fresh runtime verification.
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        port = int(created["endpoint_port"])
        now = "2026-09-18T00:00:00Z"
        self.agent.conn.execute(
            "INSERT OR REPLACE INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, runtime_verified, updated_at) "
            "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'HEALTHY', 'drlink.local', ?, 0, 0, "
            "'normal', '', 1, ?)",
            (port, now),
        )
        self.agent.conn.commit()

        seen_verified = []
        real_push = v24._push_agent_remote_service_status

        def spy_push(plane_db, *, root=None, names=None):
            row = plane_db.conn.execute(
                "SELECT runtime_verified FROM agent_remote_services WHERE name = 'ssh-access'"
            ).fetchone()
            seen_verified.append(int(row["runtime_verified"] or 0))
            return real_push(plane_db, root=root, names=names)

        original = v24._push_agent_remote_service_status
        v24._push_agent_remote_service_status = spy_push
        try:
            v24.synchronize_agent_remote_services(self.agent, root=self.agent_tmp)
        finally:
            v24._push_agent_remote_service_status = original

        self.assertGreaterEqual(len(seen_verified), 1)
        self.assertEqual(seen_verified[0], 0)

    def test_public_restart_invalidation_clears_verified_and_server_healthy(self):
        # Comment 5883274697: public system restart shell path must invalidate
        # local verification and must not leave Server HEALTHY.
        created = mgmt.upsert_remote_service_on_server(
            root=self.agent_tmp,
            name="ssh-access",
            destination="this-host",
            service="ssh",
            enabled=True,
            pool_class="normal",
            target_host="127.0.0.1",
            target_port=22,
            target_mode="self",
            runtime_verified=True,
        )
        port = int(created["endpoint_port"])
        now = "2026-09-18T00:00:00Z"
        self.agent.conn.execute(
            "INSERT OR REPLACE INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, runtime_verified, updated_at) "
            "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'HEALTHY', 'drlink.local', ?, 0, 0, "
            "'normal', '', 1, ?)",
            (port, now),
        )
        self.agent.conn.commit()
        self.agent.close()

        result = v24.invalidate_runtime_verification_for_restart(root=self.agent_tmp)
        self.assertGreaterEqual(int(result.get("cleared") or 0), 1)

        self.agent = ControlPlane(self.agent_tmp)
        v24.ensure_v2_schema(self.agent.conn)
        row = self.agent.conn.execute(
            "SELECT status, runtime_verified FROM agent_remote_services WHERE name = 'ssh-access'"
        ).fetchone()
        self.assertEqual(int(row["runtime_verified"] or 0), 0)
        self.assertNotEqual(str(row["status"] or "").upper(), "HEALTHY")

        server = self._server_status("ssh-access")
        self.assertNotEqual(server["status"], "HEALTHY")
        self.assertEqual(int(server["runtime_verified"] or 0), 0)


class PublicRestartShellPathTests(unittest.TestCase):
    """P0-B: frp_client_restart_runtime_cmd must invalidate verification."""

    def test_shell_restart_cmd_clears_agent_runtime_verified(self):
        import subprocess

        with tempfile.TemporaryDirectory(prefix="drlink-restart-shell-") as tmp:
            root = Path(tmp)
            (root / "etc/drlink").mkdir(parents=True)
            (root / "etc/drlink/config.json").write_text(
                '{"role":"agent"}\n', encoding="utf-8"
            )
            (root / "var/lib/drlink").mkdir(parents=True)
            agent = ControlPlane(str(root))
            v24.ensure_v2_schema(agent.conn)
            agent.conn.execute(
                "INSERT OR REPLACE INTO agent_remote_services"
                "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
                "pending_allocation, delete_pending, pool_class, reason, runtime_verified, updated_at) "
                "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'HEALTHY', 'drlink.local', 6012, 0, 0, "
                "'normal', '', 1, '2026-09-18T00:00:00Z')"
            )
            agent.conn.commit()
            agent.close()

            env = os.environ.copy()
            env["FRP_CLIENT_TEST_ROOT"] = str(root)
            env["FRP_SKIP_SYSTEMD"] = "1"
            env["PYTHONPATH"] = str(ROOT / "lib") + (
                (os.pathsep + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""
            )
            script = r"""
set -euo pipefail
. lib/frp-common.sh
. lib/frp-client-common.sh
frp_client_restart_runtime_cmd
"""
            proc = subprocess.run(
                ["bash", "-c", script],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("Agent restarted.", proc.stdout)

            plane = ControlPlane(str(root))
            v24.ensure_v2_schema(plane.conn)
            row = plane.conn.execute(
                "SELECT status, runtime_verified FROM agent_remote_services WHERE name = 'ssh-access'"
            ).fetchone()
            plane.close()
            self.assertEqual(int(row["runtime_verified"] or 0), 0)
            self.assertNotEqual(str(row["status"] or "").upper(), "HEALTHY")

    def test_linux_unit_has_verification_invalidation_prestart(self):
        text = (ROOT / "client" / "drlink-client.service").read_text(encoding="utf-8")
        self.assertIn("ExecStartPre=", text)
        self.assertIn("invalidate_runtime_verification_for_restart", text)

    def test_macos_plist_uses_frpc_launch_wrapper(self):
        text = (ROOT / "client" / "com.datarelay.drlink.frpc.plist").read_text(
            encoding="utf-8"
        )
        self.assertIn("@LAUNCHER@", text)
        self.assertIn("drlink-frpc-launch", (ROOT / "client" / "drlink-frpc-launch").read_text(encoding="utf-8"))
        launcher = ROOT / "client" / "drlink-frpc-launch"
        self.assertTrue(launcher.is_file())
        self.assertIn("invalidate_runtime_verification_for_restart", launcher.read_text(encoding="utf-8"))


class AgentLifecycleWorkerTests(unittest.TestCase):
    def test_pause_intent_is_not_reported_critical(self):
        from drlink_agent_lifecycle import set_lifecycle_intent

        with tempfile.TemporaryDirectory(prefix="drlink-paused-intent-") as tmp:
            set_lifecycle_intent("paused", tmp)
            os.environ["DRLINK_TEST_RUNTIME_UNIT"] = "inactive"
            try:
                view = v24.probe_agent_runtime_unit(root=tmp)
                self.assertEqual(view["level"], "Paused")
                self.assertIn("intentionally paused", view["detail"])
                os.environ["DRLINK_TEST_RUNTIME_UNIT"] = "active"
                view = v24.probe_agent_runtime_unit(root=tmp)
                self.assertEqual(view["level"], "Warning")
            finally:
                os.environ.pop("DRLINK_TEST_RUNTIME_UNIT", None)

    def test_worker_heartbeats_then_synchronizes_only_when_needed(self):
        from unittest import mock
        import drlink_agent_lifecycle as lifecycle

        with tempfile.TemporaryDirectory(prefix="drlink-lifecycle-worker-") as tmp:
            root = Path(tmp)
            (root / "etc/drlink").mkdir(parents=True)
            (root / "etc/drlink/config.json").write_text(
                '{"role":"agent"}\n', encoding="utf-8"
            )
            plane = ControlPlane(tmp)
            v24.ensure_v2_schema(plane.conn)
            plane.close()
            lifecycle.set_lifecycle_intent("running", tmp)

            with mock.patch(
                "drlink_mgmt_sync.report_agent_lifecycle_on_server",
                return_value={"ok": True, "state": "connected"},
            ) as heartbeat, mock.patch(
                "drlink_v24.synchronize_agent_remote_services"
            ) as sync:
                result = lifecycle.reconcile_once(tmp)
                self.assertEqual(result["status"], "HEARTBEAT")
                heartbeat.assert_called_once()
                sync.assert_not_called()

            with mock.patch(
                "drlink_mgmt_sync.report_agent_lifecycle_on_server",
                return_value={"ok": True, "state": "connected", "reconcile_required": True},
            ), mock.patch(
                "drlink_v24.synchronize_agent_remote_services",
                return_value={"status": "SYNCHRONIZED", "updated": 0},
            ) as forced_sync:
                result = lifecycle.reconcile_once(tmp)
                self.assertEqual(result["status"], "SYNCHRONIZED")
                forced_sync.assert_called_once()

            plane = ControlPlane(tmp)
            v24.ensure_v2_schema(plane.conn)
            plane.conn.execute(
                "INSERT OR REPLACE INTO agent_remote_services"
                "(name, destination, service_object, enabled, status, pending_allocation, "
                "delete_pending, pool_class, reason, runtime_verified, updated_at) "
                "VALUES ('pending', 'this-host', 'ssh', 1, 'DEGRADED', 1, 0, "
                "'normal', 'Server unreachable.', 0, '2026-10-01T00:00:00Z')"
            )
            plane.conn.commit()
            plane.close()
            with mock.patch(
                "drlink_mgmt_sync.report_agent_lifecycle_on_server",
                return_value={"ok": True, "state": "connected"},
            ) as heartbeat, mock.patch(
                "drlink_v24.synchronize_agent_remote_services",
                return_value={"status": "SYNCHRONIZED", "updated": 1},
            ) as sync:
                result = lifecycle.reconcile_once(tmp)
                self.assertEqual(result["status"], "SYNCHRONIZED")
                heartbeat.assert_called_once()
                sync.assert_called_once()

    def test_paused_worker_does_not_touch_server(self):
        from unittest import mock
        import drlink_agent_lifecycle as lifecycle

        with tempfile.TemporaryDirectory(prefix="drlink-lifecycle-paused-") as tmp:
            lifecycle.set_lifecycle_intent("paused", tmp)
            with mock.patch(
                "drlink_agent_lifecycle.heartbeat_once"
            ) as heartbeat, mock.patch(
                "drlink_v24.synchronize_agent_remote_services"
            ) as sync:
                result = lifecycle.reconcile_once(tmp)
                self.assertEqual(result["status"], "PAUSED")
                heartbeat.assert_not_called()
                sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
