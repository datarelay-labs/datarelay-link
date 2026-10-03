#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_management_catalog as MC
import drlink_v24
from drlink_v30_temporal import (
    ACTIVE,
    CLOCK_UNTRUSTED,
    EXPIRED,
    PERMANENT,
    canonical_expiry,
    temporary_access_state,
)


class ManagementCatalogTests(unittest.TestCase):
    def test_catalog_is_self_consistent_and_separate_from_target_permissions(self):
        MC.validate_catalog(target_permissions=frozenset(drlink_v24.PERMISSIONS))
        self.assertFalse(MC.MANAGEMENT_PERMISSION_NAMES & set(drlink_v24.PERMISSIONS))
        self.assertIn("management-temporary-access", MC.MANAGEMENT_PERMISSION_NAMES)
        self.assertIn("management-emergency-cutoff", MC.MANAGEMENT_PERMISSION_NAMES)

    def test_incident_change_requires_dedicated_permission_and_strong_annotation(self):
        tools = {t.name: t for t in MC.MANAGEMENT_TOOLS}
        apply_tool = tools["drlink_emergency_cutoff_apply"]
        self.assertEqual(apply_tool.operation_class, MC.INCIDENT_CHANGE)
        self.assertEqual(apply_tool.permission, "management-emergency-cutoff")
        self.assertEqual(apply_tool.plugin_exposure, MC.PLUGIN_CONTROLLED)
        self.assertTrue(apply_tool.destructive)
        self.assertFalse(apply_tool.read_only)

    def test_recovery_authority_is_not_advertised_as_management_tool(self):
        names = MC.MANAGEMENT_TOOL_NAMES
        for forbidden in ("restore", "uninstall", "mfa", "certificate_import", "backup_create"):
            self.assertFalse(any(forbidden in name for name in names), forbidden)

    def test_descriptors_carry_operation_permission_and_plugin_metadata(self):
        by_name = {d["name"]: d for d in MC.mcp_management_descriptors()}
        d = by_name["drlink_temporary_access_apply"]
        self.assertEqual(d["_meta"]["datarelay/operationClass"], MC.CHANGE)
        self.assertEqual(
            d["_meta"]["datarelay/requiredPermission"],
            "management-temporary-access",
        )
        self.assertEqual(
            d["_meta"]["datarelay/pluginExposure"],
            MC.PLUGIN_CONTROLLED,
        )
        self.assertFalse(d["annotations"]["readOnlyHint"])


class TemporaryAccessTimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)

    def test_no_expiry_is_permanent(self):
        state = temporary_access_state(None, now=self.now)
        self.assertEqual(state.status, PERMANENT)
        self.assertTrue(state.allows_new_authorization)

    def test_future_expiry_is_active(self):
        expiry = self.now + timedelta(hours=2)
        state = temporary_access_state(expiry.isoformat(), now=self.now)
        self.assertEqual(state.status, ACTIVE)
        self.assertTrue(state.allows_new_authorization)

    def test_expiry_is_fail_closed_at_boundary(self):
        state = temporary_access_state(self.now.isoformat(), now=self.now)
        self.assertEqual(state.status, EXPIRED)
        self.assertFalse(state.allows_new_authorization)

    def test_malformed_expiry_fails_closed(self):
        state = temporary_access_state("tomorrow-ish", now=self.now)
        self.assertEqual(state.status, CLOCK_UNTRUSTED)
        self.assertFalse(state.allows_new_authorization)

    def test_material_backward_clock_fails_closed(self):
        created = self.now + timedelta(minutes=6)
        expiry = self.now + timedelta(hours=2)
        state = temporary_access_state(
            expiry.isoformat(),
            created_at=created.isoformat(),
            now=self.now,
        )
        self.assertEqual(state.status, CLOCK_UNTRUSTED)
        self.assertFalse(state.allows_new_authorization)

    def test_small_clock_skew_is_tolerated(self):
        created = self.now + timedelta(minutes=4, seconds=59)
        expiry = self.now + timedelta(hours=2)
        state = temporary_access_state(
            expiry.isoformat(),
            created_at=created.isoformat(),
            now=self.now,
        )
        self.assertEqual(state.status, ACTIVE)

    def test_canonical_expiry_is_utc_z(self):
        self.assertEqual(
            canonical_expiry("2026-10-03T23:00:00+09:00"),
            "2026-10-03T14:00:00Z",
        )


if __name__ == "__main__":
    unittest.main()
