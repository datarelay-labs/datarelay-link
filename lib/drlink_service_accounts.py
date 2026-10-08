#!/usr/bin/env python3
"""Local non-human principals for the optional DRLink 3.0 Automation API.

Only the one-time return values of create/rotate contain bearer credentials.
No credential is stored or emitted through inventory/audit.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional

from drlink_control_db import ControlPlaneError, open_control_db
from drlink_management_catalog import MANAGEMENT_PERMISSION_NAMES
from drlink_management_core import ManagementActor

MAX_REQUESTS_PER_MINUTE = 120


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _expiry(value: str) -> Optional[str]:
    if not value:
        return None
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise ValueError("expired or timezone missing")
    except (ValueError, TypeError) as exc:
        raise ControlPlaneError("Service Account expiry must be a future ISO-8601 timestamp.") from exc
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ServiceAccountRateLimited(ControlPlaneError):
    """Authenticated principal exceeded its bounded request rate."""


class ServiceAccountUnauthenticated(ControlPlaneError):
    """Bearer credential missing, invalid, revoked, or expired."""


class ServiceAccountStore:
    def __init__(self, root: Optional[str] = None):
        self.conn = open_control_db(root)
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS management_service_accounts(
          id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
          permissions TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
          expires_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS management_service_account_credentials(
          id TEXT PRIMARY KEY, account_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL, revoked_at TEXT,
          FOREIGN KEY(account_id) REFERENCES management_service_accounts(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_service_account_credentials_token
          ON management_service_account_credentials(token_hash,revoked_at);
        CREATE TABLE IF NOT EXISTS management_service_account_rate(
          account_id TEXT PRIMARY KEY, window_start INTEGER NOT NULL, request_count INTEGER NOT NULL,
          FOREIGN KEY(account_id) REFERENCES management_service_accounts(id) ON DELETE CASCADE);
        """)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ServiceAccountStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _audit(self, *, event_type: str, actor: str, account_id: str, result: str,
               operation: Optional[str] = None) -> None:
        # Independent security event: never record credential/secret material.
        now = _now()
        self.conn.execute(
            "INSERT INTO audit_events(timestamp,actor,action,entity_type,entity_id,"
            "operation,result,event_id,schema_version,category,event_type,occurred_at,"
            "source,actor_type,actor_id,interface) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now, actor, event_type, "service-account", account_id,
             operation or event_type, result, "evt_sa_" + secrets.token_hex(16), 1, "SECURITY_LIFECYCLE",
             event_type, now, "drlink-core", "SERVICE_ACCOUNT" if actor.startswith("msa_")
             else "WEB_OPERATOR", actor, "AUTOMATION" if actor.startswith("msa_") else "WEB"),
        )

    def list_accounts(self) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT id,name,permissions,enabled,expires_at,created_at,updated_at "
            "FROM management_service_accounts ORDER BY name LIMIT 200"
        ).fetchall()
        return {"items": [
            {"id": str(row["id"]), "name": str(row["name"]),
             "permissions": str(row["permissions"]).splitlines(),
             "enabled": bool(row["enabled"]), "expires_at": row["expires_at"],
             "created_at": row["created_at"], "updated_at": row["updated_at"]}
            for row in rows
        ]}

    def create(
        self, name: str, permissions: list[str], expires_at: str = "", *, actor_id: str = "local-admin"
    ) -> dict[str, Any]:
        label = str(name or "").strip()
        if not label or len(label) > 128 or any(ord(ch) < 32 for ch in label):
            raise ControlPlaneError("Service Account name is required, printable and at most 128 characters.")
        if not isinstance(permissions, list) or any(not isinstance(x, str) for x in permissions):
            raise ControlPlaneError("Service Account permissions must be a list of names.")
        perms = sorted({x.strip().lower() for x in permissions if x.strip()})
        if not perms or any(x not in MANAGEMENT_PERMISSION_NAMES for x in perms):
            raise ControlPlaneError("Service Account permissions must be valid management permissions.")
        expiry = _expiry(expires_at)
        account_id, cred_id = "msa_" + secrets.token_hex(12), "msc_" + secrets.token_hex(12)
        token, now = "drlink_sa_" + secrets.token_urlsafe(32), _now()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                "INSERT INTO management_service_accounts(id,name,permissions,expires_at,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (account_id, label, "\n".join(perms), expiry, now, now),
            )
            self.conn.execute(
                "INSERT INTO management_service_account_credentials(id,account_id,token_hash,created_at)"
                " VALUES (?,?,?,?)", (cred_id, account_id, _digest(token), now),
            )
            self._audit(event_type="service_account.created", actor=actor_id,
                        account_id=account_id, result="success")
            self.conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self.conn.execute("ROLLBACK")
            raise ControlPlaneError("Service Account name is already in use.") from exc
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return {"id": account_id, "name": label, "permissions": perms,
                "expires_at": expiry, "credential": token, "credential_id": cred_id}

    def authenticate(self, token: str, *, limit: bool = False) -> ManagementActor:
        supplied = str(token or "")
        if not supplied.startswith("drlink_sa_") or len(supplied) > 256:
            raise ServiceAccountUnauthenticated("Invalid Service Account credential.")
        # BEGIN IMMEDIATE serializes the per-account rate window between concurrent HTTP workers.
        if limit:
            self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT a.id,a.permissions,a.enabled,a.expires_at,c.revoked_at "
                "FROM management_service_account_credentials c "
                "JOIN management_service_accounts a ON a.id=c.account_id "
                "WHERE c.token_hash=?", (_digest(supplied),),
            ).fetchone()
            if not row or not int(row["enabled"]) or row["revoked_at"]:
                raise ServiceAccountUnauthenticated("Invalid Service Account credential.")
            expiry = str(row["expires_at"] or "")
            if expiry:
                try:
                    instant = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                    valid = instant.tzinfo is not None and instant.astimezone(timezone.utc) > datetime.now(timezone.utc)
                except ValueError:
                    valid = False
                if not valid:
                    raise ServiceAccountUnauthenticated("Service Account credential is expired.")
            actor = ManagementActor.authenticated(
                str(row["id"]), set(str(row["permissions"]).splitlines()), role="Service Account"
            )
            if limit:
                minute = int(time.time()) // 60
                rate = self.conn.execute(
                    "SELECT window_start,request_count FROM management_service_account_rate WHERE account_id=?",
                    (actor.actor_id,),
                ).fetchone()
                count = (int(rate["request_count"]) + 1
                         if rate and int(rate["window_start"]) == minute else 1)
                self.conn.execute(
                    "INSERT INTO management_service_account_rate(account_id,window_start,request_count)"
                    " VALUES (?,?,?) ON CONFLICT(account_id) DO UPDATE SET"
                    " window_start=excluded.window_start,request_count=excluded.request_count",
                    (actor.actor_id, minute, count),
                )
                if count > MAX_REQUESTS_PER_MINUTE:
                    self._audit(event_type="service_account.request_limited", actor=actor.actor_id,
                                account_id=actor.actor_id, result="deny")
                    self.conn.execute("COMMIT")
                    raise ServiceAccountRateLimited("Service Account request rate exceeded.")
                self.conn.execute("COMMIT")
            return actor
        except Exception:
            if limit and self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def audit_request(self, actor: ManagementActor, *, operation: str, allowed: bool) -> None:
        self._audit(event_type="service_account.request." + ("allowed" if allowed else "denied"),
                    actor=actor.actor_id, account_id=actor.actor_id,
                    result="success" if allowed else "deny", operation=operation)

    def rotate(self, account_id: str, *, actor_id: str = "local-admin") -> dict[str, str]:
        token, cred_id, now = "drlink_sa_" + secrets.token_urlsafe(32), "msc_" + secrets.token_hex(12), _now()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT id,enabled,expires_at FROM management_service_accounts WHERE id=?", (account_id,)
            ).fetchone()
            if not row or not int(row["enabled"]):
                raise ControlPlaneError("Service Account was not found.")
            if row["expires_at"] and str(row["expires_at"]) <= now:
                raise ControlPlaneError("Expired Service Account cannot be rotated.")
            self.conn.execute(
                "UPDATE management_service_account_credentials SET revoked_at=?"
                " WHERE account_id=? AND revoked_at IS NULL", (now, account_id),
            )
            self.conn.execute(
                "INSERT INTO management_service_account_credentials(id,account_id,token_hash,created_at)"
                " VALUES (?,?,?,?)", (cred_id, account_id, _digest(token), now),
            )
            self.conn.execute("UPDATE management_service_accounts SET updated_at=? WHERE id=?", (now, account_id))
            self._audit(event_type="service_account.rotated", actor=actor_id,
                        account_id=account_id, result="success")
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return {"credential": token, "credential_id": cred_id}

    def revoke(self, account_id: str, *, actor_id: str = "local-admin") -> None:
        now = _now()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            changed = self.conn.execute(
                "UPDATE management_service_accounts SET enabled=0,updated_at=? WHERE id=? AND enabled=1",
                (now, account_id),
            ).rowcount
            if not changed:
                raise ControlPlaneError("Active Service Account was not found.")
            self.conn.execute(
                "UPDATE management_service_account_credentials SET revoked_at=?"
                " WHERE account_id=? AND revoked_at IS NULL", (now, account_id),
            )
            self.conn.execute("DELETE FROM management_service_account_rate WHERE account_id=?", (account_id,))
            self._audit(event_type="service_account.revoked", actor=actor_id,
                        account_id=account_id, result="success")
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
