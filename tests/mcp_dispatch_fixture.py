"""Shared fixture for MCP Bridge endpoint-dispatch tests (AUD-21 D4, D6).

One Control DB, one AI principal allowed to `exec` on one Managed Host, a real
Bridge (`MCPBridge`) and a fake Agent thread that claims and completes jobs on
its OWN ControlPlane connection, the way the allocator does in production. The
fixture never relaxes authorization: only AI-executor freshness (an Agent
heartbeat clock) is patched, because no real Agent runs here.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane  # noqa: E402
from drlink_mcp_bridge import MCPBridge  # noqa: E402
import drlink_v24 as v24  # noqa: E402

MACHINE = "dddddddddddddddddddddddddddddddd"
HOST = "agent-d"


class DispatchFixture(unittest.TestCase):
    """Bridge + one Managed Host + a fake Agent that completes every job."""

    agent_delay = 0.0

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-mcp-dispatch-")
        self._env = mock.patch.dict(os.environ, {"DRLINK_CONFIRM": "yes"})
        self._env.start()
        for key in ("DRLINK_TEST_ROOT", "DRLINK_AI_TEST_LOCAL_EXEC",
                    "DRLINK_AI_TEST_LOCAL_AGENTS", "DRLINK_AI_LOCAL_EXEC"):
            os.environ.pop(key, None)
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        self.plane.upsert_client(MACHINE, label=HOST, hostname=HOST)
        self.plane.set_ai_principal("ops", enabled=True)
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status = 'active', enabled = 1 WHERE name = 'ops'"
        )
        self.plane.commit_if_autonomous()
        self.principal = self.plane.get_principal("ops")
        v24.set_permission_object(self.plane, "run", permissions=["command-exec"], oneshot=True)
        v24.set_ai_access_rule(self.plane, "ops-run", mode="whitelist", source="ops",
                               destination=HOST, permission="run", enabled=True, oneshot=True)
        self.bridge = MCPBridge(root=self.tmp, plane=self.plane, auto_agents=False)
        self._ready = mock.patch.object(ControlPlane, "client_effectively_connected",
                                        return_value=True)
        self._ready.start()
        self.completed = []
        self._stop = threading.Event()
        self._agent = threading.Thread(target=self._agent_loop, daemon=True)
        self._agent.start()

    def tearDown(self):
        self._stop.set()
        self._agent.join(timeout=5)
        self._ready.stop()
        self.bridge.close()
        self.plane.close()
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _agent_loop(self):
        agent_plane = ControlPlane(self.tmp)
        try:
            while not self._stop.is_set():
                for job in agent_plane.claim_ai_jobs(MACHINE, limit=4):
                    if self.agent_delay:
                        time.sleep(self.agent_delay)
                    agent_plane.complete_ai_job(
                        job["id"], MACHINE, {"result": "ALLOW", "exit_code": 0, "stdout": "ok\n"},
                        claim_token=job["claim_token"], attempt_id=job["attempt_id"],
                    )
                    self.completed.append(job["id"])
                time.sleep(0.01)
        finally:
            agent_plane.close()

    def rpc_exec(self, command="echo ok"):
        body = {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                "params": {"name": "exec", "arguments": {"endpoint": HOST, "command": command}}}
        return self.bridge.handle_rpc(body, {}, self.principal)

    def activity(self):
        rows = self.plane.conn.execute(
            "SELECT * FROM ai_activity WHERE capability = 'exec' ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def jobs(self):
        return [dict(row) for row in self.plane.conn.execute("SELECT * FROM ai_jobs ORDER BY created_at")]
