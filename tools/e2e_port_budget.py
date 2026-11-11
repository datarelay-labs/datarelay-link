#!/usr/bin/env python3
"""Fail-closed 30-endpoint admission ledger for one real E2E RUN_ID.

This guards *test-owned* public endpoint allocation, not data-plane TCP sessions.
It never creates/deletes product resources and cannot substitute for public CLI
or independently verified endpoint/traffic evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

MAX_ENDPOINTS = 30
SCHEMA = "drlink.e2e.endpoint-budget.v1"
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fail(message: str) -> None:
    raise ValueError(message)


def root_path(value: str) -> Path:
    p = Path(value)
    if not p.is_absolute() or not p.is_dir() or p.is_symlink():
        fail("RUN root must be an existing absolute, non-symlink directory")
    if p.stat().st_mode & 0o077:
        fail("RUN root must not be accessible by group or other users (mode 0700)")
    return p


def locked_file(path: Path):
    if path.is_symlink():
        fail("refusing symlinked lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def load(path: Path, head: str) -> dict:
    if path.is_symlink() or not path.is_file():
        fail("missing or symlinked budget ledger: run init first")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if (
        doc.get("schema") != SCHEMA
        or doc.get("source_head") != head
        or doc.get("maximum_active") != MAX_ENDPOINTS
        or doc.get("maximum_distinct") != MAX_ENDPOINTS
        or not isinstance(doc.get("active"), dict)
        or not isinstance(doc.get("distinct_ports"), list)
        or not isinstance(doc.get("events"), list)
    ):
        fail("RUN_ID/candidate HEAD/budget mismatch or corrupted ledger; refusing mutation")
    return doc


def write(path: Path, doc: dict) -> None:
    # Same-directory atomic replace under the exclusive flock.
    fd, tmp = tempfile.mkstemp(prefix=".endpoint-budget-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--source-head", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    reserve = sub.add_parser("reserve")
    reserve.add_argument("--resource-id", required=True)
    reserve.add_argument("--pool", choices=("normal", "fixed"), required=True)
    confirm = sub.add_parser("confirm")
    confirm.add_argument("--resource-id", required=True)
    confirm.add_argument("--public-port", type=int, required=True)
    release = sub.add_parser("release")
    release.add_argument("--resource-id", required=True)
    release.add_argument("--receipt", required=True)
    sub.add_parser("status")
    a = parser.parse_args()

    if not SHA.fullmatch(a.source_head):
        fail("source HEAD must be a full lowercase 40-character Git SHA")
    root = root_path(a.run_root)
    ledger = root / "endpoint-allocation-budget.json"
    lock_fd = locked_file(root / ".endpoint-allocation-budget.lock")
    try:
        if a.action == "init" and not ledger.exists():
            doc = {
                "schema": SCHEMA,
                "run_id": root.name,
                "source_head": a.source_head,
                "maximum_active": MAX_ENDPOINTS,
                "maximum_distinct": MAX_ENDPOINTS,
                "active": {},
                "distinct_ports": [],
                "events": [],
            }
            write(ledger, doc)
        else:
            doc = load(ledger, a.source_head)

        if a.action in ("reserve", "confirm", "release"):
            if not KEY.fullmatch(a.resource_id):
                fail("invalid resource ID")
            active = doc["active"]
            if a.action == "reserve":
                if a.resource_id in active:
                    fail("resource ID is already reserved")
                if len(active) >= MAX_ENDPOINTS:
                    fail("E2E_ENDPOINT_BUDGET_EXCEEDED: 30 active reservations")
                active[a.resource_id] = {"pool": a.pool, "public_port": None}
                doc["events"].append({"utc": now(), "action": "reserve", "resource_id": a.resource_id, "pool": a.pool})
            elif a.action == "confirm":
                record = active.get(a.resource_id)
                if record is None or record["public_port"] is not None:
                    fail("must first reserve an unconfirmed resource ID")
                port = a.public_port
                if not 1 <= port <= 65535:
                    fail("invalid public port")
                if any(v["public_port"] == port for v in active.values()):
                    fail("duplicate live public endpoint; inspect product state")
                distinct = doc["distinct_ports"]
                if port not in distinct and len(distinct) >= MAX_ENDPOINTS:
                    fail("E2E_DISTINCT_ENDPOINT_BUDGET_EXCEEDED: observed 31st distinct port; clean up immediately")
                if port not in distinct:
                    distinct.append(port)
                record["public_port"] = port
                doc["events"].append({"utc": now(), "action": "confirm", "resource_id": a.resource_id, "public_port": port})
            else:
                if a.resource_id not in active:
                    fail("resource ID is not currently reserved")
                receipt = Path(a.receipt)
                # A receipt must be independently produced inside the current RUN root.
                if (not receipt.is_absolute() or receipt.is_symlink()
                        or not receipt.is_file() or not receipt.resolve().is_relative_to(root.resolve())):
                    fail("cleanup receipt must exist as a regular file under RUN root")
                content = receipt.read_bytes()
                if not content:
                    fail("empty cleanup receipt is not accepted")
                checksum = hashlib.sha256(content).hexdigest()
                del active[a.resource_id]
                doc["events"].append({"utc": now(), "action": "release", "resource_id": a.resource_id,
                                      "cleanup_receipt": str(receipt.relative_to(root)),
                                      "cleanup_receipt_sha256": checksum})
            write(ledger, doc)
        print(json.dumps({
            "result": "PASS",
            "run_id": doc["run_id"],
            "source_head": doc["source_head"],
            "max_active_and_distinct": MAX_ENDPOINTS,
            "active": len(doc["active"]),
            "confirmed_active": sum(v["public_port"] is not None for v in doc["active"].values()),
            "distinct_ports": len(doc["distinct_ports"]),
        }, sort_keys=True))
        return 0
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
