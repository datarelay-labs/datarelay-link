#!/usr/bin/env python3
"""Validate mandatory pre-release exhaustive human-test evidence on exact HEAD."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CLI_MIN_FEATURE_INVENTORY = 19

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
    "parser_only_path_count",
    "doc_only_path_count",
    "discovery_gap_count",
    "installer_guidance_mismatch_count",
    "terminology_drift_count",
    "procedure_drift_count",
    "structure_drift_count",
    "state_semantics_drift_count",
    "confirmation_metadata_drift_count",
    "destructive_confirmation_gap_count",
    "destructive_child_variant_metadata_gap_count",
    "error_with_zero_rc_count",
    "empty_state_silence_count",
    "next_action_stale_count",
    "active_guidance_noncanonical_count",
    "help_only_legacy_path_count",
    "public_noun_drift_count",
    "stale_regression_grammar_count",
    "active_installer_legacy_term_count",
    "doc_example_noncanonical_count",
    "role_surface_drift_count",
    "status_doc_runtime_mismatch_count",
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

CLI_REQUIRED_FEATURE_KEYS = (
    "SERVER_IDENTITY_SETTINGS",
    "ENROLLMENT",
    "MANAGED_HOST",
    "NETWORK_OBJECTS",
    "SERVICE_OBJECTS",
    "PERMISSION_OBJECTS",
    "REMOTE_SERVICE_FIXED_TCP",
    "REMOTE_ACCESS",
    "INTERNET_ACCESS",
    "AI_IDENTITY_ACCESS",
    "MCP_TLS_OAUTH",
    "CONFIGURATION_BUNDLE",
    "REVISION_ROLLBACK",
    "BACKUP_RESTORE",
    "DIAGNOSTICS_SUPPORT",
    "PRODUCT_ENGINE_UPDATE",
    "AGENT_LIFECYCLE",
    "VERSION_PROVENANCE",
    "UNINSTALL_REINSTALL",
)

CLI_REQUIRED_DOC_SURFACES = (
    "README.md",
    "README.ko.md",
    "docs/INSTALLATION.md",
    "docs/UPGRADE.md",
    "docs/REMOTE_ACCESS.md",
    "docs/AI_ACCESS_MCP.md",
    "docs/TROUBLESHOOTING.md",
    "docs/DEPLOYMENT_MODES.md",
    "docs/CLI_REFERENCE.md",
    "docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md",
    "generated:installer-completion",
    "generated:agent-recovery",
    "generated:doctor-diagnostics-remediation",
    "generated:update-recommendations",
    "generated:enrollment-output",
)

CLI_REQUIRED_HIDDEN_METRICS = (
    "PUBLIC_COMMAND_ENTRY_COUNT",
    "PUBLIC_ALIAS_PATH_COUNT",
    "ROOT_BYPASS_ALIAS_COUNT",
    "HIDDEN_COMMAND_ENTRY_COUNT",
    "HIDDEN_EXECUTABLE_PATH_COUNT",
    "LEGACY_COMPATIBILITY_PATH_COUNT",
    "PARSER_ONLY_PATH_COUNT",
    "DOC_ONLY_PATH_COUNT",
    "DUPLICATE_PUBLIC_PATH_COUNT",
)

CLI_HIDDEN_METRIC_TO_COUNTER = {
    "PUBLIC_ALIAS_PATH_COUNT": "public_alias_path_count",
    "ROOT_BYPASS_ALIAS_COUNT": "root_bypass_alias_count",
    "HIDDEN_EXECUTABLE_PATH_COUNT": "hidden_executable_path_count",
    "LEGACY_COMPATIBILITY_PATH_COUNT": "legacy_compatibility_path_count",
    "PARSER_ONLY_PATH_COUNT": "parser_only_path_count",
    "DOC_ONLY_PATH_COUNT": "doc_only_path_count",
    "DUPLICATE_PUBLIC_PATH_COUNT": "duplicate_public_path_count",
}

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
    doc_rows, doc_errors = _read_tsv(
        root / "ledger" / "docs-example-ledger.tsv",
        ("PATH", "CLASSIFICATION", "RESULT", "EVIDENCE"),
        label,
    )
    errors += doc_errors
    lane_rows, lane_errors = _read_tsv(
        root / "ledger" / "execution-lanes.tsv",
        ("LANE_ID", "KIND", "START_UTC", "END_UTC", "RESULT", "PREREQUISITE", "EVIDENCE"),
        label,
    )
    errors += lane_errors
    feature_rows, feature_errors = _read_tsv(
        root / "ledger" / "feature-ledger.tsv",
        (
            "FEATURE_ID", "FEATURE_KEY", "FEATURE", "PRODUCT_AUTHORITY", "SUPPORTED", "EXPECTED_ROLE",
            "EXPECTED_LIFECYCLE", "CANONICAL_CLI", "MENU_PATH",
            "INSTALLER_OR_GENERATED_PATH", "EXPECTED_SCENARIO", "DIRECT_USER_GOAL",
            "DIRECT_USER_RESULT", "AI_ASSISTED_USER_GOAL", "AI_ASSISTED_GUIDANCE",
            "AI_ASSISTED_RESULT",
        ),
        label,
    )
    errors += feature_errors
    cli_rows, cli_errors = _read_tsv(
        root / "ledger" / "cli-ledger.tsv",
        (
            "CLI_PATH", "ROLE", "DISCOVERED_BY", "DOCUMENTED", "PRODUCT_FEATURE",
            "RUNTIME_ONLY", "DUPLICATE_OF", "LEGACY_OR_COMPATIBILITY",
            "RUNTIME_OBSERVABLE", "MUTATION_PATH_AUDIT", "SCENARIO_ID", "EVIDENCE",
        ),
        label,
    )
    errors += cli_errors
    feature_cli_rows, feature_cli_errors = _read_tsv(
        root / "ledger" / "feature-cli-scenario.tsv",
        ("FEATURE_ID", "FEATURE", "CANONICAL_CLI", "EXPECTED_SCENARIO", "DIRECT_RESULT", "AI_RESULT"),
        label,
    )
    errors += feature_cli_errors
    ai_feature_rows, ai_feature_errors = _read_tsv(
        root / "ledger" / "ai-feature-parity.tsv",
        ("FEATURE_ID", "FEATURE", "AI_ASSISTED_RESULT"),
        label,
    )
    errors += ai_feature_errors
    ai_fcs_rows, ai_fcs_errors = _read_tsv(
        root / "ledger" / "ai-fcs-parity.tsv",
        ("FCS_ID", "AI_LANE", "RESULT", "EVIDENCE"),
        label,
    )
    errors += ai_fcs_errors
    hidden_rows, hidden_errors = _read_tsv(
        root / "ledger" / "hidden-alias-enumeration.tsv",
        ("METRIC", "COUNT", "EVIDENCE"),
        label,
    )
    errors += hidden_errors

    feature_ids = [str(row.get("FEATURE_ID") or "").strip() for row in feature_rows]
    feature_keys = [str(row.get("FEATURE_KEY") or "").strip().upper() for row in feature_rows]
    if not feature_ids:
        errors.append(f"{label}: feature-ledger.tsv must not be empty")
    if any(not item for item in feature_ids) or len(feature_ids) != len(set(feature_ids)):
        errors.append(f"{label}: feature-ledger.tsv FEATURE_ID values must be non-empty and unique")
    if any(not item for item in feature_keys) or len(feature_keys) != len(set(feature_keys)):
        errors.append(f"{label}: feature-ledger.tsv FEATURE_KEY values must be non-empty and unique")
    missing_feature_keys = [
        key for key in CLI_REQUIRED_FEATURE_KEYS if key not in set(feature_keys)
    ]
    if missing_feature_keys:
        errors.append(
            f"{label}: feature-ledger.tsv missing required FEATURE_KEY values "
            + ",".join(missing_feature_keys)
        )
    try:
        declared_feature_total = int(data.get("feature_inventory_total"))
    except (TypeError, ValueError):
        declared_feature_total = -1
    if declared_feature_total != len(feature_rows):
        errors.append(
            f"{label}: feature_inventory_total={declared_feature_total} but feature ledger={len(feature_rows)}"
        )
    known_feature_refs = {
        str(row.get("FEATURE_ID") or "").strip() for row in feature_rows
    } | {
        str(row.get("FEATURE_KEY") or "").strip().upper() for row in feature_rows
    } | {
        str(row.get("FEATURE") or "").strip() for row in feature_rows
    }
    supported_ids: set[str] = set()
    required_key_support = {
        str(row.get("FEATURE_KEY") or "").strip().upper(): str(row.get("SUPPORTED") or "").strip().upper()
        for row in feature_rows
    }
    for key in CLI_REQUIRED_FEATURE_KEYS:
        if required_key_support.get(key) != "YES":
            errors.append(f"{label}: required feature key {key} must have SUPPORTED=YES")
    feature_no_cli_gaps = 0
    features_without_ai_support = 0
    for row in feature_rows:
        fid = str(row.get("FEATURE_ID") or "").strip() or "<missing>"
        supported = str(row.get("SUPPORTED") or "").strip().upper()
        if supported not in {"YES", "NO"}:
            errors.append(f"{label}: feature {fid} SUPPORTED must be YES or NO")
            continue
        if supported != "YES":
            continue
        supported_ids.add(fid)
        if not _pass(row.get("DIRECT_USER_RESULT")):
            errors.append(f"{label}: feature {fid} DIRECT_USER_RESULT must be PASS")
        if not _pass(row.get("AI_ASSISTED_RESULT")):
            errors.append(f"{label}: feature {fid} AI_ASSISTED_RESULT must be PASS")
            features_without_ai_support += 1
        if not str(row.get("CANONICAL_CLI") or "").strip() and not str(
            row.get("INSTALLER_OR_GENERATED_PATH") or ""
        ).strip():
            feature_no_cli_gaps += 1
            errors.append(f"{label}: supported feature {fid} has no CLI or installer/generated path")

    feature_cli_ids = [str(row.get("FEATURE_ID") or "").strip() for row in feature_cli_rows]
    if set(feature_cli_ids) != set(feature_ids) or len(feature_cli_ids) != len(set(feature_cli_ids)):
        errors.append(f"{label}: feature-cli-scenario.tsv must contain each feature exactly once")
    for row in feature_cli_rows:
        fid = str(row.get("FEATURE_ID") or "").strip()
        if fid in supported_ids:
            if not _pass(row.get("DIRECT_RESULT")):
                errors.append(f"{label}: feature-cli {fid} DIRECT_RESULT must be PASS")
            if not _pass(row.get("AI_RESULT")):
                errors.append(f"{label}: feature-cli {fid} AI_RESULT must be PASS")

    ai_feature_ids = [str(row.get("FEATURE_ID") or "").strip() for row in ai_feature_rows]
    if set(ai_feature_ids) != set(feature_ids) or len(ai_feature_ids) != len(set(ai_feature_ids)):
        errors.append(f"{label}: ai-feature-parity.tsv must contain each feature exactly once")
    for row in ai_feature_rows:
        fid = str(row.get("FEATURE_ID") or "").strip()
        if fid in supported_ids and not _pass(row.get("AI_ASSISTED_RESULT")):
            errors.append(f"{label}: AI feature parity {fid} must be PASS")

    cli_paths = [str(row.get("CLI_PATH") or "").strip() for row in cli_rows]
    if not cli_paths:
        errors.append(f"{label}: cli-ledger.tsv must not be empty")
    duplicate_cli_paths = len(cli_paths) - len(set(cli_paths))
    if any(not path for path in cli_paths):
        errors.append(f"{label}: cli-ledger.tsv CLI_PATH must be non-empty")
    cli_without_product_feature = 0
    runtime_only_cli = 0
    legacy_cli = 0
    for row in cli_rows:
        path = str(row.get("CLI_PATH") or "").strip() or "<missing>"
        if str(row.get("DOCUMENTED") or "").strip().upper() != "YES":
            errors.append(f"{label}: CLI {path} DOCUMENTED must be YES")
        feature_ref = str(row.get("PRODUCT_FEATURE") or "").strip()
        if not feature_ref or feature_ref not in known_feature_refs:
            cli_without_product_feature += 1
            errors.append(f"{label}: CLI {path} PRODUCT_FEATURE must map to feature ledger")
        if str(row.get("RUNTIME_ONLY") or "").strip().upper() == "YES":
            runtime_only_cli += 1
            errors.append(f"{label}: CLI {path} must not be runtime-only")
        if str(row.get("LEGACY_OR_COMPATIBILITY") or "").strip().upper() == "YES":
            legacy_cli += 1
            errors.append(f"{label}: CLI {path} must not be legacy/compatibility")

    metric_names = [str(row.get("METRIC") or "").strip() for row in hidden_rows]
    if len(metric_names) != len(set(metric_names)):
        errors.append(f"{label}: hidden-alias-enumeration.tsv contains duplicate METRIC")
    metric_counts: dict[str, int] = {}
    for row in hidden_rows:
        metric = str(row.get("METRIC") or "").strip()
        try:
            count = int(row.get("COUNT"))
        except (TypeError, ValueError):
            errors.append(f"{label}: hidden metric {metric or '<missing>'} COUNT must be integer")
            continue
        if count < 0:
            errors.append(f"{label}: hidden metric {metric} COUNT must be non-negative")
            continue
        metric_counts[metric] = count
    missing_metrics = [m for m in CLI_REQUIRED_HIDDEN_METRICS if m not in metric_counts]
    if missing_metrics:
        errors.append(
            f"{label}: hidden-alias-enumeration.tsv missing metrics " + ",".join(missing_metrics)
        )
    if metric_counts.get("PUBLIC_COMMAND_ENTRY_COUNT") != len(cli_rows):
        errors.append(
            f"{label}: PUBLIC_COMMAND_ENTRY_COUNT={metric_counts.get('PUBLIC_COMMAND_ENTRY_COUNT')} "
            f"but cli ledger={len(cli_rows)}"
        )
    if metric_counts.get("DUPLICATE_PUBLIC_PATH_COUNT") != duplicate_cli_paths:
        errors.append(
            f"{label}: DUPLICATE_PUBLIC_PATH_COUNT must equal computed CLI duplicates {duplicate_cli_paths}"
        )
    if metric_counts.get("HIDDEN_COMMAND_ENTRY_COUNT", 0) != 0:
        errors.append(f"{label}: HIDDEN_COMMAND_ENTRY_COUNT must be 0")
    if metric_counts.get("LEGACY_COMPATIBILITY_PATH_COUNT") != legacy_cli:
        errors.append(
            f"{label}: LEGACY_COMPATIBILITY_PATH_COUNT must equal CLI ledger legacy count {legacy_cli}"
        )

    counters = data.get("counters") if isinstance(data.get("counters"), dict) else {}
    derived_zero_counts = {
        "feature_no_cli_gaps": feature_no_cli_gaps,
        "feature_without_discoverable_cli_count": feature_no_cli_gaps,
        "cli_without_product_feature_count": cli_without_product_feature,
        "runtime_only_cli_count": runtime_only_cli,
        "duplicate_public_path_count": duplicate_cli_paths,
        "legacy_compatibility_path_count": legacy_cli,
        "features_without_ai_support_count": features_without_ai_support,
    }
    for key, actual in derived_zero_counts.items():
        try:
            declared = int(counters.get(key))
        except (TypeError, ValueError):
            declared = -1
        if declared != actual:
            errors.append(f"{label}: counters.{key}={declared} but ledger={actual}")
    for metric, counter_key in CLI_HIDDEN_METRIC_TO_COUNTER.items():
        if metric not in metric_counts:
            continue
        try:
            declared = int(counters.get(counter_key))
        except (TypeError, ValueError):
            declared = -1
        if declared != metric_counts[metric]:
            errors.append(
                f"{label}: counters.{counter_key}={declared} but hidden ledger={metric_counts[metric]}"
            )

    expected_ids = {f"FCS-{idx:03d}" for idx in range(1, 16)}
    ids = [str(row.get("FCS_ID") or "").strip() for row in fcs_rows]
    if set(ids) != expected_ids or len(ids) != len(set(ids)):
        errors.append(f"{label}: fcs-results.tsv must contain each FCS-001..FCS-015 exactly once")
    ai_fcs_ids = [str(row.get("FCS_ID") or "").strip() for row in ai_fcs_rows]
    if set(ai_fcs_ids) != expected_ids or len(ai_fcs_ids) != len(set(ai_fcs_ids)):
        errors.append(f"{label}: ai-fcs-parity.tsv must contain each FCS-001..FCS-015 exactly once")
    for row in ai_fcs_rows:
        fid = str(row.get("FCS_ID") or "").strip() or "<missing>"
        if str(row.get("AI_LANE") or "").strip().upper() != "YES":
            errors.append(f"{label}: {fid} AI_LANE must be YES")
        if not _pass(row.get("RESULT")):
            errors.append(f"{label}: {fid} AI parity RESULT must be PASS")
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

    doc_paths = [str(row.get("PATH") or "").strip() for row in doc_rows]
    if not doc_paths:
        errors.append(f"{label}: docs-example-ledger.tsv must not be empty")
    if len(doc_paths) != len(set(doc_paths)):
        errors.append(f"{label}: docs-example-ledger.tsv contains duplicate PATH")
    missing_doc_surfaces = [
        item for item in CLI_REQUIRED_DOC_SURFACES if item not in set(doc_paths)
    ]
    if missing_doc_surfaces:
        errors.append(
            f"{label}: docs-example-ledger.tsv missing required surfaces "
            + ",".join(missing_doc_surfaces)
        )
    for row in doc_rows:
        if not _pass(row.get("RESULT")):
            errors.append(
                f"{label}: docs ledger {row.get('PATH') or '<missing>'} RESULT must be PASS"
            )

    lane_ids = [str(row.get("LANE_ID") or "").strip() for row in lane_rows]
    if not lane_ids:
        errors.append(f"{label}: execution-lanes.tsv must not be empty")
    if len(lane_ids) != len(set(lane_ids)):
        errors.append(f"{label}: execution-lanes.tsv contains duplicate LANE_ID")
    events: list[tuple[datetime, int]] = []
    valid_lane_count = 0
    for row in lane_rows:
        lane_id = str(row.get("LANE_ID") or "").strip() or "<missing>"
        if not _pass(row.get("RESULT")):
            errors.append(f"{label}: execution lane {lane_id} RESULT must be PASS")
        try:
            start = datetime.fromisoformat(str(row.get("START_UTC") or "").replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(row.get("END_UTC") or "").replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{label}: execution lane {lane_id} timestamps must be ISO-8601")
            continue
        if end < start:
            errors.append(f"{label}: execution lane {lane_id} END_UTC precedes START_UTC")
            continue
        valid_lane_count += 1
        events.append((start, 1))
        events.append((end, -1))
    if lane_rows and valid_lane_count == len(lane_rows):
        active = 0
        max_active = 0
        for _when, delta in sorted(events, key=lambda item: (item[0], item[1])):
            active += delta
            max_active = max(max_active, active)
        try:
            declared_lanes = int(data.get("parallel_lanes_started"))
        except (TypeError, ValueError):
            declared_lanes = -1
        if declared_lanes != len(lane_rows):
            errors.append(
                f"{label}: parallel_lanes_started={declared_lanes} but execution ledger={len(lane_rows)}"
            )
        try:
            declared_max = int(data.get("max_simultaneous_active_lanes"))
        except (TypeError, ValueError):
            declared_max = -1
        if declared_max != max_active:
            errors.append(
                f"{label}: max_simultaneous_active_lanes={declared_max} but execution ledger={max_active}"
            )
    return errors


def _validate_cli_catalog_binding(data: dict, repo_root: Path, label: str) -> list[str]:
    errors: list[str] = []
    catalog_path = repo_root / "lib" / "frp_cli_final_commands.json"
    if not catalog_path.is_file():
        return [f"{label}: missing exact-HEAD CLI catalog {catalog_path}"]
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{label}: unable to read exact-HEAD CLI catalog: {exc}"]
    if not isinstance(catalog, list):
        return [f"{label}: exact-HEAD CLI catalog must be a JSON array"]

    evidence_root = _resolve_evidence_root(repo_root, data)
    cli_rows, cli_errors = _read_tsv(
        evidence_root / "ledger" / "cli-ledger.tsv",
        (
            "CLI_PATH", "ROLE", "DISCOVERED_BY", "DOCUMENTED", "PRODUCT_FEATURE",
            "RUNTIME_ONLY", "DUPLICATE_OF", "LEGACY_OR_COMPATIBILITY",
            "RUNTIME_OBSERVABLE", "MUTATION_PATH_AUDIT", "SCENARIO_ID", "EVIDENCE",
        ),
        label,
    )
    errors += cli_errors
    hidden_rows, hidden_errors = _read_tsv(
        evidence_root / "ledger" / "hidden-alias-enumeration.tsv",
        ("METRIC", "COUNT", "EVIDENCE"),
        label,
    )
    errors += hidden_errors
    if cli_errors or hidden_errors:
        return errors

    public_catalog_rows = [row for row in catalog if not bool(row.get("hidden"))]
    catalog_paths = [" ".join(str(tok) for tok in (row.get("path") or [])) for row in public_catalog_rows]
    ledger_paths = [str(row.get("CLI_PATH") or "").strip() for row in cli_rows]
    if set(catalog_paths) != set(ledger_paths):
        missing = sorted(set(catalog_paths) - set(ledger_paths))
        extra = sorted(set(ledger_paths) - set(catalog_paths))
        if missing:
            errors.append(
                f"{label}: cli-ledger.tsv missing exact-HEAD catalog paths " + ",".join(missing[:20])
            )
        if extra:
            errors.append(
                f"{label}: cli-ledger.tsv has paths absent from exact-HEAD catalog " + ",".join(extra[:20])
            )

    metric_counts: dict[str, int] = {}
    for row in hidden_rows:
        metric = str(row.get("METRIC") or "").strip()
        try:
            metric_counts[metric] = int(row.get("COUNT"))
        except (TypeError, ValueError):
            continue

    actual_aliases = sum(len(row.get("aliases") or []) for row in catalog)
    actual_hidden = sum(bool(row.get("hidden")) for row in catalog)
    actual_duplicates = len(catalog_paths) - len(set(catalog_paths))
    actual = {
        "PUBLIC_COMMAND_ENTRY_COUNT": len(public_catalog_rows),
        "PUBLIC_ALIAS_PATH_COUNT": actual_aliases,
        "HIDDEN_COMMAND_ENTRY_COUNT": actual_hidden,
        "DUPLICATE_PUBLIC_PATH_COUNT": actual_duplicates,
    }
    for metric, value in actual.items():
        if metric_counts.get(metric) != value:
            errors.append(
                f"{label}: hidden ledger {metric}={metric_counts.get(metric)} "
                f"but exact-HEAD catalog={value}"
            )
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


def _validate_manifest_candidate_binding(repo_root: Path, candidate: str, label: str) -> list[str]:
    """Bind installed candidate identity to its documented content parent.

    A follow-on provenance commit may change generated artifacts only. Reuse
    the attestation gate's path/status rules; arbitrary ancestors and product
    changes cannot stand in for the exact runtime candidate.
    """
    manifest = repo_root / "release-manifest.json"
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return [f"{label}: release-manifest.json must be an object"]
        source = str(data.get("source_head") or "").strip().lower()
    except (OSError, ValueError) as exc:
        return [f"{label}: unable to read release-manifest.json: {exc}"]
    if not SHA_RE.fullmatch(source):
        return [f"{label}: release-manifest source_head must be a 40-character SHA"]
    if source == candidate:
        return []
    try:
        actual = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True, stderr=subprocess.PIPE).strip().lower()
        parent = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "--verify", f"{candidate}^1"], text=True, stderr=subprocess.PIPE).strip().lower()
        manifest_diff = subprocess.run(["git", "-C", str(repo_root), "diff", "--quiet", candidate, "--", "release-manifest.json"], capture_output=True, check=False)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"{label}: cannot prove manifest content-parent binding: {exc}"]
    if actual != candidate or source != parent:
        return [f"{label}: manifest source_head {source} must equal the exact candidate's first content parent ({parent}); checked-out HEAD={actual}, candidate={candidate}"]
    if manifest_diff.returncode != 0:
        return [f"{label}: content-parent binding requires the committed candidate manifest, without working-tree or staged changes"]

    module_name = "_drlink_exhaustive_provenance_binding"
    binding = sys.modules.get(module_name)
    if binding is None:
        spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name("check-release-attest-binding.py"))
        if spec is None or spec.loader is None:
            return [f"{label}: provenance binding rules unavailable"]
        binding = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = binding
        try:
            spec.loader.exec_module(binding)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            return [f"{label}: cannot load provenance binding rules: {exc}"]
    try:
        changed = binding._changed_paths(repo_root, parent, candidate)
    except binding.BindingError as exc:
        return [f"{label}: invalid provenance commit: {error}" for error in exc.errors]
    unexpected = sorted(set(changed) - binding.PROVENANCE_PATHS)
    if not changed or "release-manifest.json" not in changed or unexpected:
        return [f"{label}: candidate content-parent binding requires a generated-only provenance commit updating release-manifest.json; non-generated paths={unexpected}"]
    return []

def validate_cli_feature(data: dict, head: str, repo_root: Path | None = None) -> list[str]:
    label = "CLI_FEATURE_SCENARIO_RECONCILIATION"
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append(f"{label}: schema_version must be 1")
    if data.get("gate") != label:
        errors.append(f"{label}: gate marker mismatch")
    if not _pass(data.get("final_status")):
        errors.append(f"{label}: final_status must be PASS")
    contract_sha = str(data.get("test_contract_file_sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(contract_sha):
        errors.append(f"{label}: test_contract_file_sha256 must be a 64-character SHA256")
    if data.get("test_contract_dirty") is not False:
        errors.append(f"{label}: test_contract_dirty must be false")
    if not _pass(data.get("single_run_coordination")):
        errors.append(f"{label}: single_run_coordination must be PASS")
    errors += _require_exact_head(data, head, label, "repo_head")
    errors += _require_exact_head(data, head, label, "end_head")
    if data.get("head_unchanged") is not True:
        errors.append(f"{label}: head_unchanged must be true")
    if not _pass(data.get("cleanup_status")):
        errors.append(f"{label}: cleanup_status must be PASS")
    try:
        feature_inventory_total = int(data.get("feature_inventory_total") or 0)
    except (TypeError, ValueError):
        feature_inventory_total = 0
    if feature_inventory_total < CLI_MIN_FEATURE_INVENTORY:
        errors.append(
            f"{label}: feature_inventory_total must be >= {CLI_MIN_FEATURE_INVENTORY}"
        )
    product_source_head = str(data.get("product_source_head") or "").strip().lower()
    if not SHA_RE.fullmatch(product_source_head):
        errors.append(f"{label}: product_source_head must be a 40-character SHA")
    errors += _require_exact_head(data, head, label, "product_source_head")
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
    try:
        max_active_lanes = int(data.get("max_simultaneous_active_lanes") or 0)
    except (TypeError, ValueError):
        max_active_lanes = 0
    if max_active_lanes <= 0:
        errors.append(f"{label}: max_simultaneous_active_lanes must be > 0")
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
        contract_path = repo_root / "docs" / "CLI_FEATURE_SCENARIO_RECONCILIATION.md"
        if not contract_path.is_file():
            errors.append(f"{label}: canonical contract file is missing")
        else:
            actual_contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
            if contract_sha != actual_contract_sha:
                errors.append(
                    f"{label}: test_contract_file_sha256 must match canonical contract bytes"
                )
            dirty = subprocess.run(
                ["git", "-C", str(repo_root), "diff", "--quiet", "HEAD", "--", str(contract_path.relative_to(repo_root))],
                check=False,
            ).returncode
            if dirty != 0:
                errors.append(f"{label}: canonical contract differs from committed HEAD")
        errors += _validate_manifest_candidate_binding(repo_root, head, label)
        errors += _validate_cli_ledgers(data, repo_root, label)
        errors += _validate_cli_catalog_binding(data, repo_root, label)
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
    errors += _require_exact_head(data, head, label, "product_source_head")
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
        errors += _validate_manifest_candidate_binding(repo_root, head, label)
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
