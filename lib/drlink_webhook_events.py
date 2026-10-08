#!/usr/bin/env python3
"""Idempotent audit-to-Webhook bridge. Delivery is never in the mutation path."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from drlink_webhooks import MAX_OUTBOX, WebhookStore, _now

AUDIT_BATCH = 100


def event_class(category: str, event_type: str) -> Optional[str]:
    category = str(category or "").upper()
    name = str(event_type or "").lower()
    if name.startswith(("managed_host.", "managed_host_", "agent.lifecycle")):
        return "managed_host.lifecycle"
    if name.startswith(("policy.", "policy_", "access_rule.", "access_rule_")) or category in (
        "POLICY_CHANGE", "CONFIG_CHANGE", "CONFIGURATION_CHANGE",
    ):
        return "policy.change"
    if category in ("ATTENTION", "SECURITY_ALERT", "SYSTEM_ALERT"):
        return "attention"
    if category == "SECURITY_LIFECYCLE" or name.startswith((
        "service_account.", "management_webhook.", "web.", "mfa.",
    )):
        return "security.lifecycle"
    return None


def stage_audit_events(store: WebhookStore, limit: int = AUDIT_BATCH) -> dict[str, int]:
    """Fan out eligible audit events with durable per-subscription high-water marks.

    Cursor progression and idempotent insert share one SQLite transaction.
    A full outbox stops advancement rather than dropping events.
    """
    size = max(1, min(int(limit), AUDIT_BATCH))
    staged, examined = 0, 0
    conn = store.conn
    conn.execute("BEGIN IMMEDIATE")
    try:
        subscriptions = conn.execute(
            "SELECT id,event_classes FROM management_webhooks WHERE enabled=1 ORDER BY id"
        ).fetchall()
        backlog = int(conn.execute(
            "SELECT COUNT(*) FROM management_webhook_outbox WHERE status IN ('PENDING','SENDING')"
        ).fetchone()[0])
        for hook in subscriptions:
            wid = str(hook["id"])
            selected = set(str(hook["event_classes"]).splitlines())
            cursor_row = conn.execute(
                "SELECT last_audit_id FROM management_webhook_audit_cursors WHERE webhook_id=?",
                (wid,),
            ).fetchone()
            if cursor_row is None:
                # Pre-feature legacy hook: do not replay arbitrary historical
                # security records. Newly created hooks always set cursor on create.
                start = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM audit_events").fetchone()[0])
                conn.execute(
                    "INSERT INTO management_webhook_audit_cursors(webhook_id,last_audit_id)"
                    " VALUES (?,?)", (wid, start),
                )
                continue
            last = int(cursor_row["last_audit_id"])
            rows = conn.execute(
                "SELECT id,category,event_type,occurred_at,result,entity_type,entity_id "
                "FROM audit_events WHERE id>? ORDER BY id ASC LIMIT ?", (last, size),
            ).fetchall()
            for row in rows:
                klass = event_class(row["category"], row["event_type"])
                if klass in selected:
                    if backlog >= MAX_OUTBOX:
                        break
                    event_id = "whe_" + hashlib.sha256(
                        (wid + ":" + str(row["id"])).encode()
                    ).hexdigest()[:32]
                    envelope: dict[str, Any] = {
                        "schema_version": 1,
                        "event_id": event_id,
                        "timestamp": str(row["occurred_at"] or _now()),
                        "event_type": klass,
                        "data": {
                            "source_audit_id": int(row["id"]),
                            "event": str(row["event_type"] or "")[:120],
                            "resource_type": str(row["entity_type"] or "")[:80],
                            # Do not place arbitrary audit entity identifiers into a
                            # third-party payload. Correlate locally via source_audit_id.
                            "resource_fingerprint": hashlib.sha256(
                                str(row["entity_id"] or "").encode()
                            ).hexdigest()[:16],
                            "result": str(row["result"] or "")[:40],
                        },
                    }
                    body = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
                    if len(body.encode()) > 8192:
                        break
                    written = conn.execute(
                        "INSERT OR IGNORE INTO management_webhook_outbox("
                        "event_id,webhook_id,event_type,payload_json,next_attempt_at,created_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (event_id, wid, klass, body, _now(), _now()),
                    ).rowcount
                    staged += written
                    backlog += written
                last = int(row["id"])
                examined += 1
            conn.execute(
                "UPDATE management_webhook_audit_cursors SET last_audit_id=? WHERE webhook_id=?",
                (last, wid),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"staged": staged, "examined": examined}
