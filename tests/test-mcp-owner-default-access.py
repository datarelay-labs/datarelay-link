#!/usr/bin/env python3
"""First operator-approved OAuth owner gets all MCP capabilities; others stay deny-by-default."""
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


class FirstOwnerMcpDefaults(unittest.TestCase):
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

    def test_operator_approved_first_mcp_owner_receives_all_seven_rights(self):
        self.approve_and_exchange("chatgpt", "owner")
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT value FROM system_meta WHERE key=?",
                (v24.MCP_OWNER_PRINCIPAL_META,),
            ).fetchone()["value"],
            self.plane.get_principal("chatgpt")["id"],
        )
        self.assertEqual(
            self.plane.conn.execute("SELECT mode FROM access_policies WHERE plane='ai'"
                                    ).fetchone()["mode"], "whitelist"
        )
        self.check_caps("chatgpt", "First Test Agent", "ALLOW")
        self.plane.set_ai_principal("other-oauth-client", enabled=True)
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status='verified',auth_mode='oauth' "
            "WHERE name='other-oauth-client'"
        )
        self.check_caps("other-oauth-client", "First Test Agent", "DENY")

    def test_enrolling_another_authenticated_agent_extends_only_owner(self):
        self.approve_and_exchange("chatgpt", "owner-later-host")
        rp.sync_enrolled_client(
            self.plane, client_id="b" * 32, hostname="agent-02",
            label="Second Test Agent", services={},
        )
        self.check_caps("chatgpt", "Second Test Agent", "ALLOW")
        self.plane.set_ai_principal("other", enabled=True)
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status='verified',auth_mode='oauth' "
            "WHERE name='other'"
        )
        self.check_caps("other", "Second Test Agent", "DENY")
        # Repeat enrollment does not mint a second rule or duplicate membership.
        rp.sync_enrolled_client(
            self.plane, client_id="b" * 32, hostname="agent-02",
            label="Second Test Agent", services={},
        )
        self.assertEqual(
            self.plane.conn.execute("SELECT COUNT(*) FROM ai_policy_rules"
                                    ).fetchone()[0], 1
        )
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT COUNT(*) FROM object_group_members"
            ).fetchone()[0], 2
        )
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status='revoked' WHERE name='chatgpt'"
        )
        self.check_caps("chatgpt", "Second Test Agent", "DENY")

    def test_owner_profile_does_not_rewrite_existing_operator_resource(self):
        self.plane.set_ai_principal("owner", enabled=True)
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status='verified', auth_mode='oauth' "
            "WHERE name='owner'"
        )
        # An explicitly user-configured reserved name must never be overwritten.
        v24.set_permission_object(
            self.plane, v24.MCP_OWNER_PERMISSION,
            permissions=["host-info"], oneshot=True,
        )
        with self.assertRaisesRegex(Exception, "conflicts"):
            v24.ensure_operator_approved_mcp_owner_access(
                self.plane, self.plane.get_principal("owner")["id"]
            )
        self.assertEqual(
            self.plane.conn.execute(
                "SELECT COUNT(*) FROM ai_policy_rules"
            ).fetchone()[0], 0
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
