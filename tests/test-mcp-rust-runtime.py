#!/usr/bin/env python3
"""Focused Rust/Python bounded dispatch admission contract tests."""
from __future__ import annotations

import importlib.util
import base64
import io
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_NAME = "libdrlink_mcp_runtime.dylib" if sys.platform == "darwin" else "libdrlink_mcp_runtime.so"
LIBRARY = ROOT / "native/drlink-mcp-runtime/target/release" / LIBRARY_NAME
sys.path.insert(0, str(ROOT / "lib"))
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

    def test_python_response_writer_retries_short_writes(self):
        class PartialWriter:
            def __init__(self):
                self.data = bytearray()

            def write(self, chunk):
                count = min(13, len(chunk))
                self.data.extend(chunk[:count])
                return count

        writer = PartialWriter()
        payload = bytes(range(251)) * 900
        with mock.patch.dict(os.environ, {"DRLINK_MCP_RUNTIME": "python"}):
            runtime.write_mcp_response(writer, payload)
        self.assertEqual(writer.data, payload)


@unittest.skipUnless(LIBRARY.is_file(), "build the locked Rust MCP runtime library first")
class RustDispatchBudgetTests(unittest.TestCase):
    def test_rust_wait_signal_wakes_on_topic_change_and_times_out(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            budget = runtime.DispatchBudget(2)
            signal = budget.new_signal()
        self.assertIsNotNone(signal)
        try:
            observed = signal.snapshot()
            sender = threading.Thread(target=lambda: (time.sleep(0.03), signal.signal()))
            sender.start()
            self.assertTrue(signal.wait(observed, 1.0))
            sender.join(timeout=1)
            self.assertFalse(signal.wait(signal.snapshot(), 0.01))
        finally:
            signal.close()
            budget.close()

    def test_rust_wait_ticket_survives_subscription_close(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            budget = runtime.DispatchBudget(2)
            signal = budget.new_signal()
        observed = signal.snapshot()
        result = []
        waiter = threading.Thread(target=lambda: result.append(signal.wait(observed, 0.1)))
        waiter.start()
        time.sleep(0.02)
        signal.close()
        waiter.join(timeout=1)
        budget.close()
        self.assertEqual(result, [False])

    def test_rust_accepts_one_ready_socket_and_sets_close_on_exec(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        client = socket.socket()
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            budget = runtime.DispatchBudget(2)
            try:
                client.connect(listener.getsockname())
                fd = budget.accept(listener.fileno())
                self.assertIsInstance(fd, int)
                self.assertFalse(os.get_inheritable(fd))
                accepted = socket.socket(fileno=fd)
                try:
                    self.assertEqual(accepted.getpeername(), client.getsockname())
                finally:
                    accepted.close()
            finally:
                budget.close()
                client.close()
                listener.close()

    def test_rust_request_body_uses_bounded_reads_and_preserves_bytes(self):
        class ShortReader:
            def __init__(self, data):
                self.data = io.BytesIO(data)
                self.largest_read = 0

            def read(self, size):
                self.largest_read = max(self.largest_read, size)
                return self.data.read(min(size, 997))

        payload = bytes(range(251)) * 900
        reader = ShortReader(payload)
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            result = runtime.read_mcp_request_body(reader, len(payload))
        self.assertEqual(result, payload)
        self.assertLessEqual(reader.largest_read, 64 * 1024)

    def test_rust_request_body_rejects_short_read_and_oversized_length(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            with self.assertRaises(OSError):
                runtime.read_mcp_request_body(io.BytesIO(b"short"), 10)
            with self.assertRaises(ValueError):
                runtime.read_mcp_request_body(io.BytesIO(b""), 2_000_001)

    def test_rust_response_writer_bounds_chunks_and_applies_short_write_backpressure(self):
        class PartialWriter:
            def __init__(self):
                self.data = bytearray()
                self.largest_write = 0

            def write(self, chunk):
                self.largest_write = max(self.largest_write, len(chunk))
                count = min(997, len(chunk))
                self.data.extend(chunk[:count])
                return count

        writer = PartialWriter()
        payload = bytes(range(251)) * 900
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            runtime.write_mcp_response(writer, payload)
        self.assertEqual(writer.data, payload)
        self.assertLessEqual(writer.largest_write, 64 * 1024)

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

    def test_rust_bounded_output_matches_existing_cursor_contract(self):
        from drlink_mcp_full_control import Output, PAGE, WINDOW

        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            output = Output()
            output.append(b"A" * (WINDOW + 5))
            first = output.page(0)
            self.assertEqual(len(first["text"]), PAGE)
            self.assertEqual(first["total_bytes"], WINDOW + 5)
            self.assertEqual(first["truncated_before"], 5)
            self.assertTrue(first["cursor_was_evicted"])
            self.assertEqual(base64.b64decode(first["data_b64"]), b"A" * PAGE)
            output.close()

    def test_rust_drains_both_pipes_without_unbounded_python_capture(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            proc = subprocess.Popen(
                [sys.executable, "-c", (
                    "import sys; sys.stdout.buffer.write(b'A'*120000); "
                    "sys.stderr.buffer.write(b'B'*90000); sys.stdout.flush(); sys.stderr.flush()"
                )], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
            captured = {"stdout": bytearray(), "stderr": bytearray(), "total": [0, 0]}

            def append(name, index, chunk, limit):
                captured["total"][index] += len(chunk)
                captured[name].extend(chunk[:max(0, limit - len(captured[name]))])

            result = runtime.drain_process(
                proc,
                on_stdout=lambda chunk: append("stdout", 0, chunk, 4096),
                on_stderr=lambda chunk: append("stderr", 1, chunk, 2048),
                timeout_seconds=3,
            )
            self.assertEqual(result, 0)
            self.assertEqual(proc.wait(timeout=1), 0)
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(captured["total"], [120000, 90000])
        self.assertEqual(captured["stdout"], b"A" * 4096)
        self.assertEqual(captured["stderr"], b"B" * 2048)

    def test_rust_wait_timeout_leaves_child_waitable_for_python_cleanup(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(10)"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
            captured = bytearray()
            result = runtime.drain_process(
                proc, on_stdout=captured.extend, on_stderr=lambda _chunk: None,
                timeout_seconds=0.1,
            )
            self.assertEqual(result, 1)
            self.assertIn(b"ready", captured)
            os.killpg(proc.pid, signal.SIGKILL)
            try:
                self.assertEqual(runtime.drain_process(
                    proc, on_stdout=captured.extend, on_stderr=lambda _chunk: None,
                    timeout_seconds=3,
                ), 0)
                self.assertEqual(proc.wait(timeout=1), -signal.SIGKILL)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
                proc.stdout.close()
                proc.stderr.close()

    def test_rust_keeps_exit_watcher_when_descendant_holds_pipes_open(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            proc = subprocess.Popen(
                [sys.executable, "-c", (
                    "import subprocess,sys; "
                    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(0.7)']); "
                    "print(child.pid, flush=True)"
                )], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
            captured = bytearray()
            try:
                first = runtime.drain_process(
                    proc, on_stdout=captured.extend, on_stderr=lambda _chunk: None,
                    timeout_seconds=3,
                )
                self.assertEqual(first, 9)
                self.assertTrue(captured.strip().isdigit())
                final = runtime.drain_process(
                    proc, on_stdout=captured.extend, on_stderr=lambda _chunk: None,
                    timeout_seconds=3, wait_for_eof=True,
                )
                self.assertEqual(final, 0)
                self.assertEqual(proc.wait(timeout=1), 0)
            finally:
                if proc.poll() is None:
                    proc.wait(timeout=3)
                proc.stdout.close()
                proc.stderr.close()

    def test_rust_capture_process_bounds_output_and_reaps_child(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }):
            proc = subprocess.Popen(
                [sys.executable, "-c", (
                    "import sys; sys.stdout.buffer.write(b'X'*120000); "
                    "sys.stderr.buffer.write(b'Y'*90000)"
                )], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
            try:
                result = runtime.capture_process(
                    proc, input_data=None, timeout_seconds=3,
                    stdout_limit=4096, stderr_limit=2048,
                )
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
                proc.stdout.close()
                proc.stderr.close()
        self.assertEqual(result["exit_status"], 0)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["stdout"], b"X" * 4096)
        self.assertEqual(result["stderr"], b"Y" * 2048)
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])

    def test_final_pipe_drain_timeout_fails_capture_after_reaping(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }), mock.patch.object(runtime, "drain_process", side_effect=[9, 1]):
            proc = subprocess.Popen(
                [sys.executable, "-c", "pass"], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True,
            )
            with self.assertRaisesRegex(OSError, "output capture did not reach EOF"):
                runtime.capture_process(
                    proc, input_data=None, timeout_seconds=3,
                    stdout_limit=128, stderr_limit=128,
                )
            self.assertIsNotNone(proc.returncode)
            self.assertTrue(proc.stdout.closed)
            self.assertTrue(proc.stderr.closed)

    def test_final_pipe_timeout_releases_watcher_without_stdin_writer(self):
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }), mock.patch.object(runtime, "drain_process", side_effect=[9, 1]), \
                mock.patch.object(runtime, "free_process_watch") as free_watch:
            proc = subprocess.Popen(
                [sys.executable, "-c", "pass"], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True,
            )
            with self.assertRaisesRegex(OSError, "output capture did not reach EOF"):
                runtime.capture_process(
                    proc, input_data=None, timeout_seconds=3,
                    stdout_limit=128, stderr_limit=128,
                )
            self.assertIsNotNone(proc.returncode)
            free_watch.assert_called_once_with(proc)

    def test_final_pipe_drain_error_reaps_child_closes_streams_and_frees_watcher(self):
        drain_error = OSError("mock final drain I/O failure")
        with mock.patch.dict(os.environ, {
            "DRLINK_MCP_RUNTIME": "rust",
            "DRLINK_MCP_NATIVE_LIBRARY": str(LIBRARY),
        }), mock.patch.object(runtime, "drain_process", side_effect=[9, drain_error]), \
                mock.patch.object(runtime, "free_process_watch") as free_watch:
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True,
            )
            with self.assertRaisesRegex(OSError, "mock final drain I/O failure"):
                runtime.capture_process(
                    proc, input_data=None, timeout_seconds=3,
                    stdout_limit=128, stderr_limit=128,
                )
            self.assertIsNotNone(proc.returncode)
            self.assertTrue(proc.stdout.closed)
            self.assertTrue(proc.stderr.closed)
            free_watch.assert_called_once_with(proc)


if __name__ == "__main__":
    unittest.main()
