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

    def test_ai_access_set_tab_includes_live_rules_and_guidance(self):
        g = self.editor.grammar
        line = "set ai-access "
        hits = g.completion_candidates(line, "server", [], {}, [], inventory={"ai-access-rules": ["at-secu-group", "expernet-group"]})
        self.assertEqual(set(hits), {"at-secu-group", "expernet-group", "enabled", "disabled"})
        output = g.format_tab_candidates(line, hits, "server")
        for item in ("<Enter>", "new Rule name", "at-secu-group", "expernet-group", "Edit this AI Access Rule"):
            self.assertIn(item, output)

    def test_managed_host_group_registry_authority_and_member_display(self):
        import drlink_control_db as db
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'etc/drlink/config.json'
            config.parent.mkdir(parents=True)
            registry = root / 'registry.json'
            config.write_text(json.dumps({'role': 'server', 'registry_file': str(registry), 'public_host': '192.0.2.10'}))
            master = 'fa123456000000000000000000000001'
            worker = '43123456000000000000000000000002'
            gid = 'grp_22222222'
            clients = {master: {'label': 'Example DP Master', 'hostname': 'dp1', 'group_ids': [gid]},
                       worker: {'label': 'Example DP Worker', 'hostname': 'dp3', 'group_ids': [gid]}}
            registry.write_text(json.dumps({'schema_version': 2, 'clients': clients, 'groups': {
                'grp_11111111': {'name': 'Office'}, gid: {'name': 'Example'},
                'grp_33333333': {'name': 'Empty'}}}))
            conn = db.connect(root=temp)
            db.initialize(conn)
            timestamp = '2026-11-26T00:00:00Z'
            conn.execute('INSERT INTO client_groups(id,name,created_at,updated_at) VALUES (?,?,?,?)',
                         ('grp_11111111', 'Office', timestamp, timestamp))
            for mid, row in clients.items():
                conn.execute('INSERT INTO clients(id,label,hostname,created_at,updated_at) VALUES (?,?,?,?,?)',
                             (mid, row['label'], row['hostname'], timestamp, timestamp))
            conn.commit()
            conn.close()
            before = registry.read_bytes(), db.db_path(temp).read_bytes()
            g = self.editor.grammar
            payload = g.read_only_completion_inventory('server', temp)
            self.assertIn('Example', payload['groups'])
            self.assertIn('Empty', payload['groups'])
            self.assertEqual(before, (registry.read_bytes(), db.db_path(temp).read_bytes()))
            editor = REPL.LineEditor(dict(payload, role='server'))
            for line in ('set managed-host 43123456 group Ex', 'show managed-host-group Ex', 'show managed-host-group ex',
                         'set managed-host-group Ex', 'unset managed-host-group Ex',
                         'unset managed-host 43123456 group Ex'):
                self.assertEqual(g.completion_candidates(line, editor.role, editor.names,
                    editor.services, editor.local_services, **editor._completion_kwargs()), ['Example'], line)
            line = 'set managed-host '
            hits = g.completion_candidates(line, editor.role, editor.names, editor.services,
                editor.local_services, **editor._completion_kwargs())
            rendered = g.format_tab_candidates(line, hits, editor.role, clients=editor.clients)
            self.assertEqual(len(rendered.splitlines()), 3, rendered)
            self.assertIn(master, rendered)
            self.assertIn(worker, rendered)
            env = dict(os.environ, FRP_DEPLOY_TEST_ROOT=temp, FRP_CTL_TEST_ROOT=temp,
                       FRP_CTL_BIN_DIR=str(ROOT / "tools"))
            proc = subprocess.run([str(ROOT / 'tools/drlink'), 'show', 'managed-host-group', 'Example'], env=env,
                                  capture_output=True, text=True, check=True)
            for value in (master, worker, 'Example DP Master', 'Example DP Worker', 'dp1', 'dp3'):
                self.assertIn(value, proc.stdout)
            self.assertIn('Managed Hosts : 2', proc.stdout)
            empty = subprocess.run([str(ROOT / 'tools/drlink'), 'show', 'managed-host-group', 'Empty'], env=env,
                                   capture_output=True, text=True, check=True)
            self.assertIn('No Managed Hosts', empty.stdout)
            # Native payload refresh after a successful public group creation.
            env.pop('FRP_CTL_GRAMMAR_PAYLOAD', None)
            created = subprocess.run([str(ROOT / 'tools/drlink'), 'set', 'managed-host-group', 'NewGroup'],
                                     env=env, capture_output=True, text=True, check=True)
            self.assertIn('NewGroup', created.stdout)
            native = subprocess.run([str(ROOT / 'tools/frpctl'), '--print-grammar-payload'],
                                    env=env, capture_output=True, text=True, check=True)
            self.assertIn('NewGroup', json.loads(native.stdout)['groups'])
            self.assertEqual(g.completion_candidates('show managed-host-group New', 'server', [], {}, [],
                groups=json.loads(native.stdout)['groups']), ['NewGroup'])


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
                ('ai_policy_rules', '', ''),
            ):
                conn.execute('INSERT INTO %s (id,name,created_at,updated_at%s) '
                             'VALUES (?,?,?,?%s)' % (table, extra_columns, extra_values),
                             (table + '-id', table + '-name', timestamp, timestamp))
            conn.close()
            target = db.db_path(temp)
            before = target.read_bytes()
            inventory = self.editor.grammar.read_only_completion_inventory('server', temp)
            self.assertEqual(target.read_bytes(), before)
            self.assertNotIn('ai_access_rules-name', inventory['inventory'][self.editor.grammar.CATALOG.C_AI_RULE])
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
                ('ai-access', 'ai_policy_rules-name'),
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

    def test_all_canonical_set_unset_resources_refresh_without_legacy_roots(self):
        for command in self.editor.grammar.CATALOG.COMMANDS:
            path = command["path"]
            if len(path) >= 2 and path[0] in ("set", "unset") and not command.get("hidden"):
                with self.subTest(path=path):
                    self.assertTrue(REPL._should_refresh_inventory(list(path) + ["fixture"]))
        for tokens in (
            ["set", "ai-principal", "fixture"],
            ["unset", "service-profile", "fixture"],
            ["set", "object", "fixture"],
            ["create", "service", "fixture"],
            ["system", "import", "fixture"],
        ):
            with self.subTest(tokens=tokens):
                self.assertFalse(REPL._should_refresh_inventory(tokens))

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
