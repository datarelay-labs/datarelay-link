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


if __name__ == "__main__":
    unittest.main()
