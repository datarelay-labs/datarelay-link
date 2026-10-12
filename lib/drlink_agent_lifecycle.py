#!/usr/bin/env python3
"""Portable Agent lifecycle intent and reconnect reconciliation worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

VALID_INTENTS = frozenset({"running", "paused"})
DEFAULT_IDLE_SECONDS = 30
DEFAULT_RETRY_SECONDS = 5
MAX_RETRY_SECONDS = 60


def lifecycle_state_path(root: Optional[str] = None) -> Path:
    if root and str(root) not in ("", "/"):
        return Path(root) / "var/lib/drlink/agent-lifecycle.json"
    mac_root = str(os.environ.get("FRP_MACOS_STATE_ROOT") or "").strip()
    if mac_root:
        return Path(mac_root) / "state/agent-lifecycle.json"
    if platform.system().lower() == "darwin":
        return Path("/Library/Application Support/drlink/state/agent-lifecycle.json")
    return Path("/var/lib/drlink/agent-lifecycle.json")

def load_lifecycle_intent(root: Optional[str] = None) -> str:
    path = lifecycle_state_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "running"
    intent = str(data.get("intent") or "").strip().lower()
    return intent if intent in VALID_INTENTS else "running"


def set_lifecycle_intent(intent: str, root: Optional[str] = None) -> Path:
    value = str(intent or "").strip().lower()
    if value not in VALID_INTENTS:
        raise ValueError("lifecycle intent must be running or paused")
    path = lifecycle_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    payload = {
        "schema": 1,
        "intent": value,
        "updated_at": int(time.time()),
    }
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path

def reconciliation_needed(plane) -> bool:
    row = plane.conn.execute(
        "SELECT COUNT(*) AS n FROM agent_remote_services "
        "WHERE delete_pending = 1 OR pending_allocation = 1 "
        "OR (enabled = 1 AND (runtime_verified = 0 "
        "OR endpoint_port IS NULL OR upper(status) != 'HEALTHY'))"
    ).fetchone()
    return bool(row and int(row["n"] or 0) > 0)


def heartbeat_once(root: Optional[str] = None) -> dict:
    from drlink_mgmt_sync import report_agent_lifecycle_on_server

    return report_agent_lifecycle_on_server(root=root, state="connected")


def disconnect_once(root: Optional[str] = None) -> dict:
    from drlink_mgmt_sync import report_agent_lifecycle_on_server

    return report_agent_lifecycle_on_server(root=root, state="disconnected")


def _public_agent_diagnostic(value: object) -> str:
    """Expose diagnostic presence, never the free-form Agent-local message.

    Native failures may quote private URLs, credentials, network topology or
    configuration. Keep detailed text only in the Agent-local doctor/diagnostic
    surface; Core Job history is a wider trust and audit boundary.
    """
    return (
        "Check Agent-local diagnostics for details."
        if isinstance(value, str) and value.strip() else ""
    )


def _execute_management_job(claim: dict, root: Optional[str] = None) -> dict:
    kind = str(claim.get("job_type") or "").strip().lower()
    payload = claim.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("Management Job payload must be an object")

    if kind == "doctor":
        import frp_doctor

        _text, code, report = frp_doctor.run_doctor(
            root or "",
            {},
            fmt="json",
            quiet=True,
            verbose=False,
            skip_network=True,
        )
        counts: dict[str, int] = {}
        findings = []
        for check in list(report.checks):
            status = str(check.get("status") or "UNKNOWN").upper()
            counts[status] = counts.get(status, 0) + 1
            if status in ("FAIL", "WARN", "ERROR") and len(findings) < 20:
                findings.append(
                    {
                        "id": str(check.get("id") or "")[:128],
                        "status": status,
                        "message": _public_agent_diagnostic(check.get("message")),
                    }
                )
        return {
            "operation": "doctor",
            "overall": str(report.overall() or "UNKNOWN"),
            "exit_code": int(code),
            "check_count": len(report.checks),
            "counts": counts,
            "findings": findings,
            "network_probe_performed": False,
        }

    if kind == "support-bundle":
        import frp_support_bundle

        root_path = (
            Path(root)
            if root and str(root) not in ("", "/")
            else Path("/")
        )
        default_output = frp_support_bundle.default_output_path(root_path)
        job_suffix = "".join(
            ch for ch in str(claim.get("job_id") or "") if ch.isalnum()
        )[-12:] or "job"
        base_name = default_output.name
        if base_name.endswith(".tar.gz"):
            base_name = base_name[:-7]
        output = default_output.with_name(
            "%s-%s.tar.gz" % (base_name, job_suffix)
        )
        result = frp_support_bundle.create_support_bundle(
            root_path, output, secure_parent=True
        )
        digest_state = hashlib.sha256()
        with output.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest_state.update(chunk)
        digest = digest_state.hexdigest()
        try:
            rel = output.relative_to(root_path).as_posix()
            artifact_path = "/" + rel
        except ValueError:
            artifact_path = str(output)
        return {
            "operation": "support-bundle",
            "artifact_path": artifact_path,
            "size": int(result.get("size") or 0),
            "sha256": digest,
            "sanitized": True,
            "section_count": len(result.get("sections") or []),
            "skipped_count": len(result.get("skipped") or []),
            "role": str(result.get("role") or ""),
        }

    if kind == "version-check":
        from frp_version_identity import read_version_file

        base = Path(root) if root and str(root) not in ("", "/") else Path("/")
        version_file = base / "etc/drlink/version"
        try:
            values = read_version_file(version_file)
        except (OSError, ValueError):
            values = {}
        project_version = str(values.get("PROJECT_VERSION") or "unknown")
        relay_engine_version = str(values.get("FRP_VERSION") or "unknown")
        target_project = str(payload.get("target_project_version") or "unknown")
        target_engine = str(payload.get("target_relay_engine_version") or "unknown")

        def availability(current: str, target: str):
            if current == "unknown" or target == "unknown":
                return None
            return current != target

        return {
            "operation": "version-check",
            "project_version": project_version,
            "relay_engine_version": relay_engine_version,
            "release_channel": str(values.get("RELEASE_CHANNEL") or "unknown"),
            "source_ref": str(values.get("SOURCE_REF") or "unknown"),
            "source_head": str(values.get("SOURCE_HEAD") or "unknown"),
            "target_project_version": target_project,
            "target_relay_engine_version": target_engine,
            "target_release_channel": str(
                payload.get("target_release_channel") or "unknown"
            ),
            "product_update_available": availability(project_version, target_project),
            "relay_engine_update_available": availability(
                relay_engine_version, target_engine
            ),
        }

    from drlink_control_plane import ControlPlane
    from drlink_v24 import (
        ensure_v2_schema,
        set_remote_service_agent,
        synchronize_agent_remote_services,
        unset_remote_service_agent,
    )

    plane = ControlPlane(root)
    try:
        ensure_v2_schema(plane.conn)
        if kind == "refresh":
            result = synchronize_agent_remote_services(plane, root=root)
            affected = []
            for item in list((result or {}).get("affected") or [])[:20]:
                if isinstance(item, dict):
                    affected.append(
                        {
                            "name": str(item.get("name") or "")[:128],
                            "reason": _public_agent_diagnostic(item.get("reason")),
                        }
                    )
            return {
                "operation": "refresh",
                "status": str((result or {}).get("status") or "UNKNOWN"),
                "updated": int((result or {}).get("updated") or 0),
                "projected": int((result or {}).get("projected") or 0),
                "affected": affected,
                "runtime_error": _public_agent_diagnostic(
                    (result or {}).get("runtime_error")
                ),
            }
        if kind == "remote-service-set":
            name = str(payload.get("name") or "").strip()
            destination = str(payload.get("destination") or "").strip()
            service = str(payload.get("service") or "").strip()
            enabled = payload.get("enabled")
            if not name or not destination or not service or not isinstance(enabled, bool):
                raise ValueError("Remote Service set job payload is incomplete")
            result = set_remote_service_agent(
                plane,
                name,
                destination=destination,
                service=service,
                enabled=enabled,
                oneshot=True,
                root=root,
                server_reachable=True,
            )
            view = result.get("view") if isinstance(result, dict) else None
            return {
                "operation": "remote-service-set",
                "name": name,
                "runtime_status": str((view or {}).get("status") or "UNKNOWN"),
                "reason": _public_agent_diagnostic((view or {}).get("reason")),
                "endpoint": (view or {}).get("endpoint"),
            }
        if kind == "remote-service-delete":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Remote Service delete job payload is incomplete")
            result = unset_remote_service_agent(
                plane,
                name,
                root=root,
                server_reachable=True,
            )
            return {
                "operation": "remote-service-delete",
                "name": name,
                "status": str((result or {}).get("status") or "DELETED"),
            }
        raise ValueError("Unsupported Agent Management Job type: %s" % kind)
    finally:
        plane.close()


def _unexpired_core_claim_time(value: object, now: datetime) -> bool:
    """Core emits UTC second-precision Z time for job lease/deadline.
    Never execute Agent work with a stale, malformed or timezone-naive
    source claim. Core remains the authority for deadline completion.
    """
    if not isinstance(value, str) or len(value) != 20 or value[-1] != "Z":
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return False
    return parsed > now


def _require_core_management_completion_receipt(
    reply: object, claim: dict, reported_status: str,
) -> None:
    """Check Core's signed Job target receipt, not merely HTTP 200.

    Core can downgrade a late Agent completion to FAILED after the claim lease
    or deadline expires. No new Agent mutation, retry, credential/log exposure
    or second contradictory completion is justified by an ambiguous reply.
    """
    error = "Core Management Job completion receipt UNKNOWN; inspect Core before retrying."
    if not isinstance(reply, dict) or reply.get("ok") is not True:
        raise ValueError(error)
    job = reply.get("job")
    if not isinstance(job, dict):
        raise ValueError(error)
    if job.get("id") != claim.get("job_id") or (
        job.get("job_type") != claim.get("job_type")
    ):
        raise ValueError(error)
    targets = job.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 100:
        raise ValueError(error)
    matching = [
        item for item in targets
        if isinstance(item, dict) and item.get("target_id") == claim.get("target_id")
    ]
    if len(matching) != 1 or matching[0].get("status") != reported_status:
        raise ValueError(error)


def process_management_jobs_once(root: Optional[str] = None, *, limit: int = 4) -> dict:
    from drlink_mgmt_sync import (
        _agent_identity,
        claim_management_jobs_on_server,
        complete_management_job_on_server,
    )

    response = claim_management_jobs_on_server(root=root, limit=limit)
    # The signed server must provide an explicit bounded claim array. A
    # missing or malformed response is UNKNOWN, not a confirmed empty queue.
    # Validate the WHOLE batch before executing even one mutating Agent job:
    # duplicate entries must not run the same remote-service operation twice.
    invalid = "Core Management Job claim response UNKNOWN; inspect Core state before retrying."
    # A signed Server reply is also bound to the exact locally-enrolled
    # machine. A wrong-host claim must not cause any Agent work, even if a
    # Server route or replayed response unexpectedly includes that target.
    identity = _agent_identity(root)
    machine_id = identity.get("machine_id") if isinstance(identity, dict) else None
    if (not isinstance(machine_id, str)
        or not machine_id.strip() or len(machine_id) > 160
        or machine_id != machine_id.strip()
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in machine_id)):
        raise ValueError(invalid)
    try:
        count = max(1, min(int(limit), 16))
    except (TypeError, ValueError) as exc:
        raise ValueError(invalid) from exc
    if not isinstance(response, dict) or not isinstance(response.get("jobs"), list):
        raise ValueError(invalid)
    jobs = response["jobs"]
    if len(jobs) > count:
        raise ValueError(invalid)
    known = frozenset({
        "doctor", "refresh", "version-check", "support-bundle",
        "remote-service-set", "remote-service-delete",
    })
    seen: set[tuple[str, str]] = set()
    tokens: set[str] = set()
    now = datetime.now(timezone.utc)
    for claim in jobs:
        if not isinstance(claim, dict):
            raise ValueError(invalid)
        job_id, target_id, claim_token, kind = (
            claim.get("job_id"), claim.get("target_id"),
            claim.get("claim_token"), claim.get("job_type"),
        )
        if (not isinstance(job_id, str) or not job_id.startswith("mjob_")
            or len(job_id) != 29 or any(c not in "0123456789abcdef" for c in job_id[5:])
            or not isinstance(target_id, str) or target_id != machine_id
            or not isinstance(claim_token, str) or not claim_token
            or len(claim_token) > 128
            or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                   for ch in claim_token)
            or not isinstance(kind, str) or kind not in known
            or not _unexpired_core_claim_time(claim.get("lease_expires_at"), now)
            or not _unexpired_core_claim_time(claim.get("deadline_at"), now)
            or (claim.get("payload") is not None
                and not isinstance(claim.get("payload"), dict))
            or (job_id, target_id) in seen or claim_token in tokens):
            raise ValueError(invalid)
        seen.add((job_id, target_id))
        tokens.add(claim_token)
    processed = 0
    failed = 0
    for claim in jobs:
        # A prior Agent job in the same bounded batch may consume the next
        # claim's entire lease. Validate again immediately before each Agent
        # effect, not just once on receipt of the original signed batch.
        current = datetime.now(timezone.utc)
        if (not _unexpired_core_claim_time(claim["lease_expires_at"], current)
            or not _unexpired_core_claim_time(claim["deadline_at"], current)):
            raise ValueError(invalid)
        job_id = claim["job_id"]
        claim_token = claim["claim_token"]
        try:
            result = _execute_management_job(claim, root=root)
        except Exception:
            # Only an actual local Agent execution error may be reported as
            # FAILED. The Core still validates this authenticated claim.
            # Handler exception text can include credentials or customer data;
            # never persist it in signed Core Job history or expose it via Web.
            failed += 1
            receipt = complete_management_job_on_server(
                root=root,
                job_id=job_id,
                claim_token=claim_token,
                status="FAILED",
                result={},
                error="AGENT_JOB_EXECUTION_FAILED",
            )
            _require_core_management_completion_receipt(receipt, claim, "FAILED")
        else:
            # An acknowledgement/transport error can occur AFTER the Core
            # committed SUCCEEDED. Do NOT catch that error as Agent execution
            # failure or send a conflicting FAILED completion on the same
            # one-shot claim. Let worker retry/reconcile from Core authority.
            receipt = complete_management_job_on_server(
                root=root,
                job_id=job_id,
                claim_token=claim_token,
                status="SUCCEEDED",
                result=result,
            )
            _require_core_management_completion_receipt(receipt, claim, "SUCCEEDED")
        processed += 1
    return {"processed": processed, "failed": failed}


def reconcile_once(root: Optional[str] = None) -> dict:
    if load_lifecycle_intent(root) == "paused":
        return {"status": "PAUSED", "updated": 0}
    heartbeat = heartbeat_once(root)
    force_sync = bool((heartbeat or {}).get("reconcile_required", False))
    jobs = process_management_jobs_once(root)
    from drlink_control_plane import ControlPlane
    from drlink_v24 import ensure_v2_schema, synchronize_agent_remote_services

    plane = ControlPlane(root)
    try:
        ensure_v2_schema(plane.conn)
        if not force_sync and not reconciliation_needed(plane):
            return {
                "status": "HEARTBEAT",
                "updated": 0,
                "management_jobs_processed": int(jobs.get("processed") or 0),
                "management_jobs_failed": int(jobs.get("failed") or 0),
            }
        result = synchronize_agent_remote_services(plane, root=root)
        if isinstance(result, dict):
            result["management_jobs_processed"] = int(jobs.get("processed") or 0)
            result["management_jobs_failed"] = int(jobs.get("failed") or 0)
        return result
    finally:
        plane.close()

def worker(root: Optional[str] = None) -> int:
    idle = max(5, int(os.environ.get("DRLINK_LIFECYCLE_IDLE_SECONDS") or DEFAULT_IDLE_SECONDS))
    retry = max(1, int(os.environ.get("DRLINK_LIFECYCLE_RETRY_SECONDS") or DEFAULT_RETRY_SECONDS))
    backoff = retry
    while True:
        try:
            result = reconcile_once(root)
            status = str(result.get("status") or "").upper()
            if status in ("OFFLINE", "DEGRADED"):
                time.sleep(backoff)
                backoff = min(MAX_RETRY_SECONDS, max(retry, backoff * 2))
            else:
                backoff = retry
                time.sleep(idle)
        except KeyboardInterrupt:
            return 0
        except Exception:
            time.sleep(backoff)
            backoff = min(MAX_RETRY_SECONDS, max(retry, backoff * 2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    worker_cmd = sub.add_parser("worker")
    once_cmd = sub.add_parser("once")
    disconnect_cmd = sub.add_parser("disconnect")
    intent_cmd = sub.add_parser("set-intent")
    for item in (worker_cmd, once_cmd, disconnect_cmd, intent_cmd):
        item.add_argument("--root", default=None)
    intent_cmd.add_argument("intent", choices=sorted(VALID_INTENTS))
    args = parser.parse_args(argv)
    if args.command == "worker":
        return worker(args.root)
    if args.command == "once":
        print(json.dumps(reconcile_once(args.root), sort_keys=True))
        return 0
    if args.command == "disconnect":
        print(json.dumps(disconnect_once(args.root), sort_keys=True))
        return 0
    set_lifecycle_intent(args.intent, args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
