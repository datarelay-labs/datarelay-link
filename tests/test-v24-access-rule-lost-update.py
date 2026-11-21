#!/usr/bin/env python3
"""F-011 regression: concurrent Remote Access rule edits must not silently lose an update.

C-011 (claude-run-20261112) showed two operators editing the same enabled rule
at once: both received "rule set" success and the earlier edit vanished. The
confirmed retry now binds the rule row_version that the operator reviewed, and
every rule update advances the row_version.
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

from drlink_control_plane import ConcurrencyError, ConfirmationRequired, ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24


class AccessRuleLostUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-rule-lost-update-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ.pop("DRLINK_EXPECTED_REVISION", None)
        plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(plane.conn)
        plane.close()
        for argv in (
            ["set", "network-object", "src-a", "type", "ip", "value", "198.51.100.1"],
            ["set", "network-object", "src-b", "type", "ip", "value", "198.51.100.2"],
            ["set", "network-object", "dst-c", "type", "ip", "value", "198.51.100.3"],
            ["set", "service-object", "svc-a", "type", "tcp", "port", "18801"],
            ["set", "service-object", "svc-b", "type", "tcp", "port", "18802"],
            [
                "set", "remote-access", "r1", "mode", "blacklist", "source", "src-a",
                "destination", "dst-c", "service", "svc-a", "enabled",
            ],
        ):
            rc, _o, err = self._dispatch(argv)
            self.assertEqual(rc, 0, "%s: %s" % (argv, err))

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def _dispatch(self, argv):
        plane = ControlPlane(self.tmp)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli.dispatch(argv, root=self.tmp, plane=plane)
            return rc, out.getvalue(), err.getvalue()
        finally:
            plane.close()

    def _rule_state(self):
        plane = ControlPlane(self.tmp)
        try:
            row = plane._get_rule("remote", "r1")
            src = plane.conn.execute(
                "SELECT o.name FROM rule_sources s JOIN objects o ON o.id = s.ref_id "
                "WHERE s.rule_id = ?",
                (row["id"],),
            ).fetchone()[0]
            svc = plane.conn.execute(
                "SELECT s.name FROM rule_service_refs r JOIN service_objects s ON s.id = r.ref_id "
                "WHERE r.rule_id = ?",
                (row["id"],),
            ).fetchone()[0]
            return src, svc, int(row["row_version"])
        finally:
            plane.close()

    def test_selector_edit_advances_row_version(self):
        _src, _svc, before = self._rule_state()
        with mock.patch.object(cli, "_confirm_from_stdin", return_value=True):
            rc, _o, err = self._dispatch(
                ["set", "remote-access", "r1", "source", "src-b"]
            )
        self.assertEqual(rc, 0, err)
        src, _svc, after = self._rule_state()
        self.assertEqual(src, "src-b")
        self.assertGreater(after, before)

    def test_edit_during_confirmation_prompt_is_rejected(self):
        """Operator B reviews, A commits while B's prompt is open, B answers y."""
        calls = {"n": 0}

        def prompt_b_while_a_commits(_message):
            calls["n"] += 1
            # Operator A commits a different edit during B's prompt window.
            with mock.patch.object(cli, "_confirm_from_stdin", return_value=True):
                rc, _o, err = self._dispatch(
                    ["set", "remote-access", "r1", "source", "src-b"]
                )
            self.assertEqual(rc, 0, err)
            return True

        with mock.patch.object(cli, "_confirm_from_stdin", side_effect=prompt_b_while_a_commits):
            rc, _out, err = self._dispatch(
                ["set", "remote-access", "r1", "service", "svc-b"]
            )
        self.assertEqual(calls["n"], 1)
        self.assertEqual(rc, 1, "stale confirmed edit must fail closed")
        self.assertIn("changed while you were editing", err)
        self.assertIn("No changes were applied", err)
        src, svc, _ver = self._rule_state()
        self.assertEqual(src, "src-b", "A's committed edit must be preserved")
        self.assertEqual(svc, "svc-a", "B's stale edit must not be applied")

    def test_stale_expected_row_version_raises_concurrency_error(self):
        plane = ControlPlane(self.tmp)
        try:
            with self.assertRaises(ConfirmationRequired) as ctx:
                v24.set_access_rule(
                    plane, "remote-access", "r1", source="src-b", oneshot=True
                )
            reviewed = ctx.exception.impact["expected_row_version"]
        finally:
            plane.close()
        with mock.patch.object(cli, "_confirm_from_stdin", return_value=True):
            rc, _o, err = self._dispatch(["set", "remote-access", "r1", "service", "svc-b"])
        self.assertEqual(rc, 0, err)
        plane = ControlPlane(self.tmp)
        try:
            with self.assertRaises(ConcurrencyError):
                v24.set_access_rule(
                    plane, "remote-access", "r1", source="src-b", oneshot=True,
                    confirm=True, expected_row_version=reviewed,
                )
        finally:
            plane.close()

    def test_uncontended_confirmed_edit_still_succeeds(self):
        with mock.patch.object(cli, "_confirm_from_stdin", return_value=True):
            rc, _o, err = self._dispatch(
                ["set", "remote-access", "r1", "source", "src-b", "service", "svc-b"]
            )
        self.assertEqual(rc, 0, err)
        src, svc, _ver = self._rule_state()
        self.assertEqual((src, svc), ("src-b", "svc-b"))


if __name__ == "__main__":
    unittest.main()
