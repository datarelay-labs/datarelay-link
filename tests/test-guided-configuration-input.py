#!/usr/bin/env python3
"""Configuration menu input reaches the canonical backend without shell evaluation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r'''
source "$1"
trap frpctl_input_cleanup EXIT
frpctl_header() { :; }
frpctl_dispatch() {
  python3 -c 'import json,sys; print("DISPATCH=" + json.dumps(sys.argv[1:]))' "$@"
  if [[ "$1 $2 ${3:-}" == "system apply configuration" && "${CHECK_CONFIRMATION:-}" == "1" ]]; then
    answer="$(frpctl_read 'Apply these changes? [y/N]: ' '')"
    printf 'CONFIRM=%s\n' "$answer"
  fi
}
frpctl_nav_loop client
'''


class GuidedConfigurationInputTests(unittest.TestCase):
    def run_menu(self, action, value, *, confirm=False, eof=False):
        with tempfile.TemporaryDirectory(prefix="drlink-config-menu-") as temp:
            canary = Path(temp, "unexpected-shell-execution")
            if value == "literal":
                value = str(Path(temp, "bundle with spaces $(touch " + str(canary) + ").yaml"))
            entries = ["3", str(action), value]
            if confirm:
                entries.append("y")
            if not eof:
                entries += ["5", "6"]
            env = dict(os.environ, FRP_CTL_SOURCED="1", FRP_CTL_CMD_NAME="drlink",
                       FRP_CTL_TEST_INPUT="\n".join(entries) + "\n", TMPDIR=temp,
                       CHECK_CONFIRMATION="1" if confirm else "0")
            proc = subprocess.run(["bash", "-c", SCRIPT, "config-menu-test", str(ROOT / "tools/frpctl")],
                                  env=env, text=True, capture_output=True, timeout=20)
            dispatched = [json.loads(line[len("DISPATCH="):])
                          for line in proc.stdout.splitlines() if line.startswith("DISPATCH=")]
            self.assertFalse(canary.exists(), proc.stdout + proc.stderr)
            return proc, dispatched, value

    def test_all_four_actions_collect_one_literal_path(self):
        commands = {1: ["test", "configuration"], 2: ["system", "diff", "configuration"],
                    3: ["system", "apply", "configuration"], 4: ["system", "export", "configuration"]}
        for action, command in commands.items():
            with self.subTest(action=action):
                proc, dispatched, value = self.run_menu(action, "literal")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(dispatched, [command + [value]])
                self.assertNotIn("Missing", proc.stdout + proc.stderr)

    def test_input_actions_preserve_pasted_yaml_selector(self):
        for action in (1, 2, 3):
            with self.subTest(action=action):
                proc, dispatched, _ = self.run_menu(action, "-")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(dispatched[0][-1], "-")

    def test_path_boundary_spaces_are_literal(self):
        proc, dispatched, _ = self.run_menu(4, "  output bundle.yaml  ")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(dispatched[0][-1], "  output bundle.yaml  ")

    def test_blank_path_cancels_without_dispatch(self):
        for action in (1, 2, 3, 4):
            with self.subTest(action=action):
                proc, dispatched, _ = self.run_menu(action, "  ")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(dispatched, [])
                self.assertIn("Cancelled.", proc.stdout)
                self.assertIn("No changes were applied.", proc.stdout)

    def test_apply_leaves_backend_confirmation_unconsumed(self):
        proc, dispatched, _ = self.run_menu(3, "bundle.yaml", confirm=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(dispatched, [["system", "apply", "configuration", "bundle.yaml"]])
        self.assertIn("CONFIRM=y", proc.stdout)

    def test_eof_before_path_does_not_dispatch(self):
        with tempfile.TemporaryDirectory(prefix="drlink-config-menu-eof-") as temp:
            env = dict(os.environ, FRP_CTL_SOURCED="1", FRP_CTL_CMD_NAME="drlink",
                       FRP_CTL_TEST_INPUT="3\n1\n", TMPDIR=temp)
            proc = subprocess.run(["bash", "-c", SCRIPT, "config-menu-test", str(ROOT / "tools/frpctl")],
                                  env=env, text=True, capture_output=True, timeout=20)
            self.assertNotIn("DISPATCH=", proc.stdout)
            self.assertNotIn("Missing configuration path", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
