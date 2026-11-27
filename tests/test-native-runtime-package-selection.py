#!/usr/bin/env python3
"""Verify default runtime discovery selects the shipped Linux x86_64 assets."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import platform
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "lib/native/x86_64-unknown-linux-gnu"
EGRESS_LIBRARY = NATIVE / "libdrlink_egress.so"
MCP_LIBRARY = NATIVE / "libdrlink_mcp_runtime.so"
SUPPORTED_RUNNER = sys.platform.startswith("linux") and platform.machine() in ("x86_64", "amd64")


def load_runtime(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(SUPPORTED_RUNNER, "packaged Linux x86_64 native assets")
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
        self.assertEqual(record["target"], "x86_64-unknown-linux-gnu")
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


if __name__ == "__main__":
    unittest.main()
