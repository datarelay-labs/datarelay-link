#!/usr/bin/env python3
"""F-006 regression: an unreferenced AI Identity must be removable.

An AI Identity configured for OAuth owns an ai_oauth_clients row (and possibly
codes/tokens/pending requests). Those credential rows belong to the identity
and must be removed with it; otherwise `unset ai-identity` fails with the
misleading "referenced dependency still exists" error although no Rule or
Group references the identity.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane, ControlPlaneError


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class AiIdentityUnsetCredentialCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-ai-unset-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def _count(self, table: str, pid: str) -> int:
        return self.plane.conn.execute(
            "SELECT COUNT(*) FROM %s WHERE principal_id = ?" % table, (pid,)
        ).fetchone()[0]

    def test_unset_identity_with_oauth_client_succeeds(self):
        self.plane.set_ai_principal("bot", enabled=False)
        self.plane.configure_ai_auth("bot", "oauth")
        pid = self.plane.get_principal("bot")["id"]
        self.assertEqual(self._count("ai_oauth_clients", pid), 1)

        self.plane.unset_ai_principal("bot", confirm=True)

        self.assertIsNone(self.plane.get_principal("bot"))
        self.assertEqual(self._count("ai_oauth_clients", pid), 0)

    def test_unset_identity_without_oauth_still_succeeds(self):
        self.plane.set_ai_principal("plain", enabled=False)
        self.plane.unset_ai_principal("plain", confirm=True)
        self.assertIsNone(self.plane.get_principal("plain"))


if __name__ == "__main__":
    unittest.main()
