#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_agent_lifecycle import process_management_jobs_once
from drlink_control_plane import ControlPlane
import drlink_mgmt_sync as mgmt
import drlink_v24 as v24
from drlink_v30_jobs import ManagementJobEngine, QUEUED, SUCCEEDED
import frp_mgmt_auth as MGMT

MACHINE_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
MACHINE_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def write_identity(root: Path, machine_id: str, hostname: str):
    frp = root / "etc/frp"
    frp.mkdir(parents=True, exist_ok=True)
    (frp / "client-state.json").write_text(
        json.dumps(
            {"machine_id": machine_id, "hostname": hostname, "label": hostname},
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    (frp / "frpc.toml").write_text("[common]\n", encoding="utf-8")
    key = frp / "client-identity.key"
    pub = frp / "client-identity.pub"
    MGMT.generate_keypair(key, pub)
    os.chmod(key, 0o600)
    mac = MGMT.new_mac_key()
    mac_path = frp / "client-identity.mac"
    mac_path.write_text(mac, encoding="utf-8")
    os.chmod(mac_path, 0o600)
    return pub.read_text(encoding="utf-8"), mac


class V30ManagementJobTransportTests(unittest.TestCase):
    def setUp(self):
        self.server_tmp = tempfile.mkdtemp(prefix="drlink-v30-job-srv-")
        self.agent_tmp = tempfile.mkdtemp(prefix="drlink-v30-job-agent-")
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_CONFIRM"] = "yes"

        Path(self.server_tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.server_tmp, "etc/drlink/config.json").write_text(
            '{"role":"server"}\n', encoding="utf-8"
        )
        Path(self.agent_tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.agent_tmp, "etc/drlink/config.json").write_text(
            '{"role":"client"}\n', encoding="utf-8"
        )

        pub_a, mac_a = write_identity(Path(self.agent_tmp), MACHINE_A, "agent-a")
        self.server = ControlPlane(self.server_tmp)
        v24.ensure_v2_schema(self.server.conn)
        v24.set_service_object(self.server, "ssh", type="tcp", port=22, oneshot=True)
        self.server.upsert_client(MACHINE_A, label="agent-a", hostname="agent-a")
        self.server.upsert_client(MACHINE_B, label="agent-b", hostname="agent-b")

        self.agent = ControlPlane(self.agent_tmp)
        v24.ensure_v2_schema(self.agent.conn)
        v24.set_service_object(self.agent, "ssh", type="tcp", port=22, oneshot=True)
        self.agent.close()

        self.verifier = mgmt.InMemoryMgmtVerifier()
        self.verifier.enroll(MACHINE_A, pub_a, mac_key=mac_a, hostname="agent-a")
        self.httpd, self.base, _ = mgmt.start_mgmt_server(
            self.server, verifier=self.verifier
        )
        os.environ["DRLINK_MGMT_URL"] = self.base
        Path(self.agent_tmp, "etc/frp/server-endpoint.json").write_text(
            json.dumps({"mgmt_url": self.base}) + "\n", encoding="utf-8"
        )

    def tearDown(self):
        mgmt.stop_mgmt_server(self.httpd)
        self.server.close()
        for key in ("DRLINK_SKIP_ACTIVATION", "DRLINK_CONFIRM", "DRLINK_MGMT_URL"):
            os.environ.pop(key, None)

    def test_signed_ai_claim_rejects_bad_limit_before_agent_job_claim(self):
        from unittest import mock

        endpoint = self.base + "/v1/ai-jobs/claim"
        invalid = (0, -1, True, False, 1.5, "2", None, [])
        with mock.patch.object(
            self.server, "claim_ai_jobs",
            side_effect=AssertionError("bad signed limit reached Core claim"),
        ) as core_claim:
            for value in invalid:
                with self.subTest(limit=value):
                    with self.assertRaises(mgmt.MgmtSyncError):
                        mgmt._request_json(
                            "POST", endpoint, {"limit": value}, root=self.agent_tmp
                        )
            core_claim.assert_not_called()

        with mock.patch.object(
            self.server, "claim_ai_jobs", return_value=[],
        ) as core_claim:
            for payload, expected in (({}, 4), ({"limit": 99}, 16), ({"limit": 2}, 2)):
                with self.subTest(payload=payload):
                    response = mgmt._request_json(
                        "POST", endpoint, payload, root=self.agent_tmp
                    )
                    self.assertEqual(response, {"jobs": []})
                    self.assertEqual(core_claim.call_args.args, (MACHINE_A, expected))

    def test_signed_agent_claim_skips_unqualified_rollout_but_keeps_doctor_available(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            rollout = engine.enqueue_rollout(
                targets=(MACHINE_A,), requested_by="web:admin", wave_size=1,
                artifact={"version": "3.0.0-rc.1", "source_ref": "a" * 40,
                          "sha256": "b" * 64},
            )
            doctor = engine.enqueue(
                job_type="doctor", targets=(MACHINE_A,), requested_by="web:admin"
            )
            response = mgmt.claim_management_jobs_on_server(
                root=self.agent_tmp, limit=4
            )
            self.assertEqual(
                [claim["job_id"] for claim in response["jobs"]], [doctor["id"]]
            )
            self.assertEqual(engine.get(rollout["id"])["status"], QUEUED)
            self.assertEqual(
                engine.get(rollout["id"])["targets"][0]["status"], QUEUED
            )
            self.assertEqual(engine.get(doctor["id"])["status"], "RUNNING")
        finally:
            engine.close()

    def test_signed_management_claim_rejects_nonpositive_or_coerced_limits(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            job = engine.enqueue(
                job_type="doctor", targets=[MACHINE_A],
                requested_by="web:admin",
            )
            for invalid in (0, -1, True, False, "1", 1.5, None, []):
                with self.subTest(limit=invalid):
                    with self.assertRaises(mgmt.MgmtSyncError):
                        mgmt._request_json(
                            "POST", self.base + "/v1/management-jobs/claim",
                            {"limit": invalid}, root=self.agent_tmp,
                        )
                    # Invalid signed requests cannot acquire or mutate a Job.
                    self.assertEqual(engine.get(job["id"])["status"], QUEUED)
            response = mgmt.claim_management_jobs_on_server(
                root=self.agent_tmp, limit=1,
            )
            self.assertEqual([x["job_id"] for x in response["jobs"]], [job["id"]])
        finally:
            engine.close()

    def test_agent_cannot_report_success_for_a_legacy_rollout_claim(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            rollout = engine.enqueue_rollout(
                targets=(MACHINE_A,), requested_by="web:admin", wave_size=1,
                artifact={"version": "3.0.0-rc.1", "source_ref": "a" * 40,
                          "sha256": "b" * 64},
            )
            # Simulate an in-flight claim issued by an older server before
            # the unqualified Agent transport was excluded.
            claim = engine.claim_targets(worker_id="legacy-worker", limit=1)[0]
            self.assertEqual(claim["job_id"], rollout["id"])
            with self.assertRaises(mgmt.MgmtSyncError):
                mgmt.complete_management_job_on_server(
                    root=self.agent_tmp, job_id=rollout["id"],
                    claim_token=claim["claim_token"], status="SUCCEEDED",
                    result={"claimed_success": True},
                )
            self.assertEqual(engine.get(rollout["id"])["status"], "RUNNING")
            self.assertEqual(
                engine.get(rollout["id"])["targets"][0]["status"], "RUNNING"
            )
        finally:
            engine.close()

    def test_signed_core_rejects_explicit_non_object_success_results(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            for invalid in (None, [], "", 0, False):
                with self.subTest(value=invalid):
                    job = engine.enqueue(
                        job_type="doctor", targets=[MACHINE_A],
                        requested_by="web:admin",
                    )
                    claim = mgmt.claim_management_jobs_on_server(
                        root=self.agent_tmp, limit=1
                    )["jobs"][0]
                    self.assertEqual(claim["job_id"], job["id"])
                    # Send the exact signed JSON request, without the Agent's
                    # client-side dict coercion hiding invalid wire values.
                    with self.assertRaises(mgmt.MgmtSyncError):
                        mgmt._request_json(
                            "POST", self.base + "/v1/management-jobs/complete",
                            {"id": claim["job_id"], "claim_token": claim["claim_token"],
                             "status": "SUCCEEDED", "result": invalid},
                            root=self.agent_tmp,
                        )
                    self.assertEqual(engine.get(job["id"])["status"], "RUNNING")
        finally:
            engine.close()

    def test_signed_core_rejects_untrusted_nested_diagnostic_receipts(self):
        # A signed Host is authenticated, but raw nested Agent messages must
        # not cross into Web-visible Core Job history as trusted evidence.
        engine = ManagementJobEngine(self.server_tmp)
        secret = "PRIVATE_AGENT_MESSAGE_DO_NOT_PERSIST"
        cases = (
            ("doctor", {}, {"operation": "doctor", "findings": [
                {"id": "pki", "status": "WARN", "message": secret}]}),
            ("doctor", {}, {"operation": "doctor", "findings": [
                {"id": "pki", "status": "WARN", "message": "",
                 "raw_private": secret}]}),
            ("doctor", {}, {"operation": "doctor", "findings": secret}),
            ("refresh", {}, {"operation": "refresh", "runtime_error": secret}),
            ("refresh", {}, {"operation": "refresh", "affected": [
                {"name": "ssh", "reason": secret}]}),
            ("refresh", {}, {"operation": "refresh", "affected": [
                {"name": "ssh", "reason": "", "raw_private": secret}]}),
            ("remote-service-set",
             {"name": "ssh-access", "destination": "this-host",
              "service": "ssh", "enabled": True},
             {"operation": "remote-service-set", "name": "ssh-access",
              "runtime_status": "HEALTHY", "reason": secret}),
        )
        try:
            for kind, payload, result in cases:
                with self.subTest(kind=kind, result=result):
                    job = engine.enqueue(
                        job_type=kind, targets=[MACHINE_A],
                        requested_by="web:admin", payload=payload,
                    )
                    claim = mgmt.claim_management_jobs_on_server(
                        root=self.agent_tmp, limit=1
                    )["jobs"][0]
                    self.assertEqual(claim["job_id"], job["id"])
                    with self.assertRaises(mgmt.MgmtSyncError):
                        mgmt._request_json(
                            "POST", self.base + "/v1/management-jobs/complete",
                            {"id": job["id"], "claim_token": claim["claim_token"],
                             "status": "SUCCEEDED", "result": result},
                            root=self.agent_tmp,
                        )
                    current = engine.get(job["id"])
                    self.assertEqual(current["status"], "RUNNING")
                    self.assertNotIn(secret, json.dumps(current))
        finally:
            engine.close()

    def test_core_diagnostic_success_requires_matching_claimed_job_type(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            for kind in ("doctor", "refresh", "version-check", "support-bundle"):
                with self.subTest(kind=kind):
                    job = engine.enqueue(
                        job_type=kind, targets=[MACHINE_A],
                        requested_by="web:admin",
                    )
                    claim = mgmt.claim_management_jobs_on_server(
                        root=self.agent_tmp, limit=1
                    )["jobs"][0]
                    self.assertEqual(claim["job_id"], job["id"])
                    for invalid in (
                        {}, {"operation": "remote-service-delete"},
                        {"operation": kind, "unreviewed_metadata": "raw"},
                    ):
                        with self.subTest(kind=kind, result=invalid):
                            with self.assertRaises(mgmt.MgmtSyncError):
                                mgmt._request_json(
                                    "POST", self.base + "/v1/management-jobs/complete",
                                    {"id": claim["job_id"],
                                     "claim_token": claim["claim_token"],
                                     "status": "SUCCEEDED", "result": invalid},
                                    root=self.agent_tmp,
                                )
                            self.assertEqual(engine.get(job["id"])["status"], "RUNNING")
                    # Support Bundle is evidence-bearing: unlike the other
                    # diagnostics, a bare operation name cannot prove success.
                    receipt = {"operation": kind}
                    if kind == "support-bundle":
                        receipt.update({
                            "artifact_path": "/var/lib/drlink/support-bundles/test.tar.gz",
                            "size": 1024, "sha256": "a" * 64,
                            "sanitized": True, "section_count": 3,
                            "skipped_count": 0, "role": "client",
                        })
                    elif kind == "version-check":
                        receipt.update({
                            "project_version": "3.0.0",
                            "relay_engine_version": "0.61.1",
                            "release_channel": "development",
                            "source_ref": "main", "source_head": "a" * 40,
                            "target_project_version": "3.0.1",
                            "target_relay_engine_version": "0.61.1",
                            "target_release_channel": "development",
                            "product_update_available": True,
                            "relay_engine_update_available": False,
                        })
                    elif kind == "doctor":
                        receipt.update({
                            "overall": "PASS", "exit_code": 0,
                            "check_count": 1, "counts": {"PASS": 1},
                            "findings": [], "network_probe_performed": False,
                        })
                    elif kind == "refresh":
                        receipt.update({
                            "status": "SYNCHRONIZED",
                            "updated": 1, "projected": 1,
                            "affected": [], "runtime_error": "",
                        })
                    reply = mgmt.complete_management_job_on_server(
                        root=self.agent_tmp, job_id=job["id"],
                        claim_token=claim["claim_token"], status="SUCCEEDED",
                        result=receipt,
                    )
                    self.assertIs(reply["ok"], True)
                    self.assertEqual(engine.get(job["id"])["status"], SUCCEEDED)
        finally:
            engine.close()

    def test_signed_diagnostic_success_requires_native_evidence_fields(self):
        canonical = {
            "doctor": {
                "operation": "doctor", "overall": "PASS", "exit_code": 0,
                "check_count": 1, "counts": {"PASS": 1}, "findings": [],
                "network_probe_performed": False,
            },
            "refresh": {
                "operation": "refresh", "status": "SYNCHRONIZED",
                "updated": 1, "projected": 1, "affected": [],
                "runtime_error": "",
            },
        }
        invalid = {
            "doctor": (
                {"operation": "doctor"},
                {**canonical["doctor"], "overall": "HEALTHY"},
                {**canonical["doctor"], "exit_code": True},
                {**canonical["doctor"], "check_count": -1},
                {**canonical["doctor"], "counts": {"PASS": 2}},
                {**canonical["doctor"], "findings": None},
                {**canonical["doctor"], "network_probe_performed": True},
                {**canonical["doctor"], "overall": "secrets\nhidden"},
                {**canonical["doctor"], "counts": {"FAIL": 1}},
                {**canonical["doctor"], "overall": "PASS_WITH_WARNINGS"},
                {**canonical["doctor"], "overall": "FAIL", "exit_code": 1},
                {**canonical["doctor"], "overall": "ERROR"},
                {**canonical["doctor"], "exit_code": 2},
                {**canonical["doctor"], "overall": "FAIL",
                 "counts": {"FAIL": 1}},
                {**canonical["doctor"], "overall": "PASS_WITH_WARNINGS",
                 "counts": {"WARN": 1}, "exit_code": 1},
            ),
            "refresh": (
                {"operation": "refresh"},
                {**canonical["refresh"], "status": "HEALTHY"},
                {**canonical["refresh"], "updated": True},
                {**canonical["refresh"], "projected": -1},
                {**canonical["refresh"], "affected": None},
                {**canonical["refresh"], "runtime_error": "secret-data"},
                {**canonical["refresh"], "updated": 1000000000},
                {key: value for key, value in canonical["refresh"].items()
                 if key != "status"},
            ),
        }
        engine = ManagementJobEngine(self.server_tmp)
        try:
            for kind, cases in invalid.items():
                for result in cases:
                    with self.subTest(kind=kind, result=str(result)[:90]):
                        job = engine.enqueue(
                            job_type=kind, targets=[MACHINE_A],
                            requested_by="web:admin",
                        )
                        claim = mgmt.claim_management_jobs_on_server(
                            root=self.agent_tmp, limit=1,
                        )["jobs"][0]
                        self.assertEqual(claim["job_id"], job["id"])
                        with self.assertRaises(mgmt.MgmtSyncError):
                            mgmt._request_json(
                                "POST", self.base + "/v1/management-jobs/complete",
                                {"id": job["id"],
                                 "claim_token": claim["claim_token"],
                                 "status": "SUCCEEDED", "result": result},
                                root=self.agent_tmp,
                            )
                        self.assertEqual(engine.get(job["id"])["status"], "RUNNING")
            for kind, receipt in canonical.items():
                job = engine.enqueue(
                    job_type=kind, targets=[MACHINE_A],
                    requested_by="web:admin",
                )
                claim = mgmt.claim_management_jobs_on_server(
                    root=self.agent_tmp, limit=1,
                )["jobs"][0]
                reply = mgmt.complete_management_job_on_server(
                    root=self.agent_tmp, job_id=job["id"],
                    claim_token=claim["claim_token"], status="SUCCEEDED",
                    result=receipt,
                )
                self.assertTrue(reply["ok"])
                self.assertEqual(engine.get(job["id"])["status"], SUCCEEDED)
        finally:
            engine.close()

    def test_version_check_success_requires_consistent_bounded_receipt(self):
        # Native Agent emits a complete version comparison. A signed Host
        # reporting just an operation name is not version evidence.
        canonical = {
            "operation": "version-check", "project_version": "3.0.0",
            "relay_engine_version": "0.61.1", "release_channel": "development",
            "source_ref": "main", "source_head": "a" * 40,
            "target_project_version": "3.0.1",
            "target_relay_engine_version": "0.61.1",
            "target_release_channel": "development",
            "product_update_available": True,
            "relay_engine_update_available": False,
        }
        invalid = (
            {"operation": "version-check"},
            {key: value for key, value in canonical.items()
             if key != "project_version"},
            {**canonical, "project_version": ""},
            {**canonical, "relay_engine_version": {}},
            {**canonical, "source_ref": "a" * 400},
            {**canonical, "source_head": "secret\ninjected"},
            {**canonical, "release_channel": 3},
            {**canonical, "target_project_version": "3.0\nsecret"},
            {**canonical, "target_release_channel": ""},
            {**canonical, "product_update_available": 1},
            {**canonical, "relay_engine_update_available": "false"},
            {**canonical, "product_update_available": False},
            {**canonical, "relay_engine_update_available": True},
            {**canonical, "project_version": "unknown",
             "product_update_available": True},
        )
        engine = ManagementJobEngine(self.server_tmp)
        try:
            for result in invalid:
                with self.subTest(result=str(result)[:80]):
                    job = engine.enqueue(
                        job_type="version-check", targets=[MACHINE_A],
                        requested_by="web:admin",
                    )
                    claim = mgmt.claim_management_jobs_on_server(
                        root=self.agent_tmp, limit=1,
                    )["jobs"][0]
                    self.assertEqual(claim["job_id"], job["id"])
                    with self.assertRaises(mgmt.MgmtSyncError):
                        mgmt._request_json(
                            "POST", self.base + "/v1/management-jobs/complete",
                            {"id": job["id"], "claim_token": claim["claim_token"],
                             "status": "SUCCEEDED", "result": result},
                            root=self.agent_tmp,
                        )
                    self.assertEqual(engine.get(job["id"])["status"], "RUNNING")
            healthy = engine.enqueue(
                job_type="version-check", targets=[MACHINE_A],
                requested_by="web:admin",
            )
            claim = mgmt.claim_management_jobs_on_server(
                root=self.agent_tmp, limit=1,
            )["jobs"][0]
            reply = mgmt.complete_management_job_on_server(
                root=self.agent_tmp, job_id=healthy["id"],
                claim_token=claim["claim_token"], status="SUCCEEDED",
                result=canonical,
            )
            self.assertTrue(reply["ok"])
            self.assertEqual(engine.get(healthy["id"])["status"], SUCCEEDED)
        finally:
            engine.close()

    def test_support_bundle_success_requires_bounded_artifact_receipt(self):
        # A signed Agent identity does not prove a support archive exists.
        # A bare operation name must not become a Core Job SUCCESS.
        canonical = {
            "operation": "support-bundle",
            "artifact_path": "/var/lib/drlink/support-bundle-job.tar.gz",
            "size": 1024, "sha256": "a" * 64, "sanitized": True,
            "section_count": 3, "skipped_count": 0, "role": "client",
        }
        invalid = (
            {"operation": "support-bundle"},
            {**canonical, "artifact_path": ""},
            {**canonical, "artifact_path": "relative/archive.tar.gz"},
            {**canonical, "artifact_path": "/tmp/invalid\narchive.tar.gz"},
            {**canonical, "size": 0},
            {**canonical, "size": True},
            {**canonical, "sha256": "a" * 63},
            {**canonical, "sha256": "z" * 64},
            {**canonical, "sanitized": False},
            {**canonical, "sanitized": "true"},
            {**canonical, "section_count": -1},
            {**canonical, "skipped_count": "0"},
            {**canonical, "role": ["client"]},
        )
        engine = ManagementJobEngine(self.server_tmp)
        try:
            for result in invalid:
                with self.subTest(result=result):
                    job = engine.enqueue(
                        job_type="support-bundle", targets=[MACHINE_A],
                        requested_by="web:admin",
                    )
                    claim = mgmt.claim_management_jobs_on_server(
                        root=self.agent_tmp, limit=1,
                    )["jobs"][0]
                    self.assertEqual(claim["job_id"], job["id"])
                    with self.assertRaises(mgmt.MgmtSyncError):
                        mgmt._request_json(
                            "POST", self.base + "/v1/management-jobs/complete",
                            {"id": job["id"], "claim_token": claim["claim_token"],
                             "status": "SUCCEEDED", "result": result},
                            root=self.agent_tmp,
                        )
                    self.assertEqual(engine.get(job["id"])["status"], "RUNNING")
            healthy = engine.enqueue(
                job_type="support-bundle", targets=[MACHINE_A],
                requested_by="web:admin",
            )
            claim = mgmt.claim_management_jobs_on_server(
                root=self.agent_tmp, limit=1,
            )["jobs"][0]
            self.assertEqual(claim["job_id"], healthy["id"])
            reply = mgmt.complete_management_job_on_server(
                root=self.agent_tmp, job_id=healthy["id"],
                claim_token=claim["claim_token"],
                status="SUCCEEDED", result=canonical,
            )
            self.assertTrue(reply["ok"])
            self.assertEqual(engine.get(healthy["id"])["status"], SUCCEEDED)
        finally:
            engine.close()

    def test_core_remote_service_success_requires_exact_claimed_operation_and_name(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            cases = [
                ("remote-service-set",
                 {"name": "ssh-access", "destination": "this-host",
                  "service": "ssh", "enabled": True},
                 {"operation": "remote-service-set", "name": "ssh-access",
                  "runtime_status": "HEALTHY", "endpoint": "127.0.0.1:6022"}),
                ("remote-service-delete", {"name": "ssh-access"},
                 {"operation": "remote-service-delete", "name": "ssh-access",
                  "status": "DELETED", "runtime_verified": False}),
            ]
            for kind, payload, valid in cases:
                with self.subTest(kind=kind):
                    job = engine.enqueue(
                        job_type=kind, targets=[MACHINE_A],
                        requested_by="web:admin", resource_type="remote-service",
                        resource_ref="ssh-access", payload=payload,
                    )
                    claim = mgmt.claim_management_jobs_on_server(
                        root=self.agent_tmp, limit=1
                    )["jobs"][0]
                    self.assertEqual(claim["job_id"], job["id"])
                    invalid_results = [
                        {}, {**valid, "operation": "doctor"},
                        {**valid, "name": "another-service"},
                        {**valid, "unreviewed_metadata": "raw"},
                    ]
                    if kind == "remote-service-set":
                        invalid_results.extend([
                            {**valid, "runtime_status": None},
                            {**valid, "runtime_status": "UNKNOWN"},
                            {**valid, "runtime_status": True},
                        ])
                    else:
                        invalid_results.extend([
                            {**valid, "runtime_verified": True},
                            {**valid, "runtime_verified": None},
                            {key: value for key, value in valid.items()
                             if key != "runtime_verified"},
                        ])
                    for result in invalid_results:
                        with self.subTest(kind=kind, result=result):
                            with self.assertRaises(mgmt.MgmtSyncError):
                                mgmt._request_json(
                                    "POST", self.base + "/v1/management-jobs/complete",
                                    {"id": claim["job_id"],
                                     "claim_token": claim["claim_token"],
                                     "status": "SUCCEEDED", "result": result},
                                    root=self.agent_tmp,
                                )
                            self.assertEqual(engine.get(job["id"])["status"], "RUNNING")
                    reply = mgmt.complete_management_job_on_server(
                        root=self.agent_tmp, job_id=job["id"],
                        claim_token=claim["claim_token"], status="SUCCEEDED",
                        result=valid,
                    )
                    self.assertIs(reply["ok"], True)
                    self.assertEqual(engine.get(job["id"])["status"], SUCCEEDED)
        finally:
            engine.close()

    def test_core_signed_completion_never_persists_untrusted_agent_error_text(self):
        engine = ManagementJobEngine(self.server_tmp)
        secret = "Bearer fixture-only-untrusted-signed-completion"
        try:
            job = engine.enqueue(
                job_type="doctor", targets=[MACHINE_A], requested_by="web:admin"
            )
            claims = mgmt.claim_management_jobs_on_server(root=self.agent_tmp, limit=1)
            self.assertEqual(len(claims["jobs"]), 1)
            claim = claims["jobs"][0]
            self.assertEqual(claim["job_id"], job["id"])
            mgmt.complete_management_job_on_server(
                root=self.agent_tmp, job_id=claim["job_id"],
                claim_token=claim["claim_token"], status="FAILED",
                result={"untrusted_failure_payload": secret},
                error="Untrusted exception: " + secret,
            )
            final = engine.get(job["id"])
            self.assertEqual(final["status"], "FAILED")
            self.assertEqual(final["targets"][0]["result"], {})
            self.assertEqual(final["targets"][0]["error"],
                             "AGENT_JOB_EXECUTION_FAILED")
            self.assertEqual(final["last_error"], "AGENT_JOB_EXECUTION_FAILED")
            self.assertNotIn(secret, json.dumps(final))
        finally:
            engine.close()

    def test_core_ignores_untrusted_error_text_on_signed_success(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            job = engine.enqueue(
                job_type="doctor", targets=[MACHINE_A], requested_by="web:admin"
            )
            claim = mgmt.claim_management_jobs_on_server(
                root=self.agent_tmp, limit=1
            )["jobs"][0]
            mgmt.complete_management_job_on_server(
                root=self.agent_tmp, job_id=claim["job_id"],
                claim_token=claim["claim_token"], status="SUCCEEDED",
                result={
                    "operation": "doctor", "overall": "PASS", "exit_code": 0,
                    "check_count": 1, "counts": {"PASS": 1}, "findings": [],
                    "network_probe_performed": False,
                }, error="Bearer untrusted-success-string",
            )
            final = engine.get(job["id"])
            self.assertEqual(final["status"], "SUCCEEDED")
            self.assertEqual(final["targets"][0]["error"], "")
            self.assertNotIn("untrusted-success-string", json.dumps(final))
        finally:
            engine.close()

    def test_signed_agent_claim_is_target_bound_and_cross_target_completion_fails(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            job_a = engine.enqueue(
                job_type="doctor",
                targets=[MACHINE_A],
                requested_by="web:admin",
            )
            job_b = engine.enqueue(
                job_type="doctor",
                targets=[MACHINE_B],
                requested_by="web:admin",
            )
            claimed = mgmt.claim_management_jobs_on_server(
                root=self.agent_tmp, limit=4
            )
            self.assertEqual(len(claimed["jobs"]), 1)
            self.assertEqual(claimed["jobs"][0]["job_id"], job_a["id"])
            self.assertEqual(claimed["jobs"][0]["target_id"], MACHINE_A)

            b_claim = engine.claim_targets_for_target(
                target_id=MACHINE_B, worker_id="agent-b", limit=1
            )[0]
            with self.assertRaises(mgmt.MgmtSyncError):
                mgmt.complete_management_job_on_server(
                    root=self.agent_tmp,
                    job_id=job_b["id"],
                    claim_token=b_claim["claim_token"],
                    status="SUCCEEDED",
                    result={"forbidden": True},
                )
            self.assertNotEqual(engine.get(job_b["id"])["status"], SUCCEEDED)
        finally:
            engine.close()

    def test_safe_diagnostic_jobs_execute_on_agent_and_return_bounded_results(self):
        Path(self.agent_tmp, "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\n"
            "FRP_VERSION=0.61.1\n"
            "RELEASE_CHANNEL=dev\n"
            "SOURCE_REF=feature/v3.0-drl3-0\n"
            "SOURCE_HEAD=0123456789abcdef\n",
            encoding="utf-8",
        )
        engine = ManagementJobEngine(self.server_tmp)
        try:
            jobs = {}
            for kind in ("doctor", "refresh", "version-check", "support-bundle"):
                payload = {}
                if kind == "version-check":
                    payload = {
                        "target_project_version": "3.0.1",
                        "target_relay_engine_version": "0.61.1",
                        "target_release_channel": "dev",
                    }
                jobs[kind] = engine.enqueue(
                    job_type=kind,
                    targets=[MACHINE_A],
                    requested_by="web:admin",
                    resource_type="managed-host",
                    resource_ref=MACHINE_A,
                    payload=payload,
                )
            result = process_management_jobs_once(self.agent_tmp, limit=4)
            self.assertEqual(result, {"processed": 4, "failed": 0})

            doctor = engine.get(jobs["doctor"]["id"])
            self.assertEqual(doctor["status"], SUCCEEDED)
            doctor_result = doctor["targets"][0]["result"]
            self.assertEqual(doctor_result["operation"], "doctor")
            self.assertFalse(doctor_result["network_probe_performed"])
            self.assertLessEqual(len(doctor_result["findings"]), 20)
            self.assertLess(
                len(json.dumps(doctor_result, sort_keys=True).encode("utf-8")),
                16 * 1024,
            )

            refresh = engine.get(jobs["refresh"]["id"])
            self.assertEqual(refresh["status"], SUCCEEDED)
            refresh_result = refresh["targets"][0]["result"]
            self.assertEqual(refresh_result["operation"], "refresh")
            self.assertIn(
                refresh_result["status"],
                ("SYNCHRONIZED", "DEGRADED", "OFFLINE"),
            )
            self.assertLessEqual(len(refresh_result["affected"]), 20)

            version = engine.get(jobs["version-check"]["id"])
            self.assertEqual(version["status"], SUCCEEDED)
            version_result = version["targets"][0]["result"]
            self.assertEqual(version_result["operation"], "version-check")
            self.assertEqual(version_result["project_version"], "3.0.0")
            self.assertEqual(version_result["relay_engine_version"], "0.61.1")
            self.assertEqual(version_result["target_project_version"], "3.0.1")
            self.assertEqual(version_result["target_relay_engine_version"], "0.61.1")
            self.assertTrue(version_result["product_update_available"])
            self.assertFalse(version_result["relay_engine_update_available"])
            self.assertNotIn("token", json.dumps(version_result).lower())

            support = engine.get(jobs["support-bundle"]["id"])
            self.assertEqual(support["status"], SUCCEEDED)
            support_result = support["targets"][0]["result"]
            self.assertEqual(support_result["operation"], "support-bundle")
            self.assertTrue(support_result["sanitized"])
            self.assertTrue(
                support_result["artifact_path"].startswith(
                    "/var/lib/drlink/support-bundles/"
                )
            )
            self.assertGreater(support_result["size"], 0)
            self.assertEqual(len(support_result["sha256"]), 64)
            artifact = Path(
                self.agent_tmp, support_result["artifact_path"].lstrip("/")
            )
            self.assertTrue(artifact.is_file())
            self.assertNotIn("sections", support_result)

        finally:
            engine.close()

    def test_signed_agent_failure_persists_only_safe_core_job_error(self):
        from unittest import mock
        engine = ManagementJobEngine(self.server_tmp)
        secret = "Bearer fixture-only-signed-job-credential"
        try:
            job = engine.enqueue(
                job_type="remote-service-set",
                targets=[MACHINE_A],
                requested_by="web:admin",
                resource_type="remote-service",
                resource_ref="ssh-access",
                payload={"name": "ssh-access", "destination": "this-host",
                         "service": "ssh", "enabled": True},
            )
            with mock.patch(
                "drlink_agent_lifecycle._execute_management_job",
                side_effect=ValueError("remote failure with " + secret),
            ):
                self.assertEqual(
                    process_management_jobs_once(self.agent_tmp, limit=1),
                    {"processed": 1, "failed": 1},
                )
            final = engine.get(job["id"])
            self.assertEqual(final["status"], "FAILED")
            self.assertEqual(final["targets"][0]["status"], "FAILED")
            self.assertEqual(final["targets"][0]["error"],
                             "AGENT_JOB_EXECUTION_FAILED")
            self.assertEqual(final["last_error"], "AGENT_JOB_EXECUTION_FAILED")
            self.assertNotIn(secret, json.dumps(final))
        finally:
            engine.close()

    def test_remote_service_job_executes_on_agent_and_completes_truthfully(self):
        engine = ManagementJobEngine(self.server_tmp)
        try:
            job = engine.enqueue(
                job_type="remote-service-set",
                targets=[MACHINE_A],
                requested_by="web:admin",
                resource_type="remote-service",
                resource_ref="ssh-access",
                payload={
                    "name": "ssh-access",
                    "destination": "this-host",
                    "service": "ssh",
                    "enabled": True,
                },
                timeout_seconds=120,
            )
            result = process_management_jobs_once(self.agent_tmp, limit=4)
            self.assertEqual(result, {"processed": 1, "failed": 0})

            final = engine.get(job["id"])
            self.assertEqual(final["status"], SUCCEEDED)
            target = final["targets"][0]
            self.assertEqual(target["status"], SUCCEEDED)
            self.assertEqual(target["result"]["operation"], "remote-service-set")
            self.assertNotEqual(target["result"]["runtime_status"], "UNKNOWN")

            agent = ControlPlane(self.agent_tmp)
            try:
                row = agent.conn.execute(
                    "SELECT name,status FROM agent_remote_services WHERE name=?",
                    ("ssh-access",),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertIn(str(row["status"]), ("HEALTHY", "DEGRADED"))
            finally:
                agent.close()

            server_row = self.server.conn.execute(
                "SELECT name FROM published_services WHERE client_id=? AND name=? "
                "AND released=0",
                (MACHINE_A, "ssh-access"),
            ).fetchone()
            self.assertIsNotNone(server_row)

            # The same signed Agent path must verify real local deletion, not
            # a synthetic "DELETED" status lacking an operation receipt.
            deletion = engine.enqueue(
                job_type="remote-service-delete",
                targets=[MACHINE_A],
                requested_by="web:admin",
                resource_type="remote-service",
                resource_ref="ssh-access",
                payload={"name": "ssh-access"},
            )
            self.assertEqual(
                process_management_jobs_once(self.agent_tmp, limit=1),
                {"processed": 1, "failed": 0},
            )
            deleted_job = engine.get(deletion["id"])
            self.assertEqual(deleted_job["status"], SUCCEEDED)
            receipt = deleted_job["targets"][0]["result"]
            self.assertEqual(receipt["operation"], "remote-service-delete")
            self.assertEqual(receipt["name"], "ssh-access")
            self.assertEqual(receipt["status"], "DELETED")
            self.assertIs(receipt["runtime_verified"], False)
            agent_after = ControlPlane(self.agent_tmp)
            try:
                row = agent_after.conn.execute(
                    "SELECT name FROM agent_remote_services WHERE name=?",
                    ("ssh-access",),
                ).fetchone()
                self.assertIsNone(row)
            finally:
                agent_after.close()
        finally:
            engine.close()


    def test_agent_remote_service_jobs_require_matching_local_mutation_receipts(self):
        from unittest import mock
        from drlink_agent_lifecycle import _execute_management_job

        set_claim = {
            "job_type": "remote-service-set",
            "payload": {
                "name": "ssh-access", "destination": "this-host",
                "service": "ssh", "enabled": True,
            },
        }
        delete_claim = {
            "job_type": "remote-service-delete",
            "payload": {"name": "ssh-access"},
        }
        entity = {
            "type": "remote-service", "id": "ssh-access", "name": "ssh-access",
        }
        valid_set = {
            "operation": "set", "entity": entity,
            "view": {
                "name": "ssh-access", "service": "ssh", "enabled": True,
                "status": "HEALTHY", "endpoint": "127.0.0.1:6022",
            },
        }
        valid_delete = {"operation": "delete", "entity": entity}
        bad_set = [
            {}, {"view": valid_set["view"]},
            {**valid_set, "entity": {**entity, "id": "another-service"}},
            {**valid_set, "view": {**valid_set["view"], "enabled": False}},
            {**valid_set, "operation": "pending"},
        ]
        for response in bad_set:
            with self.subTest(set_result=response), mock.patch(
                "drlink_v24.set_remote_service_agent", return_value=response
            ):
                with self.assertRaisesRegex(ValueError, "receipt UNKNOWN"):
                    _execute_management_job(set_claim, root=self.agent_tmp)
        bad_delete = [
            {}, {"status": "DELETED"},
            {**valid_delete, "entity": {**entity, "name": "another-service"}},
            {**valid_delete, "operation": "pending"},
        ]
        for response in bad_delete:
            with self.subTest(delete_result=response), mock.patch(
                "drlink_v24.unset_remote_service_agent", return_value=response
            ):
                with self.assertRaisesRegex(ValueError, "receipt UNKNOWN"):
                    _execute_management_job(delete_claim, root=self.agent_tmp)
        with mock.patch("drlink_v24.set_remote_service_agent", return_value=valid_set):
            self.assertEqual(
                _execute_management_job(set_claim, root=self.agent_tmp)["runtime_status"],
                "HEALTHY",
            )
        with mock.patch(
            "drlink_v24.unset_remote_service_agent", return_value=valid_delete
        ):
            removed = _execute_management_job(delete_claim, root=self.agent_tmp)
        self.assertEqual(removed["status"], "DELETED")
        self.assertIs(removed["runtime_verified"], False)

    def test_agent_diagnostic_job_results_do_not_export_raw_private_messages(self):
        from types import SimpleNamespace
        from unittest import mock
        from drlink_agent_lifecycle import _execute_management_job

        secret = "Bearer fixture-only-diagnostic-private-token"
        report = SimpleNamespace(
            checks=[{"id": "pki", "status": "WARN",
                     "message": "management token invalid: " + secret}],
            overall=lambda: "WARN",
        )
        with mock.patch("frp_doctor.run_doctor", return_value=("", 1, report)):
            doctor = _execute_management_job(
                {"job_type": "doctor"}, root=self.agent_tmp
            )
        self.assertEqual(doctor["findings"][0]["id"], "pki")
        self.assertEqual(doctor["findings"][0]["status"], "WARN")
        self.assertNotIn(secret, json.dumps(doctor))

        with mock.patch(
            "drlink_v24.synchronize_agent_remote_services",
            return_value={
                "status": "DEGRADED", "updated": 0, "projected": 1,
                "affected": [{"name": "ssh-access", "reason": "RPC error " + secret}],
                "runtime_error": "connection failed with " + secret,
            },
        ):
            refresh = _execute_management_job(
                {"job_type": "refresh"}, root=self.agent_tmp
            )
        self.assertEqual(refresh["status"], "DEGRADED")
        self.assertEqual(refresh["affected"][0]["name"], "ssh-access")
        self.assertNotIn(secret, json.dumps(refresh))

        with mock.patch(
            "drlink_v24.set_remote_service_agent",
            return_value={
                "operation": "set",
                "entity": {
                    "type": "remote-service", "id": "ssh-access",
                    "name": "ssh-access",
                },
                "view": {
                    "name": "ssh-access", "service": "ssh", "enabled": True,
                    "status": "DEGRADED", "reason": "secret relay URL " + secret,
                    "endpoint": "127.0.0.1:6022",
                },
            },
        ):
            service = _execute_management_job({
                "job_type": "remote-service-set",
                "payload": {
                    "name": "ssh-access", "destination": "this-host",
                    "service": "ssh", "enabled": True,
                },
            }, root=self.agent_tmp)
        self.assertEqual(service["name"], "ssh-access")
        self.assertEqual(service["runtime_status"], "DEGRADED")
        self.assertNotIn(secret, json.dumps(service))


class V30AgentCompletionAcknowledgementBoundaryTests(unittest.TestCase):
    """A lost Core completion acknowledgement must NEVER cause a second,
    conflicting FAILED completion for an already executed Agent mutation.
    Pure signed-RPC mock: no network, production Host or Agent effect.
    """

    def setUp(self):
        # The actual signed management request obtains its machine identity
        # from the Agent client-state; isolated mocked transport tests use
        # a pinned local identity to exercise the same verification boundary.
        from unittest import mock
        identity = mock.patch(
            "drlink_mgmt_sync._agent_identity",
            return_value={"machine_id": MACHINE_A},
        )
        identity.start()
        self.addCleanup(identity.stop)
        from datetime import datetime, timedelta, timezone
        instant=datetime.now(timezone.utc).replace(microsecond=0)
        self.claim_times={
            "lease_expires_at": (instant+timedelta(minutes=2)).isoformat().replace("+00:00","Z"),
            "deadline_at": (instant+timedelta(minutes=10)).isoformat().replace("+00:00","Z"),
        }

    def test_sequential_batch_rechecks_lease_before_each_agent_mutation(self):
        from unittest import mock
        from datetime import datetime, timedelta, timezone
        from drlink_agent_lifecycle import process_management_jobs_once
        baseline = datetime.now(timezone.utc).replace(microsecond=0)
        lease = (baseline + timedelta(seconds=3)).isoformat().replace("+00:00", "Z")
        first = {
            "job_id": "mjob_" + "6" * 24,
            "target_id": MACHINE_A,
            "claim_token": "6" * 32,
            "job_type": "remote-service-set",
            "lease_expires_at": lease,
            "deadline_at": self.claim_times["deadline_at"],
        }
        second = {**first, "job_id": "mjob_" + "7" * 24,
                  "claim_token": "7" * 32}
        def acknowledged(*, job_id, **kwargs):
            return {"ok": True, "job": {
                "id": job_id, "job_type": "remote-service-set",
                "status": "SUCCEEDED",
                "targets": [{"target_id": MACHINE_A, "status": "SUCCEEDED"}],
            }}
        with mock.patch("drlink_agent_lifecycle.datetime", wraps=datetime) as clock, mock.patch(
            "drlink_mgmt_sync.claim_management_jobs_on_server",
            return_value={"jobs": [first, second]},
        ), mock.patch(
            "drlink_agent_lifecycle._execute_management_job",
            return_value={"operation": "remote-service-set", "status": "COMMITTED"},
        ) as executed, mock.patch(
            "drlink_mgmt_sync.complete_management_job_on_server",
            side_effect=acknowledged,
        ) as completed:
            # Core's two claims are live at initial validation. By the time
            # the second task would begin, the short lease has expired.
            clock.now.side_effect = [
                baseline, baseline, baseline + timedelta(seconds=5),
            ]
            with self.assertRaisesRegex(ValueError,"claim response UNKNOWN"):
                process_management_jobs_once(root="/tmp/unused-agent-fixture")
        self.assertEqual(executed.call_count,1)
        self.assertEqual(completed.call_count,1)
        self.assertEqual(completed.call_args.kwargs["job_id"], first["job_id"])

    def test_stale_or_unverified_core_claim_time_rejects_batch_before_any_agent_work(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        good = {
            "job_id": "mjob_" + "4" * 24,
            "claim_token": "4" * 32,
            "job_type": "remote-service-set",
            "target_id": MACHINE_A,
            **self.claim_times,
        }
        wrong = [
            {"lease_expires_at": "2020-01-01T00:00:00Z"},
            {"deadline_at": "2020-01-01T00:00:00Z"},
            {"lease_expires_at": None},
            {"deadline_at": {"token": "DO_NOT_COPY"}},
            {"lease_expires_at": "yesterday"},
            {"lease_expires_at": "2026-02-31T00:00:00Z"},
            {"deadline_at": "2026-02-31T00:00:00Z"},
            {"lease_expires_at": "2030-01-01T00:00:00"},  # naive calendar time
            {"lease_expires_at": "2030-01-01T00:00:00+14:00"},  # non-Core clock
        ]
        for change in wrong:
            batch = [good, {**good, "job_id": "mjob_" + "5" * 24,
                            "claim_token": "5" * 32, **change}]
            with self.subTest(change=change), mock.patch(
                "drlink_mgmt_sync.claim_management_jobs_on_server",
                return_value={"jobs": batch},
            ), mock.patch(
                "drlink_agent_lifecycle._execute_management_job",
            ) as executed, mock.patch(
                "drlink_mgmt_sync.complete_management_job_on_server",
            ) as completed:
                with self.assertRaisesRegex(ValueError,"claim response UNKNOWN"):
                    process_management_jobs_once(root="/tmp/unused-agent-fixture")
                executed.assert_not_called()
                completed.assert_not_called()

    def test_signed_claim_for_another_host_is_rejected_before_any_agent_side_effect(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        own = {"job_id": "mjob_" + "1" * 24,
               "claim_token": "a" * 32, "target_id": MACHINE_A,
               "job_type": "remote-service-set", **self.claim_times}
        other = {**own, "job_id": "mjob_" + "2" * 24,
                 "claim_token": "b" * 32, "target_id": MACHINE_B}
        for claims in ([other], [own, other], [other, own]):
            with self.subTest(claims=claims), mock.patch(
                "drlink_mgmt_sync.claim_management_jobs_on_server",
                return_value={"jobs": claims},
            ), mock.patch(
                "drlink_agent_lifecycle._execute_management_job",
                return_value={"operation": "remote-service-set"},
            ) as executed, mock.patch(
                "drlink_mgmt_sync.complete_management_job_on_server",
                return_value={"ok": True},
            ) as completed:
                with self.assertRaisesRegex(ValueError, "claim response UNKNOWN"):
                    process_management_jobs_once(root="/tmp/unused-agent-fixture")
                executed.assert_not_called()
                completed.assert_not_called()

    def test_empty_or_malformed_local_agent_identity_never_executes_signed_jobs(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        claim = {"job_id": "mjob_" + "3" * 24,
                 "claim_token": "c" * 32, "target_id": MACHINE_A,
                 "job_type": "doctor", **self.claim_times}
        for identity in ({}, {"machine_id": None}, {"machine_id": "  "},
                         {"machine_id": {"secret": "UNTRUSTED"}}):
            with self.subTest(identity=identity), mock.patch(
                "drlink_mgmt_sync._agent_identity", return_value=identity,
            ), mock.patch(
                "drlink_mgmt_sync.claim_management_jobs_on_server",
                return_value={"jobs": [claim]},
            ), mock.patch(
                "drlink_agent_lifecycle._execute_management_job",
                return_value={"operation": "doctor"},
            ) as executed, mock.patch(
                "drlink_mgmt_sync.complete_management_job_on_server",
            ) as completed:
                with self.assertRaisesRegex(ValueError, "claim response UNKNOWN"):
                    process_management_jobs_once(root="/tmp/unused-agent-fixture")
                executed.assert_not_called()
                completed.assert_not_called()

    def test_malformed_or_duplicate_signed_claim_batch_is_unknown_before_any_agent_mutation(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        valid = {
            "job_id": "mjob_" + "f" * 24,
            "claim_token": "opaque-once",
            "job_type": "remote-service-delete",
            "target_id": MACHINE_A,
            **self.claim_times,
        }
        cases = [
            None, {}, {"jobs": None}, {"jobs": "unexpected"},
            {"jobs": [{}]}, {"jobs": [None]},
            {"jobs": [{**valid, "job_id": ""}]},
            {"jobs": [{**valid, "target_id": ""}]},
            {"jobs": [{**valid, "claim_token": ""}]},
            {"jobs": [{**valid, "job_type": "agent-update-rollout"}]},
            {"jobs": [{**valid, "job_type": "unknown-privileged"}]},
            {"jobs": [{**valid, "job_type": {"secret": "private"}}]},
            {"jobs": [{**valid, "claim_token": "opaque\nspoof"}]},
            {"jobs": [{**valid, "claim_token": {"token": "private"}}]},
            {"jobs": [valid] * 5},
            {"jobs": [valid, valid]},
            {"jobs": [valid, {**valid, "claim_token": "another-one"}]},
        ]
        for response in cases:
            with self.subTest(response=str(response)[:120]), mock.patch(
                "drlink_mgmt_sync.claim_management_jobs_on_server",
                return_value=response,
            ), mock.patch(
                "drlink_agent_lifecycle._execute_management_job",
                return_value={"operation": "remote-service-delete"},
            ) as executed, mock.patch(
                "drlink_mgmt_sync.complete_management_job_on_server",
                return_value={"ok": True},
            ) as completed:
                with self.assertRaisesRegex(ValueError, "claim response UNKNOWN"):
                    process_management_jobs_once(root="/tmp/unused-agent-fixture")
                executed.assert_not_called()
                completed.assert_not_called()
        with mock.patch(
            "drlink_mgmt_sync.claim_management_jobs_on_server",
            return_value={"jobs": []},
        ):
            self.assertEqual(process_management_jobs_once(root="/tmp/unused-agent-fixture"),
                             {"processed": 0, "failed": 0})

    def test_lost_success_ack_never_sends_second_failure_completion(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once

        claim = {
            "job_id": "mjob_" + "a" * 24,
            "claim_token": "opaque-claim-token",
            "job_type": "remote-service-set",
            "target_id": MACHINE_A,
            **self.claim_times,
        }
        with mock.patch(
            "drlink_mgmt_sync.claim_management_jobs_on_server",
            return_value={"jobs": [claim]},
        ), mock.patch(
            "drlink_agent_lifecycle._execute_management_job",
            return_value={"operation": "remote-service-set", "status": "COMMITTED"},
        ) as executed, mock.patch(
            "drlink_mgmt_sync.complete_management_job_on_server",
            side_effect=TimeoutError("Core reply lost after possible commit"),
        ) as completion:
            with self.assertRaisesRegex(TimeoutError, "Core reply lost"):
                process_management_jobs_once(root="/tmp/unused-agent-fixture")
        executed.assert_called_once_with(claim, root="/tmp/unused-agent-fixture")
        self.assertEqual(
            completion.call_count, 1,
            "A possibly committed Core success MUST NOT be followed by "
            "a second contradictory FAILED completion using the same claim token.",
        )
        self.assertEqual(completion.call_args.kwargs["status"], "SUCCEEDED")

    def test_core_reply_rejects_late_target_failure_instead_of_fabricating_agent_success(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        claim = {
            "job_id": "mjob_" + "c" * 24,
            "claim_token": "opaque-current",
            "job_type": "remote-service-set",
            "target_id": MACHINE_A,
            **self.claim_times,
        }
        # Core can legally mark a late SUCCEEDED completion FAILED because its
        # signed claim lease/deadline expired during Agent work.
        late = {"ok": True, "job": {
            "id": claim["job_id"], "job_type": claim["job_type"],
            "status": "FAILED",
            "targets": [{"target_id": MACHINE_A, "status": "FAILED"}],
        }}
        with mock.patch(
            "drlink_mgmt_sync.claim_management_jobs_on_server",
            return_value={"jobs": [claim]},
        ), mock.patch(
            "drlink_agent_lifecycle._execute_management_job",
            return_value={"operation": "remote-service-set"},
        ), mock.patch(
            "drlink_mgmt_sync.complete_management_job_on_server",
            return_value=late,
        ) as complete:
            with self.assertRaisesRegex(ValueError, "completion receipt UNKNOWN"):
                process_management_jobs_once(root="/tmp/unused-agent-fixture")
        complete.assert_called_once()
        self.assertEqual(complete.call_args.kwargs["status"], "SUCCEEDED")

    def test_current_target_ack_identity_required_and_one_valid_ack_accepted(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        claim = {
            "job_id": "mjob_" + "d" * 24,
            "claim_token": "opaque-current",
            "job_type": "doctor",
            "target_id": MACHINE_A,
            **self.claim_times,
        }
        correct = {"ok": True, "job": {
            "id": claim["job_id"], "job_type": "doctor",
            "status": "SUCCEEDED",
            "targets": [{"target_id": MACHINE_A, "status": "SUCCEEDED"}],
        }}
        for reply in [
            {}, {"ok": True}, {"ok": "true", "job": correct["job"]},
            {"ok": True, "job": {**correct["job"], "id": "mjob_" + "e" * 24}},
            {"ok": True, "job": {**correct["job"], "job_type": "support-bundle"}},
            {"ok": True, "job": {**correct["job"], "targets": []}},
            {"ok": True, "job": {**correct["job"], "targets": [
                {"target_id": MACHINE_B, "status": "SUCCEEDED"}]}},
            {"ok": True, "job": {**correct["job"], "targets": [
                {"target_id": MACHINE_A, "status": "SUCCEEDED"},
                {"target_id": MACHINE_A, "status": "SUCCEEDED"}]}},
        ]:
            with self.subTest(reply=str(reply)[:90]), mock.patch(
                "drlink_mgmt_sync.claim_management_jobs_on_server",
                return_value={"jobs": [claim]},
            ), mock.patch(
                "drlink_agent_lifecycle._execute_management_job",
                return_value={"operation": "doctor"},
            ), mock.patch(
                "drlink_mgmt_sync.complete_management_job_on_server",
                return_value=reply,
            ) as complete:
                with self.assertRaisesRegex(ValueError, "completion receipt UNKNOWN"):
                    process_management_jobs_once(root="/tmp/unused-agent-fixture")
                complete.assert_called_once()
        with mock.patch(
            "drlink_mgmt_sync.claim_management_jobs_on_server",
            return_value={"jobs": [claim]},
        ), mock.patch(
            "drlink_agent_lifecycle._execute_management_job",
            return_value={"operation": "doctor"},
        ), mock.patch(
            "drlink_mgmt_sync.complete_management_job_on_server",
            return_value=correct,
        ) as complete:
            self.assertEqual(process_management_jobs_once(root="/tmp/unused-agent-fixture"),
                             {"processed": 1, "failed": 0})
            complete.assert_called_once()

    def test_agent_handler_failure_sends_one_failed_completion_not_false_success(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        claim = {
            "job_id": "mjob_" + "b" * 24,
            "claim_token": "opaque-claim",
            "job_type": "doctor",
            "target_id": MACHINE_A,
            **self.claim_times,
        }
        with mock.patch(
            "drlink_mgmt_sync.claim_management_jobs_on_server",
            return_value={"jobs": [claim]},
        ), mock.patch(
            "drlink_agent_lifecycle._execute_management_job",
            side_effect=ValueError("LOCAL_DIAGNOSTIC_FAILURE"),
        ), mock.patch(
            "drlink_mgmt_sync.complete_management_job_on_server",
            return_value={"ok": True, "job": {
                "id": claim["job_id"], "job_type": claim["job_type"],
                "status": "FAILED",
                "targets": [{"target_id": MACHINE_A, "status": "FAILED"}],
            }},
        ) as completion:
            summary = process_management_jobs_once(root="/tmp/unused-agent-fixture")
        self.assertEqual(summary, {"processed": 1, "failed": 1})
        completion.assert_called_once()
        self.assertEqual(completion.call_args.kwargs["status"], "FAILED")
        self.assertEqual(completion.call_args.kwargs["result"], {})

    def test_agent_failure_does_not_send_exception_secrets_to_core_job_history(self):
        from unittest import mock
        claim = {
            "job_id": "mjob_" + "9" * 24,
            "claim_token": "opaque-redaction-claim",
            "job_type": "remote-service-set",
            "target_id": MACHINE_A,
            **self.claim_times,
        }
        secret = "Bearer secret-agent-credential-in-exception"
        receipt = {"ok": True, "job": {
            "id": claim["job_id"], "job_type": claim["job_type"],
            "targets": [{"target_id": MACHINE_A, "status": "FAILED"}],
        }}
        with mock.patch(
            "drlink_mgmt_sync.claim_management_jobs_on_server",
            return_value={"jobs": [claim]},
        ), mock.patch(
            "drlink_agent_lifecycle._execute_management_job",
            side_effect=ValueError("Unauthorized remote-service-set: " + secret),
        ), mock.patch(
            "drlink_mgmt_sync.complete_management_job_on_server",
            return_value=receipt,
        ) as completion:
            self.assertEqual(process_management_jobs_once(root="/tmp/unused-agent-fixture"),
                             {"processed": 1, "failed": 1})
        completion.assert_called_once()
        self.assertEqual(completion.call_args.kwargs["status"], "FAILED")
        self.assertEqual(completion.call_args.kwargs["result"], {})
        self.assertEqual(completion.call_args.kwargs["error"], "AGENT_JOB_EXECUTION_FAILED")
        self.assertNotIn(secret, str(completion.call_args.kwargs))


if __name__ == "__main__":
    unittest.main()
