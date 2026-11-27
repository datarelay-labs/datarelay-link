#!/usr/bin/env python3
"""Focused ABI/socket regression for the opt-in Rust egress relay."""
from __future__ import annotations

import importlib.util
import os
import platform
import socket
import sys
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64"):
    NATIVE_TARGET, NATIVE_EXTENSION = "aarch64-apple-darwin", "dylib"
elif sys.platform.startswith("linux") and platform.machine() in ("aarch64", "arm64"):
    NATIVE_TARGET, NATIVE_EXTENSION = "aarch64-unknown-linux-gnu", "so"
else:
    NATIVE_TARGET, NATIVE_EXTENSION = "x86_64-unknown-linux-gnu", "so"
LIBRARY = ROOT / f"lib/native/{NATIVE_TARGET}/libdrlink_egress.{NATIVE_EXTENSION}"
os.environ["DRLINK_EGRESS_RUNTIME"] = "rust"
os.environ["DRLINK_EGRESS_NATIVE_LIBRARY"] = str(LIBRARY)
spec = importlib.util.spec_from_file_location(
    "frp_egress_runtime_native_test", ROOT / "lib/frp_egress_runtime.py"
)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@unittest.skipUnless(LIBRARY.is_file(), "build the locked Rust relay library first")
class RustRelayTests(unittest.TestCase):
    def _run(self, authorize, client_action, upstream_action, *, idle=2.0, join_timeout=3):
        client, client_peer = socket.socketpair()
        upstream, upstream_peer = socket.socketpair()
        result = {}

        def relay():
            result["outcome"] = runtime.relay_bidirectional(
                client, upstream, authorize_fn=authorize,
                revalidate_interval=0.05, idle_timeout=idle,
            )

        thread = threading.Thread(target=relay)
        thread.start()
        errors = []

        def run_action(action, sock):
            try:
                action(sock)
            except Exception as exc:
                errors.append(exc)

        client_thread = threading.Thread(target=run_action, args=(client_action, client_peer))
        upstream_thread = threading.Thread(target=run_action, args=(upstream_action, upstream_peer))
        client_thread.start()
        upstream_thread.start()
        try:
            client_thread.join(timeout=join_timeout)
            upstream_thread.join(timeout=join_timeout)
            thread.join(timeout=join_timeout)
            self.assertFalse(client_thread.is_alive(), "client fixture did not finish")
            self.assertFalse(upstream_thread.is_alive(), "upstream fixture did not finish")
            self.assertFalse(thread.is_alive(), "Rust relay did not close in time")
            if errors:
                raise errors[0]
            return result["outcome"], client_peer, upstream_peer
        finally:
            client_peer.close()
            upstream_peer.close()
            thread.join(timeout=1)

    def test_transfers_both_directions_and_preserves_half_close(self):
        client_result = bytearray()

        def client_action(sock):
            sock.sendall(b"request")
            sock.shutdown(socket.SHUT_WR)
            while True:
                part = sock.recv(32)
                if not part:
                    break
                client_result.extend(part)

        def upstream_action(sock):
            received = bytearray()
            while True:
                part = sock.recv(32)
                if not part:
                    break
                received.extend(part)
            self.assertEqual(received, b"request")
            sock.sendall(b"response")
            sock.shutdown(socket.SHUT_WR)

        outcome, _, _ = self._run(lambda: True, client_action, upstream_action)
        self.assertEqual(client_result, b"response")
        self.assertEqual(outcome, runtime.EG.AUDIT_UPSTREAM_CLOSED)

    def test_large_slow_reader_transfer_applies_backpressure_without_loss(self):
        payload = bytes(range(256)) * (4 * 1024 * 1024 // 256)
        returned = bytearray()

        def client_action(sock):
            sock.settimeout(10)
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)
            while True:
                part = sock.recv(64 * 1024)
                if not part:
                    break
                returned.extend(part)

        def upstream_action(sock):
            sock.settimeout(10)
            received = bytearray()
            while True:
                part = sock.recv(16 * 1024)
                if not part:
                    break
                received.extend(part)
                time.sleep(0.0002)
            sock.sendall(received)
            sock.shutdown(socket.SHUT_WR)

        outcome, _, _ = self._run(
            lambda: True, client_action, upstream_action, idle=10, join_timeout=12,
        )
        self.assertEqual(returned, payload)
        self.assertEqual(outcome, runtime.EG.AUDIT_UPSTREAM_CLOSED)

    def test_simultaneous_backpressured_half_close_preserves_both_tails(self):
        client_payload = bytes(range(251)) * 4096  # 1 MiB; exceeds each relay buffer.
        upstream_payload = b"response after request EOF"
        client_received = bytearray()

        def client_action(sock):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            sock.sendall(client_payload)
            sock.shutdown(socket.SHUT_WR)
            while True:
                part = sock.recv(4096)
                if not part:
                    break
                client_received.extend(part)
                time.sleep(0.0001)

        def upstream_action(sock):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            received = bytearray()
            while True:
                part = sock.recv(4096)
                if not part:
                    break
                received.extend(part)
                time.sleep(0.0001)
            self.assertEqual(received, client_payload)
            sock.sendall(upstream_payload)
            sock.shutdown(socket.SHUT_WR)

        outcome, _, _ = self._run(
            lambda: True, client_action, upstream_action, idle=10, join_timeout=15,
        )
        self.assertEqual(client_received, upstream_payload)
        self.assertEqual(outcome, runtime.EG.AUDIT_UPSTREAM_CLOSED)

    def test_drains_unread_payload_after_peer_hangup(self):
        payload = bytes(range(251)) * 800  # 200,800 bytes; larger than one relay read.
        returned = bytearray()

        def client_action(sock):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            sock.shutdown(socket.SHUT_WR)
            time.sleep(0.1)
            while True:
                part = sock.recv(4096)
                if not part:
                    break
                returned.extend(part)

        def upstream_action(sock):
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)

        outcome, _, _ = self._run(
            lambda: True, client_action, upstream_action, idle=3, join_timeout=5,
        )
        self.assertEqual(returned, payload)
        self.assertEqual(outcome, runtime.EG.AUDIT_UPSTREAM_CLOSED)

    def test_backpressured_hangup_does_not_busy_spin(self):
        payload = b"x" * 180_000
        client, client_peer = socket.socketpair()
        upstream, upstream_peer = socket.socketpair()
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        client_peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        result = {}

        def relay():
            result["outcome"] = runtime.relay_bidirectional(
                client, upstream, authorize_fn=lambda: True,
                revalidate_interval=1, idle_timeout=0.8,
            )

        thread = threading.Thread(target=relay)
        thread.start()
        upstream_peer.sendall(payload)
        upstream_peer.shutdown(socket.SHUT_WR)
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline and thread.is_alive():
            time.sleep(0.01)
        started = time.process_time()
        time.sleep(0.3)
        consumed = time.process_time() - started
        client_peer.close()  # release the relay after the measurement
        thread.join(timeout=2)
        upstream_peer.close()
        self.assertFalse(thread.is_alive(), "backpressured relay did not terminate")
        self.assertLess(consumed, 0.15, "persistent POLLHUP caused a busy loop")

    def test_policy_revocation_stops_forwarding_and_returns_audit_outcome(self):
        revoked_at = []
        forwarded = []

        def authorize():
            revoked_at.append(time.monotonic())
            return False

        def client_action(sock):
            time.sleep(0.12)
            try:
                sock.sendall(b"payload")
                sock.recv(1)
            except OSError:
                pass

        def upstream_action(sock):
            sock.settimeout(0.4)
            try:
                while True:
                    part = sock.recv(32)
                    if not part:
                        return
                    forwarded.append((time.monotonic(), part))
            except (OSError, TimeoutError):
                return

        outcome, _, _ = self._run(authorize, client_action, upstream_action)
        self.assertEqual(outcome, runtime.EG.AUDIT_POLICY_REVOKED)
        self.assertTrue(revoked_at)
        self.assertFalse([item for item in forwarded if item[0] > revoked_at[0]])

    def test_explicit_rust_mode_fails_closed_when_library_is_missing(self):
        client, client_peer = socket.socketpair()
        upstream, upstream_peer = socket.socketpair()
        try:
            with mock.patch.object(runtime, "_native_relay", return_value=None):
                outcome = runtime.relay_bidirectional(
                    client, upstream, authorize_fn=lambda: True,
                )
            self.assertEqual(outcome, runtime.EG.AUDIT_RELAY_FAILURE)
            self.assertEqual(client_peer.recv(1), b"")
            self.assertEqual(upstream_peer.recv(1), b"")
        finally:
            client_peer.close()
            upstream_peer.close()


class RuntimeSelectionTests(unittest.TestCase):
    def test_invalid_runtime_selector_is_rejected_instead_of_falling_back(self):
        with mock.patch.dict(os.environ, {"DRLINK_EGRESS_RUNTIME": "ruts"}):
            with self.assertRaisesRegex(ValueError, "must be auto, python or rust"):
                runtime._native_relay()


if __name__ == "__main__":
    unittest.main()
