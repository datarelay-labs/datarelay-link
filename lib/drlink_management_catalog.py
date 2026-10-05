#!/usr/bin/env python3
"""Data Relay Link 3.0 management capability catalog.

This module is intentionally transport-neutral. CLI, Web, and MCP project the
same Core capabilities; adapters must not invent authorization semantics.

Authority:
- docs/MANAGEMENT_SURFACE_CONTRACT.md
- docs/DATA_RELAY_ROADMAP.md (DRL3-0 / DRL3-1)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


OBSERVE = "OBSERVE"
TEST = "TEST"
CHANGE = "CHANGE"
INCIDENT_CHANGE = "INCIDENT_CHANGE"
JOB = "JOB"
RECOVERY_AUTHORITY = "RECOVERY_AUTHORITY"

OPERATION_CLASSES = frozenset(
    {OBSERVE, TEST, CHANGE, INCIDENT_CHANGE, JOB, RECOVERY_AUTHORITY}
)

PLUGIN_READ = "READ"
PLUGIN_CONTROLLED = "CONTROLLED"
PLUGIN_NO = "NO"
PLUGIN_EXPOSURES = frozenset({PLUGIN_READ, PLUGIN_CONTROLLED, PLUGIN_NO})


@dataclass(frozen=True)
class ManagementPermission:
    name: str
    description: str
    operation_classes: frozenset[str]


@dataclass(frozen=True)
class ManagementTool:
    name: str
    title: str
    description: str
    permission: str
    operation_class: str
    plugin_exposure: str
    input_schema: Mapping[str, Any]
    read_only: bool
    destructive: bool
    idempotent: bool

    def mcp_annotations(self) -> dict[str, bool]:
        return {
            "readOnlyHint": self.read_only,
            "destructiveHint": self.destructive,
            "openWorldHint": False,
            "idempotentHint": self.idempotent,
        }


MANAGEMENT_PERMISSIONS = (
    ManagementPermission(
        "management-read",
        "Read bounded Data Relay Link management state and audit summaries.",
        frozenset({OBSERVE}),
    ),
    ManagementPermission(
        "management-diagnose",
        "Run side-effect-free diagnosis and correlation.",
        frozenset({OBSERVE, TEST}),
    ),
    ManagementPermission(
        "management-policy-test",
        "Evaluate policy and Change Plan impact without mutation.",
        frozenset({TEST}),
    ),
    ManagementPermission(
        "management-temporary-access",
        "Preview and apply bounded Temporary Access expiry changes.",
        frozenset({TEST, CHANGE}),
    ),
    ManagementPermission(
        "management-config",
        "Preview and apply guided server-owned configuration changes through Core.",
        frozenset({TEST, CHANGE}),
    ),
    ManagementPermission(
        "management-emergency-cutoff",
        "Preview, apply, and clear Emergency New-Access Cutoff state.",
        frozenset({TEST, INCIDENT_CHANGE}),
    ),
    ManagementPermission(
        "management-job-observe",
        "Read bounded management Job status and results.",
        frozenset({OBSERVE}),
    ),
    ManagementPermission(
        "management-job-run",
        "Start or cancel explicitly admitted safe management Job families.",
        frozenset({JOB}),
    ),
)

MANAGEMENT_PERMISSION_NAMES = frozenset(p.name for p in MANAGEMENT_PERMISSIONS)


def _schema(required: tuple[str, ...] = (), **props: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {k: {"type": v} for k, v in props.items()},
        "required": list(required),
        "additionalProperties": False,
    }


MANAGEMENT_TOOLS = (
    ManagementTool(
        "drlink_inventory_list",
        "List Data Relay Link resources",
        "List a bounded page of Data Relay Link management resources.",
        "management-read",
        OBSERVE,
        PLUGIN_READ,
        _schema(("resource_type",), resource_type="string", cursor="string", limit="integer", query="string"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_inventory_get",
        "Get Data Relay Link resource",
        "Read one Data Relay Link management resource by immutable ID or canonical name.",
        "management-read",
        OBSERVE,
        PLUGIN_READ,
        _schema(("resource_type", "resource"), resource_type="string", resource="string"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_health",
        "Read Data Relay Link health",
        "Read bounded Core, Managed Host, service, audit-ingest, and job health.",
        "management-read",
        OBSERVE,
        PLUGIN_READ,
        _schema(resource_type="string", resource="string"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_diagnose_connection",
        "Diagnose connectivity",
        "Correlate policy, runtime, health, and recent decision evidence without mutation.",
        "management-diagnose",
        TEST,
        PLUGIN_READ,
        _schema(
            ("plane",),
            plane="string",
            source="string",
            destination="string",
            service="string",
            permission="string",
        ),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_policy_test",
        "Test access policy",
        "Evaluate the current Core policy without mutation.",
        "management-policy-test",
        TEST,
        PLUGIN_READ,
        _schema(
            ("plane", "source", "destination"),
            plane="string",
            source="string",
            destination="string",
            service="string",
            permission="string",
            path="string",
        ),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_audit_query",
        "Query audit history",
        "Read a bounded redacted page of authoritative Data Relay Link audit history.",
        "management-read",
        OBSERVE,
        PLUGIN_READ,
        _schema(
            start="string",
            end="string",
            category="string",
            event_type="string",
            actor="string",
            resource="string",
            result="string",
            correlation="string",
            cursor="string",
            limit="integer",
        ),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_guided_change_preview",
        "Preview guided management change",
        "Preview one guided Managed Host metadata, Object/Group, or Access Rule lifecycle change through existing Core semantics.",
        "management-config",
        TEST,
        PLUGIN_NO,
        _schema(("change_type", "payload"), change_type="string", payload="object"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_guided_change_apply",
        "Apply guided management change",
        "Apply a previously previewed revision-bound guided Core Change Plan.",
        "management-config",
        CHANGE,
        PLUGIN_NO,
        _schema(("change_plan_id", "confirmation"), change_plan_id="string", confirmation="string"),
        False,
        False,
        False,
    ),
    ManagementTool(
        "drlink_temporary_access_preview",
        "Preview Temporary Access",
        "Build a Change Plan for setting, changing, or clearing one access expiry.",
        "management-temporary-access",
        TEST,
        PLUGIN_READ,
        _schema(
            ("plane", "rule", "operation"),
            plane="string",
            rule="string",
            operation="string",
            expires_at="string",
        ),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_temporary_access_apply",
        "Apply Temporary Access",
        "Apply a previously previewed Temporary Access Change Plan.",
        "management-temporary-access",
        CHANGE,
        PLUGIN_CONTROLLED,
        _schema(("change_plan_id", "confirmation"), change_plan_id="string", confirmation="string"),
        False,
        False,
        False,
    ),
    ManagementTool(
        "drlink_live_access",
        "Read live access",
        "Read bounded current-use observations with explicit fidelity.",
        "management-read",
        OBSERVE,
        PLUGIN_READ,
        _schema(("plane",), plane="string", resource_type="string", resource="string", cursor="string", limit="integer"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_emergency_cutoff_preview",
        "Preview Emergency New-Access Cutoff",
        "Preview a reversible cutoff without mutating normal access policy.",
        "management-emergency-cutoff",
        TEST,
        PLUGIN_READ,
        _schema(("plane", "scope_kind", "scope_ref"), plane="string", scope_kind="string", scope_ref="string", operation="string", reason="string"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_emergency_cutoff_apply",
        "Apply Emergency New-Access Cutoff",
        "Apply a confirmed cutoff Change Plan for new authorization.",
        "management-emergency-cutoff",
        INCIDENT_CHANGE,
        PLUGIN_CONTROLLED,
        _schema(("change_plan_id", "confirmation"), change_plan_id="string", confirmation="string"),
        False,
        True,
        False,
    ),
    ManagementTool(
        "drlink_emergency_cutoff_clear",
        "Clear Emergency New-Access Cutoff",
        "Clear a confirmed cutoff and reveal the unchanged underlying normal policy.",
        "management-emergency-cutoff",
        INCIDENT_CHANGE,
        PLUGIN_CONTROLLED,
        _schema(("change_plan_id", "confirmation"), change_plan_id="string", confirmation="string"),
        False,
        True,
        False,
    ),
    ManagementTool(
        "drlink_job_list",
        "List management Jobs",
        "List a bounded page of management Jobs.",
        "management-job-observe",
        OBSERVE,
        PLUGIN_READ,
        _schema(cursor="string", limit="integer", status="string", job_type="string"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_job_get",
        "Get management Job",
        "Read one management Job and bounded per-target results.",
        "management-job-observe",
        OBSERVE,
        PLUGIN_READ,
        _schema(("job_id",), job_id="string"),
        True,
        False,
        True,
    ),
    ManagementTool(
        "drlink_diagnostic_job_start",
        "Start safe diagnostic Job",
        "Start an explicitly admitted bounded diagnostic Job.",
        "management-job-run",
        JOB,
        PLUGIN_CONTROLLED,
        _schema(("job_type",), job_type="string", resource_type="string", resource="string"),
        False,
        False,
        False,
    ),
)

MANAGEMENT_TOOL_NAMES = frozenset(t.name for t in MANAGEMENT_TOOLS)


def management_permission(name: str) -> ManagementPermission | None:
    key = str(name or "").strip().lower()
    return next((p for p in MANAGEMENT_PERMISSIONS if p.name == key), None)


def management_tool(name: str) -> ManagementTool | None:
    key = str(name or "").strip()
    return next((t for t in MANAGEMENT_TOOLS if t.name == key), None)


def validate_catalog(*, target_permissions: set[str] | frozenset[str] = frozenset()) -> None:
    """Fail closed when the frozen catalog violates cross-surface invariants."""
    if len(MANAGEMENT_PERMISSION_NAMES) != len(MANAGEMENT_PERMISSIONS):
        raise ValueError("duplicate management permission")
    if len(MANAGEMENT_TOOL_NAMES) != len(MANAGEMENT_TOOLS):
        raise ValueError("duplicate management tool")
    overlap = MANAGEMENT_PERMISSION_NAMES & {str(x).lower() for x in target_permissions}
    if overlap:
        raise ValueError("management permission overlaps target permission: %s" % sorted(overlap))
    for perm in MANAGEMENT_PERMISSIONS:
        if not perm.operation_classes or not perm.operation_classes <= OPERATION_CLASSES:
            raise ValueError("invalid operation classes for %s" % perm.name)
    for tool in MANAGEMENT_TOOLS:
        if tool.permission not in MANAGEMENT_PERMISSION_NAMES:
            raise ValueError("unknown permission for %s" % tool.name)
        if tool.operation_class not in OPERATION_CLASSES:
            raise ValueError("invalid operation class for %s" % tool.name)
        if tool.plugin_exposure not in PLUGIN_EXPOSURES:
            raise ValueError("invalid plugin exposure for %s" % tool.name)
        perm = management_permission(tool.permission)
        if perm is None or tool.operation_class not in perm.operation_classes:
            raise ValueError("permission/class mismatch for %s" % tool.name)
        if tool.operation_class in (CHANGE, INCIDENT_CHANGE, JOB) and tool.read_only:
            raise ValueError("mutating tool marked read-only: %s" % tool.name)
        if tool.operation_class == INCIDENT_CHANGE and not tool.destructive:
            raise ValueError("incident change must carry destructiveHint: %s" % tool.name)


def mcp_management_descriptors() -> tuple[dict[str, Any], ...]:
    """Return frozen descriptors; callers still decide when handlers are ready to advertise."""
    validate_catalog()
    out = []
    for tool in MANAGEMENT_TOOLS:
        out.append(
            {
                "name": tool.name,
                "title": tool.title,
                "description": tool.description,
                "inputSchema": dict(tool.input_schema),
                "annotations": tool.mcp_annotations(),
                "_meta": {
                    "datarelay/operationClass": tool.operation_class,
                    "datarelay/requiredPermission": tool.permission,
                    "datarelay/pluginExposure": tool.plugin_exposure,
                },
            }
        )
    return tuple(out)
