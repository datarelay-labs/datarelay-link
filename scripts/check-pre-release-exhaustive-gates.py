#!/usr/bin/env python3
"""Validate mandatory pre-release exhaustive human-test evidence on exact HEAD."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")

CLI_ZERO_COUNTERS = (
    "feature_no_cli_gaps",
    "feature_without_discoverable_cli_count",
    "cli_without_product_feature_count",
    "runtime_only_cli_count",
    "duplicate_public_path_count",
    "public_alias_path_count",
    "legacy_compatibility_path_count",
    "root_bypass_alias_count",
    "hidden_executable_path_count",
    "discovery_gap_count",
    "installer_guidance_mismatch_count",
    "destructive_confirmation_gap_count",
    "destructive_child_variant_metadata_gap_count",
    "error_with_zero_rc_count",
    "active_guidance_noncanonical_count",
    "help_only_legacy_path_count",
    "public_noun_drift_count",
    "stale_regression_grammar_count",
    "active_installer_legacy_term_count",
    "scenario_blocked_count",
    "scenario_dead_end_count",
    "cleanup_residue_count",
    "runtime_mutation_attempt_count",
    "avoidable_serial_wait_count",
    "features_without_ai_support_count",
    "fcs_without_ai_support_count",
    "ai_noncanonical_guidance_count",
    "ai_hidden_internal_syntax_leak_count",
    "ai_role_context_drift_count",
    "scripted_user_scenario_execution_count",
    "automated_harness_user_substitution_count",
    "evidence_summary_mismatch_count",
    "auditor_knowledge_leak_count",
    "tooling_blocker_count",
    "tty_tooling_block_count",
)
FULL_PASS_FIELDS = (
    "pre_run_clean_state",
    "all_reachable_assigned_hosts_clean",
    "process_cleanup",
    "user_scenarios",
    "operator_scenarios",
    "admin_scenarios",
    "negative_failure_functional",
    "performance_functional",
    "multi_platform",
    "topology_matrix",
    "parallel_multi_host",
    "operational_persona_coverage",
    "discovery_from_public_ux",
    "acting_persona_manual_free",
    "current_configured_test_hosts_only",
    "drlink_control_plane_cli_only",
    "ai_assisted_cli",
    "remote_access_real_traffic",
    "internet_access_real_traffic",
    "ai_mcp_real_traffic",
    "zero_touch",
    "configuration_bundle",
    "backup_restore",
    "reboot_recovery",
    "update_recovery",
    "endpoint_continuity",
    "user_role_execution",
    "tty_tooling_status",
    "tty_persona_coverage",
    "evidence_ledger_schema",
    "report_consistency",
    "github_report_status",
    "github_report_readback",
    "assigned_runtime_heads_match_product_source",
)

FULL_ZERO_FIELDS = (
    "commands_without_use_case",
    "public_commands_without_direct_use",
    "use_cases_without_ai_mirror",
    "oracle_only_commands_not_discoverable",
    "discoverability_defects",
    "doc_runtime_command_drift",
    "unexercised_public_commands",
    "evidence_summary_mismatch_count",
    "auditor_knowledge_leak_count",
    "scripted_user_scenario_execution_count",
    "automated_harness_user_substitution_count",
    "pre_candidate_observation_product_finding_count",
)

def git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError("unable to resolve repository HEAD")
    head = proc.stdout.strip().lower()
    if not SHA_RE.fullmatch(head):
        raise ValueError("repository HEAD is not a 40-character lowercase SHA")
    return head


def load_json(path: Path, label: str) -> tuple[dict, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"{label}: unable to read {path}: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{label}: evidence must be a JSON object"]
    return data, []

def _pass(value: object) -> bool:
    return str(value or "").strip().upper() == "PASS"


def _zero(value: object) -> bool:
    if isinstance(value, bool):
        return not value
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


def _resolve_evidence_root(repo_root: Path, data: dict) -> Path:
    raw = str(data.get("evidence_root") or "").strip()
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def _read_tsv(path: Path, required: tuple[str, ...], label: str) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        return [], [f"{label}: missing ledger {path}"]
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            fields = tuple(reader.fieldnames or ())
            missing = [key for key in required if key not in fields]
            if missing:
                return [], [f"{label}: {path} missing columns {','.join(missing)}"]
            rows = [dict(row) for row in reader]
    except Exception as exc:
        return [], [f"{label}: unable to read ledger {path}: {exc}"]
    return rows, []


def _finding_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {"total": len(rows), "open": 0, "p0": 0, "p1": 0, "p2": 0, "p3": 0, "user_blocking_open": 0}
    closed = {"RESOLVED", "CLOSED", "NON_ACTIONABLE"}
    for row in rows:
        sev = str(row.get("SEVERITY") or "").strip().upper()
        if sev in {"P0", "P1", "P2", "P3"}:
            counts[sev.lower()] += 1
        status = str(row.get("STATUS") or "").strip().upper()
        if status not in closed:
            counts["open"] += 1
            if str(row.get("USER_BLOCKING") or "").strip().upper() == "YES":
                counts["user_blocking_open"] += 1
    return counts


def _compare_count_map(actual: dict[str, int], expected: object, label: str, field: str) -> list[str]:
    if not isinstance(expected, dict):
        return [f"{label}: {field} must be an object"]
    errors: list[str] = []
    for key, value in actual.items():
        try:
            got = int(expected.get(key))
        except (TypeError, ValueError):
            got = -1
        if got != value:
            errors.append(f"{label}: {field}.{key}={got} but ledger={value}")
    return errors


def _validate_cli_ledgers(data: dict, repo_root: Path, label: str) -> list[str]:
    root = _resolve_evidence_root(repo_root, data)
    fcs_rows, errors = _read_tsv(
        root / "ledger" / "fcs-results.tsv",
        ("FCS_ID", "APPLICABLE", "DIRECT_RESULT", "AI_RESULT", "FINAL_RESULT", "BLOCK_REASON", "EVIDENCE"),
        label,
    )
    finding_rows, finding_errors = _read_tsv(
        root / "ledger" / "findings.tsv",
        ("FINDING_ID", "SEVERITY", "USER_BLOCKING", "STATUS", "CLASSIFICATION", "SURFACE", "EVIDENCE"),
        label,
    )
    errors += finding_errors
    expected_ids = {f"FCS-{idx:03d}" for idx in range(1, 16)}
    ids = [str(row.get("FCS_ID") or "").strip() for row in fcs_rows]
    if set(ids) != expected_ids or len(ids) != len(set(ids)):
        errors.append(f"{label}: fcs-results.tsv must contain each FCS-001..FCS-015 exactly once")
    for row in fcs_rows:
        fid = str(row.get("FCS_ID") or "").strip()
        if str(row.get("APPLICABLE") or "").strip().upper() != "YES":
            errors.append(f"{label}: {fid} must be applicable for release-gate PASS")
        for key in ("DIRECT_RESULT", "AI_RESULT", "FINAL_RESULT"):
            if not _pass(row.get(key)):
                errors.append(f"{label}: {fid} {key} must be PASS")
    fcs_counts = {
        "total": len(fcs_rows),
        "pass": sum(_pass(row.get("FINAL_RESULT")) for row in fcs_rows),
        "fail": sum(str(row.get("FINAL_RESULT") or "").strip().upper() in {"FAIL", "PARTIAL", "FAIL_PRECONDITION"} for row in fcs_rows),
        "blocked": sum(str(row.get("FINAL_RESULT") or "").strip().upper().startswith("BLOCKED") for row in fcs_rows),
    }
    errors += _compare_count_map(fcs_counts, data.get("fcs_counts"), label, "fcs_counts")
    findings = _finding_counts(finding_rows)
    errors += _compare_count_map(findings, data.get("finding_counts"), label, "finding_counts")
    if findings["open"] != 0:
        errors.append(f"{label}: findings ledger has {findings['open']} unresolved findings")
    return errors


def _validate_full_ledgers(data: dict, repo_root: Path, label: str) -> list[str]:
    root = _resolve_evidence_root(repo_root, data)
    scenario_rows, errors = _read_tsv(
        root / "ledger" / "scenario-results.tsv",
        ("SCENARIO_ID", "USE_CASE_ID", "APPLICABLE", "MANDATORY", "DIRECT_RESULT", "AI_REQUIRED", "AI_RESULT", "FINAL_RESULT", "BLOCK_REASON", "EVIDENCE"),
        label,
    )
    finding_rows, finding_errors = _read_tsv(
        root / "ledger" / "findings.tsv",
        ("FINDING_ID", "SEVERITY", "USER_BLOCKING", "STATUS", "CLASSIFICATION", "SURFACE", "EVIDENCE"),
        label,
    )
    errors += finding_errors
    ids = [str(row.get("SCENARIO_ID") or "").strip() for row in scenario_rows]
    if not ids:
        errors.append(f"{label}: scenario-results.tsv must not be empty")
    if len(ids) != len(set(ids)):
        errors.append(f"{label}: scenario-results.tsv contains duplicate SCENARIO_ID")
    for row in scenario_rows:
        sid = str(row.get("SCENARIO_ID") or "").strip()
        applicable = str(row.get("APPLICABLE") or "").strip().upper() == "YES"
        if not applicable:
            continue
        if not _pass(row.get("DIRECT_RESULT")):
            errors.append(f"{label}: {sid} DIRECT_RESULT must be PASS")
        if str(row.get("AI_REQUIRED") or "").strip().upper() == "YES" and not _pass(row.get("AI_RESULT")):
            errors.append(f"{label}: {sid} AI_RESULT must be PASS")
        if not _pass(row.get("FINAL_RESULT")):
            errors.append(f"{label}: {sid} FINAL_RESULT must be PASS")
    scenario_counts = {
        "total": len(scenario_rows),
        "pass": sum(_pass(row.get("FINAL_RESULT")) for row in scenario_rows),
        "fail": sum(str(row.get("FINAL_RESULT") or "").strip().upper() in {"FAIL", "PARTIAL", "FAIL_PRECONDITION"} for row in scenario_rows),
        "blocked": sum(str(row.get("FINAL_RESULT") or "").strip().upper().startswith("BLOCKED") for row in scenario_rows),
    }
    errors += _compare_count_map(scenario_counts, data.get("scenario_counts"), label, "scenario_counts")
    findings = _finding_counts(finding_rows)
    errors += _compare_count_map(findings, data.get("finding_counts"), label, "finding_counts")
    if findings["open"] != 0:
        errors.append(f"{label}: findings ledger has {findings['open']} unresolved findings")
    return errors


def _require_exact_head(data: dict, head: str, label: str, key: str) -> list[str]:
    errors: list[str] = []
    got = str(data.get(key) or "").strip().lower()
    if got != head:
        errors.append(
            f"{label}: {key} must equal exact HEAD {head}, got {got or '<missing>'}"
        )
    return errors

def validate_cli_feature(data: dict, head: str, repo_root: Path | None = None) -> list[str]:
    label = "CLI_FEATURE_SCENARIO_RECONCILIATION"
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append(f"{label}: schema_version must be 1")
    if data.get("gate") != label:
        errors.append(f"{label}: gate marker mismatch")
    if not _pass(data.get("final_status")):
        errors.append(f"{label}: final_status must be PASS")
    errors += _require_exact_head(data, head, label, "repo_head")
    errors += _require_exact_head(data, head, label, "end_head")
    if data.get("head_unchanged") is not True:
        errors.append(f"{label}: head_unchanged must be true")
    if not _pass(data.get("cleanup_status")):
        errors.append(f"{label}: cleanup_status must be PASS")
    if int(data.get("feature_inventory_total") or 0) <= 0:
        errors.append(f"{label}: feature_inventory_total must be > 0")
    product_source_head = str(data.get("product_source_head") or "").strip().lower()
    if not SHA_RE.fullmatch(product_source_head):
        errors.append(f"{label}: product_source_head must be a 40-character SHA")
    for key in ("server_source_head", "agent_source_head"):
        got = str(data.get(key) or "").strip().lower()
        if got != product_source_head:
            errors.append(f"{label}: {key} must equal product_source_head")
    if str(data.get("server_runtime_match") or "").strip().upper() != "EXACT":
        errors.append(f"{label}: server_runtime_match must be EXACT")
    if str(data.get("agent_runtime_match") or "").strip().upper() != "EXACT":
        errors.append(f"{label}: agent_runtime_match must be EXACT")
    if data.get("runtime_coverage_complete") is not True:
        errors.append(f"{label}: runtime_coverage_complete must be true")
    for key in (
        "evidence_ledger_schema",
        "report_consistency",
        "tty_tooling_status",
        "tty_persona_coverage",
        "github_report_status",
        "github_report_readback",
    ):
        if not _pass(data.get(key)):
            errors.append(f"{label}: {key} must be PASS")
    if data.get("summary_derived_from_ledger") is not True:
        errors.append(f"{label}: summary_derived_from_ledger must be true")
    if str(data.get("primary_user_evidence_mode") or "").strip().upper() != "PERSONA_LED_PUBLIC_UX":
        errors.append(f"{label}: primary_user_evidence_mode must be PERSONA_LED_PUBLIC_UX")
    if str(data.get("user_role_execution") or "").strip().upper() != "PASS":
        errors.append(f"{label}: user_role_execution must be PASS")
    if data.get("scripted_user_scenario_execution") is not False:
        errors.append(f"{label}: scripted_user_scenario_execution must be false")
    if str(data.get("automated_harness_role") or "").strip().upper() != "SUPPLEMENTAL_ONLY":
        errors.append(f"{label}: automated_harness_role must be SUPPLEMENTAL_ONLY")
    for coverage_key in (
        "direct_user_feature_coverage",
        "ai_assisted_feature_coverage",
        "direct_user_fcs_coverage",
        "ai_assisted_fcs_coverage",
    ):
        try:
            coverage = int(data.get(coverage_key))
        except (TypeError, ValueError):
            coverage = -1
        if coverage != 100:
            errors.append(f"{label}: {coverage_key} must be 100")
    if str(data.get("parallel_execution") or "").strip().upper() != "MAXIMUM_SAFE":
        errors.append(f"{label}: parallel_execution must be MAXIMUM_SAFE")
    try:
        parallel_lanes_started = int(data.get("parallel_lanes_started") or 0)
    except (TypeError, ValueError):
        parallel_lanes_started = 0
    if parallel_lanes_started <= 0:
        errors.append(f"{label}: parallel_lanes_started must be > 0")
    if data.get("serial_idle_with_runnable_work") is not False:
        errors.append(f"{label}: serial_idle_with_runnable_work must be false")
    counters = data.get("counters")
    if not isinstance(counters, dict):
        errors.append(f"{label}: counters must be an object")
    else:
        for key in CLI_ZERO_COUNTERS:
            if key not in counters or not _zero(counters.get(key)):
                errors.append(f"{label}: counters.{key} must be 0")
    if not str(data.get("evidence_root") or "").strip():
        errors.append(f"{label}: evidence_root is required")
    if repo_root is not None:
        manifest = repo_root / "release-manifest.json"
        if manifest.is_file():
            try:
                manifest_source = str(json.loads(manifest.read_text(encoding="utf-8")).get("source_head") or "").strip().lower()
            except Exception as exc:
                errors.append(f"{label}: unable to read release-manifest.json: {exc}")
            else:
                if manifest_source and manifest_source != product_source_head:
                    errors.append(f"{label}: product_source_head must equal release-manifest source_head {manifest_source}")
        errors += _validate_cli_ledgers(data, repo_root, label)
    return errors


def validate_full_user(data: dict, head: str, pass_name: str, repo_root: Path | None = None) -> list[str]:
    label = f"FULL_USER_E2E_{pass_name}"
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append(f"{label}: schema_version must be 1")
    if data.get("gate") != "FULL_USER_E2E":
        errors.append(f"{label}: gate must be FULL_USER_E2E")
    if data.get("pass_name") != pass_name:
        errors.append(f"{label}: pass_name mismatch")
    if not _pass(data.get("final_status")):
        errors.append(f"{label}: final_status must be PASS")
    errors += _require_exact_head(data, head, label, "git_head")
    errors += _require_exact_head(data, head, label, "end_head")
    product_source_head = str(data.get("product_source_head") or "").strip().lower()
    if not SHA_RE.fullmatch(product_source_head):
        errors.append(f"{label}: product_source_head must be a 40-character SHA")
    if data.get("summary_derived_from_ledger") is not True:
        errors.append(f"{label}: summary_derived_from_ledger must be true")
    if str(data.get("primary_user_evidence_mode") or "").strip().upper() != "PERSONA_LED_PUBLIC_UX":
        errors.append(f"{label}: primary_user_evidence_mode must be PERSONA_LED_PUBLIC_UX")
    if data.get("head_unchanged") is not True:
        errors.append(f"{label}: head_unchanged must be true")
    for key in FULL_PASS_FIELDS:
        if not _pass(data.get(key)):
            errors.append(f"{label}: {key} must be PASS")
    for key in FULL_ZERO_FIELDS:
        if key not in data or not _zero(data.get(key)):
            errors.append(f"{label}: {key} must be 0")
    if not str(data.get("evidence_root") or "").strip():
        errors.append(f"{label}: evidence_root is required")
    if repo_root is not None:
        manifest = repo_root / "release-manifest.json"
        if manifest.is_file():
            try:
                manifest_source = str(json.loads(manifest.read_text(encoding="utf-8")).get("source_head") or "").strip().lower()
            except Exception as exc:
                errors.append(f"{label}: unable to read release-manifest.json: {exc}")
            else:
                if manifest_source and manifest_source != product_source_head:
                    errors.append(f"{label}: product_source_head must equal release-manifest source_head {manifest_source}")
        errors += _validate_full_ledgers(data, repo_root, label)
    return errors


def default_paths(root: Path) -> dict[str, Path]:
    state = root / "e2e-reports" / "release-qualification"
    return {
        "cli-feature-scenario": Path(
            os.environ.get(
                "DRLINK_CLI_FEATURE_SCENARIO_EVIDENCE",
                state / "cli-feature-scenario.json",
            )
        ),
        "full-user-e2e-pass1": Path(
            os.environ.get(
                "DRLINK_FULL_USER_E2E_PASS1_EVIDENCE",
                state / "full-user-e2e-pass1.json",
            )
        ),
        "full-user-e2e-pass2": Path(
            os.environ.get(
                "DRLINK_FULL_USER_E2E_PASS2_EVIDENCE",
                state / "full-user-e2e-pass2.json",
            )
        ),
    }

def check_gate(root: Path, head: str, gate: str, path: Path) -> list[str]:
    data, errors = load_json(path, gate)
    if errors:
        return errors
    if gate == "cli-feature-scenario":
        return validate_cli_feature(data, head, root)
    if gate == "full-user-e2e-pass1":
        return validate_full_user(data, head, "PASS1", root)
    if gate == "full-user-e2e-pass2":
        return validate_full_user(data, head, "PASS2", root)
    return [f"unknown gate {gate}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--gate",
        choices=(
            "cli-feature-scenario",
            "full-user-e2e-pass1",
            "full-user-e2e-pass2",
            "full-user-e2e-all",
            "all",
        ),
        required=True,
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        head = git_head(root)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    paths = default_paths(root)
    gates = {
        "cli-feature-scenario": ("cli-feature-scenario",),
        "full-user-e2e-pass1": ("full-user-e2e-pass1",),
        "full-user-e2e-pass2": ("full-user-e2e-pass2",),
        "full-user-e2e-all": ("full-user-e2e-pass1", "full-user-e2e-pass2"),
        "all": (
            "cli-feature-scenario",
            "full-user-e2e-pass1",
            "full-user-e2e-pass2",
        ),
    }[args.gate]

    errors: list[str] = []
    for gate in gates:
        errors.extend(check_gate(root, head, gate, paths[gate]))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("PRE_RELEASE_EXHAUSTIVE_GATES=FAIL", file=sys.stderr)
        return 1

    print("PRE_RELEASE_EXHAUSTIVE_GATES=PASS")
    print(f"PRE_RELEASE_EXHAUSTIVE_HEAD={head}")
    for gate in gates:
        print(f"{gate.upper().replace('-', '_')}=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
