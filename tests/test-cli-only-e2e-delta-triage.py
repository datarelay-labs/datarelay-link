#!/usr/bin/env python3
"""Safety and provenance regressions for CLI-only incremental evidence triage."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import cli_only_e2e_inventory as inventory
import cli_only_e2e_delta_triage as triage


class DeltaTriageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "private"
        self.run.mkdir(mode=0o700)
        inventory.initialize(self.run, inventory.CANONICAL.read_text(), "a" * 40)
        self.source = "b" * 40
        self.receipt = self.run / "evidence" / "real.json"
        self.receipt.parent.mkdir(mode=0o700)
        self.receipt.write_text(json.dumps({
            "source_head": self.source,
            "status": "PASS_SCOPED",
            "scope": {"actual_payload": True, "samples": [0, 64]},
            "secret": "must-never-be-output",
        }))
        self.claim = {
            "scenario": "A-005",
            "subcase": "healthy-disable",
            "receipt": "evidence/real.json",
            "sha256": hashlib.sha256(self.receipt.read_bytes()).hexdigest(),
            "source_head": self.source,
            "source_pointer": "/source_head",
            "assertions": [
                {"pointer": "/status", "equals": "PASS_SCOPED"},
                {"pointer": "/scope/actual_payload", "equals": True},
                {"pointer": "/scope/samples/1", "equals": 64},
            ],
        }
        self.lanes = [
            {"id": "read-evidence", "scenario_ids": ["A-005"], "state": "READY",
             "resources": {"server-db": "read", "run-evidence": "read"}},
            {"id": "read-help", "scenario_ids": ["O-003"], "state": "READY",
             "resources": {"server-db": "read", "server-runtime": "read"}},
            {"id": "mutate-policy", "scenario_ids": ["A-005"], "state": "READY",
             "resources": {"server-db": "write", "server-runtime": "write"}},
            {"id": "public-positive", "scenario_ids": ["U-006"],
             "state": "HOLD_ENVIRONMENT", "reason": "shared forwarding missing",
             "resources": {"shared-network": "write"}},
        ]
        self.manifest = {"installed_source": self.source,
                         "claims": [self.claim], "lanes": self.lanes}

    def test_parallel_read_lanes_and_exclusive_writer(self):
        plan = triage.potential_batches(self.lanes, 3)
        self.assertEqual(plan, [["read-evidence", "read-help"], ["mutate-policy"]])
        self.assertNotIn("public-positive", str(plan))
        self.assertEqual(triage.potential_batches(self.lanes, 1),
                         [["read-evidence"], ["read-help"], ["mutate-policy"]])

    def test_real_scoped_evidence_does_not_promote_116_id(self):
        before = (self.run / "ledger/scenario-results.tsv").read_bytes()
        result = triage.analyse(self.run, self.manifest, 3)
        self.assertEqual(result["evidence_verified"], 1)
        self.assertEqual(result["evidence_errors"], 0)
        self.assertEqual(result["verified_subcase_facts"][0]["source_scope"],
                         "CURRENT_INSTALLED_SOURCE")
        self.assertEqual(result["full_scenario_PASS_promotions"], 0)
        self.assertEqual(result["new_real_cli_actions"], 0)
        self.assertEqual(result["new_product_mutations"], 0)
        self.assertEqual(before, (self.run / "ledger/scenario-results.tsv").read_bytes())

    def test_historical_source_and_unpinned_are_not_current(self):
        other = copy.deepcopy(self.manifest)
        other["installed_source"] = "c" * 40
        self.assertEqual(triage.analyse(self.run, other, 2)["verified_subcase_facts"][0]["source_scope"],
                         "HISTORICAL_SOURCE")
        unpinned = copy.deepcopy(self.manifest)
        unpinned["claims"][0].pop("source_pointer")
        self.assertEqual(triage.analyse(self.run, unpinned, 2)["verified_subcase_facts"][0]["source_scope"],
                         "UNPINNED_RECEIPT_SOURCE")

    def test_sha_mismatch_fails_closed_and_does_not_echo_secret(self):
        self.receipt.write_text(json.dumps({"secret": "must-never-be-output", "status": "FAIL"}))
        output = triage.analyse(self.run, self.manifest, 2)
        self.assertEqual(output["evidence_errors"], 1)
        self.assertNotIn("must-never-be-output", json.dumps(output))
        self.assertEqual(output["verified_subcase_facts"][0]["status"], "EVIDENCE_INVALID")

    def test_assertion_mismatch_is_evidence_error_not_product_failure(self):
        bad = copy.deepcopy(self.manifest)
        bad["claims"][0]["assertions"][0]["equals"] = "PASS_ALL"
        output = triage.analyse(self.run, bad, 2)
        self.assertEqual(output["evidence_errors"], 1)
        self.assertEqual(output["verified_subcase_facts"][0]["error_class"],
                         "EVIDENCE_VERIFICATION_FAILURE_NOT_PRODUCT_FAILURE")

    def test_bad_or_excluded_ids_are_not_allowed(self):
        for sid in ("U-007", "X-010", "BAD-000"):
            bad = copy.deepcopy(self.manifest)
            bad["claims"][0]["scenario"] = sid
            self.assertEqual(triage.analyse(self.run, bad, 3)["evidence_errors"], 1)
            bad = copy.deepcopy(self.manifest)
            bad["lanes"][0]["scenario_ids"] = [sid]
            with self.assertRaises(ValueError):
                triage.analyse(self.run, bad, 3)

    def test_symlink_escape_rejected(self):
        outside = Path(self.temp.name) / "external.json"
        outside.write_text("{}")
        (self.run / "evidence/link.json").symlink_to(outside)
        with self.assertRaises(ValueError):
            triage.evidence_path(self.run, "evidence/link.json")
        with self.assertRaises(ValueError):
            triage.evidence_path(self.run, "../external.json")
        with self.assertRaises(ValueError):
            triage.evidence_path(self.run, str(outside))

    def test_non_private_root_rejected(self):
        self.run.chmod(0o755)
        with self.assertRaises(ValueError):
            triage.root_dir(self.run)

    def test_duplicate_claim_and_invalid_lane_fail_before_parallel(self):
        bad = copy.deepcopy(self.manifest)
        bad["claims"].append(copy.deepcopy(self.claim))
        with self.assertRaises(ValueError):
            triage.analyse(self.run, bad, 3)
        bad = copy.deepcopy(self.manifest)
        bad["lanes"][0]["resources"]["run-evidence"] = "unsafe"
        with self.assertRaises(ValueError):
            triage.analyse(self.run, bad, 3)
        with self.assertRaises(ValueError):
            triage.analyse(self.run, self.manifest, 9)

    def test_cli_writes_private_new_report_once_only(self):
        man = self.run / "plan.json"
        man.write_text(json.dumps(self.manifest))
        argv = [sys.executable, "-B", str(ROOT / "tools/cli_only_e2e_delta_triage.py"),
                "--run-root", str(self.run), "--manifest", "plan.json",
                "--output", "reports/first.json", "--workers", "3"]
        first = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        self.assertEqual(first.returncode, 0, first.stderr)
        out = self.run / "reports/first.json"
        self.assertEqual(out.stat().st_mode & 0o077, 0)
        report = json.loads(out.read_text())
        self.assertEqual(report["full_scenario_PASS_promotions"], 0)
        second = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(report, json.loads(out.read_text()))


if __name__ == "__main__":
    unittest.main()
