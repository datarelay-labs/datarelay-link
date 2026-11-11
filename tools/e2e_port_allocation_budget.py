#!/usr/bin/env python3
"""RUN_ID-scoped, fail-closed 30-live-endpoint E2E safety ledger.

Only a scheduling guard: never equate this file with authoritative DRLink state.
All concurrent lanes targeting one functional E2E Server must use one ledger.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import tempfile

MAX_LIVE_ENDPOINTS = 30


class BudgetError(Exception):
    pass


def operate(ledger: Path, action: str, owner: str | None) -> dict:
    if not ledger.parent.is_dir():
        raise BudgetError("RUN_ID evidence directory does not exist")
    if ledger.is_symlink():
        raise BudgetError("ledger cannot be a symlink")
    lock_path = ledger.with_name(ledger.name + ".lock")
    if lock_path.is_symlink():
        raise BudgetError("lock cannot be a symlink")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        if ledger.exists():
            with ledger.open(encoding="utf-8") as stream:
                record = json.load(stream)
            if (
                record.get("schema") != 1
                or not isinstance(record.get("owners"), list)
                or len(record["owners"]) > MAX_LIVE_ENDPOINTS
                or any(not isinstance(x, str) or not x for x in record["owners"])
                or len(set(record["owners"])) != len(record["owners"])
            ):
                raise BudgetError("invalid or oversized ledger; repair using authoritative inventory")
            owners = record["owners"]
        else:
            owners = []
        if action == "reserve":
            if not owner or len(owner) > 192 or any(c in owner for c in "\n\r\t"):
                raise BudgetError("invalid unique RUN_ID-scoped owner")
            if owner in owners:
                raise BudgetError("duplicate owner; do not run a second create without new attribution")
            if len(owners) >= MAX_LIVE_ENDPOINTS:
                raise BudgetError("30 endpoint ceiling reached; do not issue a new product create")
            owners.append(owner)
        elif action == "release":
            if owner not in owners:
                raise BudgetError("unknown owner; verify authoritative release before retry")
            owners.remove(owner)
        if action != "status":
            data = json.dumps({"schema": 1, "owners": sorted(owners)}, indent=2) + "\n"
            tmp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ledger.parent,
                                                 prefix=ledger.name + ".", delete=False) as tmp:
                    tmp_name = tmp.name
                    os.fchmod(tmp.fileno(), 0o600)
                    tmp.write(data)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_name, ledger)
            finally:
                if tmp_name and os.path.exists(tmp_name):
                    os.unlink(tmp_name)
        return {"result": "PASS", "action": action,
                "live_reserved": len(owners), "ceiling": MAX_LIVE_ENDPOINTS}
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path,
                        help="shared private RUN_ID endpoint budget file")
    parser.add_argument("action", choices=("reserve", "release", "status"))
    parser.add_argument("--owner", help="unique RUN_ID:SCENARIO:OPERATION identifier")
    args = parser.parse_args()
    try:
        if args.action in ("reserve", "release") and not args.owner:
            raise BudgetError("--owner is required for mutation")
        if args.action == "status" and args.owner:
            raise BudgetError("--owner is not valid for status")
        result = operate(args.ledger, args.action, args.owner)
    except (BudgetError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"result": "DENY", "reason": str(exc),
                          "ceiling": MAX_LIVE_ENDPOINTS}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
