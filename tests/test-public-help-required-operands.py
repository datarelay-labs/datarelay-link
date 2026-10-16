#!/usr/bin/env python3
"""Public help examples must supply mandatory operands, including selectors."""
from __future__ import annotations

import io
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_cli_catalog as catalog
import frp_ctl_grammar as grammar
import drlink_control_cli as cli
from drlink_control_plane import ControlPlane


def examples_from_help(text):
    """Read the user-visible Examples section, rather than raw catalog values."""
    if "\nExamples:\n" not in text:
        return []
    section = text.split("\nExamples:\n", 1)[1]
    return [line.strip() for line in section.splitlines() if line.startswith("  ")]


class PublicHelpRequiredOperands(unittest.TestCase):
    def test_own_leaf_examples_include_required_operands(self):
        failures = []
        for command in catalog.PUBLIC_COMMANDS:
            for example in examples_from_help(catalog.command_help(command)):
                tokens = shlex.split(example)
                leaf = catalog.find(tokens)
                # Cross-command follow-up examples and explicit child variants
                # have their own contracts; never treat them as this leaf.
                if leaf is None or leaf["path"] != command["path"]:
                    continue
                required = [arg for arg in command["args"] if arg["required"]]
                operands = tokens[len(command["path"]):]
                if len(operands) < len(required):
                    failures.append(
                        "%s: example %r omits required operand(s) %s"
                        % (" ".join(command["path"]), example,
                           ", ".join(arg["name"] for arg in required[len(operands):]))
                    )
        self.assertFalse(failures, "\n" + "\n".join(failures))

    def test_agent_diagnostics_examples_respect_role_context(self):
        text = grammar._catalog_context_help(["system", "diagnostics"], "client")
        self.assertIsNotNone(text)
        self.assertEqual(examples_from_help(text),
                         ["system diagnostics", "system diagnostics runtime"])
        for example in examples_from_help(text):
            result = grammar.match(shlex.split(example), role="client")
            self.assertNotIn(result.get("status"), ("error", "role", "unknown", "incomplete"), result)

    def test_missing_show_selector_fails_without_database_change(self):
        with tempfile.TemporaryDirectory(prefix="drlink-help-operands-") as tmp:
            settings = Path(tmp, "etc/drlink")
            settings.mkdir(parents=True)
            (settings / "config.json").write_text('{"role":"server"}\n', encoding="utf-8")
            plane = ControlPlane(tmp)
            try:
                for resource in ("network-object", "service-object", "permission-object", "ai-identity"):
                    before = "\n".join(plane.conn.iterdump())
                    output, error = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), redirect_stderr(error):
                        rc = cli.dispatch(["show", resource], root=tmp, plane=plane)
                    self.assertNotEqual(rc, 0, resource)
                    self.assertTrue(error.getvalue() or output.getvalue(), resource)
                    self.assertEqual("\n".join(plane.conn.iterdump()), before, resource)
            finally:
                plane.close()


if __name__ == "__main__":
    unittest.main()
