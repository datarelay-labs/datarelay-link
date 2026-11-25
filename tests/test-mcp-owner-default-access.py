#!/usr/bin/env python3
"""Verified OAuth identities remain denied until a separate access rule is applied."""
from __future__ import annotations
import base64
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_plane import ControlPlane
import drlink_v24 as v24
import drlink_runtime_policy as rp

REDIRECT = "http://127.0.0.1/callback"
RESOURCE = "https://mcp.example.test/mcp"
ALL_CAPABILITIES = (
    ("list_hosts", None), ("get_host", None), ("get_system_info", None),
    ("list_processes", None), ("exec", "id -un"), ("read_file", "/tmp/foo"),
    ("write_file", "/tmp/foo"), ("delete_file", "/tmp/foo"),
    ("upload_file", "/tmp/foo"), ("download_file", "/tmp/foo"),
)


class OAuthAuthenticationSeparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-mcp-owner-")
        self.addCleanup(self.tmp.cleanup)
        self.previous = {key: os.environ.get(key) for key in (
            "DRLINK_SKIP_ACTIVATION", "DRLINK_CONFIRM", "DRLINK_TEST_ROOT",
            "FRP_DEPLOY_TEST_ROOT",
        )}
        self.addCleanup(self.restore_env)
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_CONFIRM"] = "yes"
        os.environ["DRLINK_TEST_ROOT"] = self.tmp.name
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp.name
        p = Path(self.tmp.name, "etc/drlink")
        p.mkdir(parents=True)
        (p / "config.json").write_text('{"role":"server"}\n')
        self.plane = ControlPlane(self.tmp.name)
        self.addCleanup(self.plane.close)
        v24.ensure_v2_schema(self.plane.conn)
        self.plane.upsert_client(
            "a" * 32, label="First Test Agent", hostname="agent-01",
            connected=True,
        )

    def restore_env(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_pending(self, label):
        reg = self.plane.register_oauth_client({
            "redirect_uris": [REDIRECT],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "client_name": label,
        })
        verifier = "X" * 43
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        pending = self.plane.create_oauth_pending(
            client_id=reg["client_id"], redirect_uri=REDIRECT,
            code_challenge=challenge, resource=RESOURCE, state=label,
        )
        return reg["client_id"], verifier, pending["id"]

    def approve_and_exchange(self, identity, label):
        client_id, verifier, pending_id = self.make_pending(label)
        self.assertIsNone(self.plane.conn.execute(
            "SELECT value FROM system_meta WHERE key=?",
            (v24.MCP_OWNER_PRINCIPAL_META,),
        ).fetchone())
        approval = self.plane.approve_oauth_pending(
            pending_id, identity, retain_for_browser=True
        )
        self.assertEqual(
            self.plane.get_principal(identity)["credential_status"], "pending")
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT COUNT(*) FROM ai_policy_rules"
            ).fetchone()[0], 0,
        )
        continuation = self.plane.complete_oauth_pending_browser(
            approval["completion_token"]
        )
        self.assertIsNone(self.plane.exchange_authorization_code(
            code=continuation["code"], verifier="wrong",
            redirect_uri=REDIRECT, resource=RESOURCE, client_id=client_id,
        ))
        self.assertIsNone(self.plane.conn.execute(
            "SELECT value FROM system_meta WHERE key=?",
            (v24.MCP_OWNER_PRINCIPAL_META,),
        ).fetchone())
        issued = self.plane.exchange_authorization_code(
            code=continuation["code"], verifier=verifier,
            redirect_uri=REDIRECT, resource=RESOURCE, client_id=client_id,
        )
        self.assertTrue(issued and issued["access_token"].startswith("drauth_"))
        self.assertEqual(
            self.plane.get_principal(identity)["credential_status"], "verified")
        return issued

    def check_caps(self, identity, host, expectation):
        for cap, operand in ALL_CAPABILITIES:
            with self.subTest(identity=identity, host=host, capability=cap):
                decision = v24.authorize_ai_capability_v24(
                    self.plane, identity=identity, destination=host,
                    capability=cap, operand=operand,
                )
                self.assertEqual(decision["action"], expectation, decision)

    def assert_no_implicit_policy(self):
        self.assertIsNone(v24.get_access_policy(self.plane, "ai")["mode"])
        self.assertEqual(self.plane.conn.execute("SELECT COUNT(*) FROM ai_policy_rules").fetchone()[0], 0)
        self.assertIsNone(self.plane.conn.execute(
            "SELECT value FROM system_meta WHERE key=?", (v24.MCP_OWNER_PRINCIPAL_META,)
        ).fetchone())

    def test_first_and_second_verified_identity_are_denied_without_rule(self):
        self.approve_and_exchange("chatgpt", "first")
        self.assert_no_implicit_policy()
        self.check_caps("chatgpt", "First Test Agent", "DENY")
        self.approve_and_exchange("claude", "second")
        self.assert_no_implicit_policy()
        self.check_caps("claude", "First Test Agent", "DENY")

    def test_new_enrollment_does_not_implicitly_authorize_verified_identity(self):
        self.approve_and_exchange("chatgpt", "first")
        rp.sync_enrolled_client(self.plane, client_id="b" * 32, hostname="agent-02",
                                label="Second Test Agent", services={})
        self.assert_no_implicit_policy()
        self.check_caps("chatgpt", "Second Test Agent", "DENY")

    def test_explicit_rule_and_existing_dynamic_group_are_preserved(self):
        self.approve_and_exchange("chatgpt", "first")
        v24.set_permission_object(self.plane, v24.MCP_OWNER_PERMISSION,
                                  permissions=list(v24.PERMISSIONS), oneshot=True)
        # Recreate the persisted pre-upgrade owner state in this disposable
        # fixture; production OAuth no longer creates any of these resources.
        host = self.plane.conn.execute(
            "SELECT o.name FROM objects o JOIN managed_endpoints e ON e.object_id=o.id WHERE e.client_id=?",
            ("a" * 32,),
        ).fetchone()["name"]
        v24.set_network_group(self.plane, v24.MCP_OWNER_HOST_GROUP, members=[host], oneshot=True)
        v24.set_ai_access_rule(self.plane, v24.MCP_OWNER_RULE, mode="whitelist",
                               source="chatgpt", destination=v24.MCP_OWNER_HOST_GROUP,
                               permission=v24.MCP_OWNER_PERMISSION, paths=["/*"], enabled=True, oneshot=True)
        self.plane.conn.execute("INSERT INTO system_meta(key,value) VALUES(?,?)",
                                (v24.MCP_OWNER_PRINCIPAL_META, self.plane.get_principal("chatgpt")["id"]))
        self.check_caps("chatgpt", "First Test Agent", "ALLOW")
        rp.sync_enrolled_client(self.plane, client_id="b" * 32, hostname="agent-02",
                                label="Second Test Agent", services={})
        self.check_caps("chatgpt", "Second Test Agent", "ALLOW")
        self.assertEqual(self.plane.conn.execute("SELECT COUNT(*) FROM ai_policy_rules").fetchone()[0], 1)
        self.plane.conn.execute("UPDATE ai_principals SET credential_status='revoked' WHERE name='chatgpt'")
        self.check_caps("chatgpt", "Second Test Agent", "DENY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
