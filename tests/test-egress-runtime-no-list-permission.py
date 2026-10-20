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
    "drlink_v24.py",
    "drlink_runtime_policy.py",
)


class NonListableEgressRuntimeImports(unittest.TestCase):
    def test_cache_and_authorization_use_canonical_policy_without_directory_listing(self):
        """Fresh unprivileged imports must reach real read-only SQLite policy.

        A disposable root models the module-directory restriction; this is not
        a native proxy/installer test. The old import-only assertion did not
        exercise status() or Internet Access's lazy canonical-policy imports.
        """
        seed = textwrap.dedent(
            """
            import json, sys
            from pathlib import Path
            sys.path.insert(0, sys.argv[1])
            from drlink_control_db import open_control_db
            for case in ('healthy', 'mismatch'):
                root = Path(sys.argv[2]) / case
                cfg = root / 'etc/drlink/config.json'
                cfg.parent.mkdir(parents=True)
                cfg.write_text(json.dumps({'deployment_mode': 'direct'}))
                conn = open_control_db(str(root))
                conn.execute("INSERT INTO config_revisions(revision,actor,command,created_at,summary) VALUES (7,'fixture','fixture','2026-10-20T00:00:00Z','isolated cache regression')")
                conn.execute("UPDATE runtime_generations SET generation=7, db_revision=7, status='active', error=''")
                conn.execute("INSERT OR REPLACE INTO access_policies(plane,mode,enforcement,updated_at) VALUES ('internet','whitelist','disabled','2026-10-20T00:00:00Z')")
                if case == 'mismatch':
                    conn.execute("UPDATE runtime_generations SET generation=6, db_revision=6 WHERE plane='internet'")
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                conn.execute('PRAGMA journal_mode=DELETE')
                conn.close()
            """
        )
        runner = textwrap.dedent(
            """
            import importlib.util, os, sys
            from pathlib import Path
            lib, root, case = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
            assert os.geteuid() != 0, 'root would bypass the directory-read restriction'
            try:
                os.listdir(lib)
            except PermissionError:
                pass
            else:
                raise AssertionError('module directory unexpectedly enumerable')
            assert not any(name.startswith('drlink_') for name in sys.modules), 'canonical modules already imported'
            assert (lib / 'drlink_v24.py').read_bytes(), 'known module path must remain readable'
            sys.path.insert(0, str(lib))
            name = 'frp_egress_runtime'
            spec = importlib.util.spec_from_file_location(name, lib / (name + '.py'))
            runtime = importlib.util.module_from_spec(spec)
            sys.modules[name] = runtime
            spec.loader.exec_module(runtime)
            assert runtime.RP is not None, 'canonical runtime import suppressed'
            cache = runtime.PolicyCache(root / 'etc/drlink/config.json')
            plane, error, _cfg, snapshot = cache.snapshot()
            request = dict(source_ip='192.0.2.20', hostname='example.com', port=80,
                           protocol='tcp', candidate_ips=['93.184.216.34'])
            if case == 'healthy':
                assert error is None and plane is not None, repr(error)
                assert snapshot.healthy and snapshot.generation == 7
                assert plane.db_file == root / 'var/lib/drlink/drlink.db', 'escaped disposable root'
                assert plane.conn.execute('PRAGMA query_only').fetchone()[0] == 1
                status = plane.status()
                assert status['db_healthy'] and not status['mismatch'] and status['revision'] == 7
                evaluation = plane.evaluate_internet_access(
                    request['source_ip'], request['hostname'], request['port'],
                    request['protocol'], candidate_ips=request['candidate_ips'])
                assert evaluation['action'] == 'DENY', evaluation
                assert evaluation['reason'] == 'Policy enforcement DISABLED (DENY ALL)', evaluation
                decision = cache.authorize(**request)
                assert decision['decision'] == 'DENY', decision
                assert decision['reason'] == runtime.RP.REASON_IMPLICIT_DENY, decision
                assert decision['authorized_candidates'] == [], decision
            else:
                assert plane is None and error == 'runtime generation mismatch', repr(error)
                assert snapshot is not None and not snapshot.healthy
                decision = cache.authorize(**request)
                assert decision['decision'] == 'DENY', decision
                assert decision['reason'] == runtime.EG.REASON_POLICY_UNHEALTHY, decision
                assert decision['authorized_candidates'] == [], decision
            if cache._cp is not None:
                cache._cp._close_cached_plane()
            print('CANONICAL_EGRESS_CACHE_' + case.upper() + '=PASS')
            """
        )
        with tempfile.TemporaryDirectory(prefix="drlink-egress-cache-") as tmp:
            base = Path(tmp); base.chmod(0o711)
            library = base / "lib"; library.mkdir(mode=0o700)
            for name in FILES:
                shutil.copyfile(ROOT / "lib" / name, library / name)
                (library / name).chmod(0o644)
            env = {k: v for k, v in os.environ.items() if not k.startswith(("FRP_", "DRLINK_"))}
            setup = subprocess.run(
                [sys.executable, "-I", "-B", "-c", seed, str(ROOT / "lib"), str(base)],
                env=env, capture_output=True, text=True, timeout=20, check=False,
            )
            self.assertEqual(setup.returncode, 0, "Disposable DB setup failed: " + setup.stderr)
            for case in ("healthy", "mismatch"):
                root = base / case; root.chmod(0o755)
                for path in root.rglob("*"):
                    path.chmod(0o755 if path.is_dir() else 0o644)
            identity = {}
            mode = 0o100
            if os.geteuid() == 0:
                # A numeric disposable identity requires no service account or
                # installer. It receives only group traversal of root-owned lib.
                os.chown(library, 0, 65534); mode = 0o710
                identity = {"user": 65534, "group": 65534, "extra_groups": []}
            library.chmod(mode)
            try:
                for case in ("healthy", "mismatch"):
                    with self.subTest(case=case):
                        root = base / case; db = root / "var/lib/drlink/drlink.db"
                        before = db.read_bytes()
                        run = subprocess.run(
                            [sys.executable, "-I", "-B", "-c", runner, str(library), str(root), case],
                            env=dict(env, FRP_DEPLOY_TEST_ROOT=str(root)),
                            capture_output=True, text=True, timeout=20, check=False, **identity,
                        )
                        self.assertEqual(run.returncode, 0, "Non-listable cache failed\nstdout:\n%s\nstderr:\n%s" % (run.stdout, run.stderr))
                        self.assertIn("CANONICAL_EGRESS_CACHE_" + case.upper() + "=PASS", run.stdout)
                        self.assertEqual(db.read_bytes(), before, "Read-only cache changed the closed fixture DB")
                        self.assertEqual(stat.S_IMODE(library.stat().st_mode), mode)
            finally:
                library.chmod(0o700)

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
