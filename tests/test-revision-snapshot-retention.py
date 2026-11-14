#!/usr/bin/env python3
"""OBS-P005 (option B) regression: bounded rollback-snapshot retention.

`revision_snapshots` stores one full ConfigurationBundle per config revision and made up ~85% of the 8.3 MB production
control DB (OBS-P005). Its size drives the O(DB size) integrity scan that the FRP access plugin runs per NewUserConn
(P-023). Retention keeps only the newest N rollback snapshots; the revision ledger (`config_revisions`) and the audit
trail stay complete, and the scan stays strict (no cache, no weaker check).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_control_plane as cp
from drlink_control_db import integrity_check
from drlink_control_plane import ControlPlane, ControlPlaneError

ENV = "DRLINK_REVISION_SNAPSHOT_RETENTION"


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class RevisionSnapshotRetention(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-snapretain-")
        _server_root(self.tmp)
        self.saved = {k: os.environ.get(k) for k in (ENV, "FRP_DEPLOY_TEST_ROOT", "DRLINK_SKIP_ACTIVATION")}
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ.pop(ENV, None)
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _write(self, count, size=0):
        revs = []
        for i in range(count):
            if size:
                with patch.object(
                    ControlPlane, "_capture_revision_configuration",
                    return_value=(("%06d" % i) + "x" * size, None),
                ):
                    with self.plane.conn:
                        revs.append(self.plane._write_revision("test", "rev %d" % i))
            else:
                with self.plane.conn:
                    revs.append(self.plane._write_revision("test", "rev %d" % i))
        return revs

    def _snapshot_revisions(self):
        return [r[0] for r in self.plane.conn.execute("SELECT revision FROM revision_snapshots ORDER BY revision")]

    def test_default_retention_is_bounded_and_documented(self):
        self.assertEqual(cp.REVISION_SNAPSHOT_RETENTION_DEFAULT, 100)
        self.assertEqual(cp.revision_snapshot_retention(), 100)

    def test_env_override_and_invalid_values(self):
        for raw, want in (("7", 7), ("0", 0), (" 12 ", 12), ("abc", 100), ("-3", 100), ("", 100), ("2.5", 100)):
            with self.subTest(raw=raw):
                os.environ[ENV] = raw
                self.assertEqual(cp.revision_snapshot_retention(), want)

    def test_keeps_newest_n_snapshots_and_full_ledger(self):
        os.environ[ENV] = "5"
        revs = self._write(12)
        self.assertEqual(self._snapshot_revisions(), revs[-5:])
        ledger = [r[0] for r in self.plane.conn.execute("SELECT revision FROM config_revisions ORDER BY revision")]
        self.assertEqual(ledger, revs, "the revision ledger must never be pruned")
        for rev in revs:  # ledger lookups still work for pruned revisions
            self.assertEqual(self.plane.revision_record(rev)["revision"], rev)

    def test_pruned_revision_reports_no_snapshot_and_newest_still_rolls_back(self):
        os.environ[ENV] = "3"
        revs = self._write(8)
        with self.assertRaises(ControlPlaneError) as ctx:
            self.plane.revision_snapshot(revs[0])
        self.assertIn("has no rollback snapshot", str(ctx.exception))
        self.assertIn("newest 3 revisions", str(ctx.exception))
        newest = self.plane.revision_snapshot(revs[-1])
        self.assertIsInstance(newest, dict)
        self.assertTrue(self.plane.revision_configuration(revs[-1]).strip())

    def test_zero_keeps_every_snapshot(self):
        os.environ[ENV] = "0"
        revs = self._write(9)
        self.assertEqual(self._snapshot_revisions(), revs)

    def test_fewer_revisions_than_retention_deletes_nothing(self):
        os.environ[ENV] = "50"
        revs = self._write(4)
        self.assertEqual(self._snapshot_revisions(), revs)

    def test_audit_events_are_untouched(self):
        os.environ[ENV] = "2"
        self.plane.conn.execute("PRAGMA foreign_keys=ON")
        with self.plane.conn:
            rev = self.plane._write_revision("test", "audited")
            self.plane._audit(
                revision=rev, action="x", entity_type="t", entity_id="1", operation="create",
            )
        before = self.plane.conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        self._write(6)
        after = self.plane.conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        self.assertEqual(before, after)

    def test_db_stays_healthy_after_pruning(self):
        os.environ[ENV] = "4"
        self._write(10)
        integrity_check(self.plane.conn)  # integrity_check + foreign_key_check, strict

    def test_snapshot_table_size_is_bounded_by_retention(self):
        """Deterministic stand-in for the scan-cost regression: stored snapshot bytes stop growing."""
        size = 40_000
        os.environ[ENV] = "3"
        self._write(30, size=size)
        total = self.plane.conn.execute("SELECT SUM(LENGTH(snapshot_json)) FROM revision_snapshots").fetchone()[0]
        self.assertLessEqual(total, 3 * (size + 4_096))
        os.environ[ENV] = "0"
        base = total
        self._write(10, size=size)
        grown = self.plane.conn.execute("SELECT SUM(LENGTH(snapshot_json)) FROM revision_snapshots").fetchone()[0]
        self.assertGreater(grown, base + 9 * size)

    def test_prune_rejects_non_positive_keep(self):
        for bad in (0, -1):
            with self.assertRaises(ControlPlaneError):
                with self.plane.conn:
                    self.plane._prune_revision_snapshots(bad)

    def test_restore_revision_advance_also_prunes(self):
        os.environ[ENV] = "2"
        revs = self._write(4)
        rev = self.plane.advance_restored_revision(revs[-1])
        self.assertGreater(rev, revs[-1])
        self.assertEqual(len(self._snapshot_revisions()), 2)
        self.assertIn(rev, self._snapshot_revisions())

    def test_prune_runs_inside_the_callers_transaction(self):
        os.environ[ENV] = "2"
        self._write(5)
        before = self._snapshot_revisions()
        # Production callers wrap _write_revision in BEGIN IMMEDIATE (the connection is autocommit).
        self.plane.conn.execute("BEGIN IMMEDIATE")
        try:
            self.plane._write_revision("test", "will roll back")
            self.assertNotEqual(self._snapshot_revisions(), before, "prune+insert happened in the open transaction")
        finally:
            self.plane.conn.execute("ROLLBACK")
        self.assertEqual(self._snapshot_revisions(), before, "a rolled-back change must not lose snapshots")


if __name__ == "__main__":
    unittest.main(verbosity=2)
