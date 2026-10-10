#!/usr/bin/env python3
"""Prove LineEditor passes live inventory into completion_candidates."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
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

    def test_finite_view_choices_after_selector(self):
        for resource, choices in {
            'managed-host': ['remote-services', 'agent', 'addresses'],
            'network-object': ['references'],
            'network-group': ['references'],
            'service-object': ['references'],
            'service-group': ['references'],
        }.items():
            with self.subTest(resource=resource):
                line = 'show %s fixture ' % resource
                self.assertEqual(self._cands(line), choices)
                for choice in choices:
                    self.assertIn(choice, self._cands(line + choice[:2]))

    def test_declared_inventory_from_authoritative_db_and_same_session_refresh(self):
        import drlink_control_db as db
        with tempfile.TemporaryDirectory(prefix='drlink-completion-db-') as temp:
            conn = db.connect(root=temp)
            db.initialize(conn)
            timestamp = '2026-10-07T00:00:00Z'
            for table, extra_columns, extra_values in (
                ('objects', ',type,origin', ", 'ip', 'static'"),
                ('object_groups', '', ''),
                ('ai_principals', '', ''),
                ('ai_access_rules', ',position', ',1'),
            ):
                conn.execute('INSERT INTO %s (id,name,created_at,updated_at%s) '
                             'VALUES (?,?,?,?%s)' % (table, extra_columns, extra_values),
                             (table + '-id', table + '-name', timestamp, timestamp))
            conn.close()
            target = db.db_path(temp)
            before = target.read_bytes()
            inventory = self.editor.grammar.read_only_completion_inventory('server', temp)
            self.assertEqual(target.read_bytes(), before)
            config = Path(temp) / 'etc/drlink/config.json'
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text('{"role":"server"}\n')
            env = dict(os.environ, FRP_CTL_TEST_ROOT=temp, FRP_DEPLOY_TEST_ROOT=temp)
            env.pop('FRP_CTL_GRAMMAR_PAYLOAD', None)
            native = subprocess.run(
                ['bash', str(ROOT / 'tools/frpctl'), '--print-grammar-payload'],
                env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(native.returncode, 0, native.stderr)
            self.assertEqual(json.loads(native.stdout)['inventory'], inventory['inventory'])
            self.assertEqual(target.read_bytes(), before)
            editor = REPL.LineEditor(dict(inventory, role='server'))
            for resource, name in (
                ('network-object', 'objects-name'),
                ('network-group', 'object_groups-name'),
                ('ai-identity', 'ai_principals-name'),
                ('ai-access', 'ai_access_rules-name'),
            ):
                with self.subTest(resource=resource):
                    for action in (('show',) if resource == 'ai-access'
                                   else ('show', 'unset')):
                        line = '%s %s ' % (action, resource)
                        self.assertIn(name, editor.grammar.completion_candidates(
                            line, editor.role, editor.names, editor.services,
                            editor.local_services, **editor._completion_kwargs()))
                    self.assertTrue(REPL._should_refresh_inventory(['set', resource, name]))
                    self.assertTrue(REPL._should_refresh_inventory(['unset', resource, name]))
            refreshed = dict(inventory, role='server')
            refreshed['inventory'] = {key: [] for key in inventory['inventory']}
            with patch.object(REPL.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps(refreshed))):
                REPL._refresh_editor_inventory(editor, 'drlink')
            self.assertEqual(editor.grammar.completion_candidates(
                'show ai-identity ', editor.role, editor.names, editor.services,
                editor.local_services, **editor._completion_kwargs()), [])

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
        self.assertTrue(REPL._should_refresh_inventory(["system", "apply", "configuration", "bundle.yaml"]))
        self.assertFalse(REPL._should_refresh_inventory(["show", "internet-access"]))
        self.assertFalse(REPL._should_refresh_inventory(["test", "internet-access", "source", "192.0.2.1", "destination", "example.test", "service", "https"]))
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

    def test_server_rollback_reloads_completion_inventory(self):
        """A rollback replaces object names, and Tab must use the restored revision."""
        before = {"role": "server", "inventory": {"objects": ["stale-object"]}}
        after = {"role": "server", "inventory": {"objects": ["restored-object"]}}
        editors = []
        steps = []

        def user_input(_prompt):
            editor = editors[0]
            candidates = editor.grammar.completion_candidates(
                "show network-object ", editor.role, editor.names, editor.services,
                editor.local_services, **editor._completion_kwargs())
            if not steps:
                self.assertIn("stale-object", candidates)
                steps.append("before")
                return "system rollback revision123"
            self.assertIn("restored-object", candidates)
            self.assertNotIn("stale-object", candidates)
            steps.append("after")
            return "exit"

        with patch.object(REPL.LineEditor, "bind", lambda editor: editors.append(editor)), \
             patch.object(REPL, "readline", None), \
             patch.object(REPL, "_run_backend", return_value=SimpleNamespace(returncode=0)) as backend, \
             patch.object(REPL.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stdout=json.dumps(after))) as refresh, \
             patch("builtins.input", side_effect=user_input):
            self.assertEqual(REPL.run_repl("drlink", before), 0)
        backend.assert_called_once()
        refresh.assert_called_once()
        self.assertEqual(steps, ["before", "after"])

    def test_inventory_refresh_timeout_keeps_repl_usable(self):
        """A slow completion snapshot must not lock the operator out of the REPL."""
        with patch.object(REPL.LineEditor, "bind", return_value=True), \
             patch.object(REPL, "readline", None), \
             patch.object(REPL, "_run_backend", return_value=SimpleNamespace(returncode=0)) as backend, \
             patch.object(REPL.subprocess, "run", side_effect=REPL.subprocess.TimeoutExpired(
                 cmd=["drlink", "--print-grammar-payload"], timeout=8)) as refresh, \
             patch("builtins.input", side_effect=["system rollback revision123", "exit"]):
            self.assertEqual(REPL.run_repl("drlink", {"role": "server"}), 0)
        backend.assert_called_once()
        refresh.assert_called_once()
        self.assertEqual(refresh.call_args.kwargs["timeout"], 8)

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
