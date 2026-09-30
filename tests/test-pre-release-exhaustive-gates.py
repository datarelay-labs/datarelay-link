#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
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
        "counters": {key: 0 for key in MOD.CLI_ZERO_COUNTERS},
        "evidence_root": "e2e-reports/cli-feature-scenario-test",
    }

def full_evidence(pass_name: str):
    data = {
        "schema_version": 1,
        "gate": "FULL_USER_E2E",
        "pass_name": pass_name,
        "final_status": "PASS",
        "git_head": HEAD,
        "end_head": HEAD,
        "head_unchanged": True,
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

    def test_cli_feature_stale_head_blocks(self):
        data = cli_evidence()
        data["end_head"] = "0" * 40
        errors = MOD.validate_cli_feature(data, HEAD)
        self.assertTrue(any("end_head" in item for item in errors))

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


if __name__ == "__main__":
    unittest.main()
