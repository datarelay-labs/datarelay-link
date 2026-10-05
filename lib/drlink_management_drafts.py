#!/usr/bin/env python3
"""Bounded non-authoritative Draft Workspace over the canonical v2.4 bundle engine."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from drlink_control_db import ControlPlaneError, utc_now_iso
from drlink_control_plane import ConcurrencyError
from drlink_management_change import CONFIRM_CHANGE, ManagementChangeService
from drlink_v24_bundle import BundleError, apply_v24_plan, format_v24_plan, prepare_v24_plan

DRAFT_OBSERVE = "OBSERVE"
DRAFT_OPERATE = "OPERATE"
DRAFT_ADMIN = "ADMIN"
DRAFT_AUTHORITIES = frozenset({DRAFT_OBSERVE, DRAFT_OPERATE, DRAFT_ADMIN})

DRAFT_TTL_SECONDS = 3600
MAX_ACTIVE_DRAFTS_PER_ACTOR = 16
MAX_DRAFT_BYTES = 128 * 1024
MAX_DRAFT_LIST = 50

POLICY_CHANGE_KINDS = frozenset(
    {
        "remote-access",
        "internet-access",
        "ai-access",
        "remote-access-rule",
        "internet-access-rule",
        "ai-access-rule",
    }
)



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


def _actor(value: str) -> str:
    actor = str(value or "").strip()
    if not actor:
        raise ControlPlaneError("Authenticated draft actor is required.")
    if len(actor) > 256:
        raise ControlPlaneError("Draft actor identity is too long.")
    return actor


def _authority(value: str) -> str:
    level = str(value or "").strip().upper()
    if level not in DRAFT_AUTHORITIES:
        raise ControlPlaneError("Unsupported Draft Workspace authority.")
    return level


def _bundle_text(value: str) -> str:
    text = str(value or "")
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_DRAFT_BYTES:
        raise ControlPlaneError(
            "Draft ConfigurationBundle exceeds the %d-byte bound." % MAX_DRAFT_BYTES
        )
    return text


class ManagementDraftService(ManagementChangeService):
    """Operational Draft Workspace; authoritative mutation occurs only through bundle Apply."""

    def __init__(self, root: Optional[str] = None):
        super().__init__(root)

    def __enter__(self) -> "ManagementDraftService":
        return self

    def _expire(self, *, now: Optional[datetime] = None) -> int:
        current = _utc_text(now or _utc_now())
        changed = self.plane.conn.execute(
            "UPDATE management_drafts SET status='EXPIRED',updated_at=? "
            "WHERE status='DRAFT' AND expires_at<=?",
            (current, current),
        ).rowcount
        return int(changed or 0)

    def _load(
        self,
        draft_id: str,
        *,
        actor_id: str,
        now: Optional[datetime] = None,
        require_draft: bool = True,
    ):
        actor = _actor(actor_id)
        ident = str(draft_id or "").strip()
        if not ident.startswith("draft_"):
            raise ControlPlaneError("Draft was not found.")
        self._expire(now=now)
        row = self.plane.conn.execute(
            "SELECT * FROM management_drafts WHERE id=? AND actor_id=?",
            (ident, actor),
        ).fetchone()
        if not row:
            raise ControlPlaneError("Draft was not found.")
        if require_draft and str(row["status"]) != "DRAFT":
            raise ControlPlaneError(
                "Draft is no longer editable (status=%s)." % row["status"]
            )
        return row

    def create(
        self,
        *,
        actor_id: str,
        bundle_text: str = "",
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        actor = _actor(actor_id)
        text = _bundle_text(bundle_text)
        current = now or _utc_now()
        now_text = _utc_text(current)
        expires = _utc_text(current + timedelta(seconds=DRAFT_TTL_SECONDS))
        self._expire(now=current)
        active = int(
            self.plane.conn.execute(
                "SELECT COUNT(*) FROM management_drafts "
                "WHERE actor_id=? AND status='DRAFT'",
                (actor,),
            ).fetchone()[0]
            or 0
        )
        if active >= MAX_ACTIVE_DRAFTS_PER_ACTOR:
            raise ControlPlaneError(
                "Draft Workspace limit reached (%d active drafts)."
                % MAX_ACTIVE_DRAFTS_PER_ACTOR
            )
        ident = "draft_" + secrets.token_hex(12)
        base_revision = int(self.plane.current_revision())
        self.plane.conn.execute(
            "INSERT INTO management_drafts("
            "id,actor_id,base_revision,bundle_text,status,created_at,updated_at,"
            "expires_at,applied_revision,last_error"
            ") VALUES (?,?,?,?,'DRAFT',?,?,?,NULL,'')",
            (
                ident,
                actor,
                base_revision,
                text,
                now_text,
                now_text,
                expires,
            ),
        )
        return self.get(ident, actor_id=actor, now=current)

    def get(
        self,
        draft_id: str,
        *,
        actor_id: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        row = self._load(
            draft_id, actor_id=actor_id, now=now, require_draft=False
        )
        return {key: row[key] for key in row.keys()}

    def list(
        self,
        *,
        actor_id: str,
        limit: int = 50,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        actor = _actor(actor_id)
        self._expire(now=now)
        count = max(1, min(int(limit), MAX_DRAFT_LIST))
        rows = self.plane.conn.execute(
            "SELECT id,actor_id,base_revision,status,created_at,updated_at,"
            "expires_at,applied_revision,last_error "
            "FROM management_drafts WHERE actor_id=? "
            "ORDER BY updated_at DESC,id DESC LIMIT ?",
            (actor, count),
        ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def update(
        self,
        draft_id: str,
        *,
        actor_id: str,
        bundle_text: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        text = _bundle_text(bundle_text)
        row = self._load(draft_id, actor_id=actor_id, now=now)
        current = _utc_text(now or _utc_now())
        self.plane.conn.execute(
            "UPDATE management_drafts SET bundle_text=?,updated_at=?,last_error='' "
            "WHERE id=? AND actor_id=? AND status='DRAFT'",
            (text, current, str(row["id"]), str(row["actor_id"])),
        )
        return self.get(str(row["id"]), actor_id=str(row["actor_id"]), now=now)

    def preview(
        self,
        draft_id: str,
        *,
        actor_id: str,
        authority: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        _authority(authority)
        row = self._load(draft_id, actor_id=actor_id, now=now)
        current_revision = int(self.plane.current_revision())
        base_revision = int(row["base_revision"])
        if current_revision != base_revision:
            raise ConcurrencyError(
                "REVISION_CONFLICT\n"
                "Draft base revision: %s\n"
                "Current revision: %s\n"
                "No changes were applied.\n"
                "Create a fresh Draft against current state."
                % (base_revision, current_revision)
            )
        text = str(row["bundle_text"] or "")
        if not text.strip():
            raise ControlPlaneError("Draft ConfigurationBundle is empty.")
        try:
            plan = prepare_v24_plan(self.plane, text, role="server")
        except BundleError as exc:
            self.plane.conn.execute(
                "UPDATE management_drafts SET last_error=?,updated_at=? WHERE id=?",
                (str(exc)[:1024], utc_now_iso(), str(row["id"])),
            )
            raise
        if str(plan.context) != "server":
            raise ControlPlaneError("Web Draft Workspace supports Server bundles only.")
        if int(plan.base_revision or 0) != base_revision:
            raise ConcurrencyError(
                "REVISION_CONFLICT\n"
                "Bundle source revision: %s\n"
                "Draft base revision: %s\n"
                "No changes were applied."
                % (plan.base_revision, base_revision)
            )
        changes = [dict(change) for change in plan.mutating_changes]
        policy_change = any(
            str(change.get("kind") or "") in POLICY_CHANGE_KINDS for change in changes
        )
        security_impact = list(plan.security_impact or [])
        requires_admin = bool(policy_change or security_impact)
        bundle_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="CHANGE",
            operation="configuration-bundle.apply",
            resource_type="management-draft",
            resource_ref=str(row["id"]),
            expected_revision=base_revision,
            payload={
                "kind": "configuration-bundle",
                "draft_id": str(row["id"]),
                "bundle_sha256": bundle_sha256,
                "requires_admin": requires_admin,
                "no_change": bool(plan.no_change),
            },
            impact={
                "requires_admin": requires_admin,
                "security_impact": security_impact,
                "change_count": len(changes),
            },
            confirmation_class=CONFIRM_CHANGE,
            now=now,
        )
        return {
            **issued,
            "draft_id": str(row["id"]),
            "base_revision": base_revision,
            "current_revision": current_revision,
            "no_change": bool(plan.no_change),
            "changes": changes,
            "security_impact": security_impact,
            "requires_admin": requires_admin,
            "formatted_plan": format_v24_plan(plan),
            "bundle_text": text,
        }

    def apply(
        self,
        draft_id: str,
        *,
        actor_id: str,
        authority: str,
        change_plan_id: str,
        confirmation: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        level = _authority(authority)
        if level == DRAFT_OBSERVE:
            raise ControlPlaneError("Read Only authority cannot apply a Draft.")
        if str(confirmation or "").strip().upper() != CONFIRM_CHANGE:
            raise ControlPlaneError("Draft Apply requires explicit confirmation 'APPLY'.")

        plan_row = self._load_plan(actor_id, change_plan_id, now=now)
        if (
            str(plan_row["operation_class"]) != "CHANGE"
            or str(plan_row["operation"]) != "configuration-bundle.apply"
            or str(plan_row["resource_type"]) != "management-draft"
            or str(plan_row["resource_ref"]) != str(draft_id)
        ):
            raise ControlPlaneError("Change Plan is not for this Draft Apply.")
        try:
            payload = json.loads(str(plan_row["payload_json"]))
        except Exception as exc:
            self._mark_plan(change_plan_id, "invalid", now=now)
            raise ControlPlaneError("Draft Change Plan payload is invalid.") from exc

        row = self._load(draft_id, actor_id=actor_id, now=now)
        expected_revision = int(plan_row["expected_revision"])
        current_revision = int(self.plane.current_revision())
        if current_revision != expected_revision or int(row["base_revision"]) != expected_revision:
            self._mark_plan(change_plan_id, "stale", now=now)
            raise ConcurrencyError(
                "REVISION_CONFLICT\n"
                "Expected revision %s but current revision is %s.\n"
                "No changes were applied.\nReview current state and preview the Draft again."
                % (expected_revision, current_revision)
            )
        text = str(row["bundle_text"] or "")
        bundle_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if (
            payload.get("draft_id") != str(row["id"])
            or payload.get("bundle_sha256") != bundle_sha256
        ):
            self._mark_plan(change_plan_id, "stale", now=now)
            raise ControlPlaneError(
                "Draft changed after preview. Preview the current Draft again before Apply."
            )
        if bool(payload.get("requires_admin")) and level != DRAFT_ADMIN:
            raise ControlPlaneError(
                "Admin authority is required for policy/security-impacting Draft Apply."
            )

        bundle_plan = prepare_v24_plan(self.plane, text, role="server")
        if int(bundle_plan.base_revision or 0) != expected_revision:
            self._mark_plan(change_plan_id, "stale", now=now)
            raise ConcurrencyError("Draft ConfigurationBundle revision no longer matches its Change Plan.")
        try:
            result = apply_v24_plan(
                self.plane,
                bundle_plan,
                confirm=True,
                command="web draft apply %s" % row["id"],
                summary="apply Web Draft Workspace through Core Change Plan",
                snapshot_meta={
                    "draft_id": str(row["id"]),
                    "actor_id": str(row["actor_id"]),
                    "change_plan_id": str(change_plan_id),
                },
            )
        except ConcurrencyError:
            self._mark_plan(change_plan_id, "stale", now=now)
            raise
        except Exception as exc:
            self._mark_plan(change_plan_id, "failed", now=now)
            self.plane.conn.execute(
                "UPDATE management_drafts SET last_error=?,updated_at=? WHERE id=?",
                (str(exc)[:1024], utc_now_iso(), str(row["id"])),
            )
            raise
        revision = int(result.get("revision") or self.plane.current_revision())
        self._mark_plan(change_plan_id, "applied", now=now)
        self.plane.conn.execute(
            "UPDATE management_drafts SET status='APPLIED',applied_revision=?,"
            "updated_at=?,last_error='' WHERE id=? AND status='DRAFT'",
            (revision, utc_now_iso(), str(row["id"])),
        )
        return {
            "draft_id": str(row["id"]),
            "change_plan_id": str(change_plan_id),
            "status": str(result.get("status") or "APPLIED"),
            "revision": revision,
            "no_change": str(result.get("status") or "") == "NO_CHANGE",
        }

    def cancel(
        self,
        draft_id: str,
        *,
        actor_id: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        row = self._load(draft_id, actor_id=actor_id, now=now)
        self.plane.conn.execute(
            "UPDATE management_drafts SET status='CANCELLED',updated_at=? "
            "WHERE id=? AND actor_id=? AND status='DRAFT'",
            (utc_now_iso(), str(row["id"]), str(row["actor_id"])),
        )
        return {
            "draft_id": str(row["id"]),
            "status": "CANCELLED",
            "authoritative_mutation": False,
        }

    def export(self, draft_id: str, *, actor_id: str) -> str:
        row = self._load(
            draft_id, actor_id=actor_id, require_draft=False
        )
        return str(row["bundle_text"] or "")
