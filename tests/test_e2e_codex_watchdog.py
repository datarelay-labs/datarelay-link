import argparse
import csv
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/e2e_codex_watchdog.py"
spec = importlib.util.spec_from_file_location("e2e_codex_watchdog", MODULE_PATH)
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


def ledger(root, pending=1, state=None):
    with (root / "SCENARIO_TRACKER.tsv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, delimiter="\t",
                                fieldnames=["SCENARIO_ID", "WORK_STATE"])
        writer.writeheader()
        for i in range(116):
            status = ("PARTIAL" if i < pending
                      else "HISTORICAL_PASS_DO_NOT_REPEAT_WITHOUT_CAUSE")
            if i == 0 and state:
                status = state
            writer.writerow({"SCENARIO_ID": "T-%03d" % i, "WORK_STATE": status})


class FakeCommands:
    def __init__(self, screen="GPT-6-Luna medium · Pursuing goal (12h)",
                 program="codex", process=True):
        self.screen = screen
        self.program = program
        self.process = process
        self.calls = []

    def __call__(self, argv, timeout=8):
        self.calls.append(tuple(argv))
        if argv[:2] == ["tmux", "capture-pane"]:
            stdout = self.screen
        elif argv[:2] == ["tmux", "display-message"]:
            stdout = self.program + "\n"
        elif argv[0] == "ps":
            stdout = "/path/bin/codex -c memories.use_memories=false\n" if self.process else ""
        else:
            stdout = ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def sent(self):
        return sum(1 for c in self.calls if c[:2] == ("tmux", "send-keys"))


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        ledger(self.root)
        self.args = argparse.Namespace(
            mode="once", run_dir=str(self.root), tmux_target="codex:0.0",
            cooldown_seconds=900, max_attempts=2, allow_relaunch=False,
            cwd=str(self.root), codex_binary="/bin/true",
        )

    def test_active_actor_never_receives_inputs(self):
        cmd = FakeCommands()
        report = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(report["action"], "observe")
        self.assertEqual(report["counts"]["partial"], 1)
        self.assertEqual(cmd.sent(), 0)
        self.assertTrue((self.root / "e2e_watchdog_status.json").is_file())

    def test_resume_stalled_at_most_twice_per_unchanged_ledger(self):
        cmd = FakeCommands(screen="GPT-6-Luna medium · Goal stalled (/goal resume)")
        first = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(first["action"], "resume")
        self.assertTrue(first["executed"])
        self.assertEqual(first["attempts"], 1)
        self.assertEqual(cmd.sent(), 6)
        second = watchdog.tick(self.args, command=cmd, now=10030)
        self.assertEqual(second["action"], "cooldown")
        self.assertEqual(cmd.sent(), 6)
        third = watchdog.tick(self.args, command=cmd, now=11000)
        self.assertEqual(third["action"], "resume")
        self.assertEqual(cmd.sent(), 12)
        fourth = watchdog.tick(self.args, command=cmd, now=12000)
        self.assertEqual(fourth["action"], "hold")
        self.assertIn("resume budget", fourth["reason"])
        self.assertEqual(cmd.sent(), 12)
        ledger(self.root, pending=2)
        fifth = watchdog.tick(self.args, command=cmd, now=13000)
        self.assertEqual(fifth["action"], "resume")
        self.assertEqual(fifth["selected_scenario"], "T-001")
        self.assertEqual(fifth["target_attempts"], 1)

    def test_never_approves_or_unpauses(self):
        for screen in ["Reviewing approval request\nGoal stalled (/goal resume)",
                       "Goal paused (/goal resume)"]:
            cmd = FakeCommands(screen=screen)
            result = watchdog.tick(self.args, command=cmd, now=10000)
            self.assertEqual(result["action"], "hold")
            self.assertEqual(cmd.sent(), 0)
            (self.root / "e2e_watchdog_state.json").unlink()

    def test_terminal_results_never_retry(self):
        ledger(self.root, pending=0, state="SCENARIO_FAIL_REPRODUCED")
        cmd = FakeCommands(screen="Goal stalled (/goal resume)")
        result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(result["action"], "none")
        self.assertEqual(cmd.sent(), 0)

    def test_status_has_no_mutation_even_if_stalled(self):
        self.args.mode = "status"
        cmd = FakeCommands(screen="Goal stalled (/goal resume)")
        result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(result["action"], "resume")
        self.assertEqual(cmd.sent(), 0)
        self.assertFalse((self.root / "e2e_watchdog_state.json").exists())

    def test_missing_actor_never_starts_another_actor_by_default(self):
        cmd = FakeCommands(screen="Goal stalled (/goal resume)", process=False,
                           program="bash")
        result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(result["action"], "hold")
        self.assertEqual(cmd.sent(), 0)

    def test_relaunch_requires_exact_valid_session(self):
        cmd = FakeCommands(screen="Session ended", process=False, program="bash")
        self.args.allow_relaunch = True
        (self.root / "thread.id").write_text("not-a-uuid")
        result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertFalse(result.get("executed", True))
        self.assertIn("ValueError", result["error"])
        self.assertEqual(cmd.sent(), 0)

    def test_corrupt_ledger_is_rejected_without_any_send(self):
        with (self.root / "SCENARIO_TRACKER.tsv").open("a") as f:
            f.write("T-999\tPARTIAL\n")
        cmd = FakeCommands(screen="Goal stalled (/goal resume)")
        with self.assertRaisesRegex(ValueError, "116 unique"):
            watchdog.tick(self.args, command=cmd)
        self.assertEqual(cmd.sent(), 0)


if __name__ == "__main__":
    unittest.main()
