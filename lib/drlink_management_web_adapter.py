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

    def policy_decision_trace(
        self,
        *,
        actor: ManagementActor,
        plane: str,
        source: str,
        destination: str,
        service: str = "",
        permission: str = "",
        path: str = "",
    ) -> dict[str, Any]:
        return self.core.policy_decision_trace(
            actor=actor,
            plane=plane,
            source=source,
            destination=destination,
            service=service,
            permission=permission,
            path=path,
        )

    def policy_effective_access_graph(
        self,
        *,
        actor: ManagementActor,
        plane: str = "",
    ) -> dict[str, Any]:
        return self.core.policy_effective_access_graph(
            actor=actor,
            plane=plane,
        )

    def policy_regression_list(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.policy_regression_list(actor=actor)

    def policy_regression_run(
        self, *, actor: ManagementActor, required_only: bool = False
    ) -> dict[str, Any]:
        return self.core.policy_regression_run(
            actor=actor,
            required_only=required_only,
        )

    def policy_regression_preview(
        self,
        *,
        actor: ManagementActor,
        operation: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        return self.core.policy_regression_preview(
            actor=actor,
            operation=operation,
            definition=definition,
        )

    def policy_regression_apply(
        self,
        *,
        actor: ManagementActor,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        return self.core.policy_regression_apply(
            actor=actor,
            change_plan_id=change_plan_id,
            confirmation=confirmation,
        )

    def fleet_metadata_preview(
        self,
        *,
        actor: ManagementActor,
        resource_type: str,
        resource: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        return self.core.fleet_metadata_preview(
            actor=actor,
            resource_type=resource_type,
            resource=resource,
            changes=changes,
        )

    def fleet_metadata_apply(
        self,
        *,
        actor: ManagementActor,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        return self.core.fleet_metadata_apply(
            actor=actor,
            change_plan_id=change_plan_id,
            confirmation=confirmation,
        )

    def managed_host_admission_preview(
        self, *, host: str, operation: str, actor: ManagementActor,
    ) -> dict[str, Any]:
        return self.core.managed_host_admission_preview(
            host=host, operation=operation, actor=actor,
        )

    def managed_host_admission_apply(
        self, *, change_plan_id: str, confirmation: str, actor: ManagementActor,
    ) -> dict[str, Any]:
        return self.core.managed_host_admission_apply(
            change_plan_id=change_plan_id,
            confirmation=confirmation,
            actor=actor,
        )

    def managed_host_lifecycle_preview(
        self,
        *,
        host: str,
        operation: str,
        actor: ManagementActor,
    ) -> dict[str, Any]:
        return self.core.managed_host_lifecycle_preview(
            host=host,
            operation=operation,
            actor=actor,
        )

    def managed_host_lifecycle_apply(
        self,
        *,
        change_plan_id: str,
        confirmation: str,
        actor: ManagementActor,
    ) -> dict[str, Any]:
        return self.core.managed_host_lifecycle_apply(
            change_plan_id=change_plan_id,
            confirmation=confirmation,
            actor=actor,
        )

    def system_status(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.system_status(actor=actor)

    def certificate_preflight(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.certificate_preflight(actor=actor)

    def certificate_configure(
        self,
        settings: dict[str, Any],
        *,
        actor: ManagementActor,
        confirmation: str,
    ) -> dict[str, Any]:
        return self.core.certificate_configure(
            settings,
            actor=actor,
            confirmation=confirmation,
        )

    def certificate_issue(
        self, *, actor: ManagementActor, confirmation: str
    ) -> dict[str, Any]:
        return self.core.certificate_issue(
            actor=actor,
            confirmation=confirmation,
        )

    def certificate_import(
        self,
        *,
        actor: ManagementActor,
        cert_pem: str,
        key_pem: str,
        chain_pem: str,
        confirmation: str,
    ) -> dict[str, Any]:
        return self.core.certificate_import(
            actor=actor,
            cert_pem=cert_pem,
            key_pem=key_pem,
            chain_pem=chain_pem,
            confirmation=confirmation,
        )

    def certificate_renew(
        self, *, actor: ManagementActor, confirmation: str
    ) -> dict[str, Any]:
        return self.core.certificate_renew(
            actor=actor,
            confirmation=confirmation,
        )

    def update_check(self, target: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.update_check(target, actor=actor)

    def update_product_apply(
        self, *, actor: ManagementActor, confirmation: str
    ) -> dict[str, Any]:
        return self.core.update_product_apply(
            actor=actor,
            confirmation=confirmation,
        )

    def update_product_status(
        self, job_id: str, *, actor: ManagementActor
    ) -> dict[str, Any]:
        return self.core.update_product_status(job_id, actor=actor)

    def update_engine_apply(
        self, *, actor: ManagementActor, confirmation: str
    ) -> dict[str, Any]:
        return self.core.update_engine_apply(
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

    def audit_retention_status(
        self, *, actor: ManagementActor
    ) -> dict[str, Any]:
        return self.core.audit_retention_status(actor=actor)

    def audit_retention_configure(
        self,
        *,
        actor: ManagementActor,
        control_days: int,
        access_days: int,
        max_events: int,
    ) -> dict[str, Any]:
        return self.core.audit_retention_configure(
            actor=actor,
            control_days=control_days,
            access_days=access_days,
            max_events=max_events,
        )

    def audit_retention_run(
        self, *, actor: ManagementActor
    ) -> dict[str, Any]:
        return self.core.audit_retention_run(actor=actor)

    def audit_export_create(
        self,
        *,
        actor: ManagementActor,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        return self.core.audit_export_create(actor=actor, filters=filters)

    def inventory_export_create(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.inventory_export_create(actor=actor)

    def support_bundle_create(self, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.support_bundle_create(actor=actor)

    def job_cancel(self, job_id: str, *, actor: ManagementActor) -> dict[str, Any]:
        return self.core.job_cancel(job_id, actor=actor)

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
