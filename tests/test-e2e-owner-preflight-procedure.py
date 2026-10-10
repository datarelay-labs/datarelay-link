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

    def test_canonical_points_to_owner_fix_first_procedure(self):
        self.assertIn("Current owner-ordered preparation gate", self.canonical)
        self.assertIn("docs/E2E_EXECUTION_PROCEDURE.md", self.canonical)
        self.assertIn("ChatGPT", self.canonical)
        self.assertIn("this entire canonical document", self.canonical)
        self.assertIn("previously denied security effects remain binding", self.canonical)

    def test_roadmap_priority_first_bugs_then_method_then_clean_lab(self):
        bug = self.roadmap.index("Immediate first:")
        sop = self.roadmap.index("**Next:** CHATGPT_CHAT repairs the method")
        lab = self.roadmap.index("**Only after those two gates:**")
        self.assertLess(bug, sop)
        self.assertLess(sop, lab)
        self.assertLess(lab, self.roadmap.index("### LAB-P0-01"))
        self.assertIn("F001 and F007 remain open", self.roadmap)

    def test_procedure_retains_full_e2e_and_codex_test_only(self):
        required = (
            "FULL_USER_E2E_SCENARIOS.md",
            "116 scenario", "3,600-second soak",
            "two same-HEAD PASS", "Codex TEST-ONLY",
            "F001", "F004", "F005", "F006", "F007", "D001",
            "No new full E2E", "15-FCS audit",
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
                (evidence_root / f"{key}-{suffix}.txt").write_text(
                    f"Supporting fixture output for {key}:{suffix}. Never real user E2E.\n"
                )
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

    def test_new_codex_threads_must_not_be_reused_across_pairs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = self._fixture(root)
            rows[1]["DIRECT_CODEX_THREAD"] = rows[0]["DIRECT_CODEX_THREAD"]
            path = root / rows[1]["DIRECT_CODEX_EVENTS"]
            event_log = [json.loads(line) for line in path.read_text().splitlines()]
            event_log[0]["thread_id"] = rows[0]["DIRECT_CODEX_THREAD"]
            path.write_text("\n".join(json.dumps(x) for x in event_log) + "\n")
            result = self._check(rows, root)
            self.assertIn("Codex actor thread reused across pairs",
                          " | ".join(result["ERRORS"]))
            self.assertEqual(result["EVIDENCE_SCHEMA"], "FAIL")

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
        self.assertIn("NOT_READY", plan)
        self.assertIn("TEST ONLY", plan)


class CodexActorDispatchSafeguards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import codex_fcs_actor_dispatch as dispatcher
        cls.dispatch = dispatcher

    def fixture(self, root: Path):
        base = root / "FCS-001-run"
        base.mkdir(mode=0o700)
        prompt = base / "ai-adviser-first-prompt.txt"
        prompt.write_text(
            "I am a new operator. My task is to discover the version. "
            "This is a fixed synthetic fixture without any credential."
        )
        prompt.chmod(0o600)
        lab = base / "PREFLIGHT_STATUS.json"
        status = {
            "status": "GO", "not_ready_gate_ids": [],
            "lab_phase": "INSTALLED_CANDIDATE",
            "repo_head": "a" * 40,
            "candidate_source_head": "b" * 40,
        }
        lab.write_text(json.dumps(status))
        lock = base / ".cli-feature-scenario.lock"
        lock.write_text("RUN_ID=FCS-001-run\n")
        owner = base / "owner-phase-state.json"
        owner.write_text(json.dumps({
            "phase": "CODEX_CLI_FEATURE_SCENARIO_ONLY",
            "next_codex_test_authorized": True, "p0_go_status": "GO",
            "latest_source_head": "a" * 40,
        }))
        return base, prompt, lab, lock, status

    def test_qualified_receipt_preflight_allows_plan_but_does_not_launch_model(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as temp:
            root, prompt, lab, lock, _ = self.fixture(Path(temp))
            with mock.patch.object(
                self.dispatch.subprocess, "check_output",
                return_value="a" * 40 + "\n",
            ), mock.patch.object(
                self.dispatch, "OWNER_PHASE_STATE", root / "owner-phase-state.json"
            ):
                ready = self.dispatch.validate_launch(
                    run_root=root, run_id="FCS-001-run", pair_id="PAIR-001",
                    role="AI_ADVISER", prompt_file=prompt,
                    preflight_file=lab, lock_file=lock,
                )
            self.assertEqual(ready["source_head"], "b" * 40)
            self.assertEqual(ready["repo_head"], "a" * 40)
            self.assertEqual(ready["role"], "AI_ADVISER")
            self.assertFalse(ready["target"].exists())

    def test_blockers_prevent_any_model_launch(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as temp:
            root, prompt, lab, lock, receipt = self.fixture(Path(temp))
            blocked = dict(receipt, status="NOT_READY",
                           not_ready_gate_ids=["SERVER_CLEANUP_B014"])
            lab.write_text(json.dumps(blocked))
            with mock.patch.object(
                self.dispatch.subprocess, "check_output",
                return_value="a" * 40 + "\n",
            ), mock.patch.object(
                self.dispatch.shutil, "which",
                side_effect=AssertionError("Codex binary lookup not allowed"),
            ), mock.patch.object(
                sys, "argv", [
                    "codex_fcs_actor_dispatch.py", "--run-root", str(root),
                    "--run-id", "FCS-001-run", "--pair-id", "PAIR-001",
                    "--role", "AI_ADVISER", "--prompt-file", str(prompt),
                    "--preflight", str(lab), "--lock", str(lock),
                ],
            ):
                self.assertEqual(self.dispatch.main(), 3)
            self.assertFalse((root / "actors").exists())

    def test_lock_head_permission_and_duplicate_gates(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as temp:
            root, prompt, lab, lock, receipt = self.fixture(Path(temp))
            args = dict(run_root=root, run_id="FCS-001-run",
                        pair_id="PAIR-001", role="DIRECT_USER",
                        prompt_file=prompt, preflight_file=lab,
                        lock_file=lock)
            with mock.patch.object(self.dispatch.subprocess, "check_output",
                                   return_value="a" * 40 + "\n"), \
                 mock.patch.object(
                     self.dispatch, "OWNER_PHASE_STATE",
                     root / "owner-phase-state.json",
                 ):
                self.assertEqual(self.dispatch.validate_launch(**args)["role"],
                                 "DIRECT_USER")
                lock.write_text("RUN_ID=FOREIGN-RUN\n")
                with self.assertRaisesRegex(ValueError, "lock is not owned"):
                    self.dispatch.validate_launch(**args)
                lock.write_text("RUN_ID=FCS-001-run\n")
                receipt["repo_head"] = "c" * 40
                lab.write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "repo HEAD"):
                    self.dispatch.validate_launch(**args)
                receipt["repo_head"] = "a" * 40
                lab.write_text(json.dumps(receipt))
                prompt.chmod(0o644)
                with self.assertRaisesRegex(ValueError, "not private"):
                    self.dispatch.validate_launch(**args)
                prompt.chmod(0o600)
                (root / "actors" / "PAIR-001" / "DIRECT_USER"
                 ).mkdir(parents=True)
                with self.assertRaises(FileExistsError):
                    self.dispatch.validate_launch(**args)

    def test_go_receipt_cannot_override_owner_denied_phase(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as temp:
            root, prompt, lab, lock, receipt = self.fixture(Path(temp))
            owner = root / "owner-phase-state.json"
            owner.write_text(json.dumps({
                "phase": "CHATGPT_CODEX_E2E_FINDINGS_FIX_AND_SOP",
                "next_codex_test_authorized": False,
                "p0_go_status": "NOT_READY",
                "latest_source_head": "a" * 40,
            }))
            with mock.patch.object(
                self.dispatch.subprocess, "check_output",
                return_value="a" * 40 + "\n",
            ), mock.patch.object(
                self.dispatch, "OWNER_PHASE_STATE", owner
            ):
                with self.assertRaisesRegex(ValueError, "not enabled"):
                    self.dispatch.validate_launch(
                        run_root=root, run_id="FCS-001-run",
                        pair_id="PAIR-001", role="AI_ADVISER",
                        prompt_file=prompt, preflight_file=lab,
                        lock_file=lock,
                    )

    def test_actor_log_from_real_codex_jsonl_shape_is_audit_only(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as temp:
            root = Path(temp)
            events = root / "events.jsonl"
            thread_id = str(uuid.uuid4())
            base = [
                {"type": "thread.started", "thread_id": thread_id},
                {"type": "turn.started"},
                {"type": "item.completed", "item": {
                    "type": "agent_message", "text": "fixture only"}},
                {"type": "turn.completed"},
            ]
            events.write_text("\n".join(json.dumps(x) for x in base) + "\n")
            a = self.dispatch.extract_receipt(events, "AI_ADVISER")
            self.assertEqual(a["status"], "STRUCTURAL_PASS")
            self.assertEqual(a["thread_id"], thread_id)
            base.insert(-1, {"type": "item.started",
                             "item": {"type": "mcp_tool_call", "name": "search"}})
            events.write_text("\n".join(json.dumps(x) for x in base) + "\n")
            bad = self.dispatch.extract_receipt(events, "AI_ADVISER")
            self.assertEqual(bad["status"], "STRUCTURAL_FAIL")
            self.assertIn("mcp_tool_call", bad["forbidden_ai_tool_types"])


if __name__ == "__main__":
    unittest.main()
