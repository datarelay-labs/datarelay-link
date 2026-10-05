"""Managed Host lifecycle Change Plans for DRLink 3.0 Web Management."""
from __future__ import annotations

import json
from typing import Any, Optional

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConfirmationRequired, ConcurrencyError
from drlink_management_change import ManagementChangeService

CONFIRM_REVOKE = "REVOKE"
CONFIRM_RETIRE = "RETIRE"
SUPPORTED_OPERATIONS = frozenset({"revoke-trust", "retire"})


class ManagedHostLifecycleService(ManagementChangeService):
    """Preview/apply canonical Managed Host trust revoke and retirement."""

    @staticmethod
    def _host(value: Any) -> str:
        host = str(value or "").strip()
        if not host:
            raise ControlPlaneError("Managed Host is required.")
        if len(host) > 256:
            raise ControlPlaneError("Managed Host selector is too long.")
        return host

    @staticmethod
    def _operation(value: Any) -> str:
        operation = str(value or "").strip().lower()
        if operation not in SUPPORTED_OPERATIONS:
            raise ControlPlaneError(
                "Managed Host lifecycle operation must be revoke-trust or retire."
            )
        return operation

    def _revoke_impact(self, host: str) -> tuple[dict[str, Any], bool, dict[str, Any]]:
        row = self.plane.require_client(host)
        trust = str(row["trust_status"] or "")
        services = int(
            self.plane.conn.execute(
                "SELECT COUNT(*) FROM published_services "
                "WHERE client_id=? AND released=0",
                (row["id"],),
            ).fetchone()[0]
            or 0
        )
        ports = int(
            self.plane.conn.execute(
                "SELECT COUNT(*) FROM port_reservations "
                "WHERE client_id=? AND released=0",
                (row["id"],),
            ).fetchone()[0]
            or 0
        )
        no_change = trust.lower() == "revoked"
        impact = {
            "kind": "managed-host-trust-revoke",
            "requires_confirmation": True,
            "destructive": False,
            "access_broadened": False,
            "access_narrowed": not no_change,
            "warning": (
                "This revokes the Managed Host management identity. "
                "The Agent must enroll again before it can authenticate."
            ),
            "before": "trust=%s connected=%s services=%s active_reservations=%s"
            % (
                trust or "unknown",
                "yes" if row["connected"] else "no",
                services,
                ports,
            ),
            "after": (
                "trust=revoked connected=no; published services and port "
                "reservations are retained"
            ),
            "kept": [
                "published services",
                "public port reservations",
                "Managed Host inventory record",
            ],
        }
        preview = {
            "entity": {
                "type": "managed-host",
                "id": str(row["id"]),
                "name": str(row["label"] or row["hostname"] or row["id"]),
            },
            "operation": "revoke-trust",
            "trust_status": trust,
            "services_retained": services,
            "port_reservations_retained": ports,
        }
        return impact, no_change, preview

    def _retire_impact(self, host: str) -> tuple[dict[str, Any], dict[str, Any]]:
        row = self.plane.require_client(host)
        try:
            self.plane.unset_managed_host(host)
        except ConfirmationRequired as exc:
            impact = dict(exc.impact or {})
        else:
            raise ControlPlaneError(
                "Managed Host retirement preview did not require confirmation."
            )
        preview = {
            "entity": {
                "type": "managed-host",
                "id": str(row["id"]),
                "name": str(
                    impact.get("host")
                    or row["label"]
                    or row["hostname"]
                    or row["id"]
                ),
            },
            "operation": "retire",
            "cleanup": list(impact.get("cleanup") or []),
            "before": str(impact.get("before") or ""),
            "after": str(impact.get("after") or ""),
        }
        return impact, preview

    def preview(
        self,
        *,
        actor_id: str,
        host: str,
        operation: str,
    ) -> dict[str, Any]:
        selector = self._host(host)
        action = self._operation(operation)
        expected_revision = int(self.plane.current_revision())
        if action == "revoke-trust":
            impact, no_change, preview = self._revoke_impact(selector)
            confirmation = CONFIRM_REVOKE
        else:
            impact, preview = self._retire_impact(selector)
            no_change = False
            confirmation = CONFIRM_RETIRE

        entity = dict(preview.get("entity") or {})
        resource_ref = str(entity.get("id") or selector)
        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="CHANGE",
            operation="managed-host-lifecycle.%s" % action,
            resource_type="managed-host",
            resource_ref=resource_ref,
            expected_revision=expected_revision,
            payload={
                "kind": "managed-host-lifecycle",
                "host": selector,
                "operation": action,
                "no_change": no_change,
            },
            impact=impact,
            confirmation_class=confirmation,
        )
        issued.update(
            {
                "preview": preview,
                "no_change": no_change,
                "lifecycle_operation": action,
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
        row = self._load_plan(actor_id, change_plan_id)
        if (
            str(row["operation_class"]) != "CHANGE"
            or not str(row["operation"]).startswith("managed-host-lifecycle.")
        ):
            raise ControlPlaneError(
                "Change Plan is not a Managed Host lifecycle change."
            )
        expected_confirmation = str(row["confirmation_class"] or "").strip()
        if str(confirmation or "").strip().upper() != expected_confirmation:
            raise ControlPlaneError(
                "Managed Host lifecycle apply requires explicit confirmation '%s'."
                % expected_confirmation
            )
        try:
            document = json.loads(str(row["payload_json"]))
            if str(document.get("kind") or "") != "managed-host-lifecycle":
                raise ControlPlaneError("Change Plan payload is invalid.")
            host = self._host(document.get("host"))
            operation = self._operation(document.get("operation"))
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
                "lifecycle_operation": operation,
            }

        try:
            if operation == "revoke-trust":
                result = self.plane.remove_client(
                    host,
                    revoke_only=True,
                    expected_revision=expected_revision,
                    actor=actor_id,
                    interface="WEB",
                )
            else:
                result = self.plane.unset_managed_host(
                    host,
                    confirm=True,
                    expected_revision=expected_revision,
                    actor=actor_id,
                    interface="WEB",
                )
        except ConcurrencyError:
            self._mark_plan(change_plan_id, "stale")
            raise
        except Exception:
            self._mark_plan(change_plan_id, "failed")
            raise

        self._mark_plan(change_plan_id, "applied")
        return {
            "status": "APPLIED",
            "revision": int(result.get("revision") or self.plane.current_revision()),
            "lifecycle_operation": operation,
            "result": result,
        }
