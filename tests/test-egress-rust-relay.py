#!/usr/bin/env python3
"""Focused ABI/socket regression for the opt-in Rust egress relay."""
from __future__ import annotations

import importlib.util
import os
import socket
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "native/drlink-egress/target/release/libdrlink_egress.so"
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


if __name__ == "__main__":
    unittest.main()
