#!/usr/bin/env python3
from __future__ import annotations
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"lib"))
from drlink_automation_api import AutomationApi
from drlink_control_db import ControlPlaneError

class AutomationApiTests(unittest.TestCase):
    def test_allowlist_and_core_permission_boundary(self):
        root=tempfile.mkdtemp(prefix="drlink-auto-")
        api=AutomationApi(root)
        try:
            sa=api.accounts.create("reader",["management-read"])
            out=api.invoke("/api/automation/v1/drlink_inventory_list",sa["credential"],{"resource_type":"managed-host","limit":10})
            self.assertEqual(out["resource_type"],"managed-host")
            with self.assertRaises(ControlPlaneError):
                api.invoke("/api/automation/v1/drlink_policy_test",sa["credential"],{"plane":"remote","source":"a","destination":"b"})
            with self.assertRaises(ControlPlaneError):
                api.invoke("/api/automation/v1/drlink_agent_update_rollout_start",sa["credential"],{})
        finally: api.close()
if __name__=="__main__": unittest.main()
