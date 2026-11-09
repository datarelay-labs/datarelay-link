import argparse
import csv
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import unittest.mock

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
                 program="codex", process=True, resume_works=True,
                 clear_succeeds=True):
        self.screen = screen
        self.program = program
        self.process = process
        self.resume_works = resume_works
        self.clear_succeeds = clear_succeeds
        self.draft = ""
        self.calls = []

    def __call__(self, argv, timeout=8):
        self.calls.append(tuple(argv))
        if argv[:2] == ["tmux", "capture-pane"]:
            stdout = self.screen
        elif argv[:2] == ["tmux", "display-message"]:
            stdout = self.program + "\n"
        elif argv[0] == "ps":
            stdout = "/path/bin/codex -c memories.use_memories=false\n" if self.process else ""
        elif argv[:2] == ["tmux", "send-keys"]:
            if argv[-1] == "Escape" and "Task is still running" in self.screen:
                self.screen = ("Goal stalled (/goal resume)\n"
                               "› Ask Codex to do anything\n")
            elif argv[-1] == "C-c":
                if self.clear_succeeds:
                    self.draft = ""
                    self.screen = ("Goal stalled (/goal resume)\n"
                                   "› Ask Codex to do anything\n")
            elif "-l" in argv:
                self.draft = argv[-1]
            elif argv[-1] == "Enter" and self.draft == "/goal resume":
                if self.resume_works:
                    self.screen = "Goal active Objective: CLI-only E2E\nPursuing goal (1m)"
            elif argv[-1] == "Enter" and self.program == "bash" and " resume " in self.draft:
                self.program = "codex"
                self.process = True
                self.screen = ("Resume paused goal?\n"
                               "› 1. Resume goal\n"
                               "2. Leave paused\n"
                               "Goal stalled (/goal resume)")
            elif argv[-1] == "Enter" and self.program == "codex" and "Resume paused goal?" in self.screen:
                if self.resume_works:
                    self.screen = "Goal active Objective: CLI-only E2E\nPursuing goal (1m)"
            stdout = ""
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

    def test_latest_ui_footer_wins_over_old_stalled_footer(self):
        screen = ("Goal stalled (/goal resume)\nWorked for 5m\n"
                  "Goal active Objective: tests\n"
                  "GPT-6-Luna medium · Pursuing goal (2m)")
        self.assertEqual(watchdog.ui_status(screen), "active")

    def test_active_actor_never_receives_inputs(self):
        cmd = FakeCommands()
        report = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(report["action"], "observe")
        self.assertEqual(report["counts"]["partial"], 1)
        self.assertEqual(cmd.sent(), 0)
        self.assertTrue((self.root / "e2e_watchdog_status.json").is_file())

    def test_exit_chooser_safe_escape_then_resume(self):
        screen = ("Task is still running\nChoose what happens to the current task.\n"
                  "› 1. Cancel task\n2. Run in background\n3. Exit\n"
                  "enter select · esc back")
        cmd = FakeCommands(screen=screen)
        self.assertEqual(watchdog.ui_status(screen), "exit_menu")
        with unittest.mock.patch.object(watchdog.time, "sleep", return_value=None):
            report = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(report["action"], "exit_menu_recover")
        self.assertTrue(report["executed"])
        sends = [c[-1] for c in cmd.calls if c[:2] == ("tmux", "send-keys")]
        self.assertEqual(sends, ["Escape", "C-c", "/goal resume", "Enter"])
        self.assertNotIn("Tab", str(cmd.calls))
        self.assertEqual(watchdog.ui_status(cmd.screen), "active")

    def test_approval_and_unknown_exit_like_menu_fail_closed(self):
        screen = ("Task is still running\nChoose what happens to the current task.\n"
                  "› 1. Cancel task\n2. Run in background\n3. Exit\n"
                  "enter select · esc back\nReviewing approval request")
        cmd = FakeCommands(screen=screen)
        report = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(report["action"], "hold")
        self.assertEqual(cmd.sent(), 0)
        cmd.screen = "Task is still running\n1. Cancel task\n3. Exit"
        other = watchdog.tick(self.args, command=cmd, now=12000)
        self.assertEqual(other["action"], "hold")
        self.assertEqual(cmd.sent(), 0)

    def test_resume_stalled_at_most_twice_per_unchanged_ledger(self):
        cmd = FakeCommands(screen="GPT-6-Luna medium · Goal stalled (/goal resume)")
        first = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(first["action"], "resume")
        self.assertTrue(first["executed"])
        self.assertEqual(first["attempts"], 1)
        self.assertEqual(cmd.sent(), 3)
        self.assertEqual([c[-1] for c in cmd.calls if c[:2] == ("tmux", "send-keys")],
                         ["C-c", "/goal resume", "Enter"])
        self.assertNotIn("Tab", str(cmd.calls))
        # Simulate a later stall after the successful activation.
        cmd.screen = "Goal stalled (/goal resume)"
        second = watchdog.tick(self.args, command=cmd, now=10030)
        self.assertEqual(second["action"], "cooldown")
        self.assertEqual(cmd.sent(), 3)
        third = watchdog.tick(self.args, command=cmd, now=11000)
        self.assertEqual(third["action"], "resume")
        self.assertEqual(cmd.sent(), 6)
        cmd.screen = "Goal stalled (/goal resume)"
        fourth = watchdog.tick(self.args, command=cmd, now=12000)
        self.assertEqual(fourth["action"], "hold")
        self.assertIn("resume budget", fourth["reason"])
        self.assertEqual(cmd.sent(), 6)
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

    def test_unconfirmed_resume_is_not_reported_successful(self):
        cmd = FakeCommands(screen="Goal stalled (/goal resume)", resume_works=False)
        with unittest.mock.patch.object(watchdog.time, "sleep", return_value=None):
            result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(result["action"], "resume")
        self.assertFalse(result["executed"])
        self.assertIn("did not become active", result["error"])
        self.assertEqual(cmd.sent(), 3)

    def test_uncleared_multiline_composer_is_not_submitted(self):
        cmd = FakeCommands(screen="Goal stalled (/goal resume)",
                           clear_succeeds=False)
        result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertFalse(result["executed"])
        self.assertIn("draft not confirmed empty", result["error"])
        self.assertEqual(cmd.sent(), 1)

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
        (self.root / "codex_session_id.txt").write_text("not-a-uuid")
        result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertFalse(result.get("executed", True))
        self.assertIn("ValueError", result["error"])
        self.assertEqual(cmd.sent(), 0)

    def test_exact_session_relaunch_and_goal_menu(self):
        sid = "01a1b689-b0b8-7680-a91f-02d3e744cd42"
        (self.root / "codex_session_id.txt").write_text(sid + "\n")
        sessions = self.root / ".codex" / "sessions" / "2026" / "11" / "09"
        sessions.mkdir(parents=True)
        (sessions / ("rollout-" + sid + ".jsonl")).write_text("{}\n")
        cmd = FakeCommands(screen="aella@dev-drlink:~/datarelay-link-main$ ",
                           program="bash", process=False)
        self.args.allow_relaunch = True
        with unittest.mock.patch.object(watchdog.Path, "home", return_value=self.root), (
            unittest.mock.patch.object(watchdog.time, "sleep", return_value=None)
        ):
            result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(result["action"], "relaunch")
        self.assertTrue(result["executed"])
        self.assertEqual(result["restart_last_hour"], 1)
        self.assertEqual(cmd.sent(), 3)
        self.assertIn(" resume " + sid, str(cmd.calls))
        self.assertNotIn("Tab", str(cmd.calls))
        self.assertEqual(watchdog.ui_status(cmd.screen), "active")
        # No duplicate attempt when the process is still alive.
        second = watchdog.tick(self.args, command=cmd, now=10060)
        self.assertEqual(second["action"], "observe")
        self.assertEqual(cmd.sent(), 3)

    def test_relaunch_circuit_breaker(self):
        self.args.allow_relaunch = True
        with (self.root / "e2e_watchdog_state.json").open("w") as f:
            import json
            json.dump({"restart_history": [9000, 9200, 9700]}, f)
        cmd = FakeCommands(screen="aella@dev-drlink:~/x$",
                           program="bash", process=False)
        result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertEqual(result["action"], "hold")
        self.assertIn("circuit breaker", result["reason"])
        self.assertEqual(cmd.sent(), 0)

    def test_not_idle_shell_never_relaunch(self):
        self.args.allow_relaunch = True
        sid = "01a1b689-b0b8-7680-a91f-02d3e744cd42"
        (self.root / "codex_session_id.txt").write_text(sid + "\n")
        sessions = self.root / ".codex" / "sessions" / "2026" / "11" / "09"
        sessions.mkdir(parents=True)
        (sessions / ("rollout-" + sid + ".jsonl")).write_text("{}\n")
        cmd = FakeCommands(screen="some history without an actual shell prompt",
                           program="bash", process=False)
        with unittest.mock.patch.object(watchdog.Path, "home", return_value=self.root):
            result = watchdog.tick(self.args, command=cmd, now=10000)
        self.assertFalse(result.get("executed", True))
        self.assertIn("shell prompt not visible", result["error"])
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
