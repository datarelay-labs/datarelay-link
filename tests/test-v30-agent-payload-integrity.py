#!/usr/bin/env python3
"""Fail-closed Agent runtime payload/manifest integrity (offline only)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_agent_payload import (  # noqa: E402
    AGENT_LIB_FILES,
    RUNTIME_MANIFEST_NAME,
    verify_installed_lineage,
    verify_payload_match,
    write_installed_manifest,
)


class AgentPayloadIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-agent-integrity-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.source = base / "source"
        self.installed = base / "installed"
        self.source.mkdir()
        self.installed.mkdir()
        for name in AGENT_LIB_FILES:
            (self.source / name).write_bytes(("source:" + name).encode("utf-8"))
            (self.installed / name).write_bytes(("source:" + name).encode("utf-8"))

    def test_valid_manifest_and_absent_legacy_manifest_still_pass(self):
        self.assertEqual(verify_payload_match(self.source, self.installed), [])
        self.assertEqual(verify_installed_lineage(self.installed), [])
        write_installed_manifest(self.installed)
        self.assertEqual(verify_installed_lineage(self.installed), [])

    def test_installed_runtime_symlink_must_not_pass_byte_match(self):
        filename = "drlink_agent_lifecycle.py"
        destination = self.installed / filename
        destination.unlink()
        destination.symlink_to(self.source / filename)
        failures = verify_payload_match(self.source, self.installed)
        self.assertTrue(failures, "A symlink outside Agent lib passed payload verification")
        self.assertIn(filename, " ".join(failures))

    def test_manifest_write_must_not_follow_external_symlink(self):
        outside = Path(self.temp.name) / "unrelated-config"
        outside.write_text("DO_NOT_OVERWRITE\\n", encoding="utf-8")
        manifest = self.installed / RUNTIME_MANIFEST_NAME
        manifest.symlink_to(outside)
        write_installed_manifest(self.installed)
        self.assertEqual(outside.read_text(encoding="utf-8"), "DO_NOT_OVERWRITE\\n")
        self.assertFalse(manifest.is_symlink())
        self.assertEqual(verify_installed_lineage(self.installed), [])

    def test_manifest_rewrite_preserves_restrictive_permissions(self):
        write_installed_manifest(self.installed)
        manifest = self.installed / RUNTIME_MANIFEST_NAME
        manifest.chmod(0o600)
        write_installed_manifest(self.installed)
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)

    def test_present_corrupt_manifest_fails_closed_without_throwing(self):
        payload = write_installed_manifest(self.installed)
        manifest = self.installed / RUNTIME_MANIFEST_NAME
        malformed = {
            "wrong_top_level": "[]",
            "duplicate_files_key": '{"files": {}, ' + json.dumps(payload)[1:],
            "missing_schema": json.dumps({
                "files": payload["files"], "critical": payload["critical"]
            }),
            "wrong_critical": json.dumps({
                **payload, "critical": []
            }),
            "nonfinite": json.dumps(payload).replace('"schema": 1', '"schema": NaN'),
        }
        for name, text in malformed.items():
            with self.subTest(name=name):
                manifest.write_text(text, encoding="utf-8")
                problems = verify_installed_lineage(self.installed)
                self.assertTrue(problems, "Corrupt runtime manifest was accepted: " + name)
                self.assertIn("manifest", " ".join(problems).lower())


if __name__ == "__main__":
    unittest.main()
