#!/usr/bin/env python3
"""NewUserConn authorization hot path: remove redundant work WITHOUT changing any authorization semantics.

Evidence (claude-run-20261112, installed build 7a9c7f3b on a disposable host, per-request CPU of the strict default
path, i.e. one full integrity + foreign-key scan per connection):

* `ControlPlane.__init__` resolved the live Control DB path three times per request (`db_path`, `runtime_dir`,
  `connect_read_only`), each probing several marker files (11 `stat` calls per request).
* `build_proxy_map` ran 1 + clients + services + services queries per request, i.e. its cost grew with the number of
  Managed Hosts and Remote Services even though a single JOIN returns the same rows from the same snapshot.

Nothing here caches policy, relaxes the integrity scan or reuses a connection: every request still opens its own
read-only connection, runs the complete scan and re-reads the whole policy. These tests pin that the results are
identical to the previous implementation while the redundant work is gone.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

DB = importlib.import_module("drlink_control_db")
CP = importlib.import_module("drlink_control_plane")
RP = importlib.import_module("drlink_runtime_policy")

NOW = "2026-11-17T00:00:00Z"


def legacy_build_proxy_map(plane):
    """Verbatim copy of the pre-optimization build_proxy_map: the equivalence oracle."""
    mapping = {}
    collisions = {}
    try:
        from drlink_v24_runtime import remote_service_proxy_id
    except Exception:
        remote_service_proxy_id = None
    for client in plane.conn.execute("SELECT * FROM clients"):
        hostname = client["hostname"] or ""
        mid = client["id"]
        label = client["label"] or ""
        for svc in plane.conn.execute(
            "SELECT * FROM published_services WHERE client_id = ? AND released = 0",
            (mid,),
        ):
            historical_sid = str(svc["name"]).strip().lower()
            sid = historical_sid
            meta = plane.conn.execute(
                "SELECT * FROM remote_service_meta WHERE service_id = ?",
                (svc["id"],),
            ).fetchone()
            if meta is not None and remote_service_proxy_id is not None:
                sid = remote_service_proxy_id(svc["name"])
            name = RP.expected_proxy_name(hostname, mid, sid)
            entry = {
                "client_id": mid,
                "service_id": sid,
                "public_port": svc["public_port"],
                "client_label": label,
                "hostname": hostname,
                "enabled": bool(svc["enabled"]),
                "target_mode": svc["target_mode"],
                "target_host": svc["target_host"],
                "target_port": int(svc["target_port"] or 0),
                "service_type": svc["service_type"],
                "protocol": "tcp",
                "published_id": svc["id"],
                "destination_name": str(meta["destination_name"] or "") if meta is not None else "",
                "destination_client_id": (
                    str(meta["destination_client_id"] or "").strip() or None
                    if meta is not None
                    else None
                ),
                "service_object_id": meta["service_object_id"] if meta is not None else None,
                "has_remote_meta": meta is not None,
            }
            names = [name]
            if meta is not None and historical_sid != sid:
                names.append(RP.expected_proxy_name(hostname, mid, historical_sid))
            for proxy_name in names:
                if proxy_name in mapping or proxy_name in collisions:
                    collisions.setdefault(proxy_name, [mapping.pop(proxy_name, None)]).append(entry)
                    continue
                mapping[proxy_name] = entry
    if collisions:
        owners = []
        for name, entries in sorted(collisions.items()):
            parts = []
            for e in entries:
                if not e:
                    continue
                parts.append("%s/%s" % (e.get("client_id"), e.get("service_id")))
            owners.append("%s => %s" % (name, ", ".join(parts)))
        raise CP.ControlPlaneError("derived proxy name collision (fail closed): %s" % "; ".join(owners))
    return mapping


class HotPathEfficiency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved_env = os.environ.get("FRP_DEPLOY_TEST_ROOT")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = str(self.root)
        plane = CP.ControlPlane(str(self.root))
        plane.close()
        self.db_file = DB.db_path(str(self.root))

    def tearDown(self):
        if self.saved_env is None:
            os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        else:
            os.environ["FRP_DEPLOY_TEST_ROOT"] = self.saved_env
        self.tmp.cleanup()

    # -- helpers ----------------------------------------------------------
    def _insert_client(self, plane, cid, label, host):
        plane.conn.execute(
            "INSERT INTO clients (id, label, hostname, created_at, updated_at) VALUES (?,?,?,?,?)",
            (cid, label, host, NOW, NOW),
        )

    def _insert_service(self, plane, sid, cid, name, port, public_port, enabled=1, released=0):
        plane.conn.execute(
            "INSERT INTO published_services (id, client_id, name, service_type, target_mode, target_host,"
            " target_port, public_port, enabled, released, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, cid, name, "tcp", "self", "127.0.0.1", port, public_port, enabled, released, NOW, NOW),
        )

    def _seed(self, clients: int, services: int, meta_every: int = 2):
        plane = CP.ControlPlane(str(self.root))
        try:
            port = 6000
            for ci in range(clients):
                cid = "cid%04d" % ci
                self._insert_client(plane, cid, "label-%d" % ci, "host-%d" % ci)
                for si in range(services):
                    sid = "svc%04d%02d" % (ci, si)
                    released = 1 if (si == services - 1 and services > 2) else 0
                    self._insert_service(
                        plane, sid, cid, "Svc-%d" % si, 2200 + si, port,
                        enabled=1 if si % 3 else 0, released=released,
                    )
                    port += 1
                    if si % meta_every == 0:
                        plane.conn.execute(
                            "INSERT INTO remote_service_meta (service_id, destination_name, destination_client_id)"
                            " VALUES (?,?,?)",
                            (sid, "dest-%d" % si, cid if si % 4 == 0 else None),
                        )
        finally:
            plane.close()

    def _readonly_plane(self):
        return CP.ControlPlane(str(self.root), read_only=True)

    # -- 1. DB path resolution ---------------------------------------------
    def test_live_db_path_is_resolved_once_per_plane(self):
        calls = []
        orig = DB.select_live_control_db

        def counting(host_root):
            calls.append(str(host_root))
            return self.db_file

        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)  # production shape: root=None -> live host probing
        DB.select_live_control_db = counting
        try:
            plane = CP.ControlPlane(None, read_only=True)
            try:
                self.assertEqual(plane.db_file, self.db_file)
                self.assertEqual(plane.runtime, self.db_file.parent / "runtime")
            finally:
                plane.close()
        finally:
            DB.select_live_control_db = orig
        self.assertEqual(len(calls), 1, "live DB path probed %d times while opening one request plane" % len(calls))

    def test_runtime_dir_is_unchanged_for_explicit_root(self):
        plane = self._readonly_plane()
        try:
            self.assertEqual(plane.db_file, DB.db_path(str(self.root)))
            self.assertEqual(plane.runtime, DB.runtime_dir(str(self.root)))
        finally:
            plane.close()

    # -- 2. build_proxy_map --------------------------------------------------
    def test_proxy_map_equals_legacy_implementation(self):
        self._seed(clients=5, services=7)
        plane = self._readonly_plane()
        try:
            expected = legacy_build_proxy_map(plane)
            actual = RP.build_proxy_map(plane)
        finally:
            plane.close()
        self.assertTrue(expected, "seed produced no mapped services")
        self.assertEqual(actual, expected)
        self.assertEqual(list(actual), list(expected), "proxy map iteration order must match the legacy order")
        self.assertTrue(any(e["has_remote_meta"] for e in actual.values()))
        self.assertTrue(any(not e["has_remote_meta"] for e in actual.values()))
        self.assertTrue(any(not e["enabled"] for e in actual.values()))

    def test_proxy_map_ignores_released_services_and_clients_without_services(self):
        self._seed(clients=2, services=3)
        plane = CP.ControlPlane(str(self.root))
        try:
            self._insert_client(plane, "empty", "e", "empty-host")
        finally:
            plane.close()
        plane = self._readonly_plane()
        try:
            expected = legacy_build_proxy_map(plane)
            actual = RP.build_proxy_map(plane)
            released = plane.conn.execute("SELECT COUNT(*) FROM published_services WHERE released = 1").fetchone()[0]
        finally:
            plane.close()
        self.assertGreater(released, 0)
        self.assertEqual(actual, expected)
        self.assertFalse(any(e["client_id"] == "empty" for e in actual.values()))

    def test_proxy_map_collision_still_fails_closed_with_same_message(self):
        self._seed(clients=2, services=2)
        plane = CP.ControlPlane(str(self.root))
        try:
            # two clients with the same hostname and the same 8-character machine-id prefix publish a service of
            # the same name: both derive the very same FRP proxy name
            for idx, cid in enumerate(("abcdef01-aaaa", "abcdef01-bbbb")):
                self._insert_client(plane, cid, "twin-%d" % idx, "twin-host")
                self._insert_service(plane, "twin-svc-%d" % idx, cid, "ssh", 22, 6900 + idx)
        finally:
            plane.close()
        plane = self._readonly_plane()
        try:
            with self.assertRaises(CP.ControlPlaneError) as legacy:
                legacy_build_proxy_map(plane)
            with self.assertRaises(CP.ControlPlaneError) as current:
                RP.build_proxy_map(plane)
        finally:
            plane.close()
        self.assertIn("derived proxy name collision (fail closed)", str(legacy.exception))
        self.assertEqual(str(current.exception), str(legacy.exception))

    def test_proxy_map_query_count_does_not_grow_with_clients_or_services(self):
        self._seed(clients=8, services=6)
        plane = self._readonly_plane()
        statements = []
        plane.conn.set_trace_callback(lambda s: statements.append(" ".join(str(s).split())))
        try:
            RP.build_proxy_map(plane)
        finally:
            plane.conn.set_trace_callback(None)
            plane.close()
        selects = [s for s in statements if s.upper().startswith("SELECT")]
        self.assertLessEqual(
            len(selects), 2,
            "build_proxy_map issued %d SELECTs for 8 clients x 6 services: %s" % (len(selects), selects[:4]),
        )

    def test_authorize_remote_scan_count_is_unchanged(self):
        """The full integrity + foreign-key scan must still run exactly once per authorization."""
        self._seed(clients=2, services=2)
        scans = []
        orig = CP.integrity_check

        def counting(conn):
            scans.append(1)
            return orig(conn)

        CP.integrity_check = counting
        try:
            plane = self._readonly_plane()
            try:
                name = next(iter(RP.build_proxy_map(plane)))
                RP.authorize_remote(plane, proxy_name=name, source_ip="203.0.113.9:4000")
            finally:
                plane.close()
        finally:
            CP.integrity_check = orig
        self.assertEqual(len(scans), 1)


if __name__ == "__main__":
    unittest.main()
