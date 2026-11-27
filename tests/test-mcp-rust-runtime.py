#!/usr/bin/env python3
"""Focused Rust/Python bounded dispatch admission contract tests."""
from __future__ import annotations

import importlib.util
import os
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "native/drlink-mcp-runtime/target/release/libdrlink_mcp_runtime.so"
spec = importlib.util.spec_from_file_location("drlink_mcp_runtime_test", ROOT / "lib/drlink_mcp_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class PythonDispatchBudgetTests(unittest.TestCase):
    def test_fallback_enforces_bound_and_releases(self):
        with mock.patch.dict(os.environ, {"DRLINK_MCP_RUNTIME": "python"}):
            budget = runtime.DispatchBudget(2)
        self.assertTrue(budget.try_acquire())
        self.assertTrue(budget.try_acquire())
        self.assertFalse(budget.try_acquire())
        budget.release()
        self.assertTrue(budget.try_acquire())
        self.assertEqual(budget.inflight, 2)


@unittest.skipUnless(LIBRARY.is_file(), "build the locked Rust MCP runtime library first")
class RustDispatchBudgetTests(unittest.TestCase):
    def test_rust_enforces_bound_and_release_restores_capacity(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            budget = runtime.DispatchBudget(3)
        self.assertTrue(budget.try_acquire())
        self.assertTrue(budget.try_acquire())
        self.assertTrue(budget.try_acquire())
        self.assertFalse(budget.try_acquire())
        budget.release()
        self.assertTrue(budget.try_acquire())
        self.assertEqual(budget.inflight, 3)
        while budget.inflight:
            budget.release()
        budget.close()

    def test_rust_atomic_admission_never_exceeds_limit_under_contention(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            budget = runtime.DispatchBudget(8)
        barrier = threading.Barrier(33)
        admitted = []
        lock = threading.Lock()

        def take_slot():
            barrier.wait()
            if budget.try_acquire():
                with lock:
                    admitted.append(True)

        threads = [threading.Thread(target=take_slot) for _ in range(32)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(len(admitted), 8)
        self.assertEqual(budget.inflight, 8)
        for _ in admitted:
            budget.release()
        budget.close()


if __name__ == "__main__":
    unittest.main()
