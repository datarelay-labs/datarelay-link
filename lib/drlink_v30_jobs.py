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


def _unexpired_claim_clock(value: Any, now: datetime) -> bool:
    """Accept only Core's canonical unexpired UTC-second claim timestamps."""
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        return False
    try:
        instant = _parse_utc(value)
        return _utc_text(instant) == value and instant > now
    except (TypeError, ValueError, OverflowError):
        return False


def _json(value: Any, *, max_bytes: int = 16384, field: str = "Management Job JSON") -> str:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ControlPlaneError("%s is not JSON serializable." % field) from exc
    if len(raw.encode("utf-8")) > max_bytes:
        raise ControlPlaneError("%s exceeds the %d-byte bound." % (field, max_bytes))
    return raw


def _strict_queued_job_payload(raw: Any) -> Optional[dict[str, Any]]:
    """Return only an unambiguous bounded Core-owned queued Job payload.

    Storage corruption is never authority to claim work with an invented
    empty payload. This parser is deliberately read-only and fail-closed.
    """
    if not isinstance(raw, str) or not raw:
        return None

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate Job payload field")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite Job payload number")

    try:
        if len(raw.encode("utf-8")) > 16384:
            return None
        value = json.loads(
            raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant,
        )
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _bounded_text(value: Any, *, field: str, max_len: int = 256) -> str:
    text = str(value or "").strip()
    if not text:
        raise ControlPlaneError("%s is required." % field)
    if len(text) > max_len:
        raise ControlPlaneError("%s is too long." % field)
    return text


