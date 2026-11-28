#!/usr/bin/env python3
"""LPERF: egress throughput benchmark must exercise an actually allowed CONNECT.

The entire fixture binds 127.0.0.1, compiles temporary Internet Access rules,
and never touches an installed gateway or real destination.
"""
from __future__ import annotations

import os
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
        self.assertEqual(int(metrics["ORIGIN_ACKNOWLEDGED_TRANSFERS"]), 3)
        self.assertGreater(float(metrics["CPU_PERCENT"]), 0)
        self.assertEqual(metrics["CPU_SCOPE"], "combined_local_gateway_origin_and_clients")
        self.assertGreater(float(metrics["CONNECT_P50_MS"]), 0)
        self.assertGreater(float(metrics["CONNECT_SETUP_P95_MS"]), 0)
        self.assertLessEqual(float(metrics["CONNECT_SETUP_P95_MS"]), float(metrics["CONNECT_P95_MS"]))
        self.assertGreaterEqual(int(metrics["FD_PEAK"]), int(metrics["FD_BEFORE"]))
        self.assertEqual(metrics["MEASUREMENT_SCOPE"], "connect_establish_plus_payload")
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
        self.assertEqual(metrics["ORIGIN_ACKNOWLEDGED_TRANSFERS"], "0")
        self.assertEqual(metrics["CONNECT_SETUP_P95_MS"], "n/a")
        self.assertEqual(metrics["MEASUREMENT_SCOPE"], "http_full_response")
        self.assertEqual(metrics["AUDIT_DROP_COUNT"], "0")
        self.assertGreater(int(metrics["ORIGIN_RECEIVED_BYTES"]), 3 * 32 * 1024)

    def test_concurrent_denial_is_audited_and_never_dials_origin(self):
        for protocol in ("http", "connect"):
            with self.subTest(protocol=protocol):
                proc = subprocess.run(
                    [sys.executable, str(BENCH), "--protocol", protocol,
                     "--concurrency", "5", "--transfer-kib", "16",
                     "--hold-ms", "30", "--negative-during-load"],
                    cwd=ROOT, capture_output=True, text=True, timeout=80,
                )
                output = proc.stdout + "\n" + proc.stderr
                self.assertEqual(proc.returncode, 0, output[-4000:])
                metrics = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", output, re.MULTILINE))
                self.assertEqual(metrics["PERFORMANCE_BENCHMARK"], "PASS")
                self.assertEqual(metrics["FAILURE_RATE"], "0.0000")
                self.assertEqual(metrics["NEGATIVE_DURING_LOAD_DENIED"], "1")
                self.assertEqual(metrics["NEGATIVE_UPSTREAM_ATTEMPTS"], "0")
                self.assertEqual(metrics["NEGATIVE_AUDIT_RECEIPTS"], "1")
                self.assertEqual(int(metrics["ORIGIN_ACKNOWLEDGED_TRANSFERS"]), 5 if protocol == "connect" else 0)
                self.assertEqual(metrics["AUDIT_DROP_COUNT"], "0")
                self.assertEqual(int(metrics["AUDIT_EXPECTED_CONNECTIONS"]), 6)
                self.assertEqual(int(metrics["AUDIT_UNIQUE_CONNECTIONS"]), 6)

    def test_invalid_tls_preface_does_not_count_a_buffered_upload_as_delivered(self):
        env = dict(os.environ, DRLINK_EGRESS_BENCH_INVALID_TLS_PREFACE="1")
        proc = subprocess.run(
            [sys.executable, str(BENCH), "--concurrency", "3",
             "--transfer-kib", "32", "--hold-ms", "20", "--protocol", "connect"],
            cwd=ROOT, capture_output=True, text=True, timeout=70, env=env,
        )
        text = proc.stdout + "\n" + proc.stderr
        self.assertNotEqual(proc.returncode, 0, text[-4000:])
        self.assertIn("PERFORMANCE_BENCHMARK=FAIL", text)
        metrics = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", text, re.MULTILINE))
        self.assertEqual(metrics["ORIGIN_RECEIVED_BYTES"], "0")
        self.assertEqual(metrics["ORIGIN_ACKNOWLEDGED_TRANSFERS"], "0")
        self.assertEqual(metrics["FAILURE_RATE"], "1.0000")
        self.assertEqual(metrics["AUDIT_DROP_COUNT"], "0")

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
