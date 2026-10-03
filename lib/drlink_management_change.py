#!/usr/bin/env python3
"""Data Relay Link 3.0 management Change Plan service.

Change Plans are short-lived operational state.  They bind previewed mutations
to actor, Server, operation, resource, and expected authoritative revision.
They are not configuration authority and do not create configuration revisions
until a plan is successfully applied.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_v30_temporal import ACTIVE, canonical_expiry, temporary_access_state

PLAN_VALIDITY_SECONDS = 300
SERVER_ID_META_KEY = "v30_server_instance_id"
CONFIRM_CHANGE = "APPLY"
CONFIRM_CUTOFF = "CONFIRM CUTOFF"


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
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


class ManagementChangeService:
    """Core preview/apply boundary for admitted 3.0 management mutations."""

    def __init__(self, root: Optional[str] = None):
        self.root = root
        self.plane = ControlPlane(root)
        self.server_id = self._server_id()

    def close(self) -> None:
        self.plane.close()

    def __enter__(self) -> "ManagementChangeService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _server_id(self) -> str:
        row = self.plane.conn.execute(
            "SELECT value FROM system_meta WHERE key = ?", (SERVER_ID_META_KEY,)
        ).fetchone()
        if row and str(row["value"] or "").strip():
            return str(row["value"]).strip()
        candidate = "srv-" + secrets.token_hex(16)
        self.plane.conn.execute(
            "INSERT OR IGNORE INTO system_meta(key, value) VALUES (?, ?)",
            (SERVER_ID_META_KEY, candidate),
        )
        row = self.plane.conn.execute(
            "SELECT value FROM system_meta WHERE key = ?", (SERVER_ID_META_KEY,)
        ).fetchone()
        if not row or not str(row["value"] or "").strip():
            raise ControlPlaneError("Unable to establish Data Relay Link Server identity.")
        return str(row["value"]).strip()

    @staticmethod
    def _require_actor(actor_id: str) -> str:
        actor = str(actor_id or "").strip()
        if not actor:
            raise ControlPlaneError("Authenticated management actor is required.")
        if len(actor) > 256:
            raise ControlPlaneError("Management actor identity is too long.")
        return actor

    def _issue_plan(
        self,
        *,
        actor_id: str,
        operation_class: str,
        operation: str,
        resource_type: str,
        resource_ref: str,
        expected_revision: int,
        payload: dict[str, Any],
        impact: Optional[dict[str, Any]] = None,
        confirmation_class: str = CONFIRM_CHANGE,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        actor = self._require_actor(actor_id)
        current = now or _utc_now()
        valid_until = current + timedelta(seconds=PLAN_VALIDITY_SECONDS)
        token = "cp_" + secrets.token_urlsafe(24)
        digest = _token_hash(token)
        self.plane.conn.execute(
            "INSERT INTO management_change_plans("
            "token_hash,actor_id,server_id,operation_class,operation,"
            "resource_type,resource_ref,expected_revision,payload_json,impact_json,"
            "confirmation_class,status,created_at,expires_at,consumed_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,NULL)",
            (
                digest,
                actor,
                self.server_id,
                operation_class,
                operation,
                resource_type,
                resource_ref,
                int(expected_revision),
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                json.dumps(impact or {}, sort_keys=True, separators=(",", ":")),
                confirmation_class,
                _utc_text(current),
                _utc_text(valid_until),
            ),
        )
        return {
            "change_plan_id": token,
            "operation_class": operation_class,
            "operation": operation,
            "resource_type": resource_type,
            "resource_ref": resource_ref,
            "expected_revision": int(expected_revision),
            "impact": dict(impact or {}),
            "confirmation_class": confirmation_class,
            "valid_until": _utc_text(valid_until),
        }

    def _load_plan(
        self,
        actor_id: str,
        change_plan_id: str,
        *,
        now: Optional[datetime] = None,
    ):
        actor = self._require_actor(actor_id)
        token = str(change_plan_id or "").strip()
        if not token.startswith("cp_") or len(token) < 16:
            raise ControlPlaneError("Change Plan is invalid or unavailable.")
        digest = _token_hash(token)
        row = self.plane.conn.execute(
            "SELECT * FROM management_change_plans WHERE token_hash = ?", (digest,)
        ).fetchone()
        if not row:
            raise ControlPlaneError("Change Plan is invalid or unavailable.")
        if str(row["actor_id"]) != actor or str(row["server_id"]) != self.server_id:
            raise ControlPlaneError("Change Plan is invalid or unavailable.")
        if str(row["status"]) != "pending":
            raise ControlPlaneError(
                "Change Plan is no longer pending (status=%s)." % row["status"]
            )
        current = now or _utc_now()
        try:
            expired = current >= _parse_utc(str(row["expires_at"]))
        except ValueError:
            expired = True
        if expired:
            self.plane.conn.execute(
                "UPDATE management_change_plans SET status='expired', consumed_at=? "
                "WHERE token_hash=? AND status='pending'",
                (_utc_text(current), digest),
            )
            raise ControlPlaneError("Change Plan expired. Preview the change again.")
        return row

    def _mark_plan(
        self,
        change_plan_id: str,
        status: str,
        *,
        now: Optional[datetime] = None,
    ) -> None:
        self.plane.conn.execute(
            "UPDATE management_change_plans SET status=?, consumed_at=? "
            "WHERE token_hash=? AND status='pending'",
            (
                status,
                _utc_text(now or _utc_now()),
                _token_hash(change_plan_id),
            ),
        )

    def preview_temporary_access(
        self,
        *,
        actor_id: str,
        plane: str,
        rule: str,
        operation: str,
        expires_at: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Preview set/change/clear of one WHITELIST rule expiry."""
        import drlink_v24 as v24

        family = str(plane or "").strip().lower()
        if family not in ("remote", "internet", "ai"):
            raise ControlPlaneError("Unsupported access plane: %s" % plane)
        rule_name = str(rule or "").strip()
        if not rule_name:
            raise ControlPlaneError("Temporary Access rule is required.")
        action = str(operation or "").strip().lower()
        if action not in ("set", "clear"):
            raise ControlPlaneError(
                "Temporary Access operation must be 'set' or 'clear'."
            )

        policy = v24.get_access_policy(self.plane, family)
        if str(policy.get("mode") or "").lower() != "whitelist":
            raise ControlPlaneError(
                "Temporary Access is supported only for WHITELIST grants."
            )

        if family == "ai":
            row = self.plane.conn.execute(
                "SELECT * FROM ai_policy_rules WHERE name = ? COLLATE NOCASE",
                (rule_name,),
            ).fetchone()
        else:
            row = self.plane._get_rule(family, rule_name)
        if not row:
            raise ControlPlaneError("Rule '%s' was not found." % rule_name)

        current_expiry = (
            str(row["expires_at"]).strip()
            if "expires_at" in row.keys() and row["expires_at"]
            else None
        )
        desired_expiry: Optional[str]
        if action == "clear":
            desired_expiry = None
            mutation_value = ""
        else:
            if not str(expires_at or "").strip():
                raise ControlPlaneError(
                    "Temporary Access set requires an expiration timestamp."
                )
            try:
                desired_expiry = canonical_expiry(str(expires_at))
            except ValueError as exc:
                raise ControlPlaneError(str(exc)) from exc
            state = temporary_access_state(desired_expiry, now=now or _utc_now())
            if state.status != ACTIVE:
                raise ControlPlaneError(
                    "Temporary Access expiration must be in the trusted future."
                )
            mutation_value = desired_expiry

        no_change = current_expiry == desired_expiry
        if family == "ai":
            impact = v24.ai_access_rule_update_security_impact(
                self.plane, rule_name, expires_at=mutation_value
            )
        else:
            impact = v24.access_rule_update_security_impact(
                self.plane, family, rule_name, expires_at=mutation_value
            )

        expected_revision = self.plane.current_revision()
        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="CHANGE",
            operation="temporary-access.%s" % action,
            resource_type="%s-access-rule" % family,
            resource_ref=rule_name,
            expected_revision=expected_revision,
            payload={
                "kind": "temporary-access",
                "plane": family,
                "rule": rule_name,
                "operation": action,
                "expires_at": desired_expiry,
                "no_change": no_change,
            },
            impact=impact,
            confirmation_class=CONFIRM_CHANGE,
            now=now,
        )
        issued.update(
            {
                "current_expires_at": current_expiry,
                "desired_expires_at": desired_expiry,
                "no_change": no_change,
            }
        )
        return issued

    def apply_temporary_access(
        self,
        *,
        actor_id: str,
        change_plan_id: str,
        confirmation: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Apply one previously previewed Temporary Access plan."""
        import drlink_v24 as v24

        if str(confirmation or "").strip().upper() != CONFIRM_CHANGE:
            raise ControlPlaneError(
                "Temporary Access apply requires explicit confirmation 'APPLY'."
            )
        row = self._load_plan(actor_id, change_plan_id, now=now)
        if str(row["operation_class"]) != "CHANGE" or not str(row["operation"]).startswith(
            "temporary-access."
        ):
            raise ControlPlaneError("Change Plan is not a Temporary Access change.")

        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception as exc:
            self._mark_plan(change_plan_id, "invalid", now=now)
            raise ControlPlaneError("Change Plan payload is invalid.") from exc

        expected_revision = int(row["expected_revision"])
        if payload.get("no_change"):
            if self.plane.current_revision() != expected_revision:
                self._mark_plan(change_plan_id, "stale", now=now)
                raise ConcurrencyError(
                    "REVISION_CONFLICT\n"
                    "Expected revision %s but current revision is %s.\n"
                    "No changes were applied.\nReview current state and retry."
                    % (expected_revision, self.plane.current_revision())
                )
            self._mark_plan(change_plan_id, "applied", now=now)
            return {
                "status": "NO_CHANGE",
                "revision": expected_revision,
                "operation": str(row["operation"]),
            }

        family = str(payload.get("plane") or "")
        rule_name = str(payload.get("rule") or "")
        desired = payload.get("expires_at")
        mutation_value = "" if desired is None else str(desired)
        try:
            if family == "ai":
                result = v24.set_ai_access_rule(
                    self.plane,
                    rule_name,
                    expires_at=mutation_value,
                    oneshot=True,
                    confirm=True,
                    expected_revision=expected_revision,
                )
            else:
                result = v24.set_access_rule(
                    self.plane,
                    family,
                    rule_name,
                    expires_at=mutation_value,
                    oneshot=True,
                    confirm=True,
                    expected_revision=expected_revision,
                )
        except ConcurrencyError:
            self._mark_plan(change_plan_id, "stale", now=now)
            raise

        self._mark_plan(change_plan_id, "applied", now=now)
        return {
            "status": "APPLIED",
            "revision": result.get("revision"),
            "operation": str(row["operation"]),
            "resource_type": str(row["resource_type"]),
            "resource_ref": str(row["resource_ref"]),
            "expires_at": desired,
        }

    def _resolve_cutoff_resource(
        self,
        plane: str,
        scope_kind: str,
        scope_ref: Optional[str],
    ) -> tuple[str, str, str, str]:
        """Resolve public cutoff selectors to stable Core identities."""
        from drlink_v30_cutoff import normalize_cutoff_scope

        family, kind, ref = normalize_cutoff_scope(plane, scope_kind, scope_ref)
        if kind == "plane":
            return family, kind, "", family

        if family == "remote" and kind == "remote-service":
            rows = self.plane.conn.execute(
                "SELECT id,name FROM published_services "
                "WHERE id=? OR name=? COLLATE NOCASE ORDER BY id LIMIT 3",
                (ref, ref),
            ).fetchall()
            if not rows:
                raise ControlPlaneError("Remote Service '%s' was not found." % ref)
            if len(rows) > 1:
                raise ControlPlaneError(
                    "Remote Service selector '%s' is ambiguous; use its immutable ID." % ref
                )
            return family, kind, str(rows[0]["id"]), str(rows[0]["name"])

        if family == "internet" and kind == "managed-host":
            rows = self.plane.conn.execute(
                "SELECT id,label,hostname FROM clients "
                "WHERE id=? OR label=? COLLATE NOCASE OR hostname=? COLLATE NOCASE "
                "ORDER BY id LIMIT 3",
                (ref, ref, ref),
            ).fetchall()
            if not rows:
                raise ControlPlaneError("Managed Host '%s' was not found." % ref)
            if len(rows) > 1:
                raise ControlPlaneError(
                    "Managed Host selector '%s' is ambiguous; use its immutable ID." % ref
                )
            display = str(rows[0]["label"] or rows[0]["hostname"] or rows[0]["id"])
            return family, kind, str(rows[0]["id"]), display

        if family == "ai" and kind == "ai-identity":
            rows = self.plane.conn.execute(
                "SELECT id,name FROM ai_principals "
                "WHERE id=? OR name=? COLLATE NOCASE ORDER BY id LIMIT 3",
                (ref, ref),
            ).fetchall()
            if not rows:
                raise ControlPlaneError("AI Identity '%s' was not found." % ref)
            if len(rows) > 1:
                raise ControlPlaneError("AI Identity selector '%s' is ambiguous." % ref)
            # Runtime AI authorization receives the canonical public identity name.
            return family, kind, str(rows[0]["name"]), str(rows[0]["name"])

        raise ControlPlaneError("Unsupported cutoff resource scope.")

    def preview_emergency_cutoff(
        self,
        *,
        actor_id: str,
        plane: str,
        scope_kind: str,
        scope_ref: Optional[str] = None,
        operation: str = "apply",
        reason: str = "",
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Preview applying or clearing a reversible new-authorization cutoff."""
        family, kind, canonical_ref, display = self._resolve_cutoff_resource(
            plane, scope_kind, scope_ref
        )
        action = str(operation or "").strip().lower()
        if action not in ("apply", "clear"):
            raise ControlPlaneError(
                "Emergency Cutoff operation must be 'apply' or 'clear'."
            )
        safe_reason = str(reason or "").strip()
        if len(safe_reason) > 500:
            raise ControlPlaneError("Emergency Cutoff reason is too long.")

        existing = self.plane.conn.execute(
            "SELECT * FROM emergency_cutoffs "
            "WHERE plane=? AND scope_kind=? AND scope_ref=?",
            (family, kind, canonical_ref),
        ).fetchone()
        active = bool(existing and existing["active"])
        existing_reason = str(existing["reason"] or "") if existing else ""
        if action == "apply":
            no_change = active and existing_reason == safe_reason
            impact = {
                "access_broadened": False,
                "access_narrowed": True,
                "requires_confirmation": True,
                "warning": (
                    "Emergency New-Access Cutoff will deny new %s authorization "
                    "for %s %s." % (family, kind, display)
                ),
            }
        else:
            no_change = not active
            impact = {
                "access_broadened": True,
                "access_narrowed": False,
                "requires_confirmation": True,
                "warning": (
                    "Clearing Emergency New-Access Cutoff may allow new %s authorization "
                    "under the unchanged normal policy for %s %s."
                    % (family, kind, display)
                ),
            }

        expected_revision = self.plane.current_revision()
        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="INCIDENT_CHANGE",
            operation="emergency-cutoff.%s" % action,
            resource_type="emergency-cutoff",
            resource_ref=("%s:%s" % (kind, canonical_ref)) if canonical_ref else family,
            expected_revision=expected_revision,
            payload={
                "kind": "emergency-cutoff",
                "plane": family,
                "scope_kind": kind,
                "scope_ref": canonical_ref,
                "scope_display": display,
                "operation": action,
                "reason": safe_reason,
                "no_change": no_change,
            },
            impact=impact,
            confirmation_class=CONFIRM_CUTOFF,
            now=now,
        )
        issued.update(
            {
                "scope_kind": kind,
                "scope_ref": canonical_ref,
                "scope_display": display,
                "currently_active": active,
                "desired_active": action == "apply",
                "active_sessions_terminated": False,
                "no_change": no_change,
            }
        )
        return issued

    def apply_emergency_cutoff(
        self,
        *,
        actor_id: str,
        change_plan_id: str,
        confirmation: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Apply/clear a previously previewed Emergency New-Access Cutoff."""
        if str(confirmation or "").strip().upper() != CONFIRM_CUTOFF:
            raise ControlPlaneError(
                "Emergency Cutoff requires explicit confirmation 'CONFIRM CUTOFF'."
            )
        row = self._load_plan(actor_id, change_plan_id, now=now)
        if str(row["operation_class"]) != "INCIDENT_CHANGE" or not str(
            row["operation"]
        ).startswith("emergency-cutoff."):
            raise ControlPlaneError("Change Plan is not an Emergency Cutoff change.")

        try:
            payload = json.loads(str(row["payload_json"]))
            impact = json.loads(str(row["impact_json"] or "{}"))
        except Exception as exc:
            self._mark_plan(change_plan_id, "invalid", now=now)
            raise ControlPlaneError("Change Plan payload is invalid.") from exc

        expected_revision = int(row["expected_revision"])
        if payload.get("no_change"):
            current = self.plane.current_revision()
            if current != expected_revision:
                self._mark_plan(change_plan_id, "stale", now=now)
                raise ConcurrencyError(
                    "REVISION_CONFLICT\n"
                    "Expected revision %s but current revision is %s.\n"
                    "No changes were applied.\nReview current state and retry."
                    % (expected_revision, current)
                )
            self._mark_plan(change_plan_id, "applied", now=now)
            return {
                "status": "NO_CHANGE",
                "revision": expected_revision,
                "operation": str(row["operation"]),
                "active_sessions_terminated": False,
            }

        family = str(payload.get("plane") or "")
        kind = str(payload.get("scope_kind") or "")
        ref = str(payload.get("scope_ref") or "")
        action = str(payload.get("operation") or "")
        reason = str(payload.get("reason") or "")
        timestamp = _utc_text(now or _utc_now())

        def writer():
            existing = self.plane.conn.execute(
                "SELECT * FROM emergency_cutoffs "
                "WHERE plane=? AND scope_kind=? AND scope_ref=?",
                (family, kind, ref),
            ).fetchone()
            if action == "apply":
                if existing:
                    self.plane.conn.execute(
                        "UPDATE emergency_cutoffs SET active=1,reason=?,"
                        "row_version=row_version+1,updated_at=? WHERE id=?",
                        (reason, timestamp, existing["id"]),
                    )
                    cutoff_id = str(existing["id"])
                    op = "apply"
                else:
                    cutoff_id = "cut_" + secrets.token_hex(10)
                    self.plane.conn.execute(
                        "INSERT INTO emergency_cutoffs("
                        "id,plane,scope_kind,scope_ref,active,reason,row_version,"
                        "created_at,updated_at"
                        ") VALUES (?,?,?,?,1,?,1,?,?)",
                        (cutoff_id, family, kind, ref, reason, timestamp, timestamp),
                    )
                    op = "apply"
            else:
                if not existing:
                    raise ControlPlaneError("Emergency Cutoff state no longer exists.")
                self.plane.conn.execute(
                    "UPDATE emergency_cutoffs SET active=0,"
                    "row_version=row_version+1,updated_at=? WHERE id=?",
                    (timestamp, existing["id"]),
                )
                cutoff_id = str(existing["id"])
                op = "clear"
            return {
                "entity": {
                    "type": "emergency-cutoff",
                    "id": cutoff_id,
                    "name": "%s:%s:%s" % (family, kind, ref or "*"),
                },
                "operation": op,
                "after": "active=%s" % (action == "apply"),
            }

        try:
            result = self.plane._mutate(
                ("%s emergency-cutoff %s %s" % (action, family, kind)).strip(),
                "Emergency New-Access Cutoff %s" % action,
                writer,
                expected_revision=expected_revision,
                impact=impact,
                confirm=True,
            )
        except ConcurrencyError:
            self._mark_plan(change_plan_id, "stale", now=now)
            raise

        self._mark_plan(change_plan_id, "applied", now=now)
        return {
            "status": "APPLIED",
            "revision": result.get("revision"),
            "operation": str(row["operation"]),
            "plane": family,
            "scope_kind": kind,
            "scope_ref": ref,
            "active": action == "apply",
            "active_sessions_terminated": False,
        }
