#!/usr/bin/env python3
"""LPERF: egress throughput benchmark must exercise an actually allowed CONNECT.

The entire fixture binds 127.0.0.1, compiles temporary Internet Access rules,
and never touches an installed gateway or real destination.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tests" / "run-egress-benchmark.py"


class EgressBenchmarkRegressionTests(unittest.TestCase):
    def test_allowed_connect_measures_real_transfer_and_cpu(self):
        proc = subprocess.run(
            [sys.executable, str(BENCH), "--concurrency", "3",
             "--transfer-kib", "32", "--hold-ms", "60"],
            cwd=ROOT, capture_output=True, text=True, timeout=65,
        )
        output = proc.stdout + "\n" + proc.stderr
        self.assertEqual(proc.returncode, 0, output[-4000:])
        self.assertIn("PERFORMANCE_BENCHMARK=PASS", output)
        metrics = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", output, re.MULTILINE))
        self.assertEqual(float(metrics["FAILURE_RATE"]), 0)
        self.assertEqual(int(metrics["TRANSFER_KIB_PER_CONNECTION"]), 32)
        self.assertGreaterEqual(int(metrics["ORIGIN_RECEIVED_BYTES"]), 3 * 32 * 1024)
        self.assertGreater(float(metrics["CPU_PERCENT"]), 0)
        self.assertEqual(metrics["CPU_SCOPE"], "combined_local_gateway_origin_and_clients")
        self.assertGreater(float(metrics["CONNECT_P50_MS"]), 0)
        self.assertLessEqual(float(metrics["CONNECT_P50_MS"]), float(metrics["CONNECT_P95_MS"]))
        self.assertLessEqual(float(metrics["CONNECT_P95_MS"]), float(metrics["CONNECT_P99_MS"]))
        self.assertEqual(metrics["AUDIT_DROP_COUNT"], "0")
        self.assertEqual(metrics["AUDIT_PARSE_ERRORS"], "0")
        self.assertEqual(int(metrics["AUDIT_UNIQUE_CONNECTIONS"]), 3)

    def test_http_forward_upload_obeys_policy_and_emits_audit(self):
        proc = subprocess.run(
            [sys.executable, str(BENCH), "--protocol", "http", "--concurrency", "3",
             "--transfer-kib", "32", "--hold-ms", "20"],
            cwd=ROOT, capture_output=True, text=True, timeout=65,
        )
        output = proc.stdout + "\n" + proc.stderr
        self.assertEqual(proc.returncode, 0, output[-4000:])
        self.assertIn("PERFORMANCE_BENCHMARK=PASS", output)
        metrics = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", output, re.MULTILINE))
        self.assertEqual(metrics["BENCH_PROTOCOL"], "http")
        self.assertEqual(metrics["AUDIT_DROP_COUNT"], "0")
        self.assertGreater(int(metrics["ORIGIN_RECEIVED_BYTES"]), 3 * 32 * 1024)

    def test_input_limits_prevent_unbounded_benchmarks(self):
        for arguments in [
            ["--concurrency", "0"],
            ["--concurrency", "257"],
            ["--transfer-kib", "-1"],
            ["--transfer-kib", "8193"],
            ["--churn", "-1"],
            ["--churn", "201"],
        ]:
            with self.subTest(arguments=arguments):
                proc = subprocess.run(
                    [sys.executable, str(BENCH), *arguments],
                    cwd=ROOT, capture_output=True, text=True, timeout=10,
                )
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("error:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
