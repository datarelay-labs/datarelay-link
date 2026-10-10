#!/usr/bin/env python3
from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_v24 as v24
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_drafts import (
    DRAFT_ADMIN,
    DRAFT_OBSERVE,
    DRAFT_OPERATE,
    DRAFT_TTL_SECONDS,
    MAX_ACTIVE_DRAFTS_PER_ACTOR,
    ManagementDraftService,
)
from drlink_policy_safety import PolicySafetyService


def object_bundle(revision: int, name: str = "office") -> str:
    return f"""configurationBundle:
  context: server
  sourceRevision: {revision}
  networkObjects:
    - name: {name}
      type: ip
      value: 198.51.100.10
"""


def policy_bundle(revision: int) -> str:
    return f"""configurationBundle:
  context: server
  sourceRevision: {revision}
  networkObjects:
    - name: src
      type: ip
      value: 198.51.100.10
    - name: dst
      type: ip
      value: 198.51.100.20
  serviceObjects:
    - name: ssh
      type: tcp
      port: 22
  remoteAccess:
    mode: whitelist
    enforcement: enabled
    rules:
      - name: allow-ssh
        source: src
        destination: dst
        service: ssh
        enabled: true
"""


class V30ManagementDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-draft-")
        self.base_time = datetime(2026, 10, 4, 4, 0, tzinfo=timezone.utc)
        self.service = ManagementDraftService(self.tmp)

    def tearDown(self):
        self.service.close()

    def test_core_draft_service_has_no_web_dependency(self):
        source = (ROOT / "lib/drlink_management_drafts.py").read_text(encoding="utf-8")
        self.assertNotIn("drlink_web", source)
        self.assertIn("prepare_v24_plan", source)
        self.assertIn("apply_v24_plan", source)

    def test_preview_is_zero_mutation_and_uses_canonical_bundle_plan(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:reader",
            bundle_text=object_bundle(revision),
            now=self.base_time,
        )
        before_objects = len(self.service.plane.list_objects())
        preview = self.service.preview(
            draft["id"],
            actor_id="web:reader",
            authority=DRAFT_OBSERVE,
            now=self.base_time + timedelta(seconds=1),
        )
        self.assertEqual(self.service.plane.current_revision(), revision)
        self.assertEqual(len(self.service.plane.list_objects()), before_objects)
        self.assertFalse(preview["no_change"])
        self.assertEqual(preview["changes"][0]["kind"], "network-object")
        self.assertFalse(preview["requires_admin"])
        self.assertIn("No changes were applied.", preview["formatted_plan"])

    def test_read_only_cannot_apply_but_operator_can_apply_nonpolicy_draft(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator",
            bundle_text=object_bundle(revision),
            now=self.base_time,
        )
        preview = self.service.preview(
            draft["id"],
            actor_id="web:operator",
            authority=DRAFT_OPERATE,
            now=self.base_time + timedelta(seconds=1),
        )
        with self.assertRaises(ControlPlaneError):
            self.service.apply(
                draft["id"],
                actor_id="web:operator",
                authority=DRAFT_OBSERVE,
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
                now=self.base_time + timedelta(seconds=2),
            )
        result = self.service.apply(
            draft["id"],
            actor_id="web:operator",
            authority=DRAFT_OPERATE,
            change_plan_id=preview["change_plan_id"],
            confirmation="APPLY",
            now=self.base_time + timedelta(seconds=3),
        )
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["revision"], revision + 1)
        obj = self.service.plane.get_object("office")
        self.assertIsNotNone(obj)
        stored = self.service.get(draft["id"], actor_id="web:operator")
        self.assertEqual(stored["status"], "APPLIED")

    def test_policy_or_security_impact_requires_admin(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator",
            bundle_text=policy_bundle(revision),
            now=self.base_time,
        )
        preview = self.service.preview(
            draft["id"],
            actor_id="web:operator",
            authority=DRAFT_OPERATE,
            now=self.base_time + timedelta(seconds=1),
        )
        self.assertTrue(preview["requires_admin"])
        with self.assertRaisesRegex(ControlPlaneError, "Admin authority"):
            self.service.apply(
                draft["id"],
                actor_id="web:operator",
                authority=DRAFT_OPERATE,
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
                now=self.base_time + timedelta(seconds=2),
            )
        result = self.service.apply(
            draft["id"],
            actor_id="web:operator",
            authority=DRAFT_ADMIN,
            change_plan_id=preview["change_plan_id"],
            confirmation="APPLY",
            now=self.base_time + timedelta(seconds=3),
        )
        self.assertEqual(result["status"], "APPLIED")
        decision = v24.evaluate_selector_policy(
            self.service.plane,
            "remote",
            source_name="src",
            destination_name="dst",
            service_name="ssh",
        )
        self.assertEqual(decision["result"], "ALLOW")

    def test_policy_draft_preview_has_overlay_and_required_test_blocks_apply(self):
        v24.set_network_object(
            self.service.plane,
            "safe-src",
            type="ip",
            value="198.51.100.60",
            oneshot=True,
        )
        v24.set_network_object(
            self.service.plane,
            "safe-dst",
            type="ip",
            value="198.51.100.61",
            oneshot=True,
        )
        v24.set_service_object(
            self.service.plane,
            "safe-ssh",
            type="tcp",
            port=22,
            oneshot=True,
        )
        v24.set_access_rule(
            self.service.plane,
            "remote",
            "safe-allow",
            mode="whitelist",
            source="safe-src",
            destination="safe-dst",
            service="safe-ssh",
            enabled=True,
            oneshot=True,
        )
        with PolicySafetyService(self.tmp) as safety:
            saved = safety.preview_definition(
                actor_id="web:admin",
                operation="set",
                definition={
                    "name": "must-allow-safe-ssh",
                    "plane": "remote",
                    "source": "safe-src",
                    "destination": "safe-dst",
                    "service": "safe-ssh",
                    "expected": "ALLOW",
                    "required": True,
                    "enabled": True,
                },
            )
            safety.apply_definition(
                actor_id="web:admin",
                change_plan_id=saved["change_plan_id"],
                confirmation="APPLY",
            )

        revision = self.service.plane.current_revision()
        bundle = self.service.export_current_configuration()
        self.assertIn("name: safe-allow", bundle)
        # Narrow the exact current configuration while preserving every dependency.
        bundle = bundle.replace(
            "      enabled: true\n",
            "      enabled: false\n",
            1,
        )
        self.assertIn("name: safe-allow", bundle)
        self.assertIn("enabled: false", bundle)
        draft = self.service.create(
            actor_id="web:admin",
            bundle_text=bundle,
            now=self.base_time,
        )
        preview = self.service.preview(
            draft["id"],
            actor_id="web:admin",
            authority=DRAFT_ADMIN,
            now=self.base_time + timedelta(seconds=1),
        )
        self.assertEqual(self.service.plane.current_revision(), revision)
        self.assertTrue(bool(self.service.plane._get_rule("remote", "safe-allow")["enabled"]))
        self.assertIsNotNone(preview["graph_overlay"])
        self.assertIsNotNone(preview["blast_radius"])
        self.assertTrue(preview["blast_radius"]["access_narrowed"])
        self.assertTrue(preview["blast_radius"]["newly_blocked"])
        self.assertFalse(preview["policy_regression"]["ok"])
        self.assertEqual(preview["policy_regression"]["required_failed"], 1)
        self.assertEqual(
            preview["impact"]["required_policy_test_failures"],
            1,
        )
        with self.assertRaisesRegex(
            ControlPlaneError, "Required Policy Regression Tests failed"
        ):
            self.service.apply(
                draft["id"],
                actor_id="web:admin",
                authority=DRAFT_ADMIN,
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
                now=self.base_time + timedelta(seconds=2),
            )
        self.assertEqual(self.service.plane.current_revision(), revision)
        self.assertTrue(bool(self.service.plane._get_rule("remote", "safe-allow")["enabled"]))

    def test_stale_revision_fails_closed_without_rebase(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator",
            bundle_text=object_bundle(revision),
            now=self.base_time,
        )
        v24.set_network_object(
            self.service.plane,
            "other",
            type="ip",
            value="203.0.113.7",
            oneshot=True,
        )
        with self.assertRaises(ConcurrencyError):
            self.service.preview(
                draft["id"],
                actor_id="web:operator",
                authority=DRAFT_OPERATE,
                now=self.base_time + timedelta(seconds=1),
            )
        self.assertIsNone(self.service.plane.get_object("office"))

    def test_cancel_has_zero_authoritative_mutation(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator",
            bundle_text=object_bundle(revision),
            now=self.base_time,
        )
        result = self.service.cancel(
            draft["id"],
            actor_id="web:operator",
            now=self.base_time + timedelta(seconds=1),
        )
        self.assertFalse(result["authoritative_mutation"])
        self.assertEqual(self.service.plane.current_revision(), revision)
        self.assertIsNone(self.service.plane.get_object("office"))
        with self.assertRaises(ControlPlaneError):
            self.service.preview(
                draft["id"],
                actor_id="web:operator",
                authority=DRAFT_OPERATE,
                now=self.base_time + timedelta(seconds=2),
            )

    def test_draft_is_actor_bound_and_export_is_exact(self):
        revision = self.service.plane.current_revision()
        raw = object_bundle(revision)
        draft = self.service.create(
            actor_id="web:alice",
            bundle_text=raw,
            now=self.base_time,
        )
        self.assertEqual(
            self.service.export(draft["id"], actor_id="web:alice"), raw
        )
        with self.assertRaises(ControlPlaneError):
            self.service.get(draft["id"], actor_id="web:bob")
        with self.assertRaises(ControlPlaneError):
            self.service.export(draft["id"], actor_id="web:bob")

    def test_draft_expiry_is_truthful_and_nonmutating(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator",
            bundle_text=object_bundle(revision),
            now=self.base_time,
        )
        later = self.base_time + timedelta(seconds=DRAFT_TTL_SECONDS + 1)
        with self.assertRaisesRegex(ControlPlaneError, "no longer editable"):
            self.service.preview(
                draft["id"],
                actor_id="web:operator",
                authority=DRAFT_OPERATE,
                now=later,
            )
        stored = self.service.get(
            draft["id"], actor_id="web:operator", now=later
        )
        self.assertEqual(stored["status"], "EXPIRED")
        self.assertEqual(self.service.plane.current_revision(), revision)

    def test_concurrent_draft_creates_preserve_per_actor_limit(self):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        import threading

        actor = "web:concurrent-bound"
        for idx in range(MAX_ACTIVE_DRAFTS_PER_ACTOR - 1):
            self.service.create(actor_id=actor, now=self.base_time)

        first = ManagementDraftService(self.tmp)
        second = ManagementDraftService(self.tmp)
        count_read = threading.Event()
        release_read = threading.Event()

        class PausedCountConnection:
            def __init__(self, real):
                self.real = real

            def __getattr__(self, name):
                return getattr(self.real, name)

            def execute(self, sql, *args):
                cursor = self.real.execute(sql, *args)
                if sql.startswith("SELECT COUNT(*) FROM management_drafts"):
                    result = cursor.fetchone()
                    count_read.set()
                    if not release_read.wait(5):
                        raise AssertionError("Test count-read coordination timed out")

                    class CountResult:
                        def fetchone(self):
                            return result

                    return CountResult()
                return cursor

        first.plane.conn = PausedCountConnection(first.plane.conn)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                pending_first = workers.submit(
                    first.create, actor_id=actor, now=self.base_time,
                )
                self.assertTrue(count_read.wait(3))
                pending_second = workers.submit(
                    second.create, actor_id=actor, now=self.base_time,
                )
                try:
                    pending_second.result(timeout=0.25)
                except FutureTimeoutError:
                    pass
                finally:
                    release_read.set()
                outcomes = []
                for future in (pending_first, pending_second):
                    try:
                        outcomes.append(future.result(timeout=5))
                    except ControlPlaneError as exc:
                        outcomes.append(exc)
            successes = sum(isinstance(value, dict) for value in outcomes)
            self.assertEqual(successes, 1, outcomes)
            count = self.service.plane.conn.execute(
                "SELECT COUNT(*) FROM management_drafts "
                "WHERE actor_id=? AND status='DRAFT'", (actor,),
            ).fetchone()[0]
            self.assertEqual(count, MAX_ACTIVE_DRAFTS_PER_ACTOR)
        finally:
            release_read.set()
            first.close()
            second.close()

    def test_draft_count_and_size_are_bounded(self):
        revision = self.service.plane.current_revision()
        for idx in range(MAX_ACTIVE_DRAFTS_PER_ACTOR):
            self.service.create(
                actor_id="web:bounded",
                bundle_text=object_bundle(revision, "obj-%02d" % idx),
                now=self.base_time,
            )
        with self.assertRaisesRegex(ControlPlaneError, "limit reached"):
            self.service.create(
                actor_id="web:bounded",
                bundle_text=object_bundle(revision, "overflow"),
                now=self.base_time,
            )
        with self.assertRaisesRegex(ControlPlaneError, "byte bound"):
            self.service.create(
                actor_id="web:other",
                bundle_text="x" * (129 * 1024),
                now=self.base_time,
            )

    def test_apply_requires_exact_confirmation(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator",
            bundle_text=object_bundle(revision),
            now=self.base_time,
        )
        preview = self.service.preview(
            draft["id"],
            actor_id="web:operator",
            authority=DRAFT_OPERATE,
            now=self.base_time + timedelta(seconds=1),
        )
        with self.assertRaisesRegex(ControlPlaneError, "explicit confirmation"):
            self.service.apply(
                draft["id"],
                actor_id="web:operator",
                authority=DRAFT_OPERATE,
                change_plan_id=preview["change_plan_id"],
                confirmation="yes",
                now=self.base_time + timedelta(seconds=2),
            )
        self.assertEqual(self.service.plane.current_revision(), revision)


    def test_apply_requires_previewed_actor_bound_change_plan(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:alice", bundle_text=object_bundle(revision), now=self.base_time
        )
        preview = self.service.preview(
            draft["id"], actor_id="web:alice", authority=DRAFT_OPERATE, now=self.base_time
        )
        self.assertTrue(preview["change_plan_id"].startswith("cp_"))
        with self.assertRaises(ControlPlaneError):
            self.service.apply(
                draft["id"], actor_id="web:bob", authority=DRAFT_OPERATE,
                change_plan_id=preview["change_plan_id"], confirmation="APPLY", now=self.base_time,
            )
        self.assertIsNone(self.service.plane.get_object("office"))

    def test_edit_after_preview_invalidates_change_plan(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator", bundle_text=object_bundle(revision), now=self.base_time
        )
        preview = self.service.preview(
            draft["id"], actor_id="web:operator", authority=DRAFT_OPERATE, now=self.base_time
        )
        self.service.update(
            draft["id"], actor_id="web:operator", bundle_text=object_bundle(revision, "changed"), now=self.base_time
        )
        with self.assertRaisesRegex(ControlPlaneError, "changed after preview"):
            self.service.apply(
                draft["id"], actor_id="web:operator", authority=DRAFT_OPERATE,
                change_plan_id=preview["change_plan_id"], confirmation="APPLY", now=self.base_time,
            )
        self.assertIsNone(self.service.plane.get_object("changed"))


    def test_change_plan_is_single_use_after_apply(self):
        revision = self.service.plane.current_revision()
        draft = self.service.create(
            actor_id="web:operator", bundle_text=object_bundle(revision), now=self.base_time
        )
        preview = self.service.preview(
            draft["id"], actor_id="web:operator", authority=DRAFT_OPERATE, now=self.base_time
        )
        self.service.apply(
            draft["id"], actor_id="web:operator", authority=DRAFT_OPERATE,
            change_plan_id=preview["change_plan_id"], confirmation="APPLY", now=self.base_time,
        )
        with self.assertRaisesRegex(ControlPlaneError, "no longer pending"):
            self.service.apply(
                draft["id"], actor_id="web:operator", authority=DRAFT_OPERATE,
                change_plan_id=preview["change_plan_id"], confirmation="APPLY", now=self.base_time,
            )


if __name__ == "__main__":
    unittest.main()
