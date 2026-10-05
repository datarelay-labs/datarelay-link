#!/usr/bin/env python3
"""Shared Data Relay Link 3.0 Core Management Application Service.

This module is transport-neutral. Web and MCP adapters authenticate externally,
then pass an immutable actor context here. Product validation, authorization,
query/change semantics, and handler dispatch stay in this single Core boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from drlink_control_db import ControlPlaneError
from drlink_management_catalog import (
    PLUGIN_NO,
    MANAGEMENT_TOOLS,
    management_permission,
    management_tool,
    mcp_management_descriptors,
    validate_catalog,
)
from drlink_management_change import (
    IMPLEMENTED_MANAGEMENT_CHANGE_TOOLS,
    ManagementChangeService,
)
from drlink_management_service import (
    IMPLEMENTED_MANAGEMENT_TOOLS,
    ManagementQueryService,
)
from drlink_management_guided import GuidedChangeService
from drlink_management_enrollment import ManagementEnrollmentService
from drlink_management_remote_service import ManagementRemoteServiceService
from drlink_management_system import ManagementSystemService
from drlink_management_drafts import (
    DRAFT_ADMIN,
    DRAFT_OBSERVE,
    DRAFT_OPERATE,
    ManagementDraftService,
)

IMPLEMENTED_GUIDED_CHANGE_TOOLS = frozenset(
    {
        "drlink_guided_change_preview",
        "drlink_guided_change_apply",
        "drlink_remote_service_preview",
        "drlink_remote_service_apply",
    }
)

SURFACE_MCP = "MCP"
SURFACE_WEB = "WEB"
SUPPORTED_SURFACES = frozenset({SURFACE_MCP, SURFACE_WEB})


class ManagementAuthorizationError(ControlPlaneError):
    """Authenticated actor lacks the management permission for an operation."""


@dataclass(frozen=True)
class ManagementActor:
    actor_id: str
    permissions: frozenset[str]
    role: str = ""

    @classmethod
    def authenticated(
        cls,
        actor_id: str,
        permissions: set[str] | frozenset[str] | tuple[str, ...],
        *,
        role: str = "",
    ) -> "ManagementActor":
        ident = str(actor_id or "").strip()
        if not ident:
            raise ManagementAuthorizationError("Authenticated management actor is required.")
        if len(ident) > 256:
            raise ManagementAuthorizationError("Management actor identity is too long.")
        normalized = frozenset(str(item or "").strip().lower() for item in permissions)
        normalized = frozenset(item for item in normalized if item)
        return cls(ident, normalized, str(role or "").strip())


def implemented_management_tool_names() -> frozenset[str]:
    """Derive readiness from Core service registries, not a copied adapter list."""
    names = (
        frozenset(IMPLEMENTED_MANAGEMENT_TOOLS)
        | frozenset(IMPLEMENTED_MANAGEMENT_CHANGE_TOOLS)
        | frozenset(IMPLEMENTED_GUIDED_CHANGE_TOOLS)
    )
    catalog = frozenset(tool.name for tool in MANAGEMENT_TOOLS)
    unknown = names - catalog
    if unknown:
        raise RuntimeError("implemented management tool is absent from catalog: %s" % sorted(unknown))
    return names


def _validate_input(tool, arguments: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, Mapping):
        raise ControlPlaneError("Management operation arguments must be an object.")
    schema = dict(tool.input_schema)
    properties = dict(schema.get("properties") or {})
    required = tuple(schema.get("required") or ())
    data = dict(arguments)
    missing = [name for name in required if name not in data]
    if missing:
        raise ControlPlaneError(
            "Management operation is missing required input: %s." % ", ".join(missing)
        )
    unknown = sorted(set(data) - set(properties))
    if unknown and schema.get("additionalProperties") is False:
        raise ControlPlaneError(
            "Management operation has unsupported input: %s." % ", ".join(unknown)
        )
    for name, value in data.items():
        expected = str((properties.get(name) or {}).get("type") or "")
        if value is None:
            continue
        if expected == "string" and not isinstance(value, str):
            raise ControlPlaneError("Management input '%s' must be a string." % name)
        if expected == "integer" and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise ControlPlaneError("Management input '%s' must be an integer." % name)
        if expected == "object" and not isinstance(value, Mapping):
            raise ControlPlaneError("Management input '%s' must be an object." % name)
        if expected == "array" and not isinstance(value, list):
            raise ControlPlaneError("Management input '%s' must be an array." % name)
        if expected == "boolean" and not isinstance(value, bool):
            raise ControlPlaneError("Management input '%s' must be a boolean." % name)
    return data


class ManagementCoreService:
    """One Core application boundary shared by Web and Management MCP."""

    def __init__(self, root: Optional[str] = None):
        self.root = root
        validate_catalog()
        self._ready = implemented_management_tool_names()
        missing_handlers = sorted(
            name for name in self._ready if not callable(getattr(self, "_invoke_" + name, None))
        )
        if missing_handlers:
            raise RuntimeError(
                "implemented management tool has no Core dispatcher: %s" % missing_handlers
            )

    @property
    def ready_tool_names(self) -> frozenset[str]:
        return self._ready

    def _authorize(self, actor: ManagementActor, tool, surface: str) -> None:
        if not isinstance(actor, ManagementActor) or not actor.actor_id:
            raise ManagementAuthorizationError("Authenticated management actor is required.")
        normalized_surface = str(surface or "").strip().upper()
        if normalized_surface not in SUPPORTED_SURFACES:
            raise ManagementAuthorizationError("Unsupported management surface.")
        if normalized_surface == SURFACE_MCP and tool.plugin_exposure == PLUGIN_NO:
            raise ManagementAuthorizationError(
                "Management operation is not exposed through MCP."
            )
        permission = management_permission(tool.permission)
        if permission is None or tool.operation_class not in permission.operation_classes:
            raise ManagementAuthorizationError("Management operation authorization is invalid.")
        if tool.permission.lower() not in actor.permissions:
            raise ManagementAuthorizationError(
                "Management permission '%s' is required." % tool.permission
            )

    def advertised_tool_names(
        self, *, actor: ManagementActor, surface: str
    ) -> tuple[str, ...]:
        normalized_surface = str(surface or "").strip().upper()
        names: list[str] = []
        for tool in MANAGEMENT_TOOLS:
            if tool.name not in self._ready:
                continue
            try:
                self._authorize(actor, tool, normalized_surface)
            except ManagementAuthorizationError:
                continue
            names.append(tool.name)
        return tuple(names)

    def mcp_descriptors(self, *, actor: ManagementActor) -> tuple[dict[str, Any], ...]:
        allowed = set(self.advertised_tool_names(actor=actor, surface=SURFACE_MCP))
        return tuple(
            descriptor
            for descriptor in mcp_management_descriptors()
            if descriptor["name"] in allowed
        )

    def invoke(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        actor: ManagementActor,
        surface: str,
    ) -> dict[str, Any]:
        tool = management_tool(str(name or "").strip())
        if tool is None or tool.name not in self._ready:
            raise ControlPlaneError("Management operation is not implemented.")
        self._authorize(actor, tool, surface)
        data = _validate_input(tool, arguments)
        handler = getattr(self, "_invoke_" + tool.name)
        result = handler(actor, data)
        if not isinstance(result, dict):
            raise ControlPlaneError("Management operation returned an invalid result.")
        return result

    def _invoke_drlink_inventory_list(self, actor: ManagementActor, data: dict) -> dict:
        del actor
        with ManagementQueryService(self.root) as service:
            return service.list_inventory(
                data.get("resource_type", ""),
                query=data.get("query"),
                cursor=data.get("cursor"),
                limit=data.get("limit"),
            ).as_dict()

    def _invoke_drlink_inventory_get(self, actor: ManagementActor, data: dict) -> dict:
        del actor
        with ManagementQueryService(self.root) as service:
            return service.get_inventory(data["resource_type"], data["resource"])

    def _invoke_drlink_health(self, actor: ManagementActor, data: dict) -> dict:
        del actor, data
        with ManagementQueryService(self.root) as service:
            return service.health()

    def _invoke_drlink_policy_test(self, actor: ManagementActor, data: dict) -> dict:
        del actor
        with ManagementQueryService(self.root) as service:
            return service.policy_test(
                plane=data["plane"],
                source=data["source"],
                destination=data["destination"],
                service=data.get("service"),
                permission=data.get("permission"),
                path=data.get("path"),
            )

    def _invoke_drlink_audit_query(self, actor: ManagementActor, data: dict) -> dict:
        del actor
        with ManagementQueryService(self.root) as service:
            return service.audit_query(
                start=data.get("start"),
                end=data.get("end"),
                category=data.get("category"),
                event_type=data.get("event_type"),
                actor=data.get("actor"),
                resource=data.get("resource"),
                result=data.get("result"),
                correlation=data.get("correlation"),
                cursor=data.get("cursor"),
                limit=data.get("limit"),
            ).as_dict()

    def _invoke_drlink_live_access(self, actor: ManagementActor, data: dict) -> dict:
        del actor
        with ManagementQueryService(self.root) as service:
            return service.live_access(
                plane=data["plane"],
                resource_type=data.get("resource_type"),
                resource=data.get("resource"),
                cursor=data.get("cursor"),
                limit=data.get("limit"),
            )

    def _invoke_drlink_job_list(self, actor: ManagementActor, data: dict) -> dict:
        del actor
        with ManagementQueryService(self.root) as service:
            return service.job_list(
                cursor=data.get("cursor"),
                limit=data.get("limit"),
                status=data.get("status"),
                job_type=data.get("job_type"),
            ).as_dict()

    def _invoke_drlink_job_get(self, actor: ManagementActor, data: dict) -> dict:
        del actor
        with ManagementQueryService(self.root) as service:
            return service.job_get(data["job_id"])

    @staticmethod
    def _require_web_role(actor: ManagementActor, *roles: str) -> str:
        role = str(actor.role or "").strip().lower()
        allowed = {str(item).strip().lower() for item in roles}
        if role not in allowed:
            raise ManagementAuthorizationError(
                "This Web management operation requires role: %s." % ", ".join(sorted(roles))
            )
        return role

    def system_status(self, *, actor: ManagementActor) -> dict[str, Any]:
        if "management-read" not in actor.permissions:
            raise ManagementAuthorizationError("management-read is required for system status.")
        self._require_web_role(actor, "Admin", "Operator", "Read Only")
        return ManagementSystemService(self.root).status()

    def certificate_preflight(self, *, actor: ManagementActor) -> dict[str, Any]:
        if "management-diagnose" not in actor.permissions:
            raise ManagementAuthorizationError(
                "management-diagnose is required for certificate preflight."
            )
        self._require_web_role(actor, "Admin", "Operator", "Read Only")
        return ManagementSystemService(self.root).certificate_preflight()

    def backup_validate(self, path: str, *, actor: ManagementActor) -> dict[str, Any]:
        if "management-diagnose" not in actor.permissions:
            raise ManagementAuthorizationError(
                "management-diagnose is required for backup validation."
            )
        self._require_web_role(actor, "Admin", "Operator", "Read Only")
        return ManagementSystemService(self.root).backup_validate(path)

    def backup_create(self, *, actor: ManagementActor) -> dict[str, Any]:
        self._require_web_role(actor, "Admin")
        if "management-config" not in actor.permissions:
            raise ManagementAuthorizationError(
                "management-config is required for backup creation."
            )
        return ManagementSystemService(self.root).backup_create(
            actor_id=actor.actor_id
        )

    def support_bundle_create(self, *, actor: ManagementActor) -> dict[str, Any]:
        self._require_web_role(actor, "Admin", "Operator")
        if "management-job-run" not in actor.permissions:
            raise ManagementAuthorizationError(
                "management-job-run is required for support-bundle generation."
            )
        return ManagementSystemService(self.root).support_bundle_create(
            actor_id=actor.actor_id
        )

    def enrollment_issue_manual(
        self,
        *,
        actor: ManagementActor,
        platform: str,
        ttl_seconds: Optional[int] = None,
        label: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        self._require_web_role(actor, "Admin")
        if "management-config" not in actor.permissions:
            raise ManagementAuthorizationError("management-config is required for enrollment issuance.")
        return ManagementEnrollmentService(self.root).issue_manual(
            platform=platform,
            ttl_seconds=ttl_seconds,
            label=label,
            note=note,
            actor_id=actor.actor_id,
        )

    def enrollment_list(self, *, actor: ManagementActor, limit: int = 50) -> dict[str, Any]:
        if "management-read" not in actor.permissions:
            raise ManagementAuthorizationError("management-read is required for enrollment status.")
        self._require_web_role(actor, "Admin", "Operator", "Read Only")
        return ManagementEnrollmentService(self.root).list_enrollments(limit=limit)

    def enrollment_issue_zero_touch(
        self,
        *,
        actor: ManagementActor,
        platform: str,
        ttl_seconds: Optional[int] = None,
        label: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        self._require_web_role(actor, "Admin")
        if "management-config" not in actor.permissions:
            raise ManagementAuthorizationError("management-config is required for enrollment issuance.")
        return ManagementEnrollmentService(self.root).issue_zero_touch(
            platform=platform,
            ttl_seconds=ttl_seconds,
            label=label,
            note=note,
            actor_id=actor.actor_id,
        )

    @staticmethod
    def _draft_authority(actor: ManagementActor) -> str:
        role = str(actor.role or "").strip().lower()
        if role == "admin":
            if "management-config" not in actor.permissions:
                raise ManagementAuthorizationError("Admin Draft authority requires management-config.")
            return DRAFT_ADMIN
        if role == "operator":
            if "management-config" not in actor.permissions:
                raise ManagementAuthorizationError("Operator Draft authority requires management-config.")
            return DRAFT_OPERATE
        if role == "read only":
            if "management-read" not in actor.permissions:
                raise ManagementAuthorizationError("Read Only Draft authority requires management-read.")
            return DRAFT_OBSERVE
        raise ManagementAuthorizationError("Draft Workspace requires a trusted Web operator role.")

    def draft_list(self, *, actor: ManagementActor, limit: int = 50) -> dict[str, Any]:
        authority = self._draft_authority(actor)
        del authority
        with ManagementDraftService(self.root) as service:
            return {"items": service.list(actor_id=actor.actor_id, limit=limit)}

    def draft_get(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        self._draft_authority(actor)
        with ManagementDraftService(self.root) as service:
            return service.get(draft_id, actor_id=actor.actor_id)

    def draft_export(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        self._draft_authority(actor)
        with ManagementDraftService(self.root) as service:
            return {
                "draft_id": draft_id,
                "bundle_text": service.export(draft_id, actor_id=actor.actor_id),
            }

    def draft_create(self, *, actor: ManagementActor, bundle_text: str) -> dict[str, Any]:
        authority = self._draft_authority(actor)
        if authority == DRAFT_OBSERVE:
            raise ManagementAuthorizationError("Read Only authority cannot create a Draft.")
        with ManagementDraftService(self.root) as service:
            return service.create(actor_id=actor.actor_id, bundle_text=bundle_text)

    def draft_update(
        self, draft_id: str, *, actor: ManagementActor, bundle_text: str
    ) -> dict[str, Any]:
        authority = self._draft_authority(actor)
        if authority == DRAFT_OBSERVE:
            raise ManagementAuthorizationError("Read Only authority cannot update a Draft.")
        with ManagementDraftService(self.root) as service:
            return service.update(draft_id, actor_id=actor.actor_id, bundle_text=bundle_text)

    def draft_test(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        authority = self._draft_authority(actor)
        if authority == DRAFT_OBSERVE:
            raise ManagementAuthorizationError("Read Only authority cannot test a mutable Draft.")
        with ManagementDraftService(self.root) as service:
            return service.test_bundle(
                draft_id, actor_id=actor.actor_id, authority=authority
            )

    def draft_diff(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        authority = self._draft_authority(actor)
        if authority == DRAFT_OBSERVE:
            raise ManagementAuthorizationError("Read Only authority cannot diff a mutable Draft.")
        with ManagementDraftService(self.root) as service:
            return service.diff(
                draft_id, actor_id=actor.actor_id, authority=authority
            )

    def draft_preview(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.draft_diff(draft_id, actor=actor)

    def configuration_export(self, *, actor: ManagementActor) -> dict[str, Any]:
        self._draft_authority(actor)
        with ManagementDraftService(self.root) as service:
            return {
                "bundle_text": service.export_current_configuration(),
                "redacted": True,
                "authoritative_mutation": False,
            }

    def draft_apply(
        self,
        draft_id: str,
        *,
        actor: ManagementActor,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        authority = self._draft_authority(actor)
        with ManagementDraftService(self.root) as service:
            return service.apply(
                draft_id,
                actor_id=actor.actor_id,
                authority=authority,
                change_plan_id=change_plan_id,
                confirmation=confirmation,
            )

    def draft_cancel(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        authority = self._draft_authority(actor)
        if authority == DRAFT_OBSERVE:
            raise ManagementAuthorizationError("Read Only authority cannot cancel a Draft.")
        with ManagementDraftService(self.root) as service:
            return service.cancel(draft_id, actor_id=actor.actor_id)

    def _invoke_drlink_guided_change_preview(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with GuidedChangeService(self.root) as service:
            return service.preview_guided_change(
                actor_id=actor.actor_id,
                change_type=data["change_type"],
                payload=dict(data["payload"]),
            )

    def _invoke_drlink_guided_change_apply(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with GuidedChangeService(self.root) as service:
            return service.apply_guided_change(
                actor_id=actor.actor_id,
                change_plan_id=data["change_plan_id"],
                confirmation=data["confirmation"],
            )

    def _invoke_drlink_remote_service_preview(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with ManagementRemoteServiceService(self.root) as service:
            return service.preview(
                actor_id=actor.actor_id,
                owner=data["owner"],
                name=data["name"],
                operation=data["operation"],
                destination=data.get("destination"),
                service=data.get("service"),
                enabled=data.get("enabled"),
            )

    def _invoke_drlink_remote_service_apply(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with ManagementRemoteServiceService(self.root) as service:
            return service.apply(
                actor_id=actor.actor_id,
                change_plan_id=data["change_plan_id"],
                confirmation=data["confirmation"],
            )

    def _invoke_drlink_temporary_access_preview(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with ManagementChangeService(self.root) as service:
            return service.preview_temporary_access(
                actor_id=actor.actor_id,
                plane=data["plane"],
                rule=data["rule"],
                operation=data["operation"],
                expires_at=data.get("expires_at"),
            )

    def _invoke_drlink_temporary_access_apply(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with ManagementChangeService(self.root) as service:
            return service.apply_temporary_access(
                actor_id=actor.actor_id,
                change_plan_id=data["change_plan_id"],
                confirmation=data["confirmation"],
            )

    def _invoke_drlink_emergency_cutoff_preview(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with ManagementChangeService(self.root) as service:
            return service.preview_emergency_cutoff(
                actor_id=actor.actor_id,
                plane=data["plane"],
                scope_kind=data["scope_kind"],
                scope_ref=data.get("scope_ref"),
                operation=data.get("operation", "apply"),
                reason=data.get("reason", ""),
            )

    def _invoke_drlink_emergency_cutoff_apply(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with ManagementChangeService(self.root) as service:
            return service.apply_emergency_cutoff(
                actor_id=actor.actor_id,
                change_plan_id=data["change_plan_id"],
                confirmation=data["confirmation"],
                expected_operation="apply",
            )

    def _invoke_drlink_emergency_cutoff_clear(
        self, actor: ManagementActor, data: dict
    ) -> dict:
        with ManagementChangeService(self.root) as service:
            return service.apply_emergency_cutoff(
                actor_id=actor.actor_id,
                change_plan_id=data["change_plan_id"],
                confirmation=data["confirmation"],
                expected_operation="clear",
            )
