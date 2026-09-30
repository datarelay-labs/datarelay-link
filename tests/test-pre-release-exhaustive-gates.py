#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-pre-release-exhaustive-gates.py"
SPEC = importlib.util.spec_from_file_location("pre_release_gates", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)

HEAD = subprocess.check_output(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
).strip().lower()


def cli_evidence():
    return {
        "schema_version": 1,
        "gate": "CLI_FEATURE_SCENARIO_RECONCILIATION",
        "final_status": "PASS",
        "repo_head": HEAD,
        "end_head": HEAD,
        "head_unchanged": True,
        "cleanup_status": "PASS",
        "feature_inventory_total": 25,
        "product_source_head": HEAD,
        "server_source_head": HEAD,
        "agent_source_head": HEAD,
        "server_runtime_match": "EXACT",
        "agent_runtime_match": "EXACT",
        "runtime_coverage_complete": True,
        "evidence_ledger_schema": "PASS",
        "summary_derived_from_ledger": True,
        "report_consistency": "PASS",
        "primary_user_evidence_mode": "PERSONA_LED_PUBLIC_UX",
        "tty_tooling_status": "PASS",
        "tty_persona_coverage": "PASS",
        "github_report_status": "PASS",
        "github_report_readback": "PASS",
        "fcs_counts": {"total": 15, "pass": 15, "fail": 0, "blocked": 0},
        "finding_counts": {"total": 0, "open": 0, "p0": 0, "p1": 0, "p2": 0, "p3": 0, "user_blocking_open": 0},
        "user_role_execution": "PASS",
        "scripted_user_scenario_execution": False,
        "automated_harness_role": "SUPPLEMENTAL_ONLY",
        "direct_user_feature_coverage": 100,
        "ai_assisted_feature_coverage": 100,
        "direct_user_fcs_coverage": 100,
        "ai_assisted_fcs_coverage": 100,
        "parallel_execution": "MAXIMUM_SAFE",
        "parallel_lanes_started": 4,
        "serial_idle_with_runnable_work": False,
        "counters": {key: 0 for key in MOD.CLI_ZERO_COUNTERS},
        "evidence_root": "e2e-reports/cli-feature-scenario-test",
    }

def write_cli_ledgers(root: Path):
    ledger = root / "ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    with (ledger / "fcs-results.tsv").open("w", encoding="utf-8") as fh:
        fh.write("FCS_ID\tAPPLICABLE\tDIRECT_RESULT\tAI_RESULT\tFINAL_RESULT\tBLOCK_REASON\tEVIDENCE\n")
        for idx in range(1, 16):
            fh.write(f"FCS-{idx:03d}\tYES\tPASS\tPASS\tPASS\t\tevidence-{idx}\n")
    (ledger / "findings.tsv").write_text(
        "FINDING_ID\tSEVERITY\tUSER_BLOCKING\tSTATUS\tCLASSIFICATION\tSURFACE\tEVIDENCE\n",
        encoding="utf-8",
    )


def write_full_ledgers(root: Path):
    ledger = root / "ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    (ledger / "scenario-results.tsv").write_text(
        "SCENARIO_ID\tUSE_CASE_ID\tAPPLICABLE\tMANDATORY\tDIRECT_RESULT\tAI_REQUIRED\tAI_RESULT\tFINAL_RESULT\tBLOCK_REASON\tEVIDENCE\n"
        "U-001\tUC-01\tYES\tYES\tPASS\tYES\tPASS\tPASS\t\tevidence-u1\n",
        encoding="utf-8",
    )
    (ledger / "findings.tsv").write_text(
        "FINDING_ID\tSEVERITY\tUSER_BLOCKING\tSTATUS\tCLASSIFICATION\tSURFACE\tEVIDENCE\n",
        encoding="utf-8",
    )


def full_evidence(pass_name: str):
    data = {
        "schema_version": 1,
        "gate": "FULL_USER_E2E",
        "pass_name": pass_name,
        "final_status": "PASS",
        "git_head": HEAD,
        "end_head": HEAD,
        "head_unchanged": True,
        "product_source_head": HEAD,
        "summary_derived_from_ledger": True,
        "primary_user_evidence_mode": "PERSONA_LED_PUBLIC_UX",
        "scenario_counts": {"total": 1, "pass": 1, "fail": 0, "blocked": 0},
        "finding_counts": {"total": 0, "open": 0, "p0": 0, "p1": 0, "p2": 0, "p3": 0, "user_blocking_open": 0},
        "evidence_root": f"e2e-reports/full-user-e2e-{pass_name.lower()}",
    }
    data.update({key: "PASS" for key in MOD.FULL_PASS_FIELDS})
    data.update({key: 0 for key in MOD.FULL_ZERO_FIELDS})
    return data


