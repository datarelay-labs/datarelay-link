#!/usr/bin/env python3
"""Protected, bounded, optional event Webhook outbox for DRLink 3.0.

Never an authorization or policy-enforcement dependency. Each queued event uses
one stable id across retries; senders must deduplicate by that id.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from drlink_control_db import ControlPlaneError, db_path, open_control_db

MAX_OUTBOX = 1000
MAX_ATTEMPTS = 5
ALLOWED_EVENTS = frozenset({"attention", "security.lifecycle", "policy.change", "managed_host.lifecycle"})
PRIVATE_KEYS = frozenset({
    "password", "secret", "token", "credential", "credentials", "private_key",
    "authorization", "cookie", "totp", "recovery_code", "api_key", "key",
})
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_webhook_url(url: str) -> tuple[str, str, str]:
    """Return (normalized URL, DNS name, path). No IP literal, credentials, or exotic port."""
    value = str(url or "").strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ControlPlaneError("Webhook URL contains invalid control characters.")
    if len(value) > 2048:
        raise ControlPlaneError("Webhook URL is too long.")
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
        ascii_host = hostname.encode("idna").decode("ascii")
    except (ValueError, UnicodeError) as exc:
        raise ControlPlaneError("Invalid HTTPS webhook endpoint.") from exc
    if (parsed.scheme != "https" or not hostname or
        parsed.username is not None or parsed.password is not None):
        raise ControlPlaneError("Webhook endpoint must use HTTPS DNS hostname without userinfo.")
    if parsed.fragment or parsed.query or parsed.netloc.endswith("@"):
        raise ControlPlaneError("Webhook endpoint must not contain query, fragment, or credentials.")
    if port not in (None, 443) or hostname in {"localhost", "ip6-localhost"}:
        raise ControlPlaneError("Webhook endpoint must be an external HTTPS service on port 443.")
    try:
        ipaddress.ip_address(ascii_host)
    except ValueError:
        pass
    else:
        raise ControlPlaneError("Webhook endpoint must not be an IP literal.")
    labels = ascii_host.split(".")
    if (len(ascii_host) > 253 or len(labels) < 2 or
        any(not DOMAIN.fullmatch(label) for label in labels)):
        raise ControlPlaneError("Webhook endpoint must be a valid DNS name.")
    path = parsed.path or "/"
    return "https://" + ascii_host + path, ascii_host, path


def _safe(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        raise ControlPlaneError("Webhook event payload exceeds safe nesting depth.")
    if isinstance(value, dict):
        if len(value) > 50:
            raise ControlPlaneError("Webhook event payload has too many fields.")
        return {str(k): _safe(v, depth + 1) for k, v in value.items()
                if not any(part in str(k).lower().replace("-", "_") for part in PRIVATE_KEYS)}
    if isinstance(value, (tuple, list)):
        if len(value) > 50:
            raise ControlPlaneError("Webhook event payload has too many entries.")
        return [_safe(v, depth + 1) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ControlPlaneError("Webhook event payload contains unsupported data.")


class WebhookStore:
    def __init__(self, root: Optional[str] = None):
        self.root = root
        self.conn = open_control_db(root)
        self.key_file = db_path(root).parent / "webhook-signing.key"
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS management_webhooks(
          id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT NOT NULL,event_classes TEXT NOT NULL,
          secret_hash TEXT NOT NULL,secret_ciphertext TEXT,
          enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS management_webhook_outbox(
          event_id TEXT PRIMARY KEY,webhook_id TEXT NOT NULL,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt_at TEXT,last_attempt_at TEXT,lease_token TEXT NOT NULL DEFAULT '',
          last_error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_webhook_outbox_status
          ON management_webhook_outbox(status,created_at,event_id);
        CREATE TABLE IF NOT EXISTS management_webhook_audit_cursors(
          webhook_id TEXT PRIMARY KEY,last_audit_id INTEGER NOT NULL DEFAULT 0);
        """)
        columns = {str(r[1]) for r in self.conn.execute("PRAGMA table_info(management_webhooks)")}
        if "secret_ciphertext" not in columns:
            self.conn.execute("ALTER TABLE management_webhooks ADD COLUMN secret_ciphertext TEXT")
        outbox = {str(r[1]) for r in self.conn.execute("PRAGMA table_info(management_webhook_outbox)")}
        if "next_attempt_at" not in outbox:
            self.conn.execute("ALTER TABLE management_webhook_outbox ADD COLUMN next_attempt_at TEXT")
        if "lease_token" not in outbox:
            self.conn.execute(
                "ALTER TABLE management_webhook_outbox "
                "ADD COLUMN lease_token TEXT NOT NULL DEFAULT ''"
            )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "WebhookStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _cipher(self, *, create: bool = False) -> Fernet:
        if create and not self.key_file.exists():
            if self.conn.execute(
                "SELECT 1 FROM management_webhooks WHERE secret_ciphertext IS NOT NULL LIMIT 1"
            ).fetchone():
                raise ControlPlaneError("Webhook encryption key is missing; restore protected state.")
            try:
                fd = os.open(str(self.key_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                fd = None
            if fd is not None:
                with os.fdopen(fd, "wb") as file:
                    file.write(Fernet.generate_key())
                    file.flush()
                    os.fsync(file.fileno())
        try:
            info = self.key_file.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ControlPlaneError("Webhook encryption key is not a regular private file.")
            if info.st_uid != os.geteuid():
                raise ControlPlaneError("Webhook encryption key ownership is not trusted.")
            if info.st_mode & 0o077:
                raise ControlPlaneError("Webhook encryption key is not private.")
            return Fernet(self.key_file.read_bytes())
        except (OSError, ValueError) as exc:
            raise ControlPlaneError("Protected webhook encryption key is unavailable.") from exc

    def _audit(self, event: str, webhook_id: str, actor_id: str = "local-admin") -> None:
        now = _now()
        self.conn.execute(
            "INSERT INTO audit_events(timestamp,actor,action,entity_type,entity_id,operation,"
            "result,event_id,schema_version,category,event_type,occurred_at,source,"
            "actor_type,actor_id,interface) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now, actor_id, event, "management-webhook", webhook_id, event, "success",
             "evt_wh_" + secrets.token_hex(16), 1, "SECURITY_LIFECYCLE", event, now,
             "drlink-core", "WEB_OPERATOR", actor_id, "WEB"),
        )

    def create(self, name: str, url: str, event_classes: list[str], *,
               actor_id: str = "local-admin") -> dict[str, Any]:
        endpoint, _, _ = validate_webhook_url(url)
        label = str(name or "").strip()
        classes = sorted({str(x).strip().lower() for x in event_classes})
        if not label or len(label) > 128 or not classes or any(x not in ALLOWED_EVENTS for x in classes):
            raise ControlPlaneError("Webhook name and selected event classes are required.")
        wid = "wh_" + secrets.token_hex(12)
        secret = "drlink_wh_" + secrets.token_urlsafe(32)
        sealed = self._cipher(create=True).encrypt(secret.encode()).decode()
        now = _now()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                "INSERT INTO management_webhooks(id,name,url,event_classes,secret_hash,"
                "secret_ciphertext,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (wid, label, endpoint, "\n".join(classes), _hash(secret), sealed, now, now),
            )
            self._audit("management_webhook.created", wid, actor_id)
            self.conn.execute(
                "INSERT INTO management_webhook_audit_cursors(webhook_id,last_audit_id)"
                " VALUES (?,(SELECT COALESCE(MAX(id),0) FROM audit_events))", (wid,),
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return {"id": wid, "secret": secret, "url": endpoint, "event_classes": classes}

    def signing_secret(self, webhook_id: str) -> str:
        row = self.conn.execute(
            "SELECT enabled,secret_ciphertext FROM management_webhooks WHERE id=?",
            (webhook_id,),
        ).fetchone()
        if not row or not int(row["enabled"]) or not row["secret_ciphertext"]:
            raise ControlPlaneError("Webhook signing material unavailable.")
        try:
            return self._cipher().decrypt(str(row["secret_ciphertext"]).encode()).decode()
        except (InvalidToken, UnicodeError) as exc:
            raise ControlPlaneError("Webhook signing material cannot be decrypted.") from exc

    def list_webhooks(self) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT id,name,url,event_classes,enabled,created_at,updated_at "
            "FROM management_webhooks ORDER BY name LIMIT 200"
        ).fetchall()
        items = []
        for row in rows:
            summary = self.conn.execute(
                "SELECT status,COUNT(*) AS n FROM management_webhook_outbox "
                "WHERE webhook_id=? GROUP BY status", (row["id"],),
            ).fetchall()
            items.append({
                "id": row["id"], "name": row["name"], "url": row["url"],
                "event_classes": str(row["event_classes"]).splitlines(),
                "enabled": bool(row["enabled"]), "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "delivery_counts": {str(r["status"]): int(r["n"]) for r in summary},
            })
        return {"items": items}

    def enqueue(self, webhook_id: str, event_type: str, payload: dict[str, Any], *,
                audit_actor_id: Optional[str] = None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ControlPlaneError("Webhook event body must be an object.")
        eid = "whe_" + secrets.token_hex(16)
        event = {"schema_version": 1, "event_id": eid, "timestamp": _now(),
                 "event_type": event_type, "data": _safe(payload)}
        serialized = json.dumps(event, separators=(",", ":"), sort_keys=True, allow_nan=False)
        if len(serialized.encode()) > 8192:
            raise ControlPlaneError("Webhook event payload exceeds 8 KiB.")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT enabled,event_classes FROM management_webhooks WHERE id=?", (webhook_id,)
            ).fetchone()
            if not row or not int(row["enabled"]):
                raise ControlPlaneError("Webhook is unavailable.")
            if event_type not in str(row["event_classes"]).splitlines():
                raise ControlPlaneError("Webhook event class is not selected.")
            pending = int(self.conn.execute(
                "SELECT COUNT(*) FROM management_webhook_outbox WHERE status IN ('PENDING','SENDING')"
            ).fetchone()[0])
            if pending >= MAX_OUTBOX:
                raise ControlPlaneError("Webhook outbox is at its bounded high-water mark.")
            self.conn.execute(
                "INSERT INTO management_webhook_outbox(event_id,webhook_id,event_type,"
                "payload_json,next_attempt_at,created_at) VALUES (?,?,?,?,?,?)",
                (eid, webhook_id, event_type, serialized, event["timestamp"], event["timestamp"]),
            )
            if audit_actor_id is not None:
                self._audit("management_webhook.test_requested", webhook_id, audit_actor_id)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return event

    def test_delivery(self, webhook_id: str, *, actor_id: str = "local-admin") -> dict[str, str]:
        """Queue an explicit signed test event with an atomic audit record.

        A worker performs delivery later; this operation never bypasses
        endpoint selection, queue bounds, or HTTPS destination validation.
        """
        row = self.conn.execute(
            "SELECT event_classes FROM management_webhooks WHERE id=? AND enabled=1",
            (webhook_id,),
        ).fetchone()
        if not row:
            raise ControlPlaneError("Active webhook was not found.")
        event_type = next(
            (klass for klass in str(row["event_classes"]).splitlines()
             if klass in ALLOWED_EVENTS), None,
        )
        if event_type is None:
            raise ControlPlaneError("Active webhook has no supported event class.")
        event = self.enqueue(
            webhook_id, event_type, {"kind": "test-delivery"},
            audit_actor_id=actor_id,
        )
        return {"webhook_id": webhook_id, "event_id": event["event_id"], "status": "QUEUED"}

    def rotate_secret(self, webhook_id: str, *, actor_id: str = "local-admin") -> dict[str, str]:
        secret = "drlink_wh_" + secrets.token_urlsafe(32)
        sealed = self._cipher(create=True).encrypt(secret.encode()).decode()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            updated = self.conn.execute(
                "UPDATE management_webhooks SET secret_hash=?,secret_ciphertext=?,updated_at=?"
                " WHERE id=? AND enabled=1", (_hash(secret), sealed, _now(), webhook_id),
            ).rowcount
            if not updated:
                raise ControlPlaneError("Active webhook was not found.")
            self._audit("management_webhook.rotated", webhook_id, actor_id)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return {"id": webhook_id, "secret": secret}

    def disable(self, webhook_id: str, *, actor_id: str = "local-admin") -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            updated = self.conn.execute(
                "UPDATE management_webhooks SET enabled=0,updated_at=? WHERE id=? AND enabled=1",
                (_now(), webhook_id),
            ).rowcount
            if not updated:
                raise ControlPlaneError("Active webhook was not found.")
            self.conn.execute(
                "UPDATE management_webhook_outbox SET status='FAILED',last_error='webhook disabled'"
                " WHERE webhook_id=? AND status IN ('PENDING','SENDING')", (webhook_id,),
            )
            self._audit("management_webhook.disabled", webhook_id, actor_id)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def prune_history(self, max_completed: int = 5000, retention_days: int = 30) -> int:
        """Bound delivered/failed history without touching pending or leased events."""
        ceiling = max(10, min(int(max_completed), 5000))
        age_days = max(1, min(int(retention_days), 90))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=age_days)).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            removed = self.conn.execute(
                "DELETE FROM management_webhook_outbox WHERE status IN ('DELIVERED','FAILED') "
                "AND created_at<?", (cutoff,),
            ).rowcount
            completed = int(self.conn.execute(
                "SELECT COUNT(*) FROM management_webhook_outbox "
                "WHERE status IN ('DELIVERED','FAILED')"
            ).fetchone()[0])
            excess = max(0, completed - ceiling)
            if excess:
                removed += self.conn.execute(
                    "DELETE FROM management_webhook_outbox WHERE event_id IN ("
                    "SELECT event_id FROM management_webhook_outbox "
                    "WHERE status IN ('DELIVERED','FAILED') "
                    "ORDER BY created_at,event_id LIMIT ?)", (excess,),
                ).rowcount
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return removed

    def pending(self, limit: int = 25) -> list[dict[str, Any]]:
        size = max(1, min(int(limit), 100))
        rows = self.conn.execute(
            "SELECT event_id,webhook_id,event_type,payload_json,attempts "
            "FROM management_webhook_outbox WHERE status='PENDING' "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=?) "
            "ORDER BY created_at,event_id LIMIT ?", (_now(), size),
        ).fetchall()
        return [{"event_id": str(r["event_id"]), "webhook_id": str(r["webhook_id"]),
                 "event_type": str(r["event_type"]), "payload": json.loads(r["payload_json"]),
                 "attempts": int(r["attempts"])} for r in rows]

    def claim_due(self, limit: int = 10) -> list[dict[str, Any]]:
        """Lease bounded due deliveries with a persisted state transition."""
        size = max(1, min(int(limit), 25))
        now = _now()
        stale = (datetime.now(timezone.utc) - timedelta(seconds=90)).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            # Reclaim an interrupted worker, preserving the same stable event id.
            self.conn.execute(
                "UPDATE management_webhook_outbox SET status='PENDING',lease_token='' "
                "WHERE status='SENDING' "
                "AND (last_attempt_at IS NULL OR last_attempt_at<?)", (stale,),
            )
            rows = self.conn.execute(
                "SELECT o.event_id,o.webhook_id,o.payload_json,o.attempts,w.url "
                "FROM management_webhook_outbox o JOIN management_webhooks w ON w.id=o.webhook_id "
                "WHERE o.status='PENDING' AND w.enabled=1 "
                "AND (o.next_attempt_at IS NULL OR o.next_attempt_at<=?) "
                "ORDER BY o.created_at,o.event_id LIMIT ?", (now, size),
            ).fetchall()
            tokens: dict[str, str] = {}
            for row in rows:
                token = secrets.token_hex(16)
                updated = self.conn.execute(
                    "UPDATE management_webhook_outbox "
                    "SET status='SENDING',last_attempt_at=?,lease_token=? "
                    "WHERE event_id=? AND status='PENDING'",
                    (now, token, row["event_id"]),
                ).rowcount
                if updated != 1:
                    raise ControlPlaneError("Webhook delivery claim became stale.")
                tokens[str(row["event_id"])] = token
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return [{"event_id": str(r["event_id"]), "webhook_id": str(r["webhook_id"]),
                 "payload_json": str(r["payload_json"]), "url": str(r["url"]),
                 "attempts": int(r["attempts"]),
                 "lease_token": tokens[str(r["event_id"])]} for r in rows]

    def record_attempt(
        self, event_id: str, *, lease_token: str, delivered: bool, error: str = ""
    ) -> bool:
        """Acknowledge only the exact live delivery lease, never an older worker.

        After a crash/reclaim, a late attempt must not overwrite the new
        worker's state. A successful HTTP response can still be delivered
        twice across crashes; consumers deduplicate with the stable event id.
        """
        if not isinstance(lease_token, str) or not re.fullmatch(r"[0-9a-f]{32}", lease_token):
            raise ControlPlaneError("A valid webhook delivery lease is required.")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT attempts FROM management_webhook_outbox "
                "WHERE event_id=? AND status='SENDING' AND lease_token=?",
                (event_id, lease_token),
            ).fetchone()
            if not row:
                self.conn.execute("COMMIT")
                return False
            attempts = int(row["attempts"]) + 1
            status = "DELIVERED" if delivered else "FAILED" if attempts >= MAX_ATTEMPTS else "PENDING"
            delay = min(1800, 30 * (4 ** max(0, attempts - 1)))
            next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).replace(
                microsecond=0).isoformat().replace("+00:00", "Z")
            updated = self.conn.execute(
                "UPDATE management_webhook_outbox "
                "SET attempts=?,last_attempt_at=?,next_attempt_at=?,status=?,"
                "last_error=?,lease_token='' "
                "WHERE event_id=? AND status='SENDING' AND lease_token=?",
                (attempts, _now(), next_at, status,
                 "" if delivered else str(error or "")[:120], event_id, lease_token),
            ).rowcount
            if updated != 1:
                raise ControlPlaneError("Webhook delivery lease was lost.")
            self.conn.execute("COMMIT")
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise
        return True

    @staticmethod
    def signature(secret: str, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    @staticmethod
    def verify(secret: str, payload: dict[str, Any], signature: str) -> bool:
        return hmac.compare_digest(WebhookStore.signature(secret, payload), str(signature))
