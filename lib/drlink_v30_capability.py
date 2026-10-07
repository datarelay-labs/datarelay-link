#!/usr/bin/env python3
"""Machine-auditable Data Relay Link 3.0 management capability parity inventory."""
from __future__ import annotations

from typing import Any, Iterable

from drlink_management_catalog import MANAGEMENT_TOOLS, validate_catalog

LEDGER_SCHEMA_VERSION = 1
CORE_READY = "READY"
CORE_CONTRACT_ONLY = "CONTRACT_ONLY"


def _ready_tool_names() -> frozenset[str]:
    """Use the same complete registry as Core dispatch, not a partial copy."""
    # Import lazily: the Core imports query services which expose this ledger.
    # Guided changes, Remote Services, and fleet Jobs must stay in lockstep with
    # actual dispatch readiness; surface permissions remain the adapter's job.
    from drlink_management_core import implemented_management_tool_names

    return implemented_management_tool_names()


def capability_parity_ledger(
    *,
    ready_tool_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Generate parity rows from the canonical catalog; never duplicate its tool list."""
    validate_catalog()
    ready = (
        frozenset(str(name) for name in ready_tool_names)
        if ready_tool_names is not None
        else _ready_tool_names()
    )
    catalog_names = frozenset(tool.name for tool in MANAGEMENT_TOOLS)
    unknown = ready - catalog_names
    if unknown:
        raise ValueError("implemented management tool missing from catalog: %s" % sorted(unknown))

    rows: list[dict[str, Any]] = []
    for tool in MANAGEMENT_TOOLS:
        core_ready = tool.name in ready
        rows.append(
            {
                "name": tool.name,
                "title": tool.title,
                "operation_class": tool.operation_class,
                "permission": tool.permission,
                "read_only": bool(tool.read_only),
                "destructive": bool(tool.destructive),
                "idempotent": bool(tool.idempotent),
                "core_status": CORE_READY if core_ready else CORE_CONTRACT_ONLY,
                "cli_target": "REQUIRED",
                "web_target": "FULL_PARITY",
                "plugin_target": tool.plugin_exposure,
            }
        )

    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "source": "drlink_management_catalog.MANAGEMENT_TOOLS",
        "authoritative": False,
        "machine_generated": True,
        "capability_count": len(rows),
        "core_ready_count": sum(1 for row in rows if row["core_status"] == CORE_READY),
        "contract_only_count": sum(
            1 for row in rows if row["core_status"] == CORE_CONTRACT_ONLY
        ),
        "capabilities": rows,
    }
