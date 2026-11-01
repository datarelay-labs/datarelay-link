#!/usr/bin/env python3
"""macOS live frpc process, transport socket, and current proxy epoch guards."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import drlink_v24_runtime as runtime


class MacOSRuntimeProof(unittest.TestCase):
    HOST = "Leeui-MacBookAir-2d6b3b90"
    PROXY = HOST + "-rs-ssh"
    EXPECTED = {"rs-ssh": {"id": "rs-ssh", "enabled": True}}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="drlink-macos-proof-")
        self.root = Path(self.temp.name)
        self.config = self.root / "Library/Application Support/drlink/frpc.toml"
        self.log = self.root / "Library/Application Support/drlink/logs/frpc.out.log"
        self.log.parent.mkdir(parents=True)
        self.config.write_text(
            'serverAddr = "221.139.249.113"\nserverPort = 443\n',
            encoding="utf-8"
        )
        self.logs = (
            "2026-11-01 10:34:25.890 [I] try to connect to server...\n"
            "2026-11-01 10:34:25.924 [I] login to server success\n"
            "2026-11-01 10:34:25.933 [I] [%s] start proxy success\n"
        ) % self.PROXY
        self.socket = (
            "frpc 84156 root 4u IPv4 0t0 TCP "
            "192.168.86.65:49437->221.139.249.113:443 (ESTABLISHED)"
        )
        self.launch = "state = running\npid = 84156\n"
        self.started = "Sat Oct 31 23:06:07 2026"
        self.log.write_text(self.logs, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def probe(self):
        def run(args, **kwargs):
            if args[0] == "launchctl":
                return self.launch
            if args[0] == "ps" and args[-1] == "command=":
                return "/Library/Application Support/drlink/bin/frpc -c " + str(self.config)
            if args[0] == "ps" and args[-1] == "lstart=":
                return self.started
            if args[0] == "lsof":
                return self.socket
            raise AssertionError(args)
        with (mock.patch.object(runtime.sys, "platform", "darwin"),
              mock.patch.object(runtime, "_frpc_toml_path", return_value=self.config),
              mock.patch.object(runtime.subprocess, "check_output", side_effect=run)):
            return runtime._current_runtime_ready(
                str(self.root), self.HOST, self.EXPECTED,
            )

    def test_live_process_socket_and_proxy_epoch_prove_ready(self):
        self.assertTrue(self.probe())

    def test_prior_process_success_is_not_current_generation(self):
        self.started = "Sun Nov  1 10:35:07 2026"
        self.assertFalse(self.probe())

    def test_socket_disconnected_fails_closed(self):
        self.socket = "frpc 84156 root 4u TCP 127.0.0.1:49437->221.139.249.113:80 (ESTABLISHED)"
        self.assertFalse(self.probe())

    def test_latest_epoch_reconnect_without_proxy_start_fails(self):
        self.log.write_text(
            self.logs + "2026-11-01 10:36:00.100 [I] try to connect to server...\n"
            "2026-11-01 10:36:01.100 [I] login to server success\n",
            encoding="utf-8",
        )
        self.assertFalse(self.probe())

    def test_latest_epoch_proxy_restart_recovers(self):
        self.log.write_text(
            self.logs + "2026-11-01 10:36:00.100 [I] try to connect to server...\n"
            "2026-11-01 10:36:01.100 [I] login to server success\n"
            "2026-11-01 10:36:01.110 [I] [%s] start proxy success\n" % self.PROXY,
            encoding="utf-8",
        )
        self.assertTrue(self.probe())

    def test_launch_job_stopped_fails_closed(self):
        self.launch = "state = waiting\npid = 84156\n"
        self.assertFalse(self.probe())

    def test_wrong_configured_server_fails_closed(self):
        self.config.write_text('serverAddr = "203.0.113.2"\nserverPort = 443\n')
        self.assertFalse(self.probe())

    def test_missing_proxy_start_fails_closed(self):
        self.log.write_text(
            "2026-11-01 10:34:25.924 [I] login to server success\n",
            encoding="utf-8",
        )
        self.assertFalse(self.probe())

    def test_nonmatching_daemon_pid_fails_closed(self):
        self.launch = "state = running\npid = 84156\npid = 99\n"
        self.assertFalse(self.probe())


    def test_ipv6_server_socket_proves_ready(self):
        # F-010: lsof -nP prints IPv6 peers in brackets; an IPv6 Server must
        # not be reported DEGRADED when the live control socket exists.
        self.config.write_text('serverAddr = "2001:DB8::10"\nserverPort = 443\n')
        self.socket = (
            "frpc 84156 root 4u IPv6 0t0 TCP "
            "[2001:db8::65]:49437->[2001:db8::10]:443 (ESTABLISHED)"
        )
        self.assertTrue(self.probe())

    def test_ipv6_server_wrong_peer_fails_closed(self):
        self.config.write_text('serverAddr = "2001:db8::10"\nserverPort = 443\n')
        for peer in ("[2001:db8::11]:443", "[2001:db8::10]:80", "2001:db8::10:443"):
            with self.subTest(peer=peer):
                self.socket = "frpc 84156 root 4u IPv6 0t0 TCP [2001:db8::65]:49437->%s (ESTABLISHED)" % peer
                self.assertFalse(self.probe())

    def test_dns_hostname_server_still_fails_closed(self):
        self.config.write_text('serverAddr = "relay.example.com"\nserverPort = 443\n')
        self.socket = "frpc 84156 root 4u IPv4 0t0 TCP 192.168.86.65:49437->relay.example.com:443 (ESTABLISHED)"
        self.assertFalse(self.probe())


if __name__ == "__main__":
    unittest.main()
