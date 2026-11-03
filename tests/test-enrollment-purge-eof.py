#!/usr/bin/env python3
"""Regression: frp-enrollment-purge must cancel cleanly (no Python traceback) when stdin hits EOF or Ctrl-C at the
confirmation prompt (found by CLI100 E2E A-018 on candidate ef745e86: EOFError traceback, rc 1)."""
import importlib.machinery, importlib.util, io, os, sys, unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "tools", "frp-enrollment-purge")


def load():
    loader = importlib.machinery.SourceFileLoader("frp_enrollment_purge_under_test", PATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class ConfirmYesEof(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        os.environ.pop(self.mod.PURGE_ENV, None)

    def run_confirm(self, side_effect):
        with mock.patch.object(sys.stdin, "isatty", return_value=True), mock.patch("builtins.input", side_effect=side_effect):
            out = io.StringIO()
            with redirect_stdout(out):
                with self.assertRaises(SystemExit) as cm:
                    self.mod.confirm_yes("Proceed? [y/N]: ")
        return cm.exception.code

    def test_eof_is_a_clean_cancel(self):
        code = self.run_confirm(EOFError())
        self.assertIsInstance(code, str)
        self.assertIn("Cancelled", code)
        self.assertIn("No changes were applied", code)

    def test_keyboard_interrupt_is_a_clean_cancel(self):
        self.assertIn("Cancelled", self.run_confirm(KeyboardInterrupt()))

    def test_yes_and_no_still_work(self):
        with mock.patch.object(sys.stdin, "isatty", return_value=True):
            with mock.patch("builtins.input", return_value="y"):
                self.assertTrue(self.mod.confirm_yes("Proceed? [y/N]: "))
            with mock.patch("builtins.input", return_value="n"):
                self.assertFalse(self.mod.confirm_yes("Proceed? [y/N]: "))

    def test_non_tty_still_requires_explicit_env(self):
        with mock.patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(SystemExit) as cm:
                self.mod.confirm_yes("Proceed? [y/N]: ")
        self.assertIn("confirmation required", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main(verbosity=2)
