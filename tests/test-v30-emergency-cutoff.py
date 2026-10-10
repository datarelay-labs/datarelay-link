#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_change import ManagementChangeService
from drlink_v30_cutoff import active_cutoffs, matching_cutoff
import drlink_v24 as v24


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class V30EmergencyCutoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-cutoff-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        p = ControlPlane(self.tmp)

        p.upsert_client(
            "client-a",
            label="alpha",
            hostname="alpha.local",
            connected=True,
            addresses=[{"address": "10.10.10.20", "active": True}],
        )
        p.set_published_service(
            "client-a",
            "ssh-admin",
            service_type="ssh",
            target_mode="self",
            target_port=22,
            public_port=6001,
            enabled=True,
        )

        v24.set_network_object(
            p, "outside", type="ip", value="198.51.100.10", oneshot=True
        )
        v24.set_network_object(
            p, "web", type="fqdn", value="example.com", oneshot=True
        )
        v24.set_service_object(p, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_service_object(p, "https", type="tcp", port=443, oneshot=True)

        v24.set_access_rule(
            p,
            "remote",
            "allow-ssh",
            mode="whitelist",
            source="outside",
            destination="alpha",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        v24.set_access_rule(
            p,
            "internet",
            "allow-web",
            mode="whitelist",
            source="alpha",
            destination="web",
            service="https",
            enabled=True,
            oneshot=True,
        )

        p.set_ai_principal("bot", enabled=True)
        p.conn.execute(
            "UPDATE ai_principals SET credential_status='verified' WHERE name='bot'"
        )
        v24.set_permission_object(p, "info", permissions=["host-info"], oneshot=True)
        v24.set_ai_access_rule(
            p,
            "allow-info",
            mode="whitelist",
            source="bot",
            destination="alpha",
            permission="info",
            enabled=True,
            oneshot=True,
        )
        p.close()
        os.environ.pop("DRLINK_CONFIRM", None)
        self.service = ManagementChangeService(self.tmp)

    def tearDown(self):
        self.service.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_CONFIRM", None)

    def _remote(self):
        return self.service.plane.evaluate_remote_access(
            "198.51.100.10", "alpha", "tcp", 22
        )

    def _internet(self):
        return self.service.plane.evaluate_internet_access(
            "10.10.10.20",
            "example.com",
            443,
            "tcp",
            candidate_ips=["93.184.216.34"],
        )

    def _ai(self):
        return v24.evaluate_ai_access_v24(
            self.service.plane,
            identity="bot",
            destination="alpha",
            permission="host-info",
        )

    def _apply(self, **kwargs):
        plan = self.service.preview_emergency_cutoff(
            actor_id="web:admin",
            operation="apply",
            **kwargs,
        )
        result = self.service.apply_emergency_cutoff(
            actor_id="web:admin",
            change_plan_id=plan["change_plan_id"],
            confirmation="CONFIRM CUTOFF",
        )
        self.assertFalse(result["active_sessions_terminated"])
        return plan, result

    def _clear(self, **kwargs):
        plan = self.service.preview_emergency_cutoff(
            actor_id="web:admin",
            operation="clear",
            **kwargs,
        )
        return self.service.apply_emergency_cutoff(
            actor_id="web:admin",
            change_plan_id=plan["change_plan_id"],
            confirmation="CONFIRM CUTOFF",
        )

    def test_remote_plane_cutoff_denies_new_access_and_clear_restores_policy(self):
        self.assertEqual(self._remote()["effective"], "ALLOW")
        before = self.service.plane.current_revision()
        _plan, result = self._apply(
            plane="remote", scope_kind="plane", reason="incident"
        )
        self.assertEqual(result["revision"], before + 1)
        denied = self._remote()
        self.assertEqual(denied["effective"], "DENY")
        self.assertIsNotNone(denied["cutoff"])
        self.assertIn("Emergency New-Access Cutoff", denied["reason"])
        self.assertIn("allow-ssh", denied["matched_rules"])

        self._clear(plane="remote", scope_kind="plane")
        restored = self._remote()
        self.assertEqual(restored["effective"], "ALLOW")
        self.assertIsNone(restored["cutoff"])

    def test_remote_service_cutoff_resolves_to_immutable_service_id(self):
        plan, _result = self._apply(
            plane="remote",
            scope_kind="remote-service",
            scope_ref="ssh-admin",
        )
        self.assertNotEqual(plan["scope_ref"], "ssh-admin")
        row = self.service.plane.conn.execute(
            "SELECT id FROM published_services WHERE name='ssh-admin'"
        ).fetchone()
        self.assertEqual(plan["scope_ref"], row["id"])
        self.assertEqual(self._remote()["effective"], "DENY")

    def test_internet_managed_host_cutoff_denies_candidates(self):
        initial = self._internet()
        self.assertEqual(initial["effective"], "ALLOW")
        self.assertEqual(initial["authorized_candidates"], ["93.184.216.34"])

        plan, _result = self._apply(
            plane="internet",
            scope_kind="managed-host",
            scope_ref="alpha",
        )
        self.assertEqual(plan["scope_ref"], "client-a")
        denied = self._internet()
        self.assertEqual(denied["effective"], "DENY")
        self.assertEqual(denied["authorized_candidates"], [])
        self.assertTrue(all(x.get("cutoff") for x in denied["candidate_results"]))

        self._clear(
            plane="internet",
            scope_kind="managed-host",
            scope_ref="client-a",
        )
        self.assertEqual(self._internet()["effective"], "ALLOW")

    def test_ai_identity_cutoff_denies_authorization_and_clear_restores(self):
        self.assertEqual(self._ai()["result"], "ALLOW")
        self._apply(plane="ai", scope_kind="ai-identity", scope_ref="bot")
        denied = self._ai()
        self.assertEqual(denied["result"], "DENY")
        self.assertIsNotNone(denied["cutoff"])
        self.assertIn("Emergency New-Access Cutoff", denied["reason"])
        self._clear(plane="ai", scope_kind="ai-identity", scope_ref="bot")
        self.assertEqual(self._ai()["result"], "ALLOW")

    def test_cutoff_overrides_disabled_policy_enforcement(self):
        self.service.plane.conn.execute(
            "UPDATE access_policies SET enforcement='disabled' WHERE plane='remote'"
        )
        self.assertEqual(self._remote()["effective"], "ALLOW")
        self._apply(plane="remote", scope_kind="plane")
        self.assertEqual(self._remote()["effective"], "DENY")

    def test_normal_policy_is_not_rewritten_by_cutoff(self):
        before = self.service.plane.conn.execute(
            "SELECT mode,enforcement,row_version FROM access_policies WHERE plane='remote'"
        ).fetchone()
        rule_before = self.service.plane.conn.execute(
            "SELECT row_version,enabled FROM policy_rules "
            "WHERE plane='remote' AND name='allow-ssh'"
        ).fetchone()

        self._apply(plane="remote", scope_kind="plane")
        self._clear(plane="remote", scope_kind="plane")

        after = self.service.plane.conn.execute(
            "SELECT mode,enforcement,row_version FROM access_policies WHERE plane='remote'"
        ).fetchone()
        rule_after = self.service.plane.conn.execute(
            "SELECT row_version,enabled FROM policy_rules "
            "WHERE plane='remote' AND name='allow-ssh'"
        ).fetchone()
        self.assertEqual(tuple(before), tuple(after))
        self.assertEqual(tuple(rule_before), tuple(rule_after))

    def test_cutoff_requires_strong_confirmation(self):
        plan = self.service.preview_emergency_cutoff(
            actor_id="web:admin",
            plane="remote",
            scope_kind="plane",
            operation="apply",
        )
        with self.assertRaises(ControlPlaneError):
            self.service.apply_emergency_cutoff(
                actor_id="web:admin",
                change_plan_id=plan["change_plan_id"],
                confirmation="APPLY",
            )
        self.assertEqual(self._remote()["effective"], "ALLOW")

    def test_stale_cutoff_plan_fails_closed(self):
        plan = self.service.preview_emergency_cutoff(
            actor_id="web:admin",
            plane="remote",
            scope_kind="plane",
            operation="apply",
        )
        v24.set_network_object(
            self.service.plane,
            "other",
            type="ip",
            value="203.0.113.5",
            oneshot=True,
            confirm=True,
        )
        rev = self.service.plane.current_revision()
        with self.assertRaises(ConcurrencyError):
            self.service.apply_emergency_cutoff(
                actor_id="web:admin",
                change_plan_id=plan["change_plan_id"],
                confirmation="CONFIRM CUTOFF",
            )
        self.assertEqual(self.service.plane.current_revision(), rev)
        self.assertEqual(self._remote()["effective"], "ALLOW")

    def test_unrecognized_cutoff_plane_fails_closed_on_read_paths(self):
        # A new/typoed plane must never silently return no active cutoff.
        for plane in ("unknown-plane", "", "remotee"):
            with self.subTest(plane=plane):
                with self.assertRaises(ControlPlaneError):
                    active_cutoffs(self.service.plane.conn, plane)
                with self.assertRaises(ControlPlaneError):
                    matching_cutoff(self.service.plane.conn, plane)

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(ControlPlaneError):
            self.service.preview_emergency_cutoff(
                actor_id="web:admin",
                plane="remote",
                scope_kind="managed-host",
                scope_ref="alpha",
                operation="apply",
            )


if __name__ == "__main__":
    unittest.main()
