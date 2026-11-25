#!/usr/bin/env python3
"""CLI-only E2E scope and evidence regressions, separate from Full User E2E."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import unittest
import concurrent.futures
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "tools/cli_only_e2e_inventory.py"
CANONICAL = ROOT / "docs/FULL_USER_E2E_SCENARIOS.md"
POLICY = ROOT / "docs/CLI_ONLY_E2E_SCENARIOS.md"


def load():
    spec = importlib.util.spec_from_file_location("cli_only_e2e_inventory", GEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CLIE2EContractTest(unittest.TestCase):
    def test_116_ids_and_exclusion_only_explicit_ai_mcp(self):
        m = load()
        items = m.scopes(CANONICAL.read_text())
        self.assertEqual(len(items), 116)
        self.assertEqual(len({r["SCENARIO_ID"] for r in items}), 116)
        self.assertEqual(sum(x["SCOPE"] == "EXCLUDED_AI_MCP" for x in items), 16)
        self.assertEqual(sum(x["SCOPE"] != "EXCLUDED_AI_MCP" for x in items), 100)
        mapped = {r["SCENARIO_ID"]: r for r in items}
        for required in ("U-001", "U-002", "U-006", "O-001", "O-002",
                         "O-009", "O-011", "A-015", "S-015", "S-017",
                         "C-001", "C-004", "C-015", "P-002", "P-013",
                         "P-019", "P-023", "P-024"):
            self.assertNotEqual(mapped[required]["SCOPE"], "EXCLUDED_AI_MCP")
        for excluded in ("U-007", "U-011", "O-013", "O-014", "A-006",
                         "C-006", "P-011", "X-001", "X-010"):
            self.assertEqual(mapped[excluded]["SCOPE"], "EXCLUDED_AI_MCP")
        for mixed in ("U-013", "A-007", "A-016", "A-011", "S-024", "P-024"):
            self.assertEqual(mapped[mixed]["SCOPE"], "CLI_PART_ONLY", mixed)

    def test_master_still_unmodified_and_quality_durations(self):
        text = POLICY.read_text()
        for key in ("FULL_USER_E2E_SCENARIOS.md", "WARMUP=60s",
                    "STEADY_STATE_EACH_CASE=300s", "SOAK=3600s",
                    "EXTENDED_SOAK=8h", "ENDURANCE_SOAK=24h",
                    "BLOCKED_ENVIRONMENT", "BLOCKED_TOOLING",
                    "EXCLUDED_AI_MCP", "EXECUTABLE_SCOPE_COMPLETE",
                    "ALL_APPLICABLE_CLI_E2E_PASS", "no global LAB_GO",
                    "per-host", "actual public", "exit code",
                    "persistent", "SSH", "SCP", "HTTPS",
                    "performance", "security", "release"):
            self.assertIn(key.lower(), text.lower(), key)

    def test_direct_cli_only_trigger_is_first_class(self):
        agents = (ROOT / "AGENTS.md").read_text()
        self.assertIn("CLI_ONLY_E2E_SCENARIOS.md", agents)
        self.assertIn("CLI 단독 E2E", agents)
        self.assertIn("whole CI", agents)
        self.assertIn("Genuine denied effects stay denied", agents)

    def test_initial_rows_preserve_non_applicable_and_blocked_distinction(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir(mode=0o700)
            m.initialize(root, CANONICAL.read_text(), "a" * 40)
            rows = m.read_ledger(root)
            self.assertEqual(len(rows), 116)
            self.assertEqual(sum(r["RESULT"] == "EXCLUDED_AI_MCP" for r in rows), 16)
            self.assertEqual(sum(r["RESULT"] == "NOT_RUN" for r in rows), 100)
            self.assertTrue(all(r["SOURCE_HEAD"] == "a" * 40 for r in rows))
            self.assertTrue(all(r["INSTALLED_HEAD"] == "" for r in rows))
            self.assertTrue((root / "ledger/scenario-results.tsv").is_file())
            with self.assertRaises(FileExistsError):
                m.initialize(root, CANONICAL.read_text(), "a" * 40)

    def test_checkpoint_blocker_cannot_turn_into_pass(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir(mode=0o700)
            m.initialize(root, CANONICAL.read_text(), "a" * 40)
            m.record(root, "U-001", result="BLOCKED_ENVIRONMENT", target="frp-e2e-client",
                     installed_head="b" * 40,
                     command="ssh frp-e2e-client sudo -n drlink help",
                     skip_reason="Host cleanup prohibited; no supported public route",
                     cleanup="BLOCKED_HOST", evidence="", notes="")
            row = next(r for r in m.read_ledger(root) if r["SCENARIO_ID"] == "U-001")
            self.assertEqual(row["RESULT"], "BLOCKED_ENVIRONMENT")
            self.assertIn("prohibited", row["SKIP_REASON"])
            self.assertEqual(row["INSTALLED_HEAD"], "b" * 40)
            with self.assertRaises(ValueError):
                m.record(root, "U-001", result="PASS", target="frp-e2e-client",
                         installed_head="b" * 40, command="drlink help",
                         cleanup="DONE", evidence="", skip_reason="", notes="")
            with self.assertRaises(ValueError):
                m.record(root, "U-007", result="PASS", target="frp-release-server",
                         installed_head="a" * 40, command="drlink help",
                         cleanup="DONE", evidence="", skip_reason="", notes="")
            self.assertEqual(next(r for r in m.read_ledger(root)
                                  if r["SCENARIO_ID"] == "U-007")["RESULT"],
                             "EXCLUDED_AI_MCP")

    def test_failed_soak_prerequisite_has_a_separate_visible_counter(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir(mode=0o700)
            m.initialize(root, CANONICAL.read_text(), "a" * 40)
            m.record(root, "P-013", result="FAIL_PRECONDITION",
                     target="frp-e2e-server",
                     installed_head="b" * 40,
                     command="curl --fail http://owned-test-service/",
                     evidence="", cleanup="NO_OWNED_RESOURCES",
                     skip_reason="Owned HTTP data-plane refused connection",
                     notes="Original functional failure, not a measured soak")
            report = m.summary(m.read_ledger(root))
            self.assertEqual(report["FAIL_PRECONDITION"], 1)
            self.assertEqual(report["FAIL"], 0)
            self.assertEqual(report["NOT_RUN"], 99)
            self.assertFalse(report["ALL_APPLICABLE_CLI_E2E_PASS"])

    def test_performance_profile_does_not_automatically_pass(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "private"
            root.mkdir(mode=0o700)
            m.initialize(root, CANONICAL.read_text(), "a" * 40)
            report = m.summary(m.read_ledger(root))
            self.assertFalse(report["EXECUTABLE_SCOPE_COMPLETE"])
            self.assertFalse(report["ALL_APPLICABLE_CLI_E2E_PASS"])
            self.assertEqual(report["PASS"], 0)
            self.assertEqual(report["NOT_RUN"], 100)

    def test_criteria_cover_all_original_ids_and_are_frozen(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m.initialize(root, CANONICAL.read_text(), "a"*40)
            plan = m.read_criteria(root)
            self.assertEqual(len(plan["catalog"]), 321)
            self.assertEqual(len(m.pending_criteria(root, m.read_ledger(root))), 318)
            self.assertEqual(len({x.split(".")[0] for x in plan["catalog"]}), 100)
            plan["catalog"]["U-001.01"] = "silently changed"
            m.write_json_atomic(m.criterion_path(root), plan)
            with self.assertRaisesRegex(ValueError, "catalog changed"):
                m.read_criteria(root)

    def test_group_evidence_required_for_new_positive_verdict(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m.initialize(root, CANONICAL.read_text(), "a"*40)
            (root/"receipt.txt").write_text("test-only fixture")
            args = dict(result="FUNCTIONAL_PASS_NUMERIC_UNQUALIFIED", target="lab",
                        installed_head="a"*40, command="test fixture", cleanup="DONE",
                        evidence="receipt.txt", skip_reason="NO_APPROVED_NUMERIC_SLO: absent", notes="")
            with self.assertRaisesRegex(ValueError, "criterion groups"):
                m.record(root, "P-013", **args)
            with patch.object(m, "bound_installed_head"):
                for cid in m.criteria_catalog():
                    if cid.startswith("P-013."):
                        m.record_criterion(root, cid, result="PASS", target="lab",
                            installed_head="a"*40, command="test fixture", evidence="receipt.txt", reason="")
                (root/"receipt.txt").write_text("altered")
                with self.assertRaisesRegex(ValueError, "evidence changed"):
                    m.record(root, "P-013", **args)
                (root/"receipt.txt").write_text("test-only fixture")
                m.record(root, "P-013", **args)
            self.assertEqual(m.summary(m.read_ledger(root))["FUNCTIONAL_PASS_NUMERIC_UNQUALIFIED"], 1)

    def test_distinct_gates_and_optional_soak(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m.initialize(root, CANONICAL.read_text(), "a"*40)
            rows = m.read_ledger(root)
            for row in rows:
                if row["SCOPE"] != "EXCLUDED_AI_MCP":
                    row["RESULT"] = "PASS"
            optional = next(r for r in rows if r["SCENARIO_ID"]=="P-019")
            perf = next(r for r in rows if r["SCENARIO_ID"]=="P-013")
            optional["RESULT"] = "PARTIAL"
            self.assertTrue(m.summary(rows)["ALL_APPLICABLE_CLI_E2E_PASS"])
            perf["RESULT"] = "FUNCTIONAL_PASS_NUMERIC_UNQUALIFIED"
            self.assertTrue(m.summary(rows)["CLI_FUNCTIONAL_E2E_PASS"])
            self.assertFalse(m.summary(rows)["ALL_APPLICABLE_CLI_E2E_PASS"])
            perf["RESULT"] = "MEASURED_NOT_QUALIFIED"
            self.assertFalse(m.summary(rows)["CLI_FUNCTIONAL_E2E_PASS"])
            perf["RESULT"] = "PASS"
            optional["PERFORMANCE_PROFILE"] = m.OPTIONAL_SELECTED
            self.assertFalse(m.summary(rows)["CLI_FUNCTIONAL_E2E_PASS"])
            optional["PERFORMANCE_PROFILE"] = m.OPTIONAL_UNSELECTED
            optional["RESULT"] = "FAIL"
            self.assertFalse(m.summary(rows)["CLI_FUNCTIONAL_E2E_PASS"])

    def test_narrow_na_does_not_mask_product_failure(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m.initialize(root, CANONICAL.read_text(), "a"*40)
            (root/"receipt.txt").write_text("fixture: impairment unavailable")
            args = dict(result="NOT_APPLICABLE", target="lab", installed_head="a"*40,
                        command="fixture", cleanup="NO_OWNED_RESOURCES", evidence="receipt.txt",
                        skip_reason="INFRASTRUCTURE_UNSUPPORTED: fixture", notes="")
            with self.assertRaises(ValueError):
                m.record(root, "U-012", **args)
            with self.assertRaises(ValueError):
                m.record(root, "P-020", **dict(args, skip_reason="no access"))
            m.record_criterion(root,"P-020.01",result="FAIL",installed_head="a"*40,
                              target="lab",command="fixture",evidence="receipt.txt",reason="real fail fixture")
            with self.assertRaisesRegex(ValueError, "observed failure"):
                m.record(root, "P-020", **args)

    def test_concurrent_parent_updates_are_not_lost(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m.initialize(root, CANONICAL.read_text(), "a"*40)
            ids = [r["SCENARIO_ID"] for r in m.read_ledger(root) if r["SCOPE"]!="EXCLUDED_AI_MCP"][:12]
            def write(sid):
                subprocess.run([sys.executable, str(GEN), "record", "--run-root", str(root),
                                "--scenario-id", sid, "--result", "PARTIAL",
                                "--skip-reason", "test-only fixture"], check=True, capture_output=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(write,ids))
            self.assertEqual(m.summary(m.read_ledger(root))["PARTIAL"], len(ids))



if __name__ == "__main__":
    unittest.main()
