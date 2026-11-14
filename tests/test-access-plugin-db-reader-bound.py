#!/usr/bin/env python3
"""F-008 root-cause regression: the NewUserConn DB-reader bound must stay small.

OBS-P005 B (claude-run-20261112, shared Server 6eb4ec42) found that Relay Remote Service
connection rate was capped at ~28 CPS even after the integrity-scan cost was fixed. The cause is
CPU/GIL contention between concurrent SQLite readers inside the frps access plugin: the
per-connection authorization (open read-only DB, integrity/FK scan, proxy map, ACL evaluation) is
CPU-bound, so running 8 of them at once makes each one slower than running them one after another.
Measured on the live control DB (16 requester threads, authorize only):

    DB-reader bound   req/s    CPU
    1                 81.5     101%
    2                 90.7     178%
    4                 54.1     ~330%
    8                 35.9     ~420%   (previous hard-coded value)
    unbounded         26.1     206%

The HTTP worker bound (ACCESS_MAX_CONCURRENT, 512) is what absorbs a burst; the DB-reader bound only
limits how many authorizations run at the same time, so it must stay at the throughput optimum.
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ENV = "FRP_ACCESS_DB_MAX_CONCURRENT"


def load_plugin(env=None):
    path = ROOT / "server" / "frp-access-plugin.py"
    clean = {k: v for k, v in os.environ.items() if k != ENV}
    if env is not None:
        clean[ENV] = env
    with mock.patch.dict(os.environ, clean, clear=True):
        spec = importlib.util.spec_from_file_location("frp_access_plugin_db_bound", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class AccessPluginDbReaderBoundTests(unittest.TestCase):
    def test_default_reader_bound_is_at_the_throughput_optimum(self):
        plugin = load_plugin()
        self.assertGreaterEqual(plugin.ACCESS_DB_MAX_CONCURRENT, 1)
        # >2 concurrent CPU-bound authorizations were measured slower in total than 2 (OBS-P005 B).
        self.assertLessEqual(plugin.ACCESS_DB_MAX_CONCURRENT, 2, plugin.ACCESS_DB_MAX_CONCURRENT)

    def test_reader_bound_stays_below_http_slot_bound(self):
        plugin = load_plugin()
        self.assertLess(plugin.ACCESS_DB_MAX_CONCURRENT, plugin.ACCESS_MAX_CONCURRENT)

    def test_operator_override_is_honoured(self):
        self.assertEqual(load_plugin("4").ACCESS_DB_MAX_CONCURRENT, 4)

    def test_invalid_override_falls_back_to_a_safe_bound(self):
        default = load_plugin().ACCESS_DB_MAX_CONCURRENT
        for bad in ("0", "-3", "abc", ""):
            with self.subTest(value=bad):
                self.assertEqual(load_plugin(bad).ACCESS_DB_MAX_CONCURRENT, default)


if __name__ == "__main__":
    unittest.main()
