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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from drlink_control_db import ControlPlaneError, connect_read_only
from drlink_control_plane import ControlPlane
from drlink_management_catalog import mcp_management_descriptors

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
_CURSOR_VERSION = 1
ATTENTION_DENY_WINDOW = timedelta(minutes=15)
ATTENTION_DENY_THRESHOLD = 3
ATTENTION_EXPIRY_WINDOW = timedelta(hours=24)
ATTENTION_AUDIT_BACKLOG_SECONDS = 300
HYGIENE_STALE_HOST_WINDOW = timedelta(days=7)
HYGIENE_ACCESS_REVIEW_WINDOW = timedelta(days=30)
HYGIENE_LONG_GRANT_WINDOW = timedelta(days=7)

# A catalog entry is not advertised merely because its name/schema is frozen.
# Only handlers implemented by this service may be projected by a future MCP
# adapter.
IMPLEMENTED_MANAGEMENT_TOOLS = frozenset(
    {
        "drlink_inventory_list",
        "drlink_inventory_get",
        "drlink_health",
        "drlink_access_hygiene",
        "drlink_diagnose_connection",
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
            "c.admission_state AS admission_state, "
            "c.admission_changed_at AS admission_changed_at, "
            "c.admission_actor AS admission_actor, "
            "c.connected AS connected, c.last_seen AS last_seen, "
            "c.agent_heartbeat_at AS agent_heartbeat_at, "
            "c.agent_lifecycle_state AS agent_lifecycle_state, "
            "c.agent_platform AS agent_platform, c.agent_version AS agent_version, "
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

    def capability_inventory(self) -> dict[str, Any]:
        """Return the machine-generated management parity inventory."""
        from drlink_v30_capability import capability_parity_ledger

        return capability_parity_ledger()

    def overview_summary(self) -> dict[str, Any]:
        """Return a rebuildable derived overview, never authoritative state."""
        from drlink_v30_readmodels import overview_summary

        return overview_summary(self.conn)

    def global_search(
        self, query: str, *, limit: Optional[int] = None
    ) -> dict[str, Any]:
        """Search bounded public management nouns without N-per-Host requests."""
        needle = str(query or "").strip()
        if not needle:
            raise ControlPlaneError("Search query is required.")
        if len(needle) > 128:
            raise ControlPlaneError("Search query is too long.")
        total_limit = max(1, min(int(limit or 40), 100))
        results: list[dict[str, Any]] = []
        per_type = max(1, min(8, total_limit))
        for kind in supported_inventory_types():
            if len(results) >= total_limit:
                break
            page = self.list_inventory(kind, query=needle, limit=per_type)
            for item in page.items:
                results.append({
                    "resource_type": kind,
                    "id": item.get("id"),
                    "name": item.get("name") or item.get("id"),
                    "item": dict(item),
                })
                if len(results) >= total_limit:
                    break
        if len(results) < total_limit:
            rows = self.conn.execute(
                "SELECT id,plane,name,enabled,expires_at,row_version "
                "FROM policy_rules WHERE LOWER(name) LIKE ? "
                "ORDER BY LOWER(name),id LIMIT ?",
                ("%%%s%%" % needle.lower(), total_limit - len(results)),
            ).fetchall()
            for row in rows:
                item = {key: row[key] for key in row.keys()}
                results.append({
                    "resource_type": "access-policy-rule",
                    "id": row["id"],
                    "name": row["name"],
                    "item": item,
                })
        return {"query": needle, "items": results, "limit": total_limit}

    def policy_list(
        self, *, plane: Optional[str] = None, limit: Optional[int] = None
    ) -> dict[str, Any]:
        """Return a bounded read view of Remote/Internet/AI policy rules."""
        page_limit = _bounded_limit(limit)
        family = str(plane or "").strip().lower()
        if family and family not in ("remote", "internet", "ai"):
            raise ControlPlaneError("Unsupported access plane: %s" % plane)
        items: list[dict[str, Any]] = []
        if family in ("", "remote", "internet"):
            where = " WHERE plane=?" if family in ("remote", "internet") else ""
            args: list[Any] = [family] if where else []
            args.append(page_limit)
            rows = self.conn.execute(
                "SELECT id,plane,name,position,action,enabled,description,"
                "expires_at,row_version FROM policy_rules" + where
                + " ORDER BY plane,position,id LIMIT ?",
                tuple(args),
            ).fetchall()
            items.extend({key: row[key] for key in row.keys()} for row in rows)
        if family in ("", "ai") and len(items) < page_limit:
            rows = self.conn.execute(
                "SELECT id,name,enabled,source_identity_id,destination_ref_kind,"
                "destination_ref_id,permission_ref_kind,permission_ref_id,"
                "description,expires_at,row_version FROM ai_policy_rules "
                "ORDER BY name COLLATE NOCASE,id LIMIT ?",
                (page_limit - len(items),),
            ).fetchall()
            for row in rows:
                item = {key: row[key] for key in row.keys()}
                item["plane"] = "ai"
                items.append(item)
        return {"items": items[:page_limit], "limit": page_limit, "plane": family or "all"}

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

    def revision_list(
        self, *, cursor: Optional[str] = None, limit: Optional[int] = None
    ) -> ManagementPage:
        """Return descending configuration revisions with bounded keyset pagination."""
        page_limit = _bounded_limit(limit)
        before: Optional[int] = None
        if cursor:
            text = str(cursor).strip()
            try:
                padded = text + "=" * (-len(text) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
                if payload.get("v") != _CURSOR_VERSION or payload.get("resource") != "revision":
                    raise ValueError("cursor mismatch")
                before = int(payload["revision"])
            except Exception as exc:
                raise ControlPlaneError("Invalid revision cursor.") from exc
        where = " WHERE revision < ?" if before is not None else ""
        args: list[Any] = [before] if before is not None else []
        args.append(page_limit + 1)
        rows = self.conn.execute(
            "SELECT revision,actor,command,created_at,summary FROM config_revisions"
            + where + " ORDER BY revision DESC LIMIT ?",
            tuple(args),
        ).fetchall()
        has_more = len(rows) > page_limit
        page_rows = rows[:page_limit]
        items = tuple({key: row[key] for key in row.keys()} for row in page_rows)
        next_cursor = None
        if has_more and page_rows:
            raw = json.dumps(
                {"v": _CURSOR_VERSION, "resource": "revision", "revision": int(page_rows[-1]["revision"])},
                separators=(",", ":"), sort_keys=True,
            ).encode("utf-8")
            next_cursor = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return ManagementPage("revision", items, next_cursor, page_limit)

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

    def inventory_snapshot(
        self,
        resource_types: tuple[str, ...],
        *,
        per_type_limit: int = 50,
    ) -> dict[str, Any]:
        """Return a fixed-number multi-resource snapshot in one browser request."""
        limit = max(1, min(int(per_type_limit), 100))
        resources: dict[str, Any] = {}
        for kind in resource_types:
            normalized = str(kind or "").strip().lower()
            if normalized not in _RESOURCE_SPECS:
                raise ControlPlaneError("Unsupported management resource type '%s'." % kind)
            resources[normalized] = self.list_inventory(
                normalized, limit=limit
            ).as_dict()
        return {"resources": resources, "per_type_limit": limit}

    def doctor_summary(self) -> dict[str, Any]:
        """Side-effect-free DRL3-2 health/Doctor read view."""
        health = self.health()
        attention = self.attention_summary()
        generations = self.conn.execute(
            "SELECT plane,db_revision,generation,status,activated_at,error "
            "FROM runtime_generations ORDER BY plane"
        ).fetchall()
        checks = []
        for row in generations:
            status = str(row["status"] or "unknown")
            checks.append(
                {
                    "id": "runtime.%s" % row["plane"],
                    "status": "PASS" if status in ("active", "not_configured") else "ATTENTION",
                    "message": "Runtime generation status: %s" % status,
                    "plane": row["plane"],
                    "db_revision": row["db_revision"],
                    "generation": row["generation"],
                    "activated_at": row["activated_at"],
                    "error": row["error"] or "",
                }
            )
        return {
            "read_only": True,
            "side_effect_free": True,
            "health": health,
            "attention": attention,
            "checks": checks,
        }

    def version_drift(self) -> dict[str, Any]:
        """Return Agent platform/version inventory relative to installed Server version."""
        root = Path(self.root) if self.root and str(self.root) not in ("", "/") else Path("/")
        server_version = ""
        try:
            for line in (root / "etc/drlink/version").read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == "PROJECT_VERSION":
                    server_version = value.strip()
                    break
        except OSError:
            pass
        rows = self.conn.execute(
            "SELECT id,COALESCE(NULLIF(label,''),NULLIF(hostname,''),id) AS name,"
            "COALESCE(NULLIF(agent_platform,''),'unknown') AS platform,"
            "COALESCE(NULLIF(agent_version,''),'unknown') AS version,"
            "agent_lifecycle_state AS lifecycle,agent_heartbeat_at AS heartbeat "
            "FROM clients ORDER BY LOWER(COALESCE(NULLIF(label,''),NULLIF(hostname,''),id)),id LIMIT 200"
        ).fetchall()
        hosts = []
        drift_count = 0
        unknown_count = 0
        for row in rows:
            version = str(row["version"])
            unknown = version == "unknown"
            drift = bool(server_version and not unknown and version != server_version)
            unknown_count += 1 if unknown else 0
            drift_count += 1 if drift else 0
            hosts.append({
                "id": row["id"], "name": row["name"], "platform": row["platform"],
                "version": version, "lifecycle": row["lifecycle"],
                "heartbeat": row["heartbeat"], "drift": drift, "unknown": unknown,
            })
        return {
            "server_version": server_version or "unknown", "hosts": hosts,
            "drift_count": drift_count, "unknown_count": unknown_count, "limit": 200,
        }

    def _diagnosis_managed_hosts(self, selector: str) -> list[dict[str, Any]]:
        text = str(selector or "").strip()
        if not text:
            return []
        core = ControlPlane(self.root, read_only=True)
        try:
            rows = []
            obj = core.get_object(text)
            members = []
            if obj is not None:
                members = [obj]
            else:
                group = core.get_object_group(text)
                if group is not None:
                    members = list(core._expand_group_members(str(group["id"]), set()))
            seen = set()
            for item in members:
                if str(item["type"]) != "managed_endpoint":
                    continue
                object_id = str(item["id"])
                endpoint = core.conn.execute(
                    "SELECT client_id FROM managed_endpoints WHERE object_id=?",
                    (object_id,),
                ).fetchone()
                client_id = str(endpoint["client_id"]) if endpoint and endpoint["client_id"] else ""
                if not client_id or client_id in seen:
                    continue
                client = core.conn.execute(
                    "SELECT id,label,hostname,status,trust_status,admission_state,"
                    "admission_changed_at,admission_actor,connected,last_seen,"
                    "agent_heartbeat_at,agent_lifecycle_state,agent_platform,agent_version "
                    "FROM clients WHERE id=?",
                    (client_id,),
                ).fetchone()
                if client is not None:
                    rows.append({key: client[key] for key in client.keys()})
                    seen.add(client_id)
            return rows[:100]
        finally:
            core.close()

    def active_cutoff_summary(self, *, plane: Optional[str] = None) -> dict[str, Any]:
        family = str(plane or "").strip().lower()
        if family and family not in ("remote", "internet", "ai"):
            raise ControlPlaneError("Unsupported access plane: %s" % plane)
        where = " WHERE active=1"
        args: list[Any] = []
        if family:
            where += " AND plane=?"
            args.append(family)
        count_row = self.conn.execute(
            "SELECT COUNT(*) FROM emergency_cutoffs" + where,
            tuple(args),
        ).fetchone()
        total = int(count_row[0] or 0)
        rows = self.conn.execute(
            "SELECT id,plane,scope_kind,scope_ref,reason,row_version,updated_at "
            "FROM emergency_cutoffs" + where
            + " ORDER BY plane,CASE scope_kind WHEN 'plane' THEN 0 ELSE 1 END,"
            "scope_kind,scope_ref LIMIT 200",
            tuple(args),
        ).fetchall()
        items = [{key: row[key] for key in row.keys()} for row in rows]
        return {
            "items": items,
            "count": total,
            "returned": len(items),
            "plane": family or "all",
            "active": total > 0,
            "limit": 200,
            "truncated": total > len(items),
        }

    def connection_diagnosis(
        self,
        *,
        plane: str,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        service: Optional[str] = None,
        permission: Optional[str] = None,
        path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Correlate bounded Core facts without probes or authoritative mutation."""
        family = str(plane or "").strip().lower()
        if family not in ("remote", "internet", "ai"):
            raise ControlPlaneError("Unsupported access plane: %s" % plane)
        source_text = str(source or "").strip()
        destination_text = str(destination or "").strip()
        selector_text = str(permission if family == "ai" else service or "").strip()
        layers: list[dict[str, Any]] = []

        def add(layer: str, status: str, summary: str, **evidence: Any) -> None:
            item = {"layer": layer, "status": status, "summary": summary}
            if evidence:
                item["evidence"] = evidence
            layers.append(item)

        missing = []
        if not source_text:
            missing.append("source")
        if not destination_text:
            missing.append("destination")
        if not selector_text:
            missing.append("permission" if family == "ai" else "service")
        if missing:
            add(
                "input",
                "FAILED",
                "Diagnosis input is incomplete.",
                missing=missing,
            )
        else:
            add("input", "HEALTHY", "Required flow selectors are present.")

        policy_trace = None
        if not missing:
            def no_live_dns(hostname: str):
                raise RuntimeError(
                    "live DNS is not performed by Connection Diagnosis for %s" % hostname
                )

            core = ControlPlane(self.root, read_only=True)
            try:
                from drlink_policy_safety import evaluate_policy_flow

                try:
                    policy_trace = evaluate_policy_flow(
                        core,
                        plane=family,
                        source=source_text,
                        destination=destination_text,
                        service=str(service or ""),
                        permission=str(permission or ""),
                        path=str(path or ""),
                        resolve_fn=no_live_dns if family == "internet" else None,
                    )
                    result = str(policy_trace.get("final", {}).get("result") or "DENY")
                    path_context_missing = bool(
                        family == "ai"
                        and policy_trace.get("path_required")
                        and not str(path or "").strip()
                    )
                    if path_context_missing:
                        add(
                            "policy",
                            "UNKNOWN",
                            "AI file permission requires concrete path context; runtime remains fail-closed without it.",
                            trace=policy_trace,
                        )
                    else:
                        add(
                            "policy",
                            "HEALTHY" if result == "ALLOW" else "FAILED",
                            "Core policy result is %s." % result,
                            trace=policy_trace,
                        )
                except Exception as exc:
                    message = str(exc)
                    status = "UNKNOWN" if "live DNS is not performed" in message else "FAILED"
                    add("policy", status, message)
            finally:
                core.close()
        else:
            add("policy", "N_A", "Policy evaluation requires complete flow selectors.")

        host_selector = destination_text if family in ("remote", "ai") else source_text
        hosts = self._diagnosis_managed_hosts(host_selector)
        if not host_selector:
            add("managed_host", "N_A", "No Managed Host selector is available.")
        elif not hosts:
            add(
                "managed_host",
                "N_A",
                "The selected flow does not resolve to a Managed Host in current inventory.",
            )
        else:
            connected = sum(1 for item in hosts if bool(item.get("connected")))
            trusted = sum(
                1 for item in hosts if str(item.get("trust_status") or "").lower() == "trusted"
            )
            if connected == len(hosts) and trusted == len(hosts):
                status = "HEALTHY"
                summary = "All selected Managed Hosts are connected and trusted."
            elif connected == 0:
                status = "FAILED"
                summary = "Selected Managed Host is not connected."
            else:
                status = "UNKNOWN"
                summary = "Managed Host group has mixed connection/trust state."
            add(
                "managed_host",
                status,
                summary,
                count=len(hosts),
                connected=connected,
                trusted=trusted,
                hosts=hosts[:20],
            )

        remote_service = None
        if family == "remote":
            if len(hosts) == 1:
                client_id = str(hosts[0]["id"])
                candidates = self.conn.execute(
                    "SELECT s.id,s.name,s.service_type,s.target_host,s.target_port,"
                    "s.public_port,s.enabled,s.released,m.status AS runtime_status,"
                    "m.pending_allocation,m.reason AS runtime_reason,m.runtime_verified "
                    "FROM published_services s "
                    "LEFT JOIN remote_service_meta m ON m.service_id=s.id "
                    "WHERE s.client_id=? AND s.released=0 "
                    "ORDER BY s.name COLLATE NOCASE LIMIT 50",
                    (client_id,),
                ).fetchall()
                direct = [
                    row for row in candidates
                    if str(row["name"]).casefold() == selector_text.casefold()
                    or str(row["id"]).casefold() == selector_text.casefold()
                ]
                if len(direct) == 1:
                    remote_service = direct[0]
                if remote_service is None:
                    svc = self.conn.execute(
                        "SELECT type,port FROM service_objects WHERE name=? COLLATE NOCASE",
                        (selector_text,),
                    ).fetchone()
                    if svc is not None:
                        by_port = [
                            row for row in candidates
                            if int(row["target_port"]) == int(svc["port"])
                        ]
                        if len(by_port) == 1:
                            remote_service = by_port[0]
            if remote_service is None:
                add(
                    "remote_service",
                    "UNKNOWN",
                    "No unique published Remote Service could be correlated to this flow.",
                )
            else:
                row = remote_service
                enabled = bool(row["enabled"]) and not bool(row["released"])
                runtime_status = str(row["runtime_status"] or "").upper()
                runtime_verified = bool(row["runtime_verified"])
                pending_allocation = bool(row["pending_allocation"])
                runtime_reason = str(row["runtime_reason"] or "")
                if not enabled:
                    state = "FAILED"
                    summary = "Remote Service is disabled or released."
                elif runtime_status == "HEALTHY" and runtime_verified and not pending_allocation:
                    state = "HEALTHY"
                    summary = "Remote Service runtime is verified HEALTHY."
                elif runtime_status in ("DEGRADED", "DISABLED"):
                    state = "FAILED"
                    summary = runtime_reason or (
                        "Remote Service runtime is %s." % runtime_status
                    )
                else:
                    state = "UNKNOWN"
                    summary = (
                        runtime_reason
                        or "Remote Service runtime verification is unavailable or pending."
                    )
                add(
                    "remote_service",
                    state,
                    summary,
                    id=row["id"],
                    name=row["name"],
                    public_port=row["public_port"],
                    target_host=row["target_host"],
                    target_port=row["target_port"],
                    runtime_status=runtime_status or "UNKNOWN",
                    runtime_verified=runtime_verified,
                    pending_allocation=pending_allocation,
                    reason=runtime_reason,
                )
        else:
            add("remote_service", "N_A", "Remote Service correlation applies only to Remote Access.")

        runtime = self.conn.execute(
            "SELECT plane,db_revision,generation,status,activated_at,error "
            "FROM runtime_generations WHERE plane=?",
            (family,),
        ).fetchone()
        if runtime is None:
            add("runtime", "UNKNOWN", "No runtime-generation evidence is available.")
        else:
            runtime_status = str(runtime["status"] or "unknown").lower()
            state = "HEALTHY" if runtime_status == "active" else (
                "N_A" if runtime_status == "not_configured" else "FAILED"
            )
            add(
                "runtime",
                state,
                "Runtime generation status is %s." % runtime_status,
                runtime_status=runtime_status,
                db_revision=runtime["db_revision"],
                generation=runtime["generation"],
                activated_at=runtime["activated_at"],
                error=runtime["error"] or "",
            )

        if family == "internet":
            dest_obj = self.conn.execute(
                "SELECT type FROM objects WHERE name=? COLLATE NOCASE",
                (destination_text,),
            ).fetchone()
            if dest_obj is not None and str(dest_obj["type"]) in ("ip", "cidr"):
                add("dns", "N_A", "Destination is IP/CIDR based; DNS is not required.")
            else:
                add(
                    "dns",
                    "UNKNOWN",
                    "No live DNS probe was launched; DNS/path validation is unknown unless already captured by access evidence.",
                )
        else:
            add("dns", "N_A", "DNS destination validation is not applicable to this access plane.")

        if family == "remote":
            if remote_service is None:
                add(
                    "target_reachability",
                    "UNKNOWN",
                    "No unique Remote Service was correlated, so target health cannot be determined.",
                )
            else:
                rs_status = str(remote_service["runtime_status"] or "").upper()
                rs_verified = bool(remote_service["runtime_verified"])
                rs_reason = str(remote_service["runtime_reason"] or "")
                if rs_status == "HEALTHY" and rs_verified:
                    add(
                        "target_reachability",
                        "HEALTHY",
                        "Agent runtime verification reports the Remote Service target path HEALTHY.",
                        reason=rs_reason,
                    )
                elif rs_status == "DEGRADED":
                    add(
                        "target_reachability",
                        "FAILED",
                        rs_reason or "Agent/runtime evidence reports the Remote Service target path DEGRADED.",
                        reason=rs_reason,
                    )
                else:
                    add(
                        "target_reachability",
                        "UNKNOWN",
                        "No verified target-health result is available; Connection Diagnosis does not launch an ad-hoc probe.",
                        reason=rs_reason,
                    )
        else:
            add("target_reachability", "N_A", "Target reachability probe is not applicable here.")

        active = self.active_cutoff_summary(plane=family)
        relevant = []
        for cutoff in active["items"]:
            kind = str(cutoff["scope_kind"])
            ref = str(cutoff["scope_ref"] or "")
            if kind == "plane":
                relevant.append(cutoff)
            elif family == "internet" and kind == "managed-host":
                if any(str(host["id"]).casefold() == ref.casefold() for host in hosts):
                    relevant.append(cutoff)
            elif family == "ai" and kind == "ai-identity":
                if source_text.casefold() == ref.casefold():
                    relevant.append(cutoff)
            elif family == "remote" and kind == "remote-service" and remote_service is not None:
                if str(remote_service["id"]).casefold() == ref.casefold():
                    relevant.append(cutoff)
        add(
            "emergency_cutoff",
            "FAILED" if relevant else "HEALTHY",
            (
                "Emergency New-Access Cutoff blocks this flow."
                if relevant
                else "No active Emergency New-Access Cutoff is known to block this flow."
            ),
            matching=relevant,
            active_plane_count=active["count"],
            active_sessions_terminated=False,
        )

        sources = {
            "remote": ("remote-access",),
            "internet": ("internet-access",),
            "ai": ("ai-mcp",),
        }[family]
        placeholders = ",".join("?" for _ in sources)
        audit_rows = self.conn.execute(
            "SELECT id,event_id,event_type,occurred_at,source,result,reason_code,"
            "matched_policy_json,source_meta_json,destination_meta_json "
            "FROM audit_events WHERE category='ACCESS_DECISION' "
            "AND source IN (%s) ORDER BY occurred_at DESC,id DESC LIMIT 20" % placeholders,
            tuple(sources),
        ).fetchall()
        evidence = []
        needles = {source_text.casefold(), destination_text.casefold(), selector_text.casefold()}
        needles.discard("")
        for row in audit_rows:
            meta_text = " ".join(
                str(row[key] or "") for key in ("source_meta_json", "destination_meta_json")
            ).casefold()
            if needles and not any(needle in meta_text for needle in needles):
                continue
            evidence.append(
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "occurred_at": row["occurred_at"],
                    "result": row["result"],
                    "reason_code": row["reason_code"],
                    "matched_policy": _json_field(row["matched_policy_json"], []),
                    "source_meta": _json_field(row["source_meta_json"], {}),
                    "destination_meta": _json_field(row["destination_meta_json"], {}),
                }
            )
            if len(evidence) >= 5:
                break
        if evidence:
            add(
                "recent_activity",
                "HEALTHY",
                "Recent bounded access-decision evidence reached the Data Relay Link data path.",
                events=evidence,
            )
        else:
            add(
                "recent_activity",
                "UNKNOWN",
                "No matching recent access-decision evidence proves the attempt reached the Data Relay Link data path.",
                events=[],
            )

        failed = [item for item in layers if item["status"] == "FAILED"]
        unknown = [item for item in layers if item["status"] == "UNKNOWN"]
        overall = "FAILED" if failed else ("UNKNOWN" if unknown else "HEALTHY")
        first = failed[0] if failed else (unknown[0] if unknown else None)
        if first is None:
            next_action = "No failing layer is currently proven."
        elif first["status"] == "FAILED":
            next_action = "Investigate the first failed layer: %s." % first["layer"]
        else:
            next_action = "Collect evidence for the first unknown layer: %s." % first["layer"]
        return {
            "plane": family,
            "input": {
                "source": source_text,
                "destination": destination_text,
                "service": str(service or ""),
                "permission": str(permission or ""),
                "path": str(path or ""),
            },
            "overall": overall,
            "layers": layers,
            "next_action": next_action,
            "side_effect_free": True,
            "network_probe_performed": False,
            "policy_trace": policy_trace,
        }

    @staticmethod
    def _attention_utc_text(value: datetime) -> str:
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )

    def _remote_service_attention(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT COUNT(*) AS degraded FROM published_services s "
            "JOIN remote_service_meta m ON m.service_id=s.id "
            "WHERE s.released=0 AND UPPER(COALESCE(m.status,''))='DEGRADED'"
        ).fetchone()
        return {"degraded": int(row["degraded"] or 0)}

    def _runtime_attention(self) -> dict[str, Any]:
        core = ControlPlane(self.root, read_only=True)
        try:
            current_revision = int(core.current_revision())
        finally:
            core.close()
        rows = self.conn.execute(
            "SELECT plane,db_revision,generation,status,error FROM runtime_generations "
            "ORDER BY plane"
        ).fetchall()
        mismatches = []
        failures = []
        for row in rows:
            status = str(row["status"] or "unknown").lower()
            item = {
                "plane": str(row["plane"]),
                "db_revision": row["db_revision"],
                "generation": row["generation"],
                "status": status,
                "error": str(row["error"] or ""),
            }
            if status in ("failed", "mismatch"):
                failures.append(item)
                continue
            if (
                status == "active"
                and row["generation"] is not None
                and int(row["generation"]) != current_revision
            ):
                mismatches.append(item)
        return {
            "current_revision": current_revision,
            "mismatches": mismatches,
            "failures": failures,
            "count": len(mismatches) + len(failures),
        }

    def _deny_attention(self, *, now: datetime) -> dict[str, Any]:
        since = self._attention_utc_text(now - ATTENTION_DENY_WINDOW)
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM audit_events "
            "WHERE category='ACCESS_DECISION' AND UPPER(COALESCE(result,''))='DENY' "
            "AND occurred_at>=?",
            (since,),
        ).fetchone()
        count = int(row["n"] or 0)
        return {
            "count": count,
            "since": since,
            "threshold": ATTENTION_DENY_THRESHOLD,
            "repeated": count >= ATTENTION_DENY_THRESHOLD,
        }

    @staticmethod
    def _parse_attention_timestamp(value: str) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)

    def _temporary_access_attention(self, *, now: datetime) -> dict[str, Any]:
        from drlink_v30_temporal import ACTIVE, CLOCK_UNTRUSTED, temporary_access_state

        rows = list(
            self.conn.execute(
                "SELECT plane,name,expires_at,created_at FROM policy_rules "
                "WHERE enabled=1 AND expires_at IS NOT NULL AND expires_at<>''"
            )
        )
        rows.extend(
            self.conn.execute(
                "SELECT 'ai' AS plane,name,expires_at,created_at FROM ai_policy_rules "
                "WHERE enabled=1 AND expires_at IS NOT NULL AND expires_at<>''"
            )
        )
        expiring = []
        clock_untrusted = []
        horizon = now + ATTENTION_EXPIRY_WINDOW
        for row in rows:
            state = temporary_access_state(
                row["expires_at"],
                created_at=row["created_at"],
                now=now,
            )
            item = {
                "plane": str(row["plane"]),
                "name": str(row["name"]),
                "expires_at": state.expires_at,
                "status": state.status,
            }
            if state.status == CLOCK_UNTRUSTED:
                clock_untrusted.append(item)
                continue
            expiry = self._parse_attention_timestamp(str(state.expires_at or ""))
            if state.status == ACTIVE and expiry is not None and expiry <= horizon:
                expiring.append(item)
        return {
            "expiring": expiring[:100],
            "expiring_count": len(expiring),
            "clock_untrusted": clock_untrusted[:100],
            "clock_untrusted_count": len(clock_untrusted),
            "window_hours": int(ATTENTION_EXPIRY_WINDOW.total_seconds() // 3600),
        }

    def _audit_spool_attention(self) -> dict[str, Any]:
        from drlink_v30_audit import DurableAuditSpool, default_access_spool_root

        health = []
        degraded = []
        for plane, source in (
            ("remote", "remote-access"),
            ("internet", "internet-access"),
        ):
            spool = DurableAuditSpool(
                default_access_spool_root(plane, self.root),
                source,
                create=False,
            )
            one = dict(spool.health())
            one["plane"] = plane
            health.append(one)
            unhealthy = bool(
                one.get("high_water")
                or int(one.get("enqueue_failures") or 0) > 0
                or int(one.get("dropped_deny_count") or 0) > 0
                or (
                    int(one.get("segment_count") or 0) > 0
                    and int(one.get("oldest_segment_age_seconds") or 0)
                    >= ATTENTION_AUDIT_BACKLOG_SECONDS
                )
            )
            if unhealthy:
                degraded.append(one)
        return {
            "items": health,
            "degraded": degraded,
            "degraded_count": len(degraded),
            "backlog_seconds": ATTENTION_AUDIT_BACKLOG_SECONDS,
        }

    def _system_readiness_attention(self) -> dict[str, Any]:
        from drlink_management_system import ManagementSystemService

        try:
            status = ManagementSystemService(self.root).status()
        except Exception as exc:
            return {
                "certificate_problem": False,
                "backup_problem": False,
                "update_problem": False,
                "error": str(exc)[:512],
            }
        certificate = dict(status.get("certificate") or {})
        cert_state = str(certificate.get("certificate") or "").upper()
        configured = (
            str(certificate.get("mode") or "").lower() != "not configured"
            or str(certificate.get("hostname") or "").lower() != "not configured"
        )
        certificate_problem = bool(
            cert_state
            in {
                "RENEWAL_DUE",
                "RENEWAL_FAILED_USING_CURRENT_CERT",
                "EXPIRED",
                "INVALID",
                "PENDING_ISSUANCE",
            }
            or (configured and cert_state == "ABSENT")
            or certificate.get("last_failure_class")
        )
        backup = dict(status.get("backup") or {})
        backup_problem = not bool(
            backup.get("create_available") and backup.get("validate_available")
        )
        update = dict(status.get("update") or {})
        update_problem = not bool(
            update.get("product_check_available") and update.get("engine_check_available")
        )
        return {
            "certificate_problem": certificate_problem,
            "certificate": certificate,
            "backup_problem": backup_problem,
            "backup": backup,
            "update_problem": update_problem,
            "update": update,
            "error": "",
        }

    def access_hygiene(self, *, now: Optional[datetime] = None) -> dict[str, Any]:
        """Return read-only evidence-backed hygiene recommendations."""
        current = now or datetime.now(timezone.utc)
        stale_before = self._attention_utc_text(current - HYGIENE_STALE_HOST_WINDOW)
        access_since = self._attention_utc_text(current - HYGIENE_ACCESS_REVIEW_WINDOW)
        findings: list[dict[str, Any]] = []
        for row in self.conn.execute(
            "SELECT id,COALESCE(NULLIF(label,''),NULLIF(hostname,''),id) AS name,last_seen "
            "FROM clients WHERE last_seen IS NULL OR last_seen<? ORDER BY id LIMIT 100",
            (stale_before,),
        ):
            findings.append({
                "kind": "stale-host", "resource_type": "managed-host",
                "resource_id": str(row["id"]), "label": str(row["name"]),
                "evidence_quality": "OBSERVED" if row["last_seen"] else "UNKNOWN_EVIDENCE",
                "finding_status": "STALE_OR_UNUSED" if row["last_seen"] else "UNKNOWN_EVIDENCE",
                "severity": "warning" if row["last_seen"] else "info",
                "observation_window_days": int(HYGIENE_STALE_HOST_WINDOW.days),
                "evidence": {"last_seen": row["last_seen"]},
                "recommendation": "Review host lifecycle and connectivity; no automatic mutation is performed.",
            })
        audit_row = self.conn.execute(
            "SELECT MIN(occurred_at) AS oldest,COUNT(*) AS n FROM audit_events "
            "WHERE category='ACCESS_DECISION' AND occurred_at>=?", (access_since,)
        ).fetchone()
        # Event count alone never proves an absence of successful access.
        for table, plane in (("policy_rules", "remote/internet"), ("ai_policy_rules", "ai")):
            rows = self.conn.execute(
                "SELECT id,name,expires_at,created_at FROM %s WHERE enabled=1 ORDER BY id LIMIT 100" % table
            ).fetchall()
            for row in rows:
                expiry = self._parse_attention_timestamp(str(row["expires_at"] or ""))
                created = self._parse_attention_timestamp(str(row["created_at"] or ""))
                if expiry and created and expiry - created >= HYGIENE_LONG_GRANT_WINDOW:
                    findings.append({
                        "kind": "long-lived-grant", "resource_type": "access-rule",
                        "resource_id": str(row["id"]), "label": str(row["name"]),
                        "plane": plane, "evidence_quality": "OBSERVED",
                        "finding_status": "ACTION_REQUIRED", "severity": "warning",
                        "observation_window_days": int(HYGIENE_ACCESS_REVIEW_WINDOW.days),
                        "evidence": {"created_at": row["created_at"], "expires_at": row["expires_at"]},
                        "recommendation": "Review whether this grant still needs its current duration.",
                    })
                else:
                    # Even some ACCESS_DECISION rows cannot prove complete per-rule
                    # success/failure visibility for the entire review window.
                    # Therefore never assert an unused rule without stronger evidence.
                    findings.append({
                        "kind": "access-usage-review", "resource_type": "access-rule",
                        "resource_id": str(row["id"]), "label": str(row["name"]),
                        "plane": plane, "evidence_quality": "UNKNOWN_EVIDENCE",
                        "finding_status": "UNKNOWN_EVIDENCE", "severity": "info",
                        "observation_window_days": int(HYGIENE_ACCESS_REVIEW_WINDOW.days),
                        "evidence": {
                            "access_decision_events": int(audit_row["n"] or 0) if audit_row else 0,
                            "oldest_observed_at": audit_row["oldest"] if audit_row else None,
                            "complete_per_rule_coverage": False,
                        },
                        "recommendation": "Retain the rule until sufficient usage evidence exists; do not infer unused access.",
                    })
        return {
            "items": findings[:200], "count": len(findings), "authoritative": False,
            "read_only": True, "auto_mutation": False,
            "generated_at": self._attention_utc_text(current),
        }

    def _webhook_delivery_attention(self) -> dict[str, int]:
        """Read-only delivery degradation; absent optional tables are normal."""
        table = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='management_webhook_outbox'"
        ).fetchone()
        if not table:
            return {"pending": 0, "failed": 0, "stale_lease": 0}
        stale_before = self._attention_utc_text(
            datetime.now(timezone.utc) - timedelta(seconds=90)
        )
        row = self.conn.execute(
            "SELECT "
            "COALESCE(SUM(CASE WHEN o.status='PENDING' THEN 1 ELSE 0 END),0) AS pending,"
            "COALESCE(SUM(CASE WHEN o.status='FAILED' THEN 1 ELSE 0 END),0) AS failed,"
            "COALESCE(SUM(CASE WHEN o.status='SENDING' "
            "AND o.last_attempt_at<? THEN 1 ELSE 0 END),0) AS stale_lease "
            "FROM management_webhook_outbox o JOIN management_webhooks w "
            "ON w.id=o.webhook_id WHERE w.enabled=1",
            (stale_before,),
        ).fetchone()
        return {
            "pending": int(row["pending"] or 0),
            "failed": int(row["failed"] or 0),
            "stale_lease": int(row["stale_lease"] or 0),
        }

    def attention_summary(self) -> dict[str, Any]:
        """Return bounded derived operator attention without becoming authority."""
        overview = self.overview_summary()
        hosts = overview.get("managed_hosts") or {}
        jobs = overview.get("management_jobs") or {}
        version = self.version_drift()
        now = datetime.now(timezone.utc)
        remote_services = self._remote_service_attention()
        runtime = self._runtime_attention()
        denies = self._deny_attention(now=now)
        temporary = self._temporary_access_attention(now=now)
        audit_spool = self._audit_spool_attention()
        webhook_delivery = self._webhook_delivery_attention()
        system = self._system_readiness_attention()
        cutoffs = self.active_cutoff_summary()

        items: list[dict[str, Any]] = []
        for key, label, severity in (
            ("disconnected", "Disconnected Managed Hosts", "warning"),
            ("stale", "Stale Managed Hosts", "warning"),
            ("version_unknown", "Unknown Agent Versions", "info"),
        ):
            count = int(hosts.get(key) or 0)
            if count:
                items.append({"kind": key, "label": label, "count": count, "severity": severity})
        if int(remote_services.get("degraded") or 0):
            items.append({
                "kind": "degraded-remote-services",
                "label": "DEGRADED Remote Services",
                "count": int(remote_services["degraded"]),
                "severity": "warning",
            })
        if int(runtime.get("count") or 0):
            items.append({
                "kind": "runtime-mismatch",
                "label": "Policy / Runtime Revision or Activation Problem",
                "count": int(runtime["count"]),
                "severity": "critical" if runtime.get("failures") else "warning",
            })
        if bool(denies.get("repeated")):
            items.append({
                "kind": "repeated-policy-denies",
                "label": "Repeated Policy Denies",
                "count": int(denies["count"]),
                "severity": "warning",
            })
        if version["drift_count"]:
            items.append({
                "kind": "version-drift",
                "label": "Agent Version Drift",
                "count": int(version["drift_count"]),
                "severity": "warning",
            })
        if int(temporary.get("clock_untrusted_count") or 0):
            items.append({
                "kind": "temporary-access-clock",
                "label": "Temporary Access Clock Trust Problem",
                "count": int(temporary["clock_untrusted_count"]),
                "severity": "critical",
            })
        if int(temporary.get("expiring_count") or 0):
            items.append({
                "kind": "temporary-access-expiring",
                "label": "Temporary Access Nearing Expiry",
                "count": int(temporary["expiring_count"]),
                "severity": "warning",
            })
        if webhook_delivery["failed"] or webhook_delivery["stale_lease"]:
            items.append({
                "kind": "webhook-delivery",
                "label": "Signed Webhook Delivery Degraded",
                "count": webhook_delivery["failed"] + webhook_delivery["stale_lease"],
                "severity": "warning",
            })
        if webhook_delivery["pending"] >= 800:
            items.append({
                "kind": "webhook-backlog",
                "label": "Signed Webhook Outbox Near Capacity",
                "count": webhook_delivery["pending"],
                "severity": "warning",
            })
        if int(audit_spool.get("degraded_count") or 0):
            items.append({
                "kind": "audit-spool",
                "label": "Audit Spool / High-Water Degradation",
                "count": int(audit_spool["degraded_count"]),
                "severity": "critical",
            })
        if bool(system.get("certificate_problem")):
            items.append({
                "kind": "certificate-readiness",
                "label": "Certificate / TLS Readiness",
                "count": 1,
                "severity": "warning",
            })
        if bool(system.get("backup_problem")):
            items.append({
                "kind": "backup-readiness",
                "label": "Backup / Restore Readiness",
                "count": 1,
                "severity": "warning",
            })
        if bool(system.get("update_problem")):
            items.append({
                "kind": "update-readiness",
                "label": "Update / Provenance Readiness",
                "count": 1,
                "severity": "warning",
            })
        if system.get("error"):
            items.append({
                "kind": "system-readiness",
                "label": "System Readiness Check Unavailable",
                "count": 1,
                "severity": "warning",
            })
        if int(jobs.get("failed_jobs") or 0):
            items.append({
                "kind": "failed-jobs",
                "label": "Failed Management Jobs",
                "count": int(jobs["failed_jobs"]),
                "severity": "warning",
            })
        if bool(jobs.get("saturated")):
            items.append({
                "kind": "job-saturation",
                "label": "Management Job Queue Saturated",
                "count": int(jobs.get("active_jobs") or 0),
                "severity": "critical",
            })
        if int(cutoffs.get("count") or 0):
            items.append({
                "kind": "emergency-cutoff",
                "label": "Emergency New-Access Cutoff Active",
                "count": int(cutoffs["count"]),
                "severity": "critical",
            })
        return {
            "items": items,
            "count": len(items),
            "authoritative": False,
            "generated_at": self._attention_utc_text(now),
            "signals": {
                "remote_services": remote_services,
                "runtime": runtime,
                "denies": denies,
                "temporary_access": temporary,
                "audit_spool": audit_spool,
                "webhook_delivery": webhook_delivery,
                "system_readiness": system,
                "cutoffs": cutoffs,
                "jobs": dict(jobs),
                "version": {
                    "drift_count": int(version.get("drift_count") or 0),
                    "unknown_count": int(version.get("unknown_count") or 0),
                },
            },
        }

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

    def resolve_management_job_targets(
        self,
        *,
        resource_type: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> dict[str, Any]:
        """Resolve a bounded immutable Managed Host target set for safe Jobs."""
        from drlink_v30_jobs import MAX_JOB_TARGETS

        kind = str(resource_type or "managed-host").strip().lower()
        selector = str(resource or "").strip()
        if kind not in ("managed-host", "managed-host-group"):
            raise ControlPlaneError(
                "Diagnostic Job resource_type must be managed-host or managed-host-group."
            )

        if kind == "managed-host":
            if selector:
                core = ControlPlane(self.root, read_only=True)
                try:
                    row = core.require_client(selector)
                    if str(row["trust_status"] or "").strip().lower() != "trusted":
                        raise ControlPlaneError(
                            "Diagnostic Job target Managed Host is not trusted."
                        )
                    targets = [str(row["id"])]
                    display = str(row["label"] or row["hostname"] or row["id"])
                finally:
                    core.close()
                return {
                    "targets": targets,
                    "target_count": 1,
                    "resource_type": kind,
                    "resource_ref": targets[0],
                    "resource_display": display,
                }

            rows = self.conn.execute(
                "SELECT id,label,hostname FROM clients "
                "WHERE LOWER(COALESCE(trust_status,''))='trusted' "
                "ORDER BY LOWER(COALESCE(NULLIF(label,''),NULLIF(hostname,''),id)),id "
                "LIMIT ?",
                (MAX_JOB_TARGETS + 1,),
            ).fetchall()
            if len(rows) > MAX_JOB_TARGETS:
                raise ControlPlaneError(
                    "Diagnostic Job target selection exceeds the %d-Host bound."
                    % MAX_JOB_TARGETS
                )
            if not rows:
                raise ControlPlaneError("No trusted Managed Hosts are available.")
            return {
                "targets": [str(row["id"]) for row in rows],
                "target_count": len(rows),
                "resource_type": kind,
                "resource_ref": "all",
                "resource_display": "All trusted Managed Hosts",
            }

        if not selector:
            raise ControlPlaneError("managed-host-group Diagnostic Job requires resource.")
        groups = self.conn.execute(
            "SELECT id,name FROM client_groups "
            "WHERE id=? OR name=? COLLATE NOCASE ORDER BY id LIMIT 3",
            (selector, selector),
        ).fetchall()
        if not groups:
            raise ControlPlaneError("Managed Host Group '%s' was not found." % selector)
        if len(groups) > 1:
            raise ControlPlaneError(
                "Managed Host Group selector '%s' is ambiguous; use its immutable ID."
                % selector
            )
        group = groups[0]
        rows = self.conn.execute(
            "SELECT c.id,c.label,c.hostname FROM client_group_members m "
            "JOIN clients c ON c.id=m.client_id "
            "WHERE m.group_id=? AND LOWER(COALESCE(c.trust_status,''))='trusted' "
            "ORDER BY LOWER(COALESCE(NULLIF(c.label,''),NULLIF(c.hostname,''),c.id)),c.id "
            "LIMIT ?",
            (group["id"], MAX_JOB_TARGETS + 1),
        ).fetchall()
        if len(rows) > MAX_JOB_TARGETS:
            raise ControlPlaneError(
                "Managed Host Group exceeds the %d-Host Job bound." % MAX_JOB_TARGETS
            )
        if not rows:
            raise ControlPlaneError(
                "Managed Host Group '%s' has no trusted members." % group["name"]
            )
        return {
            "targets": [str(row["id"]) for row in rows],
            "target_count": len(rows),
            "resource_type": kind,
            "resource_ref": str(group["id"]),
            "resource_display": str(group["name"]),
        }

    def _reconcile_management_job_deadlines(self) -> None:
        from drlink_v30_jobs import ManagementJobEngine

        engine = ManagementJobEngine(self.root)
        try:
            engine.expire_deadlines()
            engine.recover_expired_claims()
        finally:
            engine.close()

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

        self._reconcile_management_job_deadlines()
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

        self._reconcile_management_job_deadlines()
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
