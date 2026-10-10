#!/usr/bin/env python3
"""Data Relay Link 3.0 operational live-access snapshots.

Internet Access runtimes own their session lifecycle, so they can publish
EXACT_PER_CONNECTION observations without making operational state authority.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from drlink_control_db import resolve_root, utc_now_iso

LIVE_SCHEMA_VERSION = 1
FIDELITY_EXACT = "EXACT_PER_CONNECTION"
FIDELITY_AGGREGATE = "AGGREGATE"
FIDELITY_UNKNOWN = "UNKNOWN"

_SESSION_KEYS = (
    "session_id",
    "connection_id",
    "source_ip",
    "hostname",
    "port",
    "protocol",
    "method",
    "profile_id",
    "relay_id",
    "relay_name",
    "policy_generation",
)


def default_live_snapshot_path(producer: str, root: Optional[str] = None) -> Path:
    name = str(producer or "").strip().lower()
    if name == "internet-gateway":
        rel = Path("run/drlink/egress/live-access.json")
    elif name == "fixed-tcp":
        rel = Path("run/drlink/tcp-egress/live-access.json")
    else:
        raise ValueError("unsupported live-access producer: %s" % producer)
    resolved = resolve_root(root)
    return (Path(resolved) / rel) if resolved else (Path("/") / rel)


def _started_at(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sanitize_session(session: dict[str, Any], *, producer: str) -> dict[str, Any]:
    out: dict[str, Any] = {"producer": producer}
    for key in _SESSION_KEYS:
        if key not in session or session[key] is None:
            continue
        if key in ("port", "policy_generation"):
            try:
                out[key] = int(session[key])
            except (TypeError, ValueError):
                continue
        else:
            out[key] = str(session[key])[:512]
    started = _started_at(session.get("start_time"))
    if started:
        out["started_at"] = started
    out["status"] = "ACTIVE"
    return out


def write_live_snapshot(
    path: Path,
    *,
    producer: str,
    plane: str,
    sessions: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    observations = [
        sanitize_session(dict(session), producer=producer) for session in sessions
    ]
    observations.sort(
        key=lambda item: (
            item.get("started_at") or "",
            item.get("session_id") or "",
        )
    )
    payload = {
        "schema_version": LIVE_SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "producer": producer,
        "producer_pid": os.getpid(),
        "plane": plane,
        "fidelity": FIDELITY_EXACT,
        "active_count": len(observations),
        "observations": observations,
    }
    tmp = target.with_name(target.name + ".%s.tmp" % secrets.token_hex(6))
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)
    return payload


def _valid_snapshot_time(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return False
    return instant.tzinfo is not None and instant.utcoffset() is not None


def read_live_snapshot(path: Path) -> dict[str, Any]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "fidelity": FIDELITY_UNKNOWN,
            "observations": [],
            "active_count": None,
            "reason": "live-access producer snapshot is unavailable",
        }
    except Exception:
        return {
            "fidelity": FIDELITY_UNKNOWN,
            "observations": [],
            "active_count": None,
            "reason": "live-access producer snapshot is unreadable",
        }
    expected_producer = {"egress": "internet-gateway", "tcp-egress": "fixed-tcp"}.get(
        target.parent.name
    )
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != LIVE_SCHEMA_VERSION
        or payload.get("fidelity") != FIDELITY_EXACT
        or payload.get("plane") != "internet"
        or payload.get("producer") not in ("internet-gateway", "fixed-tcp")
        or (expected_producer is not None and payload.get("producer") != expected_producer)
        or type(payload.get("producer_pid")) is not int
        or payload.get("producer_pid") <= 0
        or not _valid_snapshot_time(payload.get("updated_at"))
        or not isinstance(payload.get("observations"), list)
        or any(not isinstance(item, dict) for item in payload["observations"])
        or type(payload.get("active_count")) is not int
        or payload["active_count"] != len(payload["observations"])
    ):
        return {
            "fidelity": FIDELITY_UNKNOWN,
            "observations": [],
            "active_count": None,
            "reason": "live-access producer snapshot schema is invalid",
        }
    # When reading the real host, a dead producer makes the snapshot stale.
    # Test roots intentionally skip /proc ownership checks.
    if not os.environ.get("FRP_DEPLOY_TEST_ROOT") and not os.environ.get(
        "DRLINK_TEST_ROOT"
    ):
        try:
            pid = int(payload.get("producer_pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid <= 0 or not Path("/proc/%d" % pid).exists():
            return {
                "fidelity": FIDELITY_UNKNOWN,
                "observations": [],
                "active_count": None,
                "reason": "live-access producer is not running",
            }
    return payload
