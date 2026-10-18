#!/usr/bin/env python3
"""P-013: cached verified policy requests must not rescan full SQLite DB or PSL.

The canonical full integrity/generation check still runs on initial load and
fingerprint mutation. Public direct policy callers retain a full check.
"""
from __future__ import annotations
import builtins
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_plane import ControlPlane
import drlink_v24
import drlink_runtime_policy as RP
import frp_egress_runtime as RT


class PolicyHotPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved_env = os.environ.get("FRP_DEPLOY_TEST_ROOT")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = str(self.root)
        self.cfg = self.root / "etc/drlink/config.json"
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text(json.dumps({"egress_listen_addr": "127.0.0.1", "egress_listen_port": 6102}) + "\n")
        plane = ControlPlane(str(self.root))
        try:
            drlink_v24.set_network_object(plane, "test-source", type="ip", value="127.0.0.1", oneshot=True)
            drlink_v24.set_network_object(plane, "test-host", type="fqdn", value="allowed.test", oneshot=True)
            drlink_v24.set_service_object(plane, "test-https", type="tcp", port=443, oneshot=True)
            drlink_v24.set_access_rule(
                plane, "internet", "test-allow", mode="whitelist", source="test-source",
                destination="test-host", service="test-https", enabled=True, oneshot=True)
            plane.compile_runtime()
        finally:
            plane.close()
        self.cache = RT.PolicyCache(self.cfg)

    def tearDown(self):
        if self.cache._cp is not None:
            self.cache._cp._close_cached_plane()
        if self.saved_env is None:
            os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)
        else:
            os.environ["FRP_DEPLOY_TEST_ROOT"] = self.saved_env
        self.tmp.cleanup()

    def _deny(self):
        return self.cache.authorize(
            source_ip="127.0.0.1", hostname="denied.test", port=443,
            protocol="https", candidate_ips=["93.184.215.14"],
        )

    def test_cache_verified_requests_do_not_repeat_full_integrity_scan(self):
        original = ControlPlane.status
        calls = []
        def counting(plane):
            calls.append(1)
            return original(plane)
        with mock.patch.object(ControlPlane, "status", counting):
            for _ in range(4):
                decision = self._deny()
                self.assertEqual(decision["decision"], "DENY")
            self.assertEqual(len(calls), 0, "verified unchanged DB scanned fully per CONNECT")
            # Uncached call must still protect its own DB integrity.
            plane = ControlPlane(str(self.root), read_only=True)
            try:
                RP.authorize_internet(plane, source_ip="127.0.0.1",
                                     hostname="denied.test", port=443, protocol="https",
                                     candidate_ips=["93.184.215.14"])
            finally:
                plane.close()
            self.assertGreaterEqual(len(calls), 1)

    def test_cached_revision_mismatch_fails_closed(self):
        plane = ControlPlane(str(self.root), read_only=True)
        try:
            current_revision = plane.current_revision()
            result = RP.authorize_internet(
                plane, source_ip="127.0.0.1", hostname="allowed.test",
                port=443, protocol="https", candidate_ips=["93.184.215.14"],
                validated_revision=current_revision - 1,
            )
        finally:
            plane.close()
        self.assertEqual(result["decision"], "DENY")
        self.assertTrue(result["reason"] in ("GENERATION_MISMATCH", "DB_UNAVAILABLE"),
                        result["reason"])

    def test_generation_mismatch_and_missing_db_fail_closed(self):
        # Simulate unexpected current-policy generation drift on the native DB.
        plane = ControlPlane(str(self.root))
        try:
            plane.conn.execute(
                "UPDATE runtime_generations SET status = 'mismatch' WHERE plane = 'internet'"
            )
        finally:
            plane.close()
        with mock.patch.object(ControlPlane, "status", wraps=ControlPlane.status) as check:
            decision = self._deny()
            self.assertEqual(decision["decision"], "DENY")
            self.assertGreater(check.call_count, 0, "mutation must recheck integrity")
        # Missing canonical policy DB must never reuse the last ALLOW snapshot.
        (self.root / "var/lib/drlink/drlink.db").unlink()
        self.assertEqual(self._deny()["decision"], "DENY")

    def test_same_revision_sqlite_write_invalidates_verified_cache(self):
        original = ControlPlane.status
        calls = []
        def counting(plane):
            calls.append(1)
            return original(plane)
        # SQL write with unchanged revision must invalidate the integrity cache.
        # This models cross-process WAL changes that bypass a config revision.
        with mock.patch.object(ControlPlane, "status", counting):
            self.assertEqual(self._deny()["decision"], "DENY")
            self.assertEqual(len(calls), 0)
            writer = ControlPlane(str(self.root))
            try:
                writer.conn.execute(
                    "INSERT INTO system_meta(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("p013-test-data-version", "canary"),
                )
            finally:
                writer.close()
            self.assertEqual(self._deny()["decision"], "DENY")
            self.assertGreaterEqual(len(calls), 1, "same-revision WAL write must trigger full check")

    def test_legacy_psl_fallback_reuses_validated_helper(self):
        # Gateway dynamic module import can omit sibling 'lib' from sys.path.
        # Force the same fallback to show parsing is cached per module.
        path = ROOT / "lib/frp_egress_control.py"
        spec = importlib.util.spec_from_file_location("eg_p013_fallback", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_import = builtins.__import__
        def block_psl(name, *args, **kwargs):
            if name == "frp_public_suffix":
                raise ImportError("simulate packaged fallback")
            return original_import(name, *args, **kwargs)
        with mock.patch("builtins.__import__", side_effect=block_psl):
            first = module._load_psl_module()
            second = module._load_psl_module()
        self.assertIs(first[3], second[3], "PSL helper reimported per policy check")
        first[3]()
        self.assertTrue(first[1]("com"))
        self.assertFalse(first[1]("example.com"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
