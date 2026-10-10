#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_change import ManagementChangeService
from drlink_policy_safety import PolicySafetyService
import drlink_v24 as v24


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


def _future(hours: int = 2) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class V30ManagementChangePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-change-plan-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.seed = ControlPlane(self.tmp)
        v24.set_network_object(
            self.seed, "src", type="ip", value="198.51.100.10", oneshot=True
        )
        v24.set_network_object(
            self.seed, "dst", type="ip", value="198.51.100.20", oneshot=True
        )
        v24.set_service_object(self.seed, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_access_rule(
            self.seed,
            "remote",
            "allow-ssh",
            mode="whitelist",
            source="src",
            destination="dst",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        self.seed.set_ai_principal("bot", enabled=True)
        self.seed.conn.execute(
            "UPDATE ai_principals SET credential_status='verified' WHERE name='bot'"
        )
        v24.set_permission_object(
            self.seed, "info", permissions=["host-info"], oneshot=True
        )
        v24.set_ai_access_rule(
            self.seed,
            "allow-info",
            mode="whitelist",
            source="bot",
            destination="dst",
            permission="info",
            enabled=True,
            oneshot=True,
        )
        self.seed.close()
        os.environ.pop("DRLINK_CONFIRM", None)
        self.service = ManagementChangeService(self.tmp)

    def tearDown(self):
        self.service.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_CONFIRM", None)

    def _row_expiry(self, plane: str, rule: str):
        if plane == "ai":
            row = self.service.plane.conn.execute(
                "SELECT expires_at FROM ai_policy_rules WHERE name=?", (rule,)
            ).fetchone()
        else:
            row = self.service.plane.conn.execute(
                "SELECT expires_at FROM policy_rules WHERE plane=? AND name=?",
                (plane, rule),
            ).fetchone()
        return row["expires_at"]

    def test_preview_is_operational_state_not_configuration_revision(self):
        before = self.service.plane.current_revision()
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=_future(),
        )
        after = self.service.plane.current_revision()
        self.assertEqual(before, after)
        self.assertEqual(preview["expected_revision"], before)
        self.assertTrue(preview["change_plan_id"].startswith("cp_"))
        persisted = self.service.plane.conn.execute(
            "SELECT token_hash,actor_id,status FROM management_change_plans"
        ).fetchone()
        self.assertNotEqual(persisted["token_hash"], preview["change_plan_id"])
        self.assertEqual(persisted["actor_id"], "web:admin")
        self.assertEqual(persisted["status"], "pending")

    def test_apply_binds_actor_and_requires_explicit_confirmation(self):
        preview = self.service.preview_temporary_access(
            actor_id="mcp:chatgpt",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=_future(),
        )
        with self.assertRaises(ControlPlaneError):
            self.service.apply_temporary_access(
                actor_id="mcp:other",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
        with self.assertRaises(ControlPlaneError):
            self.service.apply_temporary_access(
                actor_id="mcp:chatgpt",
                change_plan_id=preview["change_plan_id"],
                confirmation="yes",
            )
        self.assertIsNone(self._row_expiry("remote", "allow-ssh"))

    def test_apply_sets_expiry_and_advances_exactly_one_revision(self):
        expiry = _future()
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=expiry,
        )
        before = self.service.plane.current_revision()
        result = self.service.apply_temporary_access(
            actor_id="web:admin",
            change_plan_id=preview["change_plan_id"],
            confirmation="APPLY",
        )
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["revision"], before + 1)
        self.assertEqual(self._row_expiry("remote", "allow-ssh"), expiry)

    def test_stored_temporary_access_plan_operation_mismatch_fails_closed(self):
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=_future(),
        )
        self.service.plane.conn.execute(
            "UPDATE management_change_plans SET operation='temporary-access.clear' "
            "WHERE actor_id='web:admin'"
        )
        revision = self.service.plane.current_revision()
        with self.assertRaises(ControlPlaneError):
            self.service.apply_temporary_access(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
        self.assertEqual(self.service.plane.current_revision(), revision)
        self.assertIsNone(self._row_expiry("remote", "allow-ssh"))

    def test_replay_fails_closed(self):
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=_future(),
        )
        self.service.apply_temporary_access(
            actor_id="web:admin",
            change_plan_id=preview["change_plan_id"],
            confirmation="APPLY",
        )
        rev = self.service.plane.current_revision()
        with self.assertRaises(ControlPlaneError):
            self.service.apply_temporary_access(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
        self.assertEqual(self.service.plane.current_revision(), rev)

    def test_concurrent_revision_change_stales_plan_without_overwrite(self):
        expiry = _future()
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=expiry,
        )
        v24.set_network_object(
            self.service.plane,
            "other",
            type="ip",
            value="203.0.113.10",
            oneshot=True,
            confirm=True,
        )
        current = self.service.plane.current_revision()
        with self.assertRaises(ConcurrencyError):
            self.service.apply_temporary_access(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
        self.assertEqual(self.service.plane.current_revision(), current)
        self.assertIsNone(self._row_expiry("remote", "allow-ssh"))
        status = self.service.plane.conn.execute(
            "SELECT status FROM management_change_plans"
        ).fetchone()["status"]
        self.assertEqual(status, "stale")

    def test_expired_plan_cannot_apply(self):
        now = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=(now + timedelta(hours=2)).isoformat(),
            now=now,
        )
        with self.assertRaises(ControlPlaneError):
            self.service.apply_temporary_access(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
                now=now + timedelta(seconds=301),
            )
        self.assertIsNone(self._row_expiry("remote", "allow-ssh"))

    def test_no_change_plan_consumes_without_revision(self):
        expiry = _future()
        v24.set_access_rule(
            self.service.plane,
            "remote",
            "allow-ssh",
            expires_at=expiry,
            oneshot=True,
            confirm=True,
        )
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=expiry,
        )
        self.assertTrue(preview["no_change"])
        before = self.service.plane.current_revision()
        result = self.service.apply_temporary_access(
            actor_id="web:admin",
            change_plan_id=preview["change_plan_id"],
            confirmation="APPLY",
        )
        self.assertEqual(result["status"], "NO_CHANGE")
        self.assertEqual(self.service.plane.current_revision(), before)

    def test_clear_expiry_is_change_plan_and_restores_permanent_rule(self):
        expiry = _future()
        v24.set_access_rule(
            self.service.plane,
            "remote",
            "allow-ssh",
            expires_at=expiry,
            oneshot=True,
            confirm=True,
        )
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="clear",
        )
        self.assertIsNone(preview["desired_expires_at"])
        self.service.apply_temporary_access(
            actor_id="web:admin",
            change_plan_id=preview["change_plan_id"],
            confirmation="APPLY",
        )
        self.assertIsNone(self._row_expiry("remote", "allow-ssh"))

    def test_ai_temporary_access_uses_same_change_plan_path(self):
        expiry = _future()
        preview = self.service.preview_temporary_access(
            actor_id="mcp:chatgpt",
            plane="ai",
            rule="allow-info",
            operation="set",
            expires_at=expiry,
        )
        result = self.service.apply_temporary_access(
            actor_id="mcp:chatgpt",
            change_plan_id=preview["change_plan_id"],
            confirmation="APPLY",
        )
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(self._row_expiry("ai", "allow-info"), expiry)

    def test_required_saved_policy_failure_blocks_temporary_access_apply(self):
        with PolicySafetyService(self.tmp) as safety:
            saved = safety.preview_definition(
                actor_id="web:admin",
                operation="set",
                definition={
                    "name": "baseline-deny-check",
                    "plane": "remote",
                    "source": "src",
                    "destination": "dst",
                    "service": "ssh",
                    "expected": "DENY",
                    "required": True,
                    "enabled": True,
                },
            )
            safety.apply_definition(
                actor_id="web:admin",
                change_plan_id=saved["change_plan_id"],
                confirmation="APPLY",
            )

        before = self.service.plane.current_revision()
        preview = self.service.preview_temporary_access(
            actor_id="web:admin",
            plane="remote",
            rule="allow-ssh",
            operation="set",
            expires_at=_future(),
        )
        self.assertIsNotNone(preview["policy_regression"])
        self.assertFalse(preview["policy_regression"]["ok"])
        self.assertEqual(preview["policy_regression"]["required_failed"], 1)
        self.assertIsNotNone(preview["blast_radius"])
        self.assertIsNotNone(preview["graph_overlay"])
        self.assertEqual(
            preview["impact"]["required_policy_test_failures"],
            1,
        )
        with self.assertRaisesRegex(
            ControlPlaneError, "Required Policy Regression Tests failed"
        ):
            self.service.apply_temporary_access(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
        self.assertEqual(self.service.plane.current_revision(), before)
        self.assertIsNone(self._row_expiry("remote", "allow-ssh"))

    def test_blacklist_rule_cannot_get_temporary_access_plan(self):
        self.service.plane.conn.execute(
            "UPDATE access_policies SET mode='blacklist' WHERE plane='remote'"
        )
        with self.assertRaises(ControlPlaneError):
            self.service.preview_temporary_access(
                actor_id="web:admin",
                plane="remote",
                rule="allow-ssh",
                operation="set",
                expires_at=_future(),
            )


if __name__ == "__main__":
    unittest.main()
