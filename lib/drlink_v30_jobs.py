#!/usr/bin/env python3
"""Bounded Data Relay Link 3.0 Management Job Engine.

Management Jobs are operational state. They are deliberately separate from
ai_jobs so fleet and Agent operations do not inherit AI identity or
authorization semantics.

The engine only holds SQLite write transactions for short queue, claim, and
result state changes. Agent RPC or other remote work runs outside those
transactions.
"""
from __future__ import annotations

import json
import secrets
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional

from drlink_control_db import ControlPlaneError, open_control_db, utc_now_iso

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
JOB_STATUSES = frozenset({QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED})
TERMINAL_STATUSES = frozenset({SUCCEEDED, FAILED, CANCELLED})

ADMITTED_JOB_TYPES = frozenset({"doctor", "refresh", "version-check", "support-bundle", "remote-service-set", "remote-service-delete", "agent-update-rollout"})
ROLLOUT_JOB_TYPE = "agent-update-rollout"
# Only these two Job families have verified side-effect-free Agent handlers.
# Every new admitted Job family must fail closed under Host quarantine until
# it is explicitly proven observational and added to this small allowlist.
READ_ONLY_AGENT_JOB_TYPES = frozenset({"doctor", "version-check"})
MUTATING_AGENT_JOB_TYPES = ADMITTED_JOB_TYPES - READ_ONLY_AGENT_JOB_TYPES
MAX_ROLLOUT_WAVE_SIZE = 25
MAX_ROLLOUT_FAILURE_THRESHOLD = 100
DEFAULT_JOB_TIMEOUT_SECONDS = 300
MAX_JOB_TIMEOUT_SECONDS = 3600
DEFAULT_LEASE_SECONDS = 60
MAX_ACTIVE_JOBS = 128
MAX_JOB_TARGETS = 100
MAX_CLAIM_BATCH = 32


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_utc(value: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def _json(value: Any, *, max_bytes: int = 16384, field: str = "Management Job JSON") -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ControlPlaneError("%s is not JSON serializable." % field) from exc
    if len(raw.encode("utf-8")) > max_bytes:
        raise ControlPlaneError("%s exceeds the %d-byte bound." % (field, max_bytes))
    return raw


def _bounded_text(value: Any, *, field: str, max_len: int = 256) -> str:
    text = str(value or "").strip()
    if not text:
        raise ControlPlaneError("%s is required." % field)
    if len(text) > max_len:
        raise ControlPlaneError("%s is too long." % field)
    return text


def _normalize_targets(targets: Iterable[str], *, max_targets: int) -> tuple[str, ...]:
    # Strings and mappings are iterable but never a valid explicit Host set.
    if (isinstance(targets, (str, bytes, bytearray, Mapping))
        or not isinstance(targets, Iterable)):
        raise ControlPlaneError("Management Job targets must be a Host ID collection.")
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in targets:
        if not isinstance(raw, str):
            raise ControlPlaneError("Management Job target must be a string Host ID.")
        target = _bounded_text(raw, field="Management Job target")
        if target in seen:
            continue
        seen.add(target)
        ordered.append(target)
        if len(ordered) > max_targets:
            raise ControlPlaneError(
                "Management Job exceeds the %d-target bound." % max_targets
            )
    if not ordered:
        raise ControlPlaneError("Management Job requires at least one target.")
    return tuple(ordered)


def _planned_rollout_batches(
    target_ids: Iterable[str], canary_targets: Iterable[str], wave_size: int,
) -> list[dict[str, Any]]:
    """Expose the exact deterministic Canary/Wave groups without queue mutation.

    Batch order matches the persisted-ID ordering used by the claim barrier;
    it is not a signed artifact qualification or permission to Apply.
    """
    canaries = set(canary_targets)
    stages = (
        ("CANARY", sorted(canaries)),
        ("WAVE", sorted(host for host in target_ids if host not in canaries)),
    )
    return [
        {"phase": phase, "batch": index // wave_size + 1,
         "targets": hosts[index:index + wave_size]}
        for phase, hosts in stages
        for index in range(0, len(hosts), wave_size)
    ]


def job_operational_summary(conn, *, max_active_jobs: int = MAX_ACTIVE_JOBS) -> dict[str, Any]:
    """Return a rebuildable operational summary; never configuration authority."""
    rows = conn.execute(
        "SELECT status,COUNT(*) AS n FROM management_jobs GROUP BY status"
    ).fetchall()
    counts = {status: 0 for status in JOB_STATUSES}
    for row in rows:
        status = str(row["status"] or "")
        if status in counts:
            counts[status] = int(row["n"] or 0)
    active = counts[QUEUED] + counts[RUNNING]
    target_rows = conn.execute(
        "SELECT status,COUNT(*) AS n FROM management_job_targets "
        "WHERE status IN ('QUEUED','RUNNING') GROUP BY status"
    ).fetchall()
    target_counts = {QUEUED: 0, RUNNING: 0}
    for row in target_rows:
        target_counts[str(row["status"])] = int(row["n"] or 0)
    return {
        "active_jobs": active,
        "queued_jobs": counts[QUEUED],
        "running_jobs": counts[RUNNING],
        "failed_jobs": counts[FAILED],
        "cancelled_jobs": counts[CANCELLED],
        "succeeded_jobs": counts[SUCCEEDED],
        "queued_targets": target_counts[QUEUED],
        "running_targets": target_counts[RUNNING],
        "max_active_jobs": int(max_active_jobs),
        "saturated": active >= int(max_active_jobs),
    }


def rollout_progress_summary(
    job_type: str, payload: Mapping[str, Any],
    targets: list[Mapping[str, Any]], target_count: int,
) -> Optional[dict[str, Any]]:
    """Bounded read model of persisted scheduler facts, not update verification.

    Web and Core consumers share one interpretation of Canary/Wave progress.
    An unqualified Agent updater cannot turn a synthetic SUCCEEDED job row
    into a proven installed build or a proven successful rollback.
    """
    if str(job_type) != ROLLOUT_JOB_TYPE:
        return None
    body = payload if isinstance(payload, Mapping) else {}
    count = max(0, min(int(target_count), MAX_JOB_TARGETS))
    actual = list(targets[:MAX_JOB_TARGETS])
    totals = {name: 0 for name in JOB_STATUSES}
    for item in actual:
        status = str(item.get("status") or "").upper()
        if status in totals:
            totals[status] += 1
    canaries = body.get("canary_targets")
    if not isinstance(canaries, list):
        canaries = []
    canaries = [
        value for value in canaries[:MAX_JOB_TARGETS]
        if isinstance(value, str) and value
    ]
    by_host = {
        str(item.get("target_id") or ""): str(item.get("status") or "").upper()
        for item in actual
    }
    phase = str(body.get("rollout_state") or "UNKNOWN")
    if phase not in ("CANARY", "WAVE", "PAUSED", "HALTED"):
        phase = "UNKNOWN"
    return {
        "phase": phase,
        "halt_reason": str(body.get("halt_reason") or "")[:128],
        "target_count": count,
        "observed_count": len(actual),
        "completed_count": sum(totals[s] for s in TERMINAL_STATUSES),
        "queued_count": totals[QUEUED],
        "running_count": totals[RUNNING],
        "reported_success_count": totals[SUCCEEDED],
        "failed_count": totals[FAILED],
        "cancelled_count": totals[CANCELLED],
        "canary_count": len(canaries),
        "canary_reported_success_count": sum(
            by_host.get(host) == SUCCEEDED for host in canaries
        ),
        "operator_paused": bool(body.get("operator_paused", False)),
        "update_outcome_qualification": "NOT_VERIFIED",
        "signed_agent_update_verified": False,
        "rollback_verified": False,
    }


class ManagementJobEngine:
    """Short-transaction operational Job store and claim/complete boundary."""

    def __init__(
        self,
        root: Optional[str] = None,
        *,
        max_active_jobs: int = MAX_ACTIVE_JOBS,
        max_targets: int = MAX_JOB_TARGETS,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ):
        self.root = root
        self.conn = open_control_db(root)
        # One engine connection may be completed from several RPC workers.
        # Serialize only short SQLite state transitions; remote work never holds it.
        self._lock = threading.RLock()
        self.max_active_jobs = max(1, int(max_active_jobs))
        self.max_targets = max(1, min(int(max_targets), MAX_JOB_TARGETS))
        self.lease_seconds = max(5, min(int(lease_seconds), MAX_JOB_TIMEOUT_SECONDS))

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ManagementJobEngine":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def _rollback(self) -> None:
        try:
            self.conn.execute("ROLLBACK")
        except Exception:
            pass

    def _refresh_job_status(self, job_id: str, *, now_text: Optional[str] = None) -> str:
        now = now_text or utc_now_iso()
        job = self.conn.execute(
            "SELECT status,cancel_requested,started_at FROM management_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if not job:
            raise ControlPlaneError("Management Job was not found.")
        rows = self.conn.execute(
            "SELECT status,COUNT(*) AS n FROM management_job_targets "
            "WHERE job_id=? GROUP BY status",
            (job_id,),
        ).fetchall()
        counts = {status: 0 for status in JOB_STATUSES}
        for row in rows:
            status = str(row["status"])
            if status in counts:
                counts[status] = int(row["n"] or 0)
        if counts[RUNNING]:
            status = RUNNING
        elif counts[QUEUED]:
            status = QUEUED
        elif int(job["cancel_requested"] or 0):
            status = CANCELLED
        elif counts[FAILED]:
            status = FAILED
        else:
            status = SUCCEEDED
        finished = now if status in TERMINAL_STATUSES else None
        self.conn.execute(
            "UPDATE management_jobs SET status=?,"
            "started_at=COALESCE(started_at,CASE WHEN ?='RUNNING' THEN ? ELSE NULL END),"
            "finished_at=CASE WHEN ? IN ('SUCCEEDED','FAILED','CANCELLED') THEN ? ELSE NULL END,"
            "updated_at=? WHERE id=?",
            (status, status, now, status, finished, now, job_id),
        )
        return status

    def _enqueue_unlocked(
        self,
        *,
        job_type: str,
        targets: Iterable[str],
        requested_by: str,
        resource_type: str = "managed-host",
        resource_ref: str = "",
        payload: Optional[dict[str, Any]] = None,
        timeout_seconds: int = DEFAULT_JOB_TIMEOUT_SECONDS,
        now: Optional[datetime] = None,
        _validated_rollout: bool = False,
    ) -> dict[str, Any]:
        kind = str(job_type or "").strip().lower()
        if kind == ROLLOUT_JOB_TYPE and not _validated_rollout:
            raise ControlPlaneError(
                "Rollout Jobs require explicit canary, artifact and Host validation."
            )
        if kind not in ADMITTED_JOB_TYPES:
            raise ControlPlaneError(
                "Management Job type '%s' is not an admitted 3.0 safe job family." % kind
            )
        actor = _bounded_text(requested_by, field="Management Job actor")
        target_ids = _normalize_targets(targets, max_targets=self.max_targets)
        if type(timeout_seconds) is not int:
            raise ControlPlaneError("Management Job timeout must be an integer.")
        timeout = timeout_seconds
        if timeout < 1 or timeout > MAX_JOB_TIMEOUT_SECONDS:
            raise ControlPlaneError(
                "Management Job timeout must be between 1 and %d seconds."
                % MAX_JOB_TIMEOUT_SECONDS
            )
        current = now or _utc_now()
        created_at = _utc_text(current)
        deadline_at = _utc_text(current + timedelta(seconds=timeout))
        job_id = "mjob_" + secrets.token_hex(12)
        self._begin()
        try:
            active = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM management_jobs "
                    "WHERE status IN ('QUEUED','RUNNING')"
                ).fetchone()[0]
                or 0
            )
            if active >= self.max_active_jobs:
                raise ControlPlaneError(
                    "Management Job queue is saturated (%d active jobs)." % active
                )
            self.conn.execute(
                "INSERT INTO management_jobs("
                "id,job_type,requested_by,resource_type,resource_ref,payload_json,status,"
                "cancel_requested,target_count,created_at,started_at,finished_at,deadline_at,"
                "updated_at,last_error) "
                "VALUES (?,?,?,?,?,?,'QUEUED',0,?,?,NULL,NULL,?,?,'')",
                (
                    job_id,
                    kind,
                    actor,
                    str(resource_type or "").strip(),
                    str(resource_ref or "").strip(),
                    _json(payload or {}, field="Management Job payload"),
                    len(target_ids),
                    created_at,
                    deadline_at,
                    created_at,
                ),
            )
            self.conn.executemany(
                "INSERT INTO management_job_targets("
                "job_id,target_id,status,worker_id,claim_token,attempt,started_at,finished_at,"
                "lease_expires_at,updated_at,result_json,error) "
                "VALUES (?,?,'QUEUED','','',0,NULL,NULL,NULL,?,'{}','')",
                [(job_id, target, created_at) for target in target_ids],
            )
            self.conn.execute("COMMIT")
        except Exception:
            self._rollback()
            raise
        return self.get(job_id)

    def _get_unlocked(self, job_id: str) -> dict[str, Any]:
        job = self.conn.execute(
            "SELECT * FROM management_jobs WHERE id=?", (str(job_id),)
        ).fetchone()
        if not job:
            raise ControlPlaneError("Management Job was not found.")
        targets = self.conn.execute(
            "SELECT target_id,status,worker_id,attempt,started_at,finished_at,"
            "lease_expires_at,updated_at,result_json,error "
            "FROM management_job_targets WHERE job_id=? ORDER BY target_id LIMIT ?",
            (str(job_id), self.max_targets),
        ).fetchall()
        out = {key: job[key] for key in job.keys() if key != "payload_json"}
        out["payload"] = json.loads(str(job["payload_json"] or "{}"))
        out["targets"] = []
        for row in targets:
            item = {key: row[key] for key in row.keys() if key != "result_json"}
            try:
                item["result"] = json.loads(str(row["result_json"] or "{}"))
            except ValueError:
                item["result"] = {}
            out["targets"].append(item)
        progress = rollout_progress_summary(
            str(job["job_type"]), out["payload"], out["targets"],
            int(job["target_count"]),
        )
        if progress is not None:
            out["rollout_progress"] = progress
        return out

    def _cancel_unlocked(self, job_id: str, *, now: Optional[datetime] = None) -> dict[str, Any]:
        current = _utc_text(now or _utc_now())
        self._begin()
        try:
            job = self.conn.execute(
                "SELECT status FROM management_jobs WHERE id=?", (str(job_id),)
            ).fetchone()
            if not job:
                raise ControlPlaneError("Management Job was not found.")
            if str(job["status"]) in TERMINAL_STATUSES:
                self.conn.execute("COMMIT")
                return self.get(str(job_id))
            self.conn.execute(
                "UPDATE management_jobs SET cancel_requested=1,updated_at=? WHERE id=?",
                (current, str(job_id)),
            )
            self.conn.execute(
                "UPDATE management_job_targets SET status='CANCELLED',finished_at=?,"
                "lease_expires_at=NULL,updated_at=?,error='CANCELLED_BY_OPERATOR' "
                "WHERE job_id=? AND status='QUEUED'",
                (current, current, str(job_id)),
            )
            self._refresh_job_status(str(job_id), now_text=current)
            self.conn.execute("COMMIT")
        except Exception:
            self._rollback()
            raise
        return self.get(str(job_id))

    def _is_cancel_requested_unlocked(self, job_id: str) -> bool:
        row = self.conn.execute(
            "SELECT cancel_requested FROM management_jobs WHERE id=?", (str(job_id),)
        ).fetchone()
        return bool(row and int(row[0] or 0))

    def _halt_rollout_unlocked(
        self, job_id: str, reason: str, *, now_text: str
    ) -> bool:
        """Fence unfinished waves when a rollout loses trusted completion evidence.

        Caller holds the current SQLite write transaction. A failed/unknown
        Agent operation is never promoted to success or silently rescheduled.
        Previously running targets may still report a terminal outcome, but
        no queued target is dispatched after the rollout is halted.
        """
        row = self.conn.execute(
            "SELECT job_type,payload_json FROM management_jobs WHERE id=?",
            (str(job_id),),
        ).fetchone()
        if not row or str(row["job_type"]) != ROLLOUT_JOB_TYPE:
            return False
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        # The first reason is authoritative. A later lease timeout cannot
        # conceal the original failed canary or threshold breach.
        if payload.get("rollout_state") == "HALTED":
            return True
        payload["rollout_state"] = "HALTED"
        payload["halt_reason"] = str(reason)[:128]
        self.conn.execute(
            "UPDATE management_jobs SET payload_json=?,last_error=?,updated_at=? WHERE id=?",
            (_json(payload, field="Managed Update rollout payload"),
             str(reason)[:128], now_text, str(job_id)),
        )
        self.conn.execute(
            "UPDATE management_job_targets SET status='CANCELLED',finished_at=?,"
            "lease_expires_at=NULL,updated_at=?,error=? "
            "WHERE job_id=? AND status='QUEUED'",
            (now_text, now_text, str(reason)[:128], str(job_id)),
        )
        self._refresh_job_status(str(job_id), now_text=now_text)
        return True

    def _rollout_claim_allowed_unlocked(self, row, *, now_text: str) -> bool:
        """Enforce canary-first, pause and per-wave concurrency within the claim lock.

        This is a management Job scheduling safety boundary, not an Agent updater.
        Rollout claims must never fan out just because rows are queued.
        """
        job_id = str(row["job_id"])
        target = str(row["target_id"])
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
            if not isinstance(payload, dict):
                return False
            canary_list = payload.get("canary_targets") or []
            if not isinstance(canary_list, list) or any(
                not isinstance(host, str) or not host for host in canary_list
            ):
                return False
            canaries = set(canary_list)
            wave_size = int(payload["wave_size"])
            threshold = int(payload["failure_threshold_percent"])
            if wave_size < 1 or wave_size > MAX_ROLLOUT_WAVE_SIZE or not 0 <= threshold <= 100:
                raise ValueError("invalid scheduling bounds")
        except (TypeError, KeyError, ValueError, json.JSONDecodeError):
            return False
        if payload.get("operator_paused") or payload.get("rollout_state") in ("PAUSED", "HALTED"):
            return False

        states = {
            str(r["target_id"]): str(r["status"])
            for r in self.conn.execute(
                "SELECT target_id,status FROM management_job_targets WHERE job_id=?",
                (job_id,),
            )
        }
        if not canaries.issubset(states):
            return False

        def halt(reason: str) -> bool:
            self._halt_rollout_unlocked(job_id, reason, now_text=now_text)
            return False

        if any(states[host] in (FAILED, CANCELLED) for host in canaries):
            return halt("CANARY_FAILED")
        if canaries and not all(states[host] == SUCCEEDED for host in canaries):
            if target not in canaries:
                return False
        elif payload.get("rollout_state") == "CANARY":
            payload["rollout_state"] = "WAVE"
            self.conn.execute(
                "UPDATE management_jobs SET payload_json=?,updated_at=? WHERE id=?",
                (_json(payload, field="Managed Update rollout payload"), now_text, job_id),
            )

        completed = sum(s in TERMINAL_STATUSES for s in states.values())
        failures = sum(s == FAILED for s in states.values())
        if failures and completed and 100 * failures >= threshold * completed:
            return halt("FAILURE_THRESHOLD_REACHED")

        running = sum(s == RUNNING for s in states.values())
        if running >= wave_size:
            return False

        # A staged wave is a bounded *batch*, not a sliding concurrency
        # window. A fast completion must not admit the next wave while
        # another Host in the current wave remains in flight. Apply the
        # barrier both to multi-batch canaries and to ordinary Host waves.
        # Sorting persisted target IDs keeps the boundary stable across
        # independent worker connections and Server restarts.
        group = sorted(
            canaries if target in canaries
            else (host for host in states if host not in canaries)
        )
        if target not in group:
            return False
        preceding_count = (group.index(target) // wave_size) * wave_size
        if any(states[host] not in TERMINAL_STATUSES
               for host in group[:preceding_count]):
            return False
        return True

    def _claim_targets_unlocked(
        self,
        *,
        worker_id: str,
        limit: int = 1,
        target_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        worker = _bounded_text(worker_id, field="Management Job worker")
        if type(limit) is not int or limit < 1:
            raise ControlPlaneError("Management Job claim limit must be a positive integer.")
        count = min(limit, MAX_CLAIM_BATCH)
        # A small requested claim batch must not hide eligible canaries behind
        # alphabetically earlier non-canary targets or other paused jobs.
        scan_limit = min(
            MAX_ACTIVE_JOBS * MAX_JOB_TARGETS,
            max(count, self.max_targets * min(self.max_active_jobs, MAX_ACTIVE_JOBS)),
        )
        current_dt = now or _utc_now()
        current = _utc_text(current_dt)
        lease_until = _utc_text(current_dt + timedelta(seconds=self.lease_seconds))
        self.expire_deadlines(now=current_dt)
        self.recover_expired_claims(now=current_dt)
        self._begin()
        try:
            target_filter = str(target_id or "").strip()
            if target_filter:
                # Agent RPC cannot accept staged rollout Jobs until the
                # signed updater, health checks and rollback are qualified.
                # Leave these Jobs queued, rather than handing an unsupported
                # operation to an Agent and falsely advancing canary waves.
                rows = self.conn.execute(
                    "SELECT t.job_id,t.target_id,j.job_type,j.payload_json,j.deadline_at "
                    "FROM management_job_targets t "
                    "JOIN management_jobs j ON j.id=t.job_id "
                    "WHERE t.status='QUEUED' AND j.status IN ('QUEUED','RUNNING') "
                    "AND j.cancel_requested=0 AND j.deadline_at>? AND t.target_id=? "
                    "AND j.job_type!=? "
                    "ORDER BY j.created_at,t.target_id LIMIT ?",
                    (current, target_filter, ROLLOUT_JOB_TYPE, scan_limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT t.job_id,t.target_id,j.job_type,j.payload_json,j.deadline_at "
                    "FROM management_job_targets t "
                    "JOIN management_jobs j ON j.id=t.job_id "
                    "WHERE t.status='QUEUED' AND j.status IN ('QUEUED','RUNNING') "
                    "AND j.cancel_requested=0 AND j.deadline_at>? "
                    "ORDER BY j.created_at,t.target_id LIMIT ?",
                    (current, scan_limit),
                ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                if len(claimed) >= count:
                    break
                kind = str(row["job_type"])
                if kind in MUTATING_AGENT_JOB_TYPES:
                    host = self.conn.execute(
                        "SELECT trust_status,admission_state,status FROM clients WHERE id=?",
                        (str(row["target_id"]),),
                    ).fetchone()
                    if (not host or str(host["trust_status"] or "") != "trusted"
                        or str(host["admission_state"] or "") != "APPROVED"
                        or str(host["status"] or "").lower() in ("retired","removed","deleted")):
                        # Keep queued work unclaimed; let its bounded deadline
                        # expire rather than execute after a quarantine/revoke.
                        continue
                if kind == ROLLOUT_JOB_TYPE:
                    if not self._rollout_claim_allowed_unlocked(row, now_text=current):
                        continue
                token = secrets.token_hex(16)
                updated = self.conn.execute(
                    "UPDATE management_job_targets SET status='RUNNING',worker_id=?,"
                    "claim_token=?,attempt=attempt+1,started_at=COALESCE(started_at,?),"
                    "lease_expires_at=?,updated_at=? "
                    "WHERE job_id=? AND target_id=? AND status='QUEUED'",
                    (
                        worker,
                        token,
                        current,
                        lease_until,
                        current,
                        row["job_id"],
                        row["target_id"],
                    ),
                ).rowcount
                if updated != 1:
                    continue
                self.conn.execute(
                    "UPDATE management_jobs SET status='RUNNING',"
                    "started_at=COALESCE(started_at,?),updated_at=? WHERE id=?",
                    (current, current, row["job_id"]),
                )
                try:
                    payload = json.loads(str(row["payload_json"] or "{}"))
                except ValueError:
                    payload = {}
                claimed.append(
                    {
                        "job_id": str(row["job_id"]),
                        "target_id": str(row["target_id"]),
                        "job_type": str(row["job_type"]),
                        "payload": payload,
                        "claim_token": token,
                        "lease_expires_at": lease_until,
                        "deadline_at": str(row["deadline_at"]),
                    }
                )
            self.conn.execute("COMMIT")
            return claimed
        except Exception:
            self._rollback()
            raise

    def _complete_target_unlocked(
        self,
        *,
        job_id: str,
        target_id: str,
        claim_token: str,
        status: str,
        result: Optional[dict[str, Any]] = None,
        error: str = "",
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        terminal = str(status or "").strip().upper()
        if terminal not in TERMINAL_STATUSES:
            raise ControlPlaneError("Management Job target result must be terminal.")
        current_dt = now or _utc_now()
        current = _utc_text(current_dt)
        self._begin()
        try:
            claim = self.conn.execute(
                "SELECT t.status,t.claim_token,t.lease_expires_at,j.deadline_at "
                "FROM management_job_targets t JOIN management_jobs j ON j.id=t.job_id "
                "WHERE t.job_id=? AND t.target_id=?",
                (str(job_id), str(target_id)),
            ).fetchone()
            if (
                not claim
                or str(claim["status"]) != RUNNING
                or str(claim["claim_token"]) != str(claim_token)
            ):
                raise ControlPlaneError(
                    "Management Job target claim is stale or no longer running."
                )
            late_reason = ""
            try:
                if current_dt >= _parse_utc(str(claim["deadline_at"])):
                    late_reason = "DEADLINE_EXCEEDED"
                elif claim["lease_expires_at"] and current_dt >= _parse_utc(
                    str(claim["lease_expires_at"])
                ):
                    late_reason = "WORKER_LEASE_EXPIRED"
            except ValueError:
                late_reason = "INVALID_EXECUTION_DEADLINE"
            if late_reason:
                terminal = FAILED
                result = {}
                error = late_reason
            updated = self.conn.execute(
                "UPDATE management_job_targets SET status=?,finished_at=?,lease_expires_at=NULL,"
                "updated_at=?,result_json=?,error=? "
                "WHERE job_id=? AND target_id=? AND status='RUNNING' AND claim_token=?",
                (
                    terminal,
                    current,
                    current,
                    _json(result or {}, field="Management Job target result"),
                    str(error or "")[:1024],
                    str(job_id),
                    str(target_id),
                    str(claim_token),
                ),
            ).rowcount
            if updated != 1:
                raise ControlPlaneError(
                    "Management Job target claim is stale or no longer running."
                )
            if terminal == FAILED and error:
                self.conn.execute(
                    "UPDATE management_jobs SET last_error=?,updated_at=? WHERE id=?",
                    (str(error)[:1024], current, str(job_id)),
                )
            self._refresh_job_status(str(job_id), now_text=current)
            if terminal == FAILED:
                # Record a failed canary or reached batch threshold immediately,
                # before a subsequent worker polls the remaining queue.
                rollout = self.conn.execute(
                    "SELECT id AS job_id,job_type,payload_json FROM management_jobs WHERE id=?",
                    (str(job_id),),
                ).fetchone()
                if rollout and str(rollout["job_type"]) == ROLLOUT_JOB_TYPE:
                    self._rollout_claim_allowed_unlocked(
                        {"job_id": str(job_id), "target_id": str(target_id),
                         "payload_json": rollout["payload_json"]},
                        now_text=current,
                    )
            self.conn.execute("COMMIT")
        except Exception:
            self._rollback()
            raise
        return self.get(str(job_id))

    def _expire_deadlines_unlocked(self, *, now: Optional[datetime] = None) -> int:
        current = _utc_text(now or _utc_now())
        self._begin()
        try:
            ids = [
                str(row[0])
                for row in self.conn.execute(
                    "SELECT id FROM management_jobs WHERE status IN ('QUEUED','RUNNING') "
                    "AND deadline_at<=?",
                    (current,),
                ).fetchall()
            ]
            for job_id in ids:
                self.conn.execute(
                    "UPDATE management_job_targets SET status='FAILED',finished_at=?,"
                    "lease_expires_at=NULL,updated_at=?,error='DEADLINE_EXCEEDED' "
                    "WHERE job_id=? AND status IN ('QUEUED','RUNNING')",
                    (current, current, job_id),
                )
                self.conn.execute(
                    "UPDATE management_jobs SET status='FAILED',finished_at=?,updated_at=?,"
                    "last_error='DEADLINE_EXCEEDED' WHERE id=?",
                    (current, current, job_id),
                )
                self._halt_rollout_unlocked(
                    job_id, "DEADLINE_EXCEEDED", now_text=current
                )
            self.conn.execute("COMMIT")
            return len(ids)
        except Exception:
            self._rollback()
            raise

    def _recover_expired_claims_unlocked(self, *, now: Optional[datetime] = None) -> int:
        current = _utc_text(now or _utc_now())
        self._begin()
        try:
            rows = self.conn.execute(
                "SELECT DISTINCT job_id FROM management_job_targets "
                "WHERE status='RUNNING' AND lease_expires_at IS NOT NULL "
                "AND lease_expires_at<=?",
                (current,),
            ).fetchall()
            job_ids = [str(row[0]) for row in rows]
            self.conn.execute(
                "UPDATE management_job_targets SET status='FAILED',finished_at=?,"
                "lease_expires_at=NULL,updated_at=?,error='WORKER_LEASE_EXPIRED' "
                "WHERE status='RUNNING' AND lease_expires_at IS NOT NULL "
                "AND lease_expires_at<=?",
                (current, current, current),
            )
            for job_id in job_ids:
                self.conn.execute(
                    "UPDATE management_jobs SET last_error='WORKER_LEASE_EXPIRED',updated_at=? "
                    "WHERE id=?",
                    (current, job_id),
                )
                self._refresh_job_status(job_id, now_text=current)
                # An expired claim may have already changed its Agent runtime;
                # never continue another wave without reconciling that Host.
                self._halt_rollout_unlocked(
                    job_id, "WORKER_LEASE_EXPIRED", now_text=current
                )
            self.conn.execute("COMMIT")
            return len(job_ids)
        except Exception:
            self._rollback()
            raise

    def _recover_interrupted_unlocked(self, *, now: Optional[datetime] = None) -> int:
        """Fail in-flight targets after process restart; never invent success or resume."""
        current = _utc_text(now or _utc_now())
        self._begin()
        try:
            rows = self.conn.execute(
                "SELECT DISTINCT job_id FROM management_job_targets WHERE status='RUNNING'"
            ).fetchall()
            job_ids = [str(row[0]) for row in rows]
            for job_id in job_ids:
                # The operation contract has no safe resumability in 3.0. Once any
                # target was in flight across restart, fail every unfinished target
                # in that Job rather than silently continuing a partially interrupted
                # operation.
                self.conn.execute(
                    "UPDATE management_job_targets SET status='FAILED',finished_at=?,"
                    "lease_expires_at=NULL,updated_at=?,error='SERVER_RESTART_INTERRUPTED' "
                    "WHERE job_id=? AND status IN ('QUEUED','RUNNING')",
                    (current, current, job_id),
                )
                self.conn.execute(
                    "UPDATE management_jobs SET status='FAILED',finished_at=?,updated_at=?,"
                    "last_error='SERVER_RESTART_INTERRUPTED' WHERE id=?",
                    (current, current, job_id),
                )
                self._halt_rollout_unlocked(
                    job_id, "SERVER_RESTART_INTERRUPTED", now_text=current
                )
            self.conn.execute("COMMIT")
            return len(job_ids)
        except Exception:
            self._rollback()
            raise

    def _rollout_arguments(
        self, *, targets: Iterable[str], artifact: Mapping[str, Any],
        canary_targets: Iterable[str] = (), wave_size: int = 10,
        failure_threshold_percent: int = 0,
    ) -> tuple[tuple[str, ...], dict[str, Any]]:
        """Validate one immutable request shape for both preview and apply."""
        target_ids = _normalize_targets(targets, max_targets=self.max_targets)
        if (isinstance(canary_targets, (str, bytes, bytearray, Mapping))
            or not isinstance(canary_targets, Iterable)):
            raise ControlPlaneError("Rollout canary targets must be a Host ID collection.")
        requested_canaries = tuple(canary_targets)
        canaries = (
            _normalize_targets(requested_canaries, max_targets=self.max_targets)
            if requested_canaries else ()
        )
        if set(canaries) - set(target_ids):
            raise ControlPlaneError("Rollout canary target is outside the explicit target set.")
        if type(wave_size) is not int or type(failure_threshold_percent) is not int:
            raise ControlPlaneError("Rollout wave size and failure threshold must be integers.")
        size = wave_size
        threshold = failure_threshold_percent
        if size < 1 or size > min(MAX_ROLLOUT_WAVE_SIZE, self.max_targets):
            raise ControlPlaneError("Rollout wave size is outside the bounded 3.0 range.")
        if not canaries:
            canaries = tuple(target_ids[:size])
        if threshold < 0 or threshold > MAX_ROLLOUT_FAILURE_THRESHOLD:
            raise ControlPlaneError("Rollout failure threshold must be between 0 and 100 percent.")
        if not isinstance(artifact, dict):
            raise ControlPlaneError("Rollout artifact identity must be an object.")
        required = ("version", "source_ref", "sha256")
        normalized_artifact = {key: str(artifact.get(key) or "").strip() for key in required}
        if any(not normalized_artifact[key] for key in required):
            raise ControlPlaneError("Rollout artifact requires immutable version, source_ref, and sha256.")
        ref = normalized_artifact["source_ref"]
        if len(ref) != 40 or any(c not in "0123456789abcdefABCDEF" for c in ref):
            raise ControlPlaneError("Rollout source_ref must be an immutable 40-character Git SHA.")
        normalized_artifact["source_ref"] = ref.lower()
        if len(normalized_artifact["sha256"]) != 64 or any(c not in "0123456789abcdefABCDEF" for c in normalized_artifact["sha256"]):
            raise ControlPlaneError("Rollout artifact sha256 must be a 64-character hexadecimal digest.")
        return target_ids, {
            "artifact": normalized_artifact,
            "canary_targets": list(canaries),
            "wave_size": size,
            "failure_threshold_percent": threshold,
            "rollout_state": "CANARY" if canaries else "WAVE",
        }

    def _rollout_target_approved(self, host_id: str) -> bool:
        row = self.conn.execute(
            "SELECT trust_status,admission_state,status FROM clients WHERE id=?",
            (host_id,),
        ).fetchone()
        return bool(
            row and str(row["trust_status"] or "") == "trusted"
            and str(row["admission_state"] or "") == "APPROVED"
            and str(row["status"] or "").lower() not in ("retired", "removed", "deleted")
        )

    def preview_rollout(
        self, *, targets: Iterable[str], requested_by: str,
        artifact: Mapping[str, Any], canary_targets: Iterable[str] = (),
        wave_size: int = 10, failure_threshold_percent: int = 0,
    ) -> dict[str, Any]:
        """Read-only assessment, not an Apply plan or approval to update Agents."""
        _bounded_text(requested_by, field="Management Job actor")
        target_ids, payload = self._rollout_arguments(
            targets=targets, artifact=artifact, canary_targets=canary_targets,
            wave_size=wave_size,
            failure_threshold_percent=failure_threshold_percent,
        )
        from drlink_control_plane import agent_heartbeat_fresh

        with self._lock:
            blocked = [host for host in target_ids if not self._rollout_target_approved(host)]
            observations = []
            target_version = str(payload["artifact"]["version"])
            for host_id in target_ids:
                row = self.conn.execute(
                    "SELECT agent_version,agent_platform,agent_heartbeat_at,agent_lifecycle_state "
                    "FROM clients WHERE id=?", (host_id,),
                ).fetchone()
                installed = str(row["agent_version"] or "").strip() if row else ""
                platform = str(row["agent_platform"] or "").strip() if row else ""
                lifecycle = (
                    str(row["agent_lifecycle_state"] or "legacy").strip().lower()
                    if row else "unknown"
                )
                heartbeat = row["agent_heartbeat_at"] if row else None
                recent = bool(
                    lifecycle == "connected" and agent_heartbeat_fresh(heartbeat)
                )
                relation = (
                    "UNKNOWN" if not installed
                    else "SAME_VERSION" if installed == target_version
                    else "DIFFERENT"
                )
                observations.append({
                    "target_id": host_id,
                    "current_version": installed or "unknown",
                    "target_version": target_version,
                    "platform": platform or "unknown",
                    "version_relation": relation,
                    "last_heartbeat": heartbeat,
                    "agent_lifecycle_state": lifecycle,
                    "agent_heartbeat_fresh": recent,
                    # A recent authenticated heartbeat is not current reachability,
                    # signed release provenance or a verified update capability.
                    "provenance": "NOT_VERIFIED",
                    "update_available": "UNKNOWN",
                })
        return {
            "read_only": True, "eligible": not blocked,
            "target_observations": observations,
            "targets": list(target_ids), "target_count": len(target_ids),
            "blocked_targets": blocked,
            "canary_targets": list(payload["canary_targets"]),
            "wave_size": payload["wave_size"],
            "planned_batches": _planned_rollout_batches(
                target_ids, payload["canary_targets"], payload["wave_size"]
            ),
            "failure_threshold_percent": payload["failure_threshold_percent"],
            "artifact": dict(payload["artifact"]),
            "artifact_qualification": "NOT_VERIFIED",
            "ready_to_apply": False,
            "qualification_note": (
                "Host admission and artifact identity shape only; actual build "
                "provenance, signatures, Agent updater and rollback are not qualified."
            ),
            "requires_fresh_validation_on_apply": True,
            "creates_job": False,
        }

    def enqueue_rollout(
        self,
        *,
        targets: Iterable[str],
        requested_by: str,
        artifact: Mapping[str, Any],
        canary_targets: Iterable[str] = (),
        wave_size: int = 10,
        failure_threshold_percent: int = 0,
        timeout_seconds: int = DEFAULT_JOB_TIMEOUT_SECONDS,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Queue a bounded manual Agent update rollout.

        The immutable artifact identity is carried as Job payload. Execution remains
        Agent-owned and no SQLite transaction is held while an Agent updates.
        """
        target_ids = _normalize_targets(targets, max_targets=self.max_targets)
        # Materialize a caller-provided iterator once; consuming it to check
        # emptiness must not silently discard the actual canary selection.
        if (isinstance(canary_targets, (str, bytes, bytearray, Mapping))
            or not isinstance(canary_targets, Iterable)):
            raise ControlPlaneError("Rollout canary targets must be a Host ID collection.")
        requested_canaries = tuple(canary_targets)
        canaries = (
            _normalize_targets(requested_canaries, max_targets=self.max_targets)
            if requested_canaries else ()
        )
        unknown = sorted(set(canaries) - set(target_ids))
        if unknown:
            raise ControlPlaneError("Rollout canary target is outside the explicit target set.")
        if type(wave_size) is not int or type(failure_threshold_percent) is not int:
            raise ControlPlaneError("Rollout wave size and failure threshold must be integers.")
        size = wave_size
        threshold = failure_threshold_percent
        if size < 1 or size > min(MAX_ROLLOUT_WAVE_SIZE, self.max_targets):
            raise ControlPlaneError("Rollout wave size is outside the bounded 3.0 range.")
        # When no explicit canary is provided, treat the first bounded wave
        # as the canary gate instead of fanning out to every Agent immediately.
        if not canaries:
            canaries = tuple(target_ids[:size])
        if threshold < 0 or threshold > MAX_ROLLOUT_FAILURE_THRESHOLD:
            raise ControlPlaneError("Rollout failure threshold must be between 0 and 100 percent.")
        if not isinstance(artifact, dict):
            raise ControlPlaneError("Rollout artifact identity must be an object.")
        required = ("version", "source_ref", "sha256")
        normalized_artifact = {key: str(artifact.get(key) or "").strip() for key in required}
        if any(not normalized_artifact[key] for key in required):
            raise ControlPlaneError("Rollout artifact requires immutable version, source_ref, and sha256.")
        ref = normalized_artifact["source_ref"]
        if len(ref) != 40 or any(c not in "0123456789abcdefABCDEF" for c in ref):
            raise ControlPlaneError("Rollout source_ref must be an immutable 40-character Git SHA.")
        normalized_artifact["source_ref"] = ref.lower()
        if len(normalized_artifact["sha256"]) != 64 or any(c not in "0123456789abcdefABCDEF" for c in normalized_artifact["sha256"]):
            raise ControlPlaneError("Rollout artifact sha256 must be a 64-character hexadecimal digest.")
        payload = {
            "artifact": normalized_artifact,
            "canary_targets": list(canaries),
            "wave_size": size,
            "failure_threshold_percent": threshold,
            "rollout_state": "CANARY" if canaries else "WAVE",
        }
        with self._lock:
            # A mutable target list is never authority for a staged update.
            # Verify current trust and admission at submission, then again
            # during claim to close quarantine races.
            for host_id in target_ids:
                row = self.conn.execute(
                    "SELECT trust_status,admission_state,status FROM clients WHERE id=?",
                    (host_id,),
                ).fetchone()
                if (not row or str(row["trust_status"] or "") != "trusted"
                    or str(row["admission_state"] or "") != "APPROVED"
                    or str(row["status"] or "").lower() in ("retired","removed","deleted")):
                    raise ControlPlaneError("Managed Agent rollout target is not approved and trusted.")
            return self._enqueue_unlocked(
                job_type=ROLLOUT_JOB_TYPE,
                targets=target_ids,
                requested_by=requested_by,
                resource_type="managed-host",
                resource_ref="explicit-rollout-targets",
                payload=payload,
                timeout_seconds=timeout_seconds,
                now=now,
                _validated_rollout=True,
            )

    def rollout_control(self, job_id: str, *, action: str) -> dict[str, Any]:
        """Pause/resume a rollout without changing artifact or target identity."""
        verb = str(action or "").strip().lower()
        if verb not in ("pause", "resume"):
            raise ControlPlaneError("Rollout control action must be pause or resume.")
        with self._lock:
            self._begin()
            try:
                row = self.conn.execute(
                    "SELECT job_type,status,payload_json,cancel_requested "
                    "FROM management_jobs WHERE id=?", (str(job_id),)
                ).fetchone()
                if not row or str(row["job_type"]) != ROLLOUT_JOB_TYPE:
                    raise ControlPlaneError("Managed Update rollout was not found.")
                if str(row["status"]) in TERMINAL_STATUSES:
                    raise ControlPlaneError("Completed rollout cannot be paused or resumed.")
                if int(row["cancel_requested"] or 0):
                    raise ControlPlaneError(
                        "Cancelled Agent rollout cannot be paused or resumed."
                    )
                payload = json.loads(str(row["payload_json"] or "{}"))
                if (
                    not isinstance(payload, dict)
                    or payload.get("rollout_state") == "HALTED"
                    or payload.get("halt_reason")
                ):
                    raise ControlPlaneError(
                        "Halted Agent rollout cannot be paused or resumed. "
                        "Inspect failed targets and start a new qualified plan."
                    )
                payload["operator_paused"] = verb == "pause"
                if verb == "pause":
                    payload["rollout_state"] = "PAUSED"
                else:
                    canaries = payload.get("canary_targets") or []
                    states = {
                        str(target["target_id"]): str(target["status"])
                        for target in self.conn.execute(
                            "SELECT target_id,status FROM management_job_targets WHERE job_id=?",
                            (str(job_id),),
                        )
                    }
                    payload["rollout_state"] = (
                        "WAVE" if canaries and all(states.get(host) == SUCCEEDED for host in canaries)
                        else "CANARY"
                    )
                self.conn.execute(
                    "UPDATE management_jobs SET payload_json=?,updated_at=? WHERE id=?",
                    (_json(payload, field="Managed Update rollout payload"), utc_now_iso(), str(job_id)),
                )
                self.conn.execute("COMMIT")
            except Exception:
                self._rollback()
                raise
            return self._get_unlocked(str(job_id))

    def enqueue(self, **kwargs) -> dict[str, Any]:
        if "_validated_rollout" in kwargs:
            raise ControlPlaneError("Rollout validation cannot be supplied by a generic Job caller.")
        with self._lock:
            return self._enqueue_unlocked(**kwargs)

    def cancel(self, job_id: str, *, now: Optional[datetime] = None) -> dict[str, Any]:
        with self._lock:
            return self._cancel_unlocked(job_id, now=now)

    def claim_targets(self, **kwargs) -> list[dict[str, Any]]:
        with self._lock:
            return self._claim_targets_unlocked(**kwargs)

    def claim_targets_for_target(
        self,
        *,
        target_id: str,
        worker_id: str,
        limit: int = 1,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        target = _bounded_text(target_id, field="Management Job target")
        with self._lock:
            return self._claim_targets_unlocked(
                worker_id=worker_id,
                limit=limit,
                target_id=target,
                now=now,
            )

    def complete_target(self, **kwargs) -> dict[str, Any]:
        with self._lock:
            return self._complete_target_unlocked(**kwargs)

    def expire_deadlines(self, *, now: Optional[datetime] = None) -> int:
        with self._lock:
            return self._expire_deadlines_unlocked(now=now)

    def recover_expired_claims(self, *, now: Optional[datetime] = None) -> int:
        with self._lock:
            return self._recover_expired_claims_unlocked(now=now)

    def recover_interrupted(self, *, now: Optional[datetime] = None) -> int:
        with self._lock:
            return self._recover_interrupted_unlocked(now=now)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._get_unlocked(job_id)

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            return self._is_cancel_requested_unlocked(job_id)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return job_operational_summary(self.conn, max_active_jobs=self.max_active_jobs)


class BoundedAgentRpcWorkerPool:
    """Bound ThreadPoolExecutor's otherwise-unbounded pending-work queue."""

    def __init__(self, *, max_workers: int = 8, max_pending: int = 16):
        self.max_workers = max(1, int(max_workers))
        self.max_pending = max(0, int(max_pending))
        self.capacity = self.max_workers + self.max_pending
        self._slots = threading.BoundedSemaphore(self.capacity)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="drlink-agent-rpc"
        )
        self._closed = False

    def close(self, *, wait: bool = True) -> None:
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def __enter__(self) -> "BoundedAgentRpcWorkerPool":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _run_claim(
        self,
        engine: ManagementJobEngine,
        claim: dict[str, Any],
        handler: Callable[[dict[str, Any]], Optional[dict[str, Any]]],
    ) -> dict[str, Any]:
        try:
            if engine.is_cancel_requested(claim["job_id"]):
                return engine.complete_target(
                    job_id=claim["job_id"],
                    target_id=claim["target_id"],
                    claim_token=claim["claim_token"],
                    status=CANCELLED,
                    error="CANCELLED_BEFORE_RPC",
                )
            if claim.get("job_type") == ROLLOUT_JOB_TYPE:
                # A generic callable does not prove signed artifact identity,
                # post-update health or rollback. Never report rollout success
                # from an unqualified handler, even if it returns a result.
                raise ControlPlaneError(
                    "AGENT_UPDATER_NOT_QUALIFIED: signed Agent updater and rollback are required."
                )
            result = handler(dict(claim))
            return engine.complete_target(
                job_id=claim["job_id"],
                target_id=claim["target_id"],
                claim_token=claim["claim_token"],
                status=SUCCEEDED,
                result=dict(result or {}),
            )
        except Exception as exc:
            try:
                return engine.complete_target(
                    job_id=claim["job_id"],
                    target_id=claim["target_id"],
                    claim_token=claim["claim_token"],
                    status=FAILED,
                    error=str(exc)[:1024],
                )
            except Exception:
                raise exc

    def dispatch_once(
        self,
        engine: ManagementJobEngine,
        handler: Callable[[dict[str, Any]], Optional[dict[str, Any]]],
        *,
        worker_id: str,
        limit: Optional[int] = None,
    ) -> list[Future]:
        if self._closed:
            raise ControlPlaneError("Agent RPC worker pool is closed.")
        wanted = min(
            self.capacity,
            max(1, int(limit if limit is not None else self.max_workers)),
        )
        reserved = 0
        for _ in range(wanted):
            if not self._slots.acquire(blocking=False):
                break
            reserved += 1
        if reserved == 0:
            return []
        try:
            claims = engine.claim_targets(worker_id=worker_id, limit=reserved)
        except Exception:
            for _ in range(reserved):
                self._slots.release()
            raise
        for _ in range(reserved - len(claims)):
            self._slots.release()
        futures: list[Future] = []
        for claim in claims:
            future = self._executor.submit(self._run_claim, engine, claim, handler)
            future.add_done_callback(lambda _f: self._slots.release())
            futures.append(future)
        return futures
