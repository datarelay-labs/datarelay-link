#!/usr/bin/env python3
"""A016-UNSET-AI-IDENTITY-FK regression.

`unset ai-identity <name>` must delete an AI Identity that owns OAuth client,
authorization code, pending authorization, token and session rows.  Those tables
reference ai_principals(id) with ON DELETE NO ACTION, so deleting only
ai_sessions used to raise `FOREIGN KEY constraint failed`, which the CLI then
reported as a misleading "referenced dependency still exists" message.

Audit rows (ai_activity) are retained with principal_id detached and the
principal_name kept so history stays attributable.  A still-referenced identity
(AI Access rule) must keep being rejected with nothing deleted.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24

NOW = "2026-11-03T00:00:00Z"
LATER = "2099-01-01T00:00:00Z"


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


def _verify(plane: ControlPlane, name: str) -> None:
    plane.conn.execute(
        "UPDATE ai_principals SET credential_status = 'verified', enabled = 1 WHERE name = ?",
        (name,),
    )
    plane.conn.commit()


def _seed_oauth_state(plane: ControlPlane, name: str, tag: str) -> str:
    """Create every kind of child row an authenticated OAuth AI Identity owns."""
    pid = plane.get_principal(name)["id"]
    c = plane.conn
    c.execute(
        "INSERT INTO ai_sessions(id, principal_id, credential_fingerprint, created_at) VALUES (?,?,?,?)",
        ("sess-" + tag, pid, "fp" + tag, NOW),
    )
    c.execute(
        "INSERT INTO ai_oauth_clients(client_id, principal_id, redirect_uris, scope, created_at) VALUES (?,?,?,?,?)",
        ("client-" + tag, pid, "https://example.invalid/cb", "drlink.ai offline_access", NOW),
    )
    c.execute(
        "INSERT INTO ai_oauth_codes(code_hash, principal_id, client_id, redirect_uri, code_challenge, "
        "expires_at, created_at) VALUES (?,?,?,?,?,?,?)",
        ("code-" + tag, pid, "client-" + tag, "https://example.invalid/cb", "chal", LATER, NOW),
    )
    c.execute(
        "INSERT INTO ai_oauth_tokens(token_hash, principal_id, client_id, expires_at, created_at) VALUES (?,?,?,?,?)",
        ("tok-" + tag, pid, "client-" + tag, LATER, NOW),
    )
    c.execute(
        "INSERT INTO ai_oauth_pending(id, principal_id, client_id, redirect_uri, code_challenge, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("pend-" + tag, pid, "client-" + tag, "https://example.invalid/cb", "chal", NOW),
    )
    c.execute(
        "INSERT INTO ai_activity(timestamp, principal_id, principal_name, capability, result) VALUES (?,?,?,?,?)",
        (NOW, pid, name, "command-exec", "ALLOW"),
    )
    c.commit()
    return pid


def _count(plane: ControlPlane, table: str, pid: str) -> int:
    return plane.conn.execute(
        "SELECT COUNT(*) FROM %s WHERE principal_id = ?" % table, (pid,)
    ).fetchone()[0]


CHILD_TABLES = (
    "ai_sessions",
    "ai_oauth_clients",
    "ai_oauth_codes",
    "ai_oauth_tokens",
    "ai_oauth_pending",
)


class UnsetAiIdentityOauthCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-unset-aiid-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def _dispatch(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.dispatch(list(args), root=self.tmp, plane=self.plane)
        return rc, out.getvalue(), err.getvalue()

    def test_foreign_keys_are_enforced_so_the_test_is_meaningful(self):
        self.assertEqual(self.plane.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_unset_removes_identity_with_oauth_state_and_keeps_audit(self):
        self.plane.set_ai_principal("bot", enabled=True)
        _verify(self.plane, "bot")
        self.plane.set_ai_principal("other", enabled=True)
        _verify(self.plane, "other")
        pid = _seed_oauth_state(self.plane, "bot", "a")
        other = _seed_oauth_state(self.plane, "other", "b")
        for table in CHILD_TABLES:
            self.assertEqual(_count(self.plane, table, pid), 1, table)

        rc, _out, err = self._dispatch(["unset", "ai-identity", "bot"])

        self.assertEqual(rc, 0, err)
        self.assertNotIn("referenced", err.lower())
        self.assertIsNone(self.plane.get_principal("bot"))
        for table in CHILD_TABLES:
            self.assertEqual(_count(self.plane, table, pid), 0, table)
        # Audit history is retained, detached from the deleted principal row.
        row = self.plane.conn.execute(
            "SELECT principal_id, principal_name FROM ai_activity WHERE principal_name = 'bot'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row["principal_id"])
        # A different identity is untouched.
        self.assertIsNotNone(self.plane.get_principal("other"))
        for table in CHILD_TABLES:
            self.assertEqual(_count(self.plane, table, other), 1, table)
        self.assertEqual(_count(self.plane, "ai_activity", other), 1)
        self.assertEqual(self.plane.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_unset_is_atomic_when_a_rule_still_references_the_identity(self):
        self.plane.set_ai_principal("bot", enabled=True)
        _verify(self.plane, "bot")
        v24.set_network_object(self.plane, "host-a", type="ip", value="198.51.100.10", oneshot=True)
        v24.set_permission_object(self.plane, "exec-only", permissions=["command-exec"], oneshot=True)
        v24.set_ai_access_rule(
            self.plane, "allow-exec", mode="whitelist", source="bot", destination="host-a",
            permission="exec-only", enabled=True, oneshot=True,
        )
        pid = _seed_oauth_state(self.plane, "bot", "a")

        rc, _out, err = self._dispatch(["unset", "ai-identity", "bot"])

        self.assertNotEqual(rc, 0)
        self.assertIn("still referenced", err)
        self.assertIn("ai-access allow-exec", err)
        self.assertIsNotNone(self.plane.get_principal("bot"))
        for table in CHILD_TABLES:
            self.assertEqual(_count(self.plane, table, pid), 1, table)
        self.assertEqual(_count(self.plane, "ai_activity", pid), 1)


if __name__ == "__main__":
    unittest.main()
