#!/usr/bin/env python3
"""Matched local TCP relay experiment. Python remains policy/audit authority."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import platform
import socket
import socketserver
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))


def _line(sock: socket.socket, text: str) -> str:
    sock.sendall((text + "\n").encode())
    data = bytearray()
    while not data.endswith(b"\n"):
        part = sock.recv(128)
        if not part:
            break
        data.extend(part)
    return data.decode(errors="replace").strip()


@dataclass
class PolicyState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    allowed: bool = True
    generation: int = 1
    deny_budget: int = 0
    audit_available: bool = True
    checks: int = 0
    events: list[dict] = field(default_factory=list)

    def check(self, conn_id: str) -> bool:
        with self.lock:
            self.checks += 1
            if self.deny_budget:
                self.deny_budget -= 1
                allowed = False
            else:
                allowed = self.allowed
            return allowed

    def audit(self, conn_id: str, event: str, up: int, down: int) -> None:
        with self.lock:
            self.events.append({"id": conn_id, "event": event, "up_bytes": up, "down_bytes": down, "time": time.monotonic()})

    def set_allowed(self, value: bool) -> None:
        with self.lock:
            self.allowed = value
            self.generation += 1


class PolicyHandler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline(256).decode(errors="replace").strip().split()
        if not line:
            return
        state: PolicyState = self.server.state
        if line[0] == "CHECK" and len(line) == 2:
            allowed = state.check(line[1])
            with state.lock:
                gen = state.generation
            self.wfile.write((f"ALLOW {gen}\n" if allowed else f"DENY {gen}\n").encode())
        elif line[0] == "AUDIT" and len(line) == 5:
            try:
                if state.audit_available:
                    state.audit(line[1], line[2], int(line[3]), int(line[4]))
                    self.wfile.write(b"OK\n")
            except ValueError:
                pass


class PolicyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, addr, state):
        self.state = state
        super().__init__(addr, PolicyHandler)


class EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.accepted += 1
        while True:
            try:
                data = self.request.recv(65536)
            except OSError:
                return
            if not data:
                try:
                    self.request.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                return
            with self.server.counter_lock:
                self.server.bytes_received += len(data)
            if self.server.delay:
                time.sleep(self.server.delay)
            view = memoryview(data)
            while view:
                try:
                    sent = self.request.send(view)
                    view = view[sent:]
                except OSError:
                    return


class EchoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, addr, delay=0.0):
        self.delay = delay
        self.accepted = 0
        self.bytes_received = 0
        self.counter_lock = threading.Lock()
        super().__init__(addr, EchoHandler)


def serve_python(listen: str, upstream: str, policy_addr: str, revalidate_ms: int, idle_ms: int):
    import frp_egress_runtime as rt

    class Cache:
        class Engine:
            def snapshot(self):
                # A generation change every interval forces the same revalidation
                # RPC cadence as the Rust prototype, without local policy logic.
                return type("Snapshot", (), {"generation": 2, "healthy": True})()
        engine = Engine()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            conn_id = f"py-{threading.get_ident()}-{time.monotonic_ns()}"
            client = self.request
            try:
                with socket.create_connection((policy_addr.split(":")[0], int(policy_addr.split(":")[1])), timeout=2) as s:
                    answer = _line(s, f"CHECK {conn_id}")
                if not answer.startswith("ALLOW"):
                    _audit(policy_addr, conn_id, "denied", 0, 0)
                    return
                upstream_sock = socket.create_connection((upstream.split(":")[0], int(upstream.split(":")[1])), timeout=2)
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                upstream_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                if not _audit(policy_addr, conn_id, "connected", 0, 0):
                    upstream_sock.close()
                    client.close()
                    return
                session = {"session_id": conn_id, "connection_id": conn_id, "source_ip": "127.0.0.1", "hostname": "fixture.test", "port": int(upstream.split(":")[1]), "protocol": "tcp", "method": None, "policy_generation": 1}

                def authorize():
                    try:
                        with socket.create_connection((policy_addr.split(":")[0], int(policy_addr.split(":")[1])), timeout=1) as s:
                            return _line(s, f"CHECK {conn_id}").startswith("ALLOW")
                    except OSError:
                        return False

                started = time.monotonic()
                outcome = rt.relay_bidirectional(
                    client, upstream_sock, cache=Cache(), session=session,
                    revalidate_interval=revalidate_ms / 1000,
                    idle_timeout=idle_ms / 1000, authorize_fn=authorize,
                )
                elapsed = time.monotonic() - started
                name = "revoked" if outcome == "POLICY_REVOKED" else "timeout" if "TIMEOUT" in outcome else "closed"
                _audit(policy_addr, conn_id, name, 0, 0)
                self.server.completions.append({"id": conn_id, "elapsed": elapsed, "outcome": name})
            except OSError:
                _audit(policy_addr, conn_id, "connect_failed", 0, 0)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
        request_queue_size = 64

        def __init__(self, *server_args, **server_kwargs):
            self.relay_slots = threading.BoundedSemaphore(256)
            super().__init__(*server_args, **server_kwargs)

        def process_request(self, request, client_address):
            if not self.relay_slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                self.relay_slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.relay_slots.release()

    server = Server(tuple(map(lambda x: x if not x.isdigit() else int(x), listen.split(":"))), Handler)
    server.completions = []
    print("READY", flush=True)
    server.serve_forever(poll_interval=0.05)


def _audit(addr: str, conn_id: str, event: str, up: int, down: int):
    try:
        host, port = addr.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=1) as s:
            return _line(s, f"AUDIT {conn_id} {event} {up} {down}") == "OK"
    except OSError:
        return False


def _recv_all(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        part = sock.recv(65536)
        if not part:
            return b"".join(chunks)
        chunks.append(part)


def _transfer(addr, payload, timeout=20):
    start = time.perf_counter()
    with socket.create_connection(addr, timeout=timeout) as s:
        s.settimeout(timeout)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        send_errors = []
        def send():
            try:
                s.sendall(payload)
                s.shutdown(socket.SHUT_WR)
            except OSError as exc:
                send_errors.append(exc)
        sender = threading.Thread(target=send)
        sender.start()
        got = _recv_all(s)
        sender.join(timeout)
        if sender.is_alive():
            raise TimeoutError("sender remained blocked after response EOF")
        if send_errors:
            raise send_errors[0]
    elapsed = time.perf_counter() - start
    if got != payload:
        raise AssertionError(f"relay data mismatch expected={len(payload)} got={len(got)}")
    return elapsed, len(got)


def _proc_stats(pid):
    try:
        fields = pathlib.Path(f"/proc/{pid}/stat").read_text().split()
        cpu = (int(fields[13]) + int(fields[14])) / os.sysconf("SC_CLK_TCK")
        status = pathlib.Path(f"/proc/{pid}/status").read_text()
        rss = int(next(x.split()[1] for x in status.splitlines() if x.startswith("VmRSS:"))) * 1024
        return cpu, rss
    except (OSError, StopIteration, ValueError):
        return 0.0, 0


def _wait_listener(addr, proc):
    import select
    ready, _, _ = select.select([proc.stdout], [], [], 10)
    if not ready:
        raise RuntimeError(f"relay READY timeout pid={proc.pid} exit={proc.poll()}")
    line = proc.stdout.readline().strip()
    if line != "READY":
        raise RuntimeError(f"relay startup output {line!r} exit={proc.poll()}")


def _free_addr():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    addr = s.getsockname()
    s.close()
    return addr


def _snapshot(state):
    with state.lock:
        return {"checks": state.checks, "events": list(state.events)}


def _run_candidate(kind, args, rust_bin, output):
    state = PolicyState()
    policy_server = PolicyServer(("127.0.0.1", 0), state)
    threading.Thread(target=policy_server.serve_forever, daemon=True).start()
    policy_addr = policy_server.server_address
    echo = EchoServer(("127.0.0.1", 0))
    threading.Thread(target=echo.serve_forever, daemon=True).start()
    listen = _free_addr()
    revalidate_ms = 1000
    idle_ms = 1800
    if kind == "rust":
        cmd = [str(rust_bin), f"{listen[0]}:{listen[1]}", f"{echo.server_address[0]}:{echo.server_address[1]}", f"{policy_addr[0]}:{policy_addr[1]}", str(revalidate_ms), str(idle_ms)]
    else:
        cmd = [sys.executable, str(pathlib.Path(__file__).resolve()), "--python-server", f"{listen[0]}:{listen[1]}", f"{echo.server_address[0]}:{echo.server_address[1]}", f"{policy_addr[0]}:{policy_addr[1]}", str(revalidate_ms), str(idle_ms)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _wait_listener(listen, proc)
        metrics = {"candidate": kind, "binary": cmd[0], "pid": proc.pid, "cases": []}
        payload = bytes((i * 31 + 7) & 255 for i in range(args.payload_kib * 1024))
        for concurrency in map(int, args.concurrency.split(",")):
            all_times = []
            total_bytes = 0
            wall_s = 0.0
            cpu0, rss0 = _proc_stats(proc.pid)
            rss_samples = [rss0]
            sample_stop = threading.Event()
            def sample_process():
                while not sample_stop.wait(.01):
                    rss_samples.append(_proc_stats(proc.pid)[1])
            sampler = threading.Thread(target=sample_process, daemon=True)
            sampler.start()
            for _round in range(args.rounds):
                batch_started = time.perf_counter()
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    results = list(pool.map(lambda _: _transfer(listen, payload), range(concurrency)))
                wall_s += time.perf_counter() - batch_started
                all_times.extend(x[0] for x in results)
                total_bytes += sum(x[1] for x in results)
            sample_stop.set()
            sampler.join()
            cpu1, _ = _proc_stats(proc.pid)
            max_rss = max(rss_samples)
            case = {"connections": concurrency * args.rounds, "concurrency": concurrency, "payload_bytes": len(payload), "p50_ms": statistics.median(all_times)*1000, "p95_ms": _percentile(all_times, .95)*1000, "p99_ms": _percentile(all_times, .99)*1000, "wall_s": wall_s, "aggregate_mib_s": total_bytes / max(wall_s, 1e-9) / (1024*1024), "relay_cpu_s": max(0, cpu1-cpu0), "relay_peak_rss_bytes_sampled": max_rss, "verified_payload_bytes": total_bytes}
            metrics["cases"].append(case)

        # Bounded backpressure: a slow echo peer and 4 MiB full-duplex streams.
        echo.delay = 0.001
        slow_payload = bytes((i * 13 + 3) & 255 for i in range(4 * 1024 * 1024))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            slow = list(pool.map(lambda _: _transfer(listen, slow_payload), range(4)))
        if sum(n for _, n in slow) != 16 * 1024 * 1024:
            raise AssertionError("backpressure stream byte count mismatch")
        metrics["backpressure"] = {"sessions": 4, "bytes_each": len(slow_payload), "verified_bytes": sum(n for _, n in slow), "max_elapsed_s": max(t for t, _ in slow), "expected_buffer_cap_bytes_per_direction": 256*1024}
        echo.delay = 0

        # Fresh deny must not connect upstream or produce an allow receipt.
        with state.lock:
            state.deny_budget = 1
        accepted_before_deny = echo.accepted
        with socket.create_connection(listen, timeout=2) as s:
            s.settimeout(2)
            denied_data = s.recv(1)
        if denied_data:
            raise AssertionError("denied connection received upstream data")
        time.sleep(.05)
        if echo.accepted != accepted_before_deny:
            raise AssertionError("denied connection reached the upstream")
        metrics["denial"] = {"client_bytes": len(denied_data), "upstream_connections": echo.accepted - accepted_before_deny, "audits": [e["event"] for e in _snapshot(state)["events"] if e["event"] == "denied"]}

        # A live session is closed after the same 1s policy-generation recheck.
        state.set_allowed(True)
        rev = socket.create_connection(listen, timeout=2)
        rev.settimeout(5)
        rev.sendall(b"before-revoke")
        if rev.recv(64) != b"before-revoke":
            raise AssertionError("pre-revocation data mismatch")
        time.sleep(.1)
        state.set_allowed(False)
        revoked_data = _recv_all(rev)
        rev.close()
        time.sleep(.1)
        rev_events = [e for e in _snapshot(state)["events"] if e["event"] == "revoked"]
        if not rev_events or revoked_data:
            raise AssertionError(f"revocation failed closed: events={_snapshot(state)['events']} data={len(revoked_data)}")
        metrics["revocation"] = {"closed": True, "unexpected_post_revoke_bytes": len(revoked_data), "audit_count": len(rev_events)}
        state.set_allowed(True)

        # Explicitly exercise idle timeout and require eventual close.
        idle = socket.create_connection(listen, timeout=2)
        idle.settimeout(3)
        time.sleep(2.2)
        idle_data = idle.recv(1)
        idle.close()
        time.sleep(.1)
        timeout_events = [e for e in _snapshot(state)["events"] if e["event"] == "timeout"]
        if idle_data or not timeout_events:
            raise AssertionError(f"idle timeout missing: bytes={len(idle_data)} events={timeout_events}")
        metrics["timeout"] = {"closed": True, "audit_count": len(timeout_events), "configured_idle_ms": idle_ms}

        # Mixed load: 40 successful sessions with one fresh deny at admission.
        echo.delay = 0.002
        mixed_payload = bytes((i * 7 + 9) & 255 for i in range(256 * 1024))
        connected_before = sum(e["event"] == "connected" for e in _snapshot(state)["events"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=41) as pool:
            futures = [pool.submit(_transfer, listen, mixed_payload) for _ in range(40)]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                connected = sum(e["event"] == "connected" for e in _snapshot(state)["events"])
                if connected - connected_before >= 40:
                    break
                time.sleep(0.005)
            else:
                raise AssertionError(f"mixed load did not establish 40 allowed sessions (got {connected-connected_before})")
            with state.lock:
                state.deny_budget = 1
            denied_future = pool.submit(_denied_transfer, listen)
            mixed_results = [f.result(timeout=20) for f in futures]
            denied_result = denied_future.result(timeout=5)
            if denied_result[1]:
                raise AssertionError("mixed-load denied connection received bytes")
        if len(mixed_results) != 40:
            raise AssertionError("mixed-load allowed transfer count mismatch")
        echo.delay = 0
        time.sleep(.1)
        events = _snapshot(state)["events"]
        metrics["mixed_load"] = {"allowed_streams": 40, "verified_audit_connected": sum(e["event"] == "connected" for e in events), "denied_audits": sum(e["event"] == "denied" for e in events), "revoked_audits": sum(e["event"] == "revoked" for e in events), "policy_checks": _snapshot(state)["checks"]}
        if metrics["mixed_load"]["denied_audits"] < 2:
            raise AssertionError("fresh deny under mixed load was not audited")
        metrics["all_audits"] = {name: sum(e["event"] == name for e in events) for name in ("connected", "denied", "revoked", "timeout", "closed", "connect_failed")}
        metrics["policy_checks"] = _snapshot(state)["checks"]
        expected_connected = sum(map(int, args.concurrency.split(","))) * args.rounds + 4 + 1 + 1 + 40
        expected_closed = sum(map(int, args.concurrency.split(","))) * args.rounds + 4 + 40
        if metrics["all_audits"] != {"connected": expected_connected, "denied": 2, "revoked": 1, "timeout": 1, "closed": expected_closed, "connect_failed": 0}:
            raise AssertionError(f"audit ledger mismatch expected connected={expected_connected}/closed={expected_closed}/deny=2/revoked=1/timeout=1 actual={metrics['all_audits']}")
        # If the audit authority cannot acknowledge an ALLOW connection receipt,
        # neither candidate may forward client bytes.
        with state.lock:
            state.audit_available = False
        before_bytes = echo.bytes_received
        audit_failure = socket.create_connection(listen, timeout=2)
        audit_failure.settimeout(3)
        audit_failure.sendall(b"audit-must-be-available-before-relay")
        audit_failure.shutdown(socket.SHUT_WR)
        outage_chunks = []
        reset_on_close = False
        try:
            while True:
                part = audit_failure.recv(65536)
                if not part:
                    break
                outage_chunks.append(part)
        except ConnectionResetError:
            reset_on_close = True
        outage_response = b"".join(outage_chunks)
        audit_failure.close()
        time.sleep(.05)
        if outage_response or echo.bytes_received != before_bytes:
            raise AssertionError("relay forwarded payload without an acknowledged ALLOW audit")
        metrics["audit_sink_failure"] = {"closed": True, "reset_on_close": reset_on_close, "forwarded_bytes": echo.bytes_received - before_bytes, "ack_required_for_forwarding": True}
        metrics["functional"] = "PASS"
        output[kind] = metrics
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait()
        policy_server.shutdown(); policy_server.server_close()
        echo.shutdown(); echo.server_close()


def _denied_transfer(addr):
    with socket.create_connection(addr, timeout=3) as s:
        s.settimeout(3)
        data = s.recv(1)
        return ("denied", data)


def _percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        return 0
    return ordered[min(len(ordered)-1, max(0, int((len(ordered)-1)*p + .999999)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", default="10,50,100")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--payload-kib", type=int, default=256)
    ap.add_argument("--rust-bin", type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path)
    ap.add_argument("--order", default="python,rust", help="candidate order for balanced reruns")
    ap.add_argument("--python-server", nargs=5, metavar=("LISTEN", "UPSTREAM", "POLICY", "REVALIDATE_MS", "IDLE_MS"))
    args = ap.parse_args()
    if args.python_server:
        serve_python(args.python_server[0], args.python_server[1], args.python_server[2], int(args.python_server[3]), int(args.python_server[4]))
        return
    rust_bin = args.rust_bin or ROOT / "experiments/r1-rust-egress-poc/target/release/r1-egress-relay-poc"
    output = {}
    order = [x.strip() for x in args.order.split(",") if x.strip()]
    if sorted(order) != ["python", "rust"]:
        ap.error("--order must name python and rust once each")
    for kind in order:
        _run_candidate(kind, args, rust_bin, output)
    rust_env = os.environ.copy()
    lib_dirs = "/home/aella/.local/rust-1.75/usr/lib/x86_64-linux-gnu:/home/aella/.local/rust-1.75/usr/lib"
    rust_env["LD_LIBRARY_PATH"] = lib_dirs + (":" + rust_env["LD_LIBRARY_PATH"] if rust_env.get("LD_LIBRARY_PATH") else "")
    rust_version = subprocess.check_output(["/home/aella/.local/rust-1.75/usr/bin/rustc", "--version"], text=True, env=rust_env).strip()
    experiment_files = [pathlib.Path(__file__), pathlib.Path(__file__).parent / "Cargo.toml", pathlib.Path(__file__).parent / "Cargo.lock", pathlib.Path(__file__).parent / "src/main.rs"]
    digests = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in experiment_files}
    relay_path = ROOT / "lib/frp_egress_runtime.py"
    binary_digest = hashlib.sha256(rust_bin.read_bytes()).hexdigest()
    result = {"schema": "drlink-r1-egress-poc-v1", "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "candidate_order": order, "experiment_files_sha256": digests, "python_reference_sha256": hashlib.sha256(relay_path.read_bytes()).hexdigest(), "rust_release_binary_sha256": binary_digest, "python": sys.version, "rustc": rust_version, "host": platform.uname()._asdict(), "method": {"source": "production lib/frp_egress_runtime.py relay_bidirectional for Python; isolated Tokio TCP relay for Rust; shared Python policy/audit TCP service; local loopback destination; no product code or policy authority ported", "revalidation_ms": 1000, "idle_ms": 1800, "buffer_cap_per_direction_bytes": 262144, "benchmark_payload_kib": args.payload_kib, "rounds": args.rounds}, "results": output}
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded)


if __name__ == "__main__":
    main()
