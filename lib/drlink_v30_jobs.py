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
from typing import Any, Callable, Iterable, Optional

from drlink_control_db import ControlPlaneError, open_control_db, utc_now_iso

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
JOB_STATUSES = frozenset({QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED})
TERMINAL_STATUSES = frozenset({SUCCEEDED, FAILED, CANCELLED})

ADMITTED_JOB_TYPES = frozenset({"doctor", "refresh", "version-check", "support-bundle", "remote-service-set", "remote-service-delete"})
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
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in targets:
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
    ) -> dict[str, Any]:
        kind = str(job_type or "").strip().lower()
        if kind not in ADMITTED_JOB_TYPES:
            raise ControlPlaneError(
                "Management Job type '%s' is not an admitted 3.0 safe job family." % kind
            )
        actor = _bounded_text(requested_by, field="Management Job actor")
        target_ids = _normalize_targets(targets, max_targets=self.max_targets)
        try:
            timeout = int(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("Management Job timeout must be an integer.") from exc
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

    def _claim_targets_unlocked(
        self,
        *,
        worker_id: str,
        limit: int = 1,
        target_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        worker = _bounded_text(worker_id, field="Management Job worker")
        count = max(1, min(int(limit), MAX_CLAIM_BATCH))
        current_dt = now or _utc_now()
        current = _utc_text(current_dt)
        lease_until = _utc_text(current_dt + timedelta(seconds=self.lease_seconds))
        self.expire_deadlines(now=current_dt)
        self.recover_expired_claims(now=current_dt)
        self._begin()
        try:
            target_filter = str(target_id or "").strip()
            if target_filter:
                rows = self.conn.execute(
                    "SELECT t.job_id,t.target_id,j.job_type,j.payload_json,j.deadline_at "
                    "FROM management_job_targets t "
                    "JOIN management_jobs j ON j.id=t.job_id "
                    "WHERE t.status='QUEUED' AND j.status IN ('QUEUED','RUNNING') "
                    "AND j.cancel_requested=0 AND j.deadline_at>? AND t.target_id=? "
                    "ORDER BY j.created_at,t.target_id LIMIT ?",
                    (current, target_filter, count),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT t.job_id,t.target_id,j.job_type,j.payload_json,j.deadline_at "
                    "FROM management_job_targets t "
                    "JOIN management_jobs j ON j.id=t.job_id "
                    "WHERE t.status='QUEUED' AND j.status IN ('QUEUED','RUNNING') "
                    "AND j.cancel_requested=0 AND j.deadline_at>? "
                    "ORDER BY j.created_at,t.target_id LIMIT ?",
                    (current, count),
                ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
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
            self.conn.execute("COMMIT")
            return len(job_ids)
        except Exception:
            self._rollback()
            raise

    def enqueue(self, **kwargs) -> dict[str, Any]:
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
