"""FE2E-009/017: read-only public CLI must not contend for SQLite writer slot."""
from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_cli as cli
import drlink_v24 as v24
from drlink_control_db import db_path, open_control_db_readonly
from drlink_control_plane import ControlPlane


class ReadOnlyDbContentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-readonly-lock-")
        cfg = Path(self.tmp, "etc/drlink")
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.json").write_text('{"role":"server"}\n', encoding="utf-8")
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.seed = ControlPlane(self.tmp)
        v24.set_network_object(
            self.seed, "src", type="ip", value="198.51.100.10", oneshot=True
        )
        v24.set_network_object(
            self.seed, "dst", type="ip", value="198.51.100.20", oneshot=True
        )
        v24.set_service_object(self.seed, "ssh", type="tcp", port=22, oneshot=True)
        v24.set_access_rule(
            self.seed,
            "remote",
            "block-ssh",
            mode="blacklist",
            source="src",
            destination="dst",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        self.base_revision = self.seed.current_revision()

    def tearDown(self):
        self.seed.close()
        os.environ.pop("DRLINK_CONFIRM", None)

    def _writer_lock(self):
        conn = sqlite3.connect(str(db_path(self.tmp)), isolation_level=None, timeout=0.1)
        conn.execute("BEGIN IMMEDIATE")
        return conn

    def _dispatch_timed(self, tokens):
        out = io.StringIO()
        err = io.StringIO()
        started = time.monotonic()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(tokens, root=self.tmp)
        elapsed = time.monotonic() - started
        return rc, out.getvalue(), err.getvalue(), elapsed

    def test_read_only_connection_is_query_only_and_bounded_under_writer(self):
        writer = self._writer_lock()
        try:
            started = time.monotonic()
            conn = open_control_db_readonly(self.tmp)
            elapsed = time.monotonic() - started
            try:
                self.assertLess(elapsed, 2.0)
                self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
                self.assertEqual(
                    conn.execute("SELECT MAX(revision) FROM config_revisions").fetchone()[0],
                    self.base_revision,
                )
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute(
                        "INSERT INTO system_meta(key, value) VALUES ('readonly-probe', 'x')"
                    )
            finally:
                conn.close()
        finally:
            writer.execute("ROLLBACK")
            writer.close()
    def test_show_and_remote_access_test_do_not_wait_for_writer_slot(self):
        writer = self._writer_lock()
        try:
            rc, out, err, elapsed = self._dispatch_timed(["show", "status"])
            self.assertEqual(rc, 0, err)
            self.assertLess(elapsed, 2.0)
            self.assertIn("Data Relay Link", out)

            rc, out, err, elapsed = self._dispatch_timed(
                [
                    "test",
                    "remote-access",
                    "source",
                    "src",
                    "destination",
                    "dst",
                    "service",
                    "ssh",
                ]
            )
            self.assertEqual(rc, 0, err)
            self.assertLess(elapsed, 2.0)
            self.assertIn("DENY", out)
        finally:
            writer.execute("ROLLBACK")
            writer.close()

    def _legacy_bundle_path(self) -> Path:
        path = Path(self.tmp, "readonly-bundle.yaml")
        path.write_text(
            """apiVersion: drlink.datarelay.run/v1alpha1
kind: ConfigurationBundle
metadata:
  name: readonly-lock
spec:
  objects:
    - name: scratch-only
      type: Network
      values:
        - 192.0.2.10/32
  tests:
    - name: existing-remote-deny
      kind: remote-access
      source: 198.51.100.10
      destination: 198.51.100.20
      protocol: tcp
      port: 22
      expect: DENY
""",
            encoding="utf-8",
        )
        return path

    def test_legacy_bundle_test_and_diff_use_snapshot_not_authoritative_writer(self):
        bundle = self._legacy_bundle_path()
        writer = self._writer_lock()
        try:
            for tokens in (
                ["test", "configuration", str(bundle)],
                ["system", "diff", "configuration", str(bundle)],
            ):
                rc, out, err, elapsed = self._dispatch_timed(tokens)
                self.assertEqual(rc, 0, err)
                self.assertLess(elapsed, 2.0)
                self.assertIn("Configuration validation: PASS", out)
            self.assertEqual(self.seed.current_revision(), self.base_revision)
            self.assertIsNone(self.seed.get_object("scratch-only"))
        finally:
            writer.execute("ROLLBACK")
            writer.close()


if __name__ == "__main__":
    unittest.main()
