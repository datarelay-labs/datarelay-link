#!/usr/bin/env python3
"""Regressions for obsolete parser routes and Agent role discovery."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_cli_catalog as catalog
import frp_ctl_grammar as grammar


class RoleParserRegression(unittest.TestCase):
    def test_unknown_system_help_never_falls_back_to_domain_success(self):
        for role in ("server", "client"):
            with tempfile.TemporaryDirectory(prefix="drlink-nested-help-") as temp:
                root = Path(temp)
                config = root / ("etc/drlink/config.json" if role == "server"
                                 else "etc/frp/client-state.json")
                config.parent.mkdir(parents=True)
                config.write_text('{"role":"server"}\n' if role == "server" else '{"services":{}}\n')
                before = config.read_bytes()
                env = dict(os.environ, FRP_CTL_TEST_ROOT=temp, FRP_DEPLOY_TEST_ROOT=temp)
                for leaf in ("doctor", "not-an-operation"):
                    for tokens in (["help", "system", leaf], ["system", leaf, "?"]):
                        with self.subTest(role=role, tokens=tokens):
                            result = subprocess.run(["bash", str(ROOT / "tools/drlink"), *tokens],
                                cwd=temp, env=env, capture_output=True, text=True, timeout=30)
                            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                            self.assertIn("help system", result.stdout + result.stderr)
                for tokens in (["help", "system"], ["help", "system", "update"],
                               ["help", "system", "update", "product"]):
                    result = subprocess.run(["bash", str(ROOT / "tools/drlink"), *tokens],
                        cwd=temp, env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("product", result.stdout)
                self.assertEqual(config.read_bytes(), before)

    def test_obsolete_recovery_lists_complete_commands(self):
        for tokens in (["client"], ["enrollment"]):
            rendered = grammar.context_help(tokens, "server")
            self.assertIn("  set enrollment zero-touch\n", rendered)
            self.assertIn("  set enrollment manual\n", rendered)
            self.assertNotIn("zero-touch|manual", rendered)
        rejected = grammar.reject_obsolete_surface(["show", "services"])
        for command in ("show remote-services", "show remote-service <NAME>",
                        "set remote-service <NAME>", "unset remote-service <NAME>"):
            self.assertIn("  " + command + "\n", rejected["message"])
        self.assertNotIn("show/set/unset", rejected["message"])

    def test_retired_test_resources_reject_native_execution_and_help(self):
        for role in ('server', 'client'):
            with tempfile.TemporaryDirectory(prefix='drlink-retired-test-resource-') as temp:
                root = Path(temp)
                config = root / ('etc/drlink/config.json' if role == 'server'
                                 else 'etc/frp/client-state.json')
                config.parent.mkdir(parents=True)
                config.write_text('{"role":"server"}\n' if role == 'server'
                                  else '{"services":{}}\n')
                before = {str(p.relative_to(root)): p.read_bytes()
                          for p in root.rglob('*') if p.is_file()}
                env = dict(os.environ, FRP_CTL_TEST_ROOT=temp,
                           FRP_DEPLOY_TEST_ROOT=temp)
                for resource in ('group', 'groups', 'service', 'services'):
                    command = ['test', resource, 'fixture']
                    for tokens in (command, command + ['?'], ['help'] + command):
                        with self.subTest(role=role, tokens=tokens):
                            result = subprocess.run(
                                ['bash', str(ROOT / 'tools/drlink'), *tokens],
                                cwd=temp, env=env, capture_output=True, text=True,
                                timeout=30)
                            output = result.stdout + result.stderr
                            self.assertEqual(result.returncode, 2, output)
                            self.assertIn('not part of', output)
                            self.assertIn('test remote-access', output)
                after = {str(p.relative_to(root)): p.read_bytes()
                         for p in root.rglob('*') if p.is_file()}
                self.assertEqual(after, before)

    def test_retired_test_resource_guard_preserves_current_selector_values(self):
        self.assertIsNone(grammar.reject_obsolete_surface([
            'test', 'remote-access', 'source', 'groups',
            'destination', 'services', 'service', 'group',
        ]))

    def test_retired_credential_noun_rejects_native_execution_and_help(self):
        for role in ('server', 'client'):
            with tempfile.TemporaryDirectory(prefix='drlink-credential-grammar-') as temp:
                root = Path(temp)
                config = root / ('etc/drlink/config.json' if role == 'server'
                                 else 'etc/frp/client-state.json')
                config.parent.mkdir(parents=True)
                config.write_text('{"role":"server"}\n' if role == 'server'
                                  else '{"services":{}}\n')
                before = {str(p.relative_to(root)): p.read_bytes()
                          for p in root.rglob('*') if p.is_file()}
                env = dict(os.environ, FRP_CTL_TEST_ROOT=temp,
                           FRP_DEPLOY_TEST_ROOT=temp)
                for operation in ('rotate', 'revoke', 'configure'):
                    for operands in ([], ['fixture'], ['fixture', 'extra']):
                        command = ['system', 'credential', operation,
                                   'ai-principal', *operands]
                        for tokens in (command, command + ['?'], ['help'] + command):
                            with self.subTest(role=role, tokens=tokens):
                                result = subprocess.run(
                                    ['bash', str(ROOT / 'tools/drlink'), *tokens],
                                    cwd=temp, env=env, capture_output=True, text=True,
                                    timeout=30)
                                output = result.stdout + result.stderr
                                self.assertEqual(result.returncode, 2, output)
                                self.assertIn('ai-identity', output)
                                self.assertIn('Server', output)
                after = {str(p.relative_to(root)): p.read_bytes()
                         for p in root.rglob('*') if p.is_file()}
                self.assertEqual(after, before)

    def test_retired_noun_guard_preserves_current_identity_selector(self):
        for operation in ('rotate', 'revoke', 'configure'):
            command = ['system', 'credential', operation, 'ai-identity',
                       'ai-principal']
            if operation == 'configure':
                command += ['authentication', 'oauth']
            self.assertIsNone(grammar.reject_obsolete_surface(command))
            self.assertNotIn('Unknown help topic', grammar.help_text(command, 'server'))

    def test_native_obsolete_test_never_reaches_removed_backend(self):
        for role in ("server", "client"):
            with tempfile.TemporaryDirectory(prefix="drlink-test-access-") as temp:
                root = Path(temp)
                config = root / ("etc/drlink/config.json" if role == "server"
                                 else "etc/frp/client-state.json")
                config.parent.mkdir(parents=True)
                config.write_text('{"role":"server"}\n' if role == "server"
                                  else '{"services":{}}\n')
                before = {str(p.relative_to(root)): p.read_bytes()
                          for p in root.rglob("*") if p.is_file()}
                env = dict(os.environ, FRP_CTL_TEST_ROOT=temp,
                           FRP_DEPLOY_TEST_ROOT=temp)
                for tokens in (
                    ["test", "access", "host", "ssh", "192.0.2.1"],
                    ["test", "access", "?"],
                    ["help", "test", "access"],
                ):
                    with self.subTest(role=role, tokens=tokens):
                        result = subprocess.run(
                            ["bash", str(ROOT / "tools/drlink"), *tokens],
                            cwd=temp, env=env, capture_output=True, text=True,
                            timeout=30)
                        output = result.stdout + result.stderr
                        self.assertEqual(result.returncode, 2, output)
                        self.assertIn("test remote-access", output)
                        self.assertNotIn("frp-access", output)
                after = {str(p.relative_to(root)): p.read_bytes()
                         for p in root.rglob("*") if p.is_file()}
                self.assertEqual(after, before)

    def test_obsolete_access_test_rejects_execution_and_help(self):
        for role in ("server", "client", "both"):
            for tokens in (
                ["test", "access"],
                ["test", "access", "host", "ssh", "192.0.2.1"],
                ["test", "access", "?"],
                ["help", "test", "access"],
            ):
                with self.subTest(role=role, tokens=tokens):
                    result = grammar.match(tokens, role)
                    self.assertEqual(result["status"], "error")
                    self.assertEqual(result["exit_code"], 2)
                    self.assertIn("test remote-access", result["message"])
                    self.assertNotIn("test acl", result["message"])
            self.assertEqual(grammar.completion_candidates(
                "test access ", role, [], {}, [], trailing=True), [])

    def test_current_remote_access_test_stays_supported(self):
        tokens = ["test", "remote-access", "source", "office", "destination",
                  "host", "service", "ssh"]
        for role in ("server", "both"):
            self.assertEqual(grammar.match(tokens, role)["status"], "ok")
        self.assertEqual(grammar.match(tokens, "client")["status"], "role")

    def test_agent_system_help_recommends_usable_status(self):
        help_lines = catalog.domain_help("system", "client").splitlines()
        self.assertIn("  show status", help_lines)
        self.assertNotIn("  system status", help_lines)
        for role in ("server", "both"):
            self.assertIn("  system status", catalog.domain_help("system", role).splitlines())

    def test_diagnostics_completion_matches_role_ownership(self):
        for role, expected in (
            ("client", ["runtime"]),
            ("server", ["control-plane", "runtime", "mcp"]),
            ("both", ["control-plane", "runtime", "mcp"]),
        ):
            with self.subTest(role=role):
                choices = grammar.completion_candidates(
                    "system diagnostics ", role, [], {}, [], trailing=True)
                self.assertEqual(choices, expected)
                question = grammar.match(["system", "diagnostics", "?"], role)
                self.assertEqual(question["status"], "ok")
                self.assertIn("runtime", question["message"])
                if role == "client":
                    self.assertNotIn("control-plane", question["message"])
                    self.assertNotIn("mcp", question["message"])
                for scope in choices:
                    result = grammar.match(["system", "diagnostics", scope], role)
                    self.assertEqual(result["status"], "ok", result)
        for scope in ("mcp", "control-plane"):
            self.assertEqual(grammar.match(
                ["system", "diagnostics", scope], "client")["status"], "role")
            self.assertEqual(grammar.completion_candidates(
                "system diagnostics " + scope[:1], "client", [], {}, [],
                trailing=False), [])


if __name__ == "__main__":
    unittest.main()
