#!/usr/bin/env python3
"""LPERF-4: opt-in Bridge worker auto-tuning must stay resource-bounded.

These tests never start or mutate an installed systemd unit.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import drlink_mcp_bridge as mcp  # noqa: E402


class WorkerSelectionTests(unittest.TestCase):
    def test_unset_keeps_backward_compatible_one_worker_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(mcp._worker_count(os.environ.get("DRLINK_MCP_WORKERS", "1")), 1)

    def test_auto_selects_six_only_on_large_cpu_memory_host(self):
        with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(10))):
            with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=8 * 1024 ** 3):
                self.assertEqual(mcp._worker_count("auto"), 6)
                self.assertEqual(mcp._worker_count(" AUTO "), 6)

    def test_auto_caps_small_cpu_and_memory(self):
        with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=8 * 1024 ** 3):
            for cores, expected in [(1, 1), (2, 1), (3, 1), (4, 2), (7, 2), (8, 6), (40, 6)]:
                with self.subTest(cores=cores):
                    with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(cores))):
                        self.assertEqual(mcp._worker_count("auto"), expected)
        with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(20))):
            with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=1024 ** 3):
                self.assertEqual(mcp._worker_count("auto"), 1)
            with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=0):
                self.assertEqual(mcp._worker_count("auto"), 1)

    def test_explicit_values_always_take_precedence(self):
        with mock.patch.object(mcp.os, "sched_getaffinity", return_value={0, 1}):
            self.assertEqual(mcp._worker_count("6"), 6)
            self.assertEqual(mcp._worker_count("1"), 1)
            self.assertEqual(mcp._worker_count("9999"), mcp.MAX_WORKERS)
            self.assertEqual(mcp._worker_count("invalid"), 1)

    def test_cgroup_memory_ceiling_is_respected(self):
        # Patch only the reads, avoiding dependence on this host's cgroup.
        original = Path.read_text
        def fake_read(path, *args, **kwargs):
            name = str(path)
            if name == "/proc/meminfo":
                return "MemTotal:  8192000 kB\n"
            if name == "/sys/fs/cgroup/memory.max":
                return str(1024 ** 3) + "\n"
            if name == "/sys/fs/cgroup/memory/memory.limit_in_bytes":
                raise OSError("not available")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "read_text", new=fake_read):
            self.assertEqual(mcp._worker_memory_limit_bytes(), 1024 ** 3)


if __name__ == "__main__":
    unittest.main()
