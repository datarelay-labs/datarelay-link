#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_db as DB
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConfirmationRequired, ControlPlane
import drlink_v24 as v24


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


def _future(hours: int = 2) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _past(hours: int = 2) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class V30SchemaMigrationTests(unittest.TestCase):
    def test_v2_database_migrates_to_v3_management_foundation(self):
        conn = sqlite3.connect(":memory:", isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DB.SCHEMA_SQL)
        v24.ensure_v2_schema(conn)
        now = DB.utc_now_iso()
        conn.execute(
            "INSERT INTO schema_migrations(version,name,applied_at) VALUES (1,'initial_control_plane',?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO schema_migrations(version,name,applied_at) VALUES (2,'v24_canonical_objects_policy',?)",
            (now,),
        )

        DB.initialize(conn)

        self.assertEqual(DB.current_schema_version(conn), 3)
        policy_cols = {r[1] for r in conn.execute("PRAGMA table_info(policy_rules)")}
        ai_cols = {r[1] for r in conn.execute("PRAGMA table_info(ai_policy_rules)")}
        self.assertIn("expires_at", policy_cols)
        self.assertIn("expires_at", ai_cols)
        self.assertIsNotNone(
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='emergency_cutoffs'"
            ).fetchone()
        )
        migration = conn.execute(
            "SELECT name FROM schema_migrations WHERE version = 3"
        ).fetchone()
        self.assertEqual(migration["name"], "v30_management_foundation")
        conn.close()


