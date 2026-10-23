#!/usr/bin/env python3
"""Public audit must expose existing configuration history without changing it.

The real public grammar/dispatcher reads real SQLite and JSONL fixtures under
disposable roots. These focused regressions are not installed-host E2E proof.
Only missing/broken reader fault injection uses the handler directly.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "lib"))
import drlink_control_db as db


class PublicAuditControlHistory(unittest.TestCase):
    HOST_A = "aaaaaaaa11111111aaaaaaaa11111111"
    HOST_B = "bbbbbbbb22222222bbbbbbbb22222222"
    SECRET = "AUDIT_PRIVATE_PAYLOAD_MUST_NOT_APPEAR"

    def _fixture(self, database=True):
        directory = tempfile.TemporaryDirectory(prefix="drlink-public-audit-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        registry = root / "var/lib/drlink/registry.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({
            "schema_version": 2, "groups": {}, "reserved": [], "clients": {
                self.HOST_A: {"hostname": "audit-gateway", "label": "audit-label", "services": {}},
                self.HOST_B: {"hostname": "other-gateway", "services": {}},
            },
        }) + "\n")
        config = root / "etc/drlink/config.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({
            "deployment_mode": "direct", "public_host": "203.0.113.10",
            "registry_file": str(registry),
        }) + "\n")
        runtime = root / "var/lib/drlink/runtime"
        runtime.mkdir()
        (runtime / "generation.json").write_text('{"revision":161,"fixture":true}\n')
        conn = db.open_control_db(str(root)) if database else None
        if conn is not None:
            self.addCleanup(conn.close)
        return root, conn

    def _env(self, root):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FRP_", "DRLINK_"))}
        env.update(FRP_DEPLOY_TEST_ROOT=str(root), FRP_CTL_TEST_ROOT=str(root),
                   FRP_CTL_BIN_DIR=str(ROOT / "tools"), FRP_CTL_FORCE_DRLINK="1",
                   FRP_SKIP_SYSTEMD="1", DRLINK_SKIP_ACTIVATION="1",
                   PYTHONDONTWRITEBYTECODE="1")
        return env

    def _run(self, root, *args):
        return subprocess.run(
            ["bash", str(ROOT / "tools/frpctl"), "system", "audit", *args],
            env=self._env(root), capture_output=True, text=True, timeout=20,
        )

    def _json(self, root, *args):
        result = self._run(root, *args, "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(result.stdout.strip().startswith("("),
                         "Expected JSON audit records, got: " + result.stdout)
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def _legacy(self, root, records):
        path = root / "var/log/drlink/audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in records))

    def _event(self, conn, revision=152, timestamp="2026-10-20T08:58:40Z", **overrides):
        row = {
            "timestamp": timestamp, "revision": revision, "actor": "audit-operator",
            "action": "system rollback 147", "entity_type": "configuration-bundle",
            "entity_id": "audit-owned-bundle", "operation": "APPLIED", "result": "ok",
            "before_summary": self.SECRET, "after_summary": self.SECRET,
            "impact_summary": json.dumps({"raw_bundle": self.SECRET}),
        }
        row.update(overrides)
        conn.execute(
            "INSERT OR IGNORE INTO config_revisions(revision,actor,command,created_at,summary) "
            "VALUES (?,?,?,?,?)",
            (revision, "fixture", "fixture revision", timestamp, "fixture"),
        )
        columns = list(row)
        conn.execute(
            "INSERT INTO audit_events(%s) VALUES (%s)" %
            (",".join(columns), ",".join("?" for _ in columns)),
            [row[key] for key in columns],
        )

    def _preserved(self, root):
        """Compare persistent content/metadata; SQLite SHM read marks are excluded."""
        out = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.endswith("-shm"):
                continue
            info = path.stat()
            out[str(path.relative_to(root))] = (
                stat.S_IMODE(info.st_mode), info.st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        return out

    def test_db_only_history_exposes_revision_actor_and_rollback_target(self):
        root, conn = self._fixture()
        self._event(conn)
        table = self._run(root)
        self.assertEqual(table.returncode, 0, table.stdout + table.stderr)
        for value in ("REVISION", "ACTOR", "152", "audit-operator", "system rollback 147"):
            self.assertIn(value, table.stdout)
        rows = self._json(root)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], "control-db")
        self.assertEqual(row["revision"], 152)
        self.assertEqual(row["actor"], "audit-operator")
        self.assertEqual(row["event"], "system rollback 147")
        self.assertEqual(row["result"], "APPLIED")
        self.assertNotIn(self.SECRET, table.stdout + json.dumps(rows))

    def test_global_last_merges_both_feeds_in_timestamp_order(self):
        root, conn = self._fixture()
        self._event(conn, 11, "2026-10-20T09:01:00+09:00", entity_id="control-one")
        self._event(conn, 12, "2026-10-20T00:03:00Z", entity_id="control-three")
        self._legacy(root, [
            {"ts": "2026-10-20T00:02:00Z", "event": "backup.created", "target": "legacy-two"},
            {"ts": "2026-10-20T00:00:00Z", "event": "backup.created", "target": "legacy-zero"},
        ])
        rows = self._json(root, "last", "3")
        self.assertEqual([row["target"] for row in rows], ["control-one", "legacy-two", "control-three"])
        table = self._run(root, "last", "3")
        self.assertEqual(table.returncode, 0, table.stderr)
        lines = table.stdout.splitlines()
        self.assertIn("TIME (UTC)", lines[0])
        self.assertEqual([line[:19] for line in lines[1:]], [
            "2026-10-20 00:01:00", "2026-10-20 00:02:00", "2026-10-20 00:03:00",
        ])

    def test_filters_precede_global_limit_without_recent_200_or_500_row_cutoff(self):
        root, conn = self._fixture()
        self._event(conn, 1, "2026-10-20T00:00:00Z", action="system rollback 1")
        start = datetime(2026, 10, 20, tzinfo=timezone.utc)
        for revision in range(2, 603):
            stamp = (start + timedelta(seconds=revision)).isoformat()
            self._event(conn, revision, stamp, action="set object fixture value 192.0.2.1",
                        entity_type="object", entity_id="fixture", operation="replace")
        rows = self._json(root, "event", "rollback", "last", "1")
        self.assertEqual([row["revision"] for row in rows], [1])
        capped = self._json(root, "last", "999")
        self.assertEqual(len(capped), 500)
        self.assertEqual(capped[0]["revision"], 103)
        self.assertEqual(capped[-1]["revision"], 602)

    def test_managed_host_id_hostname_and_label_keep_legacy_and_control_matches(self):
        root, conn = self._fixture()
        self._event(conn, entity_type="client", entity_id=self.HOST_A,
                    action="set client fixture", operation="update")
        self._legacy(root, [
            {"ts": "2026-10-20T08:59:00Z", "event": "group.member_added", "client_id": self.HOST_A},
            {"ts": "2026-10-20T09:00:00Z", "event": "group.member_added", "client_id": self.HOST_B},
        ])
        for selector in (self.HOST_A[:8], "audit-gateway", "audit-label"):
            with self.subTest(selector=selector):
                rows = self._json(root, "managed-host", selector)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["revision"], 152)
                self.assertEqual(rows[1]["client_id"], self.HOST_A)
                self.assertNotIn(self.HOST_B, json.dumps(rows))

    def test_missing_db_preserves_legacy_json_and_does_not_initialize_database(self):
        root, _conn = self._fixture(database=False)
        records = [
            {"ts": "2026-10-20T00:01:00Z", "event": "backup.created", "details": {"path": "/private/backup.tgz"}},
            {"ts": "2026-10-20T00:02:00Z", "event": "group.member_added", "client_id": self.HOST_A},
        ]
        self._legacy(root, records)
        before = self._preserved(root)
        self.assertEqual(self._json(root), records)
        self.assertEqual(self._preserved(root), before)
        self.assertFalse((root / "var/lib/drlink/drlink.db").exists())

    def test_read_only_during_open_writer_preserves_database_wal_and_runtime(self):
        root, conn = self._fixture()
        self._event(conn)
        conn.execute("BEGIN IMMEDIATE")
        self._event(conn, revision=153, action="set object not-committed", entity_type="object")
        before = self._preserved(root)
        self.assertIn("var/lib/drlink/drlink.db-wal", before)
        rows = self._json(root)
        self.assertEqual([row["revision"] for row in rows], [152])
        self.assertTrue(conn.in_transaction, "The existing writer transaction must remain open")
        self.assertEqual(self._preserved(root), before)
        conn.rollback()

    def test_existing_unreadable_or_incompatible_db_never_silently_returns_legacy_only(self):
        for condition in ("corrupt", "future", "old", "missing-audit-table"):
            with self.subTest(condition=condition):
                root, conn = self._fixture()
                self._event(conn)
                self._legacy(root, [{"ts": "2026-10-20T09:00:00Z", "event": "backup.created"}])
                if condition == "future":
                    conn.execute("UPDATE schema_migrations SET version=99 WHERE version=2")
                elif condition == "old":
                    conn.execute("DELETE FROM schema_migrations WHERE version>1")
                elif condition == "missing-audit-table":
                    conn.execute("DROP TABLE audit_events")
                # Error-path fixtures use DELETE journaling so SQLite's
                # read-side WAL/SHM bookkeeping is not mistaken for mutation.
                # Live WAL preservation is tested separately with a writer open.
                conn.execute("PRAGMA journal_mode=DELETE")
                conn.close()
                if condition == "corrupt":
                    (root / "var/lib/drlink/drlink.db").write_bytes(self.SECRET.encode())
                before = self._preserved(root)
                result = self._run(root, "json")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("Control DB audit", result.stderr)
                self.assertEqual(result.stdout, "", "Do not print a partial feed as if complete")
                self.assertNotIn(self.SECRET, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self._preserved(root), before)

    def test_projection_omits_payloads_and_makes_terminal_metadata_safe(self):
        root, conn = self._fixture()
        self._event(conn, actor="operator\x1b[31m", entity_id="owned\nforged-event",
                    action="set object fixture credential " + self.SECRET,
                    entity_type="object", result=self.SECRET, operation=self.SECRET)
        records = self._json(root)
        self.assertEqual(len(records), 1)
        row = records[0]
        self.assertEqual(set(row), {"source", "id", "timestamp", "event", "target", "revision", "actor", "result"})
        self.assertEqual(row["event"], "set network-object")
        self.assertEqual(row["actor"], "-")
        self.assertEqual(row["target"], "-")
        self.assertEqual(row["result"], "unknown")
        self.assertNotIn(self.SECRET, json.dumps(records))
        self._legacy(root, [{"ts": "2026-10-20T09:00:00Z", "event": "event\x1b[31m\nforged", "target": "host\rforged"}])
        table = self._run(root)
        self.assertEqual(table.returncode, 0, table.stderr)
        self.assertNotIn("\x1b", table.stdout)
        self.assertNotIn("\r", table.stdout)
        self.assertNotIn(self.SECRET, table.stdout)
        self.assertEqual(len(table.stdout.splitlines()), 3)

    def test_missing_or_broken_reader_fails_closed_without_disclosing_import_error(self):
        root, conn = self._fixture()
        self._event(conn)
        self._legacy(root, [{"event": "backup.created"}])
        broken = root / "broken-reader.py"
        broken.write_text("raise RuntimeError(%r)\n" % self.SECRET)
        source = (ROOT / "tools/frpctl").read_text()
        function = "frpctl_audit_tail() {" + source.split("frpctl_audit_tail() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
        script = '''frpctl_lib_candidate() {
  if [[ "$1" == "drlink_control_db.py" && -n "$AUDIT_FAULT_READER" ]]; then
    printf '%s\\n' "$AUDIT_FAULT_READER"
  else
    return 1
  fi
}
''' + function + "\nfrpctl_audit_tail json\n"
        for reader in ("", str(broken)):
            with self.subTest(reader="missing" if not reader else "broken"):
                env = self._env(root)
                env["AUDIT_FAULT_READER"] = reader
                before = self._preserved(root)
                result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("Control DB audit", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertNotIn(self.SECRET, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self._preserved(root), before)

    def test_bundle_rejection_outcome_and_empty_filters_are_not_false_successes(self):
        root, conn = self._fixture()
        self._event(conn, action="system apply configuration", operation="REVISION_CONFLICT", result="ok")
        rows = self._json(root, "event", "apply")
        self.assertEqual(rows[0]["result"], "REVISION_CONFLICT")
        result = self._run(root, "event", "event-that-does-not-exist")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "(no matching audit events)")


if __name__ == "__main__":
    unittest.main()
