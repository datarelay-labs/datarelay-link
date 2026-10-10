#!/usr/bin/env python3
"""Optional Data Relay Link 3.0 read-only Web Management service."""
from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import os
import ssl
import threading
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

from drlink_control_db import ControlPlaneError
from drlink_management_core import ManagementActor
from drlink_management_service import ManagementQueryService
from drlink_management_web_adapter import ManagementWebApiAdapter
from drlink_web_auth import ROLE_ADMIN, WebAuthService, WebMfaEnrollmentChallenge, WebPrincipal

DEFAULT_WEB_LISTEN = "127.0.0.1"
DEFAULT_WEB_PORT = 8741
SESSION_COOKIE = "drlink_session"
MAX_REQUEST_BYTES = 64 * 1024
WEB_API_PREFIX = "/api/v1"

CSP = (
    "default-src 'self'; "
    "script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


def _is_loopback(host: str) -> bool:
    value = str(host or "").strip().lower()
    if value in ("localhost", "ip6-localhost"):
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def validate_web_bind(
    listen: str,
    *,
    tls_cert: Optional[str] = None,
    tls_key: Optional[str] = None,
) -> None:
    if _is_loopback(listen):
        return
    if not str(tls_cert or "").strip() or not str(tls_key or "").strip():
        raise ControlPlaneError(
            "Remote drlink-web bind requires an explicit TLS certificate and key."
        )
    if not Path(str(tls_cert)).is_file() or not Path(str(tls_key)).is_file():
        raise ControlPlaneError("Remote drlink-web TLS certificate/key is unavailable.")


def _int_arg(value: Optional[str], default: int, *, low: int = 1, high: int = 200) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ControlPlaneError("Invalid integer request parameter.") from exc
    if parsed < low or parsed > high:
        raise ControlPlaneError(
            "Request parameter must be between %d and %d." % (low, high)
        )
    return parsed


class WebApplication:
    """HTTP-independent routing target used by the server and tests."""

    def __init__(
        self,
        root: Optional[str] = None,
        *,
        static_root: Optional[str] = None,
        secure_cookie: bool = False,
    ):
        self.root = root
        self.static_root = Path(
            static_root
            or (
                Path(root) / "usr/local/share/drlink-web"
                if root and str(root) not in ("", "/")
                else Path("/usr/local/share/drlink-web")
            )
        )
        self.secure_cookie = bool(secure_cookie)
        self.auth = WebAuthService(root)
        self.adapter = ManagementWebApiAdapter(root)
        self._restore_lock = threading.RLock()
        self._restore_in_progress = False

    def close(self) -> None:
        self.auth.close()

    @staticmethod
    def _actor(principal: WebPrincipal) -> ManagementActor:
        return ManagementActor.authenticated(
            "web:%s" % principal.operator_id,
            principal.permissions,
            role=principal.role,
        )

    def authenticate(
        self,
        body: dict[str, Any],
        *,
        source_addr: str,
        user_agent: str,
    ) -> dict[str, Any]:
        issued = self.auth.authenticate(
            username=str(body.get("username") or ""),
            password=str(body.get("password") or ""),
            totp_value=str(body.get("totp") or ""),
            recovery_code=str(body.get("recovery_code") or ""),
            source_addr=source_addr,
            user_agent=user_agent,
        )
        if isinstance(issued, WebMfaEnrollmentChallenge):
            return {
                "mfa_setup_required": True,
                "enrollment_token": issued.enrollment_token,
                "totp_secret": issued.totp_secret,
                "otpauth_uri": issued.otpauth_uri,
                "expires_at": issued.expires_at,
                "operator": {
                    "id": issued.operator_id,
                    "username": issued.username,
                    "role": issued.role,
                },
            }
        return self._session_payload(issued)

    @staticmethod
    def _session_payload(issued, *, recovery_codes: Optional[list[str]] = None) -> dict[str, Any]:
        payload = {
            "session_id": issued.session_id,
            "csrf_token": issued.csrf_token,
            "expires_at": issued.expires_at,
            "idle_expires_at": issued.idle_expires_at,
            "operator": {
                "id": issued.principal.operator_id,
                "username": issued.principal.username,
                "role": issued.principal.role,
            },
            "_session_token": issued.session_token,
        }
        if recovery_codes is not None:
            payload["recovery_codes"] = list(recovery_codes)
        return payload

    def cancel_mfa_enrollment(self, body: dict[str, Any]) -> dict[str, Any]:
        cancelled = self.auth.cancel_mfa_enrollment(
            str(body.get("enrollment_token") or "")
        )
        return {"cancelled": bool(cancelled)}

    def confirm_mfa_enrollment(
        self, body: dict[str, Any], *, source_addr: str, user_agent: str
    ) -> dict[str, Any]:
        issued, recovery_codes = self.auth.confirm_mfa_enrollment(
            enrollment_token=str(body.get("enrollment_token") or ""),
            totp_value=str(body.get("totp") or ""),
            source_addr=source_addr,
            user_agent=user_agent,
        )
        return self._session_payload(issued, recovery_codes=recovery_codes)

    def session_principal(
        self,
        token: str,
        *,
        csrf_token: Optional[str] = None,
        require_csrf: bool = False,
    ) -> Optional[WebPrincipal]:
        if self._restore_in_progress:
            return None
        return self.auth.validate_session(
            token,
            csrf_token=csrf_token,
            require_csrf=require_csrf,
        )

    def _restore_apply(
        self,
        *,
        actor: ManagementActor,
        path: str,
        confirmation: str,
    ) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != "RESTORE":
            raise ControlPlaneError(
                "Restore requires explicit confirmation 'RESTORE'."
            )
        with self._restore_lock:
            if self._restore_in_progress:
                raise ControlPlaneError("Restore is already in progress.")
            self._restore_in_progress = True
            auth_ready = False
            try:
                self.auth.close()
                result = self.adapter.restore_apply(
                    path,
                    confirmation=confirmation,
                    actor=actor,
                )
                self.auth = WebAuthService(self.root)
                auth_ready = True
                revoked = self.auth.revoke_all_sessions(
                    actor_id=actor.actor_id,
                    reason="restore",
                )
                return {
                    **result,
                    "web_sessions_revoked": revoked,
                    "web_reauth_required": True,
                }
            except Exception as restore_exc:
                if not auth_ready:
                    try:
                        self.auth = WebAuthService(self.root)
                        auth_ready = True
                    except Exception as auth_exc:
                        self._restore_in_progress = True
                        raise ControlPlaneError(
                            "Web authentication is unavailable after the recovery attempt. "
                            "Use local CLI recovery before retrying Web management."
                        ) from auth_exc
                raise restore_exc
            finally:
                self._restore_in_progress = not auth_ready

    def read_api(
        self,
        path: str,
        query: dict[str, list[str]],
        principal: WebPrincipal,
    ) -> dict[str, Any]:
        actor = self._actor(principal)
        if path == "/api/v1/session":
            return {
                "operator": {
                    "id": principal.operator_id,
                    "username": principal.username,
                    "role": principal.role,
                },
                "session_id": principal.session_id,
            }
        if path == "/api/v1/overview":
            with ManagementQueryService(self.root) as service:
                return {
                    "overview": service.overview_summary(),
                    "attention": service.attention_summary(),
                }
        if path == "/api/v1/inventory":
            resource_type = _first(query, "resource_type")
            payload: dict[str, Any] = {"resource_type": resource_type}
            for key in ("cursor", "q"):
                value = _first(query, key)
                if value:
                    payload["query" if key == "q" else key] = value
            payload["limit"] = _int_arg(_first(query, "limit"), 50)
            return self.adapter.invoke(
                operation="drlink_inventory_list",
                payload=payload,
                actor=actor,
            )
        if path == "/api/v1/access-hygiene":
            with ManagementQueryService(self.root) as service:
                return service.access_hygiene()
        if path == "/api/v1/policies":
            with ManagementQueryService(self.root) as service:
                return service.policy_list(
                    plane=_first(query, "plane") or None,
                    limit=_int_arg(_first(query, "limit"), 50),
                )
        if path == "/api/v1/policy/graph":
            return self.adapter.policy_effective_access_graph(
                actor=actor,
                plane=_first(query, "plane"),
            )
        if path == "/api/v1/policy-tests":
            return self.adapter.policy_regression_list(actor=actor)
        if path == "/api/v1/objects-groups":
            with ManagementQueryService(self.root) as service:
                return service.inventory_snapshot(
                    (
                        "network-object",
                        "network-group",
                        "service-object",
                        "service-group",
                        "permission-object",
                        "permission-group",
                        "ai-identity",
                    ),
                    per_type_limit=_int_arg(_first(query, "limit"), 50, high=100),
                )
        if path == "/api/v1/search":
            with ManagementQueryService(self.root) as service:
                return service.global_search(
                    _first(query, "q"),
                    limit=_int_arg(_first(query, "limit"), 40, high=100),
                )
        if path == "/api/v1/versions":
            with ManagementQueryService(self.root) as service:
                return service.version_drift()
        if path == "/api/v1/audit/retention":
            return self.adapter.audit_retention_status(actor=actor)
        if path == "/api/v1/audit":
            payload = {}
            for key in (
                "start",
                "end",
                "category",
                "event_type",
                "actor",
                "resource",
                "result",
                "correlation_id",
                "cursor",
            ):
                value = _first(query, key)
                if value:
                    payload[key] = value
            payload["limit"] = _int_arg(_first(query, "limit"), 50)
            return self.adapter.invoke(
                operation="drlink_audit_query", payload=payload, actor=actor
            )
        if path == "/api/v1/revisions":
            with ManagementQueryService(self.root) as service:
                return service.revision_list(
                    cursor=_first(query, "cursor") or None,
                    limit=_int_arg(_first(query, "limit"), 50),
                ).as_dict()
        if path == "/api/v1/health":
            return self.adapter.invoke(
                operation="drlink_health", payload={}, actor=actor
            )
        if path == "/api/v1/live-access":
            payload: dict[str, Any] = {"plane": _first(query, "plane")}
            for key in ("resource_type", "resource", "cursor"):
                value = _first(query, key)
                if value:
                    payload[key] = value
            payload["limit"] = _int_arg(_first(query, "limit"), 50)
            return self.adapter.invoke(
                operation="drlink_live_access", payload=payload, actor=actor
            )
        if path == "/api/v1/emergency-cutoffs":
            with ManagementQueryService(self.root) as service:
                return service.active_cutoff_summary(
                    plane=_first(query, "plane") or None
                )
        if path == "/api/v1/doctor":
            with ManagementQueryService(self.root) as service:
                return service.doctor_summary()
        if path == "/api/v1/enrollments":
            return self.adapter.enrollment_list(
                actor=actor,
                limit=_int_arg(_first(query, "limit"), 50, high=100),
            )
        if path == "/api/v1/system/update/product/status":
            return self.adapter.update_product_status(
                _first(query, "job_id"),
                actor=actor,
            )
        if path == "/api/v1/system":
            return self.adapter.system_status(actor=actor)
        if path == "/api/v1/configuration/export":
            return self.adapter.configuration_export(actor=actor)
        if path == "/api/v1/drafts":
            return self.adapter.draft_list(
                actor=actor,
                limit=_int_arg(_first(query, "limit"), 50, high=50),
            )
        if path.startswith("/api/v1/drafts/"):
            suffix = path[len("/api/v1/drafts/") :]
            parts = [item for item in suffix.split("/") if item]
            if not parts:
                raise ControlPlaneError("Draft was not found.")
            draft_id = parts[0]
            if len(parts) == 1:
                return self.adapter.draft_get(draft_id, actor=actor)
            if len(parts) == 2 and parts[1] == "export":
                return self.adapter.draft_export(draft_id, actor=actor)
            raise ControlPlaneError("Web API route was not found.")
        if path == "/api/v1/jobs":
            payload: dict[str, Any] = {
                "limit": _int_arg(_first(query, "limit"), 50)
            }
            for key in ("cursor", "status", "job_type"):
                value = _first(query, key)
                if value:
                    payload[key] = value
            return self.adapter.invoke(
                operation="drlink_job_list",
                payload=payload,
                actor=actor,
            )
        if path.startswith("/api/v1/jobs/"):
            job_id = path[len("/api/v1/jobs/") :].strip()
            if not job_id or "/" in job_id:
                raise ControlPlaneError("Management Job was not found.")
            return self.adapter.invoke(
                operation="drlink_job_get",
                payload={"job_id": job_id},
                actor=actor,
            )
        if path == "/api/v1/service-accounts":
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Service Account inventory.")
            from drlink_service_accounts import ServiceAccountStore
            with ServiceAccountStore(self.root) as store:
                return store.list_accounts()
        if path == "/api/v1/webhooks":
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Webhook inventory.")
            from drlink_webhooks import WebhookStore
            with WebhookStore(self.root) as store:
                return store.list_webhooks()
        if path == "/api/v1/operators":
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Web operator management.")
            return {"items": self.auth.list_operators()}
        if path == "/api/v1/saved-views":
            return {"items": self.auth.list_saved_views(principal.operator_id)}
        if path == "/api/v1/sessions":
            return {"items": self.auth.list_sessions(principal.operator_id)}
        raise ControlPlaneError("Web API route was not found.")

    def write_api(
        self,
        path: str,
        body: dict[str, Any],
        principal: WebPrincipal,
    ) -> dict[str, Any]:
        if path.startswith("/api/v1/webhooks"):
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Webhook management.")
            from drlink_webhooks import WebhookStore
            with WebhookStore(self.root) as store:
                if path == "/api/v1/webhooks":
                    if not isinstance(body.get("event_classes"), list):
                        raise ControlPlaneError("Webhook event classes must be a list.")
                    return store.create(
                        name=body.get("name"), url=body.get("url"),
                        event_classes=body["event_classes"], actor_id="web:" + principal.operator_id,
                    )
                webhook_id = body.get("webhook_id")
                if not isinstance(webhook_id, str) or not webhook_id.startswith("wh_"):
                    raise ControlPlaneError("Webhook ID is required.")
                if path == "/api/v1/webhooks/rotate":
                    return store.rotate_secret(webhook_id, actor_id="web:" + principal.operator_id)
                if path == "/api/v1/webhooks/test":
                    return store.test_delivery(webhook_id, actor_id="web:" + principal.operator_id)
                if path == "/api/v1/webhooks/disable":
                    store.disable(webhook_id, actor_id="web:" + principal.operator_id)
                    return {"id": webhook_id, "enabled": False}
                if path == "/api/v1/webhooks/enable":
                    store.enable(webhook_id, actor_id="web:" + principal.operator_id)
                    return {"id": webhook_id, "enabled": True}
            raise ControlPlaneError("Webhook operation was not found.")
        if path.startswith("/api/v1/service-accounts"):
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Service Account management.")
            from drlink_service_accounts import ServiceAccountStore
            with ServiceAccountStore(self.root) as store:
                if path == "/api/v1/service-accounts":
                    return store.create(
                        name=body.get("name"), permissions=body.get("permissions"),
                        expires_at=body.get("expires_at") or "",
                        actor_id="web:" + principal.operator_id,
                    )
                account_id = body.get("account_id")
                if not isinstance(account_id, str) or not account_id.startswith("msa_"):
                    raise ControlPlaneError("Service Account ID is required.")
                if path == "/api/v1/service-accounts/rotate":
                    return store.rotate(account_id, actor_id="web:" + principal.operator_id)
                if path == "/api/v1/service-accounts/revoke":
                    store.revoke(account_id, actor_id="web:" + principal.operator_id)
                    return {"id": account_id, "enabled": False}
            raise ControlPlaneError("Service Account operation was not found.")
        if path == "/api/v1/operators":
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Web operator management.")
            return self.auth.create_operator_local(
                username=str(body.get("username") or ""),
                role=str(body.get("role") or ""),
                password=str(body.get("password") or ""),
            )
        if path.startswith("/api/v1/operators/") and path.endswith("/mfa"):
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Web operator management.")
            operator_id = path[len("/api/v1/operators/") : -len("/mfa")].strip("/")
            if not operator_id or "/" in operator_id:
                raise ControlPlaneError("Web operator was not found.")
            if not isinstance(body.get("required"), bool):
                raise ControlPlaneError("required must be a boolean.")
            return self.auth.set_operator_mfa_required(
                operator_id,
                required=bool(body["required"]),
                actor_id=principal.operator_id,
            )
        if path == "/api/v1/auth/logout":
            self.auth.revoke_session(
                principal.session_id, actor_id=principal.operator_id
            )
            return {"status": "logged_out"}
        if path == "/api/v1/jobs/diagnostic":
            payload = {"job_type": str(body.get("job_type") or "")}
            for key in ("resource_type", "resource"):
                if body.get(key) is not None:
                    payload[key] = str(body.get(key) or "")
            return self.adapter.invoke(
                operation="drlink_diagnostic_job_start",
                payload=payload,
                actor=self._actor(principal),
            )
        if path == "/api/v1/jobs/agent-update-rollout/preview":
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Managed Update rollout.")
            targets = body.get("targets")
            canaries = body.get("canary_targets") or []
            artifact = body.get("artifact")
            if not isinstance(targets, list) or not isinstance(canaries, list):
                raise ControlPlaneError("Rollout target and canary lists are required.")
            if not isinstance(artifact, dict):
                raise ControlPlaneError("Rollout artifact identity must be an object.")
            return self.adapter.rollout_preview(
                actor=self._actor(principal),
                targets=targets, canary_targets=canaries, artifact=artifact,
                wave_size=body.get("wave_size", 10),
                failure_threshold_percent=body.get("failure_threshold_percent", 0),
            )
        if path == "/api/v1/jobs/agent-update-rollout":
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Managed Update rollout.")
            payload = {
                "targets": body.get("targets") or [],
                "canary_targets": body.get("canary_targets") or [],
                "artifact": body.get("artifact") or {},
            }
            for key in ("wave_size", "failure_threshold_percent"):
                if body.get(key) is not None:
                    payload[key] = body[key]
            return self.adapter.invoke(
                operation="drlink_agent_update_rollout_start",
                payload=payload,
                actor=self._actor(principal),
            )
        if path == "/api/v1/jobs/agent-update-rollout/control":
            if principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Admin role is required for Managed Update rollout.")
            job_id = str(body.get("job_id") or "").strip()
            action = str(body.get("action") or "").strip().lower()
            if not job_id or action not in ("pause", "resume"):
                raise ControlPlaneError("job_id and pause/resume action are required.")
            return self.adapter.rollout_control(
                job_id, actor=self._actor(principal), action=action,
            )
        if path == "/api/v1/jobs/cancel":
            job_id = str(body.get("job_id") or "").strip()
            if not job_id:
                raise ControlPlaneError("job_id is required.")
            return self.adapter.job_cancel(
                job_id,
                actor=self._actor(principal),
            )
        if path == "/api/v1/diagnose":
            payload = {"plane": str(body.get("plane") or "")}
            for key in ("source", "destination", "service", "permission"):
                value = body.get(key)
                if value is not None:
                    payload[key] = str(value)
            return self.adapter.invoke(
                operation="drlink_diagnose_connection",
                payload=payload,
                actor=self._actor(principal),
            )
        if path == "/api/v1/audit/export":
            filters = body.get("filters") or {}
            if not isinstance(filters, dict):
                raise ControlPlaneError("Audit export filters must be an object.")
            return self.adapter.audit_export_create(
                actor=self._actor(principal),
                filters=dict(filters),
            )
        if path == "/api/v1/audit/retention/configure":
            return self.adapter.audit_retention_configure(
                actor=self._actor(principal),
                control_days=body.get("control_days"),
                access_days=body.get("access_days"),
                max_events=body.get("max_events"),
            )
        if path == "/api/v1/audit/retention/run":
            return self.adapter.audit_retention_run(
                actor=self._actor(principal)
            )
        if path == "/api/v1/inventory/export":
            return self.adapter.inventory_export_create(
                actor=self._actor(principal)
            )
        if path == "/api/v1/fleet/metadata/preview":
            changes = body.get("changes")
            if not isinstance(changes, dict):
                raise ControlPlaneError("Fleet metadata changes must be an object.")
            return self.adapter.fleet_metadata_preview(
                actor=self._actor(principal),
                resource_type=str(body.get("resource_type") or "managed-host"),
                resource=str(body.get("resource") or ""),
                changes=dict(changes),
            )
        if path == "/api/v1/fleet/metadata/apply":
            return self.adapter.fleet_metadata_apply(
                actor=self._actor(principal),
                change_plan_id=str(body.get("change_plan_id") or ""),
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/guided/preview":
            change_type = str(body.get("change_type") or "").strip()
            payload = body.get("payload")
            if not isinstance(payload, dict):
                raise ControlPlaneError("Guided change payload must be an object.")
            return self.adapter.invoke(
                operation="drlink_guided_change_preview",
                payload={"change_type": change_type, "payload": payload},
                actor=self._actor(principal),
            )
        if path == "/api/v1/guided/apply":
            return self.adapter.invoke(
                operation="drlink_guided_change_apply",
                payload={
                    "change_plan_id": str(body.get("change_plan_id") or ""),
                    "confirmation": str(body.get("confirmation") or ""),
                },
                actor=self._actor(principal),
            )
        if path == "/api/v1/remote-services/preview":
            payload = {
                "owner": str(body.get("owner") or ""),
                "name": str(body.get("name") or ""),
                "operation": str(body.get("operation") or ""),
            }
            if body.get("destination") is not None:
                payload["destination"] = str(body.get("destination") or "")
            if body.get("service") is not None:
                payload["service"] = str(body.get("service") or "")
            if body.get("enabled") is not None:
                payload["enabled"] = body.get("enabled")
            return self.adapter.invoke(
                operation="drlink_remote_service_preview",
                payload=payload,
                actor=self._actor(principal),
            )
        if path == "/api/v1/remote-services/apply":
            return self.adapter.invoke(
                operation="drlink_remote_service_apply",
                payload={
                    "change_plan_id": str(body.get("change_plan_id") or ""),
                    "confirmation": str(body.get("confirmation") or ""),
                },
                actor=self._actor(principal),
            )
        if path == "/api/v1/temporary-access/preview":
            payload = {
                "plane": str(body.get("plane") or ""),
                "rule": str(body.get("rule") or ""),
                "operation": str(body.get("operation") or ""),
            }
            if body.get("expires_at") is not None:
                payload["expires_at"] = str(body.get("expires_at") or "")
            return self.adapter.invoke(
                operation="drlink_temporary_access_preview",
                payload=payload,
                actor=self._actor(principal),
            )
        if path == "/api/v1/temporary-access/apply":
            return self.adapter.invoke(
                operation="drlink_temporary_access_apply",
                payload={
                    "change_plan_id": str(body.get("change_plan_id") or ""),
                    "confirmation": str(body.get("confirmation") or ""),
                },
                actor=self._actor(principal),
            )
        if path == "/api/v1/emergency-cutoff/preview":
            payload = {
                "plane": str(body.get("plane") or ""),
                "scope_kind": str(body.get("scope_kind") or ""),
                "scope_ref": str(body.get("scope_ref") or ""),
                "operation": str(body.get("operation") or "apply"),
            }
            if body.get("reason") is not None:
                payload["reason"] = str(body.get("reason") or "")
            return self.adapter.invoke(
                operation="drlink_emergency_cutoff_preview",
                payload=payload,
                actor=self._actor(principal),
            )
        if path == "/api/v1/emergency-cutoff/apply":
            operation = str(body.get("operation") or "apply").strip().lower()
            tool = (
                "drlink_emergency_cutoff_clear"
                if operation == "clear"
                else "drlink_emergency_cutoff_apply"
            )
            return self.adapter.invoke(
                operation=tool,
                payload={
                    "change_plan_id": str(body.get("change_plan_id") or ""),
                    "confirmation": str(body.get("confirmation") or ""),
                },
                actor=self._actor(principal),
            )
        actor = self._actor(principal)
        if path == "/api/v1/policy/trace":
            return self.adapter.policy_decision_trace(
                actor=actor,
                plane=str(body.get("plane") or ""),
                source=str(body.get("source") or ""),
                destination=str(body.get("destination") or ""),
                service=str(body.get("service") or ""),
                permission=str(body.get("permission") or ""),
                path=str(body.get("path") or ""),
            )
        if path == "/api/v1/policy-tests/run":
            return self.adapter.policy_regression_run(
                actor=actor,
                required_only=bool(body.get("required_only", False)),
            )
        if path == "/api/v1/policy-tests/preview":
            definition = body.get("definition")
            if not isinstance(definition, dict):
                raise ControlPlaneError(
                    "Policy Regression Test definition must be an object."
                )
            return self.adapter.policy_regression_preview(
                actor=actor,
                operation=str(body.get("operation") or "set"),
                definition=dict(definition),
            )
        if path == "/api/v1/policy-tests/apply":
            return self.adapter.policy_regression_apply(
                actor=actor,
                change_plan_id=str(body.get("change_plan_id") or ""),
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/managed-hosts/admission/preview":
            return self.adapter.managed_host_admission_preview(
                host=str(body.get("host") or ""),
                operation=str(body.get("operation") or ""),
                actor=actor,
            )
        if path == "/api/v1/managed-hosts/admission/apply":
            return self.adapter.managed_host_admission_apply(
                change_plan_id=str(body.get("change_plan_id") or ""),
                confirmation=str(body.get("confirmation") or ""),
                actor=actor,
            )
        if path == "/api/v1/managed-hosts/lifecycle/preview":
            return self.adapter.managed_host_lifecycle_preview(
                host=str(body.get("host") or ""),
                operation=str(body.get("operation") or ""),
                actor=actor,
            )
        if path == "/api/v1/managed-hosts/lifecycle/apply":
            return self.adapter.managed_host_lifecycle_apply(
                change_plan_id=str(body.get("change_plan_id") or ""),
                confirmation=str(body.get("confirmation") or ""),
                actor=actor,
            )
        if path == "/api/v1/system/certificate/preflight":
            return self.adapter.certificate_preflight(actor=actor)
        if path == "/api/v1/system/certificate/configure":
            settings = {
                key: body[key]
                for key in (
                    "mode",
                    "hostname",
                    "contact_email",
                    "acme_environment",
                )
                if key in body
            }
            return self.adapter.certificate_configure(
                settings,
                actor=actor,
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/system/certificate/issue":
            return self.adapter.certificate_issue(
                actor=actor,
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/system/certificate/import":
            return self.adapter.certificate_import(
                actor=actor,
                cert_pem=str(body.get("cert_pem") or ""),
                key_pem=str(body.get("key_pem") or ""),
                chain_pem=str(body.get("chain_pem") or ""),
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/system/certificate/renew":
            return self.adapter.certificate_renew(
                actor=actor,
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/system/update/check":
            return self.adapter.update_check(
                str(body.get("target") or ""),
                actor=actor,
            )
        if path == "/api/v1/system/update/product":
            return self.adapter.update_product_apply(
                actor=actor,
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/system/update/engine":
            return self.adapter.update_engine_apply(
                actor=actor,
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/system/backup/validate":
            return self.adapter.backup_validate(
                str(body.get("path") or ""),
                actor=actor,
            )
        if path == "/api/v1/system/backup/create":
            return self.adapter.backup_create(actor=actor)
        if path == "/api/v1/system/restore":
            return self._restore_apply(
                actor=actor,
                path=str(body.get("path") or ""),
                confirmation=str(body.get("confirmation") or ""),
            )
        if path == "/api/v1/system/support-bundle":
            return self.adapter.support_bundle_create(actor=actor)
        if path == "/api/v1/enrollments/manual":
            return self.adapter.enrollment_issue_manual(
                actor=actor,
                platform=str(body.get("platform") or ""),
                ttl_seconds=body.get("ttl_seconds"),
                label=str(body.get("label") or ""),
                note=str(body.get("note") or ""),
            )
        if path == "/api/v1/enrollments/zero-touch":
            ttl_value = body.get("ttl_seconds")
            return self.adapter.enrollment_issue_zero_touch(
                actor=actor,
                platform=str(body.get("platform") or ""),
                ttl_seconds=ttl_value,
                label=str(body.get("label") or ""),
                note=str(body.get("note") or ""),
                pre_approved=body.get("pre_approved", False),
            )
        if path == "/api/v1/drafts":
            return self.adapter.draft_create(
                actor=actor,
                bundle_text=str(body.get("bundle_text") or ""),
            )
        if path.startswith("/api/v1/drafts/"):
            suffix = path[len("/api/v1/drafts/") :]
            parts = [item for item in suffix.split("/") if item]
            if len(parts) != 2:
                raise ControlPlaneError("Web API route was not found.")
            draft_id, action = parts
            if action == "update":
                return self.adapter.draft_update(
                    draft_id, actor=actor, bundle_text=str(body.get("bundle_text") or "")
                )
            if action == "test":
                return self.adapter.draft_test(draft_id, actor=actor)
            if action == "diff":
                return self.adapter.draft_diff(draft_id, actor=actor)
            if action == "preview":
                return self.adapter.draft_preview(draft_id, actor=actor)
            if action == "apply":
                return self.adapter.draft_apply(
                    draft_id,
                    actor=actor,
                    change_plan_id=str(body.get("change_plan_id") or ""),
                    confirmation=str(body.get("confirmation") or ""),
                )
            if action == "cancel":
                return self.adapter.draft_cancel(draft_id, actor=actor)
            raise ControlPlaneError("Web API route was not found.")
        if path == "/api/v1/saved-views":
            return self.auth.save_view(
                principal.operator_id,
                name=str(body.get("name") or ""),
                payload=body.get("payload")
                if isinstance(body.get("payload"), dict)
                else {},
            )
        if path == "/api/v1/sessions/revoke":
            session_id = str(body.get("session_id") or "").strip()
            if not session_id:
                raise ControlPlaneError("session_id is required.")
            allowed = {
                str(item["id"]) for item in self.auth.list_sessions(principal.operator_id)
            }
            if session_id not in allowed and principal.role != ROLE_ADMIN:
                raise ControlPlaneError("Session is not owned by this operator.")
            if not self.auth.revoke_session(
                session_id, actor_id=principal.operator_id
            ):
                raise ControlPlaneError("Session was not found or already revoked.")
            return {"status": "revoked", "session_id": session_id}
        raise ControlPlaneError("Web API route was not found.")


def _first(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name) or []
    return str(values[0]) if values else ""


def _session_cookie(token: str, *, secure: bool) -> str:
    attrs = [
        "%s=%s" % (SESSION_COOKIE, token),
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
        "Max-Age=28800",
    ]
    if secure:
        attrs.append("Secure")
    return "; ".join(attrs)


def _clear_session_cookie(*, secure: bool) -> str:
    attrs = [
        "%s=" % SESSION_COOKIE,
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
        "Max-Age=0",
    ]
    if secure:
        attrs.append("Secure")
    return "; ".join(attrs)


class DrlinkWebHandler(BaseHTTPRequestHandler):
    server_version = "DataRelayLinkWeb/3.0"
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> WebApplication:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        if os.environ.get("DRLINK_WEB_QUIET") == "1":
            return
        super().log_message(fmt, *args)

    def _security_headers(self, *, api: bool = False) -> None:
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if api:
            self.send_header("Cache-Control", "no-store")

    def _json(
        self,
        status: int,
        payload: dict[str, Any],
        *,
        cookie: Optional[str] = None,
    ) -> None:
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self._security_headers(api=True)
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _body_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise ControlPlaneError("Invalid Content-Length.") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ControlPlaneError("Request body is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ControlPlaneError("Request body must be valid JSON.") from exc
        if not isinstance(body, dict):
            raise ControlPlaneError("Request body must be a JSON object.")
        return body

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie") or ""
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw)
        except cookies.CookieError:
            return ""
        morsel = jar.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _principal(self, *, csrf: bool = False) -> Optional[WebPrincipal]:
        return self.app.session_principal(
            self._cookie_token(),
            csrf_token=self.headers.get("X-CSRF-Token"),
            require_csrf=csrf,
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/automation/v1/"):
            self._error(405, "Automation API uses POST.")
            return
        if parsed.path == "/healthz":
            self._json(
                200,
                {
                    "service": "drlink-web",
                    "status": "ok",
                    "core_health_endpoint": "/api/v1/health",
                },
            )
            return
        if parsed.path.startswith("/api/"):
            principal = self._principal()
            if principal is None:
                self._error(401, "authentication required")
                return
            try:
                payload = self.app.read_api(
                    parsed.path, parse_qs(parsed.query, keep_blank_values=True), principal
                )
                self._json(200, payload)
            except ControlPlaneError as exc:
                self._error(400, str(exc))
            except Exception:
                self._error(500, "internal error")
            return
        self._static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/automation/v1/"):
            from drlink_automation_api import AutomationApi
            from drlink_service_accounts import (
                ServiceAccountRateLimited, ServiceAccountUnauthenticated,
            )
            header = str(self.headers.get("Authorization") or "")
            if not header.startswith("Bearer ") or len(header) > 512:
                self._error(401, "Service Account bearer credential required")
                return
            try:
                body = self._body_json()
                api = AutomationApi(self.app.root)
                try:
                    keys = self.headers.get_all("Idempotency-Key") or []
                    if len(keys) > 1:
                        raise ControlPlaneError("Only one Idempotency-Key is allowed.")
                    result = api.invoke(
                        parsed.path, header[7:].strip(), body,
                        idempotency_key=keys[0] if keys else None,
                    )
                finally:
                    api.close()
                self._json(200, result)
            except ServiceAccountRateLimited:
                self._error(429, "Automation API rate limit exceeded")
            except ServiceAccountUnauthenticated:
                self._error(401, "invalid Service Account credential")
            except ControlPlaneError:
                self._error(403, "Automation API request denied")
            except Exception:
                self._error(500, "internal error")
            return
        if parsed.path == "/api/v1/auth/login":
            try:
                body = self._body_json()
                payload = self.app.authenticate(
                    body,
                    source_addr=str(self.client_address[0]),
                    user_agent=self.headers.get("User-Agent") or "",
                )
                token = payload.pop("_session_token", None)
                self._json(
                    200,
                    payload,
                    cookie=_session_cookie(str(token), secure=self.app.secure_cookie)
                    if token
                    else None,
                )
            except ControlPlaneError:
                self._error(401, "invalid credentials or MFA")
            except Exception:
                self._error(500, "internal error")
            return
        if parsed.path == "/api/v1/auth/mfa/enroll/cancel":
            try:
                body = self._body_json()
                self._json(200, self.app.cancel_mfa_enrollment(body))
            except ControlPlaneError as exc:
                self._error(400, str(exc))
            except Exception:
                self._error(500, "internal error")
            return
        if parsed.path == "/api/v1/auth/mfa/enroll/confirm":
            try:
                body = self._body_json()
                payload = self.app.confirm_mfa_enrollment(
                    body,
                    source_addr=str(self.client_address[0]),
                    user_agent=self.headers.get("User-Agent") or "",
                )
                token = str(payload.pop("_session_token"))
                self._json(
                    200,
                    payload,
                    cookie=_session_cookie(token, secure=self.app.secure_cookie),
                )
            except ControlPlaneError as exc:
                self._error(400, str(exc))
            except Exception:
                self._error(500, "internal error")
            return
        principal = self._principal(csrf=True)
        if principal is None:
            self._error(403, "authenticated session and CSRF token required")
            return
        try:
            body = self._body_json()
            payload = self.app.write_api(parsed.path, body, principal)
            clear = parsed.path in (
                "/api/v1/auth/logout",
                "/api/v1/system/restore",
            )
            self._json(
                200,
                payload,
                cookie=_clear_session_cookie(secure=self.app.secure_cookie)
                if clear
                else None,
            )
        except ControlPlaneError as exc:
            self._error(400, str(exc))
        except Exception:
            self._error(500, "internal error")

    def _static(self, request_path: str) -> None:
        raw = unquote(str(request_path or "/"))
        if raw in ("", "/"):
            rel = Path("index.html")
        else:
            rel = Path(raw.lstrip("/"))
        if rel.is_absolute() or ".." in rel.parts:
            self._error(404, "not found")
            return
        target = (self.app.static_root / rel).resolve()
        root = self.app.static_root.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._error(404, "not found")
            return
        if not target.is_file():
            if "." not in rel.name:
                target = root / "index.html"
            if not target.is_file():
                self._error(404, "not found")
                return
        try:
            raw_bytes = target.read_bytes()
        except OSError:
            self._error(404, "not found")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw_bytes)))
        # app.js/styles.css use stable names, so browsers must revalidate them
        # after Web package upgrades. Long-lived caching is safe only for
        # ancillary assets whose stale copy cannot keep an old application UI.
        revalidate = target.name in {"index.html", "app.js", "styles.css"}
        self.send_header(
            "Cache-Control",
            "no-cache" if revalidate else "public, max-age=3600",
        )
        self._security_headers(api=False)
        self.end_headers()
        self.wfile.write(raw_bytes)


class DrlinkWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, app: WebApplication):
        self.app = app
        super().__init__(server_address, DrlinkWebHandler)

    def server_close(self) -> None:
        try:
            self.app.close()
        finally:
            super().server_close()


def create_server(
    *,
    root: Optional[str] = None,
    listen: str = DEFAULT_WEB_LISTEN,
    port: int = DEFAULT_WEB_PORT,
    static_root: Optional[str] = None,
    tls_cert: Optional[str] = None,
    tls_key: Optional[str] = None,
) -> DrlinkWebServer:
    validate_web_bind(listen, tls_cert=tls_cert, tls_key=tls_key)
    use_tls = bool(tls_cert and tls_key)
    app = WebApplication(root, static_root=static_root, secure_cookie=use_tls)
    server = DrlinkWebServer((listen, int(port)), app)
    if use_tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(tls_cert), str(tls_key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Data Relay Link optional Web Management")
    parser.add_argument("--listen", default=DEFAULT_WEB_LISTEN)
    parser.add_argument("--port", type=int, default=DEFAULT_WEB_PORT)
    parser.add_argument("--root")
    parser.add_argument("--static-root")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    args = parser.parse_args(argv)
    server = create_server(
        root=args.root,
        listen=args.listen,
        port=args.port,
        static_root=args.static_root,
        tls_cert=args.tls_cert,
        tls_key=args.tls_key,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
