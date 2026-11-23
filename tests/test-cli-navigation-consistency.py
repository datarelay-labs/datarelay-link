#!/usr/bin/env python3
"""U-013: consistent CLI navigation / help / destructive-label semantics.

Contract (general CLI UX standard):
  * `?`  shows context help for the current prompt and keeps the current step.
  * `0`  goes back to the previous menu (submenus) and never silently exits;
         at a top-level menu there is no previous menu, so the prompt stays and
         says which number exits.
  * "This command is destructive." is printed only for commands that really
    destroy or irreversibly remove state; every other state-changing command
    prints an exact "Impact:" description instead.
  * Error guidance is context aware: top menu names Exit, submenus name Back/0,
    Wizards name Cancel/0, and nothing tells an operator to "Choose Back/Cancel"
    at a prompt that has neither.
Uses isolated fixtures only; never mutates a live host.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_cli_catalog as catalog  # noqa: E402
import drlink_v24_wizard as wiz  # noqa: E402

CTL = ROOT / "tools" / "frpctl"

# Besides every `irreversible` command, these delete/overwrite state too:
# policy resets remove all rules; restore replaces the whole server state.
REAL_DESTRUCTIVE_EXTRA = {
    ("unset", "remote-access", "policy"),
    ("unset", "internet-access", "policy"),
    ("unset", "ai-access", "policy"),
    ("system", "restore"),
}


def _cmd(*path):
    for row in catalog.COMMANDS:
        if tuple(row["path"]) == tuple(path):
            return row
    raise AssertionError("missing command %r" % (path,))


class DestructiveLabel(unittest.TestCase):
    def test_setting_change_is_not_called_destructive(self):
        text = catalog.command_help(_cmd("set", "network-object"))
        self.assertNotIn("This command is destructive.", text)
        self.assertIn("Impact:", text)

    def test_only_real_destructive_commands_carry_label_others_get_impact(self):
        for row in catalog.COMMANDS:
            text = catalog.command_help(row)
            really = (row["risk"] == "irreversible"
                      or tuple(row["path"]) in REAL_DESTRUCTIVE_EXTRA)
            if really:
                self.assertIn("This command is destructive.", text, row["path"])
            else:
                self.assertNotIn("This command is destructive.", text, row["path"])
            if row["destructive"] and not really:
                self.assertIn("Impact:", text, row["path"])

    def test_real_destructive_commands_keep_label(self):
        for path in (("unset", "network-object"), ("unset", "managed-host"),
                     ("system", "uninstall"), ("unset", "ai-identity")):
            self.assertIn("This command is destructive.",
                          catalog.command_help(_cmd(*path)), path)

    def test_impact_text_is_specific_not_generic_boilerplate(self):
        impacts = set()
        for path in (("set", "network-object"), ("set", "internet-access"),
                     ("system", "restart"), ("system", "update", "product")):
            text = catalog.command_help(_cmd(*path))
            m = re.search(r"^Impact: (.+)$", text, re.M)
            self.assertIsNotNone(m, path)
            self.assertGreater(len(m.group(1)), 20, path)
            impacts.add(m.group(1))
        self.assertGreaterEqual(len(impacts), 3)

    def test_root_help_destructive_list_only_lists_real_destructive(self):
        text = catalog.root_help("server")
        m = re.search(r"Destructive:\n((?:  .*\n)+)", text)
        if not m:
            return
        body = m.group(1)
        self.assertNotIn("set network-object", body)
        self.assertNotIn("set remote-access", body)


class NavigationSemantics(unittest.TestCase):
    def test_classify_question_mark_is_help_everywhere(self):
        for key in ("client", "server", "server.system", "client.agent"):
            kind, _entry = catalog.navigation_classify(key, "?")
            self.assertEqual(kind, "help", key)

    def test_zero_is_back_in_submenus(self):
        for key in ("server.system", "client.agent", "server.hosts"):
            kind, entry = catalog.navigation_classify(key, "0")
            self.assertEqual(kind, "back", key)
            self.assertIsNotNone(entry, key)
            self.assertEqual(entry[3], "back", key)

    def test_zero_is_not_exit_at_top_menu(self):
        for key in ("client", "server", "both"):
            kind, entry = catalog.navigation_classify(key, "0")
            self.assertEqual(kind, "top", key)
            self.assertIsNone(entry, key)

    def test_digits_and_garbage(self):
        kind, entry = catalog.navigation_classify("server", "7")
        self.assertEqual((kind, entry[0]), ("select", "server_system"))
        self.assertEqual(catalog.navigation_classify("server", "99")[0], "invalid")
        self.assertEqual(catalog.navigation_classify("server", "abc")[0], "invalid")
        self.assertEqual(catalog.navigation_classify("server", "")[0], "invalid")

    def test_legacy_resolve_and_guided_action_unchanged(self):
        self.assertIsNone(catalog.navigation_resolve("server", "?"))
        self.assertIsNone(catalog.navigation_resolve("server", "0"))
        self.assertEqual(catalog.guided_menu_action("server", "9"), "exit")

    def test_menus_advertise_help_and_back(self):
        top = catalog.render_navigation_menu("server")
        sub = catalog.render_navigation_menu("server.system")
        self.assertIn("? Help", top)
        self.assertNotIn("0 Back", top)
        self.assertIn("? Help", sub)
        self.assertIn("0 Back", sub)

    def test_help_text_is_context_specific(self):
        top = catalog.navigation_help("server")
        sub = catalog.navigation_help("server.system")
        self.assertIn("?", top)
        self.assertIn("9", top)  # Exit number of the server top menu
        self.assertNotIn("0 returns", top.replace("0 does not", ""))
        self.assertIn("0", sub)
        self.assertIn("previous menu", sub)
        self.assertIn("Uninstall Data Relay Link", sub)

    def test_invalid_message_is_context_aware(self):
        top = catalog.navigation_invalid_message("server", "zzz")
        self.assertIn("1-9", top)
        self.assertIn("Exit", top)
        self.assertNotIn("Back/Cancel", top)
        sub = catalog.navigation_invalid_message("server.system", "zzz")
        self.assertIn("1-10", sub)
        self.assertIn("0", sub)
        self.assertNotIn("Back/Cancel", sub)

    def test_command_paste_message_is_context_aware(self):
        top = catalog.navigation_invalid_message("server", "show status")
        self.assertIn("looks like a DRLink command", top)
        self.assertIn("Exit", top)
        self.assertNotIn("Back/Cancel", top)
        sub = catalog.navigation_invalid_message("server.system", "show status")
        self.assertIn("0", sub)
        self.assertNotIn("Back/Cancel", sub)


class WizardSemantics(unittest.TestCase):
    def _io(self, answers):
        out = []
        return wiz.ScriptedIO(answers, out=out), out

    def test_choice_question_mark_helps_and_stays(self):
        io, out = self._io(["?", "2"])
        picked = wiz._ask_choice(io, "Pick one", ["alpha", "beta"])
        self.assertEqual(picked, "beta")
        text = "".join(out)
        self.assertIn("Wizard help", text)
        self.assertEqual(len(re.findall(r"^\s*1\) alpha$", text, re.M)), 2, text)  # menu re-rendered, step kept

    def test_choice_zero_and_c_cancel(self):
        for token in ("0", "c", "cancel"):
            io, out = self._io([token])
            with self.assertRaises(wiz.WizardCancelled):
                wiz._ask_choice(io, "Pick one", ["alpha", "beta"])

    def test_choice_menu_advertises_help_and_cancel(self):
        io, out = self._io(["1"])
        wiz._ask_choice(io, "Pick one", ["alpha", "beta"])
        text = "".join(out)
        self.assertIn("? Help", text)
        self.assertIn("0) Cancel", text)

    def test_text_question_mark_helps_and_stays(self):
        io, out = self._io(["?", "value1"])
        got = wiz._ask_text(io, "Name", help_text="Use letters and digits only.")
        self.assertEqual(got, "value1")
        text = "".join(out)
        self.assertIn("Use letters and digits only.", text)
        self.assertEqual(text.count("Name: "), 2)

    def test_text_question_mark_without_custom_help_still_helps(self):
        io, out = self._io(["?", "x"])
        wiz._ask_text(io, "Name")
        self.assertIn("Wizard help", "".join(out))

    def test_text_zero_cancels_only_when_not_a_valid_value_context(self):
        io, _ = self._io(["0"])
        with self.assertRaises(wiz.WizardCancelled):
            wiz._ask_text(io, "Name")

    def test_yes_no_question_mark_helps_and_stays(self):
        io, out = self._io(["?", "y"])
        self.assertTrue(wiz._ask_yes_no(io, "Apply"))
        self.assertIn("Wizard help", "".join(out))

    def test_yes_no_zero_is_cancel_not_no(self):
        io, _ = self._io(["0"])
        with self.assertRaises(wiz.WizardCancelled):
            wiz._ask_yes_no(io, "Apply")

    def test_command_paste_message_does_not_name_missing_back(self):
        io, out = self._io(["show status", "1"])
        wiz._ask_choice(io, "Pick one", ["alpha", "beta"])
        text = "".join(out)
        self.assertIn("looks like a DRLink command", text)
        self.assertNotIn("Choose Back/Cancel", text)
        self.assertIn("Cancel", text)
        self.assertIn("No changes were applied.", text)


def _make_trees(base: Path):
    client = base / "client"
    server = base / "server"
    (client / "etc/frp").mkdir(parents=True)
    (client / "etc/drlink").mkdir(parents=True)
    (client / "etc/frp/client-state.json").write_text(
        '{"schema_version":1,"allocator_url":"https://127.0.0.1:9/enroll",'
        '"frp_server":"203.0.113.10","frp_server_port":443,"hostname":"ctl-client",'
        '"machine_id":"00112233445566778899aabbccddeeff","host_id":"ctl-client-00112233",'
        '"services":{}}\n')
    (client / "etc/drlink/version").write_text("PROJECT_VERSION=1.4.0\nFRP_VERSION=0.71.0\n")
    (server / "etc/drlink").mkdir(parents=True)
    (server / "var/lib/drlink").mkdir(parents=True)
    (server / "etc/drlink/config.json").write_text(
        '{"public_ip":"203.0.113.10","public_host":"203.0.113.10","control_port":443,'
        '"port_start":6000,"port_end":6098,"listen_port":6099,'
        '"allocator_public_url":"https://203.0.113.10:6099/enroll",'
        '"registry_file":"/var/lib/drlink/registry.json"}\n')
    (server / "var/lib/drlink/registry.json").write_text(
        '{"schema_version":2,"reserved":[],"clients":{}}\n')
    (server / "etc/drlink/version").write_text("PROJECT_VERSION=1.4.0\nFRP_VERSION=0.71.0\n")
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from drlink_control_plane import ControlPlane;"
        "p = ControlPlane(sys.argv[2]); p.close()"
    )
    subprocess.run([sys.executable, "-c", code, str(ROOT / "lib"), str(server)], check=True)
    return client, server


def _run_repl(tree: Path, lines, home: Path):
    env = dict(os.environ)
    for key in [k for k in env if k.startswith("FRP_CTL_TEST") or k.startswith("FRP_CLIENT_TEST")]:
        env.pop(key)
    env.update({
        "FRP_CTL_FORCE_DRLINK": "1",
        "FRP_CTL_CMD_NAME": "drlink",
        "FRP_CTL_BIN_DIR": str(ROOT / "tools"),
        "FRP_CLIENT_LIB": str(ROOT / "lib/frp-client-common.sh"),
        "FRP_SKIP_SYSTEMD": "1",
        "HOME": str(home),
        "FRP_CTL_TEST_ROOT": str(tree),
        "FRP_DEPLOY_TEST_ROOT": str(tree),
        "FRP_CLIENT_TEST_ROOT": str(tree),
        "FRP_CTL_TEST_INPUT": "\n".join(lines) + "\n",
        "FRP_CTL_DRY_RUN": "1",
    })
    proc = subprocess.run([str(CTL)], env=env, capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


class FrpctlMenuBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        (base / "home").mkdir()
        cls.home = base / "home"
        cls.client, cls.server = _make_trees(base)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_top_menu_question_mark_shows_help_and_stays(self):
        rc, out = _run_repl(self.server, ["menu", "?", "9", "exit"], self.home)
        self.assertIn("Menu help", out)
        self.assertEqual(len(re.findall(r"^1\) Managed Hosts$", out, re.M)), 2, out)  # menu re-rendered (help text lists items indented, not counted)
        self.assertNotIn("ERROR: select a valid menu number", out)

    def test_top_menu_zero_stays_and_names_exit(self):
        rc, out = _run_repl(self.server, ["menu", "0", "9", "exit"], self.home)
        self.assertIn("top menu", out.lower())
        self.assertRegex(out, r"(?i)enter 9 to exit")
        self.assertEqual(out.count("1) Managed Hosts"), 2, out)

    def test_submenu_zero_goes_back_to_previous_menu(self):
        rc, out = _run_repl(self.server, ["menu", "7", "0", "9", "exit"], self.home)
        # System submenu rendered once, then the top menu again after `0`.
        self.assertEqual(out.count("Uninstall Data Relay Link"), 1, out)
        self.assertEqual(out.count("1) Managed Hosts"), 2, out)

    def test_submenu_question_mark_stays_in_submenu(self):
        rc, out = _run_repl(self.server, ["menu", "7", "?", "0", "9", "exit"], self.home)
        self.assertIn("Menu help", out)
        self.assertEqual(out.count("Uninstall Data Relay Link"), 3, out)  # menu+help+menu

    def test_submenu_error_guidance_names_zero_not_back_cancel(self):
        rc, out = _run_repl(self.server, ["menu", "7", "show status", "0", "9", "exit"], self.home)
        self.assertIn("looks like a DRLink command", out)
        self.assertNotIn("Choose Back/Cancel", out)
        self.assertRegex(out, r"(?i)0 .*previous menu|previous menu.*0")

    def test_top_error_guidance_names_exit(self):
        rc, out = _run_repl(self.server, ["menu", "zzz", "9", "exit"], self.home)
        self.assertRegex(out, r"(?i)select 1-9")
        self.assertIn("Exit", out)

    def test_client_menu_uses_same_semantics(self):
        rc, out = _run_repl(self.client, ["menu", "2", "0", "?", "6", "exit"], self.home)
        self.assertIn("Menu help", out)
        self.assertEqual(len(re.findall(r"^1\) Remote Services$", out, re.M)), 3, out)  # initial, after 0 (back), after ? (stay)

    def test_text_step_help_names_current_step_and_zero_cancels(self):
        rc, out = _run_repl(self.server, ["menu", "1", "3", "?", "0", "5", "9", "exit"], self.home)
        self.assertIn("Input help", out)
        self.assertIn("Current step: Managed Host name", out)
        self.assertIn("stay on this step", out.lower())
        self.assertIn("Cancelled.", out)
        self.assertNotIn("ERROR", out)

    def test_end_of_input_leaves_menu_instead_of_looping(self):
        # No exit command: stdin ends inside a submenu. Must terminate, not spin.
        rc, out = _run_repl(self.server, ["menu", "1"], self.home)
        self.assertLess(out.count("ERROR"), 3, out[-800:])

    def test_scripted_end_of_input_still_leaves_menu_cleanly(self):
        # Input that simply ends (user finished typing) is a normal way to leave.
        rc, out = _run_repl(self.server, ["menu", "1"], self.home)
        self.assertEqual(rc, 0, out[-800:])
        self.assertIn("End of input. Leaving the menu.", out)

    def test_non_tty_menu_without_input_fails_closed(self):
        # stdin is not a TTY and no scripted input exists: nothing can be answered, so a
        # guided/menu command must fail (rc != 0) instead of reporting a clean exit.
        env = dict(os.environ)
        for key in [k for k in env if k.startswith("FRP_CTL_TEST") or k.startswith("FRP_CLIENT_TEST")]:
            env.pop(key)
        env.update({
            "FRP_CTL_FORCE_DRLINK": "1", "FRP_CTL_CMD_NAME": "drlink",
            "FRP_CTL_BIN_DIR": str(ROOT / "tools"),
            "FRP_CLIENT_LIB": str(ROOT / "lib/frp-client-common.sh"),
            "FRP_SKIP_SYSTEMD": "1", "HOME": str(self.home),
            "FRP_CTL_TEST_ROOT": str(self.server), "FRP_DEPLOY_TEST_ROOT": str(self.server),
            "FRP_CLIENT_TEST_ROOT": str(self.server), "FRP_CTL_DRY_RUN": "1",
        })
        for args in (["menu"], ["set", "enrollment", "zero-touch"]):
            proc = subprocess.run([str(CTL)] + args, env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=120)
            out = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0, "%s: %s" % (args, out[-600:]))
            self.assertIn("no TTY for interactive menu", out)
            self.assertNotIn("End of input. Leaving the menu.", out)

    def test_end_of_input_is_announced_once_and_is_a_normal_exit(self):
        # Ctrl-D / exhausted input at a menu is a normal way to leave (like a shell):
        # say so once, exit 0, never exit silently with a failure status.
        for lines in (["menu"], ["menu", "1"], ["menu", "1", "?"]):
            with self.subTest(lines=lines):
                rc, out = _run_repl(self.server, lines, self.home)
                self.assertEqual(out.count("End of input. Leaving the menu."), 1, out[-800:])
                self.assertEqual(rc, 0, out[-800:])

    def test_no_legacy_valid_menu_number_wording_in_code_paths(self):
        text = (ROOT / "tools/frpctl").read_text(encoding="utf-8")
        self.assertNotIn("select a valid menu number", text)



def _source_frpctl(script: str, lines):
    """Run a snippet with tools/frpctl sourced (functions only) and scripted input."""
    env = dict(os.environ)
    for key in [k for k in env if k.startswith("FRP_CTL_TEST") or k.startswith("FRP_CLIENT_TEST")]:
        env.pop(key)
    env.update({
        "FRP_CTL_SOURCED": "1",
        "FRP_CTL_CMD_NAME": "drlink",
        "FRP_CTL_BIN_DIR": str(ROOT / "tools"),
        "FRP_CTL_TEST_INPUT": "\n".join(lines) + "\n",
    })
    body = 'source "$1"\nfrpctl_invoke() { echo "INVOKED $*"; }\n' + script
    # The scripted-input spool is keyed by PPID (this python process), so give every
    # case its own TMPDIR or a later case would resume a previous case's read offset.
    with tempfile.TemporaryDirectory(prefix="u013-wiz-") as tmp:
        env["TMPDIR"] = tmp
        proc = subprocess.run(["bash", "-c", body, "u013", str(CTL)], env=env,
                              capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


class FrpctlWizardPrompts(unittest.TestCase):
    """Bash Wizards (guided create flows) follow the same ?/0 contract as the menus."""

    FLOW = "frpctl_guided_service_profile_create demo"

    def test_choice_step_question_mark_shows_step_help_and_stays(self):
        rc, out = _source_frpctl(self.FLOW, ["?", "0"])
        self.assertIn("Input help", out)
        self.assertIn("Current step: Preset", out)
        self.assertEqual(out.count("Select [1]"), 0, out)  # label is the step name, not the raw prompt
        self.assertIn("Cancelled.", out)
        self.assertNotIn("INVOKED", out)
        self.assertEqual(rc, 0, out)

    def test_choice_step_rejects_unknown_input_instead_of_silent_default(self):
        rc, out = _source_frpctl(self.FLOW, ["9", "0"])
        self.assertIn("ERROR: select 1-4 (? for help, 0 to cancel)", out)
        self.assertNotIn("INVOKED", out)
        self.assertNotIn("Review", out)  # never proceeded with an invented preset
        self.assertEqual(rc, 0, out)

    def test_text_step_help_names_the_step_and_zero_cancels(self):
        rc, out = _source_frpctl(self.FLOW, ["1", "?", "0"])
        self.assertIn("Current step: Target host", out)
        self.assertIn("Cancelled.", out)
        self.assertNotIn("INVOKED", out)
        self.assertEqual(rc, 0, out)

    def test_confirm_step_help_explains_yes_no_and_zero_cancels(self):
        rc, out = _source_frpctl(self.FLOW, ["1", "", "22", "?", "0"])
        self.assertIn("Current step: Create profile?", out)
        self.assertIn("y or n", out)
        self.assertIn("Cancelled.", out)
        self.assertNotIn("INVOKED", out)
        self.assertEqual(rc, 0, out)

    def test_cancel_nested_service_id_does_not_append_previous_service(self):
        # Repro from PR #294 review: Add SSH, cancel the next HTTP service ID.
        # The previous SSH JSON must not be appended a second time.
        script = """
