#!/usr/bin/env python3
"""Supporting unit checks for the read-only E2E lab preflight (not user E2E)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import e2e_lab_readiness as lab  # noqa: E402

HASH_A = "a" * 40
HASH_B = "b" * 40


def host(alias="frp-e2e-server", role="server", **extra):
    return {"ssh_alias": alias, "role": role, "required": True, **extra}


def unix_response(installed="NO", source=None, paths=(), active=False):
    lines = ["HOST=test-vm", 'ID="ubuntu"', 'VERSION_ID="24.04"',
             f"DRLINK_INSTALLED={installed}"]
    if source:
        lines.append("Source HEAD: " + source)
    lines.extend("STATE_PATH_PRESENT=" + p for p in paths)
    lines.append("UNIT_drlink-client.service=" + ("active" if active else "inactive"))
    return subprocess.CompletedProcess([], 0, "\n".join(lines), "")


class LabReadinessSupportingTests(unittest.TestCase):
    def test_valid_assigned_host_set_and_invalid_alias_fails_closed(self):
        self.assertFalse(lab.verify_manifest({"hosts": [host()]}))
        for alias in ("frp-e2e-linux114", "frp-e2e-macos",
                      "frp-e2e-server; touch /tmp/unsafe", "unknown-host"):
            self.assertTrue(lab.verify_manifest({"hosts": [host(alias)]}))

    def test_preinstall_requires_absent_product_and_state(self):
        ready = lab.classify_host(host(), unix_response(), HASH_A)
        self.assertEqual(ready["status"], "PASS")
        for result in (unix_response(paths=["/var/lib/drlink"]),
                       unix_response(active=True),
                       unix_response("YES", HASH_A)):
            bad = lab.classify_host(host(), result, HASH_A)
            self.assertEqual(bad["status"], "NOT_READY", bad)

    def test_exact_installed_head_only_passes_postinstall_phase(self):
        ready = lab.classify_host(host(), unix_response("YES", HASH_A), HASH_A,
                                  "INSTALLED_CANDIDATE")
        self.assertEqual(ready["status"], "PASS")
        mismatch = lab.classify_host(host(), unix_response("YES", HASH_B), HASH_A,
                                     "INSTALLED_CANDIDATE")
        self.assertEqual(mismatch["reason"], "STALE_INSTALLED_SOURCE_HEAD")
        self.assertEqual(mismatch["status"], "NOT_READY")
        missing = lab.classify_host(host(), unix_response(), HASH_A, "INSTALLED_CANDIDATE")
        self.assertEqual(missing["status"], "NOT_READY")

    def test_os_identity_conflict_cannot_pass(self):
        row = lab.classify_host(host(expected_os_id="rocky"), unix_response(), HASH_A)
        self.assertEqual(row["status"], "NOT_READY")
        self.assertEqual(row["reason"], "Unexpected assigned native OS identity")

    def test_windows_route_failure_is_tooling_not_product_bug(self):
        result = subprocess.CompletedProcess([], 255, "",
                                              "ssh: connect to host 127.0.0.1 port 2223: Connection refused")
        row = lab.classify_host(host("frp-e2e-windows", "native-agent"), result, HASH_A)
        self.assertEqual(row["ssh_error_class"], "CONNECTION_REFUSED")
        self.assertEqual(row["status"], "NOT_READY")

    def test_run_evidence_uses_immutable_run_scoped_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "durable"
            report = {"run_id": "fixed-run-001", "status": "NOT_READY"}
            destination = lab.write_run_evidence(root, report, [
                {"ssh_alias": "frp-e2e-server", "role": "server", "ssh_rc": 0,
                 "installed": "YES", "status": "NOT_READY",
                 "reason": "STALE_INSTALLED_SOURCE_HEAD"},
            ])
            self.assertEqual(destination.name, "fixed-run-001")
            self.assertTrue((destination / "PREFLIGHT_STATUS.json").is_file())
            self.assertTrue((destination / "CLEANROOM_LEDGER.tsv").is_file())
            with self.assertRaises(FileExistsError):
                lab.write_run_evidence(root, report, [])
            self.assertEqual(json.loads(
                (destination / "PREFLIGHT_STATUS.json").read_text()
            )["status"], "NOT_READY")

    def test_approval_gates_are_explicit_and_never_inferred(self):
        names = ["dedicated_disposable_lab", "server_cleanup_B014_resolved",
                 "protected_backup_verified", "qualified_immutable_bundle",
                 "trusted_mcp_tls_verified", "actual_owner_oauth_ui_accepted",
                 "separate_ai_personas_ready", "prospective_process_registry_ready",
                 "native_platform_security_denials_resolved"]
        base = {"expected_provenance_head": HASH_A,
                "approvals": {key: True for key in names}}
        ready = {"ssh_alias": "frp-e2e-server", "required": True, "status": "PASS",
                 "reason": "clean"}
        self.assertEqual(lab.evaluate(base, [ready], HASH_A)["status"], "GO")
        base["approvals"]["server_cleanup_B014_resolved"] = False
        outcome = lab.evaluate(base, [ready], HASH_A)
        self.assertEqual(outcome["status"], "NOT_READY")
        self.assertIn("SERVER_CLEANUP_B014", outcome["not_ready_gate_ids"])
        self.assertEqual(lab.evaluate(base, [ready], HASH_B)["status"], "NOT_READY")


if __name__ == "__main__":
    unittest.main()
