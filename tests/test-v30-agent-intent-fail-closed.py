#!/usr/bin/env python3
"""A corrupted persisted Agent lifecycle intent must not silently resume Jobs."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import drlink_agent_lifecycle as lifecycle


class PersistedLifecycleIntentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="drlink-agent-intent-")
        self.addCleanup(self.directory.cleanup)
        self.root = self.directory.name
        self.path = lifecycle.lifecycle_state_path(self.root)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def test_fresh_missing_state_defaults_to_running(self):
        self.assertEqual(lifecycle.load_lifecycle_intent(self.root), "running")

    def test_valid_running_and_paused_intents_round_trip(self):
        for intent in ("paused", "running"):
            with self.subTest(intent=intent):
                lifecycle.set_lifecycle_intent(intent, self.root)
                self.assertEqual(lifecycle.load_lifecycle_intent(self.root), intent)
        # Legacy, canonical intent-only state remains compatible.
        self.path.write_text('{"intent":"running"}\n', encoding="utf-8")
        self.assertEqual(lifecycle.load_lifecycle_intent(self.root), "running")

    def test_corrupt_present_state_fails_closed_without_heartbeat_or_jobs(self):
        invalid_documents = (
            "",
            '{"schema":1,"intent":',
            '{"schema":1,"intent":"unknown"}',
            '{"schema":1,"intent":""}',
            '{"schema":1,"intent":true}',
            '{"schema":1,"intent":1}',
            "null",
            "[]",
            '{"schema":2,"intent":"running"}',
            '{"schema":true,"intent":"running"}',
            '{"schema":1,"intent":"paused","intent":"running"}',
            '{"schema":1,"intent":"running","extra":NaN}',
            '{"schema":1,"intent":"running","extra":Infinity}',
        )
        for source in invalid_documents:
            with self.subTest(source=source):
                self.path.write_text(source, encoding="utf-8")
                self.assertEqual(lifecycle.load_lifecycle_intent(self.root), "paused")
                with mock.patch.object(
                    lifecycle, "heartbeat_once",
                    side_effect=AssertionError("corrupt state triggered heartbeat"),
                ) as heartbeat:
                    self.assertEqual(
                        lifecycle.reconcile_once(self.root),
                        {"status": "PAUSED", "updated": 0},
                    )
                    heartbeat.assert_not_called()

    def test_invalid_utf8_and_read_error_fail_closed(self):
        self.path.write_bytes(b"\xff\xfe")
        self.assertEqual(lifecycle.load_lifecycle_intent(self.root), "paused")
        with mock.patch.object(Path, "read_text", side_effect=OSError("read failed")):
            self.assertEqual(lifecycle.load_lifecycle_intent(self.root), "paused")


if __name__ == "__main__":
    unittest.main()
