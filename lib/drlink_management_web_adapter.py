#!/usr/bin/env python3
"""Data Relay Link 3.0 first-party Web API management projection.

DRL3-1 defines the adapter boundary only. The separately installable HTTP/Web
service and browser authentication/session platform are DRL3-2 work.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from drlink_management_core import (
    ManagementActor,
    ManagementCoreService,
    SURFACE_WEB,
)

WEB_API_NAMESPACE = "/api/v1"


class ManagementWebApiAdapter:
    def __init__(self, root: Optional[str] = None):
        self.core = ManagementCoreService(root)

    def capability_names(self, *, actor: ManagementActor) -> tuple[str, ...]:
        return self.core.advertised_tool_names(actor=actor, surface=SURFACE_WEB)

    def invoke(
        self,
        *,
        operation: str,
        payload: Mapping[str, Any],
        actor: ManagementActor,
    ) -> dict[str, Any]:
        return self.core.invoke(
            name=operation,
            arguments=payload,
            actor=actor,
            surface=SURFACE_WEB,
        )
    def draft_list(self, *, actor: ManagementActor, limit: int = 50) -> dict[str, Any]:
        return self.core.draft_list(actor=actor, limit=limit)

    def draft_get(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.draft_get(draft_id, actor=actor)

    def draft_export(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.draft_export(draft_id, actor=actor)

    def draft_create(
        self, *, actor: ManagementActor, bundle_text: str
    ) -> dict[str, Any]:
        return self.core.draft_create(actor=actor, bundle_text=bundle_text)

    def draft_update(
        self, draft_id: str, *, actor: ManagementActor, bundle_text: str
    ) -> dict[str, Any]:
        return self.core.draft_update(draft_id, actor=actor, bundle_text=bundle_text)

    def draft_test(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.draft_test(draft_id, actor=actor)

    def draft_diff(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.draft_diff(draft_id, actor=actor)

    def draft_preview(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.draft_preview(draft_id, actor=actor)

    def configuration_export(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.configuration_export(actor=actor)

    def draft_apply(
        self,
        draft_id: str,
        *,
        actor: ManagementActor,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        return self.core.draft_apply(
            draft_id,
            actor=actor,
            change_plan_id=change_plan_id,
            confirmation=confirmation,
        )

    def draft_cancel(self, draft_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.draft_cancel(draft_id, actor=actor)
    def enrollment_list(self, *, actor: ManagementActor, limit: int = 50) -> dict[str, Any]:
        return self.core.enrollment_list(actor=actor, limit=limit)

    def system_status(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.system_status(actor=actor)

    def certificate_preflight(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.certificate_preflight(actor=actor)

    def certificate_renew(
        self, *, actor: ManagementActor, confirmation: str
    ) -> dict[str, Any]:
        return self.core.certificate_renew(
            actor=actor,
            confirmation=confirmation,
        )

    def backup_validate(self, path: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.backup_validate(path, actor=actor)

    def backup_create(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.backup_create(actor=actor)

    def restore_apply(
        self,
        path: str,
        *,
        confirmation: str,
        actor: ManagementActor,
    ) -> dict[str, Any]:
        return self.core.restore_apply(
            path,
            confirmation=confirmation,
            actor=actor,
        )

    def support_bundle_create(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.support_bundle_create(actor=actor)

    def enrollment_issue_manual(
        self,
        *,
        actor: ManagementActor,
        platform: str,
        ttl_seconds: int | None = None,
        label: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        return self.core.enrollment_issue_manual(
            actor=actor,
            platform=platform,
            ttl_seconds=ttl_seconds,
            label=label,
            note=note,
        )

    def enrollment_issue_zero_touch(
        self,
        *,
        actor: ManagementActor,
        platform: str,
        ttl_seconds: int | None = None,
        label: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        return self.core.enrollment_issue_zero_touch(
            actor=actor,
            platform=platform,
            ttl_seconds=ttl_seconds,
            label=label,
            note=note,
        )