class PreReleaseExhaustiveGateTests(unittest.TestCase):
    def test_cli_feature_valid(self):
        self.assertEqual(MOD.validate_cli_feature(cli_evidence(), HEAD), [])

    def test_cli_feature_nonzero_counter_blocks(self):
        data = cli_evidence()
        data["counters"]["public_alias_path_count"] = 1
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("public_alias_path_count" in item for item in errors))

    def test_cli_feature_runtime_mutation_attempt_blocks(self):
        data = cli_evidence()
        data["counters"]["runtime_mutation_attempt_count"] = 1
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("runtime_mutation_attempt_count" in item for item in errors))

    def test_cli_feature_parallel_execution_required(self):
        data = cli_evidence()
        data["parallel_execution"] = "SERIAL"
        data["serial_idle_with_runnable_work"] = True
        data["counters"]["avoidable_serial_wait_count"] = 1
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("parallel_execution" in item for item in errors))
        self.assertTrue(any("serial_idle_with_runnable_work" in item for item in errors))
        self.assertTrue(any("avoidable_serial_wait_count" in item for item in errors))

    def test_cli_feature_ai_and_user_role_required(self):
        data = cli_evidence()
        data["user_role_execution"] = "FAIL"
        data["scripted_user_scenario_execution"] = True
        data["ai_assisted_feature_coverage"] = 99
        data["counters"]["features_without_ai_support_count"] = 1
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("user_role_execution" in item for item in errors))
        self.assertTrue(any("scripted_user_scenario_execution" in item for item in errors))
        self.assertTrue(any("ai_assisted_feature_coverage" in item for item in errors))
        self.assertTrue(any("features_without_ai_support_count" in item for item in errors))

    def test_cli_feature_stale_head_blocks(self):
        data = cli_evidence()
        data["end_head"] = "0" * 40
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("end_head" in item for item in errors))

    def test_cli_feature_stale_runtime_and_report_block(self):
        data = cli_evidence()
        data["server_runtime_match"] = "STALE"
        data["github_report_readback"] = "FAIL"
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("server_runtime_match" in item for item in errors))
        self.assertTrue(any("github_report_readback" in item for item in errors))

    def test_cli_feature_ledger_summary_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            (repo / "release-manifest.json").write_text(json.dumps({"source_head": HEAD}), encoding="utf-8")
            data = cli_evidence()
            data["evidence_root"] = str(run)
            data["fcs_counts"]["pass"] = 14
            errors = MOD.validate_cli_feature(data, HEAD, repo)
            self.assertTrue(any("fcs_counts.pass" in item for item in errors))

    def test_full_user_pass1_valid(self):
        self.assertEqual(MOD.validate_full_user(full_evidence("PASS1"), HEAD, "PASS1"), [])

    def test_full_user_pass2_valid(self):
        self.assertEqual(MOD.validate_full_user(full_evidence("PASS2"), HEAD, "PASS2"), [])

    def test_full_user_missing_required_pass_blocks(self):
        data = full_evidence("PASS1")
        data["backup_restore"] = "PARTIAL"
        errors = MOD.validate_full_user(data, HEAD, "PASS1")
        self.assertTrue(any("backup_restore" in item for item in errors))

    def test_full_user_unexercised_command_blocks(self):
        data = full_evidence("PASS2")
        data["unexercised_public_commands"] = 1
        errors = MOD.validate_full_user(data, HEAD, "PASS2")
        self.assertTrue(any("unexercised_public_commands" in item for item in errors))

    def test_full_user_ledger_summary_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_full_ledgers(run)
            (repo / "release-manifest.json").write_text(json.dumps({"source_head": HEAD}), encoding="utf-8")
            data = full_evidence("PASS1")
            data["evidence_root"] = str(run)
            data["scenario_counts"]["pass"] = 0
            errors = MOD.validate_full_user(data, HEAD, "PASS1", repo)
            self.assertTrue(any("scenario_counts.pass" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
