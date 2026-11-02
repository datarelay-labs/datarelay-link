#!/usr/bin/env python3
"""Public CLI human UX runner must never wait indefinitely on stdin or subprocesses."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/human-ux-e2e"))
from framework.session import CliSession
from framework.types import ExecutionContext


class CliSessionBoundedTests(unittest.TestCase):
    def test_noninteractive_runner_closes_stdin_and_sets_timeout(self):
        with tempfile.TemporaryDirectory(prefix="drlink-hux-io-") as root:
            session = CliSession(root=Path(root), context=ExecutionContext.DRLINK_SERVER)
            with mock.patch("framework.session.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "OK", "")) as run:
                result = session.run("show", "status")
            self.assertEqual(result.rc, 0)
            self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_confirmed_cli_answers_only_a_visible_tty_prompt(self):
        with tempfile.TemporaryDirectory(prefix="drlink-hux-pty-") as root:
            repo = Path(root)
            script = repo / "tools/drlink"
            script.parent.mkdir(parents=True)
            script.write_text(
                "#!/bin/sh\n"
                "printf 'Apply these changes? [y/N]'\n"
                "IFS= read -r answer\n"
                "[ \"$answer\" = y ] && echo APPLIED\n",
                encoding="utf-8",
            )
            script.chmod(0o700)
            session = CliSession(root=repo, context=ExecutionContext.DRLINK_SERVER)
            session.repo = repo
            result = session.run("system", "apply", "configuration", str(repo / "x"), confirm=True)
            self.assertEqual(result.rc, 0, result.combined)
            self.assertIn("APPLIED", result.combined)

    def test_timeout_is_failure_not_false_success(self):
        with tempfile.TemporaryDirectory(prefix="drlink-hux-timeout-") as root:
            session = CliSession(root=Path(root), context=ExecutionContext.DRLINK_SERVER)
            expired = subprocess.TimeoutExpired(
                cmd=["drlink", "set", "internet-access"], timeout=30,
                output=b"partial progress", stderr=b"waiting for input",
            )
            with mock.patch("framework.session.subprocess.run", side_effect=expired):
                result = session.run("set", "internet-access", "test", "disabled")
            self.assertEqual(result.rc, 124)
            self.assertIn("partial progress", result.stdout)
            self.assertIn("Authoritative state must be inspected", result.stderr)
            self.assertIn("waiting for input", result.stderr)


if __name__ == "__main__":
    unittest.main()
