#!/usr/bin/env python3
"""F-012 regression: usage errors must break lines, not print a literal backslash-n.

U-010/U-013 (claude-run-20261112) showed `show network-object` with no name
printing `Usage: show network-object <OBJECT>\\nFind an identifier: ...` on one
line because the source escaped the newline twice. Every `show <object>` usage
error that points at a list command shares the defect.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24

SHOW_RESOURCES = (
    "network-object",
    "network-group",
    "service-object",
    "service-group",
    "permission-object",
    "permission-group",
    "enrollment",
    "ai-identity",
)


class UsageErrorNewlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-usage-newline-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(plane.conn)
        plane.close()

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def _run(self, argv):
        plane = ControlPlane(self.tmp)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli.dispatch(argv, root=self.tmp, plane=plane)
            return rc, out.getvalue() + err.getvalue()
        finally:
            plane.close()

    def test_show_usage_errors_use_real_newline(self):
        for res in SHOW_RESOURCES:
            with self.subTest(resource=res):
                rc, text = self._run(["show", res])
                self.assertNotEqual(rc, 0, text)
                self.assertIn("Usage: show %s" % res, text)
                self.assertNotIn("\\n", text, "literal backslash-n in: %r" % text)
                self.assertIn("\nFind an identifier: show ", text)


if __name__ == "__main__":
    unittest.main()
