#!/usr/bin/env python3
"""Agentless Server Peer enrollment-state and signed-management-queue tests."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_server_peer as peer
import frp_mgmt_auth as mgmt_crypto


class PeerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-server-peer-")
        self.base = Path(self.tmp.name)
        self.base.chmod(0o700)
        self.frp = self.base / "etc/frp"
        self.frp.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.identity = "peer-8d57d3e9a4e64c07b84e535f4e2fd0ac"
        self.server_url = "https://remote.xdr.ooo"
        self.write_json(self.base / "server-peer.json", {
            "role": "drlink-server-peer", "machine_id": self.identity,
            "central_origin": self.server_url,
        })
        self.write_json(self.frp / "client-state.json", {
            "machine_id": self.identity, "label": "dev-drlink Server Peer",
            "role": "drlink-server-peer",
        })
        self.write_json(self.frp / "server-endpoint.json", {"mgmt_url": self.server_url})
        (self.frp / "client-identity.mac").write_text("a" * 64)
        (self.frp / "client-identity.mac").chmod(0o600)
        mgmt_crypto.generate_keypair(
            self.frp / "client-identity.key",
            self.frp / "client-identity.pub",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def write_json(self, dest, value):
        dest.write_text(json.dumps(value), encoding="utf-8")
        dest.chmod(0o600)

    def test_separate_server_peer_identity_is_verified(self):
        info = peer.validate_peer_root(str(self.base))
        self.assertEqual(info["machine_id"], self.identity)
        self.assertEqual(info["central_origin"], self.server_url)

    def test_role_and_endpoint_restrictions(self):
        with patch.object(peer, "_confined_regular_file", wraps=peer._confined_regular_file):
            role = self.base / "server-peer.json"
            self.write_json(role, {"role": "agent", "machine_id": self.identity,
                                   "central_origin": self.server_url})
            with self.assertRaisesRegex(peer.ServerPeerDenied, "role"):
                peer.validate_peer_root(str(self.base))
        self.write_json(role, {"role": "drlink-server-peer", "machine_id": self.identity,
                               "central_origin": self.server_url})
        with self.assertRaisesRegex(peer.ServerPeerDenied, "isolated"):
            peer.validate_peer_root("/")
        self.write_json(self.frp / "server-endpoint.json", {"mgmt_url": "http://remote.xdr.ooo"})
        with self.assertRaisesRegex(peer.ServerPeerDenied, "HTTPS"):
            peer.validate_peer_root(str(self.base))
        self.write_json(self.frp / "server-endpoint.json", {"mgmt_url": self.server_url})
        self.write_json(role, {"role": "drlink-server-peer", "machine_id": "different",
                               "central_origin": self.server_url})
        with self.assertRaisesRegex(peer.ServerPeerDenied, "bound"):
            peer.validate_peer_root(str(self.base))

    def test_world_readable_state_is_denied(self):
        marker = self.base / "server-peer.json"
        marker.chmod(0o644)
        with self.assertRaisesRegex(peer.ServerPeerDenied, "accessible"):
            peer.validate_peer_root(str(self.base))
        marker.chmod(0o600)
        self.base.chmod(0o755)
        with self.assertRaisesRegex(peer.ServerPeerDenied, "accessible"):
            peer.validate_peer_root(str(self.base))

    def test_existing_signed_management_auth_binds_server_peer_identity(self):
        body = b'{"limit":4}'
        url = self.server_url + "/v1/ai-jobs/claim"
        headers = peer.management._sign_request_headers(
            "POST", url, body, root=str(self.base)
        )
        self.assertEqual(headers["X-Machine-Id"], self.identity)
        message = mgmt_crypto.signed_message(
            self.identity, body, headers["X-Timestamp"], headers["X-Mgmt-Nonce"],
            op=mgmt_crypto.MGMT_OP_AI_JOB_CLAIM, method="POST",
            path="/v1/ai-jobs/claim",
        )
        pubkey = (self.frp / "client-identity.pub").read_text("utf-8")
        self.assertTrue(mgmt_crypto.verify_signature(
            pubkey, message, headers["X-Mgmt-Signature"]
        ))

    def test_peer_forbids_insecure_management_tls(self):
        for insecure in ("1", "yes", "TRUE"):
            with patch.dict(os.environ, {"DRLINK_MGMT_INSECURE": insecure}):
                with self.assertRaisesRegex(peer.ServerPeerDenied, "Insecure management TLS"):
                    peer.validate_peer_root(str(self.base))

    def test_default_closed_no_network_when_disabled(self):
        with patch.dict(os.environ, {"DRLINK_SERVER_PEER_ENABLED": "0"}):
            with patch.object(peer.management, "claim_ai_jobs_on_server") as claim:
                with self.assertRaisesRegex(peer.ServerPeerDenied, "disabled"):
                    peer.ServerPeerLoop(str(self.base)).run_once()
                claim.assert_not_called()

    def test_signed_claim_and_completion_use_isolated_identity(self):
        job = {
            "id": "job-q1", "claim_token": "atk-owned", "attempt_id": "att-owned",
            "capability": "get_system_info", "arguments": {}, "patterns": [],
        }
        with patch.dict(os.environ, {"DRLINK_SERVER_PEER_ENABLED": "1"}):
            with (
                patch.object(peer.management, "claim_ai_jobs_on_server",
                             return_value={"jobs": [job]}) as claim,
                patch.object(peer.management, "complete_ai_job_on_server",
                             return_value={"ok": True}) as complete,
            ):
                self.assertEqual(peer.ServerPeerLoop(str(self.base)).run_once(), 1)
                claim.assert_called_once_with(root=str(self.base), limit=4)
                kwargs = complete.call_args.kwargs
                self.assertEqual(kwargs["root"], str(self.base))
                self.assertEqual(kwargs["job_id"], "job-q1")
                self.assertEqual(kwargs["claim_token"], "atk-owned")
                self.assertEqual(kwargs["attempt_id"], "att-owned")
                self.assertEqual(kwargs["result"]["result"], "ALLOW")
                self.assertEqual(kwargs["result"]["nodename"], os.uname().nodename)

    def test_job_binding_missing_refuses_completion(self):
        bad = {"id": "job-q", "claim_token": "", "attempt_id": "att1",
               "capability": "get_system_info"}
        with patch.dict(os.environ, {"DRLINK_SERVER_PEER_ENABLED": "1"}):
            with (
                patch.object(peer.management, "claim_ai_jobs_on_server",
                             return_value={"jobs": [bad]}),
                patch.object(peer.management, "complete_ai_job_on_server") as complete,
            ):
                with self.assertRaisesRegex(peer.ServerPeerDenied, "binding"):
                    peer.ServerPeerLoop(str(self.base)).run_once()
                complete.assert_not_called()

    def test_server_role_denies_arbitrary_shell_even_if_central_requests_it(self):
        for capability in ("exec", "write_file", "delete_file", "list_processes", "upload_file"):
            out = peer.execute_peer_job({
                "capability": capability, "arguments": {"command": "sudo id"},
                "patterns": [str(self.base)+"/**"],
            })
            self.assertEqual(out["result"], "DENY", capability)

    def test_file_read_needs_central_path_and_local_opt_in(self):
        file = self.base / "test.log"
        file.write_text("public fixture")
        job = {"capability": "read_file", "arguments": {"path": str(file)},
               "patterns": [str(self.base) + "/**"]}
        with patch.object(peer, "execute_as_unprivileged_user",
                          return_value={"bytes": 14, "content_b64": "cHVibGljIGZpeHR1cmU="}) as worker:
            with patch.dict(os.environ, {"DRLINK_SERVER_PEER_READ_ENABLED": "0"}):
                self.assertEqual(peer.execute_peer_job(job)["result"], "DENY")
                worker.assert_not_called()
            with patch.dict(os.environ, {"DRLINK_SERVER_PEER_READ_ENABLED": "1"}):
                self.assertEqual(peer.execute_peer_job(job)["result"], "ALLOW")
                worker.assert_called_once_with({"action": "read_file", "path": str(file)})
                worker.reset_mock()
                self.assertEqual(peer.execute_peer_job({**job, "patterns": []})["result"], "DENY")
                worker.assert_not_called()
                self.assertEqual(peer.execute_peer_job({
                    **job, "arguments": {"path": "/etc/shadow"}
                })["result"], "DENY")
                worker.assert_not_called()

    def test_expired_job_fails_without_execution(self):
        result = peer.execute_peer_job({
            "capability": "get_system_info", "arguments": {},
            "deadline_at": "2001-01-01T00:00:00Z",
        })
        self.assertEqual(result["result"], "DENY")


if __name__ == "__main__":
    unittest.main()