def _normalize_targets(targets: Iterable[str], *, max_targets: int) -> tuple[str, ...]:
    # Strings iterate individual characters and mappings iterate keys; neither
    # represents an explicit collection of immutable Managed Host targets.
    if targets is None or isinstance(targets, (str, bytes, bytearray, Mapping)):
        raise ControlPlaneError("Management Job targets must be an iterable of text IDs.")
    try:
        iterator = iter(targets)
    except TypeError as exc:
        raise ControlPlaneError(
            "Management Job targets must be an iterable of text IDs."
        ) from exc
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in iterator:
        if not isinstance(raw, str):
            raise ControlPlaneError("Management Job target must be text.")
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
        # The authoritative Core queue must not silently turn a malformed
        # caller payload into an empty object or persist an executable array.
        if payload is not None and not isinstance(payload, dict):
            raise ControlPlaneError("Management Job payload must be an object.")
        # Do not coerce boolean, fractional or string deadlines into a real
        # Job: a changed timeout can expire a queued operation unexpectedly.
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
        payload = _strict_queued_job_payload(job["payload_json"])
        if payload is None:
            # A read-only Job detail must not present a corrupt queued
            # payload as a legitimate empty object or leak raw stored text.
            raise ControlPlaneError("Management Job stored payload is malformed.")
        out["payload"] = payload
        out["targets"] = []
        for row in targets:
            item = {key: row[key] for key in row.keys() if key != "result_json"}
            result = _strict_queued_job_payload(row["result_json"])
            if result is None:
                # A corrupt result must not appear as successful empty
                # evidence in Core/Web Job history.
                raise ControlPlaneError("Management Job stored result is malformed.")
            item["result"] = result
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
            # Only the exact validated Core rollout shape can authorize a
            # staged Agent claim. Never silently upgrade corrupt/missing
            # canaries to an unrestricted wave or coerce bool/float/string
            # bounds from persisted state.
            canary_list = payload.get("canary_targets")
            if not isinstance(canary_list, list) or not canary_list or any(
                not isinstance(host, str) or not host or host != host.strip()
                for host in canary_list
            ) or len(set(canary_list)) != len(canary_list):
                return False
            if payload.get("rollout_state") not in (
                "CANARY", "WAVE", "PAUSED", "HALTED"
            ):
                return False
            wave_size = payload.get("wave_size")
            threshold = payload.get("failure_threshold_percent")
            if type(wave_size) is not int or type(threshold) is not int:
                return False
            canaries = set(canary_list)
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
            payload["rollout_state"] = "HALTED"
            payload["halt_reason"] = reason
            self.conn.execute(
                "UPDATE management_jobs SET payload_json=?,last_error=?,updated_at=? WHERE id=?",
                (_json(payload, field="Managed Update rollout payload"), reason, now_text, job_id),
            )
            self.conn.execute(
                "UPDATE management_job_targets SET status='CANCELLED',finished_at=?,"
                "updated_at=?,error=? WHERE job_id=? AND status='QUEUED'",
                (now_text, now_text, reason, job_id),
            )
            self._refresh_job_status(job_id, now_text=now_text)
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
        # Claiming reserves Core leases. Reject invalid or coerced counts
        # before any deadline recovery, transaction or target state mutation.
        if type(limit) is not int or limit < 1:
            raise ControlPlaneError(
                "Management Job claim limit must be a positive integer."
            )
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
                # SQL TEXT ordering is not proof of an unexpired UTC deadline.
                # Refuse malformed or noncanonical persisted timestamps before
                # issuing a one-shot Agent lease.
                if not _unexpired_claim_clock(row["deadline_at"], current_dt):
                    continue
                # Never lease a Job whose persisted intent is malformed,
                # ambiguous, non-object, non-finite or outside the source
                # storage bound. A corrupted record remains QUEUED and
                # eventually expires rather than executing as empty intent.
                payload = _strict_queued_job_payload(row["payload_json"])
                if payload is None:
                    continue
                kind = str(row["job_type"])
                # A corrupted persisted Job family is not permission to
                # dispatch arbitrary Agent RPCs or synthetic success claims.
                if kind not in ADMITTED_JOB_TYPES:
                    continue
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
                # Completion, like claim dispatch, requires canonical, live
                # Core clocks. An absent or noncanonical RUNNING lease must
                # never validate an unverified Agent success acknowledgement.
                if not _unexpired_claim_clock(claim["deadline_at"], current_dt):
                    late_reason = (
                        "DEADLINE_EXCEEDED"
                        if current_dt >= _parse_utc(str(claim["deadline_at"]))
                        else "INVALID_EXECUTION_DEADLINE"
                    )
                elif not _unexpired_claim_clock(claim["lease_expires_at"], current_dt):
                    late_reason = (
                        "WORKER_LEASE_EXPIRED"
                        if current_dt >= _parse_utc(str(claim["lease_expires_at"]))
                        else "INVALID_EXECUTION_DEADLINE"
                    )
            except (TypeError, ValueError, OverflowError):
                late_reason = "INVALID_EXECUTION_DEADLINE"
            if late_reason:
                terminal = FAILED
                result = {}
                error = late_reason
            if terminal != SUCCEEDED:
                # Failed/cancelled work has no verified result payload. Keep
                # untrusted partial diagnostics or credentials out of the
                # authoritative Core Job history on every completion path.
                result = {}
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

    def _rollout_arguments(
        self, *, targets: Iterable[str], artifact: Mapping[str, Any],
        canary_targets: Iterable[str] = (), wave_size: int = 10,
        failure_threshold_percent: int = 20,
    ) -> tuple[tuple[str, ...], dict[str, Any]]:
        """Validate one immutable request shape for both preview and apply."""
        target_ids = _normalize_targets(targets, max_targets=self.max_targets)
        # Do not reinterpret string characters or mapping keys as canaries.
        if canary_targets is None or isinstance(
            canary_targets, (str, bytes, bytearray, Mapping)
        ):
            raise ControlPlaneError("Rollout canary targets must be a collection of IDs.")
        requested_canaries = tuple(canary_targets)
        canaries = (
            _normalize_targets(requested_canaries, max_targets=self.max_targets)
            if requested_canaries else ()
        )
        if set(canaries) - set(target_ids):
            raise ControlPlaneError("Rollout canary target is outside the explicit target set.")
        # A coerced bool, string or fraction must never alter a canary wave.
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
        wave_size: int = 10, failure_threshold_percent: int = 20,
    ) -> dict[str, Any]:
        """Read-only assessment, not an Apply plan or approval to update Agents."""
        _bounded_text(requested_by, field="Management Job actor")
        target_ids, payload = self._rollout_arguments(
            targets=targets, artifact=artifact, canary_targets=canary_targets,
            wave_size=wave_size,
            failure_threshold_percent=failure_threshold_percent,
        )
        with self._lock:
            blocked = [host for host in target_ids if not self._rollout_target_approved(host)]
            observations = []
            target_version = str(payload["artifact"]["version"])
            for host_id in target_ids:
                row = self.conn.execute(
                    "SELECT agent_version,agent_platform,agent_heartbeat_at "
                    "FROM clients WHERE id=?", (host_id,),
                ).fetchone()
                installed = str(row["agent_version"] or "").strip() if row else ""
                platform = str(row["agent_platform"] or "").strip() if row else ""
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
                    "last_heartbeat": row["agent_heartbeat_at"] if row else None,
                    # Version alone is not signed artifact identity and can be
                    # stale or represent different commits with equal labels.
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
        failure_threshold_percent: int = 20,
        timeout_seconds: int = DEFAULT_JOB_TIMEOUT_SECONDS,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Queue a bounded manual Agent update rollout.

        The immutable artifact identity is carried as Job payload. Execution remains
        Agent-owned and no SQLite transaction is held while an Agent updates.
        """
        target_ids = _normalize_targets(targets, max_targets=self.max_targets)
        # Preserve iterator-backed canaries while rejecting a mapping or
        # scalar masquerading as an explicit list of Host identities.
        if canary_targets is None or isinstance(
            canary_targets, (str, bytes, bytearray, Mapping)
        ):
            raise ControlPlaneError("Rollout canary targets must be a collection of IDs.")
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
                    "SELECT job_type,status,payload_json FROM management_jobs WHERE id=?", (str(job_id),)
                ).fetchone()
                if not row or str(row["job_type"]) != ROLLOUT_JOB_TYPE:
                    raise ControlPlaneError("Managed Update rollout was not found.")
                if str(row["status"]) in TERMINAL_STATUSES:
                    raise ControlPlaneError("Completed rollout cannot be paused or resumed.")
                # Pause/resume is not permission to repair or reinterpret a
                # corrupted Core rollout plan. Preserve the original bytes
                # and target state until the persisted intent is investigated.
                payload = _strict_queued_job_payload(row["payload_json"])
                artifact = payload.get("artifact") if payload is not None else None
                canaries = payload.get("canary_targets") if payload is not None else None
                wave_size = payload.get("wave_size") if payload is not None else None
                threshold = payload.get("failure_threshold_percent") if payload is not None else None
                state = payload.get("rollout_state") if payload is not None else None
                hexchars = frozenset("0123456789abcdefABCDEF")
                source_ref = artifact.get("source_ref") if isinstance(artifact, dict) else None
                sha256 = artifact.get("sha256") if isinstance(artifact, dict) else None
                version = artifact.get("version") if isinstance(artifact, dict) else None
                target_ids = {
                    str(target["target_id"]) for target in self.conn.execute(
                        "SELECT target_id FROM management_job_targets WHERE job_id=?",
                        (str(job_id),),
                    )
                }
                if (
                    not isinstance(payload, dict)
                    or not isinstance(version, str) or not version.strip()
                    or not isinstance(source_ref, str) or len(source_ref) != 40
                    or not all(ch in hexchars for ch in source_ref)
                    or not isinstance(sha256, str) or len(sha256) != 64
                    or not all(ch in hexchars for ch in sha256)
                    or not isinstance(canaries, list) or not canaries
                    or len(canaries) > self.max_targets
                    or any(not isinstance(host, str) or not host
                           or host != host.strip() for host in canaries)
                    or len(set(canaries)) != len(canaries)
                    or not set(canaries).issubset(target_ids)
                    or type(wave_size) is not int
                    or not 1 <= wave_size <= min(MAX_ROLLOUT_WAVE_SIZE, self.max_targets)
                    or type(threshold) is not int
                    or not 0 <= threshold <= MAX_ROLLOUT_FAILURE_THRESHOLD
                    or state not in ("CANARY", "WAVE", "PAUSED", "HALTED")
                    or type(payload.get("operator_paused", False)) is not bool
                ):
                    raise ControlPlaneError("Management Job stored rollout payload is malformed.")
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
        # A claimed Job may sit in an executor queue until Core's lease or
        # deadline has expired. Check again at the worker execution boundary:
        # executing it then sending a downgraded completion is not safe.
        now = _utc_now()
        if (
            not _unexpired_claim_clock(claim.get("lease_expires_at"), now)
            or not _unexpired_claim_clock(claim.get("deadline_at"), now)
        ):
            raise ControlPlaneError(
                "Management Job claim UNKNOWN; inspect Core lease and deadline before retrying."
            )
        if engine.is_cancel_requested(claim["job_id"]):
            # An ambiguous CANCELLED receipt must not be re-reported FAILED.
            try:
                return engine.complete_target(
                    job_id=claim["job_id"],
                    target_id=claim["target_id"],
                    claim_token=claim["claim_token"],
                    status=CANCELLED,
                    error="CANCELLED_BEFORE_RPC",
                )
            except Exception:
                # Do not expose Core persistence/transport errors that may
                # include private fields, or invent a terminal Job result.
                raise ControlPlaneError(
                    "Management Job completion receipt UNKNOWN; inspect Core before retrying."
                ) from None
        try:
            if claim.get("job_type") == ROLLOUT_JOB_TYPE:
                # A generic callable does not prove signed artifact identity,
                # post-update health or rollback. Never report rollout success
                # from an unqualified handler, even if it returns a result.
                raise ControlPlaneError(
                    "AGENT_UPDATER_NOT_QUALIFIED: signed Agent updater and rollback are required."
                )
            result = dict(handler(dict(claim)) or {})
        except Exception:
            try:
                return engine.complete_target(
                    job_id=claim["job_id"],
                    target_id=claim["target_id"],
                    claim_token=claim["claim_token"],
                    status=FAILED,
                    # Handler exception text can include secrets or payloads;
                    # persist only fixed codes in Core's queryable Job history.
                    # Preserve the explicit unqualified-rollout safety reason.
                    error=(
                        "AGENT_UPDATER_NOT_QUALIFIED"
                        if claim.get("job_type") == ROLLOUT_JOB_TYPE
                        else "AGENT_JOB_EXECUTION_FAILED"
                    ),
                )
            except Exception:
                # An unconfirmed Core failure receipt must never expose the
                # handler's raw exception (possibly credentials) to a worker log.
                # Core remains authoritative: do not guess at terminal status.
                raise ControlPlaneError(
                    "Management Job completion receipt UNKNOWN; inspect Core before retrying."
                ) from None
        # Completion acknowledgement can fail AFTER Core committed SUCCEEDED.
        # Never send a contradictory FAILED completion for an executed handler
        # or expose raw completion errors that may contain sensitive payloads.
        try:
            return engine.complete_target(
                job_id=claim["job_id"],
                target_id=claim["target_id"],
                claim_token=claim["claim_token"],
                status=SUCCEEDED,
                result=result,
            )
        except Exception:
            raise ControlPlaneError(
                "Management Job completion receipt UNKNOWN; inspect Core before retrying."
            ) from None

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
        for index, claim in enumerate(claims):
            try:
                future = self._executor.submit(self._run_claim, engine, claim, handler)
            except Exception:
                # A concurrent shutdown/rejected submission must not leak
                # reservations for work never accepted by the executor.
                # Core retains the claimed targets for lease recovery; do not
                # fabricate a completed Agent execution or release its claim.
                for _ in range(len(claims) - index):
                    self._slots.release()
                raise
            future.add_done_callback(lambda _f: self._slots.release())
            futures.append(future)
        return futures
