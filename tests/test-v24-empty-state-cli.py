#!/usr/bin/env python3
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli


class EmptyStateCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-empty-state-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()

    def dispatch(self, tokens):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(tokens, root=self.tmp, plane=self.plane)
        return rc, out.getvalue(), err.getvalue()
    def test_major_empty_lists_are_explicit(self):
        cases = (
            (["show", "enrollments"], "No Enrollments"),
            (["show", "managed-hosts"], "No Managed Hosts"),
            (["show", "network-objects"], "No Network Objects"),
            (["show", "network-groups"], "No Network Groups"),
            (["show", "service-groups"], "No Service Groups"),
            (["show", "permission-objects"], "No Permission Objects"),
            (["show", "permission-groups"], "No Permission Groups"),
            (["show", "ai-identities"], "No AI Identities"),
            (["system", "revisions"], "No Revisions"),
        )
        for tokens, marker in cases:
            with self.subTest(tokens=tokens):
                rc, out, err = self.dispatch(list(tokens))
                self.assertEqual(rc, 0, err)
                self.assertTrue(out.strip(), tokens)
                self.assertIn(marker, out)
                self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
