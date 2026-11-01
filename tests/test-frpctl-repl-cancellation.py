#!/usr/bin/env python3
"""A declined confirmation is not reported as a failed REPL command."""
from __future__ import annotations

import importlib.util
import io
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("frp_ctl_repl", ROOT / "lib/frp_ctl_repl.py")
REPL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPL)


class ReplCancellationTests(unittest.TestCase):
    def test_declined_confirmation_does_not_get_generic_failure_banner(self):
        editor = SimpleNamespace(prompt="drlink> ", _last_display_key=None, bind=lambda: None)
        lines = iter(["unset remote-service example", "exit"])
        cancelled = subprocess.CompletedProcess(
            ["drlink", "unset", "remote-service", "example"], 1,
            stdout="Cancelled.\nNo changes were applied.\n", stderr="",
        )
        output = io.StringIO()
        with patch.object(REPL, "LineEditor", return_value=editor), \
                patch("builtins.input", side_effect=lines), \
                patch.object(REPL, "_run_backend", return_value=cancelled), \
                redirect_stdout(output):
            self.assertEqual(REPL.run_repl("drlink", {"role": "server"}), 0)
        self.assertNotIn("Command failed with exit code", output.getvalue())

    def test_declined_confirmation_is_recognized(self):
        proc = subprocess.CompletedProcess(
            ["drlink", "unset", "remote-service", "example"], 1,
            stdout="Cancelled.\nNo changes were applied.\n", stderr="",
        )
        self.assertTrue(REPL._command_was_cancelled(proc))

    def test_other_nonzero_command_is_still_a_failure(self):
        proc = subprocess.CompletedProcess(
            ["drlink", "show", "unknown"], 2, stdout="Unknown command.\n", stderr="",
        )
        self.assertFalse(REPL._command_was_cancelled(proc))

    def test_cancel_marker_without_no_change_receipt_is_not_suppressed(self):
        proc = subprocess.CompletedProcess(
            ["drlink", "unset", "remote-service", "example"], 1,
            stdout="Cancelled.\n", stderr="",
        )
        self.assertFalse(REPL._command_was_cancelled(proc))


if __name__ == "__main__":
    unittest.main()
