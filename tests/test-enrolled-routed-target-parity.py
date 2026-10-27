#!/usr/bin/env python3
"""Regression: Zero-Touch LAN targets remain authoritative through v2.4 migration.

Reproduces the public 6000/6001/6002 failure without network access:
an enrolled non-loopback target must not be aliased to this-host.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
if not LIB.is_dir():
    LIB = Path("/usr/local/lib/drlink")
sys.path.insert(0, str(LIB))

from drlink_control_plane import ControlPlane  # noqa: E402
import drlink_v24 as v24  # noqa: E402
import drlink_runtime_policy as rp  # noqa: E402
import drlink_upgrade_reconcile as ur  # noqa: E402
import drlink_v24_runtime as runtime  # noqa: E402

CLIENT = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
PUBLIC = "203.0.113.10"
LAN = "10.22.33.44"


def enrolled_services():
    return {
        "ssh": dict(id="ssh", name="SSH", preset="ssh", local_ip="127.0.0.1",
                    local_port=22, remote_port=6000, enabled=True),
        "aio-ssh": dict(id="aio-ssh", name="LAN SSH", preset="ssh", local_ip=LAN,
                        local_port=22, remote_port=6001, enabled=True),
        "https": dict(id="https", name="LAN HTTPS", preset="https", local_ip=LAN,
                      local_port=443, remote_port=6002, enabled=True),
    }


class EnrollmentRoutedTargetParity(unittest.TestCase):
    def setUp(self):
        self._orig = {key: os.environ.get(key) for key in
                      ("FRP_DEPLOY_TEST_ROOT", "DRLINK_SKIP_ACTIVATION", "DRLINK_CONFIRM")}
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-bootstrap-target-")
        self.addCleanup(self.temp.cleanup)
        self.server_root = str(Path(self.temp.name) / "server")
        self.agent_root = str(Path(self.temp.name) / "agent")
        for root, role in ((self.server_root, "server"), (self.agent_root, "agent")):
            p = Path(root, "etc/drlink")
            p.mkdir(parents=True)
            (p / "config.json").write_text(json.dumps({"role": role}) + "\n")
        state = {
            "schema_version": 1, "machine_id": CLIENT,
            "hostname": "drlink-agent", "label": "LAN Test Host",
            "frp_server": PUBLIC, "services": enrolled_services(),
        }
        p = Path(self.agent_root, "etc/frp")
        p.mkdir(parents=True)
        (p / "client-state.json").write_text(json.dumps(state) + "\n")
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_CONFIRM"] = "yes"
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.server_root
        self.server = ControlPlane(self.server_root)
        v24.ensure_v2_schema(self.server.conn)
        self.addCleanup(self.server.close)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._orig.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _publish(self):
        return rp.sync_enrolled_client(
            self.server, client_id=CLIENT, hostname="drlink-agent",
            label="LAN Test Host", services=enrolled_services(),
            addresses=[{"address": "198.51.100.10", "active": True}],
        )

    def _server_rows(self):
        return [dict(r) for r in self.server.conn.execute(
            "SELECT s.name, s.public_port, s.target_host, s.target_mode, "
            "m.destination_name, m.destination_client_id, m.service_object_id, "
            "s.id AS published_id "
            "FROM published_services s JOIN remote_service_meta m ON m.service_id=s.id "
            "WHERE s.released=0 ORDER BY s.public_port"
        )]

    def test_all_enrollment_paths_share_the_deployed_canonical_target_name(self):
        # PR220 historically emitted 24 hex digits while PR222's independent
        # helper emitted 20. Their individually green suites cannot prove the
        # merged Server and Agent refer to the same Network Object.
        for target in (LAN, "::1", "2001:db8::20", "App.Example.test"):
            with self.subTest(target=target):
                normalized, expected = v24.enrolled_destination_reference(target)
                self.assertEqual(v24.enrolled_target_object_name(target), expected)
                self.assertEqual(len(expected.split("enrolled-target-", 1)[1]), 24)
                _, actual = v24.ensure_enrolled_destination_object(self.server, target)
                self.assertEqual(actual, expected)
        for loopback in ("127.0.0.1", "localhost"):
            self.assertIsNone(v24.enrolled_target_object_name(loopback))

    def test_enrollment_lan_targets_are_bound_not_self(self):
        self._publish()
        rows = self._server_rows()
        self.assertEqual([(r["public_port"], r["target_host"]) for r in rows], [
            (6000, "127.0.0.1"), (6001, LAN), (6002, LAN)])
        self.assertEqual(rows[0]["destination_name"], "this-host")
        self.assertEqual(rows[0]["target_mode"], "self")
        self.assertIsNotNone(rows[0]["destination_client_id"])
        for row in rows[1:]:
            self.assertEqual(row["target_mode"], "routed")
            self.assertIsNone(row["destination_client_id"])
            self.assertNotEqual(row["destination_name"], "this-host")
            name = row["destination_name"]
            obj = self.server.get_object(name)
            self.assertIsNotNone(obj)
            self.assertEqual(self.server._object_values(obj["id"]), [LAN])
            pub = self.server.conn.execute(
                "SELECT * FROM published_services WHERE id=?", (row["published_id"],)
            ).fetchone()
            meta = self.server.conn.execute(
                "SELECT * FROM remote_service_meta WHERE service_id=?",
                (row["published_id"],),
            ).fetchone()
            self.assertIsNone(ur.server_target_projection_reason(self.server, pub, meta))
        self.assertEqual(rows[1]["destination_name"], rows[2]["destination_name"])

    def test_agent_seed_matches_server_and_preserves_ports(self):
        self._publish()
        self.agent = ControlPlane(self.agent_root)
        self.addCleanup(self.agent.close)
        v24.ensure_v2_schema(self.agent.conn)
        seed = v24.project_enrolled_services_into_agent_catalog(self.agent, root=self.agent_root)
        self.assertEqual(len(seed), 3)
        server_rows = {x["name"]: x for x in self._server_rows()}
        for r in self.agent.conn.execute(
            "SELECT name, destination, destination_client_id, endpoint_port "
            "FROM agent_remote_services ORDER BY name"
        ):
            matching = server_rows[r["name"]]
            if r["name"] == "ssh":
                # The Agent shows its own hostname while the Server stores
                # this-host; both are the same immutable self binding.
                self.assertIn(r["destination"], ("this-host", "drlink-agent"))
            else:
                self.assertEqual(r["destination"], matching["destination_name"])
            self.assertEqual(r["destination_client_id"], matching["destination_client_id"])
            self.assertEqual(r["endpoint_port"], matching["public_port"])
        # Initial Agent intent is unverified until a signed Server catalog
        # supplies the authoritative Network Object. Model that successful
        # read without modifying either product's live state.
        for row in self._server_rows()[1:]:
            name = row["destination_name"]
            self.agent.conn.execute(
                "INSERT OR REPLACE INTO agent_object_catalog(kind,name,payload,synced_at) "
                "VALUES('network-object', ?, ?, '2026-01-01T00:00:00Z')",
                (name, json.dumps({"name": name, "type": "host", "values": [LAN]})),
            )
        self.agent.conn.commit()
        # Desired FRP now routes to the exact Server-authorized LAN IP.
        desired = runtime.build_desired_runtime_services(
            self.agent,
            json.loads(Path(self.agent_root, "etc/frp/client-state.json").read_text()),
            root=self.agent_root,
        )
        for service in ("aio-ssh", "https"):
            self.assertEqual(desired[runtime.remote_service_proxy_id(service)]["local_ip"], LAN)

    def test_repeat_enrollment_preserves_authorized_references(self):
        self._publish()
        first = self._server_rows()
        self._publish()
        second = self._server_rows()
        self.assertEqual(first, second)
        remote = second[1]["destination_name"]
        self.assertEqual(self.server.conn.execute(
            "SELECT count(*) FROM objects WHERE name=?", (remote,)
        ).fetchone()[0], 1)
        self.assertEqual(self.server.conn.execute(
            "SELECT count(*) FROM object_values WHERE object_id=(SELECT id FROM objects WHERE name=?)",
            (remote,)
        ).fetchone()[0], 1)

    def test_upgrade_repairs_only_exact_legacy_self_bound_lan_targets(self):
        self._publish()
        for name in ("aio-ssh", "https"):
            self.server.conn.execute(
                "UPDATE published_services SET target_mode='self' "
                "WHERE name=? AND client_id=?", (name, CLIENT),
            )
            self.server.conn.execute(
                "UPDATE remote_service_meta SET destination_name='this-host', "
                "destination_client_id=?, status='DEGRADED', runtime_verified=0 "
                "WHERE service_id=(SELECT id FROM published_services "
                "WHERE name=? AND client_id=?)", (CLIENT, name, CLIENT),
            )
        registry = {"clients": {
            CLIENT: {"hostname": "drlink-agent", "services": enrolled_services()}
        }}
        self.assertEqual(
            len(ur.legacy_enrolled_lan_projection_repairs(self.server, registry)), 2
        )
        result = ur.apply_upgrade_reconciliation(self.server, registry)
        self.assertTrue(result.get("ok"), result)
        rows = self._server_rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["public_port"] for row in rows], [6000, 6001, 6002])
        for row in rows[1:]:
            self.assertEqual(row["target_mode"], "routed")
            self.assertNotEqual(row["destination_name"], "this-host")
            self.assertIsNone(row["destination_client_id"])
            pub = self.server.conn.execute(
                "SELECT * FROM published_services WHERE id=?",
                (row["published_id"],),
            ).fetchone()
            meta = self.server.conn.execute(
                "SELECT * FROM remote_service_meta WHERE service_id=?",
                (row["published_id"],),
            ).fetchone()
            self.assertIsNone(
                ur.server_target_projection_reason(self.server, pub, meta)
            )
        self.assertFalse(
            ur.legacy_enrolled_lan_projection_repairs(self.server, registry)
        )

    def test_agent_sync_repairs_only_untouched_bootstrap_seeds(self):
        self.agent = ControlPlane(self.agent_root)
        self.addCleanup(self.agent.close)
        v24.ensure_v2_schema(self.agent.conn)
        v24.project_enrolled_services_into_agent_catalog(
            self.agent, root=self.agent_root
        )
        for name in ("aio-ssh", "https"):
            self.agent.conn.execute(
                "UPDATE agent_remote_services SET destination='drlink-agent', "
                "destination_client_id=?, status='DEGRADED', runtime_verified=0 "
                "WHERE name=?", (CLIENT, name),
            )
        self.assertEqual(
            v24.repair_enrolled_lan_seed_destinations(
                self.agent, root=self.agent_root
            ), 2,
        )
        self.assertEqual(
            v24.repair_enrolled_lan_seed_destinations(
                self.agent, root=self.agent_root
            ), 0,
        )
        for name, port in (("aio-ssh", 6001), ("https", 6002)):
            row = self.agent.conn.execute(
                "SELECT * FROM agent_remote_services WHERE name=?", (name,)
            ).fetchone()
            self.assertEqual(row["destination"], v24.enrolled_target_object_name(LAN))
            self.assertIsNone(row["destination_client_id"])
            self.assertEqual(row["endpoint_port"], port)
            self.assertEqual(row["enrollment_seed"], 1)
        # Explicit operator changes invalidate seed provenance and never replay.
        self.agent.conn.execute(
            "UPDATE agent_remote_services SET enrollment_seed=0, destination='operator-target' "
            "WHERE name='aio-ssh'"
        )
        self.assertEqual(
            v24.repair_enrolled_lan_seed_destinations(
                self.agent, root=self.agent_root
            ), 0,
        )
        self.assertEqual(
            self.agent.conn.execute(
                "SELECT destination FROM agent_remote_services WHERE name='aio-ssh'"
            ).fetchone()["destination"], "operator-target",
        )

    def test_signed_server_ack_recovers_stale_legacy_self_seeds(self):
        # The old installed Agent recorded 127.0.0.1 for both LAN services,
        # even though the Server retained the signed LAN destination.
        self._publish()
        from drlink_mgmt_sync import MgmtAuthContext, server_report_remote_service_status
        state_file = Path(self.agent_root, "etc/frp/client-state.json")
        state = json.loads(state_file.read_text())
        for name in ("aio-ssh", "https"):
            state["services"][name]["local_ip"] = "127.0.0.1"
        state_file.write_text(json.dumps(state) + "\n")
        self.agent = ControlPlane(self.agent_root)
        self.addCleanup(self.agent.close)
        v24.ensure_v2_schema(self.agent.conn)
        v24.project_enrolled_services_into_agent_catalog(self.agent, root=self.agent_root)
        v24.sync_agent_catalog_from_server(
            self.agent, server_plane=self.server, root=self.agent_root
        )
        self.assertEqual(
            v24.repair_enrolled_lan_seed_destinations(self.agent, root=self.agent_root), 0
        )
        ack = server_report_remote_service_status(
            self.server,
            MgmtAuthContext(CLIENT, {"id": CLIENT}, "nonce", 1, allocator=None),
            {"services": [
                {"name": name, "status": "DEGRADED", "runtime_verified": False}
                for name in ("ssh", "aio-ssh", "https")
            ]},
        )
        by_name = {v["name"]: v for v in ack["services"]}
        self.assertEqual(by_name["aio-ssh"]["authoritative_target"]["host"], LAN)
        self.assertEqual(by_name["https"]["authoritative_target"]["host"], LAN)
        self.assertEqual(v24._reconcile_agent_from_server_status(self.agent, ack), 3)
        for name, port in (("aio-ssh", 6001), ("https", 6002)):
            row = self.agent.conn.execute(
                "SELECT * FROM agent_remote_services WHERE name=?", (name,)
            ).fetchone()
            self.assertEqual(row["destination"], v24.enrolled_target_object_name(LAN))
            self.assertIsNone(row["destination_client_id"])
            self.assertEqual(row["endpoint_port"], port)
            self.assertEqual(row["status"], "DEGRADED")
            self.assertEqual(row["runtime_verified"], 0)
        self.assertEqual(
            self.agent.conn.execute(
                "SELECT destination FROM agent_remote_services WHERE name='ssh'"
            ).fetchone()[0], "drlink-agent",
        )
        desired = runtime.build_desired_runtime_services(
            self.agent, state, root=self.agent_root
        )
        for name in ("aio-ssh", "https"):
            self.assertEqual(desired[runtime.remote_service_proxy_id(name)]["local_ip"], LAN)

    def test_signed_lan_recovery_never_guesses_or_overwrites_operator_edits(self):
        self._publish()
        from drlink_mgmt_sync import MgmtAuthContext, server_report_remote_service_status
        path = Path(self.agent_root, "etc/frp/client-state.json")
        state = json.loads(path.read_text())
        for name in ("aio-ssh", "https"):
            state["services"][name]["local_ip"] = "127.0.0.1"
        path.write_text(json.dumps(state) + "\n")
        agent = ControlPlane(self.agent_root)
        self.addCleanup(agent.close)
        v24.ensure_v2_schema(agent.conn)
        v24.project_enrolled_services_into_agent_catalog(agent, root=self.agent_root)
        v24.sync_agent_catalog_from_server(agent, server_plane=self.server, root=self.agent_root)
        # Explicit operator ownership must always take priority over the seed.
        agent.conn.execute(
            "UPDATE agent_remote_services SET enrollment_seed=0,destination='operator-target' "
            "WHERE name='aio-ssh'"
        )
        agent.conn.commit()
        ack = server_report_remote_service_status(
            self.server, MgmtAuthContext(CLIENT, {"id": CLIENT}, "nonce", 1, allocator=None),
            {"services": [{"name": name, "status": "DEGRADED", "runtime_verified": False}
                          for name in ("ssh", "aio-ssh", "https")]},
        )
        by_name = {r["name"]: r for r in ack["services"]}
        tampered = dict(by_name["https"])
        tampered["authoritative_target"] = dict(tampered["authoritative_target"])
        tampered["authoritative_target"]["host"] = "10.99.88.77"
        forged = {"services": [by_name["aio-ssh"], tampered, by_name["ssh"]]}
        v24._reconcile_agent_from_server_status(agent, forged)
        rows = {r["name"]: r for r in agent.conn.execute(
            "SELECT * FROM agent_remote_services ORDER BY name"
        )}
        self.assertEqual(rows["aio-ssh"]["destination"], "operator-target")
        self.assertEqual(rows["https"]["destination"], "drlink-agent")
        self.assertEqual(rows["ssh"]["destination"], "drlink-agent")
        # A correct authenticated per-service mapping recovers only the
        # untouched HTTPS seed after the forged probe is rejected.
        v24._reconcile_agent_from_server_status(agent, ack)
        rows = {r["name"]: r for r in agent.conn.execute(
            "SELECT * FROM agent_remote_services ORDER BY name"
        )}
        self.assertEqual(rows["aio-ssh"]["destination"], "operator-target")
        self.assertEqual(rows["https"]["destination"],
                         v24.enrolled_target_object_name(LAN))
        self.assertEqual(rows["ssh"]["destination"], "drlink-agent")
        self.assertEqual(rows["https"]["endpoint_port"], 6002)

    def test_mismatched_publication_remains_fail_closed(self):
        self._publish()
        row = self._server_rows()[1]
        self.server.conn.execute(
            "UPDATE published_services SET target_host='192.0.2.10' WHERE id=?",
            (row["published_id"],),
        )
        pub = self.server.conn.execute(
            "SELECT * FROM published_services WHERE id=?", (row["published_id"],)
        ).fetchone()
        meta = self.server.conn.execute(
            "SELECT * FROM remote_service_meta WHERE service_id=?",
            (row["published_id"],),
        ).fetchone()
        self.assertIn("diverges", ur.server_target_projection_reason(self.server, pub, meta))


if __name__ == "__main__":
    unittest.main(verbosity=2)
