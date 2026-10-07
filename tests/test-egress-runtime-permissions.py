#!/usr/bin/env python3
"""Egress runtime permission contract after atomic rewrite / restore helpers."""
from __future__ import annotations

import importlib.util
import os
import pwd
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EG = _load("frp_egress_control", "lib/frp_egress_control.py")
CFG = _load("frp_server_config", "lib/frp_server_config.py")


def _has_egress_user() -> bool:
    try:
        pwd.getpwnam("drlink-egress")
        return True
    except KeyError:
        return False


def _acl_mentions_egress(path: Path) -> bool:
    try:
        out = subprocess.check_output(["getfacl", "-p", str(path)], text=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    for line in out.splitlines():
        if line.startswith("user:drlink-egress:") and "r" in line.split(":", 2)[-1]:
            return True
    return False


def _group_readable(path: Path, *, write: bool = False) -> bool:
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    try:
        gid = pwd.getpwnam("drlink-egress").pw_gid
    except KeyError:
        return False
    try:
        import grp

        gid = grp.getgrnam("drlink-egress").gr_gid
    except Exception:
        pass
    if st.st_gid != gid:
        return False
    if write:
        return bool(mode & 0o060) == 0o060 or bool(mode & stat.S_IWGRP)
    return bool(mode & stat.S_IRGRP)


@unittest.skipUnless(os.geteuid() == 0, "requires root to exercise ownership/ACL")
@unittest.skipUnless(_has_egress_user(), "drlink-egress user required")
class EgressRuntimePermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-egress-perm-")
        self.root = Path(self.tmp.name)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = str(self.root)
        (self.root / "etc/drlink").mkdir(parents=True)
        (self.root / "var/lib/drlink").mkdir(parents=True)
        (self.root / "var/log/drlink").mkdir(parents=True)
        (self.root / "run/drlink").mkdir(parents=True)
        for d in (
            self.root / "etc/drlink",
            self.root / "var/lib/drlink",
            self.root / "var/log/drlink",
            self.root / "run/drlink",
        ):
            os.chown(d, 0, 0)
            os.chmod(d, 0o700)

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        self.tmp.cleanup()

    def _assert_egress_can_read(self, path: Path, *, write: bool = False):
        if _acl_mentions_egress(path):
            return
        self.assertTrue(
            _group_readable(path, write=write),
            "expected ACL or group-readable mode for %s (mode=%s gid=%s)"
            % (path, oct(stat.S_IMODE(path.stat().st_mode)), path.stat().st_gid),
        )

    def test_atomic_egress_control_preserves_access(self):
        path = self.root / "var/lib/drlink/egress-control.json"
        EG.save_egress_state(EG.empty_egress_state(), path=path)
        self._assert_egress_can_read(path, write=False)
        # Second mutation must not drop the grant after inode replace.
        state = EG.load_egress_state(path=path, persist_migration=False)
        EG.save_egress_state(state, path=path)
        self._assert_egress_can_read(path, write=False)

    def test_atomic_config_preserves_access(self):
        path = self.root / "etc/drlink/config.json"
        CFG.atomic_write_config(path, {"public_ip": "203.0.113.10", "schema_version": 1})
        self._assert_egress_can_read(path, write=False)
        cfg = CFG.load_config(path)
        cfg["public_hostname"] = "example.test"
        CFG.atomic_write_config(path, cfg)
        self._assert_egress_can_read(path, write=False)

    def test_reapply_helper_does_not_widen_secrets(self):
        secret = self.root / "etc/frp/server_token"
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("super-secret-token\n", encoding="utf-8")
        os.chmod(secret, 0o600)
        os.chown(secret, 0, 0)
        control = self.root / "var/lib/drlink/egress-control.json"
        EG.save_egress_state(EG.empty_egress_state(), path=control)
        EG.reapply_egress_runtime_permissions(control_path=control, parents=True)
        st = secret.stat()
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        self.assertEqual(st.st_uid, 0)
        self.assertEqual(st.st_gid, 0)
        self.assertFalse(_acl_mentions_egress(secret))



class EgressRuntimeLeastPrivilegeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-egress-least-")
        self.root = Path(self.tmp.name)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = str(self.root)
        self.runtime = self.root / "var/lib/drlink/runtime"
        self.runtime.mkdir(parents=True)
        (self.root / "etc/drlink").mkdir(parents=True)
        (self.root / "var/log/drlink/egress").mkdir(parents=True)
        (self.root / "run/drlink").mkdir(parents=True)
        self.inventory = self.runtime / "client-inventory.json"
        self.internet = self.runtime / "internet-access.json"
        self.inventory.write_text(
            '{"schema_version":2,"clients":{},"reserved":[]}\n',
            encoding="utf-8",
        )
        self.internet.write_text(
            '{"plane":"internet","rules":[]}\n',
            encoding="utf-8",
        )
        os.chmod(self.inventory, 0o640)
        os.chmod(self.internet, 0o600)

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        self.tmp.cleanup()

    def test_group_fallback_repairs_inventory_and_only_exposes_internet_projection(self):
        from unittest import mock

        with (
            mock.patch.object(EG.os, "geteuid", return_value=0),
            mock.patch.object(EG, "_egress_uid_gid", return_value=(12345, 23456)),
            mock.patch.object(EG, "_setfacl_user", return_value=False),
            mock.patch.object(EG.os, "chown", return_value=None),
        ):
            EG.reapply_egress_runtime_permissions(parents=True)

        self.assertEqual(stat.S_IMODE(self.inventory.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.runtime.stat().st_mode), 0o710)
        self.assertEqual(stat.S_IMODE(self.internet.stat().st_mode), 0o640)

    def test_acl_path_never_grants_inventory_read(self):
        from unittest import mock

        grants = []

        def fake_setfacl(path, perms):
            grants.append((Path(path), perms))
            return True

        with (
            mock.patch.object(EG.os, "geteuid", return_value=0),
            mock.patch.object(EG, "_egress_uid_gid", return_value=(12345, 23456)),
            mock.patch.object(EG, "_setfacl_user", side_effect=fake_setfacl),
            mock.patch.object(EG.os, "chown", return_value=None),
        ):
            EG.reapply_egress_runtime_permissions(parents=True)

        self.assertEqual(stat.S_IMODE(self.inventory.stat().st_mode), 0o600)
        self.assertNotIn(self.inventory, [path for path, _ in grants])
        self.assertIn((self.runtime, "--x"), grants)
        self.assertIn((self.internet, "r--"), grants)


class RestoreMissingLockHelperTests(unittest.TestCase):
    def test_restore_refuses_without_lock_helper(self):
        restore = ROOT / "tools" / "frp-restore"
        text = restore.read_text(encoding="utf-8")
        self.assertIn("refusing unlocked restore", text)
        # Static proof: soft continue without locks is gone.
        self.assertNotIn(
            "acquire_control_locks(root, timeout=timeout) if locks is not None else None",
            text,
        )


if __name__ == "__main__":
    unittest.main()
