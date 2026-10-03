#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
from drlink_v30_audit import (
    DurableAuditSpool,
    build_access_decision_event,
    default_access_spool_root,
)


def _server_root(root: str) -> None:
    p = Path(root, "etc/drlink")
    p.mkdir(parents=True, exist_ok=True)
    Path(p, "config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class V30AuditWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v30-audit-worker-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        plane = ControlPlane(self.tmp)
        plane.close()

    def tearDown(self):
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def _spool(self, plane: str, source: str):
        return DurableAuditSpool(
            default_access_spool_root(plane, self.tmp),
            source,
            segment_bytes=16 * 1024,
            high_water_bytes=64 * 1024,
        )

    def _event(self, source: str, plane: str, result: str):
        return build_access_decision_event(
            source=source,
            event_type="%s.access.decision" % plane,
            result=result,
            resource_type="%s-access" % plane,
            resource_id="resource-1",
            reason_code="TEST",
            source_meta={"ip": "198.51.100.10"},
            destination_meta={"host": "example.com", "port": 443, "protocol": "tcp"},
        )

    def _run(self):
        env = dict(os.environ)
        env["DRLINK_TEST_ROOT"] = self.tmp
        return subprocess.run(
            [sys.executable, str(ROOT / "server" / "drlink-audit-ingest.py")],
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )

    def test_worker_ingests_both_sources_and_writes_runtime_health(self):
        remote = self._spool("remote", "remote-access")
        internet = self._spool("internet", "internet-access")
        remote.enqueue(self._event("remote-access", "remote", "ALLOW"))
        internet.enqueue(self._event("internet-access", "internet", "DENY"))

        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("AUDIT_INGEST=PASS", proc.stdout)

        plane = ControlPlane(self.tmp)
        try:
            rows = plane.conn.execute(
                "SELECT source,result FROM audit_events "
                "WHERE category='ACCESS_DECISION' ORDER BY source"
            ).fetchall()
            self.assertEqual(
                [(r["source"], r["result"]) for r in rows],
                [("internet-access", "deny"), ("remote-access", "allow")],
            )
        finally:
            plane.close()

        status_path = Path(self.tmp) / "var/lib/drlink/runtime/audit-ingest.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertTrue(status["ok"])
        self.assertTrue(status["sources"]["remote-access"]["ok"])
        self.assertTrue(status["sources"]["internet-access"]["ok"])
        self.assertEqual(remote.spool_bytes(), 0)
        self.assertEqual(internet.spool_bytes(), 0)

    def test_one_bad_source_does_not_block_other_source(self):
        remote = self._spool("remote", "remote-access")
        internet = self._spool("internet", "internet-access")
        bad = remote.root / "segment-00000000000000000001-bad.jsonl"
        bad.write_text("{broken-json}\n", encoding="utf-8")
        internet.enqueue(self._event("internet-access", "internet", "ALLOW"))

        proc = self._run()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("AUDIT_INGEST=DEGRADED", proc.stdout)
        self.assertTrue(bad.exists())

        plane = ControlPlane(self.tmp)
        try:
            count = plane.conn.execute(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE category='ACCESS_DECISION' AND source='internet-access'"
            ).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            plane.close()

        status = json.loads(
            (Path(self.tmp) / "var/lib/drlink/runtime/audit-ingest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(status["ok"])
        self.assertFalse(status["sources"]["remote-access"]["ok"])
        self.assertTrue(status["sources"]["internet-access"]["ok"])


if __name__ == "__main__":
    unittest.main()
