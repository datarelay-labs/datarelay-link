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
        finally:
            engine.close()


class V30AgentCompletionAcknowledgementBoundaryTests(unittest.TestCase):
    """A lost Core completion acknowledgement must NEVER cause a second,
    conflicting FAILED completion for an already executed Agent mutation.
    Pure signed-RPC mock: no network, production Host or Agent effect.
    """

    def test_malformed_or_duplicate_signed_claim_batch_is_unknown_before_any_agent_mutation(self):
        from unittest import mock
        from drlink_agent_lifecycle import process_management_jobs_once
        valid = {
            "job_id": "mjob_" + "f" * 24,
            "claim_token": "opaque-once",
            "job_type": "remote-service-delete",
            "target_id": MACHINE_A,
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


if __name__ == "__main__":
    unittest.main()
