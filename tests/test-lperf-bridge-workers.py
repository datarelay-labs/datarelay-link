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
    def test_cpu_quota_v2_subgroup_and_parent_override_affinity(self):
        files = self._cgroup_v2_fixture(
            child=str(8 * 1024 ** 3), parent=str(8 * 1024 ** 3)
        )
        files.update({
            "/sys/fs/cgroup/system.slice/drlink-mcp-bridge.service/cpu.max": "100000 100000\n",
            "/sys/fs/cgroup/system.slice/cpu.max": "max 100000\n",
            "/sys/fs/cgroup/cpu.max": "max 100000\n",
        })
        with self._with_fake_proc(files):
            with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(10))):
                self.assertEqual(mcp._worker_effective_cpus(), 1)
                self.assertEqual(mcp._worker_count("auto"), 1)
        files["/sys/fs/cgroup/system.slice/drlink-mcp-bridge.service/cpu.max"] = "max 100000\n"
        files["/sys/fs/cgroup/system.slice/cpu.max"] = "150000 100000\n"
        with self._with_fake_proc(files):
            with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(10))):
                self.assertEqual(mcp._worker_effective_cpus(), 1)
        files["/sys/fs/cgroup/system.slice/cpu.max"] = "max 100000\n"
        with self._with_fake_proc(files):
            with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(10))):
                self.assertEqual(mcp._worker_effective_cpus(), 10)
                self.assertEqual(mcp._worker_count("auto"), 8)

    def test_cpu_quota_v1_nonroot_mount(self):
        files = {
            "/proc/self/cgroup": "9:cpu,cpuacct:/docker/abc/service\n",
            "/proc/self/mountinfo":
                "39 29 0:32 /docker/abc /sys/fs/cgroup/cpu rw - cgroup cgroup rw,cpu,cpuacct\n",
            "/sys/fs/cgroup/cpu/service/cpu.cfs_quota_us": "100000\n",
            "/sys/fs/cgroup/cpu/service/cpu.cfs_period_us": "100000\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1\n",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
        }
        with self._with_fake_proc(files):
            with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(10))):
                self.assertEqual(mcp._worker_effective_cpus(), 1)

    def test_cpu_quota_missing_or_traversal_fails_closed(self):
        files = self._cgroup_v2_fixture()
        files["/sys/fs/cgroup/system.slice/drlink-mcp-bridge.service/cpu.max"] = "max 100000\n"
        files["/sys/fs/cgroup/system.slice/cpu.max"] = "max 100000\n"
        # Deliberately missing mount-root cpu.max (unknown parent quota)
        with self._with_fake_proc(files):
            with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(10))):
                self.assertEqual(mcp._worker_effective_cpus(), 1)
        files["/proc/self/cgroup"] = "0::/system.slice/../escaped\n"
        with self._with_fake_proc(files):
            with mock.patch.object(mcp.os, "sched_getaffinity", return_value=set(range(10))):
                self.assertEqual(mcp._worker_effective_cpus(), 1)

    def test_unset_keeps_backward_compatible_one_worker_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(mcp._worker_count(os.environ.get("DRLINK_MCP_WORKERS", "1")), 1)

    def test_auto_selects_eight_on_ten_core_lab_host(self):
        with mock.patch.object(mcp, "_worker_effective_cpus", return_value=10):
            with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=8 * 1024 ** 3):
                self.assertEqual(mcp._worker_count("auto"), 8)
                self.assertEqual(mcp._worker_count(" AUTO "), 8)

    def test_auto_caps_small_cpu_and_memory(self):
        with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=8 * 1024 ** 3):
            for cores, expected in [(1, 1), (2, 1), (3, 1), (4, 2), (7, 2), (8, 6), (9, 6), (10, 8), (40, 8)]:
                with self.subTest(cores=cores):
                    with mock.patch.object(mcp, "_worker_effective_cpus", return_value=cores):
                        self.assertEqual(mcp._worker_count("auto"), expected)
        with mock.patch.object(mcp, "_worker_effective_cpus", return_value=10):
            with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=3 * 1024 ** 3):
                self.assertEqual(mcp._worker_count("auto"), 6)
        with mock.patch.object(mcp, "_worker_effective_cpus", return_value=20):
            with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=1024 ** 3):
                self.assertEqual(mcp._worker_count("auto"), 1)
            with mock.patch.object(mcp, "_worker_memory_limit_bytes", return_value=0):
                self.assertEqual(mcp._worker_count("auto"), 1)

    def test_explicit_values_always_take_precedence(self):
        with mock.patch.object(mcp, "_worker_effective_cpus", return_value=2):
            self.assertEqual(mcp._worker_count("6"), 6)
            self.assertEqual(mcp._worker_count("1"), 1)
            self.assertEqual(mcp._worker_count("9999"), mcp.MAX_WORKERS)
            self.assertEqual(mcp._worker_count("invalid"), 1)

    def _with_fake_proc(self, files):
        """Mock ONLY per-test proc and cgroup entries; never read host state."""
        def fake_read(path, *args, **kwargs):
            key = str(path)
            if key not in files:
                raise OSError("fixture has no file: " + key)
            return files[key]
        return mock.patch.object(Path, "read_text", new=fake_read)

    def _cgroup_v2_fixture(self, child="1073741824", parent="4294967296"):
        return {
            "/proc/meminfo": "MemTotal: 8388608 kB\n",
            "/proc/self/cgroup": "0::/system.slice/drlink-mcp-bridge.service\n",
            "/proc/self/mountinfo":
                "39 29 0:32 / /sys/fs/cgroup rw,nosuid - cgroup2 cgroup rw\n",
            "/sys/fs/cgroup/system.slice/drlink-mcp-bridge.service/memory.max": child + "\n",
            "/sys/fs/cgroup/system.slice/memory.max": parent + "\n",
            "/sys/fs/cgroup/memory.max": "max\n",
        }

    def test_cgroup_memory_ceiling_is_respected(self):
        files = self._cgroup_v2_fixture(child=str(1024 ** 3))
        with self._with_fake_proc(files):
            self.assertEqual(mcp._worker_memory_limit_bytes(), 1024 ** 3)
            with mock.patch.object(mcp, "_worker_effective_cpus", return_value=10):
                self.assertEqual(mcp._worker_count("auto"), 1)

    def test_nested_v2_ancestor_limit_when_child_is_unlimited(self):
        files = self._cgroup_v2_fixture(child="max", parent=str(2 * 1024 ** 3))
        with self._with_fake_proc(files):
            self.assertEqual(mcp._worker_memory_limit_bytes(), 2 * 1024 ** 3)
            with mock.patch.object(mcp, "_worker_effective_cpus", return_value=10):
                self.assertEqual(mcp._worker_count("auto"), 6)

    def test_nested_v1_memory_mount_with_nonroot_mount_root(self):
        files = {
            "/proc/meminfo": "MemTotal: 8388608 kB\n",
            "/proc/self/cgroup": "11:memory:/docker/abc/child\n",
            "/proc/self/mountinfo":
                "39 29 0:32 /docker/abc /sys/fs/cgroup/memory rw - cgroup cgroup rw,memory\n",
            "/sys/fs/cgroup/memory/child/memory.limit_in_bytes": str(6 * 1024 ** 3),
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": str(1024 ** 3),
        }
        with self._with_fake_proc(files):
            self.assertEqual(mcp._worker_memory_limit_bytes(), 1024 ** 3)

    def test_unknown_or_malformed_cgroup_fails_closed(self):
        cases = [
            {"/proc/meminfo": "MemTotal: 8388608 kB\n"},
            {
                "/proc/meminfo": "MemTotal: 8388608 kB\n",
                "/proc/self/cgroup": "0::/system.slice/../escaped\n",
                "/proc/self/mountinfo": "39 29 0:32 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n",
            },
        ]
        for files in cases:
            with self.subTest(files=files):
                with self._with_fake_proc(files):
                    self.assertEqual(mcp._worker_memory_limit_bytes(), 0)
                    with mock.patch.object(mcp, "_worker_effective_cpus", return_value=10):
                        self.assertEqual(mcp._worker_count("auto"), 1)


if __name__ == "__main__":
    unittest.main()
