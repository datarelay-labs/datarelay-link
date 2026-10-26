#!/usr/bin/env python3
"""DRLink v2.4 Server-self MCP discovery and AI Access isolation regressions."""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_cli import dispatch
from drlink_control_plane import ControlPlane
from drlink_mcp_bridge import MCPBridge, TOOL_DEFS
import drlink_v24 as v24


class ServerSelfMCPTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="drlink-mcp-server-self-")
        self.env = patch.dict(os.environ, {"DRLINK_TEST_ROOT": self.root, "DRLINK_CONFIRM": "yes"})
        self.env.start()
        self.plane = ControlPlane(self.root)
        self.bridge = MCPBridge(root=self.root, plane=self.plane)
        self.principal = {"name": "mcp-self-test", "id": "test-ai"}
        self.plane.set_ai_principal(self.principal["name"], enabled=True)

    def tearDown(self):
        self.plane.close()
        self.env.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def cli(self, *args):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = dispatch(list(args), root=self.root)
        self.assertEqual(code, 0, buf.getvalue() + err.getvalue())
        return buf.getvalue()

    def authorize_host_info(self):
        self.cli("system", "credential", "rotate", "ai-identity", self.principal["name"])
        self.cli("set", "permission-object", "server-host-info", "permissions", "host-info")
        self.cli("set", "ai-access", "self-read-only",
                 "mode", "whitelist", "source", self.principal["name"],
                 "destination", "server:self", "permission", "server-host-info", "enabled")

    def test_native_public_https_identity_is_separate_from_frp_direct_mode(self):
        from drlink_control_db import ControlPlaneError
        self.assertNotIn("https://native.xdr.ooo/mcp", self.bridge.canonical_resource())
        self.assertEqual(self.plane.mcp_public_url(), "Not configured")
        with patch.dict(os.environ, {
            "DRLINK_MCP_NATIVE_PUBLIC_URL": "https://native.xdr.ooo/mcp",
            "DRLINK_MCP_SERVER_SELF_ENABLED": "0",
        }):
            self.assertNotEqual(self.bridge.canonical_resource(),
                                "https://native.xdr.ooo/mcp")
        with patch.dict(os.environ, {
            "DRLINK_MCP_NATIVE_PUBLIC_URL": "https://NATIVE.XDR.OOO/mcp",
            "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
        }):
            self.assertEqual(self.bridge.canonical_resource(),
                             "https://native.xdr.ooo/mcp")
            self.assertEqual(self.bridge.canonical_public_base(),
                             "https://native.xdr.ooo")
            self.assertEqual(self.bridge.oauth_metadata()["resource"],
                             "https://native.xdr.ooo/mcp")
            self.assertEqual(self.bridge.as_metadata()["issuer"],
                             "https://native.xdr.ooo")
            self.assertEqual(self.bridge.as_metadata()["authorization_endpoint"],
                             "https://native.xdr.ooo/oauth/authorize")
            self.assertIn("https://native.xdr.ooo/.well-known/oauth-protected-resource",
                          self.bridge.www_authenticate_value())
            self.assertEqual(self.plane.mcp_public_url(), "Not configured")
        with patch.dict(os.environ, {
            "DRLINK_MCP_NATIVE_PUBLIC_URL": "https://mcp.link.xdr.ooo/mcp",
            "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
        }):
            self.assertEqual(self.bridge.canonical_resource(),
                             "https://mcp.link.xdr.ooo/mcp")
            self.assertEqual(self.bridge.canonical_public_base(),
                             "https://mcp.link.xdr.ooo")
            self.assertEqual(self.bridge.oauth_metadata()["resource"],
                             "https://mcp.link.xdr.ooo/mcp")
            self.assertEqual(self.bridge.as_metadata()["issuer"],
                             "https://mcp.link.xdr.ooo")
            self.assertEqual(self.bridge.as_metadata()["authorization_endpoint"],
                             "https://mcp.link.xdr.ooo/oauth/authorize")
            self.assertIn("https://mcp.link.xdr.ooo/.well-known/oauth-protected-resource",
                          self.bridge.www_authenticate_value())
        for bad_url in (
            "http://native.xdr.ooo/mcp",
            "https://native.xdr.ooo/",
            "https://native.xdr.ooo/mcp?override=1",
            "https://native.xdr.ooo/mcp#private",
            "https://root:pass@native.xdr.ooo/mcp",
            "https://127.0.0.1/mcp",
            "https://localhost/mcp",
            "https://native.xdr.ooo:abc/mcp",
            "https://evil.example/mcp/../mcp",
        ):
            with patch.dict(os.environ, {
                "DRLINK_MCP_NATIVE_PUBLIC_URL": bad_url,
                "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
            }):
                with self.assertRaises(ControlPlaneError, msg=bad_url):
                    self.bridge.canonical_resource()

    def test_self_is_not_a_managed_host_or_network_object(self):
        self.assertIsNone(self.plane.get_object(v24.SERVER_SELF_TARGET))
        self.assertFalse(any(x["name"] == v24.SERVER_SELF_TARGET for x in self.plane.list_objects()))
        self.assertEqual(v24.SERVER_SELF_TARGET, "server:self")
        self.assertTrue(any(entry[0] == "get_server" and entry[4]["readOnlyHint"] for entry in TOOL_DEFS))

    def test_default_denies_without_server_flag_or_explicit_policy(self):
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_SELF_ENABLED": "1"}):
            denied = self.bridge.call_tool(self.principal, "get_server", {})
            self.assertTrue(denied.get("isError"), denied)
            denied = self.bridge.call_tool(self.principal, "get_system_info", {"endpoint": "server:self"})
            self.assertTrue(denied.get("isError"), denied)
        self.authorize_host_info()
        self.assertEqual(
            v24.authorize_ai_capability_v24(self.plane, identity=self.principal["name"],
                                           destination="server:self", capability="get_system_info")["action"],
            "ALLOW",
        )
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_SELF_ENABLED": "0"}):
            self.assertTrue(self.bridge.call_tool(self.principal, "get_server", {}).get("isError"))

    def test_authorized_self_read_only_and_isolated_from_agents(self):
        self.authorize_host_info()
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_SELF_ENABLED": "1"}):
            result = self.bridge.call_tool(self.principal, "get_server", {})
            self.assertFalse(result.get("isError"), result)
            info = result["structuredContent"]
            self.assertEqual(info["target"], "server:self")
            self.assertEqual(info["type"], "server")
            self.assertNotIn("client_id", info)
            uname = self.bridge.call_tool(self.principal, "get_system_info", {"endpoint": "server:self"})
            self.assertEqual(uname["structuredContent"]["nodename"], os.uname().nodename)
            for name, args in (
                ("exec", {"endpoint": "server:self", "command": "id"}),
                ("write_file", {"endpoint": "server:self", "path": "/tmp/denied", "content": "x"}),
                ("read_file", {"endpoint": "server:self", "path": "/etc/passwd"}),
                ("get_system_info", {"endpoint": "server:self-other"}),
            ):
                self.assertTrue(self.bridge.call_tool(self.principal, name, args).get("isError"),
                                (name, args))
            hosts = self.bridge.call_tool(self.principal, "list_hosts", {})
            self.assertFalse(any(x.get("name") == "server:self"
                                 for x in hosts["structuredContent"]["hosts"]))
            test_decision = self.cli("test", "ai-access", "source", self.principal["name"],
                                     "destination", "server:self", "permission", "host-info")
            self.assertIn("ALLOW", test_decision)
            self.assertIn("self-read-only", test_decision)

    def test_local_executor_requires_independent_flag_scope_and_policy(self):
        self.cli("system", "credential", "rotate", "ai-identity", self.principal["name"])
        self.cli("set", "permission-object", "server-dev-perms", "permissions",
                 "file-read,file-write,command-exec")
        self.cli("set", "ai-access", "self-dev-policy", "mode", "whitelist",
                 "source", self.principal["name"], "destination", "server:self",
                 "permission", "server-dev-perms", "enabled")
        v24.set_ai_policy_path_scopes(self.plane, "self-dev-policy", [self.root + "/**"])
        test_file = self.root + "/testfile.txt"
        with patch("drlink_mcp_bridge.execute_as_unprivileged_user",
                   return_value={"path": test_file, "bytes": 1}) as worker:
            with patch.dict(os.environ, {"DRLINK_MCP_SERVER_SELF_ENABLED": "1",
                                         "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "0"}):
                self.assertTrue(self.bridge.call_tool(
                    self.principal, "server_read_file", {"path": test_file}).get("isError"))
                worker.assert_not_called()
            with patch.dict(os.environ, {"DRLINK_MCP_SERVER_SELF_ENABLED": "1",
                                         "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1"}):
                self.assertTrue(self.bridge.call_tool(
                    self.principal, "server_read_file", {"path": "/etc/shadow"}).get("isError"))
                worker.assert_not_called()
                self.assertFalse(self.bridge.call_tool(
                    self.principal, "server_read_file", {"path": test_file}).get("isError"))
                worker.assert_called_once_with({"action": "read_file", "path": test_file})
                worker.reset_mock()
                self.assertFalse(self.bridge.call_tool(
                    self.principal, "server_git",
                    {"cwd": self.root, "argv": ["git", "status", "--short"]}).get("isError"))
                worker.assert_called_once_with(
                    {"action": "run_git", "cwd": self.root, "argv": ["git", "status", "--short"]})
                worker.reset_mock()
                v24.set_ai_policy_path_scopes(self.plane, "self-dev-policy", [])
                self.assertTrue(self.bridge.call_tool(
                    self.principal, "server_git",
                    {"cwd": self.root, "argv": ["git", "status", "--short"]}).get("isError"))
                worker.assert_not_called()
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_SELF_ENABLED": "1",
                                     "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1"}):
            with patch("drlink_mcp_bridge.execute_as_unprivileged_user") as worker:
                self.assertTrue(self.bridge.call_tool(
                    self.principal, "exec", {"endpoint": "server:self", "command": "id"}
                ).get("isError"))
                worker.assert_not_called()

    def test_scoped_server_run_requires_exec_permission_and_local_flags(self):
        self.assertTrue(any(tool[0] == "server_run" and tool[4]["destructiveHint"]
                            for tool in TOOL_DEFS))
        self.cli("system", "credential", "rotate", "ai-identity", self.principal["name"])
        self.cli("set", "permission-object", "server-test-command", "permissions", "command-exec")
        self.cli("set", "ai-access", "server-test-runner", "mode", "whitelist",
                 "source", self.principal["name"], "destination", "server:self",
                 "permission", "server-test-command", "enabled")
        v24.set_ai_policy_path_scopes(self.plane, "server-test-runner", [self.root + "/**"])
        args = {"cwd": self.root, "argv": ["python3", "tests/test-example.py"]}
        with patch("drlink_mcp_bridge.execute_as_unprivileged_user",
                   return_value={"exit_status": 0, "stdout": "ok"}) as worker:
            with patch.dict(os.environ, {
                "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
                "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "0",
            }):
                self.assertTrue(self.bridge.call_tool(
                    self.principal, "server_run", args).get("isError"))
                worker.assert_not_called()
            with patch.dict(os.environ, {
                "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
                "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1",
            }):
                result = self.bridge.call_tool(self.principal, "server_run", args)
                self.assertFalse(result.get("isError"), result)
                worker.assert_called_once_with({
                    "action": "run_dev_test", "cwd": self.root,
                    "argv": ["python3", "tests/test-example.py"],
                })
                worker.reset_mock()
                result = self.bridge.call_tool(
                    self.principal, "server_run",
                    {"cwd": "/tmp/outside-worktree", "argv": args["argv"]})
                self.assertTrue(result.get("isError"), result)
                worker.assert_not_called()
                v24.set_ai_policy_path_scopes(self.plane, "server-test-runner", [])
                self.assertTrue(self.bridge.call_tool(
                    self.principal, "server_run", args).get("isError"))
                worker.assert_not_called()

    def test_legacy_network_object_cannot_authorize_server_self(self):
        # An imported/legacy object using a reserved Server selector must
        # never confer server-local privileges through name matching.
        self.plane.set_object_type("old-server-alias", "host")
        self.cli("system", "credential", "rotate", "ai-identity", self.principal["name"])
        self.cli("set", "permission-object", "old-host-info", "permissions", "host-info")
        self.cli("set", "ai-access", "old-object-rule",
                 "mode", "whitelist", "source", self.principal["name"],
                 "destination", "old-server-alias", "permission", "old-host-info", "enabled")
        self.plane.conn.execute("UPDATE objects SET name = ? WHERE name = ?",
                                ("server:self", "old-server-alias"))
        self.plane.conn.commit()
        actual = v24.authorize_ai_capability_v24(
            self.plane, identity=self.principal["name"],
            destination="server:self", capability="get_system_info")
        self.assertEqual(actual["action"], "DENY")
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_SELF_ENABLED": "1"}):
            self.assertTrue(self.bridge.call_tool(self.principal, "get_server", {}).get("isError"))

    def test_server_self_persists_as_distinct_policy_ref(self):
        self.authorize_host_info()
        row = self.plane.conn.execute(
            "SELECT destination_ref_kind, destination_ref_id FROM ai_policy_rules WHERE name = ?",
            ("self-read-only",),
        ).fetchone()
        self.assertEqual((row["destination_ref_kind"], row["destination_ref_id"]), ("server", "local"))
        allowed = v24.evaluate_ai_access_v24(
            self.plane, identity=self.principal["name"], destination="server:self", permission="host-info"
        )
        other = v24.evaluate_ai_access_v24(
            self.plane, identity=self.principal["name"], destination="server:self.other", permission="host-info"
        )
        self.assertEqual(allowed["result"], "ALLOW")
        self.assertEqual(other["result"], "DENY")
        self.assertEqual(
            v24._semantic_network_ref(self.plane.conn, row["destination_ref_kind"], row["destination_ref_id"]),
            "server:self",
        )
        rendered = self.cli("show", "ai-access", "self-read-only")
        self.assertIn("server:self", rendered)


if __name__ == "__main__":
    unittest.main()
