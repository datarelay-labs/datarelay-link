#!/usr/bin/env python3
"""Auditor-only static guard: E2E operator procedure cannot weaken the contract."""
from pathlib import Path
from unittest import mock
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "docs" / "FULL_USER_E2E_SCENARIOS.md"
PROCEDURE = ROOT / "docs" / "E2E_EXECUTION_PROCEDURE.md"
ROADMAP = ROOT / "docs" / "E2E_LAB_READINESS_ROADMAP.md"


class E2EProcedureGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = CANONICAL.read_text(encoding="utf-8")
        cls.procedure = PROCEDURE.read_text(encoding="utf-8")
        cls.roadmap = ROADMAP.read_text(encoding="utf-8")

    def test_owner_assigned_dual_server_e2e_boundaries(self):
        for doc in (self.canonical, self.procedure, self.roadmap):
            self.assertIn("MCP_DNS_SERVER", doc)
            self.assertIn("FUNCTION_PERFORMANCE_SERVER", doc)
        for doc in (self.procedure, self.roadmap):
            self.assertIn("B014", doc)
        # Each check runs on exactly the owner-designated function or MCP/DNS Server.
        self.assertIn("MCP_DNS_SERVER — MCP and DNS/hostname tests only", self.canonical)
        self.assertIn("FUNCTION_PERFORMANCE_SERVER — every other test", self.canonical)
        self.assertIn("Mixed-scope scenarios", self.canonical)
        self.assertIn("only MCP and DNS/public-hostname tests", self.procedure)
        self.assertIn("every remaining", self.procedure)
        self.assertIn("MCP + DNS/public-hostname tests only", self.roadmap)
        self.assertIn("everything else", self.roadmap)
        self.assertIn("does not create a new VM-detection", self.canonical)
        self.assertIn("No new VM-kind", self.procedure)
        self.assertIn("not a new VM guest/snapshot/restore/host-provisioning prerequisite", self.roadmap)
        self.assertIn("single443", self.canonical)
        self.assertIn("116 scenarios", self.canonical)
        self.assertIn("60s/300s/3600s", self.procedure)
        # Concrete owner-private endpoint/SSH mapping belongs to the run inventory,
        # not to the public canonical test contract or generic lab procedure.
        for doc in (self.canonical, self.procedure, self.roadmap):
            self.assertNotIn("remote.xdr.ooo", doc)
            self.assertNotIn("221.139.249.113", doc)

    def test_disposable_test_host_authorization_and_pretest_cleanup(self):
        # Owner approval covers assigned test hosts, not unrelated machines.
        self.assertIn("Owner-authorized destructive TEST HOST scope", self.canonical)
        self.assertIn("disposable test host", self.canonical)
        self.assertIn("No new VM certification", self.canonical)
        self.assertIn("Mandatory execution order on each assigned test host", self.canonical)
        self.assertIn("Clean the prior test installation", self.canonical)
        self.assertIn("clean → install → test", self.canonical)
        self.assertIn("specific cleanup effect", self.canonical)
        self.assertIn("do not disguise, reroute or retry", self.canonical)
        self.assertIn("Owner's destructive test-host authorization", self.procedure)
        self.assertIn("disposable test machines", self.procedure)
        self.assertIn("Before the first product operation", self.procedure)
        self.assertIn("clean the prior E2E product/runtime state", self.procedure)
        self.assertIn("without waiting for extra owner approval", self.procedure)
        self.assertIn("Owner decision — every assigned test host may be destroyed", self.roadmap)
        self.assertIn("verify it is", self.roadmap)
        self.assertIn("never retry such an effect under an alternate executor", self.roadmap)
        protocol = (ROOT / "docs" / "CODEX_DUAL_ROLE_TEST_PROTOCOL.md").read_text()
        self.assertIn("disposable hosts", protocol)
        self.assertIn("B014", protocol)
        self.assertIn("denied", protocol)
        # All three portable documents must not leak the live private host map.
        for doc in (self.canonical, self.procedure, self.roadmap, protocol):
            self.assertNotIn("221.139.249.113", doc)
            self.assertNotIn("remote.xdr.ooo", doc)

    def test_canonical_points_to_owner_fix_first_procedure(self):
        self.assertIn("Owner-scoped test execution (2026-10-12)", self.canonical)
        self.assertIn("docs/E2E_EXECUTION_PROCEDURE.md", self.canonical)
        self.assertIn("ChatGPT", self.canonical)
        self.assertIn("this entire canonical document", self.canonical)
        self.assertIn("Never bypass a genuine security denial", self.canonical)

    def test_lab_readiness_is_diagnostic_not_a_separate_test_queue(self):
        self.assertIn("readiness is diagnostic", self.roadmap.lower())
        self.assertIn("F001 and F007 remain open", self.roadmap)
        self.assertIn("116 canonical IDs", self.roadmap)
        self.assertIn("two complete same-HEAD", self.roadmap)
        self.assertNotIn("starts this LAB-P0 readiness workstream first",
                         self.roadmap)
        self.assertNotIn("P0 owner-ordered prerequisite sequence", self.roadmap)
        self.assertIn("B014", self.roadmap)

    def test_procedure_retains_full_e2e_and_codex_test_only(self):
        required = (
            "FULL_USER_E2E_SCENARIOS.md",
            "116 scenario", "3,600-second soak",
            "two same-HEAD PASS", "Codex runs directly",
            "F001", "F004", "F005", "F006", "F007", "D001",
            "No new full E2E",
            "first AI answer", "AI_FIRST_ANSWERS.tsv",
            "PROCESS_REGISTRY.tsv", "CLEANROOM_LEDGER.tsv",
            "status",  # diagnostics and status reports remain explicit
            "MCP", "OAuth", "B014",
            "WARMUP=60s", "STEADY_STATE_EACH_CASE=300s", "SOAK=3600s",
            "NOT_READY", "PASS1=0/PASS2=0",
            "FRP",
            "No Cursor", "not a persona",
        )
        text = self.procedure
        absent = [p for p in required if p not in text]
        self.assertEqual(absent, [], absent)

    def test_e2e_start_is_not_blocked_by_project_paperwork(self):
        self.assertNotIn("Gate R1: all actionable", self.procedure)
        self.assertNotIn("Do not start a new full run while", self.procedure)
        self.assertNotIn("Approval matrix first", self.procedure)
        self.assertIn("continue independent", self.procedure.lower())
        self.assertIn("B014", self.procedure)
        self.assertIn("116 scenario", self.procedure)
        self.assertIn("two same-HEAD PASS", self.procedure)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Data Relay Link E2E fast path", agents)
        self.assertIn("packet-lint/work-admission tooling is diagnostic here", agents)

    def test_obsolete_fcs_actor_launcher_is_not_required(self):
        self.assertFalse((ROOT / "tools/codex_fcs_actor_dispatch.py").exists())
        for path in ("docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md",
                     "docs/E2E_EXECUTION_PROCEDURE.md"):
            self.assertNotIn("codex_fcs_actor_dispatch.py",
                             (ROOT / path).read_text(encoding="utf-8"))

    def test_protocol_uses_standard_review_not_old_global_veto(self):
        protocol = (ROOT / "docs" / "CODEX_DUAL_ROLE_TEST_PROTOCOL.md").read_text()
        self.assertIn("--approve-for-me", protocol)
        self.assertNotIn("replace placeholders only after owner approval", protocol)
        self.assertNotIn("Fail-closed sanity check already performed", protocol)

    def test_real_scenario_ledger_is_updated_during_the_run(self):
        # Progress must be observable; old procedure delayed the 116-row
        # ledger until the entire run, hiding two hours of genuine attempts.
        self.assertIn("update the existing scenario-results.tsv row immediately",
                      self.procedure)
        self.assertIn("never leave a finished scenario as NOT_RUN", self.procedure)
        self.assertIn("intermediate scenario-results.tsv", self.canonical)
        self.assertIn("do not claim PASS without verified evidence", self.canonical)
        protocol = (ROOT / "docs" / "CODEX_DUAL_ROLE_TEST_PROTOCOL.md").read_text()
        self.assertIn("write its scenario-results.tsv disposition promptly", protocol)
        self.assertIn("never use a checkpoint as final release PASS", protocol)

    def test_open_runtime_continuity_findings_are_not_prematurely_closed(self):
        decision = (ROOT / "docs" / "F001_F007_RUNTIME_CONTINUITY_REMEDIATION.md"
                    ).read_text(encoding="utf-8")
        self.assertIn("F001=PARTIALLY_MITIGATED", decision)
        self.assertIn("F007=PARTIALLY_MITIGATED_FOR_METADATA_ONLY", decision)
        self.assertIn("DOES NOT close F001 or F007", decision)
        self.assertIn("PASS1=0", decision)
        self.assertIn("PASS2=0", decision)
        self.assertIn("RELEASE=HOLD", decision)

    def test_both_documents_require_prospective_isolation_and_lifetime_evidence(self):
        for token in ("natural-language mission", "prospective", "server", "baseline"):
            self.assertIn(token.lower(), self.procedure.lower())
        self.assertIn("outside `/tmp`", self.procedure.replace("outside /tmp", "outside `/tmp`"))
        self.assertIn("artifacts", self.canonical.lower())
        self.assertIn("SOAK=3600s", self.canonical)
        self.assertIn("FULL_USER_E2E", self.canonical)



class CodexDualRoleEvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import validate_codex_dual_role_pairs as paircheck
        cls.validator = paircheck

    def _fixture(self, evidence_root):
        h = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
        pairs = []
        for n in range(1, 16):
            key = f"{n:03d}"
            for suffix in ("direct", "ai-first", "ai-user"):
                output = (
                    "fixture only; never E2E PASS" if suffix == "ai-first"
                    else f"Supporting fixture output for {key}:{suffix}. Never real user E2E.\n"
                )
                (evidence_root / f"{key}-{suffix}.txt").write_text(output)
            threads = {
                role: str(uuid.uuid5(uuid.NAMESPACE_DNS, "fixture-%s-%s" % (key, role)))
                for role in ("direct", "ai-operator", "ai-adviser")
            }
            event_paths = {}
            for role, thread in threads.items():
                path = evidence_root / ("%s-%s-events.jsonl" % (key, role))
                path.write_text(
                    "\n".join(json.dumps(event) for event in (
                        {"type": "thread.started", "thread_id": thread},
                        {"type": "turn.started"},
                        {"type": "item.completed",
                         "item": {"type": "agent_message",
                                  "text": "fixture only; never E2E PASS"}},
                        {"type": "turn.completed"},
                    )) + "\n"
                )
                event_paths[role] = path.name
            goal = h("Neutral first-time operator mission")
            baseline = h("Equivalent isolated demo source baseline")
            pairs.append({
                "PAIR_ID": "PAIR-" + key, "SCENARIO_ID": "FCS-" + key,
                "FEATURE_ID": "FEATURE-CLI" if n % 2 else "FEATURE-AI",
                "ROLE": "Operator",
                "AUDITOR_CODEX_THREAD": str(
                    uuid.uuid5(uuid.NAMESPACE_DNS, "fixture-auditor")),
                "DIRECT_CODEX_THREAD": threads["direct"],
                "AI_OPERATOR_CODEX_THREAD": threads["ai-operator"],
                "AI_ADVISER_CODEX_THREAD": threads["ai-adviser"],
                "DIRECT_GOAL_SHA256": goal, "AI_GOAL_SHA256": goal,
                "DIRECT_BASELINE_SHA256": baseline,
                "AI_BASELINE_SHA256": baseline,
                "DIRECT_SOURCE_HEAD": "a" * 40, "AI_SOURCE_HEAD": "a" * 40,
                "DIRECT_RESULT": "PASS", "AI_RESULT": "PASS",
                "FINAL_RESULT": "PASS",
                "DIRECT_EVIDENCE": key + "-direct.txt",
                "AI_FIRST_ANSWER_EVIDENCE": key + "-ai-first.txt",
                "AI_FIRST_ANSWER_SHA256": hashlib.sha256(
                    (evidence_root / (key + "-ai-first.txt")).read_bytes()
                ).hexdigest(),
                "AI_OPERATOR_EVIDENCE": key + "-ai-user.txt",
                "DIRECT_CODEX_EVENTS": event_paths["direct"],
                "AI_OPERATOR_CODEX_EVENTS": event_paths["ai-operator"],
                "AI_ADVISER_CODEX_EVENTS": event_paths["ai-adviser"],
                "BLOCK_REASON": "",
            })
        return pairs

    def _check(self, rows, root):
        return self.validator.evaluate(
            rows, evidence_root=root,
            expected_ids={f"FCS-{i:03d}" for i in range(1, 16)},
            expected_features={"FEATURE-CLI", "FEATURE-AI"},
            expected_head="a" * 40,
        )

    def test_unfinished_rows_preserve_canonical_dispositions_without_pass_metadata(self):
        statuses = {
            "NOT_RUN": "NOT_RUN", "NOT_RUN_BY_SCOPE": "NOT_RUN",
            "FAIL_PRECONDITION": "FAIL_PRECONDITION",
            "BLOCKED_MANAGEMENT_PATH": "BLOCKED",
            "BLOCKED_TOOLING_TTY": "BLOCKED",
            "BLOCKED_ENVIRONMENT": "BLOCKED", "BLOCKED_TOOLING": "BLOCKED",
            "INVALIDATED_BY_CONCURRENT_STATE": "INVALIDATED_BY_CONCURRENT_STATE",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = self._fixture(root)
            for status, bucket in statuses.items():
                with self.subTest(status=status):
                    rows = [dict(r) for r in good]
                    row = rows[0]
                    for key in self.validator.FIELDS:
                        if key not in ("PAIR_ID", "SCENARIO_ID", "FEATURE_ID"):
                            row[key] = ""
                    row.update(DIRECT_RESULT=status, AI_RESULT=status,
                               FINAL_RESULT=status, BLOCK_REASON="Observed prerequisite unavailable")
                    report = self._check(rows, root)
                    self.assertEqual(report["EVIDENCE_SCHEMA"], "PASS", report["ERRORS"])
                    self.assertEqual(report["PAIR_RESULTS"][bucket], 1)
                    self.assertEqual(report["PAIR_RESULTS"]["PARTIAL"], 0)
                    self.assertFalse(report["ALL_PAIRS_STRUCTURALLY_PASS"])
                    self.assertFalse(report["PRODUCT_E2E_PASS_PROVEN"])
                    row["DIRECT_SOURCE_HEAD"] = "b" * 40
                    row["AI_SOURCE_HEAD"] = "b" * 40
                    observed = self._check(rows, root)
                    self.assertEqual(observed["EVIDENCE_SCHEMA"], "PASS", observed["ERRORS"])
                    self.assertFalse(observed["ALL_PAIRS_STRUCTURALLY_PASS"])
                    row["FINAL_RESULT"] = "PASS"
                    self.assertEqual(self._check(rows, root)["EVIDENCE_SCHEMA"], "FAIL")
                    row["FINAL_RESULT"] = status
                    for key in ("DIRECT_GOAL_SHA256", "AI_BASELINE_SHA256"):
                        row[key] = "malformed"
                        self.assertEqual(self._check(rows, root)["EVIDENCE_SCHEMA"], "FAIL")
                        row[key] = ""
                    row["BLOCK_REASON"] = ""
                    self.assertEqual(self._check(rows, root)["EVIDENCE_SCHEMA"], "FAIL")

    def test_pending_mirror_does_not_erase_completed_lane_metadata_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            row = rows[0]
            row.update(AI_RESULT="NOT_RUN", FINAL_RESULT="PARTIAL",
                       BLOCK_REASON="AI mirror pending")
            for key in ("AI_GOAL_SHA256", "AI_BASELINE_SHA256", "AI_SOURCE_HEAD"):
                row[key] = ""
            self.assertEqual(self._check(rows, root)["EVIDENCE_SCHEMA"], "PASS")
            row["DIRECT_SOURCE_HEAD"] = ""
            self.assertEqual(self._check(rows, root)["EVIDENCE_SCHEMA"], "FAIL")
            row["DIRECT_SOURCE_HEAD"] = "a" * 40
            row["AI_SOURCE_HEAD"] = "b" * 40
            self.assertEqual(self._check(rows, root)["EVIDENCE_SCHEMA"], "PASS")
            row["AI_SOURCE_HEAD"] = "malformed"
            self.assertEqual(self._check(rows, root)["EVIDENCE_SCHEMA"], "FAIL")

    def test_codex_direct_and_ai_same_scenario_fixture_structure_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self._check(self._fixture(root), root)
            self.assertEqual(result["EVIDENCE_SCHEMA"], "PASS", result["ERRORS"])
            self.assertEqual(result["SCENARIO_COVERAGE"], 15)
            self.assertEqual(result["FEATURE_COVERAGE"], 2)
            self.assertTrue(result["ALL_PAIRS_STRUCTURALLY_PASS"])
            # A valid synthetic ledger is NOT evidence of a genuine Codex E2E.
            self.assertFalse(result["ACTUAL_CODEX_ROLE_EXECUTION_VERIFIED"])
            self.assertFalse(result["PRODUCT_E2E_PASS_PROVEN"])

    def test_codex_missing_ai_or_inherited_thread_cannot_claim_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = self._fixture(root)
            for key, value in (
                ("AI_RESULT", "NOT_RUN"),
                ("AI_ADVISER_CODEX_THREAD", good[0]["DIRECT_CODEX_THREAD"]),
                ("AI_GOAL_SHA256", "b" * 64),
                ("AI_BASELINE_SHA256", "b" * 64),
                ("AI_SOURCE_HEAD", "b" * 40),
                ("AI_FIRST_ANSWER_SHA256", "b" * 64),
                ("AI_FIRST_ANSWER_EVIDENCE", "../not-a-public-actor.txt"),
            ):
                with self.subTest(key=key):
                    rows = [dict(r) for r in good]
                    rows[0][key] = value
                    result = self._check(rows, root)
                    self.assertEqual(result["EVIDENCE_SCHEMA"], "FAIL", key)
                    self.assertFalse(result["ALL_PAIRS_STRUCTURALLY_PASS"])

    def test_cli_validator_rejects_fabricated_ai_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            pairs = root / "pairs.tsv"
            features = root / "features.tsv"
            with features.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["FEATURE_ID", "SUPPORTED"],
                                        delimiter="\t")
                writer.writeheader()
                writer.writerow({"FEATURE_ID": "FEATURE-CLI", "SUPPORTED": "YES"})
                writer.writerow({"FEATURE_ID": "FEATURE-AI", "SUPPORTED": "YES"})
            def invoke():
                with pairs.open("w", newline="") as f:
                    writer = csv.DictWriter(
                        f, fieldnames=self.validator.FIELDS, delimiter="\t")
                    writer.writeheader()
                    writer.writerows(rows)
                return subprocess.run([
                    sys.executable, str(ROOT / "tools" /
                                        "validate_codex_dual_role_pairs.py"),
                    "--mode", "fcs", "--pairs", str(pairs),
                    "--evidence-root", str(root),
                    "--feature-inventory", str(features),
                    "--expected-head", "a" * 40,
                ], capture_output=True, text=True, timeout=8)
            positive = invoke()
            self.assertEqual(positive.returncode, 0, positive.stderr)
            result = json.loads(positive.stdout)
            self.assertTrue(result["ALL_PAIRS_STRUCTURALLY_PASS"])
            self.assertFalse(result["PRODUCT_E2E_PASS_PROVEN"])
            rows[0]["AI_RESULT"] = "NOT_RUN"
            false_pass = invoke()
            self.assertEqual(false_pass.returncode, 2)
            self.assertIn("FINAL PASS requires both", false_pass.stdout)

    def test_long_lived_independent_roles_can_cover_multiple_scenarios(self):
        """One honest User and one AI User can continue across scenarios."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            for row in rows[1:]:
                for role, thread_key, event_key in (
                    ("direct", "DIRECT_CODEX_THREAD", "DIRECT_CODEX_EVENTS"),
                    ("ai-operator", "AI_OPERATOR_CODEX_THREAD", "AI_OPERATOR_CODEX_EVENTS"),
                    ("ai-adviser", "AI_ADVISER_CODEX_THREAD", "AI_ADVISER_CODEX_EVENTS"),
                ):
                    shared_thread = rows[0][thread_key]
                    row[thread_key] = shared_thread
                    event_file = root / row[event_key]
                    events = [json.loads(line) for line in event_file.read_text().splitlines()]
                    events[0]["thread_id"] = shared_thread
                    event_file.write_text(
                        chr(10).join(json.dumps(event) for event in events) + chr(10)
                    )
            report = self._check(rows, root)
            self.assertEqual(report["EVIDENCE_SCHEMA"], "PASS", report["ERRORS"])
            self.assertFalse(report["PRODUCT_E2E_PASS_PROVEN"])

    def test_reused_role_must_not_reuse_another_scenarios_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            rows[1]["DIRECT_CODEX_THREAD"] = rows[0]["DIRECT_CODEX_THREAD"]
            rows[1]["DIRECT_CODEX_EVENTS"] = rows[0]["DIRECT_CODEX_EVENTS"]
            result = self._check(rows, root)
            self.assertEqual(result["EVIDENCE_SCHEMA"], "FAIL")
            self.assertIn("actor event log reused", " | ".join(result["ERRORS"]))

    def test_role_context_cannot_change_from_direct_to_ai(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            rows[1]["AI_OPERATOR_CODEX_THREAD"] = rows[0]["DIRECT_CODEX_THREAD"]
            path = root / rows[1]["AI_OPERATOR_CODEX_EVENTS"]
            events = [json.loads(line) for line in path.read_text().splitlines()]
            events[0]["thread_id"] = rows[0]["DIRECT_CODEX_THREAD"]
            path.write_text(chr(10).join(json.dumps(e) for e in events) + chr(10))
            report = self._check(rows, root)
            self.assertEqual(report["EVIDENCE_SCHEMA"], "FAIL")
            self.assertIn("actor thread changed role", " | ".join(report["ERRORS"]))

    def test_bad_raw_codex_thread_receipts_are_not_counted_as_actors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = self._fixture(root)
            cases = (
                ("missing-final-turn", None),
                ("wrong-thread-start", None),
                ("ai-adviser-command-execution", None),
                ("ai-adviser-file-change", None),
            )
            for issue, _ in cases:
                with self.subTest(issue=issue):
                    rows = [dict(r) for r in good]
                    filename = root / rows[0]["AI_ADVISER_CODEX_EVENTS"]
                    original = filename.read_text()
                    try:
                        events = [json.loads(line) for line in original.splitlines()]
                        if issue == "missing-final-turn":
                            events = events[:-1]
                        elif issue == "wrong-thread-start":
                            events[0]["thread_id"] = str(uuid.uuid4())
                        elif issue == "ai-adviser-command-execution":
                            events.insert(-1, {"type": "item.started",
                                               "item": {"type": "command_execution",
                                                        "command": "cat source.py"}})
                        elif issue == "ai-adviser-file-change":
                            events.insert(-1, {"type": "item.started",
                                               "item": {"type": "file_change"}})
                        filename.write_text(
                            "\n".join(json.dumps(x) for x in events) + "\n"
                        )
                        result = self._check(rows, root)
                        self.assertEqual(result["EVIDENCE_SCHEMA"], "FAIL", issue)
                        self.assertFalse(result["ALL_PAIRS_STRUCTURALLY_PASS"])
                    finally:
                        filename.write_text(original)

    def test_first_ai_answer_must_equal_original_codex_message_not_self_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            first = root / rows[0]["AI_FIRST_ANSWER_EVIDENCE"]
            fake = "FAKE_AI_ANSWER_THE_MODEL_NEVER_RETURNED"
            first.write_text(fake)
            rows[0]["AI_FIRST_ANSWER_SHA256"] = hashlib.sha256(
                fake.encode("utf-8")
            ).hexdigest()
            report = self._check(rows, root)
            self.assertEqual(report["EVIDENCE_SCHEMA"], "FAIL")
            self.assertIn(
                "first AI answer differs from original Codex",
                " | ".join(report["ERRORS"]),
            )

    def test_unknown_ai_adviser_tool_type_is_rejected_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            path = root / rows[0]["AI_ADVISER_CODEX_EVENTS"]
            events = [json.loads(line) for line in path.read_text().splitlines()]
            events.insert(-1, {
                "type": "item.started",
                "item": {"type": "new_future_tool_not_in_blacklist"},
            })
            path.write_text("\n".join(json.dumps(x) for x in events) + "\n")
            report = self._check(rows, root)
            self.assertEqual(report["EVIDENCE_SCHEMA"], "FAIL")
            self.assertIn("Codex AI Adviser used tools", " | ".join(report["ERRORS"]))

    def test_no_missing_fcs_or_feature_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            dropped = [r for r in rows if r["SCENARIO_ID"] != "FCS-015"]
            report = self._check(dropped, root)
            self.assertIn("missing scenario FCS-015", report["ERRORS"])
            dropped = [r for r in rows if r["FEATURE_ID"] == "FEATURE-CLI"]
            report = self._check(dropped, root)
            self.assertIn("missing feature FEATURE-AI", report["ERRORS"])

    def test_canonical_documents_select_codex_both_roles_and_do_not_run_yet(self):
        fcs = (ROOT / "docs" / "CLI_FEATURE_SCENARIO_RECONCILIATION.md"
               ).read_text(encoding="utf-8")
        full = CANONICAL.read_text(encoding="utf-8")
        plan = (ROOT / "docs" / "CODEX_DUAL_ROLE_TEST_PROTOCOL.md"
                ).read_text(encoding="utf-8")
        for text in (fcs, full, plan):
            self.assertIn("CODEX", text.upper())
        self.assertIn("docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md", fcs)
        self.assertIn("docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md", full)
        self.assertIn("ISSUE_165_PRIMARY_PERSONA_EXECUTOR=CODEX", fcs)
        self.assertIn("AI-assisted user role for the SAME feature", fcs)
        self.assertIn("same business goal", plan)
        self.assertIn("different fresh", plan.lower())
        self.assertIn("LAB_GO", plan)
        self.assertIn("NON-DESTRUCTIVE", plan)


class Canonical116E2EInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import generate_full_user_e2e_inventory as generator
        cls.generator = generator
        cls.source = CANONICAL.read_text(encoding="utf-8")

    def test_original_116_scenarios_preserved_without_duplicate_subheadings(self):
        rows = self.generator.parse_scenarios(self.source)
        self.assertEqual(len(rows), 116)
        self.assertEqual(rows[0]["SCENARIO_ID"], "U-001")
        self.assertEqual(rows[-1]["SCENARIO_ID"], "X-010")
        self.assertEqual(len({row["SCENARIO_ID"] for row in rows}), 116)
        self.assertEqual(sum(row["SCENARIO_ID"] == "U-006" for row in rows), 1)
        counts = {key: sum(row["ROLE_GROUP"] == key for row in rows)
                  for key in self.generator.EXPECTED_COUNTS}
        self.assertEqual(counts, self.generator.EXPECTED_COUNTS)
        self.assertIn("MANDATORY", rows[0]["HEADING"])
        self.assertIn("CONDITIONAL", rows[-1]["HEADING"])

    def test_canonical_missing_or_duplicate_scenario_cannot_be_qualified(self):
        original = self.source
        self.assertIn("## U-001 —", original)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.generator.parse_scenarios(original.replace(
                "## U-001 —", "## U-002 —", 1
            ))
        with self.assertRaisesRegex(ValueError, "exactly 116"):
            self.generator.parse_scenarios(original.replace(
                "## U-001 —", "### U-001 —", 1
            ))

    def test_persistent_run_inventory_is_once_only_and_not_a_user_pass(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory) / "owned-run"
            root.mkdir(mode=0o700)
            out = self.generator.write_inventory(
                root=root, content=self.source, repo_head="a" * 40,
            )
            with out.open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 116)
            manifest = json.loads(
                (out.parent / "scenario-inventory-source.json").read_text()
            )
            self.assertFalse(manifest["actual_codex_persona_test_completed"])
            self.assertIn("NOT_ACTUAL_E2E", manifest["evidence_kind"])
            self.assertEqual(manifest["scenario_count"], 116)
            self.assertEqual(out.stat().st_mode & 0o077, 0)
            with self.assertRaises(FileExistsError):
                self.generator.write_inventory(
                    root=root, content=self.source, repo_head="a" * 40,
                )


if __name__ == "__main__":
    unittest.main()
