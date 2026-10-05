#!/usr/bin/env python3
"""Guided DRL3-3 Core Change Plan service for low-risk server-owned nouns."""
from __future__ import annotations

import json
from typing import Any, Optional

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError
from drlink_management_change import (
    CONFIRM_CHANGE,
    ManagementChangeService,
)

GUIDED_CHANGE_TYPES = frozenset(
    {
        "managed-host-metadata",
        "network-object",
        "network-group",
        "service-object",
        "service-group",
        "permission-object",
        "permission-group",
        "remote-access-rule",
        "internet-access-rule",
        "ai-access-rule",
        "remote-access-policy",
        "internet-access-policy",
        "ai-access-policy",
    }
)
MAX_GUIDED_MEMBERS = 100
MAX_GUIDED_TAGS = 64


def _text(value: Any, *, field: str, max_len: int = 256, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ControlPlaneError("%s is required." % field)
    if len(text) > max_len:
        raise ControlPlaneError("%s is too long." % field)
    return text


def _list_strings(
    value: Any,
    *,
    field: str,
    max_items: int = MAX_GUIDED_MEMBERS,
) -> list[str]:
    if not isinstance(value, list):
        raise ControlPlaneError("%s must be an array." % field)
    if len(value) > max_items:
        raise ControlPlaneError("%s exceeds the %d-item bound." % (field, max_items))
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _text(raw, field=field)
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _reject_unknown(data: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ControlPlaneError(
            "%s has unsupported fields: %s." % (label, ", ".join(unknown))
        )


class GuidedChangeService(ManagementChangeService):
    """Preview/apply service that delegates semantics to existing Core CRUD."""

    def _normalize(
        self, change_type: str, payload: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        kind = str(change_type or "").strip().lower()
        if kind not in GUIDED_CHANGE_TYPES:
            raise ControlPlaneError("Unsupported guided change type: %s" % change_type)
        if not isinstance(payload, dict):
            raise ControlPlaneError("Guided change payload must be an object.")
        data = dict(payload)
        operation = str(data.get("operation") or "set").strip().lower()
        if kind in ("remote-access-policy", "internet-access-policy", "ai-access-policy"):
            if operation not in ("set-enforcement", "reset"):
                raise ControlPlaneError(
                    "Access Policy operation must be 'set-enforcement' or 'reset'."
                )
            if operation == "reset":
                _reject_unknown(data, {"operation"}, kind)
                return kind, {"operation": "reset"}
            _reject_unknown(data, {"operation", "enabled"}, kind)
            if not isinstance(data.get("enabled"), bool):
                raise ControlPlaneError("Access Policy enabled must be a boolean.")
            return kind, {"operation": "set-enforcement", "enabled": bool(data["enabled"])}
        if operation not in ("set", "delete"):
            raise ControlPlaneError("Guided change operation must be 'set' or 'delete'.")

        if kind in ("remote-access-rule", "internet-access-rule", "ai-access-rule"):
            common = {"operation", "name"}
            if kind == "ai-access-rule":
                allowed = common | {
                    "mode", "source", "destination", "permission", "paths",
                    "enabled", "expires_at",
                }
            else:
                allowed = common | {
                    "mode", "source", "destination", "service", "enabled", "expires_at",
                }
            _reject_unknown(data, allowed, kind)
            name = _text(data.get("name"), field="Access Rule name", max_len=128)
            normalized: dict[str, Any] = {"operation": operation, "name": name}
            if operation == "delete":
                if set(data) - common:
                    raise ControlPlaneError("Access Rule delete accepts only operation and name.")
                return kind, normalized
            for field in ("mode", "source", "destination"):
                if field in data:
                    normalized[field] = _text(data.get(field), field=field, max_len=256).lower() if field == "mode" else _text(data.get(field), field=field, max_len=256)
            if "enabled" in data:
                if not isinstance(data.get("enabled"), bool):
                    raise ControlPlaneError("Access Rule enabled must be a boolean.")
                normalized["enabled"] = bool(data["enabled"])
            if "expires_at" in data:
                normalized["expires_at"] = _text(
                    data.get("expires_at"), field="expires_at", max_len=64, required=False
                )
            if kind == "ai-access-rule":
                if "permission" in data:
                    normalized["permission"] = _text(data.get("permission"), field="permission", max_len=128)
                if "paths" in data:
                    normalized["paths"] = _list_strings(data.get("paths"), field="AI Access paths")
            elif "service" in data:
                normalized["service"] = _text(data.get("service"), field="service", max_len=128)
            return kind, normalized

        if kind == "managed-host-metadata":
            if operation != "set":
                raise ControlPlaneError("Managed Host metadata supports only 'set'.")
            _reject_unknown(
                data,
                {
                    "operation",
                    "host",
                    "label",
                    "description",
                    "tags",
                    "remove_tags",
                },
                "Managed Host metadata",
            )
            host = _text(data.get("host"), field="Managed Host")
            normalized: dict[str, Any] = {"operation": "set", "host": host}
            changed_fields = 0
            if "label" in data:
                normalized["label"] = _text(
                    data.get("label"), field="Managed Host label", max_len=128
                )
                changed_fields += 1
            if "description" in data:
                normalized["description"] = _text(
                    data.get("description"),
                    field="Managed Host description",
                    max_len=1024,
                    required=False,
                )
                changed_fields += 1
            if "tags" in data:
                tags = data.get("tags")
                if not isinstance(tags, dict):
                    raise ControlPlaneError("Managed Host tags must be an object.")
                if len(tags) > MAX_GUIDED_TAGS:
                    raise ControlPlaneError(
                        "Managed Host tags exceed the %d-tag bound." % MAX_GUIDED_TAGS
                    )
                clean_tags: dict[str, str] = {}
                for key, value in tags.items():
                    clean_tags[_text(key, field="Managed Host tag key", max_len=64)] = _text(
                        value,
                        field="Managed Host tag value",
                        max_len=256,
                        required=False,
                    )
                normalized["tags"] = clean_tags
                changed_fields += len(clean_tags)
            if "remove_tags" in data:
                normalized["remove_tags"] = _list_strings(
                    data.get("remove_tags"),
                    field="Managed Host remove_tags",
                    max_items=MAX_GUIDED_TAGS,
                )
                changed_fields += len(normalized["remove_tags"])
            if not changed_fields:
                raise ControlPlaneError(
                    "Managed Host metadata change requires label, description, tags, or remove_tags."
                )
            return kind, normalized

        common = {"operation", "name"}
        if kind == "network-object":
            allowed = common | {"type", "value"}
        elif kind == "network-group":
            allowed = common | {"members"}
        elif kind == "service-object":
            allowed = common | {"type", "port"}
        elif kind == "service-group":
            allowed = common | {"members"}
        elif kind == "permission-object":
            allowed = common | {"permissions"}
        else:
            allowed = common | {"members"}
        _reject_unknown(data, allowed, kind)
        name = _text(data.get("name"), field="%s name" % kind, max_len=128)
        normalized = {"operation": operation, "name": name}
        if operation == "delete":
            if set(data) - common:
                raise ControlPlaneError(
                    "%s delete accepts only operation and name." % kind
                )
            return kind, normalized

        if kind == "network-object":
            if "type" in data:
                normalized["type"] = _text(
                    data.get("type"), field="Network Object type", max_len=32
                ).lower()
            if "value" in data:
                normalized["value"] = _text(
                    data.get("value"), field="Network Object value", max_len=512
                )
            if "value" not in normalized:
                raise ControlPlaneError("Network Object value is required.")
        elif kind == "network-group":
            normalized["members"] = _list_strings(
                data.get("members"), field="Network Group members"
            )
        elif kind == "service-object":
            if "type" in data:
                normalized["type"] = _text(
                    data.get("type"), field="Service Object type", max_len=32
                ).lower()
            if "port" not in data or isinstance(data.get("port"), bool):
                raise ControlPlaneError("Service Object port is required.")
            try:
                normalized["port"] = int(data["port"])
            except (TypeError, ValueError) as exc:
                raise ControlPlaneError("Service Object port must be an integer.") from exc
        elif kind == "service-group":
            normalized["members"] = _list_strings(
                data.get("members"), field="Service Group members"
            )
        elif kind == "permission-object":
            normalized["permissions"] = _list_strings(
                data.get("permissions"), field="Permission Object permissions"
            )
        else:
            normalized["members"] = _list_strings(
                data.get("members"), field="Permission Group members"
            )
        return kind, normalized

    def _managed_host_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        host = payload["host"]
        row = self.plane.require_client(host)
        operations: list[dict[str, Any]] = []
        if "label" in payload and str(row["label"] or "") != payload["label"]:
            operations.append(self.plane.set_client_label(host, payload["label"]))
            row = self.plane.require_client(host)
        if "description" in payload and str(row["description"] or "") != payload["description"]:
            operations.append(
                self.plane.set_client_description(host, payload["description"])
            )
        current_tags = {
            str(item["key"]): str(item["value"] or "")
            for item in self.plane.conn.execute(
                "SELECT key,value FROM client_tags WHERE client_id=?",
                (row["id"],),
            )
        }
        for key, value in (payload.get("tags") or {}).items():
            if current_tags.get(key) != value:
                operations.append(self.plane.set_client_tag(host, key, value))
                current_tags[key] = value
        for key in payload.get("remove_tags") or []:
            if key in current_tags:
                operations.append(self.plane.unset_client_tag(host, key))
                current_tags.pop(key, None)
        return {
            "operation": "noop" if not operations else "update",
            "name": str(row["label"] or row["hostname"] or row["id"]),
            "entity": {
                "type": "managed-host",
                "id": str(row["id"]),
                "name": str(row["label"] or row["hostname"] or row["id"]),
            },
            "changes": len(operations),
        }

    def _execute(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        import drlink_v24 as v24

        op = payload["operation"]
        if kind in ("remote-access-policy", "internet-access-policy", "ai-access-policy"):
            family = kind.split("-", 1)[0]
            if op == "reset":
                return v24.reset_access_policy(self.plane, family, confirm=True)
            return v24.set_policy_enforcement(
                self.plane, family, bool(payload["enabled"]), confirm=True
            )
        if kind in ("remote-access-rule", "internet-access-rule", "ai-access-rule"):
            name = payload["name"]
            if kind == "ai-access-rule":
                if op == "delete":
                    return v24.unset_ai_access_rule(self.plane, name, confirm=True)
                kwargs = {
                    key: payload[key]
                    for key in ("mode", "source", "destination", "permission", "paths", "enabled", "expires_at")
                    if key in payload
                }
                return v24.set_ai_access_rule(
                    self.plane, name, oneshot=True, confirm=True, **kwargs
                )
            family = "remote" if kind == "remote-access-rule" else "internet"
            if op == "delete":
                return v24.unset_access_rule(self.plane, family, name, confirm=True)
            kwargs = {
                key: payload[key]
                for key in ("mode", "source", "destination", "service", "enabled", "expires_at")
                if key in payload
            }
            return v24.set_access_rule(
                self.plane, family, name, oneshot=True, confirm=True, **kwargs
            )
        if kind == "managed-host-metadata":
            return self._managed_host_metadata(payload)
        name = payload["name"]
        if kind == "network-object":
            if op == "delete":
                return v24.unset_network_object(self.plane, name, confirm=True)
            return v24.set_network_object(
                self.plane,
                name,
                type=payload.get("type"),
                value=payload["value"],
                oneshot=True,
                confirm=True,
            )
        if kind == "network-group":
            if op == "delete":
                return self.plane.unset_object_group(
                    name, confirm=True, public_label="Network Group"
                )
            return v24.set_network_group(
                self.plane,
                name,
                members=payload["members"],
                oneshot=True,
                confirm=True,
            )
        if kind == "service-object":
            if op == "delete":
                return v24.unset_service_object(self.plane, name, confirm=True)
            return v24.set_service_object(
                self.plane,
                name,
                type=payload.get("type"),
                port=payload["port"],
                oneshot=True,
                confirm=True,
            )
        if kind == "service-group":
            if op == "delete":
                return v24.unset_service_group(self.plane, name, confirm=True)
            return v24.set_service_group(
                self.plane,
                name,
                members=payload["members"],
                oneshot=True,
                confirm=True,
            )
        if kind == "permission-object":
            if op == "delete":
                return v24.unset_permission_object(self.plane, name, confirm=True)
            return v24.set_permission_object(
                self.plane,
                name,
                permissions=payload["permissions"],
                oneshot=True,
                confirm=True,
            )
        if kind == "permission-group":
            if op == "delete":
                return v24.unset_permission_group(self.plane, name, confirm=True)
            return v24.set_permission_group(
                self.plane,
                name,
                members=payload["members"],
                oneshot=True,
                confirm=True,
            )
        raise ControlPlaneError("Unsupported guided change type.")

    def _impact(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        import drlink_v24 as v24

        if kind in ("remote-access-policy", "internet-access-policy", "ai-access-policy"):
            family = kind.split("-", 1)[0]
            policy = v24.get_access_policy(self.plane, family)
            if payload["operation"] == "reset":
                return {
                    "requires_confirmation": True,
                    "destructive": True,
                    "access_broadened": True,
                    "access_narrowed": False,
                    "before": "mode=%s enforcement=%s" % (
                        policy.get("mode") or "none", policy.get("enforcement") or "enabled"
                    ),
                    "after": "mode removed / rules removed / effective result ALLOW",
                    "warning": "Reset removes this Access Policy mode and all of its rules.",
                }
            desired = bool(payload["enabled"])
            current_enabled = str(policy.get("enforcement") or "enabled").lower() == "enabled"
            return {
                "requires_confirmation": True,
                "destructive": False,
                "access_broadened": bool(current_enabled and not desired),
                "access_narrowed": bool((not current_enabled) and desired),
                "before": "enforcement %s" % ("ENABLED" if current_enabled else "DISABLED"),
                "after": "enforcement %s" % ("ENABLED" if desired else "DISABLED"),
            }

        if kind in ("remote-access-rule", "internet-access-rule", "ai-access-rule"):
            family = (
                "ai" if kind == "ai-access-rule"
                else "remote" if kind == "remote-access-rule"
                else "internet"
            )
            name = payload["name"]
            if family == "ai":
                existing = self.plane.conn.execute(
                    "SELECT * FROM ai_policy_rules WHERE name=? COLLATE NOCASE", (name,)
                ).fetchone()
            else:
                existing = self.plane._get_rule(family, name)
            policy = v24.get_access_policy(self.plane, family)
            mode = str(payload.get("mode") or policy.get("mode") or "").lower()
            if payload["operation"] == "delete":
                if existing is None:
                    return {"requires_confirmation": True, "destructive": True}
                special = v24.last_enabled_rule_mutation_impact(
                    self.plane, family, name, disabling=False
                )
                if special:
                    return {"destructive": True, "requires_confirmation": True, **dict(special)}
                enabled = bool(existing["enabled"])
                return {
                    "requires_confirmation": True,
                    "destructive": True,
                    "access_broadened": bool(enabled and mode == "blacklist"),
                    "access_narrowed": bool(enabled and mode == "whitelist"),
                    "affected_rules": [name],
                    "warning": "Deleting this enabled %s rule changes effective access." % mode.upper() if enabled and mode else "Delete Access Rule '%s'." % name,
                }
            if existing is not None:
                if family == "ai":
                    result = v24.ai_access_rule_update_security_impact(
                        self.plane,
                        name,
                        source=payload.get("source"),
                        destination=payload.get("destination"),
                        permission=payload.get("permission"),
                        paths=payload.get("paths"),
                        enabled=payload.get("enabled"),
                        expires_at=payload.get("expires_at") if "expires_at" in payload else None,
                    )
                else:
                    result = v24.access_rule_update_security_impact(
                        self.plane,
                        family,
                        name,
                        source=payload.get("source"),
                        destination=payload.get("destination"),
                        service=payload.get("service"),
                        enabled=payload.get("enabled"),
                        expires_at=payload.get("expires_at") if "expires_at" in payload else None,
                    )
                if result:
                    return dict(result)
            enabled = payload.get("enabled")
            return {
                "requires_confirmation": True,
                "destructive": False,
                "access_broadened": bool(existing is None and enabled is not False and mode == "whitelist"),
                "access_narrowed": bool(existing is None and enabled is not False and mode == "blacklist"),
                "affected_rules": [name],
            }

        if payload["operation"] == "delete":
            label = kind.replace("-", " ").title()
            return {
                "requires_confirmation": True,
                "destructive": True,
                "warning": "This permanently deletes the %s." % label,
                "resource": label,
                "name": payload.get("name") or payload.get("host"),
            }
        if kind == "managed-host-metadata":
            return {"requires_confirmation": False, "destructive": False}
        kwargs: dict[str, Any] = {}
        if kind == "network-object":
            kwargs["value"] = payload.get("value")
        elif kind in ("network-group", "service-group", "permission-group"):
            kwargs["members"] = payload.get("members")
        elif kind == "service-object":
            kwargs["type"] = payload.get("type")
            kwargs["port"] = payload.get("port")
        elif kind == "permission-object":
            kwargs["permissions"] = payload.get("permissions")
        impact = v24.referenced_selector_mutation_security_impact(
            self.plane,
            kind=kind,
            name=payload["name"],
            **kwargs,
        )
        return dict(impact or {"requires_confirmation": False, "destructive": False})

    def _dry_run(
        self, kind: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        savepoint = "drlink_guided_preview"
        previous_batch = self.plane._batch_mode
        previous_results = self.plane._batch_results
        self.plane.conn.execute("SAVEPOINT %s" % savepoint)
        self.plane._batch_mode = True
        self.plane._batch_results = []
        try:
            impact = self._impact(kind, payload)
            return self._execute(kind, payload), impact
        finally:
            if self.plane.conn.in_transaction:
                try:
                    self.plane.conn.execute("ROLLBACK TO SAVEPOINT %s" % savepoint)
                finally:
                    self.plane.conn.execute("RELEASE SAVEPOINT %s" % savepoint)
            self.plane._batch_mode = previous_batch
            self.plane._batch_results = previous_results

    def preview_guided_change(
        self,
        *,
        actor_id: str,
        change_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        kind, normalized = self._normalize(change_type, payload)
        expected_revision = int(self.plane.current_revision())
        preview, impact = self._dry_run(kind, normalized)
        no_change = str(preview.get("operation") or "").lower() == "noop"
        resource_ref = str(
            normalized.get("name")
            or normalized.get("host")
            or preview.get("name")
            or ""
        )
        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="CHANGE",
            operation="guided.%s.%s" % (kind, normalized["operation"]),
            resource_type=kind,
            resource_ref=resource_ref,
            expected_revision=expected_revision,
            payload={
                "change_type": kind,
                "change": normalized,
                "no_change": no_change,
            },
            impact=impact,
            confirmation_class=CONFIRM_CHANGE,
        )
        issued.update(
            {
                "preview": preview,
                "no_change": no_change,
                "change_type": kind,
            }
        )
        return issued

    def apply_guided_change(
        self,
        *,
        actor_id: str,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != CONFIRM_CHANGE:
            raise ControlPlaneError(
                "Guided change apply requires explicit confirmation 'APPLY'."
            )
        row = self._load_plan(actor_id, change_plan_id)
        if str(row["operation_class"]) != "CHANGE" or not str(row["operation"]).startswith(
            "guided."
        ):
            raise ControlPlaneError("Change Plan is not a guided management change.")
        try:
            document = json.loads(str(row["payload_json"]))
            kind, payload = self._normalize(
                str(document.get("change_type") or ""),
                dict(document.get("change") or {}),
            )
            impact = json.loads(str(row["impact_json"] or "{}"))
        except Exception as exc:
            self._mark_plan(change_plan_id, "invalid")
            if isinstance(exc, ControlPlaneError):
                raise
            raise ControlPlaneError("Change Plan payload is invalid.") from exc

        expected_revision = int(row["expected_revision"])
        if bool(document.get("no_change")):
            current = int(self.plane.current_revision())
            if current != expected_revision:
                self._mark_plan(change_plan_id, "stale")
                raise ConcurrencyError(
                    "REVISION_CONFLICT\nExpected revision %s but current revision is %s.\n"
                    "No changes were applied.\nReview current state and retry."
                    % (expected_revision, current)
                )
            self._mark_plan(change_plan_id, "applied")
            return {
                "status": "NO_CHANGE",
                "revision": current,
                "change_type": kind,
            }

        def writer():
            previous_batch = self.plane._batch_mode
            previous_results = self.plane._batch_results
            self.plane._batch_mode = True
            self.plane._batch_results = []
            try:
                result = self._execute(kind, payload)
            finally:
                self.plane._batch_mode = previous_batch
                self.plane._batch_results = previous_results
            entity = result.get("entity") if isinstance(result, dict) else None
            if not isinstance(entity, dict):
                entity = {
                    "type": kind,
                    "name": str(payload.get("name") or payload.get("host") or ""),
                }
            return {
                "entity": entity,
                "operation": "guided-change",
                "after": json.dumps(
                    {
                        "change_type": kind,
                        "resource": str(payload.get("name") or payload.get("host") or ""),
                        "operation": payload["operation"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "guided_result": result,
            }

        try:
            result = self.plane._mutate(
                "web guided %s %s"
                % (kind, str(payload.get("name") or payload.get("host") or "")),
                "apply guided management change",
                writer,
                expected_revision=expected_revision,
                impact=impact,
                confirm=True,
            )
        except ConcurrencyError:
            self._mark_plan(change_plan_id, "stale")
            raise
        self._mark_plan(change_plan_id, "applied")
        return {
            "status": "APPLIED",
            "revision": result.get("revision"),
            "change_type": kind,
            "resource_type": str(row["resource_type"]),
            "resource_ref": str(row["resource_ref"]),
            "result": result.get("guided_result"),
        }
