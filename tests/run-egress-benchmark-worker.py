#!/usr/bin/env python3
"""Worker for tests/run-egress-benchmark.py — local CONNECT latency under load."""
from __future__ import annotations

import importlib.util
import json
import os
import resource
import socket
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

spec_eg = importlib.util.spec_from_file_location(
    "frp_egress_control", ROOT / "lib" / "frp_egress_control.py"
)
EG = importlib.util.module_from_spec(spec_eg)
spec_eg.loader.exec_module(EG)


def build_client_hello(sni: str) -> bytes:
    host = sni.encode("ascii")
    name_entry = b"\x00" + len(host).to_bytes(2, "big") + host
    sni_list = len(name_entry).to_bytes(2, "big") + name_entry
    sni_ext = b"\x00\x00" + len(sni_list).to_bytes(2, "big") + sni_list
    body = bytearray()
    body += b"\x03\x03" + b"\x00" * 32 + b"\x00" + b"\x00\x02\x00\x2f" + b"\x01\x00"
    body += len(sni_ext).to_bytes(2, "big") + sni_ext
    handshake = b"\x01" + len(body).to_bytes(3, "big") + bytes(body)
    return b"\x16\x03\x01" + len(handshake).to_bytes(2, "big") + handshake


class Origin:
    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(256)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self.bytes = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket):
        try:
            conn.settimeout(5)
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                self.bytes += len(data)
                # Echo a tiny TLS-looking ack so clients don't hang forever.
                try:
                    conn.sendall(b"\x16\x03\x03\x00\x01\x00")
                except OSError:
                    break
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self):
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def main() -> int:
    concurrency = int(os.environ.get("DRLINK_EGRESS_BENCH_CONCURRENCY", "100"))
    hold_ms = int(os.environ.get("DRLINK_EGRESS_BENCH_HOLD_MS", "100"))
    churn = int(os.environ.get("DRLINK_EGRESS_BENCH_CHURN", "0"))
    transfer_kib = int(os.environ.get("DRLINK_EGRESS_BENCH_TRANSFER_KIB", "0"))

    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    os.environ["FRP_DEPLOY_TEST_ROOT"] = str(root)
    libdir = root / "usr/local/lib/drlink"
    libdir.mkdir(parents=True)
    for name in ("frp_egress_control.py", "frp_public_suffix.py", "frp_bounded_server.py", "frp_policy_fingerprint.py"):
        (libdir / name).write_text((ROOT / "lib" / name).read_text(encoding="utf-8"), encoding="utf-8")
    data_dst = libdir / "data"
    data_dst.mkdir(parents=True)
    (data_dst / "public_suffix_list.dat").write_bytes(
        (ROOT / "lib" / "data" / "public_suffix_list.dat").read_bytes()
    )
    state_path = root / "var/lib/drlink/egress-control.json"
    state_path.parent.mkdir(parents=True)
    EG.save_egress_state(EG.empty_egress_state(), path=state_path)

    def mut(state):
        pid, _ = EG.create_profile(state, "bench", enabled=False)
        EG.add_source(state, pid, "127.0.0.1/32")
        EG.add_destination(state, pid, "allowed.test", 443, protocol="https")
        EG.set_profile_enabled(state, pid, True)
        return pid

    EG.mutate_egress_state(mut, path=state_path)
    cfg = {
        "egress_control_file": "/var/lib/drlink/egress-control.json",
        "egress_conn_log_file": "/var/log/drlink/egress/connections.jsonl",
        "egress_listen_addr": "127.0.0.1",
        "egress_listen_port": 0,
    }
    cfg_path = root / "etc/drlink/config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (root / "var/log/drlink/egress").mkdir(parents=True, exist_ok=True)

    # Both a gateway profile and a compiled Internet Access rule are required.
    from drlink_control_plane import ControlPlane
    import drlink_v24 as v24

    plane = ControlPlane(str(root))
    try:
        v24.set_network_object(plane, "proxy-src", type="ip", value="127.0.0.1", oneshot=True)
        v24.set_network_object(plane, "allowed-host", type="fqdn", value="allowed.test", oneshot=True)
        v24.set_service_object(plane, "https", type="tcp", port=443, oneshot=True)
        v24.set_access_rule(
            plane, "internet", "allow-https", mode="whitelist", source="proxy-src",
            destination="allowed-host", service="https", enabled=True, oneshot=True,
        )
        plane.compile_runtime()
    finally:
        plane.close()

    origin = Origin()
    gw_path = ROOT / "server" / "frp-egress-gateway.py"
    spec = importlib.util.spec_from_file_location("frp_egress_gateway_bench", gw_path)
    GW = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(GW)

    def resolve2(hostname: str):
        if hostname == "allowed.test":
            return ["1.2.3.4"]
        raise OSError("nxdomain")

    def connect(ip: str, port: int, hostname: str, timeout: float):
        return socket.create_connection(("127.0.0.1", origin.port), timeout=timeout)

    cache = GW.PolicyCache(cfg_path)
    gw_state = GW.GatewayState(
        cache,
        resolve_fn=resolve2,
        connect_fn=connect,
        max_concurrent=max(concurrency, 256),
        per_source_limit=max(concurrency, 256),
        dns_pending_limit=128,
    )
    server = GW.ThreadedTCPServer(("127.0.0.1", 0), gw_state)
    proxy_port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.1)

    hello = build_client_hello("allowed.test")
    latencies_ms: list[float] = []
    failures = 0
    lock = threading.Lock()

    def one_connect(_i: int) -> None:
        nonlocal failures
        t0 = time.perf_counter()
        try:
            sock = socket.create_connection(("127.0.0.1", proxy_port), timeout=10)
            sock.settimeout(10)
            sock.sendall(
                b"CONNECT allowed.test:443 HTTP/1.1\r\nHost: allowed.test:443\r\n\r\n"
            )
            first = sock.recv(4096)
            if not first.startswith(b"HTTP/1.1 200"):
                with lock:
                    failures += 1
                sock.close()
                return
            elapsed = (time.perf_counter() - t0) * 1000.0
            sock.sendall(hello)  # SNI checked after CONNECT 200.
            with lock:
                latencies_ms.append(elapsed)
            if transfer_kib:
                payload = b"x" * 16384
                remaining = transfer_kib * 1024
                while remaining:
                    chunk = min(remaining, len(payload))
                    sock.sendall(payload[:chunk])
                    remaining -= chunk
            time.sleep(hold_ms / 1000.0)
            sock.close()
        except Exception:
            with lock:
                failures += 1

    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    t_wall0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [pool.submit(one_connect, i) for i in range(concurrency)]
        for fut in as_completed(futs):
            fut.result()
    wall = time.perf_counter() - t_wall0
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    user_cpu = cpu_end.ru_utime - cpu_start.ru_utime
    sys_cpu = cpu_end.ru_stime - cpu_start.ru_stime

    # Optional churn sample
    churn_ok = 0
    churn_fail = 0
    if churn > 0:
        duration = 2.0
        deadline = time.time() + duration
        interval = 1.0 / float(churn)

        def churn_one():
            nonlocal churn_ok, churn_fail
            try:
                sock = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
                sock.settimeout(5)
                sock.sendall(
                    b"CONNECT allowed.test:443 HTTP/1.1\r\nHost: allowed.test:443\r\n\r\n" + hello
                )
                first = sock.recv(4096)
                sock.close()
                if first.startswith(b"HTTP/1.1 200"):
                    churn_ok += 1
                else:
                    churn_fail += 1
            except Exception:
                churn_fail += 1

        next_t = time.time()
        while time.time() < deadline:
            threading.Thread(target=churn_one, daemon=True).start()
            next_t += interval
            sleep_for = next_t - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)
        time.sleep(0.5)

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    total = len(latencies_ms) + failures
    failure_rate = (failures / total) if total else 1.0
    throughput = (origin.bytes / (1024.0 * 1024.0)) / wall if wall > 0 else 0.0

    print("MAX_STABLE_CONCURRENT=%d" % concurrency)
    print("THROUGHPUT_MBPS=%.3f" % (throughput * 8.0))
    print("CPU_PERCENT=%.2f" % (100 * (user_cpu + sys_cpu) / wall if wall else 0))
    print("CPU_USER_S=%.5f" % user_cpu)
    print("CPU_SYS_S=%.5f" % sys_cpu)
    print("CPU_SCOPE=combined_local_gateway_origin_and_clients")
    print("TRANSFER_KIB_PER_CONNECTION=%d" % transfer_kib)
    print("ORIGIN_RECEIVED_BYTES=%d" % origin.bytes)
    print("RSS_MB=%.1f" % rss)
    print("CONNECT_P50_MS=%.2f" % percentile(latencies_ms, 50))
    print("CONNECT_P95_MS=%.2f" % percentile(latencies_ms, 95))
    print("CONNECT_P99_MS=%.2f" % percentile(latencies_ms, 99))
    print("DNS_P95_MS=n/a")
    print("TCP_CONNECT_P95_MS=n/a")
    print("FAILURE_RATE=%.4f" % failure_rate)
    print("AUDIT_DROP_COUNT=n/a")  # No measured audit loss accounting in this lab harness.
    if churn > 0:
        print("CHURN_TARGET_PER_SEC=%d" % churn)
        print("CHURN_OK=%d" % churn_ok)
        print("CHURN_FAIL=%d" % churn_fail)
    print(
        "NOTES=local userspace gateway; DNS/connect stubbed; no production/network capacity claim"
    )

    try:
        server.shutdown()
    except Exception:
        pass
    origin.stop()
    tmp.cleanup()
    os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
    return 0 if failure_rate < 0.05 and latencies_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
