#!/usr/bin/env python3
"""Internet Access gateway must queue a connection burst up to its worker capacity.

socketserver.TCPServer defaults to a listen backlog of 5. With 12+ concurrent
clients opening new connections (P-010 upload/download load through the proxy)
the accept queue overflowed (kernel ListenOverflows), SYNs were dropped and a
fraction of requests were reset or delayed by TCP retransmission before policy
code even ran. The listener backlog must follow the authorized worker capacity.
"""
from __future__ import annotations

import importlib.util
import json
import os
import select
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))


class EgressListenBacklog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = str(root)
        cfg_path = root / "etc/drlink/config.json"
        cfg_path.parent.mkdir(parents=True)
        (root / "var/log/drlink/egress").mkdir(parents=True)
        (root / "var/lib/drlink").mkdir(parents=True)
        cfg_path.write_text(json.dumps({
            "egress_conn_log_file": "/var/log/drlink/egress/connections.jsonl",
            "egress_listen_addr": "127.0.0.1",
            "egress_listen_port": 0,
        }) + "\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("frp_egress_gateway_backlog", ROOT / "server" / "frp-egress-gateway.py")
        self.GW = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.GW)
        self.cfg_path = cfg_path

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def _server(self, max_concurrent):
        cache = self.GW.PolicyCache(self.cfg_path)
        state = self.GW.GatewayState(cache, max_concurrent=max_concurrent, per_source_limit=256)
        return self.GW.ThreadedTCPServer(("127.0.0.1", 0), state)

    def test_backlog_follows_worker_capacity(self):
        server = self._server(64)
        try:
            self.assertEqual(server.request_queue_size, 64)
        finally:
            server.server_close()

    def test_burst_of_connects_is_queued_while_workers_are_busy(self):
        # The accept loop is intentionally not running: this is the kernel
        # accept queue seen by a connection burst. With the default backlog of
        # 5 only ~6 handshakes complete and the rest sit in SYN retransmission.
        burst = 48
        server = self._server(64)
        socks = []
        try:
            port = server.server_address[1]
            for _ in range(burst):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setblocking(False)
                s.connect_ex(("127.0.0.1", port))
                socks.append(s)
            deadline = time.time() + 0.8
            done = set()
            while time.time() < deadline and len(done) < burst:
                pending = [s for s in socks if s not in done]
                _r, w, _x = select.select([], pending, [], 0.1)
                for s in w:
                    if s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
                        done.add(s)
            self.assertEqual(len(done), burst, "only %d of %d handshakes completed without SYN retransmission" % (len(done), burst))
        finally:
            for s in socks:
                s.close()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
