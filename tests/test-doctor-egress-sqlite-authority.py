#!/usr/bin/env python3
"""Current SQLite Internet Access diagnostics must not depend on obsolete JSON.

Exercise the real doctor and ControlPlane against isolated files/SQLite. Only
systemctl observations are mocked; no service, network, installer, or CLI E2E
is executed or claimed by this focused regression file.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "lib"))
import drlink_control_db as control_db
import drlink_control_plane as control_plane
import frp_doctor as doctor


class EgressSQLiteAuthorityTests(unittest.TestCase):
    HTTP_EFFECTIVE = "run/drlink/egress/effective.json"
    TCP_EFFECTIVE = "run/drlink/tcp-egress/effective.json"
    DB = "var/lib/drlink/drlink.db"
    LEGACY = "var/lib/drlink/egress-control.json"
    CONFIG = {
        "public_host": "203.0.113.10", "public_ip": "203.0.113.10",
        "deployment_mode": "direct", "egress_listen_addr": "192.0.2.10",
        "egress_listen_port": 6102, "port_start": 6000, "port_end": 6098,
    }

    def _root(self):
        directory = tempfile.TemporaryDirectory(prefix="drlink-doctor-sqlite-egress-")
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def _write(self, root, relative, text):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def _json(self, root, relative, value):
        return self._write(root, relative, json.dumps(value, sort_keys=True) + "\n")

    def _fixture(self):
        root = self._root()
        self._json(root, "etc/drlink/config.json", self.CONFIG)
        for unit in ("egress", "tcp-egress"):
            self._write(root, "etc/systemd/system/drlink-" + unit + ".service",
                        "[Service]\nUser=drlink-egress\n")
        self._write(root, "var/log/drlink/egress/connections.jsonl", "")
        plane = control_plane.ControlPlane(root=str(root))
        try:
            plane.compile_runtime()
            revision = plane.current_revision()
            # Prepare a closed, rollback-journal fixture before the read-only
            # baseline, so SQLite reader/WAL sidecar mechanics are not this test.
            plane.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            plane.conn.execute("PRAGMA journal_mode=DELETE")
        finally:
            plane.close()
        self._json(root, self.HTTP_EFFECTIVE, {
            "policy_healthy": True, "policy_generation": revision,
            "max_concurrent": 32, "per_source_limit": 16, "dns_pending_limit": 16,
        })
        self._json(root, self.TCP_EFFECTIVE, {"healthy": True, "policy_generation": revision})
        self.assertFalse((root / self.LEGACY).exists())
        return root

    def _tree(self, root):
        result = {}
        for path in [root, *sorted(root.rglob("*"))]:
            info = path.lstat()
            kind = "directory" if path.is_dir() else "file"
            content = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            result[str(path.relative_to(root))] = (
                kind, stat.S_IMODE(info.st_mode), info.st_mtime_ns, info.st_ctime_ns, content,
            )
        return result

    def _diagnose(self, root, config=None, active=None):
        config = dict(self.CONFIG if config is None else config)
        active = dict(active or {})
        calls = []

        def systemctl(argv, **kwargs):
            calls.append(list(argv))
            self.assertEqual(len(argv), 3)
            self.assertEqual(argv[0], "systemctl")
            self.assertIn(argv[1], ("is-active", "is-enabled"))
            self.assertIn(argv[2], ("drlink-egress", "drlink-tcp-egress"))
            value = active.get(argv[2], "active") if argv[1] == "is-active" else "enabled"
            return subprocess.CompletedProcess(argv, 0 if value in ("active", "enabled") else 3,
                                               value + "\n", "")

        env = {k: v for k, v in os.environ.items() if not k.startswith(("FRP_", "DRLINK_"))}
        env.update(FRP_DEPLOY_TEST_ROOT=str(root), FRP_DOCTOR_FORCE_SYSTEMD="1", FRP_SKIP_SYSTEMD="0",
                   FRP_EGRESS_LISTEN_ADDR="", FRP_EGRESS_LISTEN_PORT="")
        report = doctor.Report()
        before = self._tree(root)
        with patch.dict(os.environ, env, clear=True), patch("subprocess.run", side_effect=systemctl), \
                patch.object(control_plane, "open_control_db", side_effect=AssertionError("doctor used a writable ControlPlane")) as writable, \
                patch.object(control_plane, "open_control_db_readonly", wraps=control_plane.open_control_db_readonly) as readonly:
            try:
                doctor.check_egress_control(report, doctor.Paths(str(root)), {}, config)
            finally:
                self.assertEqual(before, self._tree(root), "doctor changed files, directories, permissions, timestamps, or SQLite state")
        writable.assert_not_called()  # A caught writable-open exception must not make a negative case pass.
        self.assertEqual(sorted(calls), sorted([
            ["systemctl", verb, unit]
            for unit in ("drlink-egress", "drlink-tcp-egress") for verb in ("is-active", "is-enabled")
        ]), "missing obsolete JSON must not skip current unit observations")
        self.assertFalse((root / self.LEGACY).exists(), "doctor must not manufacture obsolete policy state")
        return report, readonly.call_count

    def _check(self, report, check_id, status):
        rows = [row for row in report.checks if row["id"] == check_id]
        self.assertEqual(len(rows), 1, (check_id, report.checks))
        self.assertEqual(rows[0]["status"], status, rows[0])
        return rows[0]

    def test_missing_obsolete_json_keeps_current_sqlite_listener_units_and_runtime_checks(self):
        root = self._fixture()
        report, readonly_calls = self._diagnose(root)
        self.assertGreater(readonly_calls, 0, "authoritative policy must be examined through a read-only ControlPlane")
        for check_id in ("EGRESS_SQLITE_AUTHORITY", "EGRESS_LISTEN_BIND", "EGRESS_PORT_COLLISION",
                         "EGRESS_UNIT", "EGRESS_TCP_UNIT", "EGRESS_EFFECTIVE_CONFIG", "EGRESS_TCP_EFFECTIVE"):
            self._check(report, check_id, doctor.PASS)
        self._check(report, "EGRESS_LISTEN", doctor.INFO)
        self.assertEqual(report.overall(), "PASS", report.checks)

    def test_missing_obsolete_json_does_not_hide_wildcard_listener_warning(self):
        root = self._fixture()
        report, _ = self._diagnose(root, dict(self.CONFIG, egress_listen_addr="0.0.0.0"))
        self._check(report, "EGRESS_SQLITE_AUTHORITY", doctor.PASS)
        issue = self._check(report, "EGRESS_LISTEN_BIND", doctor.WARN)
        self.assertIn("installer-owned", issue["recommendation"])
        self.assertEqual(report.overall(), "PASS_WITH_WARNINGS")

    def test_missing_obsolete_json_does_not_hide_failed_units(self):
        for unit, check_id in (("drlink-egress", "EGRESS_UNIT"), ("drlink-tcp-egress", "EGRESS_TCP_UNIT")):
            with self.subTest(unit=unit):
                report, _ = self._diagnose(self._fixture(), active={unit: "failed"})
                self._check(report, "EGRESS_SQLITE_AUTHORITY", doctor.PASS)
                self._check(report, check_id, doctor.FAIL)
                self.assertEqual(report.overall(), "FAIL")

    def test_missing_obsolete_json_keeps_existing_bad_effective_snapshot_severities(self):
        for path, check_id, health_key in ((self.HTTP_EFFECTIVE, "EGRESS_EFFECTIVE_CONFIG", "policy_healthy"),
                                           (self.TCP_EFFECTIVE, "EGRESS_TCP_EFFECTIVE", "healthy")):
            for fault in ("missing", "malformed", "unhealthy"):
                with self.subTest(path=path, fault=fault):
                    root = self._fixture(); target = root / path
                    if fault == "missing": target.unlink()
                    elif fault == "malformed": target.write_text("{broken current runtime snapshot\n")
                    else:
                        data = json.loads(target.read_text()); data[health_key] = False
                        target.write_text(json.dumps(data) + "\n")
                    report, _ = self._diagnose(root)
                    status = doctor.WARN if path == self.TCP_EFFECTIVE and fault != "unhealthy" else doctor.FAIL
                    self._check(report, "EGRESS_SQLITE_AUTHORITY", doctor.PASS)
                    self._check(report, check_id, status)
                    self.assertNotEqual(report.overall(), "PASS", report.checks)

    def test_bad_current_authority_cannot_be_hidden_by_healthy_effective_snapshots(self):
        for fault in ("missing", "corrupt", "newer-schema", "older-schema", "missing-generation", "failed-generation", "mismatched-generation"):
            with self.subTest(fault=fault):
                root = self._fixture(); database = root / self.DB
                if fault == "missing": database.unlink()
                elif fault == "corrupt": database.write_bytes(b"not a SQLite control database\x00")
                else:
                    with sqlite3.connect(database) as conn:
                        if fault == "newer-schema":
                            conn.execute("INSERT INTO schema_migrations(version,name,applied_at) VALUES (?,?,?)",
                                         (control_db.SCHEMA_VERSION + 1, "future-fixture", "2099-01-01T00:00:00Z"))
                        elif fault == "older-schema":
                            conn.execute("DELETE FROM schema_migrations WHERE version >= ?", (control_db.SCHEMA_VERSION,))
                        elif fault == "missing-generation": conn.execute("DELETE FROM runtime_generations WHERE plane='internet'")
                        elif fault == "failed-generation": conn.execute("UPDATE runtime_generations SET status='failed' WHERE plane='internet'")
                        else: conn.execute("UPDATE runtime_generations SET generation=generation+1 WHERE plane='internet'")
                report, _ = self._diagnose(root)
                self._check(report, "EGRESS_SQLITE_AUTHORITY", doctor.FAIL)
                self._check(report, "EGRESS_UNIT", doctor.PASS)
                self._check(report, "EGRESS_TCP_UNIT", doctor.PASS)
                self.assertEqual(report.overall(), "FAIL", "saved healthy snapshots must not hide unhealthy current authority")

    def test_empty_root_reports_missing_authority_without_creating_any_state(self):
        root = self._root()
        report, _ = self._diagnose(root)
        self._check(report, "EGRESS_SQLITE_AUTHORITY", doctor.FAIL)
        self.assertEqual(report.overall(), "FAIL")
        self.assertEqual(list(root.iterdir()), [], "diagnostics must not initialize DB, config, legacy state, or runtime directories")


if __name__ == "__main__":
    unittest.main()
