#!/usr/bin/env python3
"""Data Relay Link 3.0 durable audit spool and SQLite ingestor.

Privilege-separated access/egress processes can durably enqueue secret-safe
ACCESS_DECISION events without receiving SQLite write authority. Core seals
bounded spool segments and ingests them in short idempotent transactions.
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from drlink_control_db import ControlPlaneError, resolve_root, utc_now_iso

AUDIT_SCHEMA_VERSION = 1
ACCESS_DECISION = "ACCESS_DECISION"
MAX_EVENT_BYTES = 8 * 1024
DEFAULT_SEGMENT_BYTES = 256 * 1024
DEFAULT_HIGH_WATER_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_SEGMENTS_PER_INGEST = 4

# Pre-3.0 connection JSONL lacks the stable event identity and attribution
# guarantees required by the unified v3 audit authority. Preserve it only as
# forensic evidence under the existing backup/rotation lifecycle; never import
# it as authoritative audit or use it as a live/query backend.
LEGACY_CONNECTION_EVIDENCE_POLICY = "PRESERVE_PRE_V3_FORENSIC"
LEGACY_CONNECTION_EVIDENCE_RELATIVE_PATHS = (
    "var/log/drlink/access/connections.jsonl",
    "var/log/drlink/access-conn.jsonl",
    "var/log/drlink/egress/connections.jsonl",
    "var/log/drlink/egress-conn.jsonl",
)


def legacy_connection_evidence_contract(root: Optional[str] = None) -> dict[str, Any]:
    resolved = resolve_root(root)
    base = Path(resolved) if resolved else Path("/")
    return {
        "policy": LEGACY_CONNECTION_EVIDENCE_POLICY,
        "state_class": "FORENSIC_EVIDENCE",
        "authoritative": False,
        "import_to_unified_audit": False,
        "query_backend": False,
        "live_backend": False,
        "upgrade_action": "PRESERVE_IN_PLACE",
        "paths": [str(base / rel) for rel in LEGACY_CONNECTION_EVIDENCE_RELATIVE_PATHS],
    }


SOURCE_META_KEYS = frozenset({
    "ip", "managed_host_id", "managed_host_name",
    "ai_identity", "relay_id", "relay_name",
})
DESTINATION_META_KEYS = frozenset({
    "host", "ip", "port", "protocol", "service_id",
    "service_name", "observed_sni",
})
ACCESS_EVENT_KEYS = frozenset({
    "schema_version", "category", "event_type", "occurred_at", "source",
    "actor_type", "actor_id", "delegated_actor_id", "interface", "action",
    "resource_type", "resource_id", "result", "reason_code", "correlation_id",
    "request_id", "session_id", "matched_policy", "source_meta",
    "destination_meta", "event_id", "source_sequence",
})


class AuditUnavailable(ControlPlaneError):
    """Durable audit enqueue is unavailable; would-be ALLOW must fail closed."""


class AuditEventInvalid(ControlPlaneError):
    """Spool contains a malformed/non-secret-safe event and is retained."""


def default_access_spool_root(plane: str, root: Optional[str] = None) -> Path:
    family = str(plane or "").strip().lower()
    if family == "remote":
        rel = Path("var/log/drlink/access/audit-spool")
    elif family == "internet":
        rel = Path("var/log/drlink/egress/audit-spool")
    else:
        raise ControlPlaneError("Audit spool is supported for remote|internet access.")
    resolved = resolve_root(root)
    return (Path(resolved) / rel) if resolved else (Path("/") / rel)


def _safe_text(value: Any, *, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def _safe_meta(value: Optional[dict[str, Any]], allowed: frozenset[str]) -> dict[str, Any]:
    if not value:
        return {}
    if not isinstance(value, dict):
        raise AuditEventInvalid("Audit metadata must be an object.")
    out: dict[str, Any] = {}
    for key in allowed:
        if key not in value or value[key] is None:
            continue
        item = value[key]
        if key == "port":
            try:
                port = int(item)
            except (TypeError, ValueError) as exc:
                raise AuditEventInvalid("Audit destination port must be an integer.") from exc
            if port < 1 or port > 65535:
                raise AuditEventInvalid("Audit destination port is out of range.")
            out[key] = port
        else:
            out[key] = _safe_text(item, limit=512)
    return out


def build_access_decision_event(
    *,
    source: str,
    event_type: str,
    result: str,
    resource_type: str = "",
    resource_id: str = "",
    action: str = "authorize",
    reason_code: str = "",
    actor_type: str = "",
    actor_id: str = "",
    delegated_actor_id: str = "",
    interface: str = "",
    correlation_id: str = "",
    request_id: str = "",
    session_id: str = "",
    matched_policy: Optional[list[str]] = None,
    source_meta: Optional[dict[str, Any]] = None,
    destination_meta: Optional[dict[str, Any]] = None,
    occurred_at: Optional[str] = None,
) -> dict[str, Any]:
    decision = str(result or "").strip().upper()
    if decision not in ("ALLOW", "DENY"):
        raise AuditEventInvalid("ACCESS_DECISION result must be ALLOW or DENY.")
    source_name = _safe_text(source, limit=128)
    event_name = _safe_text(event_type, limit=128)
    if not source_name or not event_name:
        raise AuditEventInvalid("Audit source and event_type are required.")
    policies = []
    seen = set()
    for item in matched_policy or []:
        text = _safe_text(item, limit=256)
        if not text or text in seen:
            continue
        seen.add(text)
        policies.append(text)
        if len(policies) >= 32:
            break
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "category": ACCESS_DECISION,
        "event_type": event_name,
        "occurred_at": _safe_text(occurred_at or utc_now_iso(), limit=64),
        "source": source_name,
        "actor_type": _safe_text(actor_type, limit=64),
        "actor_id": _safe_text(actor_id, limit=256),
        "delegated_actor_id": _safe_text(delegated_actor_id, limit=256),
        "interface": _safe_text(interface, limit=64),
        "action": _safe_text(action, limit=128),
        "resource_type": _safe_text(resource_type, limit=128),
        "resource_id": _safe_text(resource_id, limit=256),
        "result": decision,
        "reason_code": _safe_text(reason_code, limit=256),
        "correlation_id": _safe_text(correlation_id, limit=256),
        "request_id": _safe_text(request_id, limit=256),
        "session_id": _safe_text(session_id, limit=256),
        "matched_policy": policies,
        "source_meta": _safe_meta(source_meta, SOURCE_META_KEYS),
        "destination_meta": _safe_meta(destination_meta, DESTINATION_META_KEYS),
    }


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DurableAuditSpool:
    """Bounded local durable transport journal for one enforcement source."""

    def __init__(
        self,
        root: Path,
        source: str,
        *,
        segment_bytes: int = DEFAULT_SEGMENT_BYTES,
        high_water_bytes: int = DEFAULT_HIGH_WATER_BYTES,
        create: bool = True,
    ):
        self.root = Path(root)
        self.source = _safe_text(source, limit=128)
        if not self.source:
            raise ValueError("audit spool source is required")
        self.segment_bytes = max(MAX_EVENT_BYTES * 2, int(segment_bytes))
        self.high_water_bytes = max(self.segment_bytes * 2, int(high_water_bytes))
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.root, 0o700)
            except OSError:
                pass
        self.lock_path = self.root / ".lock"
        self.state_path = self.root / "state.json"
        self.active_path = self.root / "active.jsonl"

    def _lock(self):
        fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    @staticmethod
    def _unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _load_state_locked(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            # An existing state file is authoritative. Missing, zero, or
            # coerced sequence numbers could reuse a committed audit sequence.
            next_sequence = data.get("next_sequence")
            if type(next_sequence) is not int or next_sequence < 1:
                raise ValueError("invalid sequence")
            # A corrupt counter cannot be coerced to a seemingly healthy
            # zero/positive value: it would hide lost audit evidence.
            failures = data.get("enqueue_failures", 0)
            dropped_denies = data.get("dropped_deny_count", 0)
            if (
                type(failures) is not int or failures < 0
                or type(dropped_denies) is not int or dropped_denies < 0
            ):
                raise ValueError("invalid audit spool failure counters")
            return {
                "next_sequence": next_sequence,
                "enqueue_failures": failures,
                "dropped_deny_count": dropped_denies,
                "last_error_at": str(data.get("last_error_at") or ""),
            }
        except FileNotFoundError as exc:
            # Only a genuinely fresh spool may begin at sequence 1. Losing
            # authoritative state with queued events must not replay IDs.
            if self.active_path.exists() or self.segments():
                raise AuditUnavailable("Audit spool sequence state is missing.") from exc
            return {
                "next_sequence": 1,
                "enqueue_failures": 0,
                "dropped_deny_count": 0,
                "last_error_at": "",
            }
        except Exception as exc:
            raise AuditUnavailable("Audit spool sequence state is unreadable.") from exc

    def _store_state_locked(self, state: dict[str, Any]) -> None:
        tmp = self.root / (".state.%s.tmp" % secrets.token_hex(6))
        payload = json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, payload.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.state_path)
        _fsync_dir(self.root)

    def spool_bytes(self) -> int:
        total = 0
        for path in self.root.glob("*.jsonl"):
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    def segments(self) -> list[Path]:
        return sorted(
            (p for p in self.root.glob("segment-*.jsonl") if p.is_file()),
            key=lambda p: p.name,
        )

    def _seal_active_locked(self, last_sequence: Optional[int] = None) -> Optional[Path]:
        try:
            if not self.active_path.is_file() or self.active_path.stat().st_size <= 0:
                return None
        except OSError:
            return None
        suffix = int(last_sequence or 0)
        segment = self.root / (
            "segment-%020d-%s.jsonl" % (suffix, secrets.token_hex(6))
        )
        os.replace(self.active_path, segment)
        _fsync_dir(self.root)
        return segment

    def seal_active(self) -> Optional[Path]:
        fd = self._lock()
        try:
            state = self._load_state_locked()
            return self._seal_active_locked(int(state["next_sequence"]) - 1)
        finally:
            self._unlock(fd)

    def enqueue(self, event: dict[str, Any]) -> dict[str, Any]:
        """Reserve sequence, append and fsync one event; raises on durability failure."""
        fd = self._lock()
        try:
            state = self._load_state_locked()
            sequence = int(state["next_sequence"])

            record = dict(event or {})
            if record.get("category") != ACCESS_DECISION:
                raise AuditEventInvalid("Spool accepts ACCESS_DECISION events only.")
            if str(record.get("source") or "") != self.source:
                raise AuditEventInvalid("Audit event source does not match spool source.")
            record["event_id"] = _safe_text(
                record.get("event_id") or ("evt_" + secrets.token_hex(16)), limit=96
            )
            record["source_sequence"] = sequence
            validate_access_event(record)
            line = (
                json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                + "\n"
            ).encode("utf-8")
            if len(line) > MAX_EVENT_BYTES:
                raise AuditEventInvalid("Audit event exceeds maximum encoded size.")
            if self.spool_bytes() + len(line) > self.high_water_bytes:
                raise AuditUnavailable("Audit spool high-water limit reached.")

            # Reject an invalid envelope without consuming a durable sequence.
            # Persist the next sequence before the append so a failed write or
            # crash cannot reuse an already reserved event identity.
            state["next_sequence"] = sequence + 1
            self._store_state_locked(state)

            out = os.open(
                str(self.active_path),
                os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                0o600,
            )
            try:
                os.write(out, line)
                os.fsync(out)
            except Exception as exc:
                raise AuditUnavailable("Durable audit spool append failed.") from exc
            finally:
                os.close(out)
            _fsync_dir(self.root)

            try:
                if self.active_path.stat().st_size >= self.segment_bytes:
                    self._seal_active_locked(sequence)
            except OSError as exc:
                raise AuditUnavailable("Audit spool segment rotation failed.") from exc
            return record
        finally:
            self._unlock(fd)

    def note_failure(self, *, dropped_deny: bool = False) -> None:
        """Best-effort durable health accounting for an event that was not enqueued."""
        try:
            fd = self._lock()
            try:
                state = self._load_state_locked()
                state["enqueue_failures"] = int(state.get("enqueue_failures") or 0) + 1
                if dropped_deny:
                    state["dropped_deny_count"] = (
                        int(state.get("dropped_deny_count") or 0) + 1
                    )
                state["last_error_at"] = utc_now_iso()
                self._store_state_locked(state)
            finally:
                self._unlock(fd)
        except Exception:
            return

    def health(self) -> dict[str, Any]:
        segments = self.segments()
        oldest_age = 0
        if segments:
            try:
                oldest_age = max(0, int(time.time() - min(p.stat().st_mtime for p in segments)))
            except OSError:
                oldest_age = 0
        size = self.spool_bytes()
        try:
            state = self._load_state_locked()
            state_readable = True
        except Exception:
            # A corrupt or missing authoritative sequence state is not
            # healthy, and its lost-event counters are UNKNOWN, never zero.
            state = {}
            state_readable = False
        return {
            "source": self.source,
            "spool_bytes": size,
            "high_water_bytes": self.high_water_bytes,
            "high_water": size >= self.high_water_bytes,
            "segment_count": len(segments),
            "oldest_segment_age_seconds": oldest_age,
            "state_status": "OK" if state_readable else "UNREADABLE",
            "enqueue_failures": (
                int(state.get("enqueue_failures") or 0) if state_readable else None
            ),
            "dropped_deny_count": (
                int(state.get("dropped_deny_count") or 0) if state_readable else None
            ),
            "last_error_at": (
                str(state.get("last_error_at") or "") if state_readable else None
            ),
        }


def validate_access_event(event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        raise AuditEventInvalid("Audit event must be an object.")
    # Builder sanitization is not an authorization boundary: direct spool writers
    # and imported JSONL must never persist unapproved secret-bearing fields.
    if set(event) - ACCESS_EVENT_KEYS:
        raise AuditEventInvalid("Audit event contains unapproved fields.")
    for key, allowed in (
        ("source_meta", SOURCE_META_KEYS),
        ("destination_meta", DESTINATION_META_KEYS),
    ):
        metadata = event.get(key)
        if metadata is None:
            continue
        if not isinstance(metadata, dict):
            raise AuditEventInvalid("Audit metadata must be an object.")
        if set(metadata) - allowed:
            raise AuditEventInvalid("Audit metadata contains unapproved fields.")
        if any(isinstance(value, (dict, list, tuple, bool)) for value in metadata.values()):
            raise AuditEventInvalid("Audit metadata values must be scalar.")
        # Builders normalize ports to an integer. Imported JSONL must not
        # silently coerce strings or fractional evidence to a different port.
        if (
            key == "destination_meta"
            and metadata.get("port") is not None
            and type(metadata["port"]) is not int
        ):
            raise AuditEventInvalid("Audit destination port must be an integer.")
    if (
        type(event.get("schema_version")) is not int
        or event["schema_version"] != AUDIT_SCHEMA_VERSION
    ):
        raise AuditEventInvalid("Unsupported audit schema version.")
    if event.get("category") != ACCESS_DECISION:
        raise AuditEventInvalid("Unsupported audit category for access spool.")
    for key in ("event_id", "event_type", "occurred_at", "source"):
        if not _safe_text(event.get(key), limit=1024):
            raise AuditEventInvalid("Audit event missing required field: %s" % key)
    sequence = event.get("source_sequence")
    if type(sequence) is not int or sequence < 1:
        raise AuditEventInvalid("Audit source_sequence is invalid.")
    policies = event.get("matched_policy", [])
    if (
        not isinstance(policies, list)
        or len(policies) > 32
        or any(
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 256
            for name in policies
        )
    ):
        raise AuditEventInvalid("Audit matched_policy must be a bounded list of rule names.")
    if str(event.get("result") or "").upper() not in ("ALLOW", "DENY"):
        raise AuditEventInvalid("Audit result is invalid.")
    _safe_meta(event.get("source_meta") or {}, SOURCE_META_KEYS)
    _safe_meta(event.get("destination_meta") or {}, DESTINATION_META_KEYS)


class AuditIngestor:
    """Core-owned bounded spool -> SQLite importer."""

    def __init__(self, conn: sqlite3.Connection, spool: DurableAuditSpool):
        self.conn = conn
        self.spool = spool

    def _load_segment(self, path: Path) -> list[dict[str, Any]]:
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise AuditUnavailable("Audit spool segment is unreadable.") from exc
        if len(payload) > self.spool.segment_bytes + MAX_EVENT_BYTES:
            raise AuditEventInvalid("Audit spool segment exceeds bounded size.")
        events: list[dict[str, Any]] = []
        for lineno, raw in enumerate(payload.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                raise AuditEventInvalid(
                    "Audit segment %s line %s is invalid JSON." % (path.name, lineno)
                ) from exc
            validate_access_event(event)
            if str(event["source"]) != self.spool.source:
                raise AuditEventInvalid("Audit segment contains the wrong source.")
            events.append(event)
        return events

    def _insert_event(self, event: dict[str, Any]) -> bool:
        before = self.conn.total_changes
        occurred = str(event["occurred_at"])
        source_meta = event.get("source_meta") or {}
        destination_meta = event.get("destination_meta") or {}
        matched = list(event.get("matched_policy") or [])
        self.conn.execute(
            "INSERT OR IGNORE INTO audit_events("
            "timestamp,revision,actor,action,entity_type,entity_id,operation,"
            "before_summary,after_summary,impact_summary,result,"
            "event_id,schema_version,category,event_type,occurred_at,source,source_sequence,"
            "actor_type,actor_id,delegated_actor_id,interface,reason_code,"
            "correlation_id,request_id,session_id,revision_before,revision_after,"
            "matched_policy_json,source_meta_json,destination_meta_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                occurred,
                None,
                str(event.get("actor_id") or event.get("source") or "system"),
                str(event.get("event_type") or "access.decision"),
                str(event.get("resource_type") or "access-decision"),
                str(event.get("resource_id") or ""),
                str(event.get("action") or "authorize"),
                "",
                "",
                "",
                str(event.get("result") or "DENY").lower(),
                str(event["event_id"]),
                int(event["schema_version"]),
                ACCESS_DECISION,
                str(event["event_type"]),
                occurred,
                str(event["source"]),
                int(event["source_sequence"]),
                str(event.get("actor_type") or ""),
                str(event.get("actor_id") or ""),
                str(event.get("delegated_actor_id") or ""),
                str(event.get("interface") or ""),
                str(event.get("reason_code") or ""),
                str(event.get("correlation_id") or ""),
                str(event.get("request_id") or ""),
                str(event.get("session_id") or ""),
                None,
                None,
                json.dumps(matched, sort_keys=True, separators=(",", ":")),
                json.dumps(source_meta, sort_keys=True, separators=(",", ":")),
                json.dumps(destination_meta, sort_keys=True, separators=(",", ":")),
            ),
        )
        return self.conn.total_changes > before

    def ingest(
        self, *, max_segments: int = DEFAULT_MAX_SEGMENTS_PER_INGEST
    ) -> dict[str, Any]:
        """Import a bounded batch while holding the source-spool lock.

        The lock spans segment sealing, SQLite commit, checkpoint update, and
        segment removal. Besides preventing concurrent ingestors, this gives
        disaster-recovery backup a real snapshot boundary: backup can take the
        same flock, copy pending spool state, then snapshot SQLite without an
        event moving from the spool into the database between those two copies.
        """
        # Reject malformed batch size before sealing the active spool or
        # advancing the ingestion checkpoint. Do not coerce booleans or floats.
        if (
            isinstance(max_segments, bool)
            or not isinstance(max_segments, int)
            or max_segments < 1
        ):
            raise ValueError("Audit ingest max_segments must be a positive integer.")
        limit = min(max_segments, 32)
        inserted = 0
        deduplicated = 0
        last_sequence = None
        processed = 0
        fd = self.spool._lock()
        try:
            state = self.spool._load_state_locked()
            self.spool._seal_active_locked(int(state["next_sequence"]) - 1)
            segments = self.spool.segments()[:limit]

            for segment in segments:
                events = self._load_segment(segment)
                self.conn.execute("BEGIN IMMEDIATE")
                try:
                    seg_last = 0
                    for event in events:
                        if self._insert_event(event):
                            inserted += 1
                        else:
                            deduplicated += 1
                        seg_last = max(seg_last, int(event["source_sequence"]))
                    self.conn.execute(
                        "INSERT INTO audit_ingest_checkpoints("
                        "source,last_sequence,last_segment,updated_at"
                        ") VALUES (?,?,?,?) "
                        "ON CONFLICT(source) DO UPDATE SET "
                        "last_sequence=MAX(last_sequence,excluded.last_sequence),"
                        "last_segment=excluded.last_segment,updated_at=excluded.updated_at",
                        (self.spool.source, seg_last, segment.name, utc_now_iso()),
                    )
                    self.conn.execute("COMMIT")
                    last_sequence = max(int(last_sequence or 0), seg_last)
                except Exception:
                    try:
                        self.conn.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                    raise
                try:
                    segment.unlink()
                    _fsync_dir(self.spool.root)
                except OSError:
                    # DB commit is authoritative; retained segment is harmless:
                    # event_id uniqueness makes re-ingest idempotent.
                    pass
                processed += 1
        finally:
            self.spool._unlock(fd)

        return {
            "source": self.spool.source,
            "segments_processed": processed,
            "inserted": inserted,
            "deduplicated": deduplicated,
            "last_sequence": last_sequence,
            "health": self.spool.health(),
        }
