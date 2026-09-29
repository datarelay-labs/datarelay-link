#!/usr/bin/env python3
"""P0: post-restore rebuild of allocator client-inventory + management identity."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_upgrade_reconcile as UR
import drlink_v24 as v24
import frp_mgmt_auth as MGMT

BACKUP = ROOT / "tools" / "frp-backup"
RESTORE = ROOT / "tools" / "frp-restore"
MID = "cccccccccccccccccccccccccccccccc"
MID2 = "dddddddddddddddddddddddddddddddd"
REVOKED = "ffffffffffffffffffffffffffffffff"


def _fp_digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _make_mgmt_identity(*, revoked: bool = False) -> dict:
    """Build a cryptographically valid synthetic management identity (no product secrets)."""
    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / "key.pem"
        pub = Path(tmp) / "pub.pem"
        subprocess.run(
            ["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "ec", "-in", str(key), "-pubout", "-out", str(pub)],
            check=True,
            capture_output=True,
        )
        canon = MGMT.canonicalize_pubkey_pem(pub.read_text(encoding="utf-8"))
        fingerprint = MGMT.pubkey_fingerprint(canon)
    identity = {
        "mgmt_status": "revoked" if revoked else "enrolled",
        "mgmt_alg": MGMT.MGMT_ALG,
        "mgmt_pubkey": canon,
        "mgmt_mac_key": MGMT.new_mac_key(),
        "mgmt_fingerprint": fingerprint,
        "mgmt_enrolled_at": "2026-09-28T14:38:30Z",
        "first_seen_ip": "192.0.2.10",
        "last_source_ip": "192.0.2.10",
        "last_seen_at": "2026-09-28T15:00:00Z",
        "last_enrolled_at": "2026-09-28T14:38:30Z",
    }
    if revoked:
        identity["mgmt_revoked_at"] = "2026-09-28T13:00:00Z"
    return identity


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


def rewrite_archive(source: Path, dest: Path, mutate) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with tarfile.open(source, "r:gz") as tar:
            tar.extractall(root)
        mutate(root)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        files = []
        lines = []
        for path in sorted((root / "payload").rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root / "payload").as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            mode = path.stat().st_mode & 0o777
            files.append({"path": rel, "sha256": digest, "mode": mode})
            lines.append("%s  payload/%s" % (digest, rel))
        manifest["files"] = files
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(root / "manifest.json", arcname="manifest.json")
            tar.add(root / "checksums.sha256", arcname="checksums.sha256")
            tar.add(root / "payload", arcname="payload")


class RestoreClientInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.MGMT_A = _make_mgmt_identity()
        cls.MGMT_B = _make_mgmt_identity()
        cls.MGMT_REVOKED = _make_mgmt_identity(revoked=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = Path(self.tmp.name) / "root"
        self.outdir = Path(self.tmp.name) / "out"
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.plane = seed_server(self.tree, "orig")
        self.token_before = (self.tree / "etc/frp/server_token").read_text(encoding="utf-8")
        self.inv_before = None

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

    def _seed_clients_and_services(self, *, with_revoked: bool = False) -> None:
        self.plane.upsert_client(MID, label="host-a", hostname="host-a", connected=True)
        self.plane.upsert_client(MID2, label="host-b", hostname="host-b", connected=True)
        if with_revoked:
            self.plane.upsert_client(
                REVOKED, label="host-revoked", hostname="host-revoked", connected=False
            )
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_service_object(self.plane, "web", type="tcp", port=8080, oneshot=True)
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

    def _inject_mgmt_identity(self, mapping: dict[str, dict]) -> None:
        path = self.tree / "var/lib/drlink/runtime/client-inventory.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        for cid, identity in mapping.items():
            self.assertIn(cid, state["clients"])
            # Stale forensic service must not survive restore as authority.
            state["clients"][cid].setdefault("services", {})["evil-stale"] = {
                "remote_port": 5999,
                "enabled": True,
            }
            state["clients"][cid].update(identity)
        path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    def _assert_mgmt_preserved(self, client: dict, expected: dict) -> None:
        self.assertEqual(client.get("mgmt_status"), expected["mgmt_status"])
        self.assertEqual(client.get("mgmt_alg"), expected["mgmt_alg"])
        self.assertEqual(client.get("mgmt_fingerprint"), expected["mgmt_fingerprint"])
        # Digest compare keeps failure output free of raw key/mac material.
        self.assertEqual(_fp_digest(client.get("mgmt_pubkey") or ""), _fp_digest(expected["mgmt_pubkey"]))
        self.assertEqual(_fp_digest(client.get("mgmt_mac_key") or ""), _fp_digest(expected["mgmt_mac_key"]))
        if "mgmt_enrolled_at" in expected:
            self.assertEqual(client.get("mgmt_enrolled_at"), expected["mgmt_enrolled_at"])
        if "mgmt_revoked_at" in expected:
            self.assertEqual(client.get("mgmt_revoked_at"), expected["mgmt_revoked_at"])
        self.assertNotIn("evil-stale", client.get("services") or {})

    def _assert_no_live_mutation(self) -> None:
        self.assertEqual(
            (self.tree / "etc/frp/server_token").read_text(encoding="utf-8"),
            self.token_before,
        )
        if self.inv_before is not None:
            after = (self.tree / "var/lib/drlink/runtime/client-inventory.json").read_text(
                encoding="utf-8"
            )
            self.assertEqual(_fp_digest(after), _fp_digest(self.inv_before))

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
        web = state["clients"][MID2]["services"]
        self.assertIn("rs-web", web)
        self.assertEqual(web["rs-web"]["remote_port"], 6010)
        self.assertNotEqual(state["clients"][MID].get("mgmt_status"), "enrolled")
        self.assertFalse(state["clients"][MID].get("mgmt_pubkey"))

    def test_restore_preserves_mgmt_identity_from_forensic_inventory(self):
        self._seed_clients_and_services(with_revoked=True)
        self._inject_mgmt_identity(
            {MID: self.MGMT_A, MID2: self.MGMT_B, REVOKED: self.MGMT_REVOKED}
        )
        archive = self.outdir / "mgmt.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        UR.project_client_inventory_from_control_plane(self.plane, root=str(self.tree))
        wiped = json.loads(
            (self.tree / "var/lib/drlink/runtime/client-inventory.json").read_text(encoding="utf-8")
        )
        self.assertFalse(wiped["clients"][MID].get("mgmt_pubkey"))
        self.plane.close()

        proc = run_tool(RESTORE, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = json.loads(
            (self.tree / "var/lib/drlink/runtime/client-inventory.json").read_text(encoding="utf-8")
        )
        self._assert_mgmt_preserved(after["clients"][MID], self.MGMT_A)
        self._assert_mgmt_preserved(after["clients"][MID2], self.MGMT_B)
        self._assert_mgmt_preserved(after["clients"][REVOKED], self.MGMT_REVOKED)
        self.assertEqual(after["clients"][MID]["services"]["ssh"]["remote_port"], 6001)
        self.plane = ControlPlane(str(self.tree))

    def test_rollback_preserves_mgmt_identity(self):
        self._seed_clients_and_services()
        self._inject_mgmt_identity({MID: self.MGMT_A, MID2: self.MGMT_B})
        archive = self.outdir / "rb-mgmt.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        extra = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        self.plane.upsert_client(extra, label="temp", hostname="temp", connected=True)
        UR.project_client_inventory_from_control_plane(self.plane, root=str(self.tree))
        self._inject_mgmt_identity({MID: self.MGMT_A, MID2: self.MGMT_B})
        # Extra client needs a forensic membership record for require_when_clients.
        path = self.tree / "var/lib/drlink/runtime/client-inventory.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn(extra, state["clients"])
        path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        self.assertIn(extra, after["clients"])
        self._assert_mgmt_preserved(after["clients"][MID], self.MGMT_A)
        self._assert_mgmt_preserved(after["clients"][MID2], self.MGMT_B)
        self.plane = ControlPlane(str(self.tree))

    def test_preflight_rejects_corrupt_identity_before_mutation(self):
        self._seed_clients_and_services()
        self._inject_mgmt_identity({MID: self.MGMT_A, MID2: self.MGMT_B})
        self.inv_before = (
            self.tree / "var/lib/drlink/runtime/client-inventory.json"
        ).read_text(encoding="utf-8")
        archive = self.outdir / "corrupt-mgmt.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        broken = self.outdir / "corrupt-mgmt-broken.tar.gz"

        def mutate(root: Path) -> None:
            path = root / "payload/var/lib/drlink/runtime/client-inventory.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            # Valid PEM shape is not enough: fingerprint must match pubkey.
            state["clients"][MID]["mgmt_fingerprint"] = "0" * 64
            path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        rewrite_archive(archive, broken, mutate)
        self.plane.close()
        proc = run_tool(RESTORE, str(broken))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("fingerprint", (proc.stderr or "").lower())
        self._assert_no_live_mutation()
        self.plane = ControlPlane(str(self.tree))

    def test_preflight_rejects_missing_machine_id_membership(self):
        self._seed_clients_and_services()
        self._inject_mgmt_identity({MID: self.MGMT_A, MID2: self.MGMT_B})
        self.inv_before = (
            self.tree / "var/lib/drlink/runtime/client-inventory.json"
        ).read_text(encoding="utf-8")
        archive = self.outdir / "missing-member.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        broken = self.outdir / "missing-member-broken.tar.gz"

        def mutate(root: Path) -> None:
            path = root / "payload/var/lib/drlink/runtime/client-inventory.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            # Forensic inventory exists but omits a restored SQLite client.
            del state["clients"][MID2]
            path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        rewrite_archive(archive, broken, mutate)
        self.plane.close()
        proc = run_tool(RESTORE, str(broken))
        self.assertNotEqual(proc.returncode, 0)
        err = (proc.stderr or "").lower()
        self.assertTrue("missing from forensic" in err or "management identity" in err, proc.stderr)
        self._assert_no_live_mutation()
        self.plane = ControlPlane(str(self.tree))

    def test_preflight_rejects_invalid_pubkey_before_mutation(self):
        self._seed_clients_and_services()
        self._inject_mgmt_identity({MID: self.MGMT_A, MID2: self.MGMT_B})
        self.inv_before = (
            self.tree / "var/lib/drlink/runtime/client-inventory.json"
        ).read_text(encoding="utf-8")
        archive = self.outdir / "bad-pub.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        broken = self.outdir / "bad-pub-broken.tar.gz"

        def mutate(root: Path) -> None:
            path = root / "payload/var/lib/drlink/runtime/client-inventory.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            state["clients"][MID]["mgmt_pubkey"] = (
                "-----BEGIN PUBLIC KEY-----\nnot-a-real-key\n-----END PUBLIC KEY-----\n"
            )
            path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        rewrite_archive(archive, broken, mutate)
        self.plane.close()
        proc = run_tool(RESTORE, str(broken))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("mgmt_pubkey", (proc.stderr or "").lower())
        self._assert_no_live_mutation()
        self.plane = ControlPlane(str(self.tree))

    def test_missing_forensic_inventory_with_clients_fails_closed(self):
        self._seed_clients_and_services()
        self._inject_mgmt_identity({MID: self.MGMT_A, MID2: self.MGMT_B})
        self.inv_before = (
            self.tree / "var/lib/drlink/runtime/client-inventory.json"
        ).read_text(encoding="utf-8")
        archive = self.outdir / "missing-inv.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        stripped = self.outdir / "missing-inv-stripped.tar.gz"

        def mutate(root: Path) -> None:
            for rel in (
                "payload/var/lib/drlink/runtime/client-inventory.json",
                "payload/var/lib/drlink/registry.json",
            ):
                path = root / rel
                if path.is_file():
                    path.unlink()

        rewrite_archive(archive, stripped, mutate)
        self.plane.close()
        proc = run_tool(RESTORE, str(stripped))
        self.assertNotEqual(proc.returncode, 0)
        combined = (proc.stderr or "").lower()
        self.assertTrue(
            "management identity" in combined or "forensic client inventory" in combined,
            proc.stderr,
        )
        self._assert_no_live_mutation()
        self.plane = ControlPlane(str(self.tree))

    def test_restore_rebuilds_purged_inventory(self):
        self._seed_clients_and_services()
        # Membership/forensic consistency requires inventory present in archive.
        archive = self.outdir / "good.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

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
        self.assertEqual(inv["clients"][MID]["services"]["ssh"]["remote_port"], 6001)

    def test_activation_failure_rollback_restores_inventory(self):
        self._seed_clients_and_services()
        archive = self.outdir / "rb.tar.gz"
        proc = run_tool(BACKUP, str(archive))
        self.assertEqual(proc.returncode, 0, proc.stderr)

        extra = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        self.plane.upsert_client(extra, label="temp", hostname="temp", connected=True)
        UR.project_client_inventory_from_control_plane(self.plane, root=str(self.tree))
        pre_restore = json.loads(
            (self.tree / "var/lib/drlink/runtime/client-inventory.json").read_text(encoding="utf-8")
        )
        self.assertIn(extra, pre_restore["clients"])
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
        self.assertIn(extra, after["clients"])
        self.assertEqual(after["clients"][extra]["label"], "temp")
        self.plane = ControlPlane(str(self.tree))


if __name__ == "__main__":
    unittest.main()
