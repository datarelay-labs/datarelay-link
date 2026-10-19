#!/usr/bin/env python3
"""Import the native Egress policy with a non-listable trusted module directory.

This models the least-privilege drlink-egress service: known module file paths
can be traversed, but the directory is not enumerable.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "frp_egress_runtime.py",
    "frp_egress_control.py",
    "frp_policy_fingerprint.py",
    "drlink_control_db.py",
    "drlink_control_plane.py",
    "drlink_runtime_policy.py",
)


class NonListableEgressRuntimeImports(unittest.TestCase):
    def test_canonical_policy_loads_without_directory_read_permission(self):
        with tempfile.TemporaryDirectory(prefix="drlink-egress-import-") as tmp:
            library = Path(tmp) / "lib"
            library.mkdir(mode=0o700)
            for name in FILES:
                shutil.copyfile(ROOT / "lib" / name, library / name)
                (library / name).chmod(0o644)
            library.chmod(0o100)
            try:
                self.assertEqual(stat.S_IMODE(library.stat().st_mode), 0o100)
                # -I excludes incidental PYTHONPATH/CWD imports, and the
                # trusted file's absolute path remains readable by traversal.
                runner = textwrap.dedent(
                    """
                    import importlib.util
                    import os
                    import sys
                    from pathlib import Path

                    lib = Path(sys.argv[1])
                    if os.geteuid() != 0:
                        assert not os.access(lib, os.R_OK), "unexpected module-list permission"
                    sys.path.insert(0, str(lib))
                    name = "frp_egress_runtime"
                    spec = importlib.util.spec_from_file_location(name, lib / (name + ".py"))
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[name] = mod
                    spec.loader.exec_module(mod)
                    assert mod.RP is not None, "canonical drlink_runtime_policy import was suppressed"
                    assert callable(mod.RP.ControlPlaneCache)
                    print("CANONICAL_EGRESS_POLICY_IMPORT=PASS")
                    """
                )
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
                run = subprocess.run(
                    [sys.executable, "-I", "-c", runner, str(library)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(
                    run.returncode,
                    0,
                    "Non-listable module import failed\nstdout:\n%s\nstderr:\n%s"
                    % (run.stdout, run.stderr),
                )
                self.assertIn("CANONICAL_EGRESS_POLICY_IMPORT=PASS", run.stdout)
            finally:
                library.chmod(0o700)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which("runuser"), "root and runuser required")
class NativeEgressPslInstallPermissions(unittest.TestCase):
    def test_server_sandbox_grants_only_psl_directory_traverse(self):
        """Real installer helper must allow PSL read without directory listing."""
        import pwd

        try:
            pwd.getpwnam("drlink-egress")
        except KeyError:
            self.skipTest("dedicated drlink-egress account not installed")

        with tempfile.TemporaryDirectory(prefix="drlink-egress-psl-") as tmp:
            root = Path(tmp)
            root.chmod(0o711)
            directory = root / "usr/local/lib/drlink/data"
            directory.mkdir(parents=True)
            for path in (root / "usr", root / "usr/local", root / "usr/local/lib"):
                path.chmod(0o755)
            directory.parent.chmod(0o700)
            directory.chmod(0o700)
            suffix = directory / "public_suffix_list.dat"
            suffix.write_text("// fixture public suffix list\ncom\n", encoding="ascii")
            suffix.chmod(0o644)

            secret = root / "etc/frp/server_token"
            secret.parent.mkdir(parents=True)
            secret.parent.chmod(0o700)
            secret.write_text("test-private-value\n", encoding="ascii")
            secret.chmod(0o600)

            env = dict(os.environ, FRP_SERVER_TEST_ROOT=str(root))
            prepare = subprocess.run(
                ["bash", "-c", 'source "$1"; frp_server_ensure_sandbox_dirs',
                 "bash", str(ROOT / "install-server.sh")],
                env=env, capture_output=True, text=True, timeout=35,
            )
            self.assertEqual(prepare.returncode, 0, "installer sandbox preparation failed: %s" % prepare.stderr[-600:])

            code = textwrap.dedent("""
                import os, sys
                from pathlib import Path
                data = Path(sys.argv[1])
                secret = Path(sys.argv[2])
                assert (data / "public_suffix_list.dat").read_text().startswith("// fixture")
                assert not os.access(data, os.R_OK), "PSL directory listing must remain denied"
                assert not os.access(secret, os.R_OK), "server token must remain inaccessible"
                print("PSL_LEAST_PRIVILEGE_TRAVERSE=PASS")
            """)
            probe = subprocess.run(
                ["runuser", "-u", "drlink-egress", "--", sys.executable,
                 "-c", code, str(directory), str(secret)],
                capture_output=True, text=True, timeout=12,
            )
            self.assertEqual(
                probe.returncode, 0,
                "PSL_DIRECTORY_UNTRAVERSABLE_OR_ACCESS_WIDENED: %s"
                % probe.stderr[-500:],
            )
            self.assertIn("PSL_LEAST_PRIVILEGE_TRAVERSE=PASS", probe.stdout)
            self.assertFalse(stat.S_IMODE(directory.stat().st_mode) & 0o005)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
