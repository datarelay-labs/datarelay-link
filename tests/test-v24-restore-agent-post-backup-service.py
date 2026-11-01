#!/usr/bin/env python3
"""F-018: an Agent-owned Remote Service created after a Server backup survives a Server restore.

Disposable fixture only (in-process Server/Agent control planes and the real
loopback management server); no installed Server is touched. The Server DB is
restored to its pre-service backup and the real ``post_restore_reconcile``
fail-closed projection runs. One signed lifecycle reconciliation must then
re-publish the Agent-owned service on the Server at the Agent's endpoint and
leave Agent and Server reporting the same status for every service.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_upgrade_reconcile as reconcile
import drlink_v24 as v24

_spec = importlib.util.spec_from_file_location(
    "rs_atomicity_harness", ROOT / "tests" / "test-v24-remote-service-distributed-atomicity.py")
_harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_harness)
_loader = importlib.machinery.SourceFileLoader("frp_restore_f018", str(ROOT / "tools" / "frp-restore"))
restore = importlib.util.module_from_spec(importlib.util.spec_from_loader("frp_restore_f018", _loader))
_loader.exec_module(restore)


class RestoreAgentPostBackupService(unittest.TestCase):
    # Reuse the disposable Server/Agent fixture without inheriting its tests.
    tearDown = _harness.RemoteServiceDistributedAtomicity.tearDown

    def setUp(self):
        _harness.RemoteServiceDistributedAtomicity.setUp(self)
        # Destination reachability is host-dependent; this test is about
        # Agent/Server state reconciliation, not target listeners.
        patcher = mock.patch.object(v24, "_probe_tcp", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _create(self, name, service):
        v24.set_remote_service_agent(self.agent, name, destination="this-host", service=service,
                                     enabled=True, oneshot=True, root=self.agent_tmp,
                                     server_reachable=True)

    def _agent(self):
        return {r["name"]: dict(r) for r in self.agent.conn.execute(
            "SELECT name, status, endpoint_port, runtime_verified FROM agent_remote_services "
            "WHERE delete_pending = 0")}

    def _server(self):
        return {r["name"]: dict(r) for r in self.server.conn.execute(
            "SELECT p.name, p.public_port, m.status, m.reason, m.runtime_verified "
            "FROM published_services p LEFT JOIN remote_service_meta m ON m.service_id = p.id "
            "WHERE p.released = 0")}

    def _restore_server(self, backup):
        previous = self.server.current_revision()
        backup.backup(self.server.conn)
        # The disposable fixture has no forensic management inventory; the
        # remaining restore projection (revision floor, fail-closed DEGRADED,
        # runtime compile) is the production code path.
        with mock.patch.object(reconcile, "project_client_inventory_from_control_plane"):
            restore.post_restore_reconcile(Path(self.server_tmp), previous_revision=previous)
        return previous

    def test_post_backup_agent_service_is_republished_after_server_restore(self):
        self._create("d2-pre", "ssh")
        backup = sqlite3.connect(":memory:")
        self.server.conn.commit()
        self.server.conn.backup(backup)
        self._create("d2-post", "https")
        before = self._agent()
        self.assertEqual(before["d2-post"]["status"], "HEALTHY")
        post_port = before["d2-post"]["endpoint_port"]

        previous = self._restore_server(backup)
        restored = self._server()
        self.assertNotIn("d2-post", restored)
        self.assertEqual(restored["d2-pre"]["status"], "DEGRADED")
        self.assertIn("after restore", restored["d2-pre"]["reason"])
        self.assertGreater(self.server.current_revision(), previous)

        # Lifecycle worker path when the Server requests reconciliation.
        result = v24.synchronize_agent_remote_services(
            self.agent, root=self.agent_tmp, server_verification_only=True)
        self.assertEqual(result.get("status"), "SYNCHRONIZED", result)

        agent, server = self._agent(), self._server()
        self.assertEqual(set(agent), {"d2-pre", "d2-post"})
        self.assertEqual(set(server), set(agent))
        self.assertEqual(server["d2-post"]["public_port"], post_port, "endpoint must not move")
        for name, row in agent.items():
            self.assertEqual(server[name]["public_port"], row["endpoint_port"], name)
            self.assertEqual(server[name]["status"], row["status"], name)
            self.assertEqual(row["status"], "HEALTHY", name)
            self.assertEqual(int(server[name]["runtime_verified"] or 0), 1, name)

        again = v24.synchronize_agent_remote_services(
            self.agent, root=self.agent_tmp, server_verification_only=True)
        self.assertEqual(again.get("status"), "SYNCHRONIZED", again)
        self.assertEqual((self._agent(), self._server()), (agent, server))


if __name__ == "__main__":
    unittest.main()
