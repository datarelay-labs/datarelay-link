#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_db as DB
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
import drlink_v24 as v24
from drlink_management_temporary_access_requests import (
    TemporaryAccessRequestService,
    REVIEW_PERMISSION,
)


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class Ui06TemporaryAccessRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-ui06-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)
        v24.set_network_object(self.plane, "src", type="ip", value="198.51.100.10", oneshot=True)
        v24.set_network_object(self.plane, "dst", type="ip", value="198.51.100.20", oneshot=True)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_access_rule(
            self.plane, "remote", "jit-ssh", mode="whitelist",
            source="src", destination="dst", service="ssh", enabled=True, oneshot=True,
        )
        self.plane.close()

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_CONFIRM", None)

    def service(self):
        return TemporaryAccessRequestService(self.tmp)

    def _create(self, service, actor="requester", role="Operator", seconds=1800, purpose="Emergency maintenance"):
        return service.create(
            actor_id=actor, role=role, permissions={"management-temporary-access"},
            plane="remote", rule="jit-ssh", purpose=purpose, duration_seconds=seconds,
        )

    def test_v3_database_migrates_to_v4_ui06_table_transactionally(self):
        conn = sqlite3.connect(":memory:", isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DB.SCHEMA_SQL)
        v24.ensure_v2_schema(conn)
        DB.ensure_v30_schema(conn)
        now = DB.utc_now_iso()
        for version, name in (
            (1, "initial_control_plane"),
            (2, "v24_canonical_objects_policy"),
            (3, "v30_management_foundation"),
        ):
            conn.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (?,?,?)",
                (version, name, now),
            )
        DB.initialize(conn)
        self.assertEqual(DB.current_schema_version(conn), 4)
        migration = conn.execute("SELECT name FROM schema_migrations WHERE version=4").fetchone()
        self.assertEqual(migration["name"], "ui06_two_person_temporary_access")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(temporary_access_requests)")}
        self.assertTrue({"requester_actor_id","reviewer_actor_id","row_version","approved_expires_at"}.issubset(columns))
        conn.close()

    def test_create_is_persistent_bounded_and_does_not_grant_access(self):
        with self.service() as service:
            before = service.plane.current_revision()
            request = self._create(service)
            self.assertEqual(request["status"], "PENDING")
            self.assertEqual(request["requester_actor_id"], "requester")
            self.assertEqual(request["requested_duration_seconds"], 1800)
            self.assertEqual(service.plane.current_revision(), before)
            row = service.plane._get_rule("remote", "jit-ssh")
            self.assertIsNone(row["expires_at"])
            request_id = request["id"]
        with self.service() as service:
            loaded = service.get(
                request_id, actor_id="requester", role="Operator",
                permissions={"management-temporary-access"},
            )
            self.assertEqual(loaded["status"], "PENDING")

    def test_duplicate_pending_and_invalid_text_or_duration_fail_closed(self):
        with self.service() as service:
            self._create(service)
            with self.assertRaises(ControlPlaneError):
                self._create(service)
            for seconds in (299, 86401):
                with self.assertRaises(ControlPlaneError):
                    self._create(service, actor="other-"+str(seconds), seconds=seconds)
            with self.assertRaises(ControlPlaneError):
                self._create(service, actor="bad-purpose", purpose="bad‮text")

    def test_self_review_and_non_admin_review_are_denied(self):
        with self.service() as service:
            request = self._create(service)
            with self.assertRaises(ControlPlaneError):
                service.review(
                    request["id"], actor_id="requester", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="self", row_version=request["row_version"],
                )
            with self.assertRaises(ControlPlaneError):
                service.review(
                    request["id"], actor_id="operator-reviewer", role="Operator",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="no", row_version=request["row_version"],
                )

    def test_admin_approval_shortens_duration_and_atomically_applies_canonical_expiry(self):
        with self.service() as service:
            request = self._create(service, seconds=1800)
            before = service.plane.current_revision()
            approved = service.review(
                request["id"], actor_id="reviewer", role="Admin",
                permissions={REVIEW_PERMISSION}, decision="approve",
                approved_duration_seconds=900, reason="approved maintenance",
                row_version=request["row_version"], now=_now(),
            )
            self.assertEqual(approved["status"], "APPROVED")
            self.assertEqual(approved["approved_duration_seconds"], 900)
            self.assertEqual(approved["reviewer_actor_id"], "reviewer")
            self.assertEqual(approved["applied_revision"], before + 1)
            self.assertEqual(service.plane.current_revision(), before + 1)
            row = service.plane._get_rule("remote", "jit-ssh")
            self.assertEqual(row["expires_at"], approved["approved_expires_at"])
            audit = service.plane.conn.execute(
                "SELECT event_type,actor_id,entity_id FROM audit_events "
                "WHERE event_type='temporary_access.request.approved' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual((audit["actor_id"], audit["entity_id"]), ("reviewer", request["id"]))
            with self.assertRaises(ControlPlaneError):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="replay",
                    row_version=request["row_version"],
                )

    def test_reviewer_cannot_lengthen_or_approve_stale_revision(self):
        with self.service() as service:
            request = self._create(service, seconds=900)
            with self.assertRaises(ControlPlaneError):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=901, reason="", row_version=request["row_version"],
                )
            service.plane._mutate(
                "unrelated", "unrelated", lambda: {"entity":{"type":"test","id":"x"},"operation":"test"},
                compile_runtime=False,
            )
            with self.assertRaises(ConcurrencyError):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="", row_version=request["row_version"],
                )

    def test_reject_is_one_shot_and_never_mutates_policy(self):
        with self.service() as service:
            request = self._create(service)
            before = service.plane.current_revision()
            denied = service.review(
                request["id"], actor_id="reviewer", role="Admin",
                permissions={REVIEW_PERMISSION}, decision="reject",
                approved_duration_seconds=None, reason="not justified",
                row_version=request["row_version"],
            )
            self.assertEqual(denied["status"], "REJECTED")
            self.assertEqual(service.plane.current_revision(), before)
            self.assertIsNone(service.plane._get_rule("remote", "jit-ssh")["expires_at"])

    def test_reject_rechecks_target_and_revision_before_decision(self):
        with self.service() as service:
            request = self._create(service)
            with patch.object(
                service, "_resolve_rule", side_effect=ControlPlaneError("target changed")
            ):
                with self.assertRaises(ControlPlaneError):
                    service.review(
                        request["id"], actor_id="reviewer", role="Admin",
                        permissions={REVIEW_PERMISSION}, decision="reject",
                        approved_duration_seconds=None, reason="target changed",
                        row_version=request["row_version"],
                    )
            row = service.plane.conn.execute(
                "SELECT status,row_version FROM temporary_access_requests WHERE id=?", (request["id"],)
            ).fetchone()
            self.assertEqual((row["status"], row["row_version"]), ("PENDING", 1))

            with patch.object(
                service.plane, "current_revision", return_value=request["requested_revision"] + 1
            ):
                with self.assertRaises(ConcurrencyError):
                    service.review(
                        request["id"], actor_id="reviewer", role="Admin",
                        permissions={REVIEW_PERMISSION}, decision="reject",
                        approved_duration_seconds=None, reason="stale revision",
                        row_version=request["row_version"],
                    )
            row = service.plane.conn.execute(
                "SELECT status,row_version FROM temporary_access_requests WHERE id=?", (request["id"],)
            ).fetchone()
            self.assertEqual((row["status"], row["row_version"]), ("PENDING", 1))

    def test_list_is_requester_scoped_but_admin_reviewer_can_observe_all(self):
        with self.service() as service:
            own = self._create(service, actor="a")
            self._create(service, actor="b")
            requester = service.list(
                actor_id="a", role="Operator", permissions={"management-temporary-access"}, limit=50
            )
            self.assertEqual([x["id"] for x in requester["items"]], [own["id"]])
            reviewer = service.list(
                actor_id="admin", role="Admin",
                permissions={"management-temporary-access", REVIEW_PERMISSION}, limit=50,
            )
            self.assertEqual(len(reviewer["items"]), 2)

    def test_natural_expiry_is_core_time_derived_and_early_revoke_is_narrowing(self):
        base = _now()
        with self.service() as service:
            request = self._create(service, seconds=300)
            approved = service.review(
                request["id"], actor_id="reviewer", role="Admin",
                permissions={REVIEW_PERMISSION}, decision="approve",
                approved_duration_seconds=300, reason="", row_version=request["row_version"], now=base,
            )
            expired = service.get(
                request["id"], actor_id="requester", role="Operator",
                permissions={"management-temporary-access"}, now=base+timedelta(seconds=301),
            )
            self.assertEqual(expired["status"], "EXPIRED")
            with self.assertRaises(ControlPlaneError):
                service.revoke(
                    request["id"], actor_id="requester", role="Operator",
                    permissions={"management-temporary-access"}, row_version=approved["row_version"],
                    now=base+timedelta(seconds=301),
                )

        # Separate request for early revoke.
        root2 = tempfile.mkdtemp(prefix="drlink-ui06-revoke-")
        _server_root(root2)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = root2
        plane = ControlPlane(root2)
        v24.set_network_object(plane, "src", type="ip", value="198.51.100.10", oneshot=True)
        v24.set_network_object(plane, "dst", type="ip", value="198.51.100.20", oneshot=True)
        v24.set_service_object(plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_access_rule(plane, "remote", "jit-ssh", mode="whitelist", source="src", destination="dst", service="ssh", enabled=True, oneshot=True)
        plane.close()
        with TemporaryAccessRequestService(root2) as service:
            request = self._create(service)
            approved = service.review(
                request["id"], actor_id="reviewer", role="Admin",
                permissions={REVIEW_PERMISSION}, decision="approve",
                approved_duration_seconds=900, reason="", row_version=request["row_version"], now=base,
            )
            revoked = service.revoke(
                request["id"], actor_id="requester", role="Operator",
                permissions={"management-temporary-access"}, row_version=approved["row_version"],
                now=base+timedelta(seconds=60),
            )
            self.assertEqual(revoked["status"], "REVOKED")
            expiry = service.plane._get_rule("remote", "jit-ssh")["expires_at"]
            self.assertLessEqual(expiry, (base+timedelta(seconds=60)).isoformat().replace("+00:00","Z"))
            with self.assertRaises(ControlPlaneError):
                service.revoke(
                    request["id"], actor_id="requester", role="Operator",
                    permissions={"management-temporary-access"}, row_version=revoked["row_version"],
                    now=base+timedelta(seconds=61),
                )


    def test_request_and_review_permissions_fail_closed(self):
        with self.service() as service:
            with self.assertRaises(ControlPlaneError):
                service.create(
                    actor_id="no-request-permission", role="Operator", permissions=set(),
                    plane="remote", rule="jit-ssh", purpose="maintenance", duration_seconds=900,
                )
            with self.assertRaises(ControlPlaneError):
                service.create(
                    actor_id="read-only", role="Read Only", permissions={"management-temporary-access"},
                    plane="remote", rule="jit-ssh", purpose="maintenance", duration_seconds=900,
                )
            request = self._create(service)
            for role, permissions in (
                ("Admin", {"management-temporary-access"}),
                ("Read Only", {REVIEW_PERMISSION}),
            ):
                with self.subTest(role=role, permissions=permissions):
                    with self.assertRaises(ControlPlaneError):
                        service.review(
                            request["id"], actor_id="reviewer-" + role.lower().replace(" ", "-"),
                            role=role, permissions=permissions, decision="approve",
                            approved_duration_seconds=900, reason="", row_version=request["row_version"],
                        )

    def test_wrong_and_cross_server_request_ids_fail_closed(self):
        with self.service() as service:
            request = self._create(service)
            with self.assertRaises(ControlPlaneError):
                service.review(
                    "tar_abcdefghijklmnop", actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="", row_version=1,
                )
            service.plane.conn.execute(
                "UPDATE temporary_access_requests SET server_id=? WHERE id=?",
                ("different-server", request["id"]),
            )
            with self.assertRaises(ControlPlaneError):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="", row_version=request["row_version"],
                )
            row = service.plane.conn.execute(
                "SELECT status,row_version FROM temporary_access_requests WHERE id=?", (request["id"],)
            ).fetchone()
            self.assertEqual((row["status"], row["row_version"]), ("PENDING", 1))

    def test_concurrent_approve_vs_reject_allows_exactly_one_decision(self):
        with self.service() as service:
            request = self._create(service)
        barrier = threading.Barrier(2)
        outcomes = []
        guard = threading.Lock()

        def decide(actor, decision):
            try:
                with TemporaryAccessRequestService(self.tmp) as worker:
                    barrier.wait(timeout=5)
                    result = worker.review(
                        request["id"], actor_id=actor, role="Admin",
                        permissions={REVIEW_PERMISSION}, decision=decision,
                        approved_duration_seconds=900 if decision == "approve" else None,
                        reason=decision, row_version=request["row_version"],
                    )
                    item = ("ok", result["status"])
            except Exception as exc:
                item = ("error", type(exc).__name__)
            with guard:
                outcomes.append(item)

        threads = [
            threading.Thread(target=decide, args=("reviewer-a", "approve"), daemon=True),
            threading.Thread(target=decide, args=("reviewer-b", "reject"), daemon=True),
        ]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads), outcomes)
        successes = [item for item in outcomes if item[0] == "ok"]
        self.assertEqual(len(successes), 1, outcomes)
        self.assertIn(successes[0][1], {"APPROVED", "REJECTED"})
        with self.service() as service:
            final = service.get(
                request["id"], actor_id="requester", role="Operator",
                permissions={"management-temporary-access"},
            )
            self.assertEqual(final["status"], successes[0][1])
            self.assertEqual(final["row_version"], 2)

    def test_target_rename_mode_change_and_delete_fail_closed(self):
        with self.service() as service:
            request = self._create(service)
            service.plane.conn.execute(
                "UPDATE policy_rules SET name='jit-ssh-renamed' WHERE plane='remote' AND name='jit-ssh'"
            )
            with self.assertRaises((ControlPlaneError, ConcurrencyError)):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="", row_version=request["row_version"],
                )
            service.plane.conn.execute(
                "UPDATE policy_rules SET name='jit-ssh' WHERE plane='remote' AND name='jit-ssh-renamed'"
            )
            service.plane.conn.execute(
                "UPDATE access_policies SET mode='blacklist' WHERE plane='remote'"
            )
            with self.assertRaises((ControlPlaneError, ConcurrencyError)):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="", row_version=request["row_version"],
                )
            service.plane.conn.execute(
                "UPDATE access_policies SET mode='whitelist' WHERE plane='remote'"
            )
            v24.unset_access_rule(service.plane, "remote", "jit-ssh", confirm=True)
            with self.assertRaises((ControlPlaneError, ConcurrencyError)):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="", row_version=request["row_version"],
                )
            state = service.plane.conn.execute(
                "SELECT status FROM temporary_access_requests WHERE id=?", (request["id"],)
            ).fetchone()[0]
            self.assertEqual(state, "PENDING")

    def test_policy_safety_failure_or_truncation_never_approves(self):
        with self.service() as service:
            request = self._create(service)
            before = service.plane.current_revision()
            unsafe = {
                "policy_regression": {"ok": False},
                "blast_radius": {"limits": {"truncated": False}},
            }
            with patch("drlink_policy_safety.preview_rule_expiry_policy_safety", return_value=unsafe):
                with self.assertRaises(ControlPlaneError):
                    service.review(
                        request["id"], actor_id="reviewer", role="Admin",
                        permissions={REVIEW_PERMISSION}, decision="approve",
                        approved_duration_seconds=900, reason="", row_version=request["row_version"],
                    )
            truncated = {
                "policy_regression": {"ok": True},
                "blast_radius": {"limits": {"truncated": True}},
            }
            with patch("drlink_policy_safety.preview_rule_expiry_policy_safety", return_value=truncated):
                with self.assertRaises(ControlPlaneError):
                    service.review(
                        request["id"], actor_id="reviewer", role="Admin",
                        permissions={REVIEW_PERMISSION}, decision="approve",
                        approved_duration_seconds=900, reason="", row_version=request["row_version"],
                    )
            self.assertEqual(service.plane.current_revision(), before)
            row = service.plane.conn.execute(
                "SELECT status,row_version FROM temporary_access_requests WHERE id=?", (request["id"],)
            ).fetchone()
            self.assertEqual((row["status"], row["row_version"]), ("PENDING", 1))

    def test_approved_restart_unauthorized_revoke_and_authoritative_reconciliation(self):
        marker = "DO_NOT_AUDIT_SECRET_MARKER_42"
        with self.service() as service:
            request = self._create(service, purpose="Emergency maintenance " + marker)
            service.review(
                request["id"], actor_id="reviewer", role="Admin",
                permissions={REVIEW_PERMISSION}, decision="approve",
                approved_duration_seconds=900, reason="approved", row_version=request["row_version"],
            )
            # Simulate a lost successful HTTP reply: a replay using the old receipt is forbidden.
            with self.assertRaises(ControlPlaneError):
                service.review(
                    request["id"], actor_id="reviewer", role="Admin",
                    permissions={REVIEW_PERMISSION}, decision="approve",
                    approved_duration_seconds=900, reason="replay", row_version=request["row_version"],
                )
        with self.service() as service:
            approved = service.get(
                request["id"], actor_id="requester", role="Operator",
                permissions={"management-temporary-access"},
            )
            self.assertEqual(approved["status"], "APPROVED")
            self.assertIsNotNone(approved["approved_expires_at"])
            for actor, role, permissions in (
                ("other-operator", "Operator", {"management-temporary-access"}),
                ("admin-without-review", "Admin", {"management-temporary-access"}),
                ("read-only", "Read Only", {"management-temporary-access", REVIEW_PERMISSION}),
            ):
                with self.subTest(actor=actor):
                    with self.assertRaises(ControlPlaneError):
                        service.revoke(
                            request["id"], actor_id=actor, role=role, permissions=permissions,
                            row_version=approved["row_version"],
                        )
            revoked = service.revoke(
                request["id"], actor_id="requester", role="Operator",
                permissions={"management-temporary-access"}, row_version=approved["row_version"],
            )
            self.assertEqual(revoked["status"], "REVOKED")
            events = service.plane.conn.execute(
                "SELECT * FROM audit_events WHERE entity_id=? ORDER BY id", (request["id"],)
            ).fetchall()
            event_types = {str(row["event_type"] or "") for row in events}
            self.assertTrue({
                "temporary_access.request.created",
                "temporary_access.request.approved",
                "temporary_access.request.revoked",
            }.issubset(event_types), event_types)
            serialized = "\n".join(str(dict(row)) for row in events)
            self.assertNotIn(marker, serialized)

    def test_v4_migration_fresh_repeat_failed_rollback_and_read_only_open(self):
        fresh_root = tempfile.mkdtemp(prefix="drlink-ui06-fresh-")
        _server_root(fresh_root)
        plane = ControlPlane(fresh_root)
        plane.close()
        writable = DB.open_control_db(fresh_root)
        try:
            self.assertEqual(DB.current_schema_version(writable), 4)
            before = writable.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version=4"
            ).fetchone()[0]
            DB.initialize(writable)
            after = writable.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version=4"
            ).fetchone()[0]
            self.assertEqual((before, after), (1, 1))
        finally:
            writable.close()
        reader = DB.open_control_db_readonly(fresh_root)
        try:
            self.assertEqual(DB.current_schema_version(reader), 4)
            self.assertEqual(reader.execute("PRAGMA query_only").fetchone()[0], 1)
            reader.execute("SELECT COUNT(*) FROM temporary_access_requests").fetchone()
            with self.assertRaises(sqlite3.OperationalError):
                reader.execute("DELETE FROM temporary_access_requests")
        finally:
            reader.close()

        conn = sqlite3.connect(":memory:", isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DB.SCHEMA_SQL)
        v24.ensure_v2_schema(conn)
        DB.ensure_v30_schema(conn)
        now = DB.utc_now_iso()
        for version, name in (
            (1, "initial_control_plane"),
            (2, "v24_canonical_objects_policy"),
            (3, "v30_management_foundation"),
        ):
            conn.execute(
                "INSERT INTO schema_migrations(version,name,applied_at) VALUES (?,?,?)",
                (version, name, now),
            )
        original = DB.ensure_temporary_access_request_schema
        def fail_after_schema(connection):
            original(connection)
            raise RuntimeError("injected UI06 migration failure")
        with patch.object(DB, "ensure_temporary_access_request_schema", side_effect=fail_after_schema):
            with self.assertRaises(RuntimeError):
                DB.initialize(conn)
        self.assertEqual(DB.current_schema_version(conn), 3)
        self.assertIsNone(conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='temporary_access_requests'"
        ).fetchone())
        self.assertIsNone(conn.execute(
            "SELECT name FROM schema_migrations WHERE version=4"
        ).fetchone())
        DB.initialize(conn)
        self.assertEqual(DB.current_schema_version(conn), 4)
        conn.close()


if __name__ == "__main__":
    unittest.main()