class V30TemporaryAccessEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-temp-access-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_CONFIRM", None)

    def _seed_remote(self, mode: str = "whitelist", rule: str = "remote-rule"):
        v24.set_network_object(
            self.plane, "src", type="ip", value="198.51.100.10", oneshot=True
        )
        v24.set_network_object(
            self.plane, "dst", type="ip", value="198.51.100.20", oneshot=True
        )
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_access_rule(
            self.plane,
            "remote",
            rule,
            mode=mode,
            source="src",
            destination="dst",
            service="ssh",
            enabled=True,
            oneshot=True,
        )

    def _seed_internet(self):
        v24.set_network_object(
            self.plane, "lan", type="ip", value="10.10.10.20", oneshot=True
        )
        v24.set_network_object(
            self.plane, "web", type="fqdn", value="example.com", oneshot=True
        )
        v24.set_service_object(self.plane, "https", type="tcp", port=443, oneshot=True)
        v24.set_access_rule(
            self.plane,
            "internet",
            "allow-web",
            mode="whitelist",
            source="lan",
            destination="web",
            service="https",
            enabled=True,
            oneshot=True,
        )

    def _seed_ai(self):
        self.plane.set_ai_principal("bot", enabled=True)
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status='verified' WHERE name='bot'"
        )
        v24.set_network_object(
            self.plane, "target", type="ip", value="198.51.100.30", oneshot=True
        )
        v24.set_permission_object(
            self.plane, "info", permissions=["host-info"], oneshot=True
        )
        v24.set_ai_access_rule(
            self.plane,
            "allow-info",
            mode="whitelist",
            source="bot",
            destination="target",
            permission="info",
            enabled=True,
            oneshot=True,
        )

    def test_remote_whitelist_future_expiry_allows_then_past_expiry_denies(self):
        self._seed_remote()
        self.plane.conn.execute(
            "UPDATE policy_rules SET expires_at=? WHERE plane='remote' AND name='remote-rule'",
            (_future(),),
        )
        allow = self.plane.evaluate_remote_access(
            "198.51.100.10", "198.51.100.20", "tcp", 22
        )
        self.assertEqual(allow["effective"], "ALLOW")

        self.plane.conn.execute(
            "UPDATE policy_rules SET expires_at=? WHERE plane='remote' AND name='remote-rule'",
            (_past(),),
        )
        deny = self.plane.evaluate_remote_access(
            "198.51.100.10", "198.51.100.20", "tcp", 22
        )
        self.assertEqual(deny["effective"], "DENY")
        self.assertEqual(deny["matched_rules"], [])

    def test_remote_blacklist_expiry_never_disables_blocking_rule(self):
        self._seed_remote(mode="blacklist", rule="block-ssh")
        self.plane.conn.execute(
            "UPDATE policy_rules SET expires_at=? WHERE plane='remote' AND name='block-ssh'",
            (_past(),),
        )
        result = self.plane.evaluate_remote_access(
            "198.51.100.10", "198.51.100.20", "tcp", 22
        )
        self.assertEqual(result["effective"], "DENY")
        self.assertEqual(result["matched_rules"], ["block-ssh"])

    def test_internet_expired_whitelist_rule_denies_new_authorization(self):
        self._seed_internet()
        self.plane.conn.execute(
            "UPDATE policy_rules SET expires_at=? WHERE plane='internet' AND name='allow-web'",
            (_past(),),
        )
        result = self.plane.evaluate_internet_access(
            "10.10.10.20",
            "example.com",
            443,
            "tcp",
            candidate_ips=["93.184.216.34"],
        )
        self.assertEqual(result["effective"], "DENY")
        self.assertEqual(result["matched_rules"], [])

    def test_ai_expired_whitelist_rule_denies_new_authorization(self):
        self._seed_ai()
        self.plane.conn.execute(
            "UPDATE ai_policy_rules SET expires_at=? WHERE name='allow-info'",
            (_past(),),
        )
        result = v24.evaluate_ai_access_v24(
            self.plane,
            identity="bot",
            destination="target",
            permission="host-info",
        )
        self.assertEqual(result["result"], "DENY")
        self.assertEqual(result["matched_rules"], [])

    def test_blacklist_rule_rejects_temporary_access_expiry(self):
        self._seed_remote(mode="blacklist", rule="block-ssh")
        with self.assertRaises(ControlPlaneError):
            v24.set_access_rule(
                self.plane,
                "remote",
                "block-ssh",
                expires_at=_future(),
                oneshot=True,
            )

    def test_adding_expiry_is_security_narrowing_and_requires_confirmation(self):
        self._seed_remote()
        os.environ.pop("DRLINK_CONFIRM", None)
        expiry = _future()
        with self.assertRaises(ConfirmationRequired) as ctx:
            v24.set_access_rule(
                self.plane,
                "remote",
                "remote-rule",
                expires_at=expiry,
                oneshot=True,
            )
        self.assertTrue(ctx.exception.impact["access_narrowed"])
        self.assertFalse(ctx.exception.impact["access_broadened"])
        row = self.plane._get_rule("remote", "remote-rule")
        self.assertIsNone(row["expires_at"])

        v24.set_access_rule(
            self.plane,
            "remote",
            "remote-rule",
            expires_at=expiry,
            oneshot=True,
            confirm=True,
        )
        row = self.plane._get_rule("remote", "remote-rule")
        self.assertEqual(row["expires_at"], expiry)

    def test_extending_or_clearing_expiry_is_access_broadening(self):
        self._seed_remote()
        first = _future(1)
        later = _future(3)
        v24.set_access_rule(
            self.plane,
            "remote",
            "remote-rule",
            expires_at=first,
            oneshot=True,
            confirm=True,
        )
        os.environ.pop("DRLINK_CONFIRM", None)
        with self.assertRaises(ConfirmationRequired) as ctx:
            v24.set_access_rule(
                self.plane,
                "remote",
                "remote-rule",
                expires_at=later,
                oneshot=True,
            )
        self.assertTrue(ctx.exception.impact["access_broadened"])

        with self.assertRaises(ConfirmationRequired) as ctx2:
            v24.set_access_rule(
                self.plane,
                "remote",
                "remote-rule",
                expires_at="",
                oneshot=True,
            )
        self.assertTrue(ctx2.exception.impact["access_broadened"])

    def test_ai_expiry_mutation_uses_same_confirmation_semantics(self):
        self._seed_ai()
        os.environ.pop("DRLINK_CONFIRM", None)
        expiry = _future()
        with self.assertRaises(ConfirmationRequired) as ctx:
            v24.set_ai_access_rule(
                self.plane,
                "allow-info",
                expires_at=expiry,
                oneshot=True,
            )
        self.assertTrue(ctx.exception.impact["access_narrowed"])
        v24.set_ai_access_rule(
            self.plane,
            "allow-info",
            expires_at=expiry,
            oneshot=True,
            confirm=True,
        )
        row = self.plane.conn.execute(
            "SELECT expires_at FROM ai_policy_rules WHERE name='allow-info'"
        ).fetchone()
        self.assertEqual(row["expires_at"], expiry)

    def test_expired_whitelist_rule_is_not_counted_as_effective_last_allow(self):
        self._seed_remote()
        self.plane.conn.execute(
            "UPDATE policy_rules SET expires_at=? WHERE plane='remote' AND name='remote-rule'",
            (_past(),),
        )
        impact = v24.last_enabled_rule_mutation_impact(
            self.plane,
            "remote",
            "remote-rule",
            disabling=True,
        )
        self.assertIsNone(impact)


if __name__ == "__main__":
    unittest.main()
