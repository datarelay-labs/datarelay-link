#!/usr/bin/env python3
"""Versioned, explicitly allowlisted Core adapter for non-browser automation."""
from __future__ import annotations

from typing import Any, Optional

from drlink_control_db import ControlPlaneError
from drlink_management_catalog import management_tool
from drlink_management_core import ManagementCoreService, SURFACE_WEB
from drlink_service_accounts import ServiceAccountStore

PREFIX = "/api/automation/v1/"
# Only Core operations classified as read-only TEST/OBSERVE are published.
# Temporary Access preview issues an actor-bound short-lived Change Plan but
# does not grant authority to apply it through this automation adapter.
# All mutating Core operations remain excluded until durable idempotency and
# public mutation qualification are complete.
ALLOW = frozenset({
    "drlink_inventory_list", "drlink_inventory_get", "drlink_health",
    "drlink_access_hygiene",
    "drlink_diagnose_connection", "drlink_policy_test", "drlink_audit_query",
    "drlink_live_access", "drlink_job_list", "drlink_job_get",
    "drlink_temporary_access_preview",
})


class AutomationApi:
    def __init__(self, root: Optional[str] = None):
        self.accounts = ServiceAccountStore(root)
        self.core = ManagementCoreService(root)

    def close(self) -> None:
        self.accounts.close()

    def __enter__(self) -> "AutomationApi":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def invoke(self, path: str, credential: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(path, str) or not path.startswith(PREFIX):
            raise ControlPlaneError("Automation API route was not found.")
        operation = path[len(PREFIX):]
        # Core callers bypassing HTTP must obey the same canonical route
        # boundary: no query, fragment, nested path or encoded alias.
        if not operation or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in operation):
            raise ControlPlaneError("Automation API route was not found.")
        tool = management_tool(operation)
        if operation not in ALLOW or tool is None or not tool.read_only:
            raise ControlPlaneError("Automation operation is not allowlisted.")
        actor = self.accounts.authenticate(credential, limit=True)
        try:
            if not isinstance(payload, dict):
                raise ControlPlaneError("Automation payload must be an object.")
            result = self.core.invoke(
                name=operation, arguments=payload, actor=actor, surface=SURFACE_WEB
            )
        except Exception:
            self.accounts.audit_request(actor, operation=operation, allowed=False)
            raise
        self.accounts.audit_request(actor, operation=operation, allowed=True)
        return result
