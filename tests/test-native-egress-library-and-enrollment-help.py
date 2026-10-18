#!/usr/bin/env python3
"""Native least-privilege Egress library traversal and public Bulk help regressions."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install-server.sh"
CATALOG_PATH = ROOT / "lib/frp_cli_final_commands.json"


class StaticPublicContract(unittest.TestCase):
    def test_bulk_enrollment_discoverable_under_context_help(self):
        rows = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        current = [x for x in rows if x.get("path") == ["set", "enrollment"]]
        self.assertEqual(len(current), 1)
        spec = current[0]
        self.assertIn("set enrollment bulk", spec["examples"])
        self.assertIn("bulk", spec["args"][0]["complete"])
        self.assertTrue(
            any(x.get("path") == ["set", "enrollment", "bulk"] for x in rows)
        )
        module_spec = importlib.util.spec_from_file_location(
            "egress_help_catalog", ROOT / "lib/frp_cli_catalog.py"
        )
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        rendered = module.command_help(spec)
        self.assertIn("set enrollment bulk", rendered)
        self.assertIn("zero-touch, manual, bulk", rendered)

    def test_install_source_explicitly_grants_narrow_egress_library_traverse(self):
        text = INSTALLER.read_text(encoding="utf-8")
        name = "frp_server_ensure_sandbox_dirs() {"
        self.assertIn(name, text)
        start = text.index(name)
        body = text[start : text.index("\n}\n", start) + 2]
        self.assertIn('lib_dir="$(frp_server_fs /usr/local/lib/drlink)"', body)
        self.assertIn('setfacl -m u:drlink-egress:--x "$lib_dir"', body)
        self.assertIn('chgrp drlink-egress "$lib_dir"', body)
        self.assertIn('chmod 0710 "$lib_dir"', body)
        self.assertNotIn('chmod 0755 "$lib_dir"', body)


@unittest.skipUnless(
    os.geteuid() == 0 and shutil.which("runuser") is not None,
    "requires native sandbox root execution",
)
class LiveNativeServiceUserTraverse(unittest.TestCase):
    def setUp(self):
        try:
            pwd.getpwnam("drlink-egress")
        except KeyError:
            self.skipTest("installed egress runtime principal unavailable")
        self.t = tempfile.TemporaryDirectory(prefix="drlink-egress-library-r54-")
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.root.chmod(0o755)
        self.lib = self.root / "usr/local/lib/drlink"
        self.lib.mkdir(parents=True)
        self.lib.chmod(0o700)
        self.entry = self.lib / "native_egress_script.py"
        self.entry.write_text("print('NATIVE_EGRESS_EXECUTED')\n", encoding="utf-8")
        self.entry.chmod(0o644)

    def _reconcile(self):
        env = os.environ.copy()
        env["FRP_SERVER_TEST_ROOT"] = str(self.root)
        run = subprocess.run(
            ["bash", "-c", f'source "{INSTALLER}"; frp_server_ensure_sandbox_dirs'],
            env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(run.returncode, 0, run.stderr[-1600:])

    def test_service_can_load_installed_scripts_without_world_directory_access(self):
        self._reconcile()
        # The code is not secret, but the directory must not be world-listable
        # or world-traversable merely to run the non-root Egress service.
        mode = stat.S_IMODE(self.lib.stat().st_mode)
        self.assertEqual(mode & 0o007, 0, oct(mode))
        self.assertFalse(bool(mode & stat.S_IWGRP))
        user = subprocess.run(
            ["runuser", "-u", "drlink-egress", "--", "python3", str(self.entry)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(user.returncode, 0, user.stderr)
        self.assertEqual(user.stdout.strip(), "NATIVE_EGRESS_EXECUTED")
        nobody = subprocess.run(
            ["runuser", "-u", "nobody", "--", "python3", str(self.entry)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertNotEqual(nobody.returncode, 0)
        token_dir = self.root / "etc/frp"
        self.assertEqual(stat.S_IMODE(token_dir.stat().st_mode), 0o700)
        self._reconcile()
        again = subprocess.run(
            ["runuser", "-u", "drlink-egress", "--", "python3", str(self.entry)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(again.returncode, 0, again.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
