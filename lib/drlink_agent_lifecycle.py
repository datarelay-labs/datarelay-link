#!/usr/bin/env python3
"""Portable Agent lifecycle intent and reconnect reconciliation worker."""
from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path
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


def reconcile_once(root: Optional[str] = None) -> dict:
    if load_lifecycle_intent(root) == "paused":
        return {"status": "PAUSED", "updated": 0}
    heartbeat = heartbeat_once(root)
    force_sync = bool((heartbeat or {}).get("reconcile_required", False))
    from drlink_control_plane import ControlPlane
    from drlink_v24 import ensure_v2_schema, synchronize_agent_remote_services

    plane = ControlPlane(root)
    try:
        ensure_v2_schema(plane.conn)
        if not force_sync and not reconciliation_needed(plane):
            return {"status": "HEARTBEAT", "updated": 0}
        return synchronize_agent_remote_services(plane, root=root, force_runtime=force_sync)
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
