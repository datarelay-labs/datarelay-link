#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_db import ControlPlaneError
from drlink_management_enrollment import ManagementEnrollmentService
from drlink_management_core import ManagementActor, ManagementAuthorizationError, ManagementCoreService
from drlink_web_auth import ROLE_ADMIN, ROLE_OPERATOR, ROLE_READ_ONLY, permissions_for_role
import frp_pki


class V30WebEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-enrollment-")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        root = Path(self.tmp)
        pki = root / "etc/drlink/pki"
        material = frp_pki.ensure_pki(pki, "127.0.0.1")
        cfg = {
            "role": "server",
            "allocator_public_url": "https://127.0.0.1:9443/enroll",
            "tls_ca_cert": "/etc/drlink/pki/ca.crt",
            "enrollments_dir": "/var/lib/drlink/enrollments",
            "bootstrap_dir": "/var/lib/drlink/bootstrap",
            "registry_file": "/var/lib/drlink/registry.json",
            "enrollment_retention_days": 30,
        }
        config = root / "etc/drlink/config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps(cfg) + "\n", encoding="utf-8")
        self.assertTrue(Path(material["ca_crt"]).is_file())
        self.service = ManagementEnrollmentService(self.tmp)

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def test_zero_touch_linux_is_display_once_and_persisted_state_is_redacted(self):
        result = self.service.issue_zero_touch(
            platform="linux", ttl_seconds=600, label="agent-a", note="lab"
        )
        self.assertTrue(result["display_once"])
        self.assertTrue(result["management_only"])
        self.assertIn("curl", result["command"])
        self.assertEqual(result["ttl_seconds"], 600)

        rows = self.service.list_enrollments()
        self.assertEqual(rows["total"], 1)
        item = rows["items"][0]
        self.assertEqual(item["id"], result["enrollment_id"])
        self.assertEqual(item["state"], "pending")
        serialized = json.dumps(rows)
        self.assertNotIn(result["command"], serialized)
        self.assertNotIn("secret", serialized.lower())

        ticket_path = Path(self.tmp) / "var/lib/drlink/bootstrap" / (result["enrollment_id"] + ".json")
        persisted = ticket_path.read_text(encoding="utf-8")
        self.assertNotIn("_short_handle", persisted)
        self.assertNotIn(result["command"], persisted)

    def test_platform_guidance_uses_existing_authority_for_windows_and_macos(self):
        windows = self.service.issue_zero_touch(platform="windows", ttl_seconds=600)
        macos = self.service.issue_zero_touch(platform="macos", ttl_seconds=600)
        self.assertEqual(windows["platform"], "windows")
        self.assertIn("powershell", windows["command"].lower())
        self.assertEqual(macos["platform"], "macos")
        self.assertIn("curl", macos["command"])
        self.assertEqual(self.service.list_enrollments()["total"], 2)

    def test_ttl_and_platform_fail_closed(self):
        with self.assertRaisesRegex(ControlPlaneError, "between 60 and 86400"):
            self.service.issue_zero_touch(platform="linux", ttl_seconds=86401)
        with self.assertRaisesRegex(ControlPlaneError, "Unsupported Agent platform"):
            self.service.issue_zero_touch(platform="solaris", ttl_seconds=600)
        self.assertEqual(self.service.list_enrollments()["total"], 0)


    def test_core_role_boundary_and_audit_attribution(self):
        core = ManagementCoreService(self.tmp)
        admin = ManagementActor.authenticated(
            "web:admin-1", permissions_for_role(ROLE_ADMIN), role=ROLE_ADMIN
        )
        operator = ManagementActor.authenticated(
            "web:operator-1", permissions_for_role(ROLE_OPERATOR), role=ROLE_OPERATOR
        )
        reader = ManagementActor.authenticated(
            "web:reader-1", permissions_for_role(ROLE_READ_ONLY), role=ROLE_READ_ONLY
        )
        with self.assertRaises(ManagementAuthorizationError):
            core.enrollment_issue_zero_touch(
                actor=operator, platform="linux", ttl_seconds=600
            )
        issued = core.enrollment_issue_zero_touch(
            actor=admin, platform="linux", ttl_seconds=600, label="audited-agent"
        )
        self.assertEqual(core.enrollment_list(actor=operator)["total"], 1)
        self.assertEqual(core.enrollment_list(actor=reader)["total"], 1)
        audit_path = Path(self.tmp) / "var/log/drlink/audit.jsonl"
        audit_text = audit_path.read_text(encoding="utf-8")
        self.assertIn('"event":"enrollment.created"', audit_text)
        self.assertIn('"actor":"web:admin-1"', audit_text)
        self.assertNotIn(issued["command"], audit_text)
        self.assertNotIn("bt1.", audit_text)


if __name__ == "__main__":
    unittest.main()
