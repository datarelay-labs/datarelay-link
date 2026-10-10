#!/usr/bin/env python3
"""DRLink 3.0 optional integration packaging/source-truth regression."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from frp_project_files import load_entries
from frp_state_paths import backup_optional_files, restore_optional_exact


EXPECTED = {
    "lib/drlink_service_accounts.py",
    "lib/drlink_automation_api.py",
    "lib/drlink_automation_server.py",
    "lib/drlink_webhooks.py",
    "lib/drlink_webhook_events.py",
    "lib/drlink_webhook_delivery.py",
    "server/drlink-automation.py",
    "server/drlink-automation.service",
    "server/drlink-webhook-delivery.py",
    "server/drlink-webhook-delivery.service",
    "server/drlink-webhook-delivery.timer",
}


class IntegrationPackagingTests(unittest.TestCase):
    def test_server_manifest_has_all_required_modules_and_protected_state(self):
        records = load_entries(ROOT / "lib/server-project-files.manifest")
        sources = {rec.source for rec in records if rec.cls in {"project", "unit", "optional"}}
        self.assertEqual(EXPECTED - sources, set())
        for src in EXPECTED:
            self.assertTrue((ROOT / src).is_file(), src)
        self.assertIn(
            "var/lib/drlink/webhook-signing.key",
            {rec.dest for rec in records if rec.cls == "protected"},
        )

    def test_backup_restore_key_and_opt_in_units_are_grounded(self):
        self.assertIn("var/lib/drlink/webhook-signing.key", backup_optional_files())
        self.assertIn("var/lib/drlink/webhook-signing.key", restore_optional_exact())
        for unit_name in ("drlink-automation.service", "drlink-webhook-delivery.timer"):
            unit = (ROOT / "server" / unit_name).read_text()
            self.assertIn("ConditionPathExists=/var/lib/drlink/drlink.db", unit)
            self.assertIn("[Install]", unit)
        worker = (ROOT / "server/drlink-webhook-delivery.service").read_text()
        self.assertIn("ReadWritePaths=/var/lib/drlink", worker)
        self.assertNotIn("SuccessExitStatus=1", worker)

    def test_development_runner_includes_new_user_paths(self):
        runner = (ROOT / "tests/run-all.sh").read_text()
        for test in ("test-v30-automation-http.py", "test-v30-automation-standalone.py",
                     "test-v30-webhook-events.py", "test-v30-webhook-delivery.py"):
            self.assertIn("python3 tests/" + test, runner)


if __name__ == "__main__":
    unittest.main()