_FRP_ZT_CLIENT_NAME=test-host
_FRP_ZT_PLATFORM=linux
frpctl_zt_invoke_create_client() {
    if [[ "$1" == "--one-line" && "$2" == "--services-file" ]]; then
        printf 'SERVICES_JSON '
        cat "$3"
    else
        echo "INVOKED_INVALID_ARGS"
    fi
}
frpctl_zt_run_services
"""
        rc, out = _source_frpctl(script, ["1", "", "", "", "2", "0", "5"])
        self.assertEqual(rc, 0, out)
        match = re.search(r"^SERVICES_JSON (.+)$", out, re.M)
        self.assertIsNotNone(match, out)
        import json
        items = json.loads(match.group(1))
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["id"], "ssh")
        self.assertNotIn("INVOKED_INVALID_ARGS", out)

    def test_cancel_nested_service_host_or_port_does_not_append_stale_service(self):
        for answers in (
            ["1", "", "", "", "2", "", "0", "5"],
            ["1", "", "", "", "2", "", "", "0", "5"],
        ):
            with self.subTest(answers=answers):
                script = """
_FRP_ZT_CLIENT_NAME=test-host
frpctl_zt_invoke_create_client() {
    printf 'SERVICES_JSON '
    cat "$3"
}
frpctl_zt_run_services
"""
                rc, out = _source_frpctl(script, answers)
                self.assertEqual(rc, 0, out)
                match = re.search(r"^SERVICES_JSON (.+)$", out, re.M)
                self.assertIsNotNone(match, out)
                import json
                items = json.loads(match.group(1))
                self.assertEqual([x["id"] for x in items], ["ssh"])

    def test_cancel_nested_identification_cannot_invoke_enrollment(self):
        for answers in (["0", "22"], ["test-host", "0", "22"]):
            with self.subTest(answers=answers):
                script = """
