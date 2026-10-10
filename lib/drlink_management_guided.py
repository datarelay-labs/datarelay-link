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
            port = data.get("port")
            if "port" not in data or isinstance(port, bool):
                raise ControlPlaneError("Service Object port is required.")
            if isinstance(port, str):
                port = port.strip()
                if not port.isascii() or not port.isdecimal():
                    raise ControlPlaneError("Service Object port must be an integer.")
            elif not isinstance(port, int):
                raise ControlPlaneError("Service Object port must be an integer.")
            try:
                normalized["port"] = int(port)
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

    @staticmethod
    def _needs_policy_regression(
        kind: str,
        impact: dict[str, Any],
    ) -> bool:
        return bool(
            kind in {
                "remote-access-policy",
                "internet-access-policy",
                "ai-access-policy",
                "remote-access-rule",
                "internet-access-rule",
                "ai-access-rule",
            }
            or impact.get("access_broadened")
            or impact.get("access_narrowed")
        )

    def _dry_run(
        self, kind: str, payload: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        Optional[dict[str, Any]],
        Optional[dict[str, Any]],
        Optional[dict[str, Any]],
    ]:
        from drlink_policy_safety import (
            build_effective_access_graph,
            diff_effective_access_graphs,
            evaluate_graph_paths,
            run_saved_policy_tests,
        )

        savepoint = "drlink_guided_preview"
        previous_batch = self.plane._batch_mode
        previous_results = self.plane._batch_results
        preview: dict[str, Any] = {}
        impact: dict[str, Any] = {}
        regression: Optional[dict[str, Any]] = None
        current_graph: Optional[dict[str, Any]] = None
        proposed_graph: Optional[dict[str, Any]] = None
        proposed_for_current: dict[str, dict[str, Any]] = {}
        needs_policy_safety = False
        self.plane.conn.execute("SAVEPOINT %s" % savepoint)
        self.plane._batch_mode = True
        self.plane._batch_results = []
        try:
            impact = self._impact(kind, payload)
            needs_policy_safety = self._needs_policy_regression(kind, impact)
            if needs_policy_safety:
                current_graph = build_effective_access_graph(self.plane)
            preview = self._execute(kind, payload)
            if needs_policy_safety:
                regression = run_saved_policy_tests(
                    self.plane,
                    required_only=True,
                    enabled_only=True,
                )
                proposed_graph = build_effective_access_graph(self.plane)
                proposed_for_current = evaluate_graph_paths(
                    self.plane,
                    list((current_graph or {}).get("paths") or []),
                )
        finally:
            if self.plane.conn.in_transaction:
                try:
                    self.plane.conn.execute("ROLLBACK TO SAVEPOINT %s" % savepoint)
                finally:
                    self.plane.conn.execute("RELEASE SAVEPOINT %s" % savepoint)
            self.plane._batch_mode = previous_batch
            self.plane._batch_results = previous_results

        blast_radius = None
        graph_overlay = None
        if needs_policy_safety and current_graph is not None and proposed_graph is not None:
            current_for_proposed = evaluate_graph_paths(
                self.plane,
                list(proposed_graph.get("paths") or []),
            )
            blast_radius = diff_effective_access_graphs(
                current_graph,
                proposed_graph,
                current_for_proposed=current_for_proposed,
                proposed_for_current=proposed_for_current,
            )
            added = [
                str(item.get("id"))
                for item in blast_radius.get("references_added") or []
                if item.get("id")
            ]
            removed = [
                str(item.get("id"))
                for item in blast_radius.get("references_removed") or []
                if item.get("id")
            ]
            current_ids = {
                str(item.get("id"))
                for item in current_graph.get("edges") or []
                if item.get("id")
            }
            proposed_ids = {
                str(item.get("id"))
                for item in proposed_graph.get("edges") or []
                if item.get("id")
            }
            graph_overlay = {
                "current": current_graph,
                "proposed": proposed_graph,
                "added_edge_ids": added,
                "removed_edge_ids": removed,
                "unchanged_edge_ids": sorted(current_ids & proposed_ids),
                "decision_changes": list(blast_radius.get("decision_changes") or []),
                "limits": dict(blast_radius.get("limits") or {}),
                "bounded": True,
            }
            impact = {
                **impact,
                "access_broadened": bool(
                    impact.get("access_broadened")
                    or blast_radius.get("access_broadened")
                ),
                "access_narrowed": bool(
                    impact.get("access_narrowed")
                    or blast_radius.get("access_narrowed")
                ),
                "blast_radius": {
                    "affected_rules": list(blast_radius.get("affected_rules") or []),
                    "affected_managed_hosts": list(
                        blast_radius.get("affected_managed_hosts") or []
                    ),
                    "affected_remote_services": list(
                        blast_radius.get("affected_remote_services") or []
                    ),
                    "affected_destinations": list(
                        blast_radius.get("affected_destinations") or []
                    ),
                    "decision_change_count": len(
                        blast_radius.get("decision_changes") or []
                    ),
                    "newly_reachable_count": len(
                        blast_radius.get("newly_reachable") or []
                    ),
                    "newly_blocked_count": len(
                        blast_radius.get("newly_blocked") or []
                    ),
                    "references_added_count": len(
                        blast_radius.get("references_added") or []
                    ),
                    "references_removed_count": len(
                        blast_radius.get("references_removed") or []
                    ),
                    "unknown_count": len(blast_radius.get("unknowns") or []),
                    "limits": dict(blast_radius.get("limits") or {}),
                    "truncated": bool(
                        (blast_radius.get("limits") or {}).get("truncated")
                    ),
                    "truncated_by": list(
                        (blast_radius.get("limits") or {}).get("truncated_by") or []
                    ),
                    "bounded": True,
                },
            }
        return preview, impact, regression, blast_radius, graph_overlay

    def _normalize_fleet_metadata_changes(
        self, changes: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(changes, dict):
            raise ControlPlaneError("Fleet metadata changes must be an object.")
        _reject_unknown(
            changes,
            {"description", "tags", "remove_tags", "add_groups", "remove_groups"},
            "Fleet Managed Host metadata",
        )
        normalized: dict[str, Any] = {}
        if "description" in changes:
            normalized["description"] = _text(
                changes.get("description"),
                field="Managed Host description",
                max_len=1024,
                required=False,
            )
        if "tags" in changes:
            tags = changes.get("tags")
            if not isinstance(tags, dict):
                raise ControlPlaneError("Fleet Managed Host tags must be an object.")
            if len(tags) > MAX_GUIDED_TAGS:
                raise ControlPlaneError(
                    "Fleet Managed Host tags exceed the %d-tag bound."
                    % MAX_GUIDED_TAGS
                )
            normalized["tags"] = {
                _text(key, field="Managed Host tag key", max_len=64): _text(
                    value,
                    field="Managed Host tag value",
                    max_len=256,
                    required=False,
                )
                for key, value in tags.items()
            }
        if "remove_tags" in changes:
            normalized["remove_tags"] = _list_strings(
                changes.get("remove_tags"),
                field="Fleet Managed Host remove_tags",
                max_items=MAX_GUIDED_TAGS,
            )
        for key, field in (
            ("add_groups", "Fleet Managed Host add_groups"),
            ("remove_groups", "Fleet Managed Host remove_groups"),
        ):
            if key in changes:
                normalized[key] = _list_strings(
                    changes.get(key),
                    field=field,
                    max_items=32,
                )
        if set(normalized.get("tags") or {}) & set(
            normalized.get("remove_tags") or []
        ):
            raise ControlPlaneError(
                "A Fleet metadata Change Plan cannot set and remove the same tag."
            )
        if set(normalized.get("add_groups") or []) & set(
            normalized.get("remove_groups") or []
        ):
            raise ControlPlaneError(
                "A Fleet metadata Change Plan cannot add and remove the same group."
            )
        if not normalized or not any(
            (
                "description" in normalized,
                bool(normalized.get("tags")),
                bool(normalized.get("remove_tags")),
                bool(normalized.get("add_groups")),
                bool(normalized.get("remove_groups")),
            )
        ):
            raise ControlPlaneError(
                "Fleet metadata change requires description, tags, remove_tags, "
                "add_groups, or remove_groups."
            )
        return normalized

    def _execute_fleet_metadata(
        self, targets: list[str], changes: dict[str, Any]
    ) -> dict[str, Any]:
        applied = 0
        target_results = []
        for target in targets:
            row = self.plane.require_client(target)
            if str(row["trust_status"] or "").strip().lower() != "trusted":
                raise ControlPlaneError(
                    "Fleet metadata target Managed Host is no longer trusted: %s"
                    % target
                )
            operations = []
            if "description" in changes:
                operations.append(
                    self.plane.set_client_description(
                        target, changes["description"]
                    )
                )
            for key, value in (changes.get("tags") or {}).items():
                operations.append(self.plane.set_client_tag(target, key, value))
            for key in changes.get("remove_tags") or []:
                operations.append(self.plane.unset_client_tag(target, key))
            for group in changes.get("add_groups") or []:
                operations.append(
                    self.plane.set_client_group_member(group, target)
                )
            for group in changes.get("remove_groups") or []:
                operations.append(
                    self.plane.unset_client_group_member(group, target)
                )
            applied += len(operations)
            target_results.append(
                {
                    "managed_host_id": str(row["id"]),
                    "operation_count": len(operations),
                }
            )
        return {
            "target_count": len(targets),
            "operation_count": applied,
            "targets": target_results[:100],
        }

    def preview_fleet_metadata(
        self,
        *,
        actor_id: str,
        resource_type: str,
        resource: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        from drlink_management_service import ManagementQueryService

        normalized = self._normalize_fleet_metadata_changes(changes)
        with ManagementQueryService(self.root) as query:
            selection = query.resolve_management_job_targets(
                resource_type=resource_type,
                resource=resource,
            )
        targets = list(selection["targets"])
        expected_revision = int(self.plane.current_revision())

        self.plane.conn.execute("SAVEPOINT drlink_fleet_metadata_preview")
        previous_batch = self.plane._batch_mode
        previous_results = self.plane._batch_results
        self.plane._batch_mode = True
        self.plane._batch_results = []
        try:
            preview = self._execute_fleet_metadata(targets, normalized)
        except Exception:
            self.plane.conn.execute("ROLLBACK TO drlink_fleet_metadata_preview")
            self.plane.conn.execute("RELEASE drlink_fleet_metadata_preview")
            raise
        else:
            self.plane.conn.execute("ROLLBACK TO drlink_fleet_metadata_preview")
            self.plane.conn.execute("RELEASE drlink_fleet_metadata_preview")
        finally:
            self.plane._batch_mode = previous_batch
            self.plane._batch_results = previous_results

        impact = {
            "access_broadened": False,
            "access_narrowed": False,
            "requires_confirmation": True,
            "destructive": False,
            "target_count": len(targets),
            "operation_count": int(preview.get("operation_count") or 0),
            "warning": (
                "Apply bounded metadata/group/tag changes to %d Managed Host(s) "
                "as one revision." % len(targets)
            ),
        }
        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="CHANGE",
            operation="fleet-metadata.apply",
            resource_type="managed-host-fleet",
            resource_ref=str(selection["resource_ref"]),
            expected_revision=expected_revision,
            payload={
                "targets": targets,
                "selection": {
                    key: selection[key]
                    for key in (
                        "resource_type",
                        "resource_ref",
                        "resource_display",
                        "target_count",
                    )
                },
                "changes": normalized,
            },
            impact=impact,
            confirmation_class=CONFIRM_CHANGE,
        )
        issued.update(
            {
                "selection": {
                    key: selection[key]
                    for key in (
                        "resource_type",
                        "resource_ref",
                        "resource_display",
                        "target_count",
                    )
                },
                "changes": normalized,
                "preview": preview,
            }
        )
        return issued

    def apply_fleet_metadata(
        self,
        *,
        actor_id: str,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != CONFIRM_CHANGE:
            raise ControlPlaneError(
                "Fleet metadata apply requires explicit confirmation 'APPLY'."
            )
        row = self._load_plan(actor_id, change_plan_id)
        if (
            str(row["operation_class"]) != "CHANGE"
            or str(row["operation"]) != "fleet-metadata.apply"
        ):
            raise ControlPlaneError(
                "Change Plan is not a Fleet metadata change."
            )
        try:
            document = json.loads(str(row["payload_json"]))
            targets = [str(item) for item in document.get("targets") or []]
            changes = self._normalize_fleet_metadata_changes(
                dict(document.get("changes") or {})
            )
            selection = dict(document.get("selection") or {})
            impact = json.loads(str(row["impact_json"] or "{}"))
        except Exception as exc:
            self._mark_plan(change_plan_id, "invalid")
            if isinstance(exc, ControlPlaneError):
                raise
            raise ControlPlaneError("Fleet metadata Change Plan is invalid.") from exc
        if not targets or len(targets) > 100:
            self._mark_plan(change_plan_id, "invalid")
            raise ControlPlaneError(
                "Fleet metadata Change Plan target set is invalid."
            )
        expected_revision = int(row["expected_revision"])
        if int(self.plane.current_revision()) != expected_revision:
            self._mark_plan(change_plan_id, "stale")
            raise ConcurrencyError(
                "REVISION_CONFLICT\nExpected revision %s but current revision is %s.\n"
                "No changes were applied.\nReview current state and retry."
                % (expected_revision, self.plane.current_revision())
            )

        def writer():
            previous_batch = self.plane._batch_mode
            previous_results = self.plane._batch_results
            self.plane._batch_mode = True
            self.plane._batch_results = []
            try:
                fleet_result = self._execute_fleet_metadata(targets, changes)
            finally:
                self.plane._batch_mode = previous_batch
                self.plane._batch_results = previous_results
            return {
                "entity": {
                    "type": "managed-host-fleet",
                    "id": str(selection.get("resource_ref") or "fleet"),
                    "name": str(selection.get("resource_display") or "Managed Host Fleet"),
                },
                "operation": "fleet-metadata",
                "after": json.dumps(
                    {
                        "target_count": fleet_result["target_count"],
                        "operation_count": fleet_result["operation_count"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "fleet_result": fleet_result,
            }

        try:
            result = self.plane._mutate(
                "web fleet metadata %s"
                % str(selection.get("resource_ref") or "fleet"),
                "apply bounded Managed Host metadata/group/tag change",
                writer,
                expected_revision=expected_revision,
                impact=impact,
                confirm=True,
                compile_runtime=False,
                actor=actor_id,
                interface="WEB",
            )
        except ConcurrencyError:
            self._mark_plan(change_plan_id, "stale")
            raise
        self._mark_plan(change_plan_id, "applied")
        return {
            "status": "APPLIED",
            "revision": result.get("revision"),
            "selection": selection,
            "changes": changes,
            "result": result.get("fleet_result"),
        }

    def preview_guided_change(
        self,
        *,
        actor_id: str,
        change_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        kind, normalized = self._normalize(change_type, payload)
        expected_revision = int(self.plane.current_revision())
        preview, impact, regression, blast_radius, graph_overlay = self._dry_run(
            kind, normalized
        )
        no_change = str(preview.get("operation") or "").lower() == "noop"
        if regression is not None:
            impact = {
                **impact,
                "required_policy_tests": int(regression.get("count") or 0),
                "required_policy_test_failures": int(
                    regression.get("required_failed") or 0
                ),
            }
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
                "policy_regression": regression,
                "blast_radius": blast_radius,
                "graph_overlay": graph_overlay,
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
        current = int(self.plane.current_revision())
        if current != expected_revision:
            self._mark_plan(change_plan_id, "stale")
            raise ConcurrencyError(
                "REVISION_CONFLICT\nExpected revision %s but current revision is %s.\n"
                "No changes were applied.\nReview current state and retry."
                % (expected_revision, current)
            )
        if bool(document.get("no_change")):
            self._mark_plan(change_plan_id, "applied")
            return {
                "status": "NO_CHANGE",
                "revision": current,
                "change_type": kind,
            }

        if self._needs_policy_regression(kind, impact):
            _preview, _fresh_impact, regression, _blast_radius, _graph_overlay = (
                self._dry_run(kind, payload)
            )
            if regression is not None and not bool(regression.get("ok")):
                self._mark_plan(change_plan_id, "failed")
                failures = [
                    "%s expect=%s got=%s"
                    % (
                        item.get("name"),
                        item.get("expected"),
                        item.get("got"),
                    )
                    for item in regression.get("items") or []
                    if item.get("required") and not item.get("ok")
                ]
                raise ControlPlaneError(
                    "Required Policy Regression Tests failed.\n"
                    "No changes were applied.\n"
                    + "\n".join("  - %s" % item for item in failures)
                )

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
                actor=actor_id,
                interface="WEB",
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
