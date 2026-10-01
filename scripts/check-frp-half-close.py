#!/usr/bin/env python3
"""Functional half-close probe for an official FRP candidate pair."""

from __future__ import annotations

import argparse
import socket
import subprocess
import threading
import time
from pathlib import Path

PAYLOAD = b"drlink-half-close-probe"
PREFIX = b"DRLINK_HALF_CLOSE:"


def reserve_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def wait_tcp(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            conn = socket.create_connection(("127.0.0.1", port), 0.25)
            conn.close()
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    raise RuntimeError(f"port {port} not ready: {last_error}")


def serve_eof_response(listener: socket.socket, stop: threading.Event) -> None:
    listener.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _addr = listener.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        with conn:
            conn.settimeout(3)
            chunks: list[bytes] = []
            try:
                while True:
                    data = conn.recv(65536)
                    if not data:
                        break
                    chunks.append(data)
                conn.sendall(PREFIX + b"".join(chunks))
            except OSError:
                pass


def terminate(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def run_probe(frps: Path, frpc: Path, stage: Path) -> int:
    bind_port, remote_port, target_port = reserve_port(), reserve_port(), reserve_port()
    token = "drlink-half-close-compat-not-a-secret"
    stage.mkdir(parents=True, exist_ok=True)
    frps_cfg = stage / "half-close-frps.toml"
    frpc_cfg = stage / "half-close-frpc.toml"
    frps_log = stage / "half-close-frps.log"
    frpc_log = stage / "half-close-frpc.log"
    frps_cfg.write_text(
        f'bindAddr = "127.0.0.1"\nbindPort = {bind_port}\n'
        f'auth.method = "token"\nauth.token = "{token}"\n',
        encoding="utf-8",
    )
    frpc_cfg.write_text(
        f'serverAddr = "127.0.0.1"\nserverPort = {bind_port}\n'
        f'auth.method = "token"\nauth.token = "{token}"\nloginFailExit = true\n'
        '[[proxies]]\nname = "half-close-compat"\ntype = "tcp"\n'
        f'localIP = "127.0.0.1"\nlocalPort = {target_port}\nremotePort = {remote_port}\n',
        encoding="utf-8",
    )

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", target_port))
    listener.listen(16)
    stop = threading.Event()
    thread = threading.Thread(target=serve_eof_response, args=(listener, stop), daemon=True)
    thread.start()
    server = client = None
    server_out = client_out = None
    try:
        server_out = frps_log.open("wb")
        client_out = frpc_log.open("wb")
        server = subprocess.Popen([str(frps), "-c", str(frps_cfg)], stdout=server_out, stderr=subprocess.STDOUT)
        wait_tcp(bind_port)
        client = subprocess.Popen([str(frpc), "-c", str(frpc_cfg)], stdout=client_out, stderr=subprocess.STDOUT)
        wait_tcp(remote_port)

        conn = socket.create_connection(("127.0.0.1", remote_port), 3)
        with conn:
            conn.settimeout(5)
            conn.sendall(PAYLOAD)
            conn.shutdown(socket.SHUT_WR)
            received = bytearray()
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                received.extend(data)
        expected = PREFIX + PAYLOAD
        if bytes(received) != expected:
            print(f"FRP_HALF_CLOSE=FAIL expected_len={len(expected)} actual_len={len(received)}")
            return 1
        print(f"FRP_HALF_CLOSE=PASS response_bytes={len(received)}")
        return 0
    finally:
        terminate(client)
        terminate(server)
        if client_out is not None:
            client_out.close()
        if server_out is not None:
            server_out.close()
        stop.set()
        listener.close()
        thread.join(timeout=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frps", required=True, type=Path)
    parser.add_argument("--frpc", required=True, type=Path)
    parser.add_argument("--stage", required=True, type=Path)
    args = parser.parse_args()
    for binary in (args.frps, args.frpc):
        if not binary.is_file():
            parser.error(f"missing binary: {binary}")
    return run_probe(args.frps, args.frpc, args.stage)


if __name__ == "__main__":
    raise SystemExit(main())
