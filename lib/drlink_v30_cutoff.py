#!/usr/bin/env python3
"""Emergency New-Access Cutoff primitives for Data Relay Link 3.0."""
from __future__ import annotations

from typing import Any, Iterable, Optional

from drlink_control_db import ControlPlaneError

CUTOFF_SCOPE_KINDS = {
    "remote": frozenset({"plane", "remote-service"}),
    "internet": frozenset({"plane", "managed-host"}),
    "ai": frozenset({"plane", "ai-identity"}),
}


def normalize_cutoff_scope(
    plane: str,
    scope_kind: str,
    scope_ref: Optional[str] = None,
) -> tuple[str, str, str]:
    family = str(plane or "").strip().lower()
    if family not in CUTOFF_SCOPE_KINDS:
        raise ControlPlaneError("Unsupported access plane: %s" % plane)
    kind = str(scope_kind or "").strip().lower()
    if kind not in CUTOFF_SCOPE_KINDS[family]:
        raise ControlPlaneError(
            "Unsupported %s cutoff scope '%s'. Supported: %s"
            % (family, scope_kind, ", ".join(sorted(CUTOFF_SCOPE_KINDS[family])))
        )
    ref = str(scope_ref or "").strip()
    if kind == "plane":
        if ref:
            raise ControlPlaneError("Plane-level cutoff does not accept a resource reference.")
        return family, kind, ""
    if not ref:
        raise ControlPlaneError("%s cutoff requires a resource reference." % kind)
    if len(ref) > 256:
        raise ControlPlaneError("Cutoff resource reference is too long.")
    return family, kind, ref


def active_cutoffs(conn, plane: str) -> list[dict[str, Any]]:
    family = str(plane or "").strip().lower()
    if family not in CUTOFF_SCOPE_KINDS:
        raise ControlPlaneError("Unsupported access plane: %s" % plane)
    rows = conn.execute(
        "SELECT id,plane,scope_kind,scope_ref,reason,row_version,updated_at "
        "FROM emergency_cutoffs WHERE active=1 AND plane=? "
        "ORDER BY CASE scope_kind WHEN 'plane' THEN 0 ELSE 1 END, scope_kind, scope_ref",
        (family,),
    ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def _same(value: Optional[str], expected: str) -> bool:
    return str(value or "").strip().casefold() == str(expected or "").strip().casefold()


def matching_cutoff(
    conn,
    plane: str,
    *,
    remote_service: Optional[str] = None,
    remote_service_id: Optional[str] = None,
    managed_hosts: Iterable[str] = (),
    ai_identity: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Return the active cutoff that blocks this new authorization, if any."""
    family = str(plane or "").strip().lower()
    if family not in CUTOFF_SCOPE_KINDS:
        raise ControlPlaneError("Unsupported access plane: %s" % plane)
    hosts = tuple(str(x or "").strip() for x in managed_hosts if str(x or "").strip())
    for cutoff in active_cutoffs(conn, family):
        kind = str(cutoff["scope_kind"])
        ref = str(cutoff["scope_ref"] or "")
        if kind == "plane":
            return cutoff
        if family == "remote" and kind == "remote-service":
            if _same(remote_service, ref) or _same(remote_service_id, ref):
                return cutoff
        if family == "internet" and kind == "managed-host":
            if any(_same(host, ref) for host in hosts):
                return cutoff
        if family == "ai" and kind == "ai-identity" and _same(ai_identity, ref):
            return cutoff
    return None


def cutoff_reason(cutoff: dict[str, Any]) -> str:
    kind = str(cutoff.get("scope_kind") or "plane")
    ref = str(cutoff.get("scope_ref") or "")
    suffix = ("%s=%s" % (kind, ref)) if ref else kind
    return "Emergency New-Access Cutoff active (%s)" % suffix
