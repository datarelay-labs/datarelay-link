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
