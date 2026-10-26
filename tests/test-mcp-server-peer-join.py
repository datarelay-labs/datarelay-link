#!/usr/bin/env python3
"""Root-only private Server Peer join, no secret in argv/logs."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("server_peer_join",
                                               ROOT / "tools/operator-server-peer-join.py")
assert SPEC and SPEC.loader
JOIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(JOIN)


class ServerPeerJoinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-peer-private-")
        self.path = Path(self.tmp.name)
        self.secret = "0123456789abcdef." + "a" * 64
        self.sha = "8" * 40

    def tearDown(self):
        self.tmp.cleanup()

    def test_direct_secret_storage_uses_0600(self):
        dest = self.path / "code"
        JOIN._save_code(self.secret, dest)
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
        self.assertEqual(dest.read_text().strip(), self.secret)
        with self.assertRaises(FileExistsError):
            JOIN._save_code(self.secret, dest)

    def test_root_required_before_asking_code(self):
        with (
            patch.object(JOIN.os, "geteuid", return_value=1000),
            patch.object(JOIN.getpass, "getpass") as prompt,
        ):
            with self.assertRaisesRegex(JOIN.peer.ServerPeerDenied, "Root"):
                JOIN.join(self.sha)
            prompt.assert_not_called()

    def test_private_tty_code_is_deleted_after_success(self):
        state = self.path / "isolated-state"
        captured = []

        def enrollment_only(**kwargs):
            codefile = Path(kwargs["code_file"])
            captured.append(codefile)
            self.assertTrue(codefile.exists())
            self.assertEqual(codefile.stat().st_mode & 0o777, 0o600)
            self.assertEqual(codefile.read_text().strip(), self.secret)
            return {"central_origin": "https://remote.xdr.ooo"}

        with (
            patch.object(JOIN, "SECRET_TEMP_PARENT", self.path),
            patch.object(JOIN.deployer, "ROOT", state),
            patch.object(JOIN.deployer, "UNIT", self.path / "peer.service"),
            patch.object(JOIN.deployer, "code_matches_head"),
            patch.object(JOIN.os, "geteuid", return_value=0),
            patch.object(JOIN.sys.stdin, "isatty", return_value=True),
            patch.object(JOIN.getpass, "getpass", return_value=self.secret) as prompt,
            patch.object(JOIN.peer, "validate_peer_root",
                         side_effect=JOIN.peer.ServerPeerDenied("missing")),
            patch.object(JOIN.enrollment, "enroll", side_effect=enrollment_only) as enroll,
            patch.object(JOIN.deployer, "apply") as apply,
            patch.object(JOIN.deployer, "verify") as verify,
        ):
            JOIN.join(self.sha)
            prompt.assert_called_once()
            enroll.assert_called_once()
            apply.assert_called_once_with(self.sha)
            verify.assert_called_once()
        self.assertEqual(len(captured), 1)
        self.assertFalse(captured[0].exists())

    def test_existing_peer_skips_new_enrollment(self):
        state = self.path / "peer"
        state.mkdir()
        with (
            patch.object(JOIN.deployer, "ROOT", state),
            patch.object(JOIN.deployer, "UNIT", self.path / "peer.service"),
            patch.object(JOIN.deployer, "code_matches_head"),
            patch.object(JOIN.os, "geteuid", return_value=0),
            patch.object(JOIN.peer, "validate_peer_root", return_value={"machine_id":"ready"}),
            patch.object(JOIN.getpass, "getpass") as prompt,
            patch.object(JOIN.enrollment, "enroll") as enroll,
            patch.object(JOIN.deployer, "apply") as apply,
            patch.object(JOIN.deployer, "verify") as verify,
        ):
            JOIN.join(self.sha)
            prompt.assert_not_called()
            enroll.assert_not_called()
            apply.assert_called_once_with(self.sha)
            verify.assert_called_once()

    def test_preexisting_service_is_verified_not_reinstalled(self):
        unit = self.path / "peer.service"
        unit.write_text("Existing Peer")
        with (
            patch.object(JOIN.deployer, "UNIT", unit),
            patch.object(JOIN.deployer, "code_matches_head"),
            patch.object(JOIN.os, "geteuid", return_value=0),
            patch.object(JOIN.getpass, "getpass") as prompt,
            patch.object(JOIN.deployer, "verify") as verify,
            patch.object(JOIN.deployer, "apply") as apply,
        ):
            JOIN.join(self.sha)
            verify.assert_called_once()
            apply.assert_not_called()
            prompt.assert_not_called()

    def test_invalid_code_format_never_creates_secret_file(self):
        with self.assertRaisesRegex(JOIN.peer.ServerPeerDenied, "format"):
            JOIN._save_code("not a manual code", self.path / "not-created")
        self.assertFalse((self.path / "not-created").exists())


if __name__ == "__main__":
    unittest.main()
