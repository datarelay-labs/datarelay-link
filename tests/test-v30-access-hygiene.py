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
            attention=svc.attention_summary()
        self.assertFalse(any(
            item["kind"] == "access-hygiene-review"
            for item in attention["items"]
        ))
        self.assertGreater(
            attention["signals"]["access_hygiene"]["unknown_evidence"], 0
        )
        self.assertEqual(attention["signals"]["access_hygiene"]["action_required"], 0)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["auto_mutation"])
        reviews=[x for x in result["items"] if x["kind"]=="access-usage-review"]
        self.assertTrue(reviews)
        self.assertTrue(all(x["evidence_quality"]=="UNKNOWN_EVIDENCE" for x in reviews))
        self.assertTrue(all(x["finding_status"]=="UNKNOWN_EVIDENCE" for x in reviews))
        cp=ControlPlane(tmp)
        try:self.assertEqual(before,cp.current_revision())
        finally:cp.close()

    def test_evidence_age_uses_recorded_timestamp_never_infers_unused_access(self):
        root = tempfile.mkdtemp(prefix="drlink-hygiene-age-")
        now = datetime(2026, 10, 8, tzinfo=timezone.utc)
        last_seen = now - timedelta(days=45, hours=3)
        plane = ControlPlane(root)
        try:
            plane.upsert_client("known-age", hostname="known-age")
            plane.upsert_client("unknown-age", hostname="unknown-age")
            plane.upsert_client("invalid-age", hostname="invalid-age")
            plane.upsert_client("invalid-late", hostname="invalid-late")
            plane.conn.execute(
                "UPDATE clients SET last_seen=? WHERE id=?",
                (last_seen.isoformat().replace("+00:00", "Z"), "known-age"),
            )
            # Newly upserted hosts receive a live timestamp by default; erase
            # only this isolated fixture's observation to model unknown age.
            plane.conn.execute(
                "UPDATE clients SET last_seen=NULL WHERE id='unknown-age'"
            )
            plane.conn.execute(
                "UPDATE clients SET last_seen='0000-invalid' WHERE id='invalid-age'"
            )
            # Lexically late but invalid evidence must not be silently omitted
            # from the review just because it sorts after the UTC cutoff.
            plane.conn.execute(
                "UPDATE clients SET last_seen='zz-not-a-timestamp' WHERE id='invalid-late'"
            )
            plane.conn.commit()
            revision = plane.current_revision()
        finally:
            plane.close()
        with ManagementQueryService.open_read_only(root) as service:
            result = service.access_hygiene(now=now)
        by_id = {
            item["resource_id"]: item
            for item in result["items"] if item["kind"] == "stale-host"
        }
        self.assertEqual(by_id["known-age"]["age_days"], 45)
        self.assertEqual(by_id["known-age"]["age_reference"], "last_seen")
        self.assertEqual(by_id["unknown-age"]["age_days"], None)
        self.assertEqual(by_id["unknown-age"]["evidence_quality"], "UNKNOWN_EVIDENCE")
        self.assertEqual(by_id["invalid-age"]["age_days"], None)
        self.assertEqual(by_id["invalid-age"]["evidence_quality"], "UNKNOWN_EVIDENCE")
        self.assertEqual(by_id["invalid-age"]["finding_status"], "UNKNOWN_EVIDENCE")
        self.assertEqual(by_id["invalid-late"]["age_days"], None)
        self.assertEqual(by_id["invalid-late"]["evidence_quality"], "UNKNOWN_EVIDENCE")
        self.assertEqual(by_id["invalid-late"]["finding_status"], "UNKNOWN_EVIDENCE")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["auto_mutation"])
        reader = ControlPlane(root, read_only=True)
        try:
            self.assertEqual(reader.current_revision(), revision)
        finally:
            reader.close()

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

    def test_expiring_service_accounts_are_advisory_without_exposing_tokens(self):
        import json
        from drlink_service_accounts import ServiceAccountStore

        root = tempfile.mkdtemp(prefix="drlink-hygiene-expiring-account-")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires = (now + timedelta(days=3)).isoformat().replace("+00:00", "Z")
        later = (now + timedelta(days=40)).isoformat().replace("+00:00", "Z")
        with ServiceAccountStore(root) as store:
            near = store.create("review-soon", ["management-read"], expires_at=expires)
            store.create("future-account", ["management-read"], expires_at=later)
        plane = ControlPlane(root)
        try:
            before_revision = plane.current_revision()
        finally:
            plane.close()
        with ManagementQueryService.open_read_only(root) as service:
            hygiene = service.access_hygiene(now=now)
            attention = service.attention_summary()
        matches = [
            item for item in hygiene["items"]
            if item["kind"] == "service-account-expiry"
        ]
        self.assertEqual(len(matches), 1)
        item = matches[0]
        self.assertEqual(item["resource_id"], near["id"])
        self.assertEqual(item["finding_status"], "ACTION_REQUIRED")
        self.assertEqual(item["evidence_quality"], "OBSERVED")
        self.assertEqual(item["evidence"]["expires_at"], expires)
        self.assertNotIn(near["credential"], json.dumps(hygiene))
        self.assertNotIn(near["credential"], json.dumps(attention))
        self.assertGreaterEqual(attention["signals"]["access_hygiene"]["action_required"], 1)
        plane = ControlPlane(root)
        try:
            self.assertEqual(plane.current_revision(), before_revision)
        finally:
            plane.close()

    def test_orphan_marker_surfaces_advisory_without_deleting_object(self):
        import drlink_v24 as v24

        root = tempfile.mkdtemp(prefix="drlink-hygiene-orphan-")
        plane = ControlPlane(root)
        try:
            v24.set_network_object(
                plane, "legacy-source", type="ip",
                value="198.51.100.24", oneshot=True,
            )
            plane.conn.execute(
                "UPDATE objects SET orphan_reason=? WHERE name=?",
                ("unresolved-reference", "legacy-source"),
            )
            plane.conn.commit()
            rev = plane.current_revision()
        finally:
            plane.close()

        with ManagementQueryService.open_read_only(root) as service:
            result = service.access_hygiene()
            attention = service.attention_summary()
        items = [i for i in result["items"] if i["kind"] == "orphan-object"]
        hygiene_attention = [
            item for item in attention["items"]
            if item["kind"] == "access-hygiene-review"
        ]
        self.assertEqual(len(hygiene_attention), 1)
        self.assertEqual(hygiene_attention[0]["count"], 1)
        self.assertEqual(hygiene_attention[0]["severity"], "warning")
        self.assertEqual(attention["signals"]["access_hygiene"]["action_required"], 1)
        self.assertEqual(result["items"][0]["kind"], "orphan-object")
        self.assertEqual(len(items), 1)
        finding = items[0]
        self.assertEqual(finding["label"], "legacy-source")
        self.assertEqual(finding["resource_type"], "object")
        self.assertEqual(finding["finding_status"], "ACTION_REQUIRED")
        self.assertEqual(finding["evidence_quality"], "OBSERVED")
        self.assertTrue(finding["evidence"]["orphan_reason_recorded"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["auto_mutation"])

        plane = ControlPlane(root)
        try:
            self.assertEqual(plane.current_revision(), rev)
            self.assertIsNotNone(plane.get_object("legacy-source"))
        finally:
            plane.close()

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
