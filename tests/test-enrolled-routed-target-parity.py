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

CLIENT = "3a757a3e612b432fb44f7d75d87a38ae"
PUBLIC = "129.225.184.60"
LAN = "192.168.219.125"


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
            "hostname": "drlink-agent", "label": "ATSecu JumpHost",
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
            label="ATSecu JumpHost", services=enrolled_services(),
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
            self.assertEqual(r["destination"], matching["destination_name"])
            self.assertEqual(r["destination_client_id"], matching["destination_client_id"])
            self.assertEqual(r["endpoint_port"], matching["public_port"])
        # Desired FRP still routes to original authorized LAN IP, never loopback.
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
