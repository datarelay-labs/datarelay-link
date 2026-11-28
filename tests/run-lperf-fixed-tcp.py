#!/usr/bin/env python3
"""Source-bound Fixed TCP Egress loopback benchmark; never touches installed services."""
import importlib.util
import json
import os
import resource
import socket
import socketserver
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fixedtcp_source_test", ROOT/"tests/test-fixed-tcp-egress.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class _Echo(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 256

class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(12)
        while True:
            try:
                data=self.request.recv(65536)
                if not data: break
                self.request.sendall(data)
            except OSError:
                break

def pct(a,p):
    a=sorted(a)
    if not a: return None
    ix=(len(a)-1)*p
    low=int(ix)
    high=min(low+1,len(a)-1)
    return round(a[low]+(a[high]-a[low])*(ix-low),2)

def main():
    fixture=mod.SQLiteFixedTcpRuntimeTests(
        "test_sqlite_policy_allows_bidirectional_fixed_tcp_application_data"
    )
    fixture.setUp()
    server=None
    try:
        server=_Echo(("127.0.0.1",0),_Handler)
        fixture.echo_port=server.server_address[1]
        threading.Thread(target=server.serve_forever,daemon=True).start()
        # Only test-local admission budget is tuned; installed systemd/config unchanged.
        fixture.state.max_concurrent=128
        fixture.state.per_source_limit=128
        fixture.state._sem=threading.BoundedSemaphore(128)
        gateway=("127.0.0.1",fixture.listen_port)
        output=[]
        counts=tuple(int(x) for x in os.environ.get("LPERF_TCP_COUNTS","10,50,100").split(","))
        if not counts or len(counts)>3 or any(n<1 or n>100 for n in counts):
            raise ValueError("Fixed TCP concurrency must be 1..100, max 3 rounds")
        for n in counts:
            barrier=threading.Barrier(n+1)
            data=b"FIXED_TCP_LPERF_"*(1024) # 16KiB full duplex per connection
            lat=[]
            failures=[]
            def one(i):
                try:
                    barrier.wait(timeout=15)
                    t0=time.monotonic()
                    with socket.create_connection(gateway,timeout=12) as sock:
                        sock.settimeout(12)
                        sock.sendall(data)
                        chunks=[]
                        remaining=len(data)
                        while remaining:
                            packet=sock.recv(min(65536,remaining))
                            if not packet: break
                            chunks.append(packet)
                            remaining-=len(packet)
                        if b"".join(chunks)!=data:
                            failures.append((i,"payload-mismatch"))
                            return
                    lat.append((time.monotonic()-t0)*1000)
                except Exception as e:
                    failures.append((i,type(e).__name__))
            cpu0=resource.getrusage(resource.RUSAGE_SELF)
            t0=time.monotonic()
            with ThreadPoolExecutor(max_workers=n) as pool:
                work=[pool.submit(one,i) for i in range(n)]
                barrier.wait(timeout=15)
                for f in work:f.result(timeout=30)
            wall=time.monotonic()-t0
            cpu1=resource.getrusage(resource.RUSAGE_SELF)
            output.append({"connections":n,"success":len(lat),"failures":len(failures),
                           "failure_examples":failures[:3],
                           "p50_ms":pct(lat,.50),"p95_ms":pct(lat,.95),
                           "p99_ms":pct(lat,.99),
                           "throughput_mbps":round(8*n*len(data)/(max(wall,.001)*1000000),3),
                           "combined_cpu_pct":round(100*(cpu1.ru_utime+cpu1.ru_stime-cpu0.ru_utime-cpu0.ru_stime)/max(wall,.001),2)})
            print("FIXED_TCP_LOAD",json.dumps(output[-1],sort_keys=True),flush=True)
        initial_upstream=len(fixture.connect_attempts)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.bind(("127.0.0.2",0))
            client.connect(gateway)
            denied_payload=client.recv(256)
        time.sleep(.4)
        audits=[json.loads(x) for x in fixture.log_path.read_text().splitlines()]
        decision_counts=Counter(str(x.get("decision")) for x in audits)
        unmatched=[x for x in audits if x.get("source_ip")=="127.0.0.2"]
        print("FIXED_TCP_AUDIT",json.dumps({"records":len(audits),"decision_counts":dict(decision_counts),
              "denied_source_records":len(unmatched),"unauthorized_upstream_attempts":len(fixture.connect_attempts)-initial_upstream,
              "denied_response_bytes":len(denied_payload)},sort_keys=True),flush=True)
        assert all(row["failures"]==0 and row["success"]==row["connections"] for row in output), output
        assert len(audits)==2*sum(counts)+1,(len(audits),len(output))
        assert len(unmatched)==1 and unmatched[0].get("decision")==mod.EG.DECISION_DENY
        assert len(fixture.connect_attempts)==sum(counts)
        print("LPERF_FIXED_TCP_LOOPBACK=PASS",flush=True)
    finally:
        if server:
            server.shutdown()
            server.server_close()
        fixture.tearDown()

if __name__=="__main__":
    main()
