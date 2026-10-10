#!/usr/bin/env python3
"""Versioned, explicitly allowlisted Core adapter for non-browser automation."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from drlink_control_db import ControlPlaneError
from drlink_management_catalog import management_tool
from drlink_management_core import ManagementCoreService, SURFACE_WEB
from drlink_service_accounts import ServiceAccountStore

PREFIX = "/api/automation/v1/"
# Mutations are limited to actor-bound, revision-bound Temporary Access
# Change Plans. They require a durable idempotency key and explicit APPLY.
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
MUTATIONS = frozenset({"drlink_temporary_access_apply"})
ALLOW = frozenset({
    "drlink_inventory_list", "drlink_inventory_get", "drlink_health",
    "drlink_access_hygiene",
    "drlink_diagnose_connection", "drlink_policy_test", "drlink_audit_query",
    "drlink_live_access", "drlink_job_list", "drlink_job_get",
    "drlink_temporary_access_preview",
})


class AutomationApi:
    def __init__(self, root: Optional[str] = None):
        self.accounts = ServiceAccountStore(root)
        self.core = ManagementCoreService(root)
        self.accounts.conn.execute("""
            CREATE TABLE IF NOT EXISTS management_automation_idempotency (
              actor_id TEXT NOT NULL, operation TEXT NOT NULL,
              key_hash TEXT NOT NULL, request_hash TEXT NOT NULL,
              response_json TEXT NOT NULL, created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              PRIMARY KEY(actor_id, operation, key_hash)
            )
        """)

    def close(self) -> None:
        self.accounts.close()

    def __enter__(self) -> "AutomationApi":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _apply_once(self, operation: str, actor, payload: dict, key: str) -> dict:
        if not isinstance(key, str) or not IDEMPOTENCY_KEY.fullmatch(key):
            raise ControlPlaneError("A valid Idempotency-Key (8-128 ASCII characters) is required.")
        if payload.get("confirmation") != "APPLY":
            raise ControlPlaneError("Explicit APPLY confirmation is required.")
        conn = self.accounts.conn
        key_hash = hashlib.sha256(key.encode("ascii")).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        now = datetime.now(timezone.utc)
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT request_hash,response_json,expires_at FROM management_automation_idempotency "
                "WHERE actor_id=? AND operation=? AND key_hash=?",
                (actor.actor_id, operation, key_hash),
            ).fetchone()
            if row:
                if row["request_hash"] != request_hash:
                    raise ControlPlaneError("Idempotency key was reused with different data.")
                if datetime.fromisoformat(row["expires_at"]) > now:
                    result = json.loads(row["response_json"])
                    conn.execute("COMMIT")
                    return result
                conn.execute(
                    "DELETE FROM management_automation_idempotency "
                    "WHERE actor_id=? AND operation=? AND key_hash=?",
                    (actor.actor_id, operation, key_hash),
                )
            result = self.core.invoke(
                name=operation, arguments=payload, actor=actor, surface=SURFACE_WEB
            )
            conn.execute(
                "INSERT INTO management_automation_idempotency "
                "(actor_id,operation,key_hash,request_hash,response_json,created_at,expires_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (actor.actor_id, operation, key_hash, request_hash,
                 json.dumps(result, sort_keys=True), now.isoformat(),
                 (now + timedelta(hours=24)).isoformat()),
            )
            conn.execute("COMMIT")
            return result
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    def invoke(self, path: str, credential: str, payload: dict[str, Any],
               *, idempotency_key: Optional[str] = None) -> dict[str, Any]:
        if not isinstance(path, str) or not path.startswith(PREFIX):
            raise ControlPlaneError("Automation API route was not found.")
        operation = path[len(PREFIX):]
        # Core callers bypassing HTTP must obey the same canonical route
        # boundary: no query, fragment, nested path or encoded alias.
        if not operation or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in operation):
            raise ControlPlaneError("Automation API route was not found.")
        tool = management_tool(operation)
        if tool is None or (
            operation not in ALLOW and operation not in MUTATIONS
        ) or (operation in ALLOW and not tool.read_only):
            raise ControlPlaneError("Automation operation is not allowlisted.")
        actor = self.accounts.authenticate(credential, limit=True)
        try:
            if not isinstance(payload, dict):
                raise ControlPlaneError("Automation payload must be an object.")
            if operation in MUTATIONS:
                result = self._apply_once(operation, actor, payload, idempotency_key)
            else:
                result = self.core.invoke(
                    name=operation, arguments=payload, actor=actor, surface=SURFACE_WEB
                )
        except Exception:
            self.accounts.audit_request(actor, operation=operation, allowed=False)
            raise
        self.accounts.audit_request(actor, operation=operation, allowed=True)
        return result
