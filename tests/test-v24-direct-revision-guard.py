#!/usr/bin/env python3
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


class DirectRevisionGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-direct-revision-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ.pop("DRLINK_EXPECTED_REVISION", None)
        plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(plane.conn)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(
                ["set", "network-object", "race", "type", "ip", "value", "198.51.100.10"],
                root=self.tmp,
                plane=plane,
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.prepared_revision = plane.current_revision()
        plane.close()

    def tearDown(self):
        os.environ.pop("DRLINK_EXPECTED_REVISION", None)
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def _edit(self, value: str):
        plane = ControlPlane(self.tmp)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli.dispatch(
                    ["set", "network-object", "race", "value", value],
                    root=self.tmp,
                    plane=plane,
                )
            return rc, out.getvalue(), err.getvalue()
        finally:
            plane.close()
    def test_stale_second_direct_edit_fails_closed(self):
        os.environ["DRLINK_EXPECTED_REVISION"] = str(self.prepared_revision)

        rc1, _out1, err1 = self._edit("198.51.100.20")
        self.assertEqual(rc1, 0, err1)

        rc2, _out2, err2 = self._edit("198.51.100.30")
        self.assertEqual(rc2, 1)
        self.assertIn("REVISION_CONFLICT", err2)
        self.assertIn("No changes were applied", err2)

        plane = ControlPlane(self.tmp)
        try:
            obj = plane.require_object("race")
            values = plane._object_values(obj["id"])
            self.assertEqual(values, ["198.51.100.20"])
            self.assertEqual(plane.current_revision(), self.prepared_revision + 1)
        finally:
            plane.close()

    def test_invalid_revision_guard_is_non_mutating(self):
        os.environ["DRLINK_EXPECTED_REVISION"] = "not-an-integer"
        rc, _out, err = self._edit("198.51.100.40")
        self.assertEqual(rc, 1)
        self.assertIn("non-negative integer", err)


if __name__ == "__main__":
    unittest.main()
