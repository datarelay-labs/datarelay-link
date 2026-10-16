#!/usr/bin/env python3
"""Isolated TCP regression: large denied HTTP uploads return an HTTP policy code."""
import importlib.util
import socket
import sys
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lib"))
spec = importlib.util.spec_from_file_location(
    "drlink_egress_gateway",
    REPO / "server/frp-egress-gateway.py",
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class DeniedUploadResponse(unittest.TestCase):
    def _probe(self, length):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(5)
        results = []
        def serve():
            try:
                accepted, _ = server.accept()
                with accepted:
                    raw = gateway._read_until_double_crlf(accepted, gateway.MAX_HEADER_BYTES)
                    method, target, version, headers, prefix = gateway._parse_request(raw)
                    self.assertEqual(method, "POST")
                    self.assertEqual(target, "http://unapproved.example.test/upload")
                    self.assertEqual(version, "HTTP/1.1")
                    self.assertEqual(gateway._parse_content_length(headers), length)
                    gateway._send_denial_with_bounded_upload_drain(
                        accepted, 403, "Forbidden",
                        content_length=length, body_prefix=prefix,
                    )
            except Exception as exc:
                results.append(exc)
            finally:
                server.close()

        worker = threading.Thread(target=serve)
        worker.start()
        try:
            with socket.create_connection(server.getsockname(), timeout=5) as client:
                client.settimeout(5)
                head = (
                    f"POST http://unapproved.example.test/upload HTTP/1.1\r\n"
                    f"Host: unapproved.example.test\r\nContent-Length: {length}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                client.sendall(head + b"x" * length)
                raw = bytearray()
                while True:
                    data = client.recv(65536)
                    if not data:
                        break
                    raw.extend(data)
                self.assertTrue(raw.startswith(b"HTTP/1.1 403 Forbidden"), raw[:300])
                self.assertTrue(raw.endswith(b"denied\n"), raw[-100:])
        finally:
            worker.join(timeout=7)
            self.assertFalse(worker.is_alive(), "policy response server blocked")
            self.assertFalse(results, results)

    def test_denied_64k_upload_provides_explicit_403(self):
        self._probe(64 * 1024)

    def test_denied_1m_upload_provides_explicit_403(self):
        self._probe(1024 * 1024)


if __name__ == "__main__":
    unittest.main()
