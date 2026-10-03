#!/usr/bin/env python3
"""Transport-neutral Data Relay Link 3.0 management query service.

CLI, Web, and MCP adapters consume this Core query boundary rather than issuing
surface-specific SQL. The service uses a separate SQLite read-only/query-only
connection for inventory and opens short-lived read-only Core views for
evaluators that already exist in the control plane.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional

from drlink_control_db import ControlPlaneError, connect_read_only
from drlink_control_plane import ControlPlane
from drlink_management_catalog import mcp_management_descriptors

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
_CURSOR_VERSION = 1

# A catalog entry is not advertised merely because its name/schema is frozen.
# Only handlers implemented by this service may be projected by a future MCP
# adapter.
IMPLEMENTED_MANAGEMENT_TOOLS = frozenset(
    {
        "drlink_inventory_list",
        "drlink_inventory_get",
        "drlink_health",
        "drlink_policy_test",
        "drlink_audit_query",
        "drlink_live_access",
        "drlink_job_list",
        "drlink_job_get",
    }
)


@dataclass(frozen=True)
class ManagementPage:
    resource_type: str
    items: tuple[dict[str, Any], ...]
    next_cursor: Optional[str]
    limit: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "items": [dict(item) for item in self.items],
            "next_cursor": self.next_cursor,
            "limit": self.limit,
        }


# Internal projections. Public adapters use product nouns from the keys and do
# not expose table/schema names.
_RESOURCE_SPECS: dict[str, dict[str, str]] = {
    "managed-host": {
        "from": "clients c",
        "id": "c.id",
        "name": "COALESCE(NULLIF(c.label, ''), NULLIF(c.hostname, ''), c.id)",
        "select": (
            "c.id AS id, "
            "COALESCE(NULLIF(c.label, ''), NULLIF(c.hostname, ''), c.id) AS name, "
            "c.hostname AS hostname, c.status AS status, c.trust_status AS trust_status, "
            "c.connected AS connected, c.last_seen AS last_seen, "
            "c.agent_heartbeat_at AS agent_heartbeat_at, "
            "c.agent_lifecycle_state AS agent_lifecycle_state, "
            "c.row_version AS row_version, c.updated_at AS updated_at"
        ),
    },
    "remote-service": {
        "from": "published_services s LEFT JOIN clients c ON c.id = s.client_id",
        "id": "s.id",
        "name": "s.name",
        "select": (
            "s.id AS id, s.name AS name, s.client_id AS managed_host_id, "
            "COALESCE(NULLIF(c.label, ''), NULLIF(c.hostname, ''), c.id) AS managed_host, "
            "s.service_type AS service_type, s.target_mode AS target_mode, "
            "s.target_host AS target_host, s.target_port AS target_port, "
            "s.public_port AS public_port, s.enabled AS enabled, s.released AS released"
        ),
    },
    "network-object": {
        "from": "objects o",
        "id": "o.id",
        "name": "o.name",
        "select": (
            "o.id AS id, o.name AS name, o.type AS type, o.origin AS origin, "
            "o.status AS status, o.description AS description, o.row_version AS row_version"
        ),
        "where": "o.type <> 'managed_endpoint'",
    },
    "network-group": {
        "from": "object_groups g",
        "id": "g.id",
        "name": "g.name",
        "select": (
            "g.id AS id, g.name AS name, g.description AS description, "
            "g.row_version AS row_version"
        ),
    },
    "service-object": {
        "from": "service_objects s",
        "id": "s.id",
        "name": "s.name",
        "select": (
            "s.id AS id, s.name AS name, s.type AS type, s.port AS port, "
            "s.description AS description, s.row_version AS row_version"
        ),
    },
    "service-group": {
        "from": "service_groups g",
        "id": "g.id",
        "name": "g.name",
        "select": (
            "g.id AS id, g.name AS name, g.description AS description, "
            "g.row_version AS row_version"
        ),
    },
    "permission-object": {
        "from": "permission_objects p",
        "id": "p.id",
        "name": "p.name",
        "select": (
            "p.id AS id, p.name AS name, p.description AS description, "
            "p.row_version AS row_version"
        ),
    },
    "permission-group": {
        "from": "permission_groups g",
        "id": "g.id",
        "name": "g.name",
        "select": (
            "g.id AS id, g.name AS name, g.description AS description, "
            "g.row_version AS row_version"
        ),
    },
    "ai-identity": {
        "from": "ai_principals a",
        "id": "a.id",
        "name": "a.name",
        "select": (
            "a.id AS id, a.name AS name, a.enabled AS enabled, "
            "a.credential_status AS credential_status, a.auth_mode AS auth_mode, "
            "a.last_seen AS last_seen, a.row_version AS row_version"
        ),
    },
}


def supported_inventory_types() -> tuple[str, ...]:
    return tuple(sorted(_RESOURCE_SPECS))


def _bounded_limit(value: Optional[int]) -> int:
    if value is None:
        return DEFAULT_PAGE_SIZE
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ControlPlaneError("Management query limit must be an integer.") from exc
    if limit < 1:
        raise ControlPlaneError("Management query limit must be at least 1.")
    return min(limit, MAX_PAGE_SIZE)


def _encode_cursor(resource_type: str, name_key: str, resource_id: str) -> str:
    raw = json.dumps(
        {
            "v": _CURSOR_VERSION,
            "resource": resource_type,
            "name": name_key,
            "id": resource_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: Optional[str], resource_type: str
) -> Optional[tuple[str, str]]:
    if cursor is None or not str(cursor).strip():
        return None
    text = str(cursor).strip()
    try:
        padded = text + "=" * (-len(text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception as exc:
        raise ControlPlaneError("Invalid management query cursor.") from exc
    if (
        payload.get("v") != _CURSOR_VERSION
        or payload.get("resource") != resource_type
        or not isinstance(payload.get("name"), str)
        or not isinstance(payload.get("id"), str)
    ):
        raise ControlPlaneError("Management query cursor does not match this resource.")
    return payload["name"], payload["id"]


def _encode_audit_cursor(occurred_at: str, row_id: int) -> str:
    raw = json.dumps(
        {
            "v": _CURSOR_VERSION,
            "resource": "audit",
            "time": str(occurred_at),
            "id": int(row_id),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_audit_cursor(cursor: Optional[str]) -> Optional[tuple[str, int]]:
    if cursor is None or not str(cursor).strip():
        return None
    text = str(cursor).strip()
    try:
        padded = text + "=" * (-len(text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        row_id = int(payload.get("id"))
    except Exception as exc:
        raise ControlPlaneError("Invalid audit query cursor.") from exc
    if (
        payload.get("v") != _CURSOR_VERSION
        or payload.get("resource") != "audit"
        or not isinstance(payload.get("time"), str)
        or row_id < 1
    ):
        raise ControlPlaneError("Audit query cursor is invalid.")
    return payload["time"], row_id


def _encode_job_cursor(created_at: str, job_id: str) -> str:
    raw = json.dumps(
        {
            "v": _CURSOR_VERSION,
            "resource": "management-job",
            "time": str(created_at or ""),
            "id": str(job_id or ""),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_job_cursor(cursor: Optional[str]) -> Optional[tuple[str, str]]:
    if cursor is None or not str(cursor).strip():
        return None
    text = str(cursor).strip()
    try:
        padded = text + "=" * (-len(text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception as exc:
        raise ControlPlaneError("Invalid management Job cursor.") from exc
    if (
        payload.get("v") != _CURSOR_VERSION
        or payload.get("resource") != "management-job"
        or not isinstance(payload.get("time"), str)
        or not isinstance(payload.get("id"), str)
    ):
        raise ControlPlaneError("Management Job cursor is invalid.")
    return payload["time"], payload["id"]


def _json_field(value: Any, fallback):
    if value is None or value == "":
        return fallback
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return fallback
    return decoded


def _encode_live_cursor(plane: str, started_at: str, observation_id: str) -> str:
    raw = json.dumps(
        {
            "v": _CURSOR_VERSION,
            "resource": "live:%s" % plane,
            "time": str(started_at or ""),
            "id": str(observation_id or ""),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_live_cursor(
    cursor: Optional[str], plane: str
) -> Optional[tuple[str, str]]:
    if cursor is None or not str(cursor).strip():
        return None
    text = str(cursor).strip()
    try:
        padded = text + "=" * (-len(text) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception as exc:
        raise ControlPlaneError("Invalid live-access cursor.") from exc
    if (
        payload.get("v") != _CURSOR_VERSION
        or payload.get("resource") != "live:%s" % plane
        or not isinstance(payload.get("time"), str)
        or not isinstance(payload.get("id"), str)
    ):
        raise ControlPlaneError("Live-access cursor does not match this plane.")
    return payload["time"], payload["id"]


class ManagementQueryService:
    """Bounded read side of the 3.0 Core Management Service."""

    def __init__(self, root: Optional[str] = None):
        self.root = root
        self.conn = connect_read_only(root=root)

    @classmethod
    def open_read_only(cls, root: Optional[str] = None) -> "ManagementQueryService":
        return cls(root)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ManagementQueryService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def ready_mcp_descriptors() -> tuple[dict[str, Any], ...]:
        return tuple(
            descriptor
            for descriptor in mcp_management_descriptors()
            if descriptor["name"] in IMPLEMENTED_MANAGEMENT_TOOLS
        )

    def list_inventory(
        self,
        resource_type: str,
        *,
        query: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> ManagementPage:
        kind = str(resource_type or "").strip().lower()
        spec = _RESOURCE_SPECS.get(kind)
        if spec is None:
            raise ControlPlaneError(
                "Unsupported management resource type '%s'. Supported: %s"
                % (resource_type, ", ".join(supported_inventory_types()))
            )

        page_limit = _bounded_limit(limit)
        after = _decode_cursor(cursor, kind)
        where_parts: list[str] = []
        args: list[Any] = []

        if spec.get("where"):
            where_parts.append(str(spec["where"]))

        name_expr = str(spec["name"])
        id_expr = str(spec["id"])
        needle = str(query or "").strip().lower()
        if needle:
            where_parts.append("LOWER(%s) LIKE ?" % name_expr)
            args.append("%%%s%%" % needle)
        if after is not None:
            where_parts.append(
                "(LOWER(%s) > ? OR (LOWER(%s) = ? AND %s > ?))"
                % (name_expr, name_expr, id_expr)
            )
            args.extend((after[0], after[0], after[1]))

        where_sql = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        sql = (
            "SELECT %s FROM %s%s ORDER BY LOWER(%s), %s LIMIT ?"
            % (spec["select"], spec["from"], where_sql, name_expr, id_expr)
        )
        args.append(page_limit + 1)
        rows = self.conn.execute(sql, tuple(args)).fetchall()

        has_more = len(rows) > page_limit
        page_rows = rows[:page_limit]
        items = tuple(
            {key: row[key] for key in row.keys()}
            for row in page_rows
        )
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_cursor(
                kind,
                str(last["name"] or "").lower(),
                str(last["id"]),
            )
        return ManagementPage(kind, items, next_cursor, page_limit)

    def get_inventory(self, resource_type: str, selector: str) -> dict[str, Any]:
        kind = str(resource_type or "").strip().lower()
        spec = _RESOURCE_SPECS.get(kind)
        if spec is None:
            raise ControlPlaneError(
                "Unsupported management resource type '%s'." % resource_type
            )
        text = str(selector or "").strip()
        if not text:
            raise ControlPlaneError("Management resource selector is required.")

        clauses = ["(%s = ? OR %s = ? COLLATE NOCASE)" % (spec["id"], spec["name"])]
        args: list[Any] = [text, text]
        if spec.get("where"):
            clauses.append(str(spec["where"]))
        sql = "SELECT %s FROM %s WHERE %s LIMIT 2" % (
            spec["select"],
            spec["from"],
            " AND ".join(clauses),
        )
        rows = self.conn.execute(sql, tuple(args)).fetchall()
        if not rows:
            raise ControlPlaneError("%s '%s' was not found." % (kind, text))
        if len(rows) > 1:
            raise ControlPlaneError("%s '%s' is ambiguous." % (kind, text))
        row = rows[0]
        return {key: row[key] for key in row.keys()}

    def get_managed_host(self, selector: str) -> Optional[dict[str, Any]]:
        try:
            return self.get_inventory("managed-host", selector)
        except ControlPlaneError as exc:
            if "was not found" in str(exc):
                return None
            raise

    def health(self) -> dict[str, Any]:
        """Return bounded Core health without creating configuration state."""
        plane = ControlPlane(self.root, read_only=True)
        try:
            status = dict(plane.status())
        finally:
            plane.close()
        from drlink_v30_jobs import job_operational_summary

        status["resource"] = "data-relay-link"
        status["read_only"] = True
        status["management_jobs"] = job_operational_summary(self.conn)
        return status

    def policy_test(
        self,
        *,
        plane: str,
        source: str,
        destination: str,
        service: Optional[str] = None,
        permission: Optional[str] = None,
        path: Optional[str] = None,
        resolve_fn=None,
    ) -> dict[str, Any]:
        """Delegate to the same Core evaluators used by CLI/runtime."""
        family = str(plane or "").strip().lower()
        core = ControlPlane(self.root, read_only=True)
        try:
            import drlink_v24 as v24

            if family in ("remote", "internet"):
                if not service:
                    raise ControlPlaneError("%s policy test requires service." % family)
                return v24.evaluate_selector_policy(
                    core,
                    family,
                    source_name=source,
                    destination_name=destination,
                    service_name=service,
                    resolve_fn=resolve_fn,
                )
            if family == "ai":
                if not permission:
                    raise ControlPlaneError("AI policy test requires permission.")
                return v24.test_ai_access_v24(
                    core,
                    identity=source,
                    destination=destination,
                    permission=permission,
                    path=path,
                )
            raise ControlPlaneError("Unsupported access plane: %s" % plane)
        finally:
            core.close()

    def audit_query(
        self,
        *,
        start: Optional[str] = None,
        end: Optional[str] = None,
        category: Optional[str] = None,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        result: Optional[str] = None,
        correlation: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> ManagementPage:
        """Read bounded unified 3.0 audit history with keyset pagination."""
        page_limit = _bounded_limit(limit)
        after = _decode_audit_cursor(cursor)
        where_parts = ["occurred_at IS NOT NULL"]
        args: list[Any] = []

        start_text = str(start or "").strip()
        end_text = str(end or "").strip()
        if start_text:
            where_parts.append("occurred_at >= ?")
            args.append(start_text)
        if end_text:
            where_parts.append("occurred_at <= ?")
            args.append(end_text)

        category_text = str(category or "").strip().upper()
        if category_text:
            where_parts.append("category = ?")
            args.append(category_text)

        event_type_text = str(event_type or "").strip()
        if event_type_text:
            where_parts.append("event_type = ?")
            args.append(event_type_text)

        actor_text = str(actor or "").strip()
        if actor_text:
            where_parts.append("actor_id = ?")
            args.append(actor_text)

        resource_text = str(resource or "").strip()
        if resource_text:
            where_parts.append("entity_id = ?")
            args.append(resource_text)

        result_text = str(result or "").strip().lower()
        if result_text:
            where_parts.append("LOWER(result) = ?")
            args.append(result_text)

        correlation_text = str(correlation or "").strip()
        if correlation_text:
            where_parts.append("correlation_id = ?")
            args.append(correlation_text)

        if after is not None:
            where_parts.append(
                "(occurred_at < ? OR (occurred_at = ? AND id < ?))"
            )
            args.extend((after[0], after[0], after[1]))

        args.append(page_limit + 1)
        rows = self.conn.execute(
            "SELECT * FROM audit_events WHERE %s "
            "ORDER BY occurred_at DESC, id DESC LIMIT ?"
            % " AND ".join(where_parts),
            tuple(args),
        ).fetchall()

        has_more = len(rows) > page_limit
        page_rows = rows[:page_limit]
        items = []
        for row in page_rows:
            items.append(
                {
                    "row_id": int(row["id"]),
                    "event_id": row["event_id"],
                    "schema_version": int(row["schema_version"] or 1),
                    "category": row["category"],
                    "event_type": row["event_type"],
                    "occurred_at": row["occurred_at"],
                    "source": row["source"],
                    "source_sequence": row["source_sequence"],
                    "actor_type": row["actor_type"],
                    "actor_id": row["actor_id"],
                    "delegated_actor_id": row["delegated_actor_id"],
                    "interface": row["interface"],
                    "action": row["action"],
                    "resource_type": row["entity_type"],
                    "resource_id": row["entity_id"],
                    "operation": row["operation"],
                    "result": row["result"],
                    "reason_code": row["reason_code"],
                    "correlation_id": row["correlation_id"],
                    "request_id": row["request_id"],
                    "session_id": row["session_id"],
                    "revision_before": row["revision_before"],
                    "revision_after": row["revision_after"],
                    "matched_policy": _json_field(row["matched_policy_json"], []),
                    "source_meta": _json_field(row["source_meta_json"], {}),
                    "destination_meta": _json_field(
                        row["destination_meta_json"], {}
                    ),
                    "before_summary": row["before_summary"] or "",
                    "after_summary": row["after_summary"] or "",
                    "impact_summary": row["impact_summary"] or "",
                    "legacy": row["event_id"] is None,
                }
            )

        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_audit_cursor(
                str(last["occurred_at"]),
                int(last["id"]),
            )
        return ManagementPage(
            resource_type="audit-event",
            items=tuple(items),
            next_cursor=next_cursor,
            limit=page_limit,
        )

    def job_list(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> ManagementPage:
        """Read a bounded keyset page of management Jobs."""
        from drlink_v30_jobs import JOB_STATUSES

        page_limit = _bounded_limit(limit)
        after = _decode_job_cursor(cursor)
        where: list[str] = []
        args: list[Any] = []
        status_text = str(status or "").strip().upper()
        if status_text:
            if status_text not in JOB_STATUSES:
                raise ControlPlaneError("Unsupported management Job status.")
            where.append("status=?")
            args.append(status_text)
        type_text = str(job_type or "").strip().lower()
        if type_text:
            where.append("job_type=?")
            args.append(type_text)
        if after is not None:
            where.append("(created_at < ? OR (created_at = ? AND id < ?))")
            args.extend((after[0], after[0], after[1]))
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        args.append(page_limit + 1)
        rows = self.conn.execute(
            "SELECT id,job_type,requested_by,resource_type,resource_ref,status,"
            "cancel_requested,target_count,created_at,started_at,finished_at,"
            "deadline_at,updated_at,last_error FROM management_jobs"
            + where_sql
            + " ORDER BY created_at DESC,id DESC LIMIT ?",
            tuple(args),
        ).fetchall()
        has_more = len(rows) > page_limit
        page_rows = rows[:page_limit]
        items = tuple({key: row[key] for key in row.keys()} for row in page_rows)
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_job_cursor(str(last["created_at"]), str(last["id"]))
        return ManagementPage(
            resource_type="management-job",
            items=items,
            next_cursor=next_cursor,
            limit=page_limit,
        )

    def job_get(self, job_id: str) -> dict[str, Any]:
        """Read one management Job and its bounded per-target terminal/progress truth."""
        from drlink_v30_jobs import MAX_JOB_TARGETS

        ident = str(job_id or "").strip()
        if not ident:
            raise ControlPlaneError("Management Job ID is required.")
        row = self.conn.execute(
            "SELECT id,job_type,requested_by,resource_type,resource_ref,status,"
            "cancel_requested,target_count,created_at,started_at,finished_at,"
            "deadline_at,updated_at,last_error FROM management_jobs WHERE id=?",
            (ident,),
        ).fetchone()
        if not row:
            raise ControlPlaneError("Management Job was not found.")
        out = {key: row[key] for key in row.keys()}
        target_rows = self.conn.execute(
            "SELECT target_id,status,worker_id,attempt,started_at,finished_at,"
            "lease_expires_at,updated_at,result_json,error "
            "FROM management_job_targets WHERE job_id=? ORDER BY target_id LIMIT ?",
            (ident, MAX_JOB_TARGETS),
        ).fetchall()
        targets = []
        for target in target_rows:
            item = {key: target[key] for key in target.keys() if key != "result_json"}
            item["result"] = _json_field(target["result_json"], {})
            targets.append(item)
        out["targets"] = targets
        return out

    def live_access(
        self,
        *,
        plane: str,
        resource_type: Optional[str] = None,
        resource: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Read bounded current-use state with explicit plane fidelity."""
        from drlink_v30_live import (
            FIDELITY_EXACT,
            FIDELITY_UNKNOWN,
            default_live_snapshot_path,
            read_live_snapshot,
        )

        family = str(plane or "").strip().lower()
        if family not in ("remote", "internet", "ai"):
            raise ControlPlaneError("Unsupported access plane: %s" % plane)
        page_limit = _bounded_limit(limit)
        after = _decode_live_cursor(cursor, family)
        selector = str(resource or "").strip().casefold()

        if family == "remote":
            return {
                "plane": "remote",
                "resource_type": resource_type,
                "resource": resource,
                "fidelity": FIDELITY_UNKNOWN,
                "active_count": None,
                "observations": [],
                "next_cursor": None,
                "limit": page_limit,
                "reason": (
                    "official FRP does not expose a proven exact active-connection "
                    "lifecycle without a fork"
                ),
            }

        if family == "internet":
            snapshots = [
                read_live_snapshot(
                    default_live_snapshot_path("internet-gateway", self.root)
                ),
                read_live_snapshot(
                    default_live_snapshot_path("fixed-tcp", self.root)
                ),
            ]
            if any(item.get("fidelity") != FIDELITY_EXACT for item in snapshots):
                reasons = [
                    str(item.get("reason") or "")
                    for item in snapshots
                    if item.get("fidelity") != FIDELITY_EXACT
                ]
                return {
                    "plane": "internet",
                    "resource_type": resource_type,
                    "resource": resource,
                    "fidelity": FIDELITY_UNKNOWN,
                    "active_count": None,
                    "observations": [],
                    "next_cursor": None,
                    "limit": page_limit,
                    "reason": "; ".join(x for x in reasons if x)
                    or "one or more live-access producers are unavailable",
                }

            observations: list[dict[str, Any]] = []
            for snapshot in snapshots:
                producer = str(snapshot.get("producer") or "internet")
                for raw in snapshot.get("observations") or []:
                    if not isinstance(raw, dict):
                        continue
                    item = dict(raw)
                    item["observation_kind"] = "NETWORK_SESSION"
                    item["observation_id"] = "%s:%s" % (
                        producer,
                        item.get("session_id") or item.get("connection_id") or "",
                    )
                    if selector:
                        searchable = {
                            str(item.get(key) or "").strip().casefold()
                            for key in (
                                "session_id",
                                "connection_id",
                                "hostname",
                                "relay_id",
                                "relay_name",
                                "profile_id",
                                "source_ip",
                            )
                        }
                        if selector not in searchable:
                            continue
                    observations.append(item)

            observations.sort(
                key=lambda item: (
                    str(item.get("started_at") or ""),
                    str(item.get("observation_id") or ""),
                ),
                reverse=True,
            )
            matching_count = len(observations)
            if after is not None:
                observations = [
                    item
                    for item in observations
                    if (
                        str(item.get("started_at") or "") < after[0]
                        or (
                            str(item.get("started_at") or "") == after[0]
                            and str(item.get("observation_id") or "") < after[1]
                        )
                    )
                ]
            has_more = len(observations) > page_limit
            page = observations[:page_limit]
            next_cursor = None
            if has_more and page:
                last = page[-1]
                next_cursor = _encode_live_cursor(
                    family,
                    str(last.get("started_at") or ""),
                    str(last.get("observation_id") or ""),
                )
            return {
                "plane": "internet",
                "resource_type": resource_type,
                "resource": resource,
                "fidelity": FIDELITY_EXACT,
                "active_count": matching_count,
                "observations": page,
                "next_cursor": next_cursor,
                "limit": page_limit,
                "reason": "",
            }

        # AI Access current-use truth comes from authoritative queued/running jobs.
        base_where = ["j.status IN ('queued','running')"]
        base_args: list[Any] = []
        if selector:
            base_where.append(
                "(LOWER(j.id)=? OR LOWER(COALESCE(a.name,''))=? "
                "OR LOWER(COALESCE(o.name,''))=? OR LOWER(COALESCE(j.client_id,''))=?)"
            )
            base_args.extend((selector, selector, selector, selector))
        count_row = self.conn.execute(
            "SELECT COUNT(*) FROM ai_jobs j "
            "LEFT JOIN ai_principals a ON a.id=j.principal_id "
            "LEFT JOIN objects o ON o.id=j.endpoint_object_id "
            "WHERE %s" % " AND ".join(base_where),
            tuple(base_args),
        ).fetchone()
        matching_count = int(count_row[0] or 0)

        where = list(base_where)
        args = list(base_args)
        if after is not None:
            where.append(
                "(COALESCE(j.claimed_at,j.created_at) < ? OR "
                "(COALESCE(j.claimed_at,j.created_at) = ? AND j.id < ?))"
            )
            args.extend((after[0], after[0], after[1]))
        args.append(page_limit + 1)
        rows = self.conn.execute(
            "SELECT j.id,j.capability,j.status,j.created_at,j.claimed_at,j.updated_at,"
            "j.client_id,a.name AS ai_identity,o.name AS endpoint_name "
            "FROM ai_jobs j "
            "LEFT JOIN ai_principals a ON a.id=j.principal_id "
            "LEFT JOIN objects o ON o.id=j.endpoint_object_id "
            "WHERE %s "
            "ORDER BY COALESCE(j.claimed_at,j.created_at) DESC,j.id DESC LIMIT ?"
            % " AND ".join(where),
            tuple(args),
        ).fetchall()
        has_more = len(rows) > page_limit
        page_rows = rows[:page_limit]
        observations = tuple(
            {
                "observation_kind": "AI_JOB",
                "observation_id": str(row["id"]),
                "job_id": str(row["id"]),
                "status": str(row["status"]).upper(),
                "capability": row["capability"],
                "ai_identity": row["ai_identity"],
                "managed_host_id": row["client_id"],
                "endpoint": row["endpoint_name"],
                "started_at": row["claimed_at"] or row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in page_rows
        )
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_live_cursor(
                family,
                str(last["claimed_at"] or last["created_at"] or ""),
                str(last["id"]),
            )
        return {
            "plane": "ai",
            "resource_type": resource_type,
            "resource": resource,
            "fidelity": FIDELITY_EXACT,
            "active_count": matching_count,
            "observations": list(observations),
            "next_cursor": next_cursor,
            "limit": page_limit,
            "reason": "",
        }
