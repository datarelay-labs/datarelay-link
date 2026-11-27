#!/usr/bin/env python3
"""Verify default runtime discovery selects the shipped target-native assets."""
from __future__ import annotations

import importlib.util
import hashlib
import contextlib
import io
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
        verifier, fixture, target = self._fresh_target_fixture()
        dirty_git = mock.Mock(side_effect=lambda *args: subprocess.CompletedProcess(
            [], 0, " M native/drlink-mcp-runtime/src/lib.rs\n", "")
            if args and args[0] == "status" else subprocess.CompletedProcess([], 0, "", ""))
        with mock.patch.object(verifier, "ROOT", fixture), \
                mock.patch.object(verifier, "git", dirty_git), \
                mock.patch.object(sys, "argv", ["verify-native-runtime-assets.py", "--target", target]):
            with self.assertRaisesRegex(SystemExit, "working-tree changes"):
                verifier.main()

    def _fresh_target_fixture(self):
        spec = importlib.util.spec_from_file_location(
            "native_runtime_verifier_fixture", ROOT / "scripts/verify-native-runtime-assets.py")
        verifier = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(verifier)
        temp = tempfile.TemporaryDirectory(prefix="native-target-provenance-")
        self.addCleanup(temp.cleanup)
        fixture = Path(temp.name)
        target = "x86_64-unknown-linux-gnu"
        target_dir = fixture / "lib/native" / target
        target_dir.mkdir(parents=True)
        files = {
            "scripts/build-native-runtime-assets.sh": b"build script",
            "native/drlink-egress/Cargo.lock": b"egress lock",
            "native/drlink-mcp-runtime/Cargo.lock": b"mcp lock",
        }
        for relative, content in files.items():
            path = fixture / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        libraries = {}
        for name, content in (("libdrlink_egress.so", b"egress library"),
                              ("libdrlink_mcp_runtime.so", b"mcp library")):
            (target_dir / name).write_bytes(content)
            libraries[name] = hashlib.sha256(content).hexdigest()
        record = {
            "target": target,
            "source_head": "a" * 40,
            "cargo_locks": {
                "drlink-egress": hashlib.sha256(files["native/drlink-egress/Cargo.lock"]).hexdigest(),
                "drlink-mcp-runtime": hashlib.sha256(files["native/drlink-mcp-runtime/Cargo.lock"]).hexdigest(),
            },
            "build_script": hashlib.sha256(files["scripts/build-native-runtime-assets.sh"]).hexdigest(),
            "libraries": libraries,
        }
        (target_dir / "runtime-build.json").write_text(json.dumps(record), encoding="utf-8")
        return verifier, fixture, target

    def test_target_scoped_verifier_accepts_one_fresh_matrix_package(self):
        verifier, fixture, target = self._fresh_target_fixture()
        with mock.patch.object(verifier, "ROOT", fixture), \
                mock.patch.object(verifier, "git", return_value=subprocess.CompletedProcess([], 0, "", "")), \
                mock.patch.object(sys, "argv", ["verify-native-runtime-assets.py", "--target", target]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(verifier.main(), 0)
        self.assertIn("mode=target", output.getvalue())

    def test_full_provenance_verifier_still_requires_every_supported_target(self):
        spec = importlib.util.spec_from_file_location(
            "native_runtime_verifier_full_test", ROOT / "scripts/verify-native-runtime-assets.py")
        verifier = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory(prefix="native-full-provenance-") as temp, \
                mock.patch.object(verifier, "ROOT", Path(temp)), \
                mock.patch.object(sys, "argv", ["verify-native-runtime-assets.py"]), \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(verifier.main(), 1)
        self.assertIn("target(s) missing", error.getvalue())


if __name__ == "__main__":
    unittest.main()
