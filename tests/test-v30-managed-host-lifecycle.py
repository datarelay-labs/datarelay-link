from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_v24 as v24
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_core import (
    ManagementActor,
    ManagementAuthorizationError,
    ManagementCoreService,
)
from drlink_management_host_lifecycle import ManagedHostLifecycleService

MID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class V30ManagedHostLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-host-lifecycle-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        plane = ControlPlane(self.tmp)
        try:
            v24.ensure_v2_schema(plane.conn)
        finally:
            plane.close()

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_SKIP_ACTIVATION", None)

    def _seed_host(self, label: str = "host-a", *, with_service: bool = True):
        plane = ControlPlane(self.tmp)
        try:
            plane.upsert_client(
                MID,
                label=label,
                hostname=label,
                connected=True,
                addresses=[{"address": "10.0.0.5", "active": True}],
            )
            if with_service:
                v24.set_service_object(
                    plane, "ssh", type="tcp", port=22, oneshot=True
                )
                plane.set_published_service(
                    MID,
                    "ssh-access",
                    service_type="tcp",
                    target_mode="self",
                    target_host="127.0.0.1",
                    target_port=22,
                    enabled=True,
                    public_port=6011,
                )
                pub = plane.conn.execute(
                    "SELECT id FROM published_services "
                    "WHERE client_id=? AND name='ssh-access'",
                    (MID,),
                ).fetchone()
                plane.conn.execute(
                    "INSERT OR REPLACE INTO port_reservations"
                    "(public_port,client_id,service_id,service_name,released,created_at) "
                    "VALUES (6011,?,?, 'ssh-access',0,datetime('now'))",
                    (MID, pub["id"]),
                )
                plane.conn.commit()
        finally:
            plane.close()

    @staticmethod
    def _admin() -> ManagementActor:
        return ManagementActor.authenticated(
            "web:admin",
            {"management-read", "management-config"},
            role="Admin",
        )

    def test_revoke_preview_and_apply_keep_services_and_ports(self):
        self._seed_host()
        with ManagedHostLifecycleService(self.tmp) as service:
            before = service.plane.current_revision()
            preview = service.preview(
                actor_id="web:admin",
                host="host-a",
                operation="revoke-trust",
            )
            self.assertEqual(preview["confirmation_class"], "REVOKE")
            self.assertIn("published services", preview["impact"]["kept"])
            self.assertEqual(service.plane.current_revision(), before)
            row = service.plane.require_client("host-a")
            self.assertEqual(str(row["trust_status"]), "trusted")
            with self.assertRaisesRegex(ControlPlaneError, "REVOKE"):
                service.apply(
                    actor_id="web:admin",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
            self.assertEqual(service.plane.current_revision(), before)
            applied = service.apply(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="REVOKE",
            )
            self.assertEqual(applied["revision"], before + 1)
            row = service.plane.require_client("host-a")
            self.assertEqual(str(row["trust_status"]), "revoked")
            self.assertEqual(int(row["connected"] or 0), 0)
            self.assertIsNotNone(
                service.plane.conn.execute(
                    "SELECT id FROM published_services WHERE client_id=?",
                    (MID,),
                ).fetchone()
            )
            self.assertIsNotNone(
                service.plane.conn.execute(
                    "SELECT public_port FROM port_reservations "
                    "WHERE client_id=? AND released=0",
                    (MID,),
                ).fetchone()
            )
            revision = service.plane.conn.execute(
                "SELECT actor FROM config_revisions WHERE revision=?",
                (before + 1,),
            ).fetchone()
            self.assertEqual(revision["actor"], "web:admin")
            audit = service.plane.conn.execute(
                "SELECT actor_id,interface FROM audit_events "
                "WHERE revision=? ORDER BY id DESC LIMIT 1",
                (before + 1,),
            ).fetchone()
            self.assertEqual(audit["actor_id"], "web:admin")
            self.assertEqual(audit["interface"], "WEB")

    def test_retire_preview_cleanup_and_apply_remove_owned_state(self):
        self._seed_host()
        with ManagedHostLifecycleService(self.tmp) as service:
            before = service.plane.current_revision()
            preview = service.preview(
                actor_id="web:admin",
                host="host-a",
                operation="retire",
            )
            self.assertEqual(preview["confirmation_class"], "RETIRE")
            cleanup = "\n".join(preview["impact"]["cleanup"])
            self.assertIn("published service ssh-access", cleanup)
            self.assertIn("port reservation 6011", cleanup)
            self.assertEqual(service.plane.current_revision(), before)
            self.assertIsNotNone(service.plane.get_client("host-a"))

            applied = service.apply(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="RETIRE",
            )
            self.assertEqual(applied["revision"], before + 1)
            self.assertIsNone(service.plane.get_client("host-a"))
            self.assertIsNone(
                service.plane.conn.execute(
                    "SELECT id FROM published_services WHERE client_id=?",
                    (MID,),
                ).fetchone()
            )
            active = service.plane.conn.execute(
                "SELECT COUNT(*) FROM port_reservations "
                "WHERE client_id=? AND released=0",
                (MID,),
            ).fetchone()[0]
            self.assertEqual(int(active), 0)

    def test_referenced_host_retire_preview_fails_closed(self):
        self._seed_host(with_service=False)
        plane = ControlPlane(self.tmp)
        try:
            v24.set_network_object(
                plane, "office", type="ip", value="198.51.100.10", oneshot=True
            )
            v24.set_service_object(
                plane, "ssh", type="tcp", port=22, oneshot=True
            )
            v24.set_access_rule(
                plane,
                "remote",
                "to-host",
                mode="whitelist",
                source="office",
                destination="host-a",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
            before = plane.current_revision()
        finally:
            plane.close()
        with ManagedHostLifecycleService(self.tmp) as service:
            with self.assertRaisesRegex(ControlPlaneError, "still referenced"):
                service.preview(
                    actor_id="web:admin",
                    host="host-a",
                    operation="retire",
                )
            self.assertEqual(service.plane.current_revision(), before)
            self.assertIsNotNone(service.plane.get_client("host-a"))

    def test_stale_plan_rejected_before_lifecycle_mutation(self):
        self._seed_host(with_service=False)
        with ManagedHostLifecycleService(self.tmp) as service:
            preview = service.preview(
                actor_id="web:admin",
                host="host-a",
                operation="revoke-trust",
            )
        plane = ControlPlane(self.tmp)
        try:
            plane.set_client_description("host-a", "revision drift")
        finally:
            plane.close()
        with ManagedHostLifecycleService(self.tmp) as service:
            with self.assertRaises(ConcurrencyError):
                service.apply(
                    actor_id="web:admin",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="REVOKE",
                )
            row = service.plane.require_client("host-a")
            self.assertNotEqual(str(row["trust_status"]), "revoked")

    def test_core_requires_admin_and_management_config(self):
        self._seed_host(with_service=False)
        core = ManagementCoreService(self.tmp)
        operator = ManagementActor.authenticated(
            "web:operator",
            {"management-read", "management-config"},
            role="Operator",
        )
        with self.assertRaises(ManagementAuthorizationError):
            core.managed_host_lifecycle_preview(
                host="host-a",
                operation="revoke-trust",
                actor=operator,
            )
        preview = core.managed_host_lifecycle_preview(
            host="host-a",
            operation="revoke-trust",
            actor=self._admin(),
        )
        self.assertEqual(preview["confirmation_class"], "REVOKE")


if __name__ == "__main__":
    unittest.main()
