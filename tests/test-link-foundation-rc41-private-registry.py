#!/usr/bin/env python3
"""Public-safe tests for the limited RC41 private read-only workflow."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / ".github/workflows/foundation-rc41-private-read.yml"
PIN = ROOT / "tools/verify-link-foundation-rc41.py"
spec = importlib.util.spec_from_file_location("rc41_private_pin", PIN)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FoundationPrivatePackageReadContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = FLOW.read_text(encoding="utf-8")

    def test_only_trusted_same_repo_pr_branch_can_use_secret(self):
        self.assertIn("on:\n  pull_request:\n", self.source)
        self.assertNotIn("pull_request_target", self.source)
        self.assertNotIn("workflow_dispatch:", self.source)
        self.assertNotIn("push:", self.source)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            self.source,
        )
        self.assertIn(
            "github.event.pull_request.head.ref == 'feat/drl3-ux-saved-admission-pfci'",
            self.source,
        )
        self.assertIn("permissions:\n  contents: read", self.source)
        self.assertNotIn("packages: write", self.source)

    def test_secret_access_only_one_scoped_step_with_no_checkout(self):
        self.assertEqual(self.source.count("secrets.FOUNDATION_READ_TOKEN"), 1)
        self.assertIn("FOUNDATION_READ_TOKEN: ${{ secrets.FOUNDATION_READ_TOKEN }}", self.source)
        self.assertNotIn("actions/checkout", self.source)
        self.assertNotIn("actions/upload-artifact", self.source)
        self.assertNotIn("npm install", self.source)
        self.assertNotIn("npm publish", self.source)
        self.assertNotIn("npm ci", self.source)
        self.assertIn("npm pack", self.source)
        self.assertIn("--ignore-scripts", self.source)
        self.assertIn("trap 'rm -rf \"$scratch\"' EXIT", self.source)
        self.assertIn("umask 077", self.source)

    def test_exact_all_ten_independent_owner_sha256_pins(self):
        pinned = dict(re.findall(
            r"^\s+\[([a-z0-9-]+)\]=([0-9a-f]{64})$",
            self.source,
            flags=re.MULTILINE,
        ))
        self.assertEqual(pinned, gate.PACKAGE_SHA256)
        self.assertIn("0.1.0-rc.41", self.source)
        self.assertIn("FOUNDATION_RC41_PRIVATE_READ=PASS_10_OF_10", self.source)
        self.assertIn("PRIVATE_ARTIFACTS_PUBLISHED_TO_PUBLIC_ACTIONS=NO",
                      self.source)

    def test_runner_executes_registered_security_contract(self):
        runner = (ROOT / "tests/run-all.sh").read_text(encoding="utf-8")
        self.assertEqual(
            runner.count("python3 tests/test-link-foundation-rc41-private-registry.py -q"), 1
        )


if __name__ == "__main__":
    unittest.main()
