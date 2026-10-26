#!/usr/bin/env python3
"""Server-local MCP worker contract and privilege-boundary regressions."""
from __future__ import annotations

import os
import shutil
import subprocess
from types import SimpleNamespace
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_mcp_server_executor import (
    ExecutorDenied, _allowed_roots, execute_as_unprivileged_user, worker_dispatch,
)


class ServerLocalWorkerTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="drlink-v240-smcp-")
        self.path = Path(self.base)
        self.config = patch.dict(os.environ, {"DRLINK_MCP_SERVER_ALLOWED_ROOTS": self.base})
        self.config.start()

    def tearDown(self):
        self.config.stop()
        shutil.rmtree(self.base, ignore_errors=True)

    def run_worker(self, action, **kwargs):
        return worker_dispatch({"action": action, **kwargs})

    def test_read_write_delete_regular_file(self):
        path = self.path / "test.txt"
        result = self.run_worker("write_file", path=str(path), content="safe test")
        self.assertEqual(result["bytes"], 9)
        result = self.run_worker("read_file", path=str(path))
        import base64
        self.assertEqual(base64.b64decode(result["content_b64"]), b"safe test")
        self.assertTrue(self.run_worker("delete_file", path=str(path))["deleted"])
        self.assertFalse(path.exists())

    def test_existing_file_mode_preserved_and_unsafe_replacements_denied(self):
        path = self.path / "editable.py"
        path.write_text("old")
        path.chmod(0o755)
        initial = path.stat()
        self.run_worker("write_file", path=str(path), content="new")
        final = path.stat()
        self.assertEqual(final.st_mode & 0o777, 0o755)
        self.assertEqual((final.st_uid, final.st_gid), (initial.st_uid, initial.st_gid))
        self.assertEqual(path.read_text(), "new")

        other = self.path / "another-name.py"
        os.link(path, other)
        with self.assertRaisesRegex(ExecutorDenied, "hard-link"):
            self.run_worker("write_file", path=str(path), content="bad")
        self.assertEqual(path.read_text(), "new")

        other.unlink()
        with patch("drlink_mcp_server_executor.os.geteuid", return_value=initial.st_uid + 1):
            with self.assertRaisesRegex(ExecutorDenied, "ownership"):
                self.run_worker("write_file", path=str(path), content="bad")
        self.assertEqual(path.read_text(), "new")

    def test_fail_closed_paths_symlink_special_and_secrets(self):
        (self.path / "good.txt").write_text("good")
        (self.path / "redirect").symlink_to(self.path)
        out = Path(self.base).parent / "nonexistent-outside-file"
        for path in (
            self.path / "redirect" / "good.txt",
            self.path / ".ssh" / "id_rsa",
            self.path / ".git" / "config",
            self.path / ".env",
            self.path / "private.pem",
            self.path / "nested" / ".." / "good.txt",
            out,
        ):
            with self.assertRaises((ExecutorDenied, OSError), msg=str(path)):
                self.run_worker("read_file", path=str(path))
        with self.assertRaises((ExecutorDenied, OSError)):
            self.run_worker("write_file", path=str(self.path / "redirect" / "escape.txt"), content="x")
        with self.assertRaises((ExecutorDenied, OSError)):
            self.run_worker("delete_file", path=str(self.path / "redirect" / "good.txt"))
        self.assertEqual((self.path / "good.txt").read_text(), "good")

    def test_read_only_git_argv_strict(self):
        subprocess.run(["git", "init", "-q", self.base], check=True, capture_output=True)
        for argv in (["git", "status", "--short"], ["git", "rev-parse", "--show-toplevel"],
                     ["git", "diff", "--check"]):
            ret = self.run_worker("run_git", argv=argv, cwd=self.base)
            self.assertEqual(ret["exit_status"], 0, (argv, ret))
        for argv in (
            ["git", "add", "test.txt"],
            ["git", "push", "origin", "main"],
            ["git", "-c", "alias.pwn=!id", "status"],
            ["sh", "-c", "id"],
            ["git", "status", ";", "id"],
        ):
            with self.assertRaises((ExecutorDenied, OSError), msg=str(argv)):
                self.run_worker("run_git", argv=argv, cwd=self.base)

    def test_external_unprivileged_executor_fail_closed(self):
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_EXEC_USER": ""}):
            with self.assertRaises(ExecutorDenied):
                execute_as_unprivileged_user({"action": "read_file", "path": str(self.path / "a")})
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_EXEC_USER": "root"}):
            with self.assertRaises(ExecutorDenied):
                execute_as_unprivileged_user({"action": "read_file", "path": str(self.path / "a")})
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_EXEC_USER": "isolated-worker"}):
            with patch("drlink_mcp_server_executor.pwd.getpwnam",
                       return_value=SimpleNamespace(pw_uid=7001, pw_gid=7002)):
                with patch("drlink_mcp_server_executor.grp.getgrgid",
                           return_value=SimpleNamespace(gr_name="docker")):
                    with self.assertRaisesRegex(ExecutorDenied, "primary group"):
                        execute_as_unprivileged_user({"action": "read_file", "path": str(self.path / "a")})
        with patch.dict(os.environ, {"DRLINK_MCP_SERVER_ALLOWED_ROOTS": ""}):
            with self.assertRaises(ExecutorDenied):
                _allowed_roots()

    def test_release_manifest_includes_worker(self):
        manifest = (ROOT / "lib" / "server-project-files.manifest").read_text()
        self.assertIn("lib/drlink_mcp_server_executor.py python", manifest)
        installer = (ROOT / "install-server.sh").read_text()
        self.assertIn('"$BASE_DIR/lib/drlink_mcp_server_executor.py"', installer)
        updater = (ROOT / "lib" / "frp-server-upgrade.sh").read_text()
        self.assertIn("  drlink_mcp_server_executor.py", updater)

    def test_unknown_operations_denied(self):
        for action in ("exec", "bash", "sudo", "shell", "run_python", "run_test"):
            with self.assertRaises(ExecutorDenied):
                self.run_worker(action, path=str(self.path / "dummy"))


if __name__ == "__main__":
    unittest.main()
