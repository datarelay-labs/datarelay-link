#!/usr/bin/env python3
"""Disposable Native MCP rollout fixtures; no real systemd or privilege changes."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import pwd
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/operator-native-mcp-full-control.py"
if not HELPER.exists():
    HELPER = Path(__file__).with_name("operator-native-mcp-full-control.py")
spec = importlib.util.spec_from_file_location("native_mcp_rollout", HELPER)
rollout = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rollout
spec.loader.exec_module(rollout)


class RolloutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-mcp-rollout-")
        self.root = Path(self.temp.name)
        self.layout = rollout.Layout(self.root / "installed")
        self.layout.root.mkdir()
        self.account = pwd.getpwuid(os.geteuid())
        self.settings = rollout.profile(self.account.pw_name, [str(self.root)], os.geteuid() == 0)
        self.files = {name: ("# candidate module\nVALUE = " + str(i) + "\n").encode()
                      for i, name in enumerate(rollout.TARGETS[:-1])}
        self.head = "a" * 40
        self.selected = {"head": self.head, "source": str(self.root), "clean": True, "files": self.files}
        self.patches = [patch.object(rollout, "OWNER_UID", os.geteuid()),
                        patch.object(rollout, "OWNER_GID", os.getegid()),
                        patch.object(rollout, "require_root"),
                        patch.object(rollout, "candidate", return_value=self.selected),
                        patch.object(rollout, "service")]
        self.mocks = [item.start() for item in self.patches]
        for name in rollout.TARGETS[:1]:
            target = self.layout.target(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"# original module\n")
        self.untouched = {
            "etc/systemd/system/drlink-mcp-bridge.service": b"[Service]\nUser=root\n",
            "etc/systemd/system/drlink-mcp-bridge.service.d/native-self.conf": (
                b"[Service]\nEnvironment=DRLINK_MCP_SERVER_SELF_ENABLED=1\n"
                b"Environment=DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0\n"),
            "etc/drlink/oauth.json": b"fixture OAuth state\n",
            "var/lib/drlink/control.db": b"fixture database\n",
            "etc/letsencrypt/live/fixture/fullchain.pem": b"fixture certificate\n",
        }
        for name, data in self.untouched.items():
            target = self.layout.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def install(self):
        return rollout.apply(self.root, self.head, self.settings, self.layout)

    def assert_untouched(self):
        for name, data in self.untouched.items():
            self.assertEqual((self.layout.root / name).read_bytes(), data, name)

    def test_check_is_read_only_and_lists_exact_targets(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = rollout.check(self.root, self.head, self.settings, self.layout)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual({item["path"] for item in result["changes"]},
                         {str(self.layout.target(name)) for name in rollout.TARGETS})
        self.mocks[-1].assert_not_called()
        self.assertFalse(self.layout.backups.exists())

    def test_apply_and_rollback_preserve_unrelated_state(self):
        result = self.install()
        self.mocks[-2].assert_called_once_with(self.root, self.head, clean_required=True)
        for name, data in self.files.items():
            self.assertEqual(self.layout.target(name).read_bytes(), data)
        receipt = Path(result["receipt"])
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(receipt.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(set(json.loads(receipt.read_text())["files"]), set(rollout.TARGETS))
        self.assertEqual([call.args[0] for call in self.mocks[-1].call_args_list],
                         ["is-active", "daemon-reload", "restart", "is-active"])
        self.assert_untouched()
        rollout.rollback(receipt, self.layout)
        self.assertEqual(self.layout.target(rollout.TARGETS[0]).read_bytes(), b"# original module\n")
        for name in rollout.TARGETS[1:]:
            self.assertFalse(self.layout.target(name).exists())
        self.assert_untouched()

    def test_failed_restart_restores_original_and_absent_files(self):
        failed = False
        def service(action):
            nonlocal failed
            if action == "restart" and not failed:
                failed = True
                raise rollout.RolloutError("fixture first restart failed")
        self.mocks[-1].side_effect = service
        with self.assertRaisesRegex(rollout.RolloutError, "was rolled back"):
            self.install()
        self.assertEqual(self.layout.target(rollout.TARGETS[0]).read_bytes(), b"# original module\n")
        for name in rollout.TARGETS[1:]:
            self.assertFalse(self.layout.target(name).exists())
        self.assertEqual(sum(call.args[0] == "restart" for call in self.mocks[-1].call_args_list), 2)
        self.assert_untouched()

    def test_full_control_dropin_takes_precedence_without_changing_self_profile(self):
        self.install()
        environment = {}
        directory = self.layout.target(rollout.TARGETS[-1]).parent
        for path in sorted(directory.glob("*.conf")):
            for line in path.read_text().splitlines():
                if line.startswith("Environment="):
                    for assignment in shlex.split(line[len("Environment="):]):
                        key, value = assignment.split("=", 1)
                        environment[key] = value
        self.assertEqual(environment["DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED"], "1")
        self.assertEqual(environment["DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED"], "1")
        self.assertEqual(environment["DRLINK_MCP_SERVER_EXEC_USER"], self.account.pw_name)
        self.assert_untouched()

    def test_concurrent_edit_during_backup_is_preserved(self):
        target = self.layout.target(rollout.TARGETS[0])
        def service(action):
            if action == "is-active":
                target.write_bytes(b"# independently updated module\n")
        self.mocks[-1].side_effect = service
        with self.assertRaisesRegex(rollout.RolloutError, "changed while preparing"):
            self.install()
        self.assertEqual(target.read_bytes(), b"# independently updated module\n")
        for name in rollout.TARGETS[1:]:
            self.assertFalse(self.layout.target(name).exists())

    def test_rollback_rejects_later_edits_before_any_restore(self):
        result = self.install()
        changed = self.layout.target(rollout.TARGETS[1])
        changed.write_bytes(b"# later independent edit\n")
        self.mocks[-1].reset_mock()
        with self.assertRaisesRegex(rollout.RolloutError, "subsequently modified"):
            rollout.rollback(result["receipt"], self.layout)
        self.assertEqual(changed.read_bytes(), b"# later independent edit\n")
        self.assertEqual(self.layout.target(rollout.TARGETS[0]).read_bytes(), self.files[rollout.TARGETS[0]])
        self.mocks[-1].assert_not_called()

    def test_rollback_rejects_corrupt_backup(self):
        result = self.install()
        (Path(result["receipt"]).parent / "0.before").write_bytes(b"tampered backup")
        with self.assertRaisesRegex(rollout.RolloutError, "backup hash"):
            rollout.rollback(result["receipt"], self.layout)
        self.assertEqual(self.layout.target(rollout.TARGETS[0]).read_bytes(), self.files[rollout.TARGETS[0]])

    def test_rollback_preserves_later_permission_edit(self):
        result = self.install()
        target = self.layout.target(rollout.TARGETS[0])
        target.chmod(0o600)
        with self.assertRaisesRegex(rollout.RolloutError, "subsequently modified"):
            rollout.rollback(result["receipt"], self.layout)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_receipt_directory_traversal_is_rejected(self):
        with self.assertRaisesRegex(rollout.RolloutError, "dedicated rollout"):
            rollout.load_receipt(self.layout.backups / ".." / "receipt.json", self.layout)

    def test_operator_oauth_identity_hint_is_explicit_and_display_only(self):
        settings = rollout.profile(
            self.account.pw_name, [str(self.root)], os.geteuid() == 0,
            approval_identity="plugin-personal-e2e")
        self.assertEqual(settings["approval_identity"], "plugin-personal-e2e")
        conf = rollout.dropin(settings).decode()
        self.assertIn('Environment="DRLINK_MCP_OAUTH_OPERATOR_IDENTITY=plugin-personal-e2e"', conf)
        self.assertEqual(rollout.check(self.root, self.head, settings, self.layout)["profile"], settings)
        self.assertNotIn("DRLINK_MCP_OAUTH_OPERATOR_IDENTITY", rollout.dropin(self.settings).decode())
        for bad in ("", "agent with space", "agent<script>", "a\nEnvironment=BAD=1", "/tmp/x"):
            with self.assertRaisesRegex(rollout.RolloutError, "AI Identity name"):
                rollout.profile(self.account.pw_name, [str(self.root)], os.geteuid() == 0,
                                approval_identity=bad)

    def test_account_root_and_path_gates(self):
        with self.assertRaisesRegex(rollout.RolloutError, "separate --allow-root"):
            rollout.profile("root", [str(self.root)])
        for user, roots in (("", [str(self.root)]), (self.account.pw_name, []),
                            (self.account.pw_name, ["relative"]),
                            (self.account.pw_name, [str(self.root / "missing")])):
            with self.assertRaises(rollout.RolloutError):
                rollout.profile(user, roots, True)
        self.mocks[2].side_effect = rollout.RolloutError("root required")
        with self.assertRaisesRegex(rollout.RolloutError, "root required"):
            self.install()
        self.mocks[-2].assert_not_called()

    def test_symlink_target_is_rejected(self):
        target = self.layout.target(rollout.TARGETS[1])
        target.symlink_to(self.root / "unrelated")
        with self.assertRaisesRegex(rollout.RolloutError, "Symlink"):
            self.install()
        self.mocks[-1].assert_not_called()

    def test_dropin_is_separate_and_escapes_systemd_values(self):
        settings = dict(self.settings, roots=['/fixture/percent% and "quote"'])
        text = rollout.dropin(settings).decode()
        self.assertIn('percent%% and \\"quote\\"', text)
        self.assertNotIn("User=", text)
        self.assertNotIn("ExecStart", text)
        self.assertNotIn("OAUTH", text)
        self.assertIn("DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED=1", text)

    def test_real_git_clean_exact_head_provenance(self):
        self.patches[-2].stop()
        source = self.root / "source"
        (source / "lib").mkdir(parents=True)
        for name in rollout.MODULES:
            (source / "lib" / name).write_text("VALUE = 1\n")
        def git(*args):
            return subprocess.check_output(["git", "-C", str(source), *args], stderr=subprocess.DEVNULL).decode().strip()
        git("init", "-q")
        git("add", "lib")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        head = git("rev-parse", "HEAD")
        selected = rollout.candidate(source, head, clean_required=True)
        self.assertTrue(selected["clean"])
        self.assertEqual(set(selected["files"]), set(rollout.TARGETS[:-1]))
        with self.assertRaisesRegex(rollout.RolloutError, "does not match"):
            rollout.candidate(source, "b" * 40, clean_required=True)
        with self.assertRaisesRegex(rollout.RolloutError, "requires --head"):
            rollout.candidate(source, clean_required=True)
        (source / "lib" / rollout.MODULES[0]).write_text("VALUE = 2\n")
        with self.assertRaisesRegex(rollout.RolloutError, "completely clean"):
            rollout.candidate(source, head, clean_required=True)


if __name__ == "__main__":
    unittest.main()
