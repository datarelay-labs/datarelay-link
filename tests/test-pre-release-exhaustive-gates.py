#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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
CONTRACT = ROOT / "docs" / "CLI_FEATURE_SCENARIO_RECONCILIATION.md"
CONTRACT_SHA = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()


def cli_evidence():
    return {
        "schema_version": 1,
        "gate": "CLI_FEATURE_SCENARIO_RECONCILIATION",
        "final_status": "PASS",
        "test_contract_file_sha256": CONTRACT_SHA,
        "test_contract_dirty": False,
        "single_run_coordination": "PASS",
        "repo_head": HEAD,
        "end_head": HEAD,
        "head_unchanged": True,
        "cleanup_status": "PASS",
        "feature_inventory_total": 19,
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
        "max_simultaneous_active_lanes": 4,
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
    feature_header = (
        "FEATURE_ID\tFEATURE_KEY\tFEATURE\tPRODUCT_AUTHORITY\tSUPPORTED\tEXPECTED_ROLE\t"
        "EXPECTED_LIFECYCLE\tCANONICAL_CLI\tMENU_PATH\tINSTALLER_OR_GENERATED_PATH\t"
        "EXPECTED_SCENARIO\tDIRECT_USER_GOAL\tDIRECT_USER_RESULT\tAI_ASSISTED_USER_GOAL\t"
        "AI_ASSISTED_GUIDANCE\tAI_ASSISTED_RESULT\n"
    )
    cli_header = (
        "CLI_PATH\tROLE\tDISCOVERED_BY\tDOCUMENTED\tPRODUCT_FEATURE\tRUNTIME_ONLY\t"
        "DUPLICATE_OF\tLEGACY_OR_COMPATIBILITY\tRUNTIME_OBSERVABLE\tMUTATION_PATH_AUDIT\t"
        "SCENARIO_ID\tEVIDENCE\n"
    )
    feature_cli_header = (
        "FEATURE_ID\tFEATURE\tCANONICAL_CLI\tEXPECTED_SCENARIO\tDIRECT_RESULT\tAI_RESULT\n"
    )
    ai_feature_header = "FEATURE_ID\tFEATURE\tAI_ASSISTED_RESULT\n"
    feature_lines = []
    cli_lines = []
    feature_cli_lines = []
    ai_feature_lines = []
    for idx in range(1, 20):
        fid = f"FEAT-{idx:03d}"
        feature_key = MOD.CLI_REQUIRED_FEATURE_KEYS[idx - 1]
        feature = f"Feature {idx:03d}"
        cli = f"show test-feature-{idx:03d}"
        fcs = f"FCS-{((idx - 1) % 15) + 1:03d}"
        feature_lines.append(
            f"{fid}\t{feature_key}\t{feature}\tPRODUCT_MASTER\tYES\tSERVER\tDISCOVER->SHOW\t{cli}\t"
            f"System\t\t{fcs}\tgoal-{idx}\tPASS\tai-goal-{idx}\tcanonical guidance\tPASS\n"
        )
        cli_lines.append(
            f"{cli}\tserver\thelp\tYES\t{fid}\tNO\t\tNO\tYES\tREAD_ONLY_EXECUTED\t"
            f"{fcs}\tevidence-{idx}\n"
        )
        feature_cli_lines.append(
            f"{fid}\t{feature}\t{cli}\t{fcs}\tPASS\tPASS\n"
        )
        ai_feature_lines.append(f"{fid}\t{feature}\tPASS\n")
    (ledger / "feature-ledger.tsv").write_text(
        feature_header + "".join(feature_lines), encoding="utf-8"
    )
    (ledger / "cli-ledger.tsv").write_text(
        cli_header + "".join(cli_lines), encoding="utf-8"
    )
    (ledger / "feature-cli-scenario.tsv").write_text(
        feature_cli_header + "".join(feature_cli_lines), encoding="utf-8"
    )
    (ledger / "ai-feature-parity.tsv").write_text(
        ai_feature_header + "".join(ai_feature_lines), encoding="utf-8"
    )
    with (ledger / "ai-fcs-parity.tsv").open("w", encoding="utf-8") as fh:
        fh.write("FCS_ID\tAI_LANE\tRESULT\tEVIDENCE\n")
        for idx in range(1, 16):
            fh.write(f"FCS-{idx:03d}\tYES\tPASS\tai-evidence-{idx}\n")
    (ledger / "hidden-alias-enumeration.tsv").write_text(
        "METRIC\tCOUNT\tEVIDENCE\n"
        "PUBLIC_COMMAND_ENTRY_COUNT\t19\tcatalog\n"
        "PUBLIC_ALIAS_PATH_COUNT\t0\tcatalog\n"
        "ROOT_BYPASS_ALIAS_COUNT\t0\tgrammar\n"
        "HIDDEN_COMMAND_ENTRY_COUNT\t0\tcatalog\n"
        "HIDDEN_EXECUTABLE_PATH_COUNT\t0\tparser\n"
        "LEGACY_COMPATIBILITY_PATH_COUNT\t0\tparser\n"
        "PARSER_ONLY_PATH_COUNT\t0\tparity\n"
        "DOC_ONLY_PATH_COUNT\t0\tparity\n"
        "DUPLICATE_PUBLIC_PATH_COUNT\t0\tcatalog\n",
        encoding="utf-8",
    )
    (ledger / "docs-example-ledger.tsv").write_text(
        "PATH\tCLASSIFICATION\tRESULT\tEVIDENCE\n"
        + "".join(
            f"{path}\tCANONICAL_PUBLIC\tPASS\tevidence-{idx}\n"
            for idx, path in enumerate(MOD.CLI_REQUIRED_DOC_SURFACES, 1)
        ),
        encoding="utf-8",
    )
    (ledger / "execution-lanes.tsv").write_text(
        "LANE_ID\tKIND\tSTART_UTC\tEND_UTC\tRESULT\tPREREQUISITE\tEVIDENCE\n"
        "direct-1\tDIRECT_PERSONA\t2026-10-02T00:00:00Z\t2026-10-02T00:00:10Z\tPASS\tNONE\tdirect-1\n"
        "ai-1\tAI_PERSONA\t2026-10-02T00:00:00Z\t2026-10-02T00:00:10Z\tPASS\tNONE\tai-1\n"
        "docs-1\tDOC_SCAN\t2026-10-02T00:00:00Z\t2026-10-02T00:00:10Z\tPASS\tNONE\tdocs-1\n"
        "catalog-1\tCATALOG_AUDIT\t2026-10-02T00:00:00Z\t2026-10-02T00:00:10Z\tPASS\tNONE\tcatalog-1\n",
        encoding="utf-8",
    )


def write_cli_catalog(root: Path, count: int = 19):
    lib = root / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    rows = []
    for idx in range(1, count + 1):
        rows.append(
            {
                "path": ["show", f"test-feature-{idx:03d}"],
                "roles": "server",
                "category": "Test",
                "summary": "test",
                "detail": "test",
                "examples": [],
                "args": [],
                "tail": None,
                "internal": None,
                "aliases": [],
                "destructive": False,
                "hidden": False,
                "risk": "none",
                "confirmation": "none",
                "surface": "",
                "flags": [],
            }
        )
    (lib / "frp_cli_final_commands.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
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

    def test_cli_feature_contract_binding_and_single_run_required(self):
        data = cli_evidence()
        data["test_contract_file_sha256"] = "0" * 64
        data["test_contract_dirty"] = True
        data["single_run_coordination"] = "FAIL"
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("test_contract_dirty" in item for item in errors))
        self.assertTrue(any("single_run_coordination" in item for item in errors))

    def test_cli_feature_max_parallel_lanes_required(self):
        data = cli_evidence()
        data["max_simultaneous_active_lanes"] = 0
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("max_simultaneous_active_lanes" in item for item in errors))

    def test_cli_feature_required_doc_surface_missing_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            docs = run / "ledger" / "docs-example-ledger.tsv"
            lines = [
                line
                for line in docs.read_text(encoding="utf-8").splitlines()
                if not line.startswith("README.ko.md\t")
            ]
            docs.write_text("\n".join(lines) + "\n", encoding="utf-8")
            data = cli_evidence()
            data["evidence_root"] = str(run)
            errors = MOD._validate_cli_ledgers(data, repo, "CLI_TEST")
            self.assertTrue(any("missing required surfaces" in item for item in errors))

    def test_cli_feature_execution_lane_count_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            data = cli_evidence()
            data["evidence_root"] = str(run)
            data["parallel_lanes_started"] = 3
            errors = MOD._validate_cli_ledgers(data, repo, "CLI_TEST")
            self.assertTrue(any("parallel_lanes_started" in item for item in errors))

    def test_cli_feature_required_feature_key_missing_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            ledger = run / "ledger" / "feature-ledger.tsv"
            lines = ledger.read_text(encoding="utf-8").splitlines()
            cols = lines[1].split("\t")
            cols[1] = "UNRELATED_EXTRA"
            lines[1] = "\t".join(cols)
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            data = cli_evidence()
            data["evidence_root"] = str(run)
            errors = MOD._validate_cli_ledgers(data, repo, "CLI_TEST")
            self.assertTrue(any("missing required FEATURE_KEY" in item for item in errors))

    def test_cli_feature_feature_ledger_failure_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            ledger = run / "ledger" / "feature-ledger.tsv"
            lines = ledger.read_text(encoding="utf-8").splitlines()
            cols = lines[1].split("\t")
            cols[12] = "FAIL"
            lines[1] = "\t".join(cols)
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            data = cli_evidence()
            data["evidence_root"] = str(run)
            errors = MOD._validate_cli_ledgers(data, repo, "CLI_TEST")
            self.assertTrue(any("DIRECT_USER_RESULT must be PASS" in item for item in errors))

    def test_cli_feature_cli_orphan_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            ledger = run / "ledger" / "cli-ledger.tsv"
            lines = ledger.read_text(encoding="utf-8").splitlines()
            cols = lines[1].split("\t")
            cols[4] = "FEAT-999"
            lines[1] = "\t".join(cols)
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            data = cli_evidence()
            data["evidence_root"] = str(run)
            errors = MOD._validate_cli_ledgers(data, repo, "CLI_TEST")
            self.assertTrue(any("PRODUCT_FEATURE must map to feature ledger" in item for item in errors))

    def test_cli_feature_hidden_metric_summary_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            ledger = run / "ledger" / "hidden-alias-enumeration.tsv"
            text = ledger.read_text(encoding="utf-8").replace(
                "PUBLIC_ALIAS_PATH_COUNT\t0",
                "PUBLIC_ALIAS_PATH_COUNT\t1",
            )
            ledger.write_text(text, encoding="utf-8")
            data = cli_evidence()
            data["evidence_root"] = str(run)
            errors = MOD._validate_cli_ledgers(data, repo, "CLI_TEST")
            self.assertTrue(any("public_alias_path_count" in item for item in errors))

    def test_cli_feature_exact_head_catalog_binding(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            write_cli_catalog(repo)
            data = cli_evidence()
            data["evidence_root"] = str(run)
            self.assertEqual(
                MOD._validate_cli_catalog_binding(data, repo, "CLI_TEST"), []
            )

            write_cli_catalog(repo, count=18)
            errors = MOD._validate_cli_catalog_binding(data, repo, "CLI_TEST")
            self.assertTrue(
                any(
                    "missing exact-HEAD catalog paths" in item
                    or "PUBLIC_COMMAND_ENTRY_COUNT" in item
                    for item in errors
                )
            )

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

    def test_cli_feature_development_manifest_may_precede_exact_evidence_head(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run = repo / "run"
            write_cli_ledgers(run)
            (repo / "docs").mkdir(parents=True)
            contract = ROOT / "docs" / "CLI_FEATURE_SCENARIO_RECONCILIATION.md"
            (repo / "docs" / contract.name).write_bytes(contract.read_bytes())
            (repo / "lib").mkdir(parents=True)
            (repo / "lib" / "frp_cli_final_commands.json").write_bytes(
                (ROOT / "lib" / "frp_cli_final_commands.json").read_bytes()
            )
            (repo / "release-manifest.json").write_text(
                json.dumps({"source_head": "1" * 40, "channel": "development"}), encoding="utf-8"
            )
            data = cli_evidence()
            data["evidence_root"] = str(run)
            data["test_contract_file_sha256"] = hashlib.sha256(contract.read_bytes()).hexdigest()
            errors = MOD.validate_cli_feature(data, HEAD, repo)
            self.assertFalse(any("release-manifest source_head" in item for item in errors), errors)

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
