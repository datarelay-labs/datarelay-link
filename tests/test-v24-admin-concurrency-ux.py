#!/usr/bin/env python3
"""Regression for public admin object concurrency and stale Bundle review UX."""
from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from drlink_control_plane import ConcurrencyError, ControlPlane
import drlink_v24 as v24
from drlink_v24_bundle import export_configuration_v24, format_v24_plan, prepare_v24_plan


class AdminConcurrencyUxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-admin-concurrency-")
        root = Path(self.tmp.name)
        (root / "etc/drlink").mkdir(parents=True)
        (root / "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")
        self.plane = ControlPlane(self.tmp.name)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_network_object(self.plane, "e2e-race", type="ip", value="192.0.2.10", oneshot=True)

    def tearDown(self):
        self.plane.close()
        self.tmp.cleanup()

    def test_two_prepared_concurrent_edits_cannot_both_succeed(self):
        before = self.plane.current_revision()
        barrier = threading.Barrier(2)
        original = ControlPlane._mutate

        def synchronized(plane, command, *args, **kwargs):
            if str(command).startswith("set object e2e-race value "):
                barrier.wait(timeout=10)
            return original(plane, command, *args, **kwargs)

        def edit(value):
            plane = ControlPlane(self.tmp.name)
            try:
                return v24.set_network_object(plane, "e2e-race", value=value, oneshot=True)
            except Exception as exc:
                return exc
            finally:
                plane.close()

        with mock.patch.object(ControlPlane, "_mutate", synchronized), ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(edit, ("192.0.2.11", "192.0.2.12")))

        self.assertEqual(sum(isinstance(r, dict) for r in results), 1, results)
        failures = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(len(failures), 1, results)
        self.assertIsInstance(failures[0], ConcurrencyError)
        self.assertEqual(self.plane.current_revision(), before + 1)
        values = self.plane._object_values(self.plane.require_object("e2e-race")["id"])
        self.assertIn(values, (["192.0.2.11"], ["192.0.2.12"]))

    def test_network_wizard_rejects_edit_committed_after_review_started(self):
        import drlink_v24_wizard as wizard
        from drlink_control_db import ControlPlaneError

        class ConcurrentEditIO(wizard.ScriptedIO):
            def __init__(self, root):
                super().__init__(["1", "192.0.2.12", "1"])
                self.root = root
                self.changed = False

            def ask(self, prompt=""):
                if prompt == "Select: " and not self.changed:
                    other = ControlPlane(self.root)
                    try:
                        v24.set_network_object(
                            other, "e2e-race", value="192.0.2.11", oneshot=True
                        )
                    finally:
                        other.close()
                    self.changed = True
                return super().ask(prompt)

        initial_revision = self.plane.current_revision()
        io = ConcurrentEditIO(self.tmp.name)
        wizard.set_wizard_io(io)
        try:
            with self.assertRaisesRegex(ControlPlaneError, "(?i)changed|conflict|revision"):
                wizard.run_network_object_wizard(self.plane, "e2e-race")
        finally:
            wizard.set_wizard_io(None)
        self.assertTrue(io.changed)
        self.assertEqual(self.plane.current_revision(), initial_revision + 1)
        self.assertEqual(
            self.plane._object_values(self.plane.require_object("e2e-race")["id"]),
            ["192.0.2.11"],
        )

    def test_referenced_service_object_port_change_needs_confirmation(self):
        from drlink_control_plane import ConfirmationRequired

        v24.set_service_object(
            self.plane, "test-service", type="tcp", port=22, oneshot=True
        )
        self.plane.conn.execute(
            "INSERT INTO agent_remote_services "
            "(name, destination, service_object, enabled, updated_at) "
            "VALUES ('test-rs', 'this-host', 'test-service', 1, '2026-11-01T00:00:00Z')"
        )
        before = self.plane.current_revision()
        with self.assertRaisesRegex(ConfirmationRequired, "(?i)reference|remote service"):
            v24.set_service_object(
                self.plane, "test-service", type="tcp", port=2222,
                oneshot=True,
            )
        self.assertEqual(self.plane.current_revision(), before)
        self.assertEqual(v24.get_service_object(self.plane, "test-service")["port"], 22)
        v24.set_service_object(
            self.plane, "test-service", type="tcp", port=2222,
            oneshot=True, confirm=True,
        )
        self.assertEqual(v24.get_service_object(self.plane, "test-service")["port"], 2222)

    def test_stale_noop_with_explicit_object_version_rejects(self):
        previous = int(self.plane.require_object("e2e-race")["row_version"])
        v24.set_network_object(self.plane, "e2e-race", value="192.0.2.11", oneshot=True)
        before = self.plane.current_revision()
        with self.assertRaises(ConcurrencyError):
            self.plane.replace_object_value(
                "e2e-race", "192.0.2.11", expected_row_version=previous
            )
        self.assertEqual(self.plane.current_revision(), before)

    def test_public_object_detail_exposes_current_revision(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        import drlink_control_cli as cli
        stdout, stderr = io.StringIO(), io.StringIO()
        revision = self.plane.current_revision()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = cli.dispatch(
                ["show", "network-object", "e2e-race"], root=self.tmp.name,
                plane=self.plane,
            )
        self.assertEqual(rc, 0, stderr.getvalue())
        self.assertIn("Configuration revision: %d" % revision, stdout.getvalue())

    def test_stale_configuration_review_explicitly_warns(self):
        snapshot = export_configuration_v24(self.plane)
        fresh = format_v24_plan(prepare_v24_plan(self.plane, snapshot, role="server"))
        self.assertNotIn("STALE_CONFIGURATION_REVISION", fresh)
        prior = self.plane.current_revision()
        v24.set_network_object(self.plane, "e2e-race", value="192.0.2.20", oneshot=True)
        current = self.plane.current_revision()
        stale = format_v24_plan(prepare_v24_plan(self.plane, snapshot, role="server"))
        self.assertIn("STALE_CONFIGURATION_REVISION", stale)
        self.assertIn("Base revision: %d" % prior, stale)
        self.assertIn("Current revision: %d" % current, stale)
        self.assertIn("No changes were applied", stale)


if __name__ == "__main__":
    unittest.main()
