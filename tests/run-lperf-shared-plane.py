#!/usr/bin/env python3
"""Disposable shared-control-plane MCP + Egress test, exploratory only.

Uses the SAME SQLite ControlPlane root for synthetic multi-Agent MCP calls
and gateway Internet Access policy, not two independent benchmark roots.
No installed service, credentials, routes, ACLs or public ports are touched.
"""
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"lib"))
sys.path.insert(0,str(ROOT/"tests"))

def module_from_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

scale=module_from_file("lperf_scale_shared_probe", ROOT/"tests/test-mcp-bridge-scale-target.py")
bench=module_from_file("lperf_egress_shared_probe", ROOT/"tests/run-egress-benchmark-worker.py")
import frp_egress_control as EG
import drlink_v24 as v24

class SharedControlPlaneLoad(scale.MCPBridgeScaleTargetTests):
    def test_mcp_and_egress_share_control_plane(self):
        root=Path(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"]=str(root)
        self.addCleanup(lambda:os.environ.pop("FRP_DEPLOY_TEST_ROOT",None))
        self.assertTrue((root/"var/lib/drlink").exists())

        # Prepare Egress state and compiled Internet ACL in the already
        # running MCP/Agent 100-host root. No extra database is used.
        libdir=root/"usr/local/lib/drlink"
        libdir.mkdir(parents=True,exist_ok=True)
        for name in ("frp_egress_control.py","frp_public_suffix.py",
                     "frp_bounded_server.py","frp_policy_fingerprint.py"):
            (libdir/name).write_bytes((ROOT/"lib"/name).read_bytes())
        (libdir/"data").mkdir(exist_ok=True)
        (libdir/"data/public_suffix_list.dat").write_bytes(
            (ROOT/"lib/data/public_suffix_list.dat").read_bytes())

        eg_path=root/"var/lib/drlink/egress-control.json"
        EG.save_egress_state(EG.empty_egress_state(),path=eg_path)
        def mutate(state):
            pid,_=EG.create_profile(state,"shared-bench",enabled=False)
            EG.add_source(state,pid,"127.0.0.1/32")
            EG.add_destination(state,pid,"allowed.test",443,protocol="https")
            EG.set_profile_enabled(state,pid,True)
        EG.mutate_egress_state(mutate,path=eg_path)

        plane=self.plane
        v24.set_network_object(plane,"proxy-src",type="ip",value="127.0.0.1",oneshot=True)
        v24.set_network_object(plane,"allowed-host",type="fqdn",value="allowed.test",oneshot=True)
        v24.set_service_object(plane,"https",type="tcp",port=443,oneshot=True)
        v24.set_access_rule(plane,"internet","allow-https",mode="whitelist",
                            source="proxy-src",destination="allowed-host",
                            service="https",enabled=True,oneshot=True)
        # Same 30 target ACLs as MCP scale test; all updates on one shared DB.
        for index in range(scale.TARGET_CONCURRENT_CALLS):
            label="scale%03d"%index
            rule="mcp-shared-%03d"%index
            v24.set_ai_access_rule(
                plane,rule,mode="whitelist",source="cursor-dev",
                destination=label,permission="lab-maintenance-perms",
                enabled=True,oneshot=True)
            v24.set_ai_policy_path_scopes(
                plane,rule,[self.etc_glob,self.opt_glob,self.vendor_glob])
        plane.compile_runtime()

        cfg=root/"etc/drlink/config.json"
        cfg.parent.mkdir(parents=True,exist_ok=True)
        old=json.loads(cfg.read_text()) if cfg.is_file() else {}
        old.update(egress_control_file="/var/lib/drlink/egress-control.json",
                   egress_conn_log_file="/var/log/drlink/egress/connections.jsonl",
                   egress_listen_addr="127.0.0.1",egress_listen_port=0)
        cfg.write_text(json.dumps(old)+"\n")
        (root/"var/log/drlink/egress").mkdir(parents=True,exist_ok=True)

        hello=bench.build_client_hello("allowed.test")
        transfer_size=16*1024
        origin=bench.Origin(expected_tls_bytes=len(hello)+transfer_size)
        self.addCleanup(origin.stop)
        GW=module_from_file("frp_egress_gateway_shared_probe",
                            ROOT/"server/frp-egress-gateway.py")
        attempts=[]
        def connect(ip,port,hostname,timeout):
            if hostname!="allowed.test" or ip!="1.2.3.4":
                attempts.append((ip,port,hostname))
                raise OSError("Unexpected unauthorized upstream call")
            return socket.create_connection(("127.0.0.1",origin.port),timeout=timeout)
        cache=GW.PolicyCache(cfg)
        gw=GW.GatewayState(cache,resolve_fn=lambda h:["1.2.3.4"] if h in ("allowed.test","denied.test") else [],
                           connect_fn=connect,max_concurrent=100,per_source_limit=100)
        gateway=GW.ThreadedTCPServer(("127.0.0.1",0),gw)
        self.addCleanup(gateway.server_close)
        self.addCleanup(gateway.shutdown)
        threading.Thread(target=gateway.serve_forever,daemon=True).start()
        port=gateway.server_address[1]
        ok=[]
        denies=[]
        errors=[]
        t0=time.monotonic()
        def one_egress(i):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=10) as sock:
                    sock.settimeout(10)
                    host="denied.test" if i==0 else "allowed.test"
                    sock.sendall(("CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n\r\n"%
                                  (host,host)).encode())
                    result=sock.recv(4096)
                    if i==0:
                        print("MIXED_DENY_RESPONSE", repr(result[:230]), flush=True)
                        denies.append(result.startswith(b"HTTP/1.1 403"))
                        return
                    if not result.startswith(b"HTTP/1.1 200"):
                        errors.append(("connect",i,result[:100]))
                        return
                    sock.sendall(hello+b"x"*transfer_size)
                    ack=b""
                    while len(ack)<len(bench.TRANSFER_ACK):
                        chunk=sock.recv(len(bench.TRANSFER_ACK)-len(ack))
                        if not chunk: break
                        ack+=chunk
                    if ack==bench.TRANSFER_ACK:
                        ok.append((i,round((time.monotonic()-t0)*1000)))
                    else:
                        errors.append(("ack",i,ack))
            except Exception as e:
                errors.append(("exception",i,type(e).__name__))
        def egress_burst():
            with ThreadPoolExecutor(max_workers=21) as pool:
                list(pool.map(one_egress,range(21)))

        with ThreadPoolExecutor(max_workers=2) as pool:
            mcp_task=pool.submit(self._simultaneous_calls,
                                 lambda i:"scale%03d"%i)
            egress_task=pool.submit(egress_burst)
            egress_task.result(timeout=45)
            mcp_task.result(timeout=90)

        audit_path=root/"var/log/drlink/egress/connections.jsonl"
        audits=[json.loads(x) for x in audit_path.read_text().splitlines()]
        ids={x.get("connection_id") for x in audits}
        dbfile=plane.conn.execute("PRAGMA database_list").fetchall()
        self.assertTrue(dbfile, "no SQLite backing DB")
        jobs=plane.conn.execute(
            "SELECT COUNT(*) FROM ai_jobs WHERE status='done'").fetchone()[0]
        print("SHARED_PLANEROOT",root,"SAME_SQLITE_ROOT",str(root) in str(dbfile),flush=True)
        print("SHARED_MCP_JOB_DONE",jobs,"EGRESS_ALLOWED",len(ok),
              "EGRESS_DENIED",denies,"EGRESS_AUDITS",len(ids),
              "ACKS",origin.acknowledged_transfers,"FORBIDDEN_CONNECTS",len(attempts),
              "EGRESS_ERRORS",errors[:3],flush=True)
        self.assertEqual(jobs,scale.TARGET_CONCURRENT_CALLS*scale.ROUNDS)
        self.assertEqual(len(ok),20)
        self.assertEqual(denies,[True])
        self.assertEqual(origin.acknowledged_transfers,20)
        self.assertEqual(len(ids),21)
        self.assertFalse(attempts)
        self.assertFalse(errors)

if __name__=="__main__":
    unittest.main(defaultTest="SharedControlPlaneLoad.test_mcp_and_egress_share_control_plane")
