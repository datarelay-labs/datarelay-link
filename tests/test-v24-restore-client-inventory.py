#!/usr/bin/env python3
"""P0: post-restore rebuild of allocator client-inventory from SQLite."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_upgrade_reconcile as UR
import drlink_v24 as v24

BACKUP = ROOT / "tools" / "frp-backup"
RESTORE = ROOT / "tools" / "frp-restore"
MID = "cccccccccccccccccccccccccccccccc"
MID2 = "dddddddddddddddddddddddddddddddd"


def seed_server(tree: Path, marker: str = "orig") -> ControlPlane:
    for rel in (
        "etc/drlink/pki",
        "etc/frp",
        "var/lib/drlink/enrollments",
        "var/lib/drlink/bootstrap",
        "var/lib/drlink/backups",
        "var/lib/drlink/runtime",
        "var/log/drlink",
    ):
        (tree / rel).mkdir(parents=True, exist_ok=True)
    (tree / "etc/drlink/config.json").write_text(
        json.dumps(
            {
                "role": "server",
                "marker": marker,
                "public_hostname": "dr.example.test",
                "public_host": "dr.example.test",
                "port_start": 6000,
                "port_end": 6098,
                "allocator_listen_port": 6099,
                "registry_file": str(tree / "var/lib/drlink/runtime/client-inventory.json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tree / "etc/drlink/version").write_text(
        "PROJECT_VERSION=2.4.0\nRELEASE_CHANNEL=dev\nSOURCE_REF=test\n",
        encoding="utf-8",
    )
    for name in ("ca.key", "ca.crt", "server.key", "server.crt"):
        (tree / "etc/drlink/pki" / name).write_text("%s-%s\n" % (name, marker), encoding="utf-8")
    (tree / "etc/frp/frps.toml").write_text("bindPort = 443\n", encoding="utf-8")
    (tree / "etc/frp/server_token").write_text("token-%s\n" % marker, encoding="utf-8")
    os.environ["FRP_DEPLOY_TEST_ROOT"] = str(tree)
    os.environ["FRP_BACKUP_ALREADY_LOCKED"] = "1"
    os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
    plane = ControlPlane(str(tree))
    v24.ensure_v2_schema(plane.conn)
    return plane


def run_tool(tool: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True,
        text=True,
        env=merged,
    )


class RestoreClientInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = Path(self.tmp.name) / "root"
        self.outdir = Path(self.tmp.name) / "out"
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.plane = seed_server(self.tree, "orig")

    def tearDown(self):
        try:
            self.plane.close()
        except Exception:
            pass
        for key in (
            "FRP_DEPLOY_TEST_ROOT",
            "FRP_BACKUP_ALREADY_LOCKED",
            "DRLINK_SKIP_ACTIVATION",
            "FRP_RESTORE_HOOK_FAIL_AFTER",
            "FRP_RESTORE_HOOK_HEALTH_FAIL",
            "FRP_RESTORE_HOOK_ROLLBACK_HEALTH_FAIL",
        ):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _seed_clients_and_services(self) -> None:
        self.plane.upsert_client(MID, label="host-a", hostname="host-a", connected=True)
        self.plane.upsert_client(MID2, label="host-b", hostname="host-b", connected=True)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_service_object(self.plane, "web", type="tcp", port=8080, oneshot=True)
        # Legacy-style enrolled service (no service_object binding).
        self.plane.set_published_service(
            MID,
            "ssh",
            service_type="ssh",
            target_mode="self",
            target_host="127.0.0.1",
            target_port=22,
            enabled=True,
            public_port=6001,
            from_preset="ssh",
        )
        # v2.4 Remote Service with Service Object binding.
        self.plane.set_published_service(
            MID2,
            "web",
            service_type="tcp",
            target_mode="self",
            target_host="127.0.0.1",
            target_port=8080,
            enabled=True,
            public_port=6010,
        )
        pub = self.plane.conn.execute(
            "SELECT id FROM published_services WHERE client_id = ? AND name = ?",
            (MID2, "web"),
        ).fetchone()
        sobj = v24.get_service_object(self.plane, "web")
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO remote_service_meta"
            "(service_id, status, pool_class, service_object_id, destination_name, "
            "destination_client_id, pending_allocation, delete_pending, reason) "
            "VALUES (?, 'HEALTHY', 'normal', ?, 'this-host', ?, 0, 0, '')",
            (pub["id"], sobj["id"], MID2),
        )
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO port_reservations"
            "(public_port, client_id, service_id, service_name, released, created_at) "
            "VALUES (6001, ?, '', 'ssh', 0, datetime('now'))",
            (MID,),
        )
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO port_reservations"
            "(public_port, client_id, service_id, service_name, released, created_at) "
            "VALUES (6010, ?, ?, 'web', 0, datetime('now'))",
            (MID2, pub["id"]),
        )
        self.plane.conn.commit()
        self.plane.compile_runtime()
        UR.project_client_inventory_from_control_plane(self.plane, root=str(self.tree))

    def test_project_rebuilds_inventory_from_sqlite(self):
        self._seed_clients_and_services()
        inv_path = self.tree / "var/lib/drlink/runtime/client-inventory.json"
        inv_path.unlink()
        rebuilt = UR.project_client_inventory_from_control_plane(self.plane, root=str(self.tree))
        self.assertEqual(rebuilt, inv_path)
        state = json.loads(inv_path.read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], 2)
        self.assertIn(MID, state["clients"])
        self.assertIn(MID2, state["clients"])
        self.assertEqual(state["clients"][MID]["services"]["ssh"]["remote_port"], 6001)
        self.assertEqual(state["clients"][MID]["services"]["ssh"]["preset"], "ssh")
        web = state["clients"][MID2]["services"]
        self.assertIn("rs-web", web)
        self.assertTrue(web["rs-web"]["v24_remote_service"])
        self.assertEqual(web["rs-web"]["remote_port"], 6010)
        self.assertEqual(sorted(state["reserved"]), [6001, 6010])

    def test_restore_rebuilds_purged_inventory(self):
        self._seed_clients_and_services()
        archive = self.outdir / "good.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        # Mutate live DB + leave a stale inventory that restore must purge/rebuild.
        self.plane.conn.execute("UPDATE clients SET label='mutated' WHERE id=?", (MID,))
        self.plane.conn.commit()
        stale = self.tree / "var/lib/drlink/runtime/client-inventory.json"
        stale.write_text(
            json.dumps({"schema_version": 2, "reserved": [], "clients": {"evil": {"services": {}}}})
            + "\n",
            encoding="utf-8",
        )
        self.plane.close()

        proc = run_tool(RESTORE, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.plane = ControlPlane(str(self.tree))
        label = self.plane.conn.execute(
            "SELECT label FROM clients WHERE id=?", (MID,)
        ).fetchone()[0]
        self.assertEqual(label, "host-a")

        inv = json.loads(
            (self.tree / "var/lib/drlink/runtime/client-inventory.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("evil", inv["clients"])
        self.assertIn(MID, inv["clients"])
        self.assertEqual(inv["clients"][MID]["label"], "host-a")
        self.assertEqual(inv["clients"][MID]["services"]["ssh"]["remote_port"], 6001)
        self.assertEqual(inv["clients"][MID2]["services"]["rs-web"]["remote_port"], 6010)
        self.assertTrue(
            (self.tree / "var/lib/drlink/runtime/remote-access.json").is_file()
        )

    def test_activation_failure_rollback_restores_inventory(self):
        self._seed_clients_and_services()
        archive = self.outdir / "rb.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        # Live mutation after backup becomes the validated pre-restore snapshot.
        extra = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        self.plane.upsert_client(extra, label="temp", hostname="temp", connected=True)
        UR.project_client_inventory_from_control_plane(self.plane, root=str(self.tree))
        pre_restore = json.loads(
            (self.tree / "var/lib/drlink/runtime/client-inventory.json").read_text(encoding="utf-8")
        )
        self.assertIn(extra, pre_restore["clients"])
        # Release the live DB handle before the restore tool replaces files.
        self.plane.close()

        proc = run_tool(
            RESTORE,
            str(archive),
            env={"FRP_RESTORE_HOOK_FAIL_AFTER": "2"},
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("previous state was restored", proc.stderr)
        after = json.loads(
            (self.tree / "var/lib/drlink/runtime/client-inventory.json").read_text(encoding="utf-8")
        )
        # Automatic rollback must rebuild inventory from the restored prior DB,
        # including live clients that existed immediately before the failed restore.
        self.assertIn(extra, after["clients"])
        self.assertEqual(after["clients"][extra]["label"], "temp")
        self.assertEqual(
            after["clients"][MID]["services"]["ssh"]["remote_port"],
            pre_restore["clients"][MID]["services"]["ssh"]["remote_port"],
        )
        self.assertTrue(
            (self.tree / "var/lib/drlink/runtime/client-inventory.json").is_file()
        )
        self.plane = ControlPlane(str(self.tree))


if __name__ == "__main__":
    unittest.main()
