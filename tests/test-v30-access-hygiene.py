#!/usr/bin/env python3
from __future__ import annotations
import sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"lib"))
from drlink_control_plane import ControlPlane
from drlink_management_service import ManagementQueryService

class AccessHygieneTests(unittest.TestCase):
    def test_insufficient_history_never_claims_unused_and_never_mutates(self):
        tmp=tempfile.mkdtemp(prefix="drlink-hygiene-")
        cp=ControlPlane(tmp)
        try:
            cp.upsert_client("host-a", hostname="host-a")
            cp.set_rule("remote", "standing")
            cp.set_rule_action("remote", "standing", "ALLOW")
            cp.set_rule_enabled("remote", "standing", True)
            before=cp.current_revision()
        finally:
            cp.close()
        with ManagementQueryService(tmp) as svc:
            result=svc.access_hygiene(now=datetime(2026,10,8,tzinfo=timezone.utc))
        self.assertTrue(result["read_only"])
        self.assertFalse(result["auto_mutation"])
        reviews=[x for x in result["items"] if x["kind"]=="access-usage-review"]
        self.assertTrue(reviews)
        self.assertTrue(all(x["evidence_quality"]=="INSUFFICIENT_DATA" for x in reviews))
        cp=ControlPlane(tmp)
        try:self.assertEqual(before,cp.current_revision())
        finally:cp.close()

if __name__=="__main__": unittest.main()
