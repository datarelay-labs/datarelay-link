#!/usr/bin/env python3
"""Prove LineEditor passes live inventory into completion_candidates."""
from __future__ import annotations

import importlib.util
import json
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REPL = load("frp_ctl_repl", "lib/frp_ctl_repl.py")


class ReplLiveInventoryTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "role": "server",
            "names": ["24cd7856"],
            "clients": [{"id": "24cd7856", "label": "a", "hostname": "h"}],
            "services": {"24cd7856": ["ssh"]},
            "local_services": [],
            "groups": ["edge"],
            "egress": ["vendor-api"],
            "access_lists": ["office"],
            "service_profiles": ["office-ssh"],
            "inventory_warning": False,
        }
        self.editor = REPL.LineEditor(self.payload)

    def _cands(self, line: str):
        trailing = bool(line) and line[-1:] in " \t"
        return self.editor.grammar.completion_candidates(
            line,
            self.editor.role,
            self.editor.names,
            self.editor.services,
            self.editor.local_services,
            trailing=trailing,
            **self.editor._completion_kwargs(),
        )

    def test_editor_retains_inventory_fields(self):
        self.assertEqual(self.editor.egress_profiles, ["vendor-api"])
        self.assertEqual(self.editor.access_lists, ["office"])
        self.assertEqual(self.editor.service_profiles, ["office-ssh"])

    def test_tab_uses_live_inventory(self):
        self.assertIn("24cd7856", self._cands("show managed-host "))
        self.assertIn("24cd7856", self._cands("unset managed-host "))

    def test_mutation_refresh_helper_updates_all_fields(self):
        # Simulate a refreshed payload after create/delete.
        refreshed = dict(self.payload)
        refreshed["names"] = ["24cd7856", "new-host"]
        refreshed["clients"] = list(self.payload["clients"]) + [
            {"id": "new-host", "label": "b", "hostname": "h2"}
        ]
        refreshed["egress"] = ["vendor-api", "new-profile"]
        refreshed["access_lists"] = ["office", "remote"]
        refreshed["service_profiles"] = ["office-ssh", "office-http"]
        self.editor.payload = refreshed
        self.editor.role = refreshed["role"]
        self.editor.names = refreshed["names"]
        self.editor.clients = refreshed["clients"]
        self.editor.services = refreshed["services"]
        self.editor.local_services = refreshed["local_services"]
        self.editor.groups = refreshed["groups"]
        self.editor.egress_profiles = refreshed["egress"]
        self.editor.access_lists = refreshed["access_lists"]
        self.editor.service_profiles = refreshed["service_profiles"]
        self.assertIn("new-host", self._cands("show managed-host "))
        # Delete path
        self.editor.names = ["24cd7856"]
        self.assertNotIn("new-host", self._cands("show managed-host "))

    def test_should_refresh_current_grammar(self):
        self.assertTrue(REPL._should_refresh_inventory(["set", "internet-access", "x"]))
        self.assertTrue(REPL._should_refresh_inventory(["unset", "remote-access", "office"]))
        self.assertTrue(REPL._should_refresh_inventory(["system", "services", "apply"]))
        self.assertFalse(REPL._should_refresh_inventory(["show", "internet-access"]))
        self.assertFalse(REPL._should_refresh_inventory(["test", "internet-access", "1.1.1.1", "a", "443"]))
        self.assertFalse(REPL._should_refresh_inventory(["help", "commands"]))

    def test_current_agent_mutations_and_menu_refresh_inventory(self):
        for tokens in (
            ["set", "remote-service", "new-service"],
            ["unset", "remote-service", "new-service"],
            ["system", "apply", "configuration", "bundle.yaml"],
            ["system", "synchronize"],
            ["menu"],
        ):
            with self.subTest(tokens=tokens):
                self.assertTrue(REPL._should_refresh_inventory(tokens))
        self.assertFalse(REPL._should_refresh_inventory(["system", "diff", "configuration", "bundle.yaml"]))
        self.assertFalse(REPL._should_refresh_inventory(["test", "configuration", "bundle.yaml"]))

    def test_same_session_create_delete_and_menu_reload_completion_source(self):
        for via_menu in (False, True):
            with self.subTest(via_menu=via_menu):
                source = {"role": "client", "local_services": ["ssh"]}
                captured = []
                reads = []
                step = 0
                buffer = ""
                backend_calls = []

                def backend(argv, env):
                    backend_calls.append(argv)
                    source["local_services"] = ["ssh", "new-service"] if len(backend_calls) == 1 else ["ssh"]
                    return SimpleNamespace(returncode=0)

                def read_inventory(argv, **kwargs):
                    self.assertEqual(argv, ["drlink", "--print-grammar-payload"])
                    self.assertNotIn("FRP_CTL_GRAMMAR_PAYLOAD", kwargs["env"])
                    reads.append(list(source["local_services"]))
                    return SimpleNamespace(returncode=0, stdout=json.dumps(source))

                def input_line(_prompt):
                    nonlocal step, buffer
                    step += 1
                    if step == 1:
                        return "menu" if via_menu else "set remote-service new-service destination this-host service http enabled"
                    editor = captured[0]
                    if step == 2:
                        buffer = "show remote-service new"
                        self.assertEqual(editor.completer("new", 0), "new-service ")
                        self.assertNotIn("managed-host", editor.grammar.completion_candidates(
                            "show ", editor.role, editor.names, editor.services,
                            editor.local_services, trailing=True))
                        return "menu" if via_menu else "unset remote-service new-service"
                    buffer = "show remote-service new"
                    self.assertIsNone(editor.completer("new", 0))
                    buffer = "show remote-service ss"
                    self.assertEqual(editor.completer("ss", 0), "ssh ")
                    return "exit"

                fake_readline = SimpleNamespace(
                    get_line_buffer=lambda: buffer,
                    get_current_history_length=lambda: 0,
                    add_history=lambda _line: None,
                )
                with patch.object(REPL.LineEditor, "bind", lambda editor: captured.append(editor)), \
                     patch.object(REPL, "readline", fake_readline), \
                     patch.object(REPL, "_run_backend", side_effect=backend), \
                     patch.object(REPL.subprocess, "run", side_effect=read_inventory), \
                     patch.dict("os.environ", {"FRP_CTL_GRAMMAR_PAYLOAD": "stale"}), \
                     patch("builtins.input", side_effect=input_line):
                    self.assertEqual(REPL.run_repl("drlink", dict(source)), 0)
                self.assertEqual(reads, [["ssh", "new-service"], ["ssh"]])

    def test_failed_remote_service_command_does_not_reload_inventory(self):
        with patch.object(REPL.LineEditor, "bind", return_value=True), \
             patch.object(REPL, "readline", None), \
             patch.object(REPL, "_run_backend", return_value=SimpleNamespace(returncode=1)), \
             patch.object(REPL.subprocess, "run") as inventory, \
             patch("builtins.input", side_effect=["set remote-service invalid", "exit"]):
            self.assertEqual(REPL.run_repl("drlink", {"role": "client"}), 0)
        inventory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
