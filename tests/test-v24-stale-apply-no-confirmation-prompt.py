#!/usr/bin/env python3
"""F-007 regression: a stale Bundle must be rejected before asking to apply.

The review text already says "Apply will reject this stale snapshot". Asking
"Apply these changes? [y/N]" afterwards is misleading (the confirmed apply can
only fail with REVISION_CONFLICT), so `system apply configuration` must reject
a stale Bundle without prompting. A current Bundle must still prompt.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24

BUNDLE = """configurationBundle:
  context: server
  sourceRevision: %d
  networkObjects:
    - name: f007-new
      type: ip
      value: 198.51.100.77
"""


class StaleApplyNoConfirmationPrompt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-f007-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ.pop("DRLINK_CONFIRM", None)
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def _apply(self, source_revision: int, answer: bool):
        path = Path(self.tmp, "bundle.yaml")
        path.write_text(BUNDLE % source_revision, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "_stdin_is_interactive", return_value=True), \
                mock.patch.object(cli, "_confirm_from_stdin", return_value=answer) as confirm, \
                redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(["system", "apply", "configuration", str(path)],
                              root=self.tmp, plane=self.plane)
        return rc, out.getvalue() + err.getvalue(), confirm

    def test_stale_bundle_rejected_without_prompt(self):
        v24.set_network_object(self.plane, "other", type="ip", value="198.51.100.1", oneshot=True)
        stale = self.plane.current_revision() - 1
        rc, text, confirm = self._apply(stale, answer=True)
        confirm.assert_not_called()
        self.assertNotEqual(rc, 0)
        self.assertIn("REVISION_CONFLICT", text)
        self.assertIsNone(self.plane.get_object("f007-new"))

    def test_current_bundle_still_prompts_and_applies(self):
        rc, text, confirm = self._apply(self.plane.current_revision(), answer=True)
        confirm.assert_called_once()
        self.assertEqual(rc, 0, text)
        self.assertIsNotNone(self.plane.get_object("f007-new"))


if __name__ == "__main__":
    unittest.main()
