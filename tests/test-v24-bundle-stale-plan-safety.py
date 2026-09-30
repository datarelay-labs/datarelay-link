#!/usr/bin/env python3
"""P0: ConfigurationBundle stale-plan / current-state safety.

Apply must re-diff and recalculate security impact against authoritative state
under a race-safe guard. Stale prepared plans must not:
  - return false NO_CHANGE after concurrent mutation
  - remove the now-last BLACKLIST blocker without current-state confirmation
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ConcurrencyError, ConfirmationRequired, ControlPlane
import drlink_v24 as v24
from drlink_v24_bundle import apply_v24_plan, export_configuration_v24, prepare_v24_plan


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class BundleStalePlanSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-stale-plan-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ.pop("DRLINK_CONFIRM", None)
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def test_stale_no_change_plan_is_rejected_without_overwrite(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        prepared_rev = self.plane.current_revision()
        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.10
""",
        )
        self.assertTrue(plan.no_change)
        self.assertEqual(plan.base_revision, prepared_rev)

        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.20", oneshot=True
        )
        concurrent_rev = self.plane.current_revision()
        self.assertGreater(concurrent_rev, prepared_rev)

        with self.assertRaises(ConcurrencyError) as ctx:
            apply_v24_plan(self.plane, plan)
        self.assertIn("REVISION_CONFLICT", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), concurrent_rev)
        self.assertEqual(
            self.plane._object_values(self.plane.get_object("office")["id"])[:1],
            ["198.51.100.20"],
        )

    def test_true_no_change_remains_idempotent(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        yaml_text = """configurationBundle:
  context: server
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.10
"""
        plan = prepare_v24_plan(self.plane, yaml_text)
        self.assertTrue(plan.no_change)
        rev_before = self.plane.current_revision()
        result = apply_v24_plan(self.plane, plan)
        self.assertEqual(result["status"], "NO_CHANGE")
        self.assertEqual(result["revision"], rev_before)
        self.assertEqual(self.plane.current_revision(), rev_before)

    def test_normal_apply_still_applied(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.30
""",
        )
        self.assertFalse(plan.no_change)
        result = apply_v24_plan(self.plane, plan)
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(
            self.plane._object_values(self.plane.get_object("office")["id"])[:1],
            ["198.51.100.30"],
        )

    def test_exported_bundle_pins_source_revision_and_rejects_stale_apply(self):
        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.10", oneshot=True
        )
        exported_rev = self.plane.current_revision()
        exported = export_configuration_v24(self.plane)
        self.assertIn("sourceRevision: %s" % exported_rev, exported)

        edited = exported.replace("198.51.100.10", "198.51.100.30", 1)
        plan = prepare_v24_plan(self.plane, edited)
        self.assertEqual(plan.base_revision, exported_rev)
        self.assertFalse(plan.no_change)

        v24.set_network_object(
            self.plane, "office", type="ip", value="198.51.100.20", oneshot=True
        )
        concurrent_rev = self.plane.current_revision()

        with self.assertRaises(ConcurrencyError) as ctx:
            apply_v24_plan(self.plane, plan, confirm=True)
        self.assertIn("REVISION_CONFLICT", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), concurrent_rev)
        self.assertEqual(
            self.plane._object_values(self.plane.get_object("office")["id"])[:1],
            ["198.51.100.20"],
        )

    def test_source_revision_validation_fails_closed(self):
        for token in ("-1", "not-a-revision", "true"):
            with self.subTest(source_revision=token):
                raw = """configurationBundle:
  context: server
  sourceRevision: %s
  networkObjects:
    - name: office
      type: ip
      value: 198.51.100.10
""" % token
                with self.assertRaises(Exception) as ctx:
                    prepare_v24_plan(self.plane, raw)
                self.assertIn("sourceRevision", str(ctx.exception))

    def test_stale_plan_cannot_bypass_last_blacklist_confirmation(self):
        v24.set_network_object(self.plane, "src", type="ip", value="198.51.100.1", oneshot=True)
        v24.set_network_object(self.plane, "dst", type="ip", value="198.51.100.2", oneshot=True)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        for name in ("deny1", "deny2"):
            v24.set_access_rule(
                self.plane,
                "remote",
                name,
                mode="blacklist",
                source="src",
                destination="dst",
                service="ssh",
                enabled=True,
                oneshot=True,
            )

        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  remoteAccess:
    mode: blacklist
    enforcement: enabled
    rules:
      - name: deny1
        source: src
        destination: dst
        service: ssh
        enabled: false
      - name: deny2
        source: src
        destination: dst
        service: ssh
        enabled: true
""",
        )
        self.assertFalse(plan.no_change)
        self.assertEqual(plan.security_impact, [])

        # Concurrent writer disables deny2 with confirmation → deny1 is now last blocker.
        v24.set_access_rule(
            self.plane, "remote", "deny2", enabled=False, oneshot=True, confirm=True
        )
        self.assertTrue(bool(self.plane._get_rule("remote", "deny1")["enabled"]))
        self.assertFalse(bool(self.plane._get_rule("remote", "deny2")["enabled"]))

        rev_before = self.plane.current_revision()
        with self.assertRaises(ConcurrencyError) as ctx:
            apply_v24_plan(self.plane, plan, confirm=False)
        self.assertIn("REVISION_CONFLICT", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), rev_before)
        self.assertTrue(bool(self.plane._get_rule("remote", "deny1")["enabled"]))
        self.assertFalse(bool(self.plane._get_rule("remote", "deny2")["enabled"]))

        # The operator must re-review current state. The fresh plan now exposes
        # the broadened-access confirmation that the stale plan could not bypass.
        fresh = prepare_v24_plan(self.plane, plan.source_text)
        with self.assertRaises(ConfirmationRequired) as fresh_ctx:
            apply_v24_plan(self.plane, fresh, confirm=False)
        self.assertTrue(fresh_ctx.exception.impact.get("access_broadened"))
        result = apply_v24_plan(self.plane, fresh, confirm=True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertFalse(bool(self.plane._get_rule("remote", "deny1")["enabled"]))

    def test_confirmation_cancel_leaves_state_unchanged(self):
        v24.set_network_object(self.plane, "src", type="ip", value="198.51.100.1", oneshot=True)
        v24.set_network_object(self.plane, "dst", type="ip", value="198.51.100.2", oneshot=True)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_access_rule(
            self.plane,
            "remote",
            "deny1",
            mode="blacklist",
            source="src",
            destination="dst",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  remoteAccess:
    mode: blacklist
    enforcement: enabled
    rules:
      - name: deny1
        source: src
        destination: dst
        service: ssh
        enabled: false
""",
        )
        self.assertTrue(plan.security_impact)
        rev_before = self.plane.current_revision()
        with self.assertRaises(ConfirmationRequired):
            apply_v24_plan(self.plane, plan, confirm=False)
        self.assertEqual(self.plane.current_revision(), rev_before)
        self.assertTrue(bool(self.plane._get_rule("remote", "deny1")["enabled"]))


if __name__ == "__main__":
    unittest.main()
