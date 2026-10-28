#!/usr/bin/env python3
"""Hermetic regressions for the read-only DRLink worktree audit."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "drlink-worktree-audit.py"
spec = importlib.util.spec_from_file_location("drlink_worktree_audit", TOOL)
audit = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def run(*argv: str, cwd: Path) -> str:
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False, timeout=15)
    if proc.returncode:
        raise AssertionError(f"{argv} rc={proc.returncode}: {proc.stderr}")
    return proc.stdout.strip()


class WorktreeAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-audit-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        run("git", "init", "-q", "-b", "main", cwd=self.repo)
        run("git", "config", "user.email", "test@example.invalid", cwd=self.repo)
        run("git", "config", "user.name", "Worktree Audit Test", cwd=self.repo)
        (self.repo / ".gitignore").write_text("*.cache\n")
        (self.repo / "tracked.txt").write_text("original\n")
        run("git", "add", ".", cwd=self.repo)
        run("git", "commit", "-qm", "base", cwd=self.repo)
        self.clean = self.root / "checkout-clean"
        run("git", "worktree", "add", "-q", "--detach", str(self.clean), "main", cwd=self.repo)

    def report(self):
        return audit.inventory(str(self.repo), "main", None, False)

    def item(self, report, path):
        return next(e for e in report["worktrees"] if e["path"] == str(path))

    def test_parser_supports_branch_detached_and_locked(self):
        raw = "worktree /test/a\nHEAD 123\ndetached\n\nworktree /test/b\nHEAD 456\nbranch refs/heads/main\nlocked preserved\n"
        a, b = audit.parse_worktrees(raw)
        self.assertTrue(a["detached"])
        self.assertEqual(b["branch"], "main")
        self.assertEqual(b["locked"], "preserved")

    def test_clean_detached_is_only_review_not_auto_remove(self):
        report = self.report()
        self.assertEqual(report["base_head"], run("git", "rev-parse", "main", cwd=self.repo))
        e = self.item(report, self.clean)
        self.assertTrue(e["head_in_main"])
        self.assertEqual(e["tracked_modified_or_untracked"], 0)
        self.assertEqual(e["ignored_files"], 0)
        self.assertIn("PROCESS_VISIBILITY_UNKNOWN", e["protection_reasons"])
        self.assertNotEqual(e["disposition"], "SAFE_TO_DELETE")
        self.assertTrue(self.clean.is_dir())

    def test_dirty_tracked_and_untracked_are_preserved(self):
        (self.clean / "tracked.txt").write_text("modified\n")
        (self.clean / "new.txt").write_text("new\n")
        e = self.item(self.report(), self.clean)
        self.assertGreaterEqual(e["tracked_modified_or_untracked"], 2)
        self.assertEqual(e["disposition"], "PRESERVE_WIP")

    def test_ignored_data_are_preserved(self):
        (self.clean / "log.cache").write_text("sensitive test data\n")
        e = self.item(self.report(), self.clean)
        self.assertEqual(e["tracked_modified_or_untracked"], 0)
        self.assertEqual(e["ignored_files"], 1)
        self.assertEqual(e["disposition"], "PRESERVE_WIP")

    def test_unmerged_branch_not_mislabeled_merged(self):
        feature = self.root / "checkout-feature"
        run("git", "worktree", "add", "-q", "-b", "audit-feature", str(feature), "main", cwd=self.repo)
        (feature / "tracked.txt").write_text("unique work\n")
        run("git", "add", ".", cwd=feature)
        run("git", "commit", "-qm", "feature", cwd=feature)
        e = self.item(self.report(), feature)
        self.assertFalse(e["head_in_main"])
        self.assertIn("BRANCH_CHECKOUT", e["protection_reasons"])
        self.assertIn("HEAD_NOT_IN_MAIN", e["protection_reasons"])

    def test_index_references_preserve_even_clean_candidate(self):
        index = self.root / "workspace.md"
        index.write_text(f"- `{self.clean}`: frozen_evidence_source\n")
        e = self.item(audit.inventory(str(self.repo), "main", str(index), False), self.clean)
        self.assertIn("WORKSPACE_INDEX_REFERENCE", e["protection_reasons"])

    def test_missing_explicit_workspace_index_fails_closed(self):
        nonexistent = str(self.root / "missing-workspace-index.md")
        with self.assertRaises(OSError):
            audit.inventory(str(self.repo), "main", nonexistent, False)

    def test_report_written_private_and_no_git_mutation(self):
        before = run("git", "status", "--porcelain", cwd=self.repo)
        target = self.root / "private" / "audit.json"
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--repository", str(self.repo),
             "--skip-process-scan", "--output", str(target)],
            capture_output=True, text=True, check=False, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(target.read_text())["worktree_count"], 2)
        self.assertEqual(before, run("git", "status", "--porcelain", cwd=self.repo))
        self.assertTrue(self.clean.is_dir())


if __name__ == "__main__":
    unittest.main()
