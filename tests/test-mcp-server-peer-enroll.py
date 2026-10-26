#!/usr/bin/env python3
"""Hermetic Server Peer enrollment test; no real central credentials or calls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import drlink_server_peer_enroll as enrollment
import drlink_server_peer as peer
import frp_mgmt_auth as MGMT


class ServerPeerEnrollTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-peer-enroll-")
        self.base = Path(self.tmp.name)
        self.peer_root = self.base / "server-peer"
        self.codefile = self.base / "central-code.txt"
        self.code = "0123456789abcdef." + "a" * 64
        self.codefile.write_text(self.code)
        self.codefile.chmod(0o600)
        self.central = "https://remote.xdr.ooo"
        self.label = "test DRLink Server"

    def tearDown(self):
        self.tmp.cleanup()

    def simulate(self, url, request, id, secret):
        if url.endswith("/enroll/preflight"):
            return {"valid": True}
        if url.endswith("/enroll"):
            self.assertEqual(request["services"], [])
            self.assertEqual(request["mgmt_alg"], "ecdsa-p256-sha256")
            self.assertIn("PUBLIC KEY", request["mgmt_pubkey"])
            response = {
                "services": [], "mgmt_status": "enrolled",
                "token_ciphertext": "test-ciphertext",
                "frp_server": "remote.xdr.ooo", "frp_server_port": 443,
                "frp_transport": "tcp", "public_hostname": "remote.xdr.ooo",
            }
            response["response_hmac"] = MGMT.hmac_hex(secret, MGMT.canonical_json(response))
            return response
        raise AssertionError("Unexpected path: " + url)

    def run_enroll(self):
        return enrollment.enroll(root=str(self.peer_root), central=self.central,
                                 code_file=str(self.codefile), label=self.label)

    def test_uses_separate_root_without_installing_agent(self):
        with patch.object(enrollment, "_post", side_effect=self.simulate) as post:
            result = self.run_enroll()
        self.assertEqual(result["central_origin"], self.central)
        self.assertEqual(post.call_count, 2)
        self.assertTrue((self.peer_root / "server-peer.json").exists())
        self.assertTrue((self.peer_root / "etc/frp/client-identity.key").exists())
        self.assertTrue((self.peer_root / "etc/frp/client-identity.mac").exists())
        self.assertFalse((self.peer_root / "enroll-pending.json").exists())
        self.assertEqual((self.peer_root / "server-peer.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.peer_root / "etc/frp/client-identity.key").stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(peer.ServerPeerDenied, "already enrolled"):
            self.run_enroll()

    def test_crash_replay_preserves_machine_id_and_operation_id(self):
        payloads = []
        def incomplete(url, req, id, secret):
            if url.endswith("/enroll/preflight"):
                return {"valid": True}
            payloads.append(req)
            raise peer.ServerPeerDenied("lost network response")
        with patch.object(enrollment, "_post", side_effect=incomplete):
            with self.assertRaisesRegex(peer.ServerPeerDenied, "lost network response"):
                self.run_enroll()
        key = self.peer_root / "etc/frp/client-identity.key"
        before_key = key.read_bytes()
        with patch.object(enrollment, "_post", side_effect=self.simulate) as r:
            self.run_enroll()
        # Crash recovery must bypass a now-consumed /enroll/preflight.
        self.assertEqual(r.call_count, 1)
        self.assertTrue(r.call_args_list[0].args[0].endswith("/enroll"))
        actual = r.call_args_list[0].args[1]
        self.assertEqual(payloads[0]["machine_id"], actual["machine_id"])
        self.assertEqual(payloads[0]["operation_id"], actual["operation_id"])
        self.assertEqual(before_key, key.read_bytes())

    def test_missing_or_open_code_file_fails_before_network(self):
        self.codefile.chmod(0o644)
        with patch.object(enrollment, "_post") as post:
            with self.assertRaisesRegex(peer.ServerPeerDenied, "private"):
                self.run_enroll()
            post.assert_not_called()
        self.codefile.chmod(0o600)
        self.codefile.write_text("not-a-code")
        with self.assertRaisesRegex(peer.ServerPeerDenied, "manual Enrollment Code"):
            self.run_enroll()

    def test_insecure_or_mismatched_central_fails(self):
        with patch.object(enrollment, "_post") as post:
            with self.assertRaisesRegex(peer.ServerPeerDenied, "HTTPS"):
                enrollment.enroll(root=str(self.peer_root), central="http://remote.xdr.ooo",
                                  code_file=str(self.codefile), label=self.label)
            post.assert_not_called()
        with patch.object(enrollment, "_post", side_effect=peer.ServerPeerDenied("lost network response")):
            with self.assertRaises(peer.ServerPeerDenied):
                self.run_enroll()
        with patch.object(enrollment, "_post") as post:
            with self.assertRaisesRegex(peer.ServerPeerDenied, "different enrollment transaction"):
                enrollment.enroll(root=str(self.peer_root),
                                  central="https://different.xdr.ooo",
                                  code_file=str(self.codefile), label=self.label)
            post.assert_not_called()

    def test_replay_after_local_mac_write_crash_preserves_original_identity(self):
        real_writer = enrollment._atomic_json
        def fail_once_on_state(path, data):
            if path.name == "client-state.json":
                raise OSError("simulated crash after MAC persisted")
            return real_writer(path, data)
        with patch.object(enrollment, "_post", side_effect=self.simulate):
            with patch.object(enrollment, "_atomic_json", side_effect=fail_once_on_state):
                with self.assertRaisesRegex(OSError, "simulated crash"):
                    self.run_enroll()
        mac = (self.peer_root / "etc/frp/client-identity.mac").read_bytes()
        with patch.object(enrollment, "_post", side_effect=self.simulate) as remote:
            self.run_enroll()
            self.assertEqual(remote.call_count, 1)
        self.assertEqual((self.peer_root / "etc/frp/client-identity.mac").read_bytes(), mac)
        self.assertFalse((self.peer_root / "enroll-pending.json").exists())

    def test_invalid_hmac_never_marks_client_enrolled(self):
        with patch.object(enrollment, "_post",
                          side_effect=lambda url, body, id, secret:
                          {"valid": True} if url.endswith("preflight") else
                          {"services": [], "mgmt_status": "enrolled",
                           "token_ciphertext": "x", "response_hmac": "bad"}):
            with self.assertRaisesRegex(peer.ServerPeerDenied, "HMAC"):
                self.run_enroll()
        self.assertFalse((self.peer_root / "server-peer.json").exists())
        self.assertTrue((self.peer_root / "enroll-pending.json").exists())

    def test_rejects_nonempty_remote_services_even_with_valid_mac(self):
        def malicious(url, req, eid, secret):
            if url.endswith("preflight"):
                return {"valid": True}
            result = {"services": [{"id": "unexpected"}],
                      "mgmt_status": "enrolled", "token_ciphertext": "x"}
            result["response_hmac"] = MGMT.hmac_hex(secret, MGMT.canonical_json(result))
            return result
        with patch.object(enrollment, "_post", side_effect=malicious):
            with self.assertRaisesRegex(peer.ServerPeerDenied, "management-only"):
                self.run_enroll()

    def test_single_code_not_reused_on_new_identity(self):
        with patch.object(enrollment, "_post", side_effect=self.simulate):
            self.run_enroll()
        with patch.object(enrollment, "_post") as post:
            with self.assertRaises(peer.ServerPeerDenied):
                self.run_enroll()
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
