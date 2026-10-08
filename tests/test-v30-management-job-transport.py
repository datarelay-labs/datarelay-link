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


class SignedRolloutArtifactOfflineTests(unittest.TestCase):
    """Release-signed immutable Agent bundle validation, with disposable keys."""

    def setUp(self):
        import hashlib

        from drlink_v30_agent_artifact import AGENT_REL

        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-v30-signed-artifact-")
        self.root = Path(self.tmp.name)
        self.key = self.root / "release-private-test-only.pem"
        self.pub = self.root / "release-public-test-only.pem"
        MGMT.generate_keypair(self.key, self.pub)
        self.bundle = self.root / "bootstrap-client.sh"
        self.bundle.write_bytes(b"#!/bin/sh\necho verified-fixture\n")
        self.target = {
            "version": "3.0.0",
            "source_ref": "a" * 40,
            "sha256": hashlib.sha256(self.bundle.read_bytes()).hexdigest(),
        }
        self.manifest = {
            "schema_version": 1,
            "qualification_status": "PASS",
            "channel": "development",
            "project_version": "3.0.0",
            "source_head": self.target["source_ref"],
            "git_ref": self.target["source_ref"],
            "immutable_source_ref": self.target["source_ref"],
            "artifacts": [{
                "relative_path": AGENT_REL,
                "artifact_type": "agent-installer",
                "platform": "linux",
                "source_head": self.target["source_ref"],
                "sha256": self.target["sha256"],
                "size": self.bundle.stat().st_size,
            }],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _verify(self, *, manifest=None, signature=None, target=None,
                pubkey=None, bundle=None, channel="development"):
        from drlink_v30_agent_artifact import verify_signed_agent_bundle

        data = json.dumps(
            self.manifest if manifest is None else manifest,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        signed = MGMT.sign_message(self.key, data) if signature is None else signature
        return verify_signed_agent_bundle(
            manifest_bytes=data, signature_b64=signed,
            trusted_release_public_key=(
                self.pub.read_text() if pubkey is None else pubkey
            ),
            bundle_path=self.bundle if bundle is None else bundle,
            target=self.target if target is None else target,
            expected_channel=channel,
        )

    def test_signed_manifest_and_exact_bundle_verify_without_apply(self):
        result = self._verify()
        self.assertTrue(result["signature_verified"])
        self.assertEqual(result["source_ref"], self.target["source_ref"])
        self.assertEqual(result["sha256"], self.target["sha256"])
        self.assertFalse(result["update_completed"])
        self.assertFalse(result["post_update_health_verified"])
        self.assertFalse(result["rollback_verified"])
        self.assertEqual(self.bundle.read_bytes(), b"#!/bin/sh\necho verified-fixture\n")

    def test_wrong_release_key_or_changed_signed_bytes_fail_closed(self):
        from drlink_v30_agent_artifact import AgentArtifactError, verify_signed_agent_bundle

        different = self.root / "other.key"
        other_pub = self.root / "other.pub"
        MGMT.generate_keypair(different, other_pub)
        with self.assertRaises(AgentArtifactError):
            self._verify(pubkey=other_pub.read_text())
        with self.assertRaises(AgentArtifactError):
            self._verify(pubkey=self.key.read_text())
        raw = json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode()
        sig = MGMT.sign_message(self.key, raw)
        changed = raw.replace(b'"development"', b'"stable"')
        with self.assertRaises(AgentArtifactError):
            verify_signed_agent_bundle(
                manifest_bytes=changed, signature_b64=sig,
                trusted_release_public_key=self.pub.read_text(),
                bundle_path=self.bundle, target=self.target,
                expected_channel="development",
            )
        with self.assertRaises(AgentArtifactError):
            self._verify(signature="unsigned")

    def test_signed_but_unqualified_or_wrong_target_refused(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        for change in (
            {"qualification_status": "PENDING"},
            {"channel": "stable"},
            {"source_head": "b" * 40},
            {"immutable_source_ref": "main"},
            {"project_version": "3.0.1"},
            {"schema_version": 2},
            {"schema_version": True},
            {"artifacts": self.manifest["artifacts"] * 2},
            {"artifacts": [{**self.manifest["artifacts"][0], "sha256": "f" * 64}]},
            {"artifacts": [{**self.manifest["artifacts"][0], "platform": "windows"}]},
        ):
            with self.subTest(change=change), self.assertRaises(AgentArtifactError):
                self._verify(manifest={**self.manifest, **change})
        with self.assertRaises(AgentArtifactError):
            self._verify(target={**self.target, "source_ref": "main"})
        with self.assertRaises(AgentArtifactError):
            self._verify(channel="stable")
        with self.assertRaises(AgentArtifactError):
            self._verify(
                manifest={**self.manifest, "project_version": "٣.٠.٠"},
                target={**self.target, "version": "٣.٠.٠"},
            )

    def test_signed_duplicate_json_key_must_fail_even_with_valid_signature(self):
        from drlink_v30_agent_artifact import (
            AgentArtifactError, verify_signed_agent_bundle,
        )

        original = json.dumps(
            self.manifest, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        ambiguous = original.replace(
            b'{"artifacts":', b'{"source_head":"' + (b"f" * 40) + b'","artifacts":',
            1,
        )
        self.assertNotEqual(original, ambiguous)
        # A genuine signature alone is not enough: duplicate identity fields
        # can be interpreted differently by two consumers of the manifest.
        signature = MGMT.sign_message(self.key, ambiguous)
        with self.assertRaises(AgentArtifactError):
            verify_signed_agent_bundle(
                manifest_bytes=ambiguous, signature_b64=signature,
                trusted_release_public_key=self.pub.read_text(),
                bundle_path=self.bundle, target=self.target,
                expected_channel="development",
            )

    def test_read_only_preflight_cli_checks_real_files_and_rejects_bad_signature(self):
        import subprocess

        raw = json.dumps(
            self.manifest, sort_keys=True, separators=(",", ":")
        ).encode()
        manifest = self.root / "manifest.json"
        signature = self.root / "manifest.sig"
        manifest.write_bytes(raw)
        signature.write_text(MGMT.sign_message(self.key, raw) + "\n")
        args = [
            sys.executable, str(ROOT / "lib/drlink_v30_agent_artifact.py"),
            "--manifest", str(manifest),
            "--signature", str(signature),
            "--release-public-key", str(self.pub),
            "--bundle", str(self.bundle),
            "--source-head", self.target["source_ref"],
            "--version", self.target["version"],
            "--sha256", self.target["sha256"],
            "--channel", "development",
        ]
        before = self.bundle.read_bytes()
        accepted = subprocess.run(args, capture_output=True, text=True, timeout=12)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        result = json.loads(accepted.stdout)
        self.assertTrue(result["signature_verified"])
        self.assertFalse(result["update_completed"])
        self.assertFalse(result["post_update_health_verified"])
        self.assertEqual(self.bundle.read_bytes(), before)

        signature.write_text("invalid-signature\n")
        rejected = subprocess.run(args, capture_output=True, text=True, timeout=12)
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("AGENT_ARTIFACT_UNQUALIFIED", rejected.stderr)
        self.assertNotIn("BEGIN PRIVATE KEY", rejected.stderr)
        self.assertEqual(self.bundle.read_bytes(), before)

    def test_bundle_mutation_and_symlink_are_denied(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        link = self.root / "bundle-link.sh"
        link.symlink_to(self.bundle)
        with self.assertRaises(AgentArtifactError):
            self._verify(bundle=link)
        self.bundle.write_bytes(b"#!/bin/sh\necho tampered\n")
        with self.assertRaises(AgentArtifactError):
            self._verify()

    def test_installed_exact_identity_and_hashes_are_required(self):
        import shutil

        from drlink_agent_payload import AGENT_LIB_FILES, write_installed_manifest
        from drlink_v30_agent_artifact import (
            AgentArtifactError, verify_installed_agent_lineage,
        )

        verified = self._verify()
        target_root = self.root / "agent-root"
        libdir = target_root / "usr/local/lib/drlink"
        libdir.mkdir(parents=True)
        for filename in AGENT_LIB_FILES:
            shutil.copy2(ROOT / "lib" / filename, libdir / filename)
        write_installed_manifest(libdir)
        version = target_root / "etc/drlink/version"
        version.parent.mkdir(parents=True)
        exact = (
            "PROJECT_VERSION=3.0.0\nRELEASE_CHANNEL=development\n"
            "SOURCE_REF={head}\nSOURCE_HEAD={head}\nBUNDLE_SHA256={digest}\n"
        ).format(head=self.target["source_ref"], digest=self.target["sha256"])
        version.write_text(exact)
        state = verify_installed_agent_lineage(target_root, verified_bundle=verified)
        self.assertTrue(state["installed_identity_verified"])
        self.assertTrue(state["runtime_lineage_verified"])
        self.assertFalse(state["post_update_health_verified"])
        self.assertFalse(state["rollback_verified"])
        version.write_text(exact.replace("SOURCE_HEAD=" + self.target["source_ref"],
                                         "SOURCE_HEAD=" + "b" * 40))
        with self.assertRaises(AgentArtifactError):
            verify_installed_agent_lineage(target_root, verified_bundle=verified)
        version.write_text(exact)
        (libdir / "drlink_v30_agent_artifact.py").write_text("# corrupted\n")
        with self.assertRaises(AgentArtifactError):
            verify_installed_agent_lineage(target_root, verified_bundle=verified)
        shutil.copy2(ROOT / "lib/drlink_v30_agent_artifact.py",
                     libdir / "drlink_v30_agent_artifact.py")
        (libdir / "runtime-sha256.json").unlink()
        with self.assertRaises(AgentArtifactError):
            verify_installed_agent_lineage(target_root, verified_bundle=verified)
        with self.assertRaises(AgentArtifactError):
            verify_installed_agent_lineage(
                target_root, verified_bundle={**verified, "signature_verified": False}
            )
        write_installed_manifest(libdir)
        current = libdir / "drlink_v30_agent_artifact.py"
        redirect = libdir / "redirect-copy.py"
        shutil.copy2(current, redirect)
        current.unlink()
        current.symlink_to(redirect)
        with self.assertRaises(AgentArtifactError):
            verify_installed_agent_lineage(target_root, verified_bundle=verified)



class SignedDistributionStagingTests(unittest.TestCase):
    """Offline Server-side detached-signature staging with test-only keys."""

    def setUp(self):
        import hashlib

        import drlink_qualified_artifacts as qa

        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-v30-dist-stage-")
        self.root = Path(self.tmp.name)
        self.unsigned = self.root / "unsigned"
        agent_dir = self.unsigned / "agent"
        agent_dir.mkdir(parents=True)
        self.staging = self.root / "staging"
        self.staging.mkdir()
        self.key = self.root / "release-test-only.key"
        self.pub = self.root / "release-test-only.pub"
        MGMT.generate_keypair(self.key, self.pub)
        self.fingerprint = MGMT.pubkey_fingerprint(self.pub.read_text())
        self.agent = agent_dir / "bootstrap-client.sh"
        self.agent.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.target = {
            "source_ref": "a" * 40,
            "version": "3.0.0",
            "sha256": hashlib.sha256(self.agent.read_bytes()).hexdigest(),
        }
        manifest = {
            "schema_version": 1,
            "drlink_version": qa.DRLINK_VERSION,
            "frp_version": qa.FRP_VERSION,
            "qualification_status": "PASS",
            "channel": "development",
            "source_head": self.target["source_ref"],
            "git_ref": self.target["source_ref"],
            "immutable_source_ref": self.target["source_ref"],
            "project_version": self.target["version"],
            "artifacts": [{
                "artifact_type": "agent-installer",
                "platform": "linux",
                "architecture": "any",
                "relative_path": "agent/bootstrap-client.sh",
                "source_head": self.target["source_ref"],
                "sha256": self.target["sha256"],
                "size": self.agent.stat().st_size,
            }],
        }
        self.manifest = self.unsigned / "manifest.json"
        self.manifest.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        (self.unsigned / "SHA256SUMS").write_text(
            self.target["sha256"] + "  agent/bootstrap-client.sh\n"
        )
        self.signature = self.root / "manifest.sig"
        self.signature.write_text(
            MGMT.sign_message(self.key, self.manifest.read_bytes()) + "\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _stage(self, **overrides):
        from drlink_v30_signed_distribution import stage_signed_candidate

        args = {
            "unsigned_artifact_root": self.unsigned,
            "detached_signature_file": self.signature,
            "trusted_release_public_key_file": self.pub,
            "pinned_release_key_fingerprint": self.fingerprint,
            "target": self.target,
            "expected_channel": "development",
            "staging_parent": self.staging,
        }
        args.update(overrides)
        return stage_signed_candidate(**args)

    def test_external_signature_stages_separate_unpublished_tree(self):
        import drlink_qualified_artifacts as qa
        from drlink_v30_signed_distribution import (
            SIGNATURE_REL, verify_signed_server_tree,
        )

        before = self.manifest.read_bytes()
        staged = self._stage()
        new_root = Path(staged["candidate_path"])
        self.assertNotEqual(new_root, self.unsigned)
        self.assertTrue(new_root.is_dir())
        self.assertTrue(staged["staged_signature_verified"])
        self.assertFalse(staged["published"])
        self.assertFalse(staged["update_completed"])
        self.assertFalse(staged["rollback_verified"])
        self.assertEqual(staged["signed_manifest_endpoint"],
                         "/artifacts/agent/manifest.sig")
        self.assertEqual(
            qa.resolve_http_path(new_root, "/artifacts/agent/manifest.sig"),
            new_root / SIGNATURE_REL,
        )
        self.assertEqual((new_root / "manifest.json").read_bytes(), before)
        self.assertFalse((self.unsigned / SIGNATURE_REL).exists())
        report = verify_signed_server_tree(
            new_root,
            trusted_release_public_key_file=self.pub,
            pinned_release_key_fingerprint=self.fingerprint,
            target=self.target, expected_channel="development",
        )
        self.assertTrue(report["staged_signature_verified"])
        self.assertEqual(report["target"]["source_ref"], self.target["source_ref"])
        self.assertFalse(report["target"]["post_update_health_verified"])

    def test_pinned_key_and_signature_are_not_trusted_from_distribution(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        for bad_pin in ("0" * 64, "bad-fingerprint", ""):
            with self.subTest(bad_pin=bad_pin), self.assertRaises(AgentArtifactError):
                self._stage(pinned_release_key_fingerprint=bad_pin)
        other_key = self.root / "untrusted-release.key"
        other_pub = self.root / "untrusted-release.pub"
        MGMT.generate_keypair(other_key, other_pub)
        self.signature.write_text(
            MGMT.sign_message(other_key, self.manifest.read_bytes()) + "\n"
        )
        with self.assertRaises(AgentArtifactError):
            self._stage()
        self.assertEqual(list(self.staging.iterdir()), [])
        # The candidate cannot carry its own replacement release trust anchor.
        self.signature.write_text(
            MGMT.sign_message(self.key, self.manifest.read_bytes()) + "\n"
        )
        imported_pub = self.unsigned / "release-public.pem"
        imported_pub.write_text(self.pub.read_text())
        with self.assertRaises(AgentArtifactError):
            self._stage(trusted_release_public_key_file=imported_pub)
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_tamper_missing_sidecar_symlink_and_extra_sidecar_fail_closed(self):
        from drlink_v30_agent_artifact import AgentArtifactError
        from drlink_v30_signed_distribution import verify_signed_server_tree

        staged = self._stage()
        new_root = Path(staged["candidate_path"])
        bundle = new_root / "agent/bootstrap-client.sh"
        bundle.write_bytes(bundle.read_bytes() + b"tampered")
        with self.assertRaises(AgentArtifactError):
            verify_signed_server_tree(
                new_root,
                trusted_release_public_key_file=self.pub,
                pinned_release_key_fingerprint=self.fingerprint,
                target=self.target, expected_channel="development",
            )
        signature = self.unsigned / "agent/manifest.sig"
        signature.write_text(self.signature.read_text())
        with self.assertRaises(AgentArtifactError):
            self._stage()
        signature.unlink()
        link = self.unsigned / "agent/untrusted-symlink"
        link.symlink_to(self.key)
        with self.assertRaises(AgentArtifactError):
            self._stage()

    def test_unsigned_extra_agent_payload_file_cannot_enter_signed_stage(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        (self.unsigned / "agent/unlisted-installer.sh").write_bytes(
            b"#!/bin/sh\\necho unsigned-extra\\n"
        )
        with self.assertRaises(AgentArtifactError):
            self._stage()
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_unlisted_frp_http_artifact_cannot_enter_signed_candidate(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        extra = self.unsigned / "frp/0.71.0/unlisted.bin"
        extra.parent.mkdir(parents=True)
        extra.write_bytes(b"unsigned binary")
        with self.assertRaises(AgentArtifactError):
            self._stage()
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_server_install_manifest_includes_offline_verifier_only(self):
        from frp_project_files import load_entries

        entries = load_entries(ROOT / "lib/server-project-files.manifest")
        included = {item.source for item in entries}
        self.assertIn("lib/drlink_v30_agent_artifact.py", included)
        self.assertIn("lib/drlink_v30_signed_distribution.py", included)
        self.assertIn("lib/drlink_agent_payload.py", included)
        self.assertNotIn("lib/drlink-v30-signing-private-key.pem", included)



class SignedAgentEnrolledHTTPSTests(unittest.TestCase):
    """A disposable TLS Server proves the Agent's read-only signed preflight."""

    def setUp(self):
        import ipaddress
        import ssl
        import threading
        from datetime import datetime, timedelta, timezone
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        self.fixture = SignedDistributionStagingTests(
            "test_external_signature_stages_separate_unpublished_tree"
        )
        self.fixture.setUp()
        self.root = self.fixture.root
        published = Path(self.fixture._stage()["candidate_path"])
        self.payloads = {
            "/artifacts/manifest.json": (published / "manifest.json").read_bytes(),
            "/artifacts/agent/manifest.sig": (
                published / "agent/manifest.sig"
            ).read_bytes(),
            "/artifacts/agent/bootstrap-client.sh": (
                published / "agent/bootstrap-client.sh"
            ).read_bytes(),
        }
        self.requests = []
        self.redirect = False

        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "drlink-local-test")])
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(hours=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                ), critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        self.ca = self.root / "enrollment-ca.pem"
        private = self.root / "local-tls.key"
        self.ca.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        private.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        private.chmod(0o600)
        parent = self

        class Receiver(BaseHTTPRequestHandler):
            def do_GET(self):
                parent.requests.append(self.path)
                if parent.redirect and self.path == "/artifacts/manifest.json":
                    self.send_response(302)
                    self.send_header("Location", "http://untrusted.example.test/manifest.json")
                    self.end_headers()
                    return
                data = parent.payloads.get(self.path)
                if data is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.ca), str(private))
        self.server.socket = context.wrap_socket(
            self.server.socket, server_side=True
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = "https://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.fixture.tearDown()

    def _preflight(self, **overrides):
        from drlink_v30_agent_artifact_transport import (
            verify_enrolled_server_candidate,
        )

        kwargs = {
            "enrolled_https_origin": self.origin,
            "enrollment_ca_file": self.ca,
            "trusted_release_public_key_file": self.fixture.pub,
            "pinned_release_key_fingerprint": self.fixture.fingerprint,
            "target": self.fixture.target,
            "expected_channel": "development",
        }
        kwargs.update(overrides)
        return verify_enrolled_server_candidate(**kwargs)

    def test_real_tls_verified_download_has_no_apply_side_effects(self):
        candidate = self._preflight()
        self.assertTrue(candidate["signature_verified"])
        self.assertEqual(candidate["source_ref"], self.fixture.target["source_ref"])
        self.assertEqual(candidate["transport"], "ENROLLED_SERVER_HTTPS")
        self.assertFalse(candidate["update_completed"])
        self.assertFalse(candidate["rollback_verified"])
        self.assertFalse(candidate["post_update_health_verified"])
        self.assertEqual(self.requests, [
            "/artifacts/manifest.json", "/artifacts/agent/manifest.sig",
            "/artifacts/agent/bootstrap-client.sh",
        ])
        self.assertFalse((self.root / "usr/local/bin/drlink").exists())

    def _stage(self, parent=None, **overrides):
        from drlink_v30_agent_artifact_transport import (
            stage_enrolled_server_candidate,
        )

        kwargs = {
            "enrolled_https_origin": self.origin,
            "enrollment_ca_file": self.ca,
            "trusted_release_public_key_file": self.fixture.pub,
            "pinned_release_key_fingerprint": self.fixture.fingerprint,
            "target": self.fixture.target,
            "expected_channel": "development",
            "staging_parent": parent or self._private_stage_parent(),
        }
        kwargs.update(overrides)
        return stage_enrolled_server_candidate(**kwargs)

    def _private_stage_parent(self):
        parent = self.root / "private-agent-stage"
        parent.mkdir(mode=0o700, exist_ok=True)
        return parent

    def test_verified_download_is_retained_private_and_reverified_before_use(self):
        import stat
        from drlink_v30_agent_artifact_transport import verify_staged_enrolled_candidate

        staged = self._stage()
        directory = Path(staged["candidate_dir"])
        self.assertTrue(staged["candidate_staged"])
        self.assertEqual(staged["source_ref"], self.fixture.target["source_ref"])
        self.assertFalse(staged["update_completed"])
        self.assertFalse(staged["post_update_health_verified"])
        self.assertFalse(staged["rollback_verified"])
        self.assertEqual(
            stat.S_IMODE(directory.stat().st_mode), 0o700,
        )
        for path, original in (
            (directory / "manifest.json", self.payloads["/artifacts/manifest.json"]),
            (directory / "agent/manifest.sig", self.payloads["/artifacts/agent/manifest.sig"]),
            (directory / "agent/bootstrap-client.sh", self.payloads["/artifacts/agent/bootstrap-client.sh"]),
        ):
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        verified = verify_staged_enrolled_candidate(
            candidate_dir=directory,
            trusted_release_public_key_file=self.fixture.pub,
            pinned_release_key_fingerprint=self.fixture.fingerprint,
            target=self.fixture.target, expected_channel="development",
        )
        self.assertTrue(verified["signature_verified"])
        self.assertFalse(verified["update_completed"])
        self.assertFalse((self.root / "usr/local/bin/drlink").exists())
        self.assertEqual(len(self.requests), 3)

    def test_staged_bundle_signature_and_file_substitution_fail_closed(self):
        from drlink_v30_agent_artifact import AgentArtifactError
        from drlink_v30_agent_artifact_transport import verify_staged_enrolled_candidate

        staged = self._stage()
        directory = Path(staged["candidate_dir"])
        def reverify():
            return verify_staged_enrolled_candidate(
                candidate_dir=directory,
                trusted_release_public_key_file=self.fixture.pub,
                pinned_release_key_fingerprint=self.fixture.fingerprint,
                target=self.fixture.target, expected_channel="development",
            )
        bundle = directory / "agent/bootstrap-client.sh"
        old = bundle.read_bytes()
        bundle.write_bytes(old + b"altered")
        with self.assertRaises(AgentArtifactError):
            reverify()
        bundle.write_bytes(old)
        signature = directory / "agent/manifest.sig"
        previous_signature = signature.read_bytes()
        signature.write_bytes(b"invalid-signature\n")
        with self.assertRaises(AgentArtifactError):
            reverify()
        signature.write_bytes(previous_signature)
        outside = self.root / "not-an-agent.sh"
        outside.write_bytes(old)
        bundle.unlink()
        bundle.symlink_to(outside)
        with self.assertRaises(AgentArtifactError):
            reverify()
        bundle.unlink()
        bundle.write_bytes(old)
        (directory / "agent/extra-script.sh").write_bytes(b"unexpected")
        with self.assertRaises(AgentArtifactError):
            reverify()

    def test_staged_agent_directory_symlink_is_never_accepted(self):
        from drlink_v30_agent_artifact import AgentArtifactError
        from drlink_v30_agent_artifact_transport import verify_staged_enrolled_candidate

        candidate = Path(self._stage()["candidate_dir"])
        agent = candidate / "agent"
        moved = self.root / "relocated-agent-directory"
        agent.rename(moved)
        agent.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(AgentArtifactError):
            verify_staged_enrolled_candidate(
                candidate_dir=candidate,
                trusted_release_public_key_file=self.fixture.pub,
                pinned_release_key_fingerprint=self.fixture.fingerprint,
                target=self.fixture.target, expected_channel="development",
            )

    def test_invalid_signed_download_leaves_no_persistent_candidate(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        parent = self._private_stage_parent()
        self.redirect = True
        with self.assertRaises(AgentArtifactError):
            self._stage(parent=parent)
        self.assertEqual(list(parent.iterdir()), [])
        self.redirect = False
        self.requests.clear()
        self.payloads["/artifacts/agent/bootstrap-client.sh"] += b"changed"
        with self.assertRaises(AgentArtifactError):
            self._stage(parent=parent)
        self.assertEqual(list(parent.iterdir()), [])

    def test_candidate_staging_refuses_unbounded_accumulation(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        parent = self._private_stage_parent()
        existing = [Path(self._stage(parent=parent)["candidate_dir"]) for _ in range(3)]
        self.assertEqual(len(list(parent.iterdir())), 3)
        requests_before = len(self.requests)
        with self.assertRaises(AgentArtifactError):
            self._stage(parent=parent)
        # A rejected fourth update must not retry downloads, delete old
        # candidates, or silently reuse a stale candidate.
        self.assertEqual(len(self.requests), requests_before)
        self.assertEqual({p.name for p in parent.iterdir()},
                         {p.name for p in existing})
        self.assertTrue(all(p.is_dir() for p in existing))

    def test_parallel_staging_has_no_more_than_three_candidate_slots(self):
        from concurrent.futures import ThreadPoolExecutor
        from drlink_v30_agent_artifact import AgentArtifactError
        from drlink_v30_agent_artifact_transport import verify_staged_enrolled_candidate

        parent = self._private_stage_parent()

        def attempt(_):
            try:
                return self._stage(parent=parent)["candidate_dir"]
            except AgentArtifactError:
                return None

        with ThreadPoolExecutor(max_workers=5) as workers:
            outcomes = list(workers.map(attempt, range(5)))
        created = [Path(item) for item in outcomes if item is not None]
        self.assertGreaterEqual(len(created), 1)
        self.assertLessEqual(len(created), 3)
        self.assertEqual(
            {item.name for item in created},
            {item.name for item in parent.iterdir()},
        )
        for item in created:
            report = verify_staged_enrolled_candidate(
                candidate_dir=item,
                trusted_release_public_key_file=self.fixture.pub,
                pinned_release_key_fingerprint=self.fixture.fingerprint,
                target=self.fixture.target, expected_channel="development",
            )
            self.assertTrue(report["signature_verified"])
            self.assertFalse(report["update_completed"])

    def test_candidate_staging_requires_independent_private_directory(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        parent = self.root / "public-stage"
        parent.mkdir(mode=0o755)
        with self.assertRaises(AgentArtifactError):
            self._stage(parent=parent)
        self.assertEqual(list(parent.iterdir()), [])
        alias = self.root / "stage-symlink"
        private = self._private_stage_parent()
        alias.symlink_to(private, target_is_directory=True)
        with self.assertRaises(AgentArtifactError):
            self._stage(parent=alias)
        self.assertEqual(list(private.iterdir()), [])

    def test_redirect_and_signed_bundle_tamper_fail_closed(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        self.redirect = True
        with self.assertRaises(AgentArtifactError):
            self._preflight()
        self.assertEqual(self.requests, ["/artifacts/manifest.json"])
        self.redirect = False
        self.requests.clear()
        self.payloads["/artifacts/agent/bootstrap-client.sh"] += b"tamper"
        with self.assertRaises(AgentArtifactError):
            self._preflight()
        self.assertEqual(len(self.requests), 3)

    def test_wrong_tls_ca_release_fingerprint_or_http_origin_denied(self):
        from drlink_v30_agent_artifact import AgentArtifactError

        self.ca.write_text("not a CA")
        with self.assertRaises(AgentArtifactError):
            self._preflight()
        self.assertEqual(self.requests, [])
        with self.assertRaises(AgentArtifactError):
            self._preflight(pinned_release_key_fingerprint="0" * 64)
        self.assertEqual(self.requests, [])
        for origin in (
            "http://127.0.0.1", "https://user:pass@127.0.0.1",
            "https://127.0.0.1/artifacts/manifest.json",
            "https://127.0.0.1/?redirect=true",
            "https://127.0.0.1:0",
        ):
            with self.subTest(origin=origin), self.assertRaises(AgentArtifactError):
                self._preflight(enrolled_https_origin=origin)

if __name__ == "__main__":
    unittest.main()
