#!/usr/bin/env python3
"""PF-12A Link: safe count-only historical configuration summary, no raw secret values."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from drlink_web_config_history import compare_product_revisions


def snapshot(revision, *, network_count=1, remote_rules=1, secret_value="TOKEN.TOPSECRET", first_ip="192.0.2.15"):
    return yaml.safe_dump({
        "configurationBundle": {
            "context": "server",
            "sourceRevision": revision,
            "networkObjects": [
                {"name": "secret-%s" % index, "type": "ip", "value": first_ip if index == 0 else "10.0.0.%d" % index}
                for index in range(network_count)
            ],
            "serviceObjects": [{"name": "smtp", "port": 25, "type": "tcp"}],
            "remoteAccess": {
                "mode": "whitelist", "enforcement": "enabled",
                "rules": [
                    {"name": "secret-rule-%d" % x, "source": secret_value,
                     "destination": "redacted-destination", "service": "smtp", "enabled": True}
                    for x in range(remote_rules)
                ],
            },
        },
    }, sort_keys=False)


class ConfigHistoryTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="pf12a-link-history-")
        self.addCleanup(self.work.cleanup)
        self.root = self.work.name
        self.add_revision(1, snapshot(1, network_count=1, remote_rules=1))
        self.add_revision(2, snapshot(2, network_count=2, remote_rules=2))

    def add_revision(self, number, yaml_string, *, summary="do not leak TOKEN.TOPSECRET"):
        plane = ControlPlane(self.root)
        try:
            plane.conn.execute(
                "INSERT INTO config_revisions(revision,actor,command,created_at,summary) VALUES (?,?,?,?,?)",
                (number, "secret.actor@example.test", "api-key change", "2026-10-10T01:00:00Z", summary),
            )
            plane.conn.execute(
                "INSERT INTO revision_snapshots(revision,snapshot_json) VALUES (?,?)",
                (number, json.dumps({"snapshot_format":"drlink-revision-configuration-v1","configuration_bundle":yaml_string})),
            )
            plane.conn.commit()
        finally:
            plane.close()

    def report(self, from_rev=1, to_rev=2):
        return compare_product_revisions(self.root, from_rev, to_rev)

    def test_counts_diff_and_pinned_foundation_fingerprints_are_deterministic(self):
        a = self.report()
        b = self.report()
        self.assertEqual(a, b)
        self.assertEqual(a["from_revision"], 1)
        self.assertEqual(a["to_revision"], 2)
        self.assertEqual(a["source_scope"], "allowlisted_counts_only")
        self.assertEqual(a["changed_categories"], 3)
        self.assertEqual(a["counts"]["from"]["network_objects"], 1)
        self.assertEqual(a["counts"]["to"]["network_objects"], 2)
        self.assertEqual(a["counts"]["from"]["remote_access_rules"], 1)
        self.assertEqual(a["counts"]["to"]["remote_access_rules"], 2)
        self.assertEqual(a["counts"]["to"]["service_objects"], 1)
        self.assertEqual(len(a["from_fingerprint"]), 64)
        self.assertEqual(len(a["to_fingerprint"]), 64)
        self.assertTrue(a["read_only"])
        self.assertFalse(a["authoritative_mutation"])

    def test_no_full_semantic_equality_claim_for_same_count_different_values(self):
        self.add_revision(3, snapshot(3, network_count=2, remote_rules=2, first_ip="10.1.99.3"))
        report = self.report(2, 3)
        self.assertEqual(report["changed_categories"], 0)
        self.assertFalse(report["full_semantic_diff_verified"])
        self.assertFalse(report["semantic_equivalence_proven"])

    def test_raw_snapshots_secrets_names_ips_and_actors_never_leave_projection(self):
        encoded = json.dumps(self.report(), sort_keys=True)
        for sensitive in ("TOPSECRET", "192.0.2.", "10.0.0.", "smtp", "secret-rule",
                          "secret.actor", "api-key", "configurationBundle",
                          "sourceRevision", "redacted-destination"):
            with self.subTest(secret=sensitive):
                self.assertNotIn(sensitive, encoded)

    def test_rollback_preview_always_requires_privileged_out_of_band_proof(self):
        d = self.report()["rollback_preview"]
        self.assertFalse(d["may_submit_to_product_authority"])
        self.assertTrue(d["product_apply_required"])
        self.assertIn("unsupported", d["blockers"])
        self.assertIn("mfa_required", d["blockers"])
        self.assertIn("backup_missing", d["blockers"])
        self.assertIn("out_of_band_required", d["blockers"])
        self.assertIn("audit_unavailable", d["blockers"])

    def test_missing_legacy_and_malformed_snapshots_fail_closed_without_raw_data(self):
        scenarios = [
            (4, "{}"),
            (5, json.dumps({"configuration_bundle": "{}"})),
            (6, json.dumps({"configuration_bundle": "not: [valid yaml"})),
            (7, json.dumps({"configuration_bundle": "x" * 140_000})),
        ]
        for version, text in scenarios:
            plane = ControlPlane(self.root)
            try:
                plane.conn.execute(
                    "INSERT INTO config_revisions(revision,actor,command,created_at,summary) VALUES(?,?,?,?,?)",
                    (version, "secret.actor", "change", "2026-10-10T00:00:00Z", "TOPSECRET"),
                )
                plane.conn.execute("INSERT INTO revision_snapshots(revision,snapshot_json) VALUES(?,?)",
                                   (version, text))
                plane.conn.commit()
            finally:
                plane.close()
            with self.subTest(revision=version):
                with self.assertRaisesRegex(ControlPlaneError, "unavailable"):
                    self.report(1, version)

    def test_unknown_sections_and_inconsistent_revision_rejected(self):
        doc = yaml.safe_load(snapshot(8))
        doc["configurationBundle"]["secrets"] = [{"apiKey": "TOPSECRET"}]
        self.add_revision(8, yaml.safe_dump(doc))
        self.add_revision(9, snapshot(100))
        with self.assertRaisesRegex(ControlPlaneError, "unavailable"):
            self.report(1, 8)
        with self.assertRaisesRegex(ControlPlaneError, "unavailable"):
            self.report(1, 9)

    def test_yaml_python_tags_and_duplicate_mapping_keys_rejected(self):
        self.add_revision(10, "!!python/object/apply:os.system ['echo should-not-run']")
        self.add_revision(11,
            "configurationBundle:\n  context: server\n  context: server\n  sourceRevision: 11\n")
        for version in (10, 11):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ControlPlaneError, "unavailable"):
                    self.report(1, version)

    def test_invalid_revision_ids_and_order_do_not_touch_stored_snapshots(self):
        for a,b in [(0,2), (2,2), (3,2), ("1;DROP TABLE config_revisions",2),
                    (1,True), (1,9999999999999), (-1,2)]:
            with self.subTest(args=(a,b)):
                with self.assertRaises(ControlPlaneError):
                    self.report(a,b)

    def test_authoritative_history_snapshot_table_is_unchanged(self):
        plane = ControlPlane(self.root, read_only=True)
        try:
            before = [tuple(r) for r in plane.conn.execute(
                "SELECT revision,snapshot_json FROM revision_snapshots ORDER BY revision")]
        finally:
            plane.close()
        self.report()
        plane = ControlPlane(self.root, read_only=True)
        try:
            after = [tuple(r) for r in plane.conn.execute(
                "SELECT revision,snapshot_json FROM revision_snapshots ORDER BY revision")]
        finally:
            plane.close()
        self.assertEqual(before, after)

    def test_genuine_link_core_revision_writes_are_compatible(self):
        # Exercise the actual product exporter, not manually seeded snapshots.
        # All native writes are confined to this disposable test root.
        import drlink_v24 as v24
        with tempfile.TemporaryDirectory(prefix="pf12a-native-core-export-") as root:
            config = Path(root, "etc/drlink")
            config.mkdir(parents=True, exist_ok=True)
            (config / "config.json").write_text(
                '{"role":"server"}\\n', encoding="utf-8",
            )
            plane = ControlPlane(root)
            try:
                v24.set_network_object(
                    plane, "source-one", type="ip",
                    value="198.51.100.10", oneshot=True,
                )
                first = plane.current_revision()
                first_record = plane.revision_snapshot(first)
                self.assertEqual(
                    first_record["snapshot_format"],
                    "drlink-revision-configuration-v1",
                )
                v24.set_network_object(
                    plane, "source-two", type="ip",
                    value="198.51.100.11", oneshot=True,
                )
                second = plane.current_revision()
                self.assertGreater(second, first)
            finally:
                plane.close()
            result = compare_product_revisions(root, first, second)
            self.assertEqual(result["from_revision"], first)
            self.assertEqual(result["to_revision"], second)
            self.assertEqual(
                result["counts"]["from"]["network_objects"] + 1,
                result["counts"]["to"]["network_objects"],
            )
            self.assertFalse(result["rollback_preview"]["may_submit_to_product_authority"])
            self.assertNotIn("198.51.100.", json.dumps(result))

    def test_corrupt_authoritative_database_error_is_redacted(self):
        with mock.patch(
            "drlink_web_config_history.ControlPlane",
            side_effect=RuntimeError("SQL error token=TOPSECRET 192.0.2.15"),
        ):
            with self.assertRaises(ControlPlaneError) as raised:
                self.report()
        self.assertNotIn("TOPSECRET", str(raised.exception))
        self.assertNotIn("192.0.2.", str(raised.exception))

    def test_trusted_count_too_large_rejected(self):
        self.add_revision(12, snapshot(12, network_count=1025))
        with self.assertRaisesRegex(ControlPlaneError, "unavailable"):
            self.report(1,12)


if __name__ == "__main__":
    unittest.main()
