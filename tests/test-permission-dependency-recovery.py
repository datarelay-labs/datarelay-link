#!/usr/bin/env python3
"""Public Permission recovery guidance preserves fail-closed reference safety."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import frp_cli_catalog as catalog
import drlink_v24 as v24
from drlink_control_plane import ControlPlane, ControlPlaneError


class PermissionDependencyRecovery(unittest.TestCase):
    def test_public_help_discovers_inspection_and_protected_delete_recovery(self):
        for resource in ("permission-object", "permission-group"):
            for action in ("show", "unset"):
                with self.subTest(resource=resource, action=action):
                    help_text = catalog.command_help(catalog.find([action, resource], role="server"))
                    self.assertIn("show ai-access", help_text)
                    self.assertIn("set ai-access <RULE>", help_text)
                    self.assertIn("unset ai-access <RULE>", help_text)
                    self.assertIn("Disabling", help_text)
                    self.assertNotIn(" references", catalog.usage_line(catalog.find([action, resource])))
                    if resource == "permission-object":
                        self.assertIn("show permission-groups", help_text)
                        self.assertIn("set permission-group <GROUP>", help_text)
                    if action == "unset":
                        self.assertIn("Confirmation: y_n", help_text)

    def test_referenced_object_error_names_canonical_recovery_without_mutation(self):
        self._assert_error_recovery("permission-object")

    def test_referenced_group_error_names_canonical_recovery_without_mutation(self):
        self._assert_error_recovery("permission-group")

    def _assert_error_recovery(self, resource):
        with tempfile.TemporaryDirectory(prefix="drlink-permission-recovery-") as root:
            Path(root, "etc/drlink").mkdir(parents=True)
            Path(root, "etc/drlink/config.json").write_text('{"role":"server"}\n')
            plane = ControlPlane(root)
            self.addCleanup(plane.close)
            plane.set_ai_principal("bot", enabled=True)
            plane.conn.execute("UPDATE ai_principals SET credential_status = 'verified' WHERE name = 'bot'")
            plane.conn.commit()
            v24.set_network_object(plane, "target", type="ip", value="198.51.100.10", oneshot=True)
            v24.set_permission_object(plane, "read-only", permissions=["host-info"], oneshot=True)
            v24.set_permission_group(plane, "ops", members=["read-only"], oneshot=True)
            # Disabled rules still hold immutable references and must block deletion.
            v24.set_ai_access_rule(plane, "allow-read", mode="whitelist", source="bot",
                                  destination="target", permission="read-only" if resource == "permission-object" else "ops",
                                  enabled=False, oneshot=True)
            before = list(plane.conn.iterdump())
            fn = v24.unset_permission_object if resource == "permission-object" else v24.unset_permission_group
            name = "read-only" if resource == "permission-object" else "ops"
            with patch.object(plane, "_mutate", side_effect=AssertionError("reference validation must precede mutation/confirmation")):
                with self.assertRaises(ControlPlaneError) as error:
                    fn(plane, name, confirm=True)
            text = str(error.exception)
            self.assertIn("still referenced", text)
            self.assertIn("No changes were applied.", text)
            self.assertIn("show ai-access allow-read", text)
            self.assertIn("set ai-access allow-read", text)
            self.assertIn("unset ai-access allow-read", text)
            self.assertIn("Disabling", text)
            if resource == "permission-object":
                self.assertIn("show permission-group ops", text)
                self.assertIn("set permission-group ops", text)
            self.assertEqual(before, list(plane.conn.iterdump()))


if __name__ == "__main__":
    unittest.main()
