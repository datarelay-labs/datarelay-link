#!/usr/bin/env python3
"""Revision discovery/diff/rollback public contract."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_cli as cli
import drlink_v24 as v24
import frp_ctl_grammar as grammar
from drlink_control_plane import ControlPlane
from drlink_v24_bundle import apply_v24_plan, prepare_v24_plan


class TTYInput(io.StringIO):
    def isatty(self):
        return True


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text(
        '{"role":"server"}\n', encoding="utf-8"
    )


class RevisionRollbackContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-revision-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        os.environ.pop("DRLINK_SKIP_ACTIVATION", None)

    def _dispatch(self, args, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        stream = stdin if stdin is not None else io.StringIO("")
        with patch("sys.stdin", stream), redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(list(args), root=self.tmp, plane=self.plane)
        return rc, out.getvalue(), err.getvalue()

    def _object_value(self, name):
        row = self.plane.conn.execute(
            "SELECT v.value FROM objects o JOIN object_values v "
            "ON v.object_id=o.id WHERE o.name=? COLLATE NOCASE",
            (name,),
        ).fetchone()
        return None if row is None else row["value"]

    def test_revision_diff_and_rollback_preserve_history(self):
        v24.set_network_object(
            self.plane, "alpha", type="ip", value="10.0.0.1", oneshot=True
        )
        self.assertEqual(self.plane.current_revision(), 1)

        snap1 = self.plane.revision_snapshot(1)
        self.assertEqual(
            snap1.get("snapshot_format"), "drlink-revision-configuration-v1"
        )
        self.assertIn("configurationBundle:", snap1.get("configuration_bundle", ""))

        v24.set_network_object(
            self.plane, "alpha", type="ip", value="10.0.0.2", oneshot=True
        )
        v24.set_network_object(
            self.plane, "beta", type="ip", value="10.0.0.3", oneshot=True
        )
        self.assertEqual(self.plane.current_revision(), 3)

        rc, out, err = self._dispatch(["system", "revision", "1"])
        self.assertEqual(rc, 0, err)
        self.assertIn("Rollback available: YES", out)

        rc, out, err = self._dispatch(["system", "diff", "1", "3"])
        self.assertEqual(rc, 0, err)
        self.assertIn("--- revision-1", out)
        self.assertIn("+++ revision-3", out)
        self.assertIn("10.0.0.1", out)
        self.assertIn("10.0.0.2", out)
        self.assertIn("beta", out)

        rc, out, err = self._dispatch(["system", "rollback", "1"])
        self.assertEqual(rc, 1)
        self.assertIn("requires confirmation", err)
        self.assertEqual(self.plane.current_revision(), 3)
        self.assertEqual(self._object_value("alpha"), "10.0.0.2")

        rc, out, err = self._dispatch(
            ["system", "rollback", "1"], TTYInput("n\n")
        )
        self.assertEqual(rc, 1)
        self.assertIn("Cancelled", out)
        self.assertEqual(self.plane.current_revision(), 3)
        self.assertEqual(self._object_value("alpha"), "10.0.0.2")

        rc, out, err = self._dispatch(
            ["system", "rollback", "1"], TTYInput("y\n")
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("Rollback result: APPLIED", out)
        self.assertEqual(self.plane.current_revision(), 4)
        self.assertEqual(self._object_value("alpha"), "10.0.0.1")
        self.assertIsNone(self._object_value("beta"))

        revisions = [r["revision"] for r in self.plane.list_revisions()]
        self.assertEqual(revisions[:4], [4, 3, 2, 1])
        row4 = self.plane.revision_record(4)
        self.assertEqual(row4["command"], "system rollback 1")
        snap4 = self.plane.revision_snapshot(4)
        self.assertEqual(snap4.get("rollback_target_revision"), 1)

        rc, out, err = self._dispatch(["system", "rollback", "1"])
        self.assertEqual(rc, 0, err)
        self.assertIn("Rollback result: NO CHANGE", out)
        self.assertEqual(self.plane.current_revision(), 4)

    def test_policy_reset_rollback_uses_apply_safety_pipeline(self):
        v24.set_network_object(
            self.plane, "anchor", type="ip", value="10.10.10.10", oneshot=True
        )
        self.assertEqual(self.plane.current_revision(), 1)
        plan = prepare_v24_plan(
            self.plane,
            """configurationBundle:
  context: server
  remoteAccess:
    mode: whitelist
    enforcement: enabled
    rules: []
""",
        )
        result = apply_v24_plan(self.plane, plan, confirm=True)
        self.assertEqual(result.get("status"), "APPLIED")
        self.assertEqual(v24.get_access_policy(self.plane, "remote")["mode"], "whitelist")

        rc, out, err = self._dispatch(["system", "rollback", "1"])
        self.assertEqual(rc, 1)
        self.assertIn("system rollback requires confirmation", err)
        self.assertEqual(v24.get_access_policy(self.plane, "remote")["mode"], "whitelist")

        rc, out, err = self._dispatch(
            ["system", "rollback", "1"], TTYInput("y\n")
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("RESET remote-access policy", out)
        self.assertIn("This change resets Remote Access", out)
        self.assertIn("Rollback result: APPLIED", out)
        self.assertIsNone(v24.get_access_policy(self.plane, "remote")["mode"])

    def test_public_grammar_routes_revision_commands_to_control_plane(self):
        for tokens in (
            ["system", "revision", "1"],
            ["system", "diff", "1", "2"],
            ["system", "rollback", "1"],
        ):
            result = grammar.match(tokens, "server")
            self.assertEqual(result.get("status"), "ok", (tokens, result))
            self.assertEqual(result.get("action"), "control_plane", (tokens, result))
            self.assertEqual(result.get("tokens"), tokens, (tokens, result))

    def test_legacy_summary_only_revision_fails_closed(self):
        v24.set_network_object(
            self.plane, "alpha", type="ip", value="10.0.0.1", oneshot=True
        )
        self.plane.conn.execute(
            "UPDATE revision_snapshots SET snapshot_json=? WHERE revision=1",
            (json.dumps({"summary": "legacy"}),),
        )
        self.plane.conn.commit()
        rc, out, err = self._dispatch(
            ["system", "rollback", "1"], TTYInput("y\n")
        )

        self.assertEqual(rc, 1)
        self.assertIn("predates configuration snapshots", err)
        self.assertEqual(self.plane.current_revision(), 1)

    def test_public_catalog_exposes_revision_commands(self):
        rows = json.loads(
            (ROOT / "lib/frp_cli_final_commands.json").read_text(encoding="utf-8")
        )
        paths = {tuple(row.get("path") or ()) for row in rows}
        self.assertIn(("system", "revision"), paths)
        self.assertIn(("system", "diff"), paths)
        self.assertIn(("system", "rollback"), paths)

        text = (ROOT / "lib/frp_cli_catalog.py").read_text(encoding="utf-8")
        self.assertIn("system revision <REVISION>", text)
        self.assertIn("system diff <REVISION_A> <REVISION_B>", text)
        self.assertIn("system rollback <REVISION>", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
