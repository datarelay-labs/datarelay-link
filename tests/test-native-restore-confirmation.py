#!/usr/bin/env python3
"""Exercise the native restore approval boundary; every restore helper is a stub.

Only the current confirmation function and restore dispatcher arm are extracted.
No installed CLI, archive, backup tool, or real restore helper can run here.
"""
from pathlib import Path
import os
import pty
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeRestoreConfirmation(unittest.TestCase):
    def run_boundary(self, answer="", *, tty=False, preflight=0, bypass=False):
        source = (ROOT / "tools/frpctl").read_text()
        function = "frpctl_confirm_restore() {" + source.split(
            "frpctl_confirm_restore() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
        # Select the canonical dispatch arm, not the guided-menu workflow arm.
        dispatch = source.split('action="$(frpctl_json_get "$result" action)"', 1)[1]
        arm = dispatch.split("    restore_backup)\n", 1)[1].split(
            "    doctor)\n", 1)[0]
        self.assertTrue(arm.rstrip().endswith(";;"))
        with tempfile.TemporaryDirectory(prefix="drlink-restore-gate-") as tmp:
            marker = Path(tmp) / "calls"
            script = Path(tmp) / "boundary.sh"
            script.write_text("""#!/bin/bash
frpctl_restore_preflight() { printf 'preflight\\n' >> "$CALLS"; return "$PREFLIGHT_RC"; }
frpctl_require_server() { return 0; }
frpctl_load_passthrough() { :; }
frpctl_json_get() { printf '/fixture/not-an-archive'; }
frpctl_read() {
  printf '%s' "$1" >&2
  if [[ -n "${FRP_CTL_TEST_INPUT:-}" ]]; then printf y; return 0; fi
  local answer; IFS= read -r answer || :; printf '%s' "${answer:-$2}"
}
# This invoker records arguments; it never resolves or executes any tool.
frpctl_run() { printf 'mock-invocation:%s\\n' "$*" >> "$CALLS"; return 0; }
_frpctl_pt=()
if [[ "$BYPASS" == 1 ]]; then _frpctl_pt=(--yes); fi
""" + function + """
boundary_dispatch() {
  local result='fixture'
  _FRP_CTL_RC=0
  case restore_backup in
    restore_backup)
""" + arm + """  esac
}
boundary_dispatch
dispatch_rc=$?
if [[ "$dispatch_rc" != 0 ]]; then exit "$dispatch_rc"; fi
exit "$_FRP_CTL_RC"
""")
            env = dict(os.environ, CALLS=str(marker), PREFLIGHT_RC=str(preflight),
                       BYPASS="1" if bypass else "0")
            # Test-only automation knobs must not substitute for an actual TTY.
            if bypass:
                env.update(FRP_CTL_TEST_INPUT="y", FRP_RESTORE_YES="1",
                           DRLINK_CONFIRM="yes")
            if tty:
                master, slave = pty.openpty()
                try:
                    proc = subprocess.Popen(["bash", str(script)], stdin=slave,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            env=env, text=True)
                    os.close(slave)
                    slave = None
                    os.write(master, (answer + "\n").encode())
                    stdout, stderr = proc.communicate(timeout=10)
                    result = subprocess.CompletedProcess(proc.args, proc.returncode,
                                                         stdout, stderr)
                finally:
                    os.close(master)
                    if slave is not None:
                        os.close(slave)
            else:
                result = subprocess.run(["bash", str(script)], input=answer + "\n",
                                        env=env, capture_output=True, text=True, timeout=10)
            calls = marker.read_text().splitlines() if marker.exists() else []
            return result, calls

    def test_non_tty_refuses_before_preflight_or_mock_invocation(self):
        for bypass in (False, True):
            with self.subTest(automation_knobs=bypass):
                result, calls = self.run_boundary("y", bypass=bypass)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(calls, [])
                self.assertIn("confirmation", result.stdout + result.stderr)
                self.assertIn("No changes were applied", result.stdout + result.stderr)

    def test_actual_tty_yes_invokes_only_stub_once_after_preflight(self):
        result, calls = self.run_boundary("yes", tty=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls, ["preflight",
                                "mock-invocation:frp-restore --yes /fixture/not-an-archive"])

    def test_actual_tty_no_and_default_cancel_without_mock_invocation(self):
        for answer in ("n", ""):
            with self.subTest(answer=answer):
                result, calls = self.run_boundary(answer, tty=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(calls, ["preflight"])
                self.assertIn("Cancelled", result.stdout + result.stderr)

    def test_preflight_failures_preserve_exit_status_without_mock_invocation(self):
        for code in (1, 2):
            with self.subTest(code=code):
                result, calls = self.run_boundary("y", tty=True, preflight=code)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertEqual(calls, ["preflight"])

    def test_actual_tty_no_cannot_be_overridden_by_automation_knobs(self):
        result, calls = self.run_boundary("n", tty=True, bypass=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls, ["preflight"])
        self.assertIn("Cancelled", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
