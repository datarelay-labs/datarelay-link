#!/usr/bin/env python3
"""Standalone DRLink Automation HTTP adapter (not dependent on Web Management).

Only loopback cleartext is permitted. A non-loopback listener requires an
explicit operator-owned TLS certificate and key.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from drlink_automation_api import AutomationApi, PREFIX
from drlink_control_db import ControlPlaneError
from drlink_service_accounts import ServiceAccountRateLimited, ServiceAccountUnauthenticated

DEFAULT_PORT = 8742
MAX_BODY_BYTES = 16 * 1024
MAX_CONCURRENT = 16


def validate_bind(host: str, *, tls_cert: Optional[str], tls_key: Optional[str]) -> None:
    address = str(host or "").strip().lower()
    if address in ("localhost", "ip6-localhost"):
        return
    try:
        if ipaddress.ip_address(address).is_loopback:
            return
    except ValueError:
        pass
    if not tls_cert or not tls_key:
        raise ControlPlaneError("Non-loopback Automation API requires TLS certificate and key.")
    if not Path(tls_cert).is_file() or not Path(tls_key).is_file():
        raise ControlPlaneError("Automation API TLS material is unavailable.")


class AutomationHandler(BaseHTTPRequestHandler):
    server_version = "DataRelayLinkAutomation/3.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *_args: object) -> None:
        # Do not echo bearer material, URLs or submitted JSON in web server logs.
        if os.environ.get("DRLINK_AUTOMATION_QUIET") != "1":
            print("DRLink automation request")

    def _json(self, status: int, data: dict) -> None:
        # Keep error categories stable and machine readable without exposing
        # internal exception text, bearer credentials, or private routes.
        error_codes = {
            400: "INVALID_REQUEST", 401: "UNAUTHENTICATED",
            403: "OPERATION_DENIED", 404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE",
            429: "RATE_LIMITED", 500: "INTERNAL_ERROR",
            503: "CAPACITY_EXCEEDED",
        }
        if status >= 400 and "error" in data:
            data = {**data, "code": error_codes.get(status, "REQUEST_FAILED")}
        raw = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "service": "drlink-automation"})
        else:
            self._json(405, {"error": "Automation operations require POST."})

    def do_POST(self) -> None:
        path = urlsplit(self.path)
        if (
            path.scheme or path.netloc or not path.path.startswith(PREFIX)
            or path.query or path.fragment
        ):
            # Unread rejected bodies must not become a following HTTP request.
            self.close_connection = True
            self._json(404, {"error": "Automation operation was not found."})
            return
        auth_values = self.headers.get_all("Authorization") or []
        if len(auth_values) != 1:
            self.close_connection = True
            self._json(401, {"error": "One Service Account credential is required."})
            return
        header = str(auth_values[0])
        if not header.startswith("Bearer ") or len(header) > 512:
            self.close_connection = True
            self._json(401, {"error": "Service Account credential required."})
            return
        lengths = self.headers.get_all("Content-Length") or []
        # Neither chunked nor ambiguous duplicate framing is supported. In
        # particular, do not let an intermediary interpret a different body
        # boundary from the Automation listener.
        if self.headers.get_all("Transfer-Encoding") or len(lengths) != 1:
            self.close_connection = True
            self._json(400, {"error": "Exactly one Content-Length is required."})
            return
        length_text = str(lengths[0])
        if (
            len(length_text) > 8 or not length_text.isascii()
            or not length_text.isdecimal()
        ):
            self.close_connection = True
            self._json(400, {"error": "Content-Length must be bounded decimal."})
            return
        length = int(length_text)
        if length < 2 or length > MAX_BODY_BYTES:
            self.close_connection = True
            self._json(413, {"error": "Automation request size is outside allowed bounds."})
            return
        if not self.server.concurrent.acquire(blocking=False):
            self.close_connection = True
            self._json(503, {"error": "Automation server concurrency limit reached."})
            return
        try:
            self.connection.settimeout(10.0)
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                self._json(400, {"error": "Invalid JSON body."})
                return
            api = AutomationApi(self.server.root)
            try:
                keys = self.headers.get_all("Idempotency-Key") or []
                if len(keys) > 1:
                    raise ControlPlaneError("Only one Idempotency-Key is allowed.")
                payload = api.invoke(
                    path.path, header[7:].strip(), data,
                    idempotency_key=keys[0] if keys else None,
                )
            finally:
                api.close()
            self._json(200, payload)
        except ServiceAccountRateLimited:
            self._json(429, {"error": "Automation API rate limit exceeded."})
        except ServiceAccountUnauthenticated:
            self._json(401, {"error": "Invalid Service Account credential."})
        except ControlPlaneError:
            self._json(403, {"error": "Automation operation denied."})
        except Exception:
            self._json(500, {"error": "Internal automation error."})
        finally:
            self.server.concurrent.release()


class AutomationServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16
    def __init__(self, address, *, root: Optional[str]):
        self.root = root
        self.concurrent = threading.BoundedSemaphore(MAX_CONCURRENT)
        super().__init__(address, AutomationHandler)


def create_server(*, root: Optional[str] = None, listen: str = "127.0.0.1",
                  port: int = DEFAULT_PORT, tls_cert: Optional[str] = None,
                  tls_key: Optional[str] = None) -> AutomationServer:
    validate_bind(listen, tls_cert=tls_cert, tls_key=tls_key)
    server = AutomationServer((listen, int(port)), root=root)
    if tls_cert and tls_key:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(tls_cert, tls_key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        except Exception:
            server.server_close()
            raise
    return server


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone Data Relay Link Automation API")
    parser.add_argument("--root")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    args = parser.parse_args(argv)
    server = create_server(root=args.root, listen=args.listen, port=args.port,
                           tls_cert=args.tls_cert, tls_key=args.tls_key)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
