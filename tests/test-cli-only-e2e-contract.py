#!/usr/bin/env python3
"""CLI-only E2E scope and evidence regressions, separate from Full User E2E."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
