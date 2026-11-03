#!/usr/bin/env python3
"""A 'was not found' CLI error must tell the operator the next step.

U-013 finding (CLI100 E2E): `unset network-object <missing>` and similar
commands answered only "<Kind> '<name>' was not found. / No changes were
applied." with no recovery step, so the operator had to guess the list command.
Every not-found error for a named resource now names the `show ...` command that
lists the existing names; errors that already carry their own next step keep it.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24


class NotFoundNextStep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-nf-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text('{"role": "server"}\n', encoding="utf-8")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key in ("DRLINK_CONFIRM", "FRP_DEPLOY_TEST_ROOT"):
            os.environ.pop(key, None)

    def _run(self, *tokens):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(list(tokens), root=self.tmp, plane=self.plane)
        return rc, out.getvalue() + err.getvalue()

    def test_unset_missing_resource_names_the_list_command(self):
        cases = (
            ("network-object", "Network Object", "show network-objects"),
            ("network-group", "Network Group", "show network-groups"),
            ("service-object", "Service Object", "show service-objects"),
            ("service-group", "Service Group", "show service-groups"),
            ("permission-object", "Permission Object", "show permission-objects"),
            ("permission-group", "Permission Group", "show permission-groups"),
            ("managed-host", "Managed Host", "show managed-hosts"),
        )
        before = list(self.plane.conn.iterdump())
        for resource, label, listing in cases:
            with self.subTest(resource=resource):
                rc, message = self._run("unset", resource, "nosuch")
                self.assertNotEqual(rc, 0)
                self.assertIn("%s 'nosuch' was not found." % label, message)
                self.assertIn(listing, message)
                self.assertIn("No changes were applied.", message)
        self.assertEqual(list(self.plane.conn.iterdump()), before)

    def test_show_missing_resource_names_the_list_command(self):
        for resource, listing in (
            ("network-object", "show network-objects"),
            ("service-object", "show service-objects"),
        ):
            with self.subTest(resource=resource):
                rc, message = self._run("show", resource, "nosuch")
                self.assertNotEqual(rc, 0)
                self.assertIn("was not found", message)
                self.assertIn(listing, message)

    def test_cli_error_adds_next_step_only_when_missing(self):
        auto = v24.cli_error("Remote Service 'x' was not found.")
        self.assertIn("show remote-services", auto)
        self.assertIn("No changes were applied.", auto)
        explicit = v24.cli_error("Network Object 'x' was not found.", next_step="Custom recovery.")
        self.assertIn("Custom recovery.", explicit)
        self.assertNotIn("show network-objects", explicit)

    def test_show_status_labels_policy_mode_and_enforcement(self):
        # U-013 (low): "BLACKLIST / ENABLED" gave no hint which word is Mode vs Enforcement.
        policy = {"mode": "blacklist", "enforcement": "enabled"}
        with unittest.mock.patch.object(v24, "get_access_policy", return_value=policy):
            text = v24.format_show_status("server", self.plane)
        self.assertIn("Remote Access: Mode BLACKLIST / Enforcement ENABLED", text)
        self.assertNotIn("Remote Access: BLACKLIST / ENABLED", text)
        unsupported = {"mode": "blacklist", "enforcement": "enabled"}
        with unittest.mock.patch.object(v24, "get_access_policy", return_value=unsupported):
            text = v24.format_show_status("server", self.plane)
        self.assertIn("Internet Access: Mode BLACKLIST / FAIL CLOSED (UNSUPPORTED MODE)", text)

    def test_unrelated_errors_are_unchanged(self):
        plain = v24.cli_error("Something else failed.")
        self.assertEqual(plain, "ERROR:\nSomething else failed.\n\nNo changes were applied.")


if __name__ == "__main__":
    unittest.main()
