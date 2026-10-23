#!/usr/bin/env python3
"""Agent Bundle revisions must not stale Server-only policy health on an Agent.

Real SQLite, role detection, Bundle prepare/apply and status methods are used.
Only disposable-root activation/management transport and the displayed unit
observation are isolated. These are focused regressions, not native E2E proof.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "lib"))
import drlink_control_plane as control_plane
import drlink_v24 as v24
import drlink_v24_bundle as bundle


class AgentStatusPolicyGenerationTests(unittest.TestCase):
    CREATE = """configurationBundle:
  context: agent
  remoteServices:
    - name: status-regression
      destination: this-host
      service: http
      enabled: false
"""
    REMOVE = """configurationBundle:
  context: agent
  remoteServices:
    - name: status-regression
      state: absent
"""

    def _write(self, root, relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n")

    def _fixture(self, role="agent", revision=38):
        directory = tempfile.TemporaryDirectory(prefix="drlink-agent-status-role-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FRP_", "DRLINK_"))}
        env.update(FRP_DEPLOY_TEST_ROOT=str(root), FRP_CTL_TEST_ROOT=str(root),
                   FRP_SKIP_SYSTEMD="1", DRLINK_SKIP_ACTIVATION="1", DRLINK_SERVER_REACHABLE="1")
        isolation = patch.dict(os.environ, env, clear=True)
        isolation.start(); self.addCleanup(isolation.stop)
        # Retain the real role detector while excluding this runner's macOS
        # state from an otherwise marker-free disposable-root fixture.
        mac_roots = patch.object(v24, "_macos_agent_state_roots",
                                 side_effect=lambda path=None: [Path(path) / "Library/Application Support/drlink"])
        mac_roots.start(); self.addCleanup(mac_roots.stop)
        management = patch("drlink_mgmt_sync.use_live_mgmt_path", return_value=False)
        management.start(); self.addCleanup(management.stop)
        if role == "agent":
            self._write(root, "etc/frp/client-state.json", {
                "machine_id": "a" * 32, "hostname": "status-agent", "host_id": "status-agent", "services": {},
            })
        elif role == "server":
            self._write(root, "etc/drlink/config.json", {"deployment_mode": "direct"})
        plane = control_plane.ControlPlane(root=str(root))
        self.addCleanup(plane.close)
        self._revision(plane, 36)
        plane.conn.execute("UPDATE runtime_generations SET db_revision=36, generation=36, error=''")
        if revision != 36:
            self._revision(plane, revision)
        self.assertEqual(v24.detect_cli_role(str(root)), role)
        return root, plane

    def _revision(self, plane, value):
        plane.conn.execute(
            "INSERT INTO config_revisions(revision, actor, command, created_at, summary) VALUES (?, ?, ?, ?, ?)",
            (value, "fixture", "fixture historical revision", "2026-10-20T00:00:00Z", "isolated revision seed"),
        )

    def _generations(self, plane):
        return [dict(r) for r in plane.conn.execute("SELECT * FROM runtime_generations ORDER BY plane")]

    def _render(self, plane, level="Healthy"):
        with patch.object(v24, "probe_agent_runtime_unit", return_value={
            "level": level, "detail": "isolated unit observation", "runtime_required": True,
        }), patch.object(v24, "detect_server_reachable", return_value=False):
            return plane.format_status()

    def _tree(self, root):
        out = {}
        for path in [root, *sorted(root.rglob("*"))]:
            info = path.lstat()
            out[str(path.relative_to(root))] = (
                stat.S_IMODE(info.st_mode), info.st_mtime_ns, info.st_ctime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            )
        return out

    def test_actual_agent_bundle_apply_and_cleanup_advance_37_38_without_server_policy_compile(self):
        _root, plane = self._fixture(revision=36)
        before = self._generations(plane)
        self.assertFalse(plane.status()["mismatch"])
        with patch.object(plane, "compile_runtime", side_effect=AssertionError("Agent Bundle must not compile Server policy")) as compiler:
            for expected, text in ((37, self.CREATE), (38, self.REMOVE)):
                plan = bundle.prepare_v24_plan(plane, text)
                result = bundle.apply_v24_plan(plane, plan, confirm=True)
                self.assertEqual(result, {"status": "APPLIED", "revision": expected})
                self.assertEqual(plane.current_revision(), expected)
                self.assertEqual(self._generations(plane), before, "Agent activation must not rewrite Server policy rows")
                with self.subTest(agent_bundle_revision=expected):
                    status = plane.status()
                    self.assertTrue(status["db_healthy"])
                    self.assertFalse(status["mismatch"], "Coherent Server policy generation36 is inapplicable to Agent Bundle37/38")
                    self.assertRegex(self._render(plane), r"(?m)^Control DB\s*:\s*Healthy\s*$")
            compiler.assert_not_called()
        self.assertIsNone(plane.conn.execute("SELECT name FROM agent_remote_services WHERE name='status-regression'").fetchone())

    def test_server_and_unknown_role_keep_existing_stale_active_warning(self):
        for role in ("server", "unknown"):
            with self.subTest(role=role):
                root, plane = self._fixture(role)
                if role == "server":
                    self._write(root, "etc/frp/client-state.json", {"services": {}})
                    self.assertEqual(v24.detect_cli_role(str(root)), "server", "Server marker must take precedence")
                status = plane.status()
                self.assertTrue(status["db_healthy"])
                self.assertTrue(status["mismatch"])

    def test_agent_exemption_preserves_existing_anomaly_warnings_only(self):
        _root, plane = self._fixture()
        cases = (
            ("explicit mismatch", "remote", 38, 38, "mismatch", "compile/activation failure"),
            ("future", "remote", 39, 39, "active", ""),
            ("split revisions", "remote", 38, 36, "active", ""),
            ("error-bearing lag", "remote", 36, 36, "active", "activation failed"),
            ("malformed generation", "remote", 36, "invalid", "active", ""),
            ("negative generation", "remote", -1, -1, "active", ""),
            ("unknown plane", "unexpected", 36, 36, "active", ""),
        )
        for label, name, db_revision, generation, status, error in cases:
            with self.subTest(case=label):
                plane.conn.execute("DELETE FROM runtime_generations WHERE plane='unexpected'")
                plane.conn.execute("UPDATE runtime_generations SET db_revision=36, generation=36, status='active', error='' WHERE plane='remote'")
                plane.conn.execute(
                    "INSERT OR REPLACE INTO runtime_generations(plane, db_revision, generation, status, error) VALUES (?, ?, ?, ?, ?)",
                    (name, db_revision, generation, status, error),
                )
                self.assertTrue(plane.status()["mismatch"], "Must retain the pre-existing warning: " + label)
                self.assertRegex(self._render(plane), r"(?m)^Control DB\s*:\s*Warning\s*$")
        # Scope guard: do not expand the old predicate to metadata anomalies
        # it did not flag when generation already equals current revision.
        plane.conn.execute("DELETE FROM runtime_generations WHERE plane='unexpected'")
        plane.conn.execute("UPDATE runtime_generations SET generation=38, db_revision=36, status='active', error='metadata-only' WHERE plane IN ('remote','internet')")
        self.assertFalse(plane.status()["mismatch"])

    def test_real_foreign_key_integrity_failure_remains_critical_on_agent(self):
        _root, plane = self._fixture()
        plane.conn.execute("PRAGMA foreign_keys=OFF")
        plane.conn.execute("INSERT INTO revision_snapshots(revision, snapshot_json) VALUES (999, '{}')")
        plane.conn.execute("PRAGMA foreign_keys=ON")
        self.assertFalse(plane.status()["db_healthy"])
        self.assertRegex(self._render(plane), r"(?m)^Control DB\s*:\s*Critical\s*$")

    def test_failed_agent_runtime_observation_is_not_hidden_by_healthy_control_db(self):
        _root, plane = self._fixture()
        text = self._render(plane, level="Critical")
        self.assertRegex(text, r"(?m)^Control DB\s*:\s*Healthy\s*$")
        self.assertRegex(text, r"(?m)^Agent Runtime\s*:\s*Critical — isolated unit observation\s*$")

    def test_readonly_status_keeps_all_fixture_files_and_generation_rows_unchanged(self):
        root, writer = self._fixture()
        expected = self._generations(writer)
        # Set up a closed rollback-journal fixture before the observation;
        # this is not a claim about live SQLite WAL/SHM byte immutability.
        writer.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.conn.execute("PRAGMA journal_mode=DELETE")
        writer.close()
        before = self._tree(root)
        with patch.object(control_plane, "open_control_db", side_effect=AssertionError("writable opener forbidden")) as writable:
            reader = control_plane.ControlPlane(root=str(root), read_only=True)
            try:
                self.assertEqual(reader.conn.execute("PRAGMA query_only").fetchone()[0], 1)
                self.assertFalse(reader.status()["mismatch"])
                self.assertRegex(self._render(reader), r"(?m)^Control DB\s*:\s*Healthy\s*$")
                self.assertEqual(self._generations(reader), expected)
            finally:
                reader.close()
            writable.assert_not_called()
        self.assertEqual(self._tree(root), before, "Status/role detection must not repair state or create runtime files")


if __name__ == "__main__":
    unittest.main()
