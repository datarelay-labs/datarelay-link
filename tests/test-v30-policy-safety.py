from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_v24 as v24
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_core import (
    ManagementActor,
    ManagementAuthorizationError,
    ManagementCoreService,
)
from drlink_management_guided import GuidedChangeService
from drlink_policy_safety import (
    MAX_GRAPH_PATHS,
    PolicySafetyService,
    diff_effective_access_graphs,
)


class V30PolicySafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-policy-safety-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        plane = ControlPlane(self.tmp)
        try:
            v24.ensure_v2_schema(plane.conn)
            v24.set_network_object(
                plane, "src", type="ip", value="198.51.100.10", oneshot=True
            )
            v24.set_network_object(
                plane, "dst", type="ip", value="198.51.100.20", oneshot=True
            )
            v24.set_service_object(
                plane, "ssh", type="tcp", port=22, oneshot=True
            )
            v24.set_access_rule(
                plane,
                "remote",
                "allow-ssh",
                mode="whitelist",
                source="src",
                destination="dst",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
        finally:
            plane.close()

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_SKIP_ACTIVATION", None)

    @staticmethod
    def _admin():
        return ManagementActor.authenticated(
            "web:admin",
            {
                "management-read",
                "management-policy-test",
                "management-config",
            },
            role="Admin",
        )

    @staticmethod
    def _reader():
        return ManagementActor.authenticated(
            "web:reader",
            {"management-read", "management-policy-test"},
            role="Read Only",
        )

    def _definition(self, **overrides):
        value = {
            "name": "critical-ssh",
            "plane": "remote",
            "source": "src",
            "destination": "dst",
            "service": "ssh",
            "expected": "ALLOW",
            "required": True,
            "enabled": True,
        }
        value.update(overrides)
        return value

    def test_decision_trace_reuses_canonical_evaluator(self):
        with PolicySafetyService(self.tmp) as service:
            trace = service.decision_trace(
                plane="remote",
                source="src",
                destination="dst",
                service="ssh",
            )
        self.assertEqual(trace["final"]["result"], "ALLOW")
        self.assertEqual(trace["policy"]["mode"], "whitelist")
        self.assertIn("allow-ssh", trace["policy"]["matched_rules"])
        self.assertEqual(trace["normalized_input"]["source"], "src")
        self.assertEqual(trace["normalized_input"]["destination"], "dst")
        self.assertIn("reason", trace["final"])

    def test_effective_access_graph_is_query_only_bounded_and_matches_core_decision(self):
        plane = ControlPlane(self.tmp)
        try:
            before_revision = plane.current_revision()
            before_meta = int(
                plane.conn.execute("SELECT COUNT(*) FROM system_meta").fetchone()[0]
            )
        finally:
            plane.close()

        with PolicySafetyService.open_read_only(self.tmp) as service:
            graph = service.effective_access_graph(planes=["remote"])
        self.assertEqual(graph["scope"], "policy-and-inventory")
        self.assertFalse(graph["network_topology"])
        self.assertLessEqual(graph["limits"]["host_count"], 100)
        self.assertFalse(graph["limits"]["truncated"])
        self.assertTrue(
            any(
                item["kind"] == "policy-rule" and item.get("rule") == "allow-ssh"
                for item in graph["nodes"]
            )
        )
        flow = next(
            item
            for item in graph["paths"]
            if item["input"] == {
                "plane": "remote",
                "source": "src",
                "destination": "dst",
                "service": "ssh",
            }
        )
        self.assertEqual(flow["decision"], "ALLOW")
        self.assertEqual(flow["status"], "computed")
        self.assertIn("allow-ssh", flow["rules"])

        core = ManagementCoreService(self.tmp)
        via_core = core.policy_effective_access_graph(
            actor=self._reader(),
            plane="remote",
        )
        self.assertEqual(via_core["paths"][0]["decision"], "ALLOW")
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before_revision)
            self.assertEqual(
                int(plane.conn.execute("SELECT COUNT(*) FROM system_meta").fetchone()[0]),
                before_meta,
            )
        finally:
            plane.close()

    def test_blast_radius_reports_bounded_truncation_metadata(self):
        count = MAX_GRAPH_PATHS + 1
        current_paths = []
        proposed_paths = []
        for index in range(count):
            key = "remote|src-%s|dst|ssh|" % index
            flow = {
                "plane": "remote",
                "source": "src-%s" % index,
                "destination": "dst",
                "service": "ssh",
            }
            current_paths.append(
                {
                    "key": key,
                    "input": flow,
                    "decision": "DENY",
                    "status": "computed",
                    "rules": ["rule-%s" % index],
                }
            )
            proposed_paths.append(
                {
                    "key": key,
                    "input": flow,
                    "decision": "ALLOW",
                    "status": "computed",
                    "rules": ["rule-%s" % index],
                }
            )
        blast = diff_effective_access_graphs(
            {
                "paths": current_paths,
                "edges": [],
                "nodes": [],
                "unknowns": [],
                "limits": {"truncated": False},
            },
            {
                "paths": proposed_paths,
                "edges": [],
                "nodes": [],
                "unknowns": [],
                "limits": {"truncated": False},
            },
        )
        self.assertEqual(len(blast["decision_changes"]), MAX_GRAPH_PATHS)
        self.assertEqual(blast["limits"]["decision_changes_total"], count)
        self.assertEqual(blast["limits"]["newly_reachable_total"], count)
        self.assertTrue(blast["limits"]["truncated"])
        self.assertIn("decision_changes", blast["limits"]["truncated_by"])
        self.assertIn("newly_reachable", blast["limits"]["truncated_by"])

    def test_saved_test_preview_apply_run_and_delete_are_revision_bound(self):
        with PolicySafetyService(self.tmp) as service:
            before = service.plane.current_revision()
            preview = service.preview_definition(
                actor_id="web:admin",
                operation="set",
                definition=self._definition(),
            )
            self.assertEqual(preview["confirmation_class"], "APPLY")
            self.assertTrue(preview["preview"]["assertion_ok"])
            self.assertEqual(service.plane.current_revision(), before)
            self.assertEqual(service.list_tests()["count"], 0)

            with self.assertRaisesRegex(ControlPlaneError, "APPLY"):
                service.apply_definition(
                    actor_id="web:admin",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="SAVE",
                )
            self.assertEqual(service.plane.current_revision(), before)

            applied = service.apply_definition(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
            self.assertEqual(applied["revision"], before + 1)
            listed = service.list_tests()
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["items"][0]["name"], "critical-ssh")
            run = service.run_tests(required_only=True)
            self.assertTrue(run["ok"])
            self.assertEqual(run["passed"], 1)
            self.assertEqual(run["required_failed"], 0)

            revision = service.plane.conn.execute(
                "SELECT actor FROM config_revisions WHERE revision=?",
                (before + 1,),
            ).fetchone()
            self.assertEqual(revision["actor"], "web:admin")
            audit = service.plane.conn.execute(
                "SELECT actor_id,interface,entity_type FROM audit_events "
                "WHERE revision=? ORDER BY id DESC LIMIT 1",
                (before + 1,),
            ).fetchone()
            self.assertEqual(audit["actor_id"], "web:admin")
            self.assertEqual(audit["interface"], "WEB")
            self.assertEqual(audit["entity_type"], "policy-regression-test")

            delete_preview = service.preview_definition(
                actor_id="web:admin",
                operation="delete",
                definition={"name": "critical-ssh"},
            )
            self.assertEqual(delete_preview["confirmation_class"], "DELETE TEST")
            with self.assertRaisesRegex(ControlPlaneError, "DELETE TEST"):
                service.apply_definition(
                    actor_id="web:admin",
                    change_plan_id=delete_preview["change_plan_id"],
                    confirmation="APPLY",
                )
            deleted = service.apply_definition(
                actor_id="web:admin",
                change_plan_id=delete_preview["change_plan_id"],
                confirmation="DELETE TEST",
            )
            self.assertEqual(deleted["status"], "APPLIED")
            self.assertEqual(service.list_tests()["count"], 0)

    def test_required_saved_test_reports_failure_without_mutation(self):
        with PolicySafetyService(self.tmp) as service:
            preview = service.preview_definition(
                actor_id="web:admin",
                operation="set",
                definition=self._definition(expected="DENY"),
            )
            self.assertFalse(preview["preview"]["assertion_ok"])
            service.apply_definition(
                actor_id="web:admin",
                change_plan_id=preview["change_plan_id"],
                confirmation="APPLY",
            )
            before = service.plane.current_revision()
            result = service.run_tests(required_only=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["required_failed"], 1)
            self.assertEqual(result["items"][0]["got"], "ALLOW")
            self.assertEqual(service.plane.current_revision(), before)

    def test_required_saved_test_blocks_security_relevant_guided_apply(self):
        with PolicySafetyService(self.tmp) as safety:
            saved = safety.preview_definition(
                actor_id="web:admin",
                operation="set",
                definition=self._definition(),
            )
            safety.apply_definition(
                actor_id="web:admin",
                change_plan_id=saved["change_plan_id"],
                confirmation="APPLY",
            )

        with GuidedChangeService(self.tmp) as guided:
            before = guided.plane.current_revision()
            preview = guided.preview_guided_change(
                actor_id="web:admin",
                change_type="remote-access-rule",
                payload={
                    "operation": "set",
                    "name": "allow-ssh",
                    "enabled": False,
                },
            )
            regression = preview["policy_regression"]
            self.assertIsNotNone(regression)
            self.assertFalse(regression["ok"])
            self.assertEqual(regression["required_failed"], 1)
            self.assertEqual(
                preview["impact"]["required_policy_test_failures"], 1
            )
            with self.assertRaisesRegex(
                ControlPlaneError, "Required Policy Regression Tests failed"
            ):
                guided.apply_guided_change(
                    actor_id="web:admin",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
            self.assertEqual(guided.plane.current_revision(), before)
            row = guided.plane._get_rule("remote", "allow-ssh")
            self.assertTrue(bool(row["enabled"]))

    def test_stale_saved_test_change_plan_fails_closed(self):
        with PolicySafetyService(self.tmp) as service:
            preview = service.preview_definition(
                actor_id="web:admin",
                operation="set",
                definition=self._definition(),
            )
        plane = ControlPlane(self.tmp)
        try:
            v24.set_network_object(
                plane,
                "other",
                type="ip",
                value="198.51.100.30",
                oneshot=True,
            )
        finally:
            plane.close()

        with PolicySafetyService(self.tmp) as service:
            with self.assertRaises(ConcurrencyError):
                service.apply_definition(
                    actor_id="web:admin",
                    change_plan_id=preview["change_plan_id"],
                    confirmation="APPLY",
                )
            self.assertEqual(service.list_tests()["count"], 0)

    def test_core_permissions_keep_read_and_mutation_separate(self):
        plane = ControlPlane(self.tmp)
        try:
            before_revision = plane.current_revision()
            before_meta = int(
                plane.conn.execute("SELECT COUNT(*) FROM system_meta").fetchone()[0]
            )
        finally:
            plane.close()

        core = ManagementCoreService(self.tmp)
        trace = core.policy_decision_trace(
            actor=self._reader(),
            plane="remote",
            source="src",
            destination="dst",
            service="ssh",
        )
        self.assertEqual(trace["final"]["result"], "ALLOW")
        self.assertEqual(core.policy_regression_list(actor=self._reader())["count"], 0)
        self.assertTrue(core.policy_regression_run(actor=self._reader())["ok"])
        plane = ControlPlane(self.tmp)
        try:
            self.assertEqual(plane.current_revision(), before_revision)
            meta_count = int(
                plane.conn.execute("SELECT COUNT(*) FROM system_meta").fetchone()[0]
            )
            self.assertEqual(meta_count, before_meta)
        finally:
            plane.close()
        with self.assertRaises(ManagementAuthorizationError):
            core.policy_regression_preview(
                actor=self._reader(),
                operation="set",
                definition=self._definition(),
            )

        preview = core.policy_regression_preview(
            actor=self._admin(),
            operation="set",
            definition=self._definition(),
        )
        self.assertEqual(preview["confirmation_class"], "APPLY")


if __name__ == "__main__":
    unittest.main()
