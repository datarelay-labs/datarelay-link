#!/usr/bin/env python3
"""Verify default runtime discovery selects the shipped target-native assets."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
machine = platform.machine().lower()
if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
    TARGET, EXTENSION = "x86_64-unknown-linux-gnu", "so"
elif sys.platform.startswith("linux") and machine in ("aarch64", "arm64"):
    TARGET, EXTENSION = "aarch64-unknown-linux-gnu", "so"
elif sys.platform == "darwin" and machine in ("arm64", "aarch64"):
    TARGET, EXTENSION = "aarch64-apple-darwin", "dylib"
else:
    TARGET, EXTENSION = "", ""
NATIVE = ROOT / "lib/native" / TARGET if TARGET else ROOT / "lib/native/unsupported"
EGRESS_LIBRARY = NATIVE / ("libdrlink_egress." + EXTENSION)
MCP_LIBRARY = NATIVE / ("libdrlink_mcp_runtime." + EXTENSION)
SUPPORTED_RUNNER = bool(TARGET)


def load_runtime(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(SUPPORTED_RUNNER, "packaged native assets for this platform")
class PackagedRuntimeSelectionTests(unittest.TestCase):
    def test_default_egress_selector_loads_shipped_runtime(self):
        self.assertTrue(EGRESS_LIBRARY.is_file())
        runtime = load_runtime("packaged_egress_runtime_test", "lib/frp_egress_runtime.py")
        with mock.patch.dict(os.environ, {"DRLINK_EGRESS_RUNTIME": "rust"}, clear=False):
            os.environ.pop("DRLINK_EGRESS_NATIVE_LIBRARY", None)
            runtime._NATIVE_RELAY = None
            runtime._NATIVE_RELAY_CHECKED = False
            relay = runtime._native_relay()
        self.assertIsNotNone(relay)

    def test_build_record_matches_shipped_libraries_and_locked_toolchain(self):
        record_path = NATIVE / "runtime-build.json"
        self.assertTrue(record_path.is_file())
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["target"], TARGET)
        self.assertEqual(record["rustc"], "1.75.0")
        for name, expected in record["libraries"].items():
            actual = hashlib.sha256((NATIVE / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)

    def test_default_mcp_selector_loads_shipped_runtime(self):
        self.assertTrue(MCP_LIBRARY.is_file())
        runtime = load_runtime("packaged_mcp_runtime_test", "lib/drlink_mcp_runtime.py")
        with mock.patch.dict(os.environ, {"DRLINK_MCP_RUNTIME": "rust"}, clear=False):
            os.environ.pop("DRLINK_MCP_NATIVE_LIBRARY", None)
            runtime._PROCESS_CHECKED = False
            runtime._PROCESS_DRAIN = None
            drain = runtime._native_process_drain()
        self.assertIsNotNone(drain)

    def test_provenance_verifier_rejects_uncommitted_native_source(self):
        source_dir = ROOT / "native/drlink-egress/src"
        with tempfile.NamedTemporaryFile(prefix=".provenance-drift-", suffix=".rs",
                                         dir=source_dir) as drift:
            drift.write(b"// uncommitted native build input\n")
            drift.flush()
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/verify-native-runtime-assets.py")],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("working-tree changes", result.stderr)


if __name__ == "__main__":
    unittest.main()
