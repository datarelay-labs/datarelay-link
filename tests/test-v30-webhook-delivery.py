#!/usr/bin/env python3
"""DRLink signed Webhook: real local TLS exchange plus deny/retry boundaries."""
from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_db import ControlPlaneError
from drlink_webhook_delivery import PinnedHTTPSConnection, delivery_tick, resolve_public_target
from drlink_webhooks import WebhookStore


class Receiver(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.__class__.requests.append((self.path, dict(self.headers), body))
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):
        pass


class WebhookDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-hook-delivery-")
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _event(self):
        with WebhookStore(self.root) as store:
            hook = store.create("alerts", "https://hooks.example.com/drlink", ["attention"])
            event = store.enqueue(hook["id"], "attention", {
                "kind": "new-alert", "secret": "NEVER_SEND_ME", "nested": {
                    "api_key": "ALSO_NEVER_SEND", "name": "test-alert"
                }
            })
            key = store.key_file
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            db = Path(self.root, "var/lib/drlink/drlink.db").read_bytes()
            self.assertNotIn(hook["secret"].encode(), db)
            self.assertNotIn(b"NEVER_SEND_ME", db)
            self.assertEqual(store.signing_secret(hook["id"]), hook["secret"])
            return hook, event

    def _tls_server(self):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hooks.example.com")])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(hours=1))
                .not_valid_after(now + timedelta(days=1))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("hooks.example.com")]),
                               critical=False)
                .sign(key, hashes.SHA256()))
        cert_path = Path(self.root, "receiver.pem")
        key_path = Path(self.root, "receiver.key")
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_path), str(key_path))
        Receiver.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client_context = ssl.create_default_context(cafile=str(cert_path))
        return server, thread, client_context

    def test_untrusted_or_wrong_hostname_tls_cert_never_delivers_payload(self):
        """Real TLS handshake must authenticate the destination hostname."""
        server, thread, trusted_context = self._tls_server()
        public = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                   "", ("8.8.8.8", 443))]
        port = server.server_address[1]
        def dial_disposable_server(conn):
            self.assertEqual(conn.selected[4], ("8.8.8.8", 443))
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.settimeout(5)
            raw.connect(("127.0.0.1", port))
            conn.sock = conn._context.wrap_socket(raw, server_hostname=conn.host)

        try:
            for label, host, context in (
                ("untrusted-ca", "hooks.example.com", ssl.create_default_context()),
                ("wrong-hostname", "wrong.example.com", trusted_context),
            ):
                with self.subTest(tls_failure=label):
                    with WebhookStore(self.root) as store:
                        hook = store.create(label, "https://" + host + "/drlink",
                                            ["attention"])
                        event = store.enqueue(hook["id"], "attention",
                                              {"kind": "tls-rejection"})
                    with patch("drlink_webhook_delivery.socket.getaddrinfo",
                               return_value=public), \
                         patch("drlink_webhook_delivery.ssl.create_default_context",
                               return_value=context), \
                         patch.object(PinnedHTTPSConnection, "connect",
                                      dial_disposable_server):
                        result = delivery_tick(self.root)
                    self.assertEqual(result, {"claimed": 1, "delivered": 0, "failed": 1})
                    # A failed TLS handshake must not send the HTTP payload,
                    # expose the signing secret, or silently follow a redirect.
                    self.assertEqual(Receiver.requests, [])
                    with WebhookStore(self.root) as store:
                        row = store.conn.execute(
                            "SELECT status,attempts FROM management_webhook_outbox "
                            "WHERE event_id=?", (event["event_id"],)
                        ).fetchone()
                        self.assertEqual((row["status"], row["attempts"]),
                                         ("PENDING", 1))
                        self.assertEqual(store.claim_due(), [])
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    def test_https_redirect_never_retransmits_a_signed_event(self):
        """A valid TLS peer cannot redirect our signed payload to a new URL."""
        hook, event = self._event()
        server, thread, trusted_context = self._tls_server()
        port = server.server_address[1]
        public = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                   "", ("8.8.8.8", 443))]
        dial_count = []

        def dial_disposable_server(conn):
            self.assertEqual(conn.selected[4], ("8.8.8.8", 443))
            dial_count.append(conn.host)
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.settimeout(5)
            raw.connect(("127.0.0.1", port))
            conn.sock = conn._context.wrap_socket(raw, server_hostname=conn.host)

        def respond_with_redirect(handler):
            body = handler.rfile.read(int(handler.headers["Content-Length"]))
            Receiver.requests.append((handler.path, dict(handler.headers), body))
            handler.send_response(302)
            handler.send_header("Location", "http://127.0.0.1:1/exfiltrate")
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        try:
            with patch("drlink_webhook_delivery.socket.getaddrinfo",
                       return_value=public), \
                 patch("drlink_webhook_delivery.ssl.create_default_context",
                       return_value=trusted_context), \
                 patch.object(PinnedHTTPSConnection, "connect",
                              dial_disposable_server), \
                 patch.object(Receiver, "do_POST", respond_with_redirect):
                result = delivery_tick(self.root)

            self.assertEqual(result, {"claimed": 1, "delivered": 0, "failed": 1})
            self.assertEqual(dial_count, ["hooks.example.com"])
            self.assertEqual(len(Receiver.requests), 1)
            self.assertEqual(Receiver.requests[0][0], "/drlink")
            with WebhookStore(self.root) as store:
                row = store.conn.execute(
                    "SELECT status,attempts FROM management_webhook_outbox "
                    "WHERE event_id=?", (event["event_id"],)
                ).fetchone()
                self.assertEqual((row["status"], row["attempts"]), ("PENDING", 1))
                self.assertEqual(store.claim_due(), [])
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    def test_real_https_delivery_has_valid_hmac_stable_event_id_and_no_secrets(self):
        hook, event = self._event()
        server, thread, client_context = self._tls_server()
        port = server.server_address[1]
        public = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                   "", ("8.8.8.8", 443))]

        def test_socket_connect(conn):
            # The product's validated address is public. A test-only socket mapping
            # sends the same HTTP/TLS bytes to our disposable loopback receiver.
            self.assertEqual(conn.selected[4], ("8.8.8.8", 443))
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.settimeout(5)
            raw.connect(("127.0.0.1", port))
            conn.sock = conn._context.wrap_socket(raw, server_hostname=conn.host)

        try:
            with patch("drlink_webhook_delivery.socket.getaddrinfo", return_value=public), \
                 patch("drlink_webhook_delivery.ssl.create_default_context",
                       return_value=client_context), \
                 patch.object(PinnedHTTPSConnection, "connect", test_socket_connect):
                result = delivery_tick(self.root)
            self.assertEqual(result, {"claimed": 1, "delivered": 1, "failed": 0})
            self.assertEqual(len(Receiver.requests), 1)
            uri, headers, body = Receiver.requests[0]
            self.assertEqual(uri, "/drlink")
            self.assertEqual(headers["X-DRLink-Event-ID"], event["event_id"])
            data = json.loads(body)
            self.assertEqual(data["event_id"], event["event_id"])
            self.assertNotIn("NEVER_SEND_ME", body.decode())
            self.assertNotIn("ALSO_NEVER_SEND", body.decode())
            with WebhookStore(self.root) as store:
                self.assertTrue(store.verify(hook["secret"], data, headers["X-DRLink-Signature"]))
                self.assertEqual(store.pending(), [])
                row = store.conn.execute(
                    "SELECT status,attempts FROM management_webhook_outbox WHERE event_id=?",
                    (event["event_id"],),
                ).fetchone()
                self.assertEqual((row["status"], row["attempts"]), ("DELIVERED", 1))
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    def test_mixed_public_and_private_dns_fails_before_any_tcp_connect(self):
        hook, event = self._event()
        mixed = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
        ]
        with patch("drlink_webhook_delivery.socket.getaddrinfo", return_value=mixed), \
             patch.object(PinnedHTTPSConnection, "connect", side_effect=AssertionError("dialed")):
            result = delivery_tick(self.root)
        self.assertEqual(result, {"claimed": 1, "delivered": 0, "failed": 1})
        with WebhookStore(self.root) as store:
            row = store.conn.execute(
                "SELECT status,attempts,next_attempt_at FROM management_webhook_outbox WHERE event_id=?",
                (event["event_id"],),
            ).fetchone()
            self.assertEqual((row["status"], row["attempts"]), ("PENDING", 1))
            self.assertGreater(row["next_attempt_at"], event["timestamp"])
            self.assertEqual(store.claim_due(), [])  # no retry storm

    def test_nonpositive_or_nonnumeric_tick_limit_does_not_claim_or_send(self):
        hook, event = self._event()
        with patch("drlink_webhook_delivery.send_signed_event",
                   side_effect=AssertionError("unexpected delivery")):
            for invalid in (0, -1, False, True, "0", 1.5):
                with self.subTest(limit=invalid), self.assertRaises(ControlPlaneError):
                    delivery_tick(self.root, limit=invalid)
        with WebhookStore(self.root) as store:
            row = store.conn.execute(
                "SELECT status, attempts, lease_token FROM management_webhook_outbox "
                "WHERE event_id=?", (event["event_id"],),
            ).fetchone()
            self.assertEqual((row["status"], row["attempts"], row["lease_token"]),
                             ("PENDING", 0, ""))
            self.assertEqual(store.pending()[0]["event_id"], event["event_id"])

    def test_secret_key_loss_and_private_address_denied(self):
        hook, _ = self._event()
        with WebhookStore(self.root) as store:
            store.key_file.unlink()
            with self.assertRaises(ControlPlaneError):
                store.signing_secret(hook["id"])
            with self.assertRaises(ControlPlaneError):
                store.rotate_secret(hook["id"])
        for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"):
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            candidates = [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                           (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443))]
            with patch("drlink_webhook_delivery.socket.getaddrinfo", return_value=candidates):
                with self.assertRaises(ControlPlaneError):
                    resolve_public_target("hooks.example.com")


if __name__ == "__main__":
    unittest.main()
