#!/usr/bin/env python3
"""DRL3-3 Remote Service Web/Core Change Plan over target-bound Agent Jobs."""
from __future__ import annotations

import json
from typing import Any, Optional

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError
from drlink_management_change import CONFIRM_CHANGE, ManagementChangeService
from drlink_v30_jobs import ManagementJobEngine


class ManagementRemoteServiceService(ManagementChangeService):
    """Preview and enqueue Agent-owned Remote Service lifecycle operations."""

    def _owner(self, selector: str):
        token = str(selector or "").strip()
        if not token:
            raise ControlPlaneError("Remote Service owner Managed Host is required.")
        return self.plane.require_client(token)

    def preview(
        self,
        *,
        actor_id: str,
        owner: str,
        name: str,
        operation: str,
        destination: Optional[str] = None,
        service: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> dict[str, Any]:
        import drlink_v24 as v24

        row = self._owner(owner)
        owner_id = str(row["id"])
        op = str(operation or "set").strip().lower()
        if op not in ("set", "delete"):
            raise ControlPlaneError("Remote Service operation must be 'set' or 'delete'.")
        service_name = str(name or "").strip()
        if not service_name:
            raise ControlPlaneError("Remote Service name is required.")
        if len(service_name) > 128:
            raise ControlPlaneError("Remote Service name is too long.")

        payload: dict[str, Any] = {
            "kind": "remote-service",
            "operation": op,
            "owner_id": owner_id,
            "name": service_name,
        }
        if op == "set":
            destination_value = str(destination or "").strip()
            service_value = str(service or "").strip()
            if not destination_value or not service_value or not isinstance(enabled, bool):
                raise ControlPlaneError(
                    "Remote Service set requires destination, service, and enabled."
                )
            if len(destination_value) > 256 or len(service_value) > 128:
                raise ControlPlaneError("Remote Service input is too long.")
            if v24.get_service_object(self.plane, service_value) is None:
                raise ControlPlaneError(
                    "Service Object '%s' was not found." % service_value
                )
            if v24.get_service_group(self.plane, service_value) is not None:
                raise ControlPlaneError(
                    "Remote Service uses one Service Object, not a Service Group."
                )
            payload.update(
                {
                    "destination": destination_value,
                    "service": service_value,
                    "enabled": enabled,
                }
            )
            impact = {
                "requires_confirmation": True,
                "destructive": False,
                "owner_managed_host_id": owner_id,
                "owner_connectivity": self.plane.managed_host_connectivity(row),
                "runtime_authority": "agent-rpc",
            }
        else:
            existing = self.plane.conn.execute(
                "SELECT id FROM published_services "
                "WHERE client_id=? AND name=? COLLATE NOCASE AND released=0",
                (owner_id, service_name),
            ).fetchone()
            impact = {
                "requires_confirmation": True,
                "destructive": True,
                "owner_managed_host_id": owner_id,
                "owner_connectivity": self.plane.managed_host_connectivity(row),
                "existing_server_projection": bool(existing),
                "runtime_authority": "agent-rpc",
            }

        expected_revision = int(self.plane.current_revision())
        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="CHANGE",
            operation="remote-service.%s" % op,
            resource_type="remote-service",
            resource_ref="%s:%s" % (owner_id, service_name),
            expected_revision=expected_revision,
            payload=payload,
            impact=impact,
            confirmation_class=CONFIRM_CHANGE,
        )
        issued.update(
            {
                "owner": {
                    "id": owner_id,
                    "name": str(row["label"] or row["hostname"] or owner_id),
                    "connectivity": self.plane.managed_host_connectivity(row),
                },
                "remote_service": service_name,
            }
        )
        return issued

    def apply(
        self,
        *,
        actor_id: str,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != CONFIRM_CHANGE:
            raise ControlPlaneError(
                "Remote Service apply requires explicit confirmation 'APPLY'."
            )
        row = self._load_plan(actor_id, change_plan_id)
        operation = str(row["operation"] or "")
        if str(row["operation_class"]) != "CHANGE" or operation not in (
            "remote-service.set",
            "remote-service.delete",
        ):
            raise ControlPlaneError("Change Plan is not a Remote Service change.")
        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception as exc:
            self._mark_plan(change_plan_id, "invalid")
            raise ControlPlaneError("Remote Service Change Plan payload is invalid.") from exc
        # A persisted plan must remain bound to the previewed operation and
        # target. Never infer a destructive delete from an unknown payload op.
        if (
            not isinstance(payload, dict)
            or payload.get("kind") != "remote-service"
            or payload.get("operation") != operation.split(".", 1)[1]
            or not isinstance(payload.get("owner_id"), str)
            or not isinstance(payload.get("name"), str)
            or not payload["owner_id"]
            or not payload["name"]
            or str(row["resource_ref"])
            != "%s:%s" % (payload["owner_id"], payload["name"])
        ):
            self._mark_plan(change_plan_id, "invalid")
            raise ControlPlaneError("Remote Service Change Plan binding is invalid.")

        expected_revision = int(row["expected_revision"])
        current_revision = int(self.plane.current_revision())
        if current_revision != expected_revision:
            self._mark_plan(change_plan_id, "stale")
            raise ConcurrencyError(
                "REVISION_CONFLICT\n"
                "Expected revision %s but current revision is %s.\n"
                "No Agent Job was queued. Preview the Remote Service change again."
                % (expected_revision, current_revision)
            )

        owner_id = str(payload.get("owner_id") or "")
        owner = self.plane.require_client(owner_id)
        connectivity = self.plane.managed_host_connectivity(owner)
        if connectivity != "connected":
            raise ControlPlaneError(
                "Managed Host '%s' is %s. No Agent Job was queued."
                % (str(owner["label"] or owner["hostname"] or owner_id), connectivity)
            )

        op = str(payload.get("operation") or "")
        job_type = "remote-service-set" if op == "set" else "remote-service-delete"
        job_payload = {
            key: payload[key]
            for key in ("name", "destination", "service", "enabled")
            if key in payload
        }
        engine = ManagementJobEngine(self.root)
        try:
            job = engine.enqueue(
                job_type=job_type,
                targets=[owner_id],
                requested_by=actor_id,
                resource_type="remote-service",
                resource_ref=str(payload.get("name") or ""),
                payload=job_payload,
                timeout_seconds=120,
            )
        finally:
            engine.close()
        self._mark_plan(change_plan_id, "applied")
        return {
            "status": "QUEUED",
            "job_id": str(job["id"]),
            "job_status": str(job["status"]),
            "target_managed_host_id": owner_id,
            "remote_service": str(payload.get("name") or ""),
            "operation": op,
            "authoritative_revision_at_enqueue": current_revision,
        }
