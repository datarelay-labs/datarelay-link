#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
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
    def _git(self, repo, *args):
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True, stderr=subprocess.PIPE
        ).strip()

    def _provenance_repo(self, repo):
        self._git(repo, "init", "--quiet")
        self._git(repo, "config", "user.name", "Quality fixture")
        self._git(repo, "config", "user.email", "quality@example.test")
        (repo / "docs").mkdir()
        (repo / "docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md").write_bytes(CONTRACT.read_bytes())
        write_cli_ledgers(repo / "cli-run")
        write_cli_catalog(repo)
        write_full_ledgers(repo / "full-run")
        (repo / "dist").mkdir()
        (repo / "dist/bootstrap-client.sh").write_text("content payload\n")
        (repo / "release-manifest.json").write_text(json.dumps({"source_head": "0" * 40}))
        self._git(repo, "add", ".")
        self._git(repo, "commit", "--quiet", "-m", "content")
        content = self._git(repo, "rev-parse", "HEAD")
        (repo / "release-manifest.json").write_text(json.dumps({"source_head": content}))
        (repo / "dist/bootstrap-client.sh").write_text("generated provenance payload\n")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "--quiet", "-m", "generated provenance")
        return content, self._git(repo, "rev-parse", "HEAD")

    def _candidate_evidence(self, repo, candidate):
        cli = cli_evidence()
        for key in ("repo_head", "end_head", "product_source_head", "server_source_head", "agent_source_head"):
            cli[key] = candidate
        cli["evidence_root"] = str(repo / "cli-run")
        full = full_evidence("PASS1")
        for key in ("git_head", "end_head", "product_source_head"):
            full[key] = candidate
        full["evidence_root"] = str(repo / "full-run")
        return cli, full

    def test_provenance_candidate_passes_both_user_gate_validators(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            content, candidate = self._provenance_repo(repo)
            self.assertNotEqual(content, candidate)
            cli, full = self._candidate_evidence(repo, candidate)
            self.assertEqual(MOD.validate_cli_feature(cli, candidate, repo), [])
            self.assertEqual(MOD.validate_full_user(full, candidate, "PASS1", repo), [])

    def test_content_parent_runtime_cannot_replace_exact_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            content, candidate = self._provenance_repo(repo)
            cli, full = self._candidate_evidence(repo, candidate)
            for key in ("product_source_head", "server_source_head", "agent_source_head"):
                cli[key] = content
            full["product_source_head"] = content
            for errors in (MOD.validate_cli_feature(cli, candidate, repo), MOD.validate_full_user(full, candidate, "PASS1", repo)):
                self.assertTrue(any("product_source_head must equal exact HEAD" in x for x in errors), errors)

    def test_stale_runtime_still_blocks_valid_provenance_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            content, candidate = self._provenance_repo(repo)
            cli, _ = self._candidate_evidence(repo, candidate)
            cli["server_source_head"] = content
            errors = MOD.validate_cli_feature(cli, candidate, repo)
            self.assertTrue(any("server_source_head must equal product_source_head" in x for x in errors), errors)

    def test_old_ancestor_manifest_rejected_by_both_user_gates(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _, _ = self._provenance_repo(repo)
            (repo / "SHA256SUMS").write_text("another metadata revision\n")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "--quiet", "-m", "later metadata")
            candidate = self._git(repo, "rev-parse", "HEAD")
            cli, full = self._candidate_evidence(repo, candidate)
            for errors in (MOD.validate_cli_feature(cli, candidate, repo), MOD.validate_full_user(full, candidate, "PASS1", repo)):
                self.assertTrue(any("first content parent" in x for x in errors), errors)

    def test_product_changes_cannot_be_claimed_as_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _, parent = self._provenance_repo(repo)
            (repo / "release-manifest.json").write_text(json.dumps({"source_head": parent}))
            (repo / "lib/runtime.py").write_text("changed product\n")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "--quiet", "-m", "product change disguised as provenance")
            candidate = self._git(repo, "rev-parse", "HEAD")
            cli, full = self._candidate_evidence(repo, candidate)
            for errors in (MOD.validate_cli_feature(cli, candidate, repo), MOD.validate_full_user(full, candidate, "PASS1", repo)):
                self.assertTrue(any("non-generated paths" in x for x in errors), errors)

    def test_provenance_cannot_delete_generated_payload(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _, parent = self._provenance_repo(repo)
            (repo / "release-manifest.json").write_text(json.dumps({"source_head": parent}))
            (repo / "dist/bootstrap-client.sh").unlink()
            self._git(repo, "add", "--all")
            self._git(repo, "commit", "--quiet", "-m", "deleted payload")
            candidate = self._git(repo, "rev-parse", "HEAD")
            errors = MOD._validate_manifest_candidate_binding(repo, candidate, "TEST")
            self.assertTrue(any("must not rename or delete" in x for x in errors), errors)

    def test_manifest_binding_uses_checked_out_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _, candidate = self._provenance_repo(repo)
            (repo / "SHA256SUMS").write_text("later metadata\n")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "--quiet", "-m", "later candidate")
            errors = MOD._validate_manifest_candidate_binding(repo, candidate, "TEST")
            self.assertTrue(any("checked-out HEAD" in x for x in errors), errors)

    def test_generated_change_without_manifest_update_is_not_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._git(repo, "init", "--quiet")
            self._git(repo, "config", "user.name", "Quality fixture")
            self._git(repo, "config", "user.email", "quality@example.test")
            (repo / "SHA256SUMS").write_text("content\n")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "--quiet", "-m", "content")
            parent = self._git(repo, "rev-parse", "HEAD")
            (repo / "SHA256SUMS").write_text("changed metadata only\n")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "--quiet", "-m", "not a provenance commit")
            candidate = self._git(repo, "rev-parse", "HEAD")
            # The manifest is uncommitted: it cannot prove the committed binding.
            (repo / "release-manifest.json").write_text(json.dumps({"source_head": parent}))
            errors = MOD._validate_manifest_candidate_binding(repo, candidate, "TEST")
            self.assertTrue(any("updating release-manifest.json" in x for x in errors), errors)

    def test_missing_git_parent_cannot_satisfy_manifest_binding(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "release-manifest.json").write_text(json.dumps({"source_head": "1" * 40}))
            errors = MOD._validate_manifest_candidate_binding(repo, HEAD, "TEST")
            self.assertTrue(any("cannot prove manifest content-parent" in x for x in errors), errors)

    def test_missing_or_malformed_manifest_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            for source in (None, "not-a-sha"):
                (repo / "release-manifest.json").write_text(json.dumps({"source_head": source}))
                errors = MOD._validate_manifest_candidate_binding(repo, HEAD, "TEST")
                self.assertTrue(any("40-character SHA" in x for x in errors), errors)
            for value in ([], "manifest", None):
                (repo / "release-manifest.json").write_text(json.dumps(value))
                errors = MOD._validate_manifest_candidate_binding(repo, HEAD, "TEST")
                self.assertTrue(any("must be an object" in x for x in errors), errors)

    def test_dirty_manifest_cannot_prove_committed_parent_binding(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            parent, candidate = self._provenance_repo(repo)
            (repo / "release-manifest.json").write_text(json.dumps({"source_head": parent, "uncommitted": True}))
            for staged in (False, True):
                if staged:
                    self._git(repo, "add", "release-manifest.json")
                errors = MOD._validate_manifest_candidate_binding(repo, candidate, "TEST")
                self.assertTrue(any("committed candidate manifest" in x for x in errors), errors)

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


class EvidenceInputIntegrityTests(unittest.TestCase):
    """Malformed reports must never become qualification success."""

    def test_public_gate_command_rejects_bad_counts_without_mutating_evidence(self):
        for value in (0.5, False, float("inf")):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as td:
                repo = Path(td)
                fixtures = PreReleaseExhaustiveGateTests()
                _content, candidate = fixtures._provenance_repo(repo)
                _cli, data = fixtures._candidate_evidence(repo, candidate)
                data["unexercised_public_commands"] = value
                report = repo / "e2e-reports/release-qualification/full-user-e2e-pass1.json"
                report.parent.mkdir(parents=True)
                report.write_text(json.dumps(data) + "\n")
                before = report.read_bytes()
                env = {key: value for key, value in os.environ.items()
                       if key not in {"DRLINK_CLI_FEATURE_SCENARIO_EVIDENCE",
                                      "DRLINK_FULL_USER_E2E_PASS1_EVIDENCE",
                                      "DRLINK_FULL_USER_E2E_PASS2_EVIDENCE"}}
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--root", str(repo), "--gate", "full-user-e2e-pass1"],
                    env=env, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("unexercised_public_commands", result.stderr)
                self.assertIn("PRE_RELEASE_EXHAUSTIVE_GATES=FAIL", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("PRE_RELEASE_EXHAUSTIVE_GATES=PASS", result.stdout)
                self.assertEqual(report.read_bytes(), before)

    def test_tsv_decimal_counts_remain_supported(self):
        for text, expected in (("0", 0), ("0019", 19), (" 19 ", 19)):
            with self.subTest(text=text):
                self.assertEqual(MOD._count(text, from_tsv=True), expected)
        for text in ("0.5", "NaN", "Infinity", "-1", "1e3", "", "9" * 4500):
            with self.subTest(text=text[:20]):
                self.assertEqual(MOD._count(text, from_tsv=True), -1)

    def test_full_all_nonapplicable_is_not_an_executed_full_run(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            write_full_ledgers(repo / "run")
            path = repo / "run/ledger/scenario-results.tsv"
            path.write_text(path.read_text().splitlines()[0] + "\nX-001\tUC-01\tNO\tNO\tNOT_APPLICABLE\tNO\tNOT_APPLICABLE\tNOT_APPLICABLE\tOptional separate adapter not in scope\tevidence-x1\n")
            data = full_evidence("PASS1")
            data["evidence_root"] = "run"
            data["scenario_counts"]["pass"] = 0
            errors = MOD._validate_full_ledgers(data, repo, "TEST")
            self.assertTrue(any("executed applicable" in x for x in errors), errors)

    def test_cli_zero_counters_reject_non_integer_values(self):
        for key in MOD.CLI_ZERO_COUNTERS:
            for value in (False, 0.0, 0.5, -0.5, "0", float("nan"), float("inf")):
                with self.subTest(key=key, value=value):
                    data = cli_evidence()
                    data["counters"][key] = value
                    errors = MOD.validate_cli_feature(data, HEAD)
                    self.assertTrue(any(key in error for error in errors), errors)

    def test_full_zero_counters_reject_non_integer_values(self):
        for key in MOD.FULL_ZERO_FIELDS:
            for value in (False, 0.0, 0.5, -0.5, "0", float("nan"), float("inf")):
                with self.subTest(key=key, value=value):
                    data = full_evidence("PASS1")
                    data[key] = value
                    errors = MOD.validate_full_user(data, HEAD, "PASS1")
                    self.assertTrue(any(key in error for error in errors), errors)

    def test_cli_numeric_summary_fields_require_json_integers(self):
        cases = {
            "feature_inventory_total": (19.5, "19", float("inf")),
            "direct_user_feature_coverage": (100.5, "100", float("inf")),
            "ai_assisted_feature_coverage": (100.5, "100", float("inf")),
            "direct_user_fcs_coverage": (100.5, "100", float("inf")),
            "ai_assisted_fcs_coverage": (100.5, "100", float("inf")),
            "parallel_lanes_started": (True, 4.5, "4", float("inf")),
            "max_simultaneous_active_lanes": (True, 4.5, "4", float("inf")),
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    data = cli_evidence()
                    data[key] = value
                    errors = MOD.validate_cli_feature(data, HEAD)
                    self.assertTrue(any(key in error for error in errors), errors)

    def test_schema_version_is_not_a_boolean_or_float(self):
        for value in (True, 1.0, "1"):
            with self.subTest(value=value):
                cli = cli_evidence()
                cli["schema_version"] = value
                full = full_evidence("PASS1")
                full["schema_version"] = value
                self.assertTrue(any("schema_version" in x for x in MOD.validate_cli_feature(cli, HEAD)))
                self.assertTrue(any("schema_version" in x for x in MOD.validate_full_user(full, HEAD, "PASS1")))

    def test_count_map_rejects_lossy_values(self):
        for expected in (False, 0.5, -0.5, "0", float("inf"), float("nan")):
            with self.subTest(expected=expected):
                self.assertTrue(MOD._compare_count_map({"total": 0}, {"total": expected}, "TEST", "counts"))
        self.assertEqual(MOD._compare_count_map({"total": 0}, {"total": 0}, "TEST", "counts"), [])

    def test_malformed_tsv_does_not_hide_columns(self):
        cases = (
            "ID\tRESULT\tRESULT\nx\tFAIL\tPASS\n",
            "ID\tRESULT\nx\tPASS\textra\n",
            "ID\tRESULT\nx\n",
            "ID\t\tRESULT\nx\tignored\tPASS\n",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "malformed.tsv"
            for text in cases:
                with self.subTest(text=text):
                    path.write_text(text)
                    _rows, errors = MOD._read_tsv(path, ("ID", "RESULT"), "TEST")
                    self.assertTrue(errors)

    def test_full_scenario_flags_fail_closed(self):
        for field in ("APPLICABLE", "MANDATORY", "AI_REQUIRED"):
            for value in ("", "YSE", "UNKNOWN"):
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as td:
                    repo = Path(td)
                    write_full_ledgers(repo / "run")
                    path = repo / "run/ledger/scenario-results.tsv"
                    lines = path.read_text().splitlines()
                    fields = lines[0].split("\t")
                    row = lines[1].split("\t")
                    row[fields.index(field)] = value
                    path.write_text(lines[0] + "\n" + "\t".join(row) + "\n")
                    data = full_evidence("PASS1")
                    data["evidence_root"] = "run"
                    errors = MOD._validate_full_ledgers(data, repo, "TEST")
                    self.assertTrue(any(field in x for x in errors), errors)

    def test_full_nonapplicable_cannot_be_counted_as_pass(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            write_full_ledgers(repo / "run")
            path = repo / "run/ledger/scenario-results.tsv"
            path.write_text(path.read_text().replace("UC-01\tYES", "UC-01\tNO"))
            data = full_evidence("PASS1")
            data["evidence_root"] = "run"
            errors = MOD._validate_full_ledgers(data, repo, "TEST")
            self.assertTrue(any("NOT_APPLICABLE" in x for x in errors), errors)

    def test_full_nonapplicable_requires_a_reason(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            write_full_ledgers(repo / "run")
            path = repo / "run/ledger/scenario-results.tsv"
            path.write_text(path.read_text() + "X-001\tUC-02\tNO\tNO\tNOT_APPLICABLE\tNO\tNOT_APPLICABLE\tNOT_APPLICABLE\t\tevidence-x1\n")
            data = full_evidence("PASS1")
            data["evidence_root"] = "run"
            data["scenario_counts"]["total"] = 2
            errors = MOD._validate_full_ledgers(data, repo, "TEST")
            self.assertTrue(any("reason" in x for x in errors), errors)

    def test_full_explicit_nonapplicable_disposition_remains_supported(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            write_full_ledgers(repo / "run")
            path = repo / "run/ledger/scenario-results.tsv"
            path.write_text(path.read_text() + "X-001\tUC-02\tNO\tNO\tNOT_APPLICABLE\tNO\tNOT_APPLICABLE\tNOT_APPLICABLE\tSeparate optional adapter outside declared product scope\tevidence-x1\n")
            data = full_evidence("PASS1")
            data["evidence_root"] = "run"
            data["scenario_counts"]["total"] = 2
            self.assertEqual(MOD._validate_full_ledgers(data, repo, "TEST"), [])

    def test_full_empty_scenario_or_use_case_id_is_invalid(self):
        for field in ("SCENARIO_ID", "USE_CASE_ID"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                repo = Path(td)
                write_full_ledgers(repo / "run")
                path = repo / "run/ledger/scenario-results.tsv"
                lines = path.read_text().splitlines()
                row = lines[1].split("\t")
                row[lines[0].split("\t").index(field)] = ""
                path.write_text(lines[0] + "\n" + "\t".join(row) + "\n")
                data = full_evidence("PASS1")
                data["evidence_root"] = "run"
                errors = MOD._validate_full_ledgers(data, repo, "TEST")
                self.assertTrue(any(field in x for x in errors), errors)

    def test_cli_timeline_rejects_missing_timezone_without_crashing(self):
        for original in ("2026-10-02T00:00:00Z", "2026-10-02T00:00:10Z"):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as td:
                repo = Path(td)
                write_cli_ledgers(repo / "run")
                path = repo / "run/ledger/execution-lanes.tsv"
                path.write_text(path.read_text().replace(original, original[:-1], 1))
                data = cli_evidence()
                data["evidence_root"] = "run"
                errors = MOD._validate_cli_ledgers(data, repo, "TEST")
                self.assertTrue(any("timezone" in x for x in errors), errors)

    def test_cli_zero_length_lane_cannot_prove_parallel_execution(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            write_cli_ledgers(repo / "run")
            path = repo / "run/ledger/execution-lanes.tsv"
            path.write_text(path.read_text().replace("2026-10-02T00:00:10Z", "2026-10-02T00:00:00Z", 1))
            data = cli_evidence()
            data["evidence_root"] = "run"
            self.assertTrue(MOD._validate_cli_ledgers(data, repo, "TEST"))

    def test_cli_explicit_offset_timeline_remains_valid(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            write_cli_ledgers(repo / "run")
            path = repo / "run/ledger/execution-lanes.tsv"
            path.write_text(path.read_text().replace("2026-10-02T00:00:00Z", "2026-10-02T09:00:00+09:00", 1).replace("2026-10-02T00:00:10Z", "2026-10-02T09:00:10+09:00", 1))
            data = cli_evidence()
            data["evidence_root"] = "run"
            self.assertEqual(MOD._validate_cli_ledgers(data, repo, "TEST"), [])


if __name__ == "__main__":
    unittest.main()