_FRP_ZT_CLIENT_NAME=
frpctl_zt_invoke_create_client() { echo "INVOKED_ENROLLMENT"; }
frpctl_zt_run_ssh
"""
                rc, out = _source_frpctl(script, answers)
                self.assertIn("Cancelled. No changes were applied.", out)
                self.assertNotIn("INVOKED_ENROLLMENT", out)
                self.assertNotEqual(rc, 0, out)

    def test_end_of_input_inside_wizard_is_announced_and_changes_nothing(self):
        rc, out = _source_frpctl(self.FLOW, ["1"])
        self.assertIn("End of input. Cancelled; no changes were applied.", out)
        self.assertNotIn("INVOKED", out)

    def test_text_prompt_end_of_input_is_announced_not_silent(self):
        # frpctl_read_text is the prompt layer behind F-013 "Managed Host name": Ctrl-D
        # there must say that the step was cancelled instead of silently vanishing.
        script = 'frpctl_read_text "Managed Host name (? help, 0 or empty cancels): " "" >/dev/null\n' \
                 'frpctl_read_text "Managed Host name (? help, 0 or empty cancels): " "" >/dev/null || echo "RC=$?"'
        rc, out = _source_frpctl(script, ["first"])
        self.assertEqual(out.count("End of input. Cancelled; no changes were applied."), 1, out)
        self.assertIn("RC=1", out)

    def test_every_selection_error_names_the_help_key(self):
        # Terminology consistency: an invalid-number error must always tell the operator
        # about `?` (and the cancel/back key), never just print the valid range.
        text = CTL.read_text(encoding="utf-8")
        bare = [ln.strip() for ln in text.splitlines()
                if "ERROR: select " in ln and "? for help" not in ln]
        self.assertEqual(bare, [], bare)

    def test_submenu_end_of_input_cannot_spin_in_a_continue_loop(self):
        # `read_menu ... || continue` re-reads forever once stdin is closed (Ctrl-D).
        text = CTL.read_text(encoding="utf-8")
        spinning = [ln.strip() for ln in text.splitlines()
                    if "frpctl_read_menu" in ln and ln.rstrip().endswith("|| continue")]
        self.assertEqual(spinning, [], spinning)

    def test_no_raw_select_prompts_remain_outside_the_navigation_loop(self):
        text = CTL.read_text(encoding="utf-8")
        raw = [m.group(0) for m in re.finditer(r'frpctl_read "Select[^"]*"', text)]
        self.assertLessEqual(len(raw), 1, raw)  # only frpctl_nav_loop classifies ?/0 itself


if __name__ == "__main__":
    unittest.main(verbosity=2)
