#!/usr/bin/env python3
"""Data Relay Link 3.0 Management MCP projection.

This adapter depends only on the shared Core Management Service. It does not
call the Web API adapter and does not inherit the legacy AI-job authorization
model.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from drlink_management_core import (
    ManagementActor,
    ManagementAuthorizationError,
    ManagementCoreService,
    SURFACE_MCP,
)
from drlink_management_catalog import MANAGEMENT_PERMISSION_NAMES


class ManagementMcpAdapter:
    def __init__(self, root: Optional[str] = None):
        self.core = ManagementCoreService(root)

    def actor_from_ai_access(
        self, *, identity: str, destination: str
    ) -> ManagementActor:
        """Resolve management permissions through the canonical AI Access evaluator."""
        from drlink_control_plane import ControlPlane
        import drlink_v24 as v24

        principal_name = str(identity or "").strip()
        target = str(destination or "").strip()
        if not principal_name or not target:
            raise ManagementAuthorizationError(
                "AI Identity and management destination are required."
            )
        plane = ControlPlane(self.core.root, read_only=True)
        try:
            principal = plane.get_principal(principal_name)
            allowed = set()
            authenticated = False
            for permission in sorted(MANAGEMENT_PERMISSION_NAMES):
                decision = v24.evaluate_ai_access_v24(
                    plane,
                    identity=principal_name,
                    destination=target,
                    permission=permission,
                )
                if str(decision.get("auth") or "").upper() == "VERIFIED":
                    authenticated = True
                if str(decision.get("result") or "").upper() == "ALLOW":
                    allowed.add(permission)
            if not authenticated or principal is None:
                raise ManagementAuthorizationError(
                    "Verified AI Identity is required for management MCP."
                )
            actor_id = "ai:%s" % str(principal["id"])
            return ManagementActor.authenticated(actor_id, allowed)
        finally:
            plane.close()

    def list_tools(self, *, actor: ManagementActor) -> tuple[dict[str, Any], ...]:
        return self.core.mcp_descriptors(actor=actor)

    def call_tool(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        actor: ManagementActor,
    ) -> dict[str, Any]:
        return self.core.invoke(
            name=name,
            arguments=arguments,
            actor=actor,
            surface=SURFACE_MCP,
        )
