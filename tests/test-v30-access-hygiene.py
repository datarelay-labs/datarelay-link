#!/usr/bin/env python3
from __future__ import annotations
import sys, tempfile, unittest
import io
from contextlib import redirect_stdout
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
        self.assertTrue(all(x["evidence_quality"]=="UNKNOWN_EVIDENCE" for x in reviews))
        self.assertTrue(all(x["finding_status"]=="UNKNOWN_EVIDENCE" for x in reviews))
        cp=ControlPlane(tmp)
        try:self.assertEqual(before,cp.current_revision())
        finally:cp.close()

    def test_web_mcp_and_automation_use_same_read_only_core(self):
        from drlink_management_core import ManagementActor, ManagementAuthorizationError
        from drlink_management_mcp_adapter import ManagementMcpAdapter
        from drlink_management_web_adapter import ManagementWebApiAdapter
        from drlink_automation_api import AutomationApi

        root=tempfile.mkdtemp(prefix="drlink-hygiene-parity-")
        cp=ControlPlane(root)
        try:
            cp.upsert_client("host-a", hostname="alpha")
            cp.set_rule("remote", "standing")
            cp.set_rule_action("remote", "standing", "ALLOW")
            cp.set_rule_enabled("remote", "standing", True)
            before=cp.current_revision()
        finally:
            cp.close()
        reader=ManagementActor.authenticated("reader",{"management-read"})
        no_read=ManagementActor.authenticated("diagnostics",{"management-diagnose"})
        mcp=ManagementMcpAdapter(root)
        web=ManagementWebApiAdapter(root)
        names={tool["name"] for tool in mcp.list_tools(actor=reader)}
        self.assertIn("drlink_access_hygiene",names)
        self.assertNotIn("drlink_access_hygiene",
                         {tool["name"] for tool in mcp.list_tools(actor=no_read)})
        with self.assertRaises(ManagementAuthorizationError):
            mcp.call_tool(name="drlink_access_hygiene",arguments={},actor=no_read)
        via_mcp=mcp.call_tool(name="drlink_access_hygiene",arguments={},actor=reader)
        via_web=web.invoke(operation="drlink_access_hygiene",payload={},actor=reader)
        self.assertEqual(via_mcp["items"],via_web["items"])
        self.assertTrue(via_web["read_only"])
        self.assertFalse(via_web["auto_mutation"])
        with AutomationApi(root) as automation:
            account=automation.accounts.create("audit-reviewer",["management-read"])
            via_api=automation.invoke(
                "/api/automation/v1/drlink_access_hygiene",account["credential"],{}
            )
            self.assertEqual(via_api["items"],via_mcp["items"])
            with self.assertRaises(Exception):
                automation.invoke(
                    "/api/automation/v1/drlink_access_hygiene",account["credential"],
                    {"unexpected":True}
                )
        cp=ControlPlane(root)
        try:
            self.assertEqual(cp.current_revision(),before)
        finally:
            cp.close()

    def test_cli_list_detail_test_and_grammar_preserve_read_only_revision(self):
        from drlink_control_cli import dispatch
        from frp_ctl_grammar import match, context_help
        from frp_cli_catalog import to_internal

        root = tempfile.mkdtemp(prefix="drlink-hygiene-cli-")
        plane = ControlPlane(root)
        try:
            plane.upsert_client("host-a", hostname="alpha")
            plane.set_rule("remote", "standing")
            plane.set_rule_action("remote", "standing", "ALLOW")
            plane.set_rule_enabled("remote", "standing", True)
            rev = plane.current_revision()
        finally:
            plane.close()

        with ManagementQueryService.open_read_only(root) as query:
            finding = next(
                item for item in query.access_hygiene()["items"]
                if item["kind"] == "access-usage-review"
            )
        finding_id = "%s:%s" % (finding["kind"], finding["resource_id"])
        commands = (
            (["show", "access-hygiene"], "UNKNOWN_EVIDENCE"),
            (["show", "access-hygiene", finding_id], "UNKNOWN_EVIDENCE"),
            (["test", "access-hygiene"], "Automatic policy changes: NO"),
        )
        for tokens, expected in commands:
            parsed = match(tokens, role="server")
            self.assertEqual(parsed["status"], "ok", tokens)
            self.assertEqual(parsed["action"], "control_plane", tokens)
            self.assertEqual(to_internal(tokens), tokens)
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(dispatch(tokens, root=root), 0)
            self.assertIn(expected, stream.getvalue())
        self.assertIn("access-hygiene", context_help(["show"], "server"))
        self.assertIn("access-hygiene", context_help(["test"], "server"))
        with self.assertRaises(SystemExit):
            dispatch(["show", "access-hygiene", "missing:host"], root=root)

        plane = ControlPlane(root)
        try:
            self.assertEqual(plane.current_revision(), rev)
        finally:
            plane.close()

if __name__=="__main__": unittest.main()
