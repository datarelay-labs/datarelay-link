#!/usr/bin/env python3
"""Validate mandatory pre-release exhaustive human-test evidence on exact HEAD."""
from __future__ import annotations

import argparse
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
    "error_with_zero_rc_count",
    "scenario_blocked_count",
    "scenario_dead_end_count",
    "cleanup_residue_count",
    "runtime_mutation_attempt_count",
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
)

FULL_ZERO_FIELDS = (
    "commands_without_use_case",
    "public_commands_without_direct_use",
    "use_cases_without_ai_mirror",
    "oracle_only_commands_not_discoverable",
    "discoverability_defects",
    "doc_runtime_command_drift",
    "unexercised_public_commands",
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


def _require_exact_head(data: dict, head: str, label: str, key: str) -> list[str]:
    errors: list[str] = []
    got = str(data.get(key) or "").strip().lower()
    if got != head:
        errors.append(
            f"{label}: {key} must equal exact HEAD {head}, got {got or '<missing>'}"
        )
    return errors

def validate_cli_feature(data: dict, head: str) -> list[str]:
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
    counters = data.get("counters")
    if not isinstance(counters, dict):
        errors.append(f"{label}: counters must be an object")
    else:
        for key in CLI_ZERO_COUNTERS:
            if key not in counters or not _zero(counters.get(key)):
                errors.append(f"{label}: counters.{key} must be 0")
    if not str(data.get("evidence_root") or "").strip():
        errors.append(f"{label}: evidence_root is required")
    return errors


def validate_full_user(data: dict, head: str, pass_name: str) -> list[str]:
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
        return validate_cli_feature(data, head)
    if gate == "full-user-e2e-pass1":
        return validate_full_user(data, head, "PASS1")
    if gate == "full-user-e2e-pass2":
        return validate_full_user(data, head, "PASS2")
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
