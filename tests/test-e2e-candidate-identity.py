#!/usr/bin/env python3
"""No false stale-installed-HEAD or false exact-candidate PASS on E2E."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import e2e_candidate_identity as identity


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], text=True,
                       capture_output=True, check=True)
    return p.stdout.strip()


class CandidateFixture:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "E2E Test")
        git(self.root, "config", "user.email", "e2e@example.invalid")
        (self.root / "readme.txt").write_text("baseline\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "baseline")
        self.old = git(self.root, "rev-parse", "HEAD")
        (self.root / "readme.txt").write_text("real content\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "source")
        self.content = git(self.root, "rev-parse", "HEAD")
        self.make_provenance()
        return self

    def make_provenance(self, manifest_overrides=None, extra_file=None):
        data = {"source_head": self.content, "git_ref": self.content,
                "immutable_source_ref": self.content}
        data.update(manifest_overrides or {})
        (self.root / "release-manifest.json").write_text(json.dumps(data) + "\n")
        (self.root / "SHA256SUMS").write_text("fixture\n")
        if extra_file:
            file = self.root / extra_file
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("unsafe runtime addition\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "provenance")
        self.provenance = git(self.root, "rev-parse", "HEAD")

    def __exit__(self, *_):
        self.tmp.cleanup()


class ImmutableProvenanceE2ETests(unittest.TestCase):
    def test_lab_readiness_resolves_both_manifest_pin_styles(self):
        import e2e_lab_readiness as readiness
        with CandidateFixture() as f:
            self.assertEqual(readiness.resolve_installed_content_head(
                f.root, f.provenance, f.provenance), f.content)
            self.assertEqual(readiness.resolve_installed_content_head(
                f.root, f.provenance, f.content), f.content)
            self.assertEqual(readiness.resolve_installed_content_head(
                f.root, f.content, f.content), f.content)
            with self.assertRaises(ValueError):
                readiness.resolve_installed_content_head(f.root, f.provenance, f.old)

    def test_exact_and_content_parent_are_qualified(self):
        with CandidateFixture() as f:
            self.assertEqual(identity.bound_installed_head(f.root, f.provenance,
                                                             f.provenance), "exact")
            self.assertEqual(identity.bound_installed_head(f.root, f.provenance,
                                                             f.content), "provenance-parent")

    def test_all_ancestors_and_missing_commits_rejected(self):
        with CandidateFixture() as f:
            for candidate, installed in ((f.provenance, f.old),
                                         (f.provenance, "a" * 40),
                                         ("b" * 40, f.content)):
                with self.subTest(candidate=candidate, installed=installed):
                    with self.assertRaises(ValueError):
                        identity.bound_installed_head(f.root, candidate, installed)

    def test_changed_source_file_in_provenance_commit_rejected(self):
        with CandidateFixture() as f:
            git(f.root, "checkout", "-q", f.content)
            f.make_provenance(extra_file="lib/product_runtime.py")
            with self.assertRaisesRegex(ValueError, "product or unsupported"):
                identity.bound_installed_head(f.root, f.provenance, f.content)

    def test_manifest_parent_and_ref_mismatches_rejected(self):
        for field in ("source_head", "git_ref", "immutable_source_ref"):
            with self.subTest(field=field), CandidateFixture() as f:
                git(f.root, "checkout", "-q", f.content)
                f.make_provenance({field: f.old})
                with self.assertRaisesRegex(ValueError, "manifest"):
                    identity.bound_installed_head(f.root, f.provenance, f.content)

    def test_checkout_changes_cannot_forge_committed_manifest(self):
        with CandidateFixture() as f:
            (f.root / "release-manifest.json").write_text('{"source_head":"bad"}')
            self.assertEqual(identity.bound_installed_head(f.root, f.provenance,
                                                             f.content), "provenance-parent")

    def test_provenance_allowlist_matches_release_attestation(self):
        spec = importlib.util.spec_from_file_location(
            "release_attest_binding_test_only", ROOT / "scripts/check-release-attest-binding.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(identity.PROVENANCE_PATHS, module.PROVENANCE_PATHS)

    def test_ledger_record_accepts_verified_parent_without_waiving_evidence(self):
        import cli_only_e2e_inventory as ledger
        with CandidateFixture() as f:
            original = ledger.CANONICAL
            try:
                ledger.CANONICAL = f.root / "docs" / "FULL_USER_E2E_SCENARIOS.md"
                with tempfile.TemporaryDirectory() as t:
                    private = Path(t) / "private"
                    private.mkdir(mode=0o700)
                    ledger.initialize(private, original.read_text(), f.provenance)
                    (private / "actual-output.txt").write_text("unit fixture only\n")
                    kwargs = dict(result="PASS", target="isolated-unit-fixture",
                                  command="drlink show status",
                                  cleanup="NO_OWNED_RESOURCES",
                                  evidence="actual-output.txt", skip_reason="", notes="")
                    with self.assertRaises(ValueError):
                        ledger.record(private, "U-005", installed_head=f.old, **kwargs)
                    row = next(x for x in ledger.read_ledger(private)
                               if x["SCENARIO_ID"] == "U-005")
                    self.assertEqual(row["RESULT"], "NOT_RUN")
                    ledger.record(private, "U-005", installed_head=f.content, **kwargs)
                    row = next(x for x in ledger.read_ledger(private)
                               if x["SCENARIO_ID"] == "U-005")
                    self.assertEqual(row["RESULT"], "PASS")
                    self.assertEqual(row["SOURCE_HEAD"], f.provenance)
                    self.assertEqual(row["INSTALLED_HEAD"], f.content)
            finally:
                ledger.CANONICAL = original


if __name__ == "__main__":
    unittest.main()
