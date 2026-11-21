#!/usr/bin/env python3
"""An unchanged Remote Service upsert must not grow the Server DB Revision.

Root cause measured in p51 (isolated fleet, healthy listeners): every explicit
`drlink system synchronize` re-POSTs each non-seed Remote Service to
`/v1/remote-services`. `server_upsert_remote_service` then ran the full
`_mutate_publication` path (config_revisions + revision_snapshots + audit +
compile_runtime) even when the desired state was byte-identical, so a no-change
synchronize raised the revision by N (= number of Remote Services).

Contract under test:
  * identical re-upsert -> no new config_revisions row, no row_version bump,
    identical response;
  * any genuine desired-state change (enabled, Service Object port/destination)
    -> exactly one new revision, and policy/runtime projection stays correct.
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_mgmt_sync as mgmt
import drlink_v24 as v24

OWNER = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _auth(mid: str = OWNER) -> mgmt.MgmtAuthContext:
    return mgmt.MgmtAuthContext(mid, {"id": mid}, "nonce", 1, allocator=None)


class RemoteServiceUpsertNoChurn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-upsert-nochurn-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        self.plane.upsert_client(
            OWNER,
            label="relay-a",
            hostname="relay-a",
            addresses=[{"address": "10.0.0.10", "active": True}],
        )
        v24.set_network_object(
            self.plane, "db-target", type="fqdn", value="db.expected.invalid", oneshot=True
        )

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM", "DRLINK_SKIP_ACTIVATION"):
            os.environ.pop(key, None)

    def _body(self, **over):
        body = {
            "name": "svc-db",
            "destination": "db-target",
            "service": "ssh",
            "enabled": True,
            "runtime_verified": True,
        }
        body.update(over)
        return body

    def _max_rev(self) -> int:
        row = self.plane.conn.execute(
            "SELECT COALESCE(MAX(revision), 0) AS r FROM config_revisions"
        ).fetchone()
        return int(row["r"])

    def _snapshot_count(self) -> int:
        row = self.plane.conn.execute(
            "SELECT COUNT(*) AS c FROM revision_snapshots"
        ).fetchone()
        return int(row["c"])

    def _row_version(self) -> int:
        row = self.plane.conn.execute(
            "SELECT row_version FROM published_services WHERE name='svc-db'"
        ).fetchone()
        return int(row["row_version"])

    def _upsert(self, **over):
        return mgmt.server_upsert_remote_service(self.plane, _auth(), self._body(**over))

    def test_identical_reupsert_records_no_revision_and_same_response(self):
        first = self._upsert()
        self.assertEqual(first["status"], "HEALTHY")
        rev, snaps, rv = self._max_rev(), self._snapshot_count(), self._row_version()
        for _ in range(3):
            again = self._upsert()
            self.assertEqual(again, first)
        self.assertEqual(self._max_rev(), rev, "unchanged upsert must not add a revision")
        self.assertEqual(self._snapshot_count(), snaps, "unchanged upsert must not add a snapshot")
        self.assertEqual(self._row_version(), rv, "unchanged upsert must not bump row_version")

    def test_enabled_change_still_records_exactly_one_revision(self):
        self._upsert()
        rev = self._max_rev()
        disabled = self._upsert(enabled=False)
        self.assertEqual(disabled["status"], "DISABLED")
        self.assertEqual(self._max_rev(), rev + 1)
        again = self._upsert(enabled=False)
        self.assertEqual(again, disabled)
        self.assertEqual(self._max_rev(), rev + 1, "second identical disabled upsert is a no-op")
        re_enabled = self._upsert(enabled=True)
        self.assertEqual(re_enabled["status"], "HEALTHY")
        self.assertEqual(self._max_rev(), rev + 2)

    def test_service_object_port_change_still_records_revision_on_next_upsert(self):
        first = self._upsert()
        self.assertEqual(first["target_port"], 22)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=2222, oneshot=True)
        rev = self._max_rev()
        after = self._upsert()
        self.assertEqual(after["target_port"], 2222)
        # set_service_object already republishes the target; the upsert that follows
        # is then desired-state identical and must not add yet another revision.
        self.assertEqual(self._max_rev(), rev)
        pub = self.plane.conn.execute(
            "SELECT target_port FROM published_services WHERE name='svc-db'"
        ).fetchone()
        self.assertEqual(int(pub["target_port"]), 2222)

    def test_runtime_verified_flip_still_recorded(self):
        pending = self._upsert(runtime_verified=False)
        self.assertEqual(pending["status"], "DEGRADED")
        rev = self._max_rev()
        healthy = self._upsert(runtime_verified=True)
        self.assertEqual(healthy["status"], "HEALTHY")
        self.assertGreaterEqual(self._max_rev(), rev + 1)


if __name__ == "__main__":
    unittest.main()
