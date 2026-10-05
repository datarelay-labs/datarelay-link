"""DRLink 3.0 policy safety: Decision Trace and saved regression tests."""
from __future__ import annotations

import json
import secrets
from typing import Any, Optional

from drlink_control_db import ControlPlaneError, utc_now_iso
from drlink_control_plane import ConcurrencyError, ControlPlane
from drlink_management_change import CONFIRM_CHANGE, ManagementChangeService

CONFIRM_DELETE_TEST = "DELETE TEST"
MAX_POLICY_TESTS = 200
MAX_POLICY_TEST_NAME = 128
MAX_SELECTOR = 256


def _text(value: Any, field: str, *, max_len: int = MAX_SELECTOR, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ControlPlaneError("%s is required." % field)
    if len(text) > max_len:
        raise ControlPlaneError("%s is too long." % field)
    return text


def _bool(value: Any, field: str, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    raise ControlPlaneError("%s must be a boolean." % field)


def normalize_policy_test(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ControlPlaneError("Policy Regression Test must be an object.")
    allowed = {
        "name",
        "plane",
        "source",
        "destination",
        "service",
        "permission",
        "path",
        "expected",
        "required",
        "enabled",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ControlPlaneError(
            "Policy Regression Test has unsupported fields: %s."
            % ", ".join(unknown)
        )
    name = _text(data.get("name"), "Policy Regression Test name", max_len=MAX_POLICY_TEST_NAME)
    plane = _text(data.get("plane"), "plane", max_len=16).lower()
    if plane not in ("remote", "internet", "ai"):
        raise ControlPlaneError("Policy Regression Test plane must be remote, internet, or ai.")
    source = _text(data.get("source"), "source")
    destination = _text(data.get("destination"), "destination")
    expected = _text(data.get("expected"), "expected", max_len=8).upper()
    if expected not in ("ALLOW", "DENY"):
        raise ControlPlaneError("Policy Regression Test expected must be ALLOW or DENY.")
    service = _text(data.get("service"), "service", required=False)
    permission = _text(data.get("permission"), "permission", required=False)
    path = _text(data.get("path"), "path", max_len=1024, required=False)
    if plane in ("remote", "internet"):
        if not service:
            raise ControlPlaneError("%s Policy Regression Test requires service." % plane)
        if permission or path:
            raise ControlPlaneError(
                "%s Policy Regression Test does not accept permission/path." % plane
            )
    else:
        if not permission:
            raise ControlPlaneError("AI Policy Regression Test requires permission.")
        if service:
            raise ControlPlaneError("AI Policy Regression Test does not accept service.")
    return {
        "name": name,
        "plane": plane,
        "source": source,
        "destination": destination,
        "service": service,
        "permission": permission,
        "path": path,
        "expected": expected,
        "required": _bool(data.get("required"), "required", True),
        "enabled": _bool(data.get("enabled"), "enabled", True),
    }


def _decision(result: dict[str, Any]) -> str:
    token = str(
        result.get("result")
        or result.get("decision")
        or result.get("action")
        or "DENY"
    ).strip().upper()
    if token in ("ALLOW", "ALLOWED", "PERMIT"):
        return "ALLOW"
    return "DENY"


def evaluate_policy_flow(
    plane_db: ControlPlane,
    *,
    plane: str,
    source: str,
    destination: str,
    service: str = "",
    permission: str = "",
    path: str = "",
    resolve_fn=None,
) -> dict[str, Any]:
    """Evaluate one flow through the canonical runtime-equivalent Core evaluator."""
    import drlink_v24 as v24

    family = str(plane or "").strip().lower()
    if family in ("remote", "internet"):
        if not service:
            raise ControlPlaneError("%s policy test requires service." % family)
        result = v24.evaluate_selector_policy(
            plane_db,
            family,
            source_name=source,
            destination_name=destination,
            service_name=service,
            resolve_fn=resolve_fn,
        )
    elif family == "ai":
        if not permission:
            raise ControlPlaneError("AI policy test requires permission.")
        result = v24.test_ai_access_v24(
            plane_db,
            identity=source,
            destination=destination,
            permission=permission,
            path=path or None,
        )
    else:
        raise ControlPlaneError("Unsupported access plane: %s" % plane)

    decision = _decision(result)
    normalized_input = {
        "plane": family,
        "source": str(source),
        "destination": str(destination),
    }
    if family == "ai":
        normalized_input["permission"] = str(permission)
        if path:
            normalized_input["path"] = str(path)
    else:
        normalized_input["service"] = str(service)

    reason = str(result.get("reason") or "").strip()
    if not reason:
        mode = str(result.get("mode") or "").upper()
        matched = list(result.get("matched_rules") or [])
        enforcement = str(result.get("enforcement") or "enabled").upper()
        if enforcement == "DISABLED":
            reason = "Policy enforcement is disabled; effective result is ALLOW."
        elif mode == "WHITELIST" and not matched:
            reason = "WHITELIST requires at least one enabled matching rule."
        elif mode == "BLACKLIST" and matched:
            reason = "BLACKLIST denies because an enabled rule matched."
        elif matched:
            reason = "Effective decision follows the matching enabled rule set."
        else:
            reason = "Effective decision follows the policy mode default."

    trace = {
        "normalized_input": normalized_input,
        "policy": {
            "mode": result.get("mode"),
            "enforcement": result.get("enforcement"),
            "matched_rules": list(result.get("matched_rules") or []),
        },
        "final": {
            "result": decision,
            "reason": reason,
        },
        "plane": family,
        "member_results": list(result.get("member_results") or []),
        "group_test": bool(result.get("group_test")),
        "mixed": bool(result.get("mixed")),
        "candidate_ips": list(result.get("candidate_ips") or []),
        "authorized_candidates": list(result.get("authorized_candidates") or []),
    }
    if family == "ai":
        trace["auth"] = result.get("auth")
        trace["path_required"] = bool(result.get("path_required"))
        trace["patterns"] = list(result.get("patterns") or [])
    return trace


def _row_to_test(row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "plane": str(row["plane"]),
        "source": str(row["source"]),
        "destination": str(row["destination"]),
        "service": str(row["service"] or ""),
        "permission": str(row["permission"] or ""),
        "path": str(row["path"] or ""),
        "expected": str(row["expected"]),
        "required": bool(row["required"]),
        "enabled": bool(row["enabled"]),
        "row_version": int(row["row_version"]),
        "created_revision": row["created_revision"],
        "updated_revision": row["updated_revision"],
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def list_saved_policy_tests(
    plane_db: ControlPlane,
    *,
    enabled_only: bool = False,
    required_only: bool = False,
    limit: int = MAX_POLICY_TESTS,
) -> list[dict[str, Any]]:
    bound = max(1, min(int(limit), MAX_POLICY_TESTS))
    clauses = []
    args: list[Any] = []
    if enabled_only:
        clauses.append("enabled=1")
    if required_only:
        clauses.append("required=1")
        clauses.append("enabled=1")
    sql = "SELECT * FROM management_policy_tests"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
    args.append(bound)
    return [_row_to_test(row) for row in plane_db.conn.execute(sql, args)]


def run_saved_policy_tests(
    plane_db: ControlPlane,
    *,
    required_only: bool = False,
    enabled_only: bool = True,
) -> dict[str, Any]:
    definitions = list_saved_policy_tests(
        plane_db,
        enabled_only=enabled_only,
        required_only=required_only,
    )
    results: list[dict[str, Any]] = []
    for definition in definitions:
        try:
            trace = evaluate_policy_flow(
                plane_db,
                plane=definition["plane"],
                source=definition["source"],
                destination=definition["destination"],
                service=definition["service"],
                permission=definition["permission"],
                path=definition["path"],
            )
            got = str(trace["final"]["result"])
            ok = got == definition["expected"]
            results.append(
                {
                    **definition,
                    "got": got,
                    "ok": ok,
                    "trace": trace,
                }
            )
        except Exception as exc:
            results.append(
                {
                    **definition,
                    "got": "ERROR",
                    "ok": False,
                    "error": str(exc),
                    "trace": None,
                }
            )
    failed = [row for row in results if not row["ok"]]
    required_failed = [row for row in failed if row["required"]]
    return {
        "items": results,
        "count": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "required_failed": len(required_failed),
        "ok": not required_failed,
    }


MAX_GRAPH_HOSTS = 100
MAX_GRAPH_NODES = 600
MAX_GRAPH_EDGES = 1200
MAX_GRAPH_PATHS = 400
MAX_GRAPH_UNKNOWNS = 100


def _ref_name(conn, kind: str, ident: str, *, service: bool = False, permission: bool = False) -> str:
    if service:
        table = "service_objects" if kind == "service_object" else "service_groups"
    elif permission:
        table = "permission_objects" if kind == "permission_object" else "permission_groups"
    else:
        table = "objects" if kind == "object" else "object_groups"
    row = conn.execute("SELECT name FROM %s WHERE id=?" % table, (ident,)).fetchone()
    return str(row["name"]) if row else str(ident)


def _graph_node_id(kind: str, name: str) -> str:
    return "%s:%s" % (str(kind), str(name).strip().lower())


def _offline_dns(_hostname: str) -> list[str]:
    raise RuntimeError("Effective Access Graph does not perform live DNS resolution.")


def _evaluate_graph_input(plane_db: ControlPlane, flow: dict[str, Any]) -> dict[str, Any]:
    try:
        trace = evaluate_policy_flow(
            plane_db,
            plane=str(flow.get("plane") or ""),
            source=str(flow.get("source") or ""),
            destination=str(flow.get("destination") or ""),
            service=str(flow.get("service") or ""),
            permission=str(flow.get("permission") or ""),
            path=str(flow.get("path") or ""),
            resolve_fn=_offline_dns,
        )
        decision = str(trace.get("final", {}).get("result") or "DENY").upper()
        if bool(trace.get("path_required")) and not str(flow.get("path") or ""):
            return {
                "decision": "UNKNOWN",
                "status": "unknown",
                "reason": "Concrete path context is required for this AI permission.",
            }
        return {
            "decision": decision,
            "status": "computed",
            "reason": str(trace.get("final", {}).get("reason") or ""),
        }
    except Exception as exc:
        return {
            "decision": "UNKNOWN",
            "status": "unknown",
            "reason": str(exc),
        }


def evaluate_graph_paths(
    plane_db: ControlPlane,
    paths: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in paths[:MAX_GRAPH_PATHS]:
        key = str(item.get("key") or "")
        flow = dict(item.get("input") or {})
        if not key or not flow:
            continue
        out[key] = _evaluate_graph_input(plane_db, flow)
    return out


def build_effective_access_graph(
    plane_db: ControlPlane,
    *,
    planes: Optional[list[str]] = None,
    max_hosts: int = MAX_GRAPH_HOSTS,
    max_nodes: int = MAX_GRAPH_NODES,
    max_edges: int = MAX_GRAPH_EDGES,
    max_paths: int = MAX_GRAPH_PATHS,
) -> dict[str, Any]:
    """Build a bounded policy/inventory graph using canonical Core state/evaluation."""
    import drlink_v24 as v24

    requested = [str(p).strip().lower() for p in (planes or ["remote", "internet", "ai"])]
    for plane in requested:
        if plane not in ("remote", "internet", "ai"):
            raise ControlPlaneError("Unsupported access plane: %s" % plane)

    node_limit = max(1, min(int(max_nodes), MAX_GRAPH_NODES))
    edge_limit = max(1, min(int(max_edges), MAX_GRAPH_EDGES))
    path_limit = max(1, min(int(max_paths), MAX_GRAPH_PATHS))
    host_limit = max(1, min(int(max_hosts), MAX_GRAPH_HOSTS))
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    paths: list[dict[str, Any]] = []
    path_by_key: dict[str, dict[str, Any]] = {}
    host_ids: set[str] = set()
    truncated = {
        "nodes": False,
        "edges": False,
        "paths": False,
        "hosts": False,
        "unknowns": False,
    }
    unknowns: list[str] = []

    def add_node(kind: str, name: str, **meta: Any) -> Optional[str]:
        node_id = _graph_node_id(kind, name)
        if node_id in nodes:
            nodes[node_id].update({k: v for k, v in meta.items() if v is not None})
            return node_id
        if len(nodes) >= node_limit:
            truncated["nodes"] = True
            return None
        if kind == "managed-host":
            if len(host_ids) >= host_limit:
                truncated["hosts"] = True
                return None
            host_ids.add(node_id)
        nodes[node_id] = {"id": node_id, "kind": kind, "name": str(name), **meta}
        return node_id

    def add_edge(kind: str, source: Optional[str], target: Optional[str], **meta: Any) -> None:
        if not source or not target:
            return
        edge_id = "%s|%s|%s|%s|%s" % (
            kind,
            source,
            target,
            str(meta.get("plane") or ""),
            str(meta.get("rule") or ""),
        )
        if edge_id in edges:
            return
        if len(edges) >= edge_limit:
            truncated["edges"] = True
            return
        edges[edge_id] = {
            "id": edge_id,
            "kind": kind,
            "source": source,
            "target": target,
            **meta,
        }

    def add_managed_services(object_id: str, host_name: str, host_node: Optional[str]) -> None:
        if not host_node:
            return
        ep = plane_db.conn.execute(
            "SELECT client_id FROM managed_endpoints WHERE object_id=?", (object_id,)
        ).fetchone()
        client_id = str(ep["client_id"]) if ep and ep["client_id"] else ""
        if not client_id:
            return
        for svc in plane_db.conn.execute(
            "SELECT id,name,service_type,target_host,target_port,public_port,enabled "
            "FROM published_services WHERE client_id=? AND released=0 "
            "ORDER BY name COLLATE NOCASE",
            (client_id,),
        ):
            svc_name = "%s/%s" % (host_name, str(svc["name"]))
            svc_node = add_node(
                "remote-service",
                svc_name,
                host=host_name,
                service_id=str(svc["id"]),
                service_type=str(svc["service_type"]),
                target_host=str(svc["target_host"]),
                target_port=int(svc["target_port"]),
                public_port=svc["public_port"],
                enabled=bool(svc["enabled"]),
            )
            add_edge("publishes", host_node, svc_node, plane="remote")

    def add_network_ref(kind: str, ident: str, *, plane: str, role: str) -> tuple[Optional[str], str]:
        name = _ref_name(plane_db.conn, kind, ident)
        if kind == "object":
            row = plane_db.conn.execute("SELECT * FROM objects WHERE id=?", (ident,)).fetchone()
            is_managed = bool(row and str(row["type"]) == "managed_endpoint")
            node_kind = "managed-host" if is_managed else "network-object"
            node = add_node(
                node_kind,
                name,
                object_type=str(row["type"]) if row else None,
                origin=str(row["origin"]) if row else None,
            )
            if is_managed:
                add_managed_services(ident, name, node)
            return node, name

        node = add_node("network-group", name)
        if node:
            try:
                members = plane_db._expand_group_members(ident, set())
            except Exception as exc:
                unknowns.append("Network Group %s: %s" % (name, exc))
                members = []
            for member in members:
                mname = str(member["name"])
                mkind = "managed-host" if str(member["type"]) == "managed_endpoint" else "network-object"
                mnode = add_node(
                    mkind,
                    mname,
                    object_type=str(member["type"]),
                    origin=str(member["origin"]),
                )
                add_edge("member-of", mnode, node, plane=plane, role=role)
                if mkind == "managed-host":
                    add_managed_services(str(member["id"]), mname, mnode)
        return node, name

    def add_service_ref(kind: str, ident: str, *, plane: str) -> tuple[Optional[str], str]:
        name = _ref_name(plane_db.conn, kind, ident, service=True)
        node_kind = "service-object" if kind == "service_object" else "service-group"
        node = add_node(node_kind, name)
        if node and kind == "service_group":
            for row in plane_db.conn.execute(
                "SELECT s.name AS name FROM service_group_members m "
                "JOIN service_objects s ON s.id=m.service_object_id "
                "WHERE m.group_id=? ORDER BY s.name COLLATE NOCASE",
                (ident,),
            ):
                member = add_node("service-object", str(row["name"]))
                add_edge("member-of", member, node, plane=plane)
        return node, name

    def add_permission_ref(kind: str, ident: str) -> tuple[Optional[str], str]:
        name = _ref_name(plane_db.conn, kind, ident, permission=True)
        node_kind = "permission-object" if kind == "permission_object" else "permission-group"
        node = add_node(node_kind, name)
        if node and kind == "permission_group":
            for row in plane_db.conn.execute(
                "SELECT p.name AS name FROM permission_group_members m "
                "JOIN permission_objects p ON p.id=m.permission_object_id "
                "WHERE m.group_id=? ORDER BY p.name COLLATE NOCASE",
                (ident,),
            ):
                member = add_node("permission-object", str(row["name"]))
                add_edge("member-of", member, node, plane="ai")
        return node, name

    def add_path(flow: dict[str, Any], *, rule: str, enabled: bool) -> None:
        key_parts = [
            str(flow.get("plane") or ""),
            str(flow.get("source") or ""),
            str(flow.get("destination") or ""),
            str(flow.get("service") or flow.get("permission") or ""),
            str(flow.get("path") or ""),
        ]
        key = "|".join(part.lower() for part in key_parts)
        existing = path_by_key.get(key)
        if existing is not None:
            rules = existing.setdefault("rules", [])
            if rule not in rules:
                rules.append(rule)
            return
        if len(paths) >= path_limit:
            truncated["paths"] = True
            return
        evaluated = _evaluate_graph_input(plane_db, flow)
        item = {
            "key": key,
            "rule": rule,
            "rules": [rule],
            "rule_enabled": bool(enabled),
            "plane": str(flow.get("plane") or ""),
            "input": flow,
            **evaluated,
        }
        paths.append(item)
        path_by_key[key] = item
        if evaluated["status"] == "unknown":
            unknowns.append("%s: %s" % (rule, evaluated.get("reason") or "unknown"))

    for plane in requested:
        policy = v24.get_access_policy(plane_db, plane)
        policy_node = add_node(
            "access-policy",
            plane,
            plane=plane,
            mode=policy.get("mode"),
            enforcement=policy.get("enforcement"),
        )
        if plane in ("remote", "internet"):
            rows = plane_db.conn.execute(
                "SELECT * FROM policy_rules WHERE plane=? ORDER BY position,name COLLATE NOCASE",
                (plane,),
            ).fetchall()
            for row in rows:
                rule_name = str(row["name"])
                rule_node = add_node(
                    "policy-rule",
                    "%s/%s" % (plane, rule_name),
                    plane=plane,
                    rule=rule_name,
                    enabled=bool(row["enabled"]),
                    action=str(row["action"]),
                    expires_at=row["expires_at"] if "expires_at" in row.keys() else None,
                )
                add_edge("contains", policy_node, rule_node, plane=plane, rule=rule_name)
                src_refs = list(plane_db.conn.execute(
                    "SELECT ref_kind,ref_id FROM rule_sources WHERE rule_id=? ORDER BY ref_kind,ref_id",
                    (row["id"],),
                ))
                dst_refs = list(plane_db.conn.execute(
                    "SELECT ref_kind,ref_id FROM rule_destinations WHERE rule_id=? ORDER BY ref_kind,ref_id",
                    (row["id"],),
                ))
                svc_refs = list(plane_db.conn.execute(
                    "SELECT ref_kind,ref_id FROM rule_service_refs WHERE rule_id=? ORDER BY ref_kind,ref_id",
                    (row["id"],),
                ))
                srcs: list[str] = []
                dsts: list[str] = []
                svcs: list[str] = []
                for ref in src_refs:
                    node, name = add_network_ref(str(ref["ref_kind"]), str(ref["ref_id"]), plane=plane, role="source")
                    srcs.append(name)
                    add_edge("source-selector", node, rule_node, plane=plane, rule=rule_name)
                for ref in dst_refs:
                    node, name = add_network_ref(str(ref["ref_kind"]), str(ref["ref_id"]), plane=plane, role="destination")
                    dsts.append(name)
                    add_edge("destination-selector", rule_node, node, plane=plane, rule=rule_name)
                for ref in svc_refs:
                    node, name = add_service_ref(str(ref["ref_kind"]), str(ref["ref_id"]), plane=plane)
                    svcs.append(name)
                    add_edge("service-selector", rule_node, node, plane=plane, rule=rule_name)
                if not svcs:
                    for svc in plane_db.conn.execute(
                        "SELECT protocol,port FROM rule_services WHERE rule_id=? ORDER BY protocol,port",
                        (row["id"],),
                    ):
                        name = "%s/%s" % (str(svc["protocol"]), int(svc["port"]))
                        svcs.append(name)
                        node = add_node("service", name)
                        add_edge("service-selector", rule_node, node, plane=plane, rule=rule_name)
                for source in srcs:
                    for destination in dsts:
                        for service in svcs:
                            add_path(
                                {
                                    "plane": plane,
                                    "source": source,
                                    "destination": destination,
                                    "service": service,
                                },
                                rule=rule_name,
                                enabled=bool(row["enabled"]),
                            )
        else:
            rows = plane_db.conn.execute(
                "SELECT * FROM ai_policy_rules ORDER BY name COLLATE NOCASE"
            ).fetchall()
            for row in rows:
                rule_name = str(row["name"])
                rule_node = add_node(
                    "policy-rule",
                    "ai/%s" % rule_name,
                    plane="ai",
                    rule=rule_name,
                    enabled=bool(row["enabled"]),
                    expires_at=row["expires_at"] if "expires_at" in row.keys() else None,
                )
                add_edge("contains", policy_node, rule_node, plane="ai", rule=rule_name)
                principal_name = ""
                principal_node = None
                if row["source_identity_id"]:
                    principal = plane_db.conn.execute(
                        "SELECT name,credential_status,enabled FROM ai_principals WHERE id=?",
                        (row["source_identity_id"],),
                    ).fetchone()
                    if principal:
                        principal_name = str(principal["name"])
                        principal_node = add_node(
                            "ai-identity",
                            principal_name,
                            credential_status=str(principal["credential_status"]),
                            enabled=bool(principal["enabled"]),
                        )
                        add_edge("source-identity", principal_node, rule_node, plane="ai", rule=rule_name)
                destination_name = ""
                destination_node = None
                if row["destination_ref_kind"] and row["destination_ref_id"]:
                    destination_node, destination_name = add_network_ref(
                        str(row["destination_ref_kind"]),
                        str(row["destination_ref_id"]),
                        plane="ai",
                        role="destination",
                    )
                    add_edge("destination-selector", rule_node, destination_node, plane="ai", rule=rule_name)
                permission_name = ""
                permission_node = None
                if row["permission_ref_kind"] and row["permission_ref_id"]:
                    permission_node, permission_name = add_permission_ref(
                        str(row["permission_ref_kind"]),
                        str(row["permission_ref_id"]),
                    )
                    add_edge("permission-selector", rule_node, permission_node, plane="ai", rule=rule_name)
                patterns = [
                    str(item["pattern"])
                    for item in plane_db.conn.execute(
                        "SELECT pattern FROM ai_policy_path_scopes WHERE rule_id=? ORDER BY pattern COLLATE NOCASE",
                        (row["id"],),
                    )
                ]
                if rule_node and patterns:
                    nodes[rule_node]["path_scopes"] = patterns[:32]
                if principal_name and destination_name and permission_name:
                    add_path(
                        {
                            "plane": "ai",
                            "source": principal_name,
                            "destination": destination_name,
                            "permission": permission_name,
                            "path": "",
                        },
                        rule=rule_name,
                        enabled=bool(row["enabled"]),
                    )

    unique_unknowns = sorted(set(unknowns))
    truncated["unknowns"] = len(unique_unknowns) > MAX_GRAPH_UNKNOWNS
    return {
        "revision": int(plane_db.current_revision()),
        "planes": requested,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "paths": paths,
        "limits": {
            "max_hosts": host_limit,
            "max_nodes": node_limit,
            "max_edges": edge_limit,
            "max_paths": path_limit,
            "max_unknowns": MAX_GRAPH_UNKNOWNS,
            "host_count": len(host_ids),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "path_count": len(paths),
            "unknown_count_total": len(unique_unknowns),
            "unknown_count_returned": min(len(unique_unknowns), MAX_GRAPH_UNKNOWNS),
            "truncated": any(truncated.values()),
            "truncated_by": [key for key, value in truncated.items() if value],
        },
        "unknowns": unique_unknowns[:MAX_GRAPH_UNKNOWNS],
        "scope": "policy-and-inventory",
        "network_topology": False,
    }


def preview_rule_expiry_policy_safety(
    plane_db: ControlPlane,
    *,
    family: str,
    rule_name: str,
    expires_at: str,
) -> dict[str, Any]:
    """Evaluate Temporary Access expiry mutation in rollback-only proposed state."""
    import drlink_v24 as v24

    current_graph = build_effective_access_graph(plane_db)
    savepoint = "drlink_temporary_access_preview"
    previous_batch = plane_db._batch_mode
    previous_results = plane_db._batch_results
    proposed_graph: dict[str, Any]
    proposed_for_current: dict[str, dict[str, Any]]
    regression: dict[str, Any]
    plane_db.conn.execute("SAVEPOINT %s" % savepoint)
    plane_db._batch_mode = True
    plane_db._batch_results = []
    try:
        if family == "ai":
            v24.set_ai_access_rule(
                plane_db,
                rule_name,
                expires_at=expires_at,
                oneshot=True,
                confirm=True,
            )
        else:
            v24.set_access_rule(
                plane_db,
                family,
                rule_name,
                expires_at=expires_at,
                oneshot=True,
                confirm=True,
            )
        regression = run_saved_policy_tests(
            plane_db,
            required_only=True,
            enabled_only=True,
        )
        proposed_graph = build_effective_access_graph(plane_db)
        proposed_for_current = evaluate_graph_paths(
            plane_db,
            list(current_graph.get("paths") or []),
        )
    finally:
        if plane_db.conn.in_transaction:
            try:
                plane_db.conn.execute("ROLLBACK TO SAVEPOINT %s" % savepoint)
            finally:
                plane_db.conn.execute("RELEASE SAVEPOINT %s" % savepoint)
        plane_db._batch_mode = previous_batch
        plane_db._batch_results = previous_results

    current_for_proposed = evaluate_graph_paths(
        plane_db,
        list(proposed_graph.get("paths") or []),
    )
    blast = diff_effective_access_graphs(
        current_graph,
        proposed_graph,
        current_for_proposed=current_for_proposed,
        proposed_for_current=proposed_for_current,
    )
    current_ids = {
        str(item.get("id"))
        for item in current_graph.get("edges") or []
        if item.get("id")
    }
    proposed_ids = {
        str(item.get("id"))
        for item in proposed_graph.get("edges") or []
        if item.get("id")
    }
    return {
        "policy_regression": regression,
        "blast_radius": blast,
        "graph_overlay": {
            "current": current_graph,
            "proposed": proposed_graph,
            "added_edge_ids": [
                str(item.get("id"))
                for item in blast.get("references_added") or []
                if item.get("id")
            ],
            "removed_edge_ids": [
                str(item.get("id"))
                for item in blast.get("references_removed") or []
                if item.get("id")
            ],
            "unchanged_edge_ids": sorted(current_ids & proposed_ids),
            "decision_changes": list(blast.get("decision_changes") or []),
            "limits": dict(blast.get("limits") or {}),
            "bounded": True,
        },
    }


def diff_effective_access_graphs(
    current: dict[str, Any],
    proposed: dict[str, Any],
    *,
    current_for_proposed: Optional[dict[str, dict[str, Any]]] = None,
    proposed_for_current: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Compare current/proposed graph facts and canonical modeled decisions."""
    current_for_proposed = current_for_proposed or {}
    proposed_for_current = proposed_for_current or {}
    current_edges = {str(item["id"]): item for item in current.get("edges") or []}
    proposed_edges = {str(item["id"]): item for item in proposed.get("edges") or []}
    current_nodes = {str(item["id"]): item for item in current.get("nodes") or []}
    proposed_nodes = {str(item["id"]): item for item in proposed.get("nodes") or []}
    current_paths = {str(item["key"]): item for item in current.get("paths") or []}
    proposed_paths = {str(item["key"]): item for item in proposed.get("paths") or []}
    keys = sorted(set(current_paths) | set(proposed_paths))
    changes: list[dict[str, Any]] = []
    broadened = False
    narrowed = False
    affected_rules: set[str] = set()
    for key in keys:
        before_item = current_paths.get(key)
        after_item = proposed_paths.get(key)
        before_eval = (
            {"decision": before_item.get("decision"), "status": before_item.get("status")}
            if before_item
            else current_for_proposed.get(key)
        ) or {"decision": "UNKNOWN", "status": "unknown"}
        after_eval = (
            {"decision": after_item.get("decision"), "status": after_item.get("status")}
            if after_item
            else proposed_for_current.get(key)
        ) or {"decision": "UNKNOWN", "status": "unknown"}
        before = str(before_eval.get("decision") or "UNKNOWN").upper()
        after = str(after_eval.get("decision") or "UNKNOWN").upper()
        if before == after and bool(before_item) == bool(after_item):
            continue
        flow = dict((after_item or before_item or {}).get("input") or {})
        rules = {
            str(rule)
            for item in (before_item, after_item)
            if item
            for rule in (item.get("rules") or ([item.get("rule")] if item.get("rule") else []))
            if rule
        }
        affected_rules.update(rules)
        if before == "DENY" and after == "ALLOW":
            broadened = True
        if before == "ALLOW" and after == "DENY":
            narrowed = True
        changes.append(
            {
                "key": key,
                "flow": flow,
                "current": before,
                "proposed": after,
                "current_status": before_eval.get("status"),
                "proposed_status": after_eval.get("status"),
                "rules": sorted(rules),
            }
        )

    added_ids = sorted(set(proposed_edges) - set(current_edges))
    removed_ids = sorted(set(current_edges) - set(proposed_edges))
    changed_node_ids = set()
    for edge_id in added_ids:
        edge = proposed_edges[edge_id]
        changed_node_ids.update([str(edge["source"]), str(edge["target"])])
        if edge.get("rule"):
            affected_rules.add(str(edge["rule"]))
    for edge_id in removed_ids:
        edge = current_edges[edge_id]
        changed_node_ids.update([str(edge["source"]), str(edge["target"])])
        if edge.get("rule"):
            affected_rules.add(str(edge["rule"]))
    combined_nodes = {**current_nodes, **proposed_nodes}

    def names(kind: str) -> list[str]:
        return sorted(
            {
                str(combined_nodes[node_id]["name"])
                for node_id in changed_node_ids
                if node_id in combined_nodes and combined_nodes[node_id].get("kind") == kind
            },
            key=str.lower,
        )

    affected_hosts_set = set(names("managed-host"))
    affected_destinations = {
        str((change.get("flow") or {}).get("destination"))
        for change in changes
        if (change.get("flow") or {}).get("destination")
    }
    all_edges = list(current_edges.values()) + list(proposed_edges.values())
    changed_groups = {
        node_id
        for node_id in changed_node_ids
        if node_id in combined_nodes
        and combined_nodes[node_id].get("kind") == "network-group"
    }
    for edge in all_edges:
        if edge.get("kind") == "member-of" and str(edge.get("target")) in changed_groups:
            source_id = str(edge.get("source") or "")
            source_node = combined_nodes.get(source_id) or {}
            if source_node.get("kind") == "managed-host":
                affected_hosts_set.add(str(source_node.get("name") or ""))
        if edge.get("kind") == "destination-selector" and str(edge.get("id")) in set(added_ids + removed_ids):
            target_id = str(edge.get("target") or "")
            target_node = combined_nodes.get(target_id) or {}
            if target_node.get("name"):
                affected_destinations.add(str(target_node["name"]))

    affected_hosts = sorted(filter(None, affected_hosts_set), key=str.lower)
    affected_services = set(names("remote-service"))
    for node in combined_nodes.values():
        if node.get("kind") == "remote-service" and str(node.get("host") or "") in affected_hosts_set:
            affected_services.add(str(node.get("name") or ""))

    newly_reachable = [
        item
        for item in changes
        if item["current"] == "DENY" and item["proposed"] == "ALLOW"
    ]
    newly_blocked = [
        item
        for item in changes
        if item["current"] == "ALLOW" and item["proposed"] == "DENY"
    ]
    combined_unknowns = sorted(
        set((current.get("unknowns") or []) + (proposed.get("unknowns") or []))
    )
    current_limits = dict(current.get("limits") or {})
    proposed_limits = dict(proposed.get("limits") or {})
    truncated_by: list[str] = []
    if bool(current_limits.get("truncated")):
        truncated_by.append("current_graph")
    if bool(proposed_limits.get("truncated")):
        truncated_by.append("proposed_graph")
    if len(changes) > MAX_GRAPH_PATHS:
        truncated_by.append("decision_changes")
    if len(newly_reachable) > MAX_GRAPH_PATHS:
        truncated_by.append("newly_reachable")
    if len(newly_blocked) > MAX_GRAPH_PATHS:
        truncated_by.append("newly_blocked")
    if len(added_ids) > MAX_GRAPH_EDGES:
        truncated_by.append("references_added")
    if len(removed_ids) > MAX_GRAPH_EDGES:
        truncated_by.append("references_removed")
    if len(combined_unknowns) > MAX_GRAPH_UNKNOWNS:
        truncated_by.append("unknowns")

    return {
        "access_broadened": broadened,
        "access_narrowed": narrowed,
        "affected_rules": sorted(affected_rules, key=str.lower),
        "affected_managed_hosts": affected_hosts,
        "affected_remote_services": sorted(affected_services, key=str.lower),
        "affected_destinations": sorted(
            filter(None, affected_destinations),
            key=str.lower,
        ),
        "decision_changes": changes[:MAX_GRAPH_PATHS],
        "newly_reachable": newly_reachable[:MAX_GRAPH_PATHS],
        "newly_blocked": newly_blocked[:MAX_GRAPH_PATHS],
        "references_added": [proposed_edges[item] for item in added_ids[:MAX_GRAPH_EDGES]],
        "references_removed": [current_edges[item] for item in removed_ids[:MAX_GRAPH_EDGES]],
        "facts": {
            "current_revision": current.get("revision"),
            "proposed_revision": proposed.get("revision"),
            "current_modeled_flows": len(current_paths),
            "proposed_modeled_flows": len(proposed_paths),
        },
        "limits": {
            "max_decision_changes": MAX_GRAPH_PATHS,
            "max_reference_changes": MAX_GRAPH_EDGES,
            "max_unknowns": MAX_GRAPH_UNKNOWNS,
            "decision_changes_total": len(changes),
            "newly_reachable_total": len(newly_reachable),
            "newly_blocked_total": len(newly_blocked),
            "references_added_total": len(added_ids),
            "references_removed_total": len(removed_ids),
            "unknown_count_total": len(combined_unknowns),
            "current_graph": current_limits,
            "proposed_graph": proposed_limits,
            "truncated": bool(truncated_by),
            "truncated_by": truncated_by,
        },
        "unknowns": combined_unknowns[:MAX_GRAPH_UNKNOWNS],
        "bounded": True,
    }


class PolicySafetyService(ManagementChangeService):
    """Saved test lifecycle + side-effect-free Decision Trace."""

    def __init__(self, root: Optional[str] = None, *, query_only: bool = False):
        self.root = root
        self.plane = ControlPlane(root, read_only=True) if query_only else ControlPlane(root)
        self.server_id = "" if query_only else self._server_id()

    @classmethod
    def open_read_only(cls, root: Optional[str] = None) -> "PolicySafetyService":
        return cls(root, query_only=True)

    def decision_trace(self, **flow: Any) -> dict[str, Any]:
        return evaluate_policy_flow(self.plane, **flow)

    def effective_access_graph(
        self,
        *,
        planes: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return build_effective_access_graph(self.plane, planes=planes)


    def list_tests(self) -> dict[str, Any]:
        items = list_saved_policy_tests(self.plane)
        return {"items": items, "count": len(items)}

    def run_tests(self, *, required_only: bool = False) -> dict[str, Any]:
        return run_saved_policy_tests(
            self.plane,
            required_only=required_only,
            enabled_only=True,
        )

    def _existing(self, name: str):
        return self.plane.conn.execute(
            "SELECT * FROM management_policy_tests WHERE name=? COLLATE NOCASE",
            (str(name),),
        ).fetchone()

    def preview_definition(
        self,
        *,
        actor_id: str,
        operation: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        action = str(operation or "set").strip().lower()
        if action not in ("set", "delete"):
            raise ControlPlaneError("Policy Regression Test operation must be set or delete.")
        expected_revision = int(self.plane.current_revision())
        if action == "delete":
            name = _text(definition.get("name"), "Policy Regression Test name", max_len=MAX_POLICY_TEST_NAME)
            row = self._existing(name)
            if not row:
                raise ControlPlaneError("Policy Regression Test '%s' was not found." % name)
            normalized = {"name": name}
            current = _row_to_test(row)
            preview = {"operation": "delete", "before": current, "after": None}
            impact = {
                "requires_confirmation": True,
                "destructive": True,
                "warning": (
                    "Deleting this saved Policy Regression Test removes a safety assertion."
                    + (" It is REQUIRED." if current["required"] else "")
                ),
            }
            no_change = False
            confirmation = CONFIRM_DELETE_TEST
        else:
            normalized = normalize_policy_test(definition)
            row = self._existing(normalized["name"])
            current = _row_to_test(row) if row else None
            comparable = {
                key: normalized[key]
                for key in (
                    "name",
                    "plane",
                    "source",
                    "destination",
                    "service",
                    "permission",
                    "path",
                    "expected",
                    "required",
                    "enabled",
                )
            }
            no_change = bool(
                current
                and all(current.get(key) == value for key, value in comparable.items())
            )
            try:
                trace = evaluate_policy_flow(
                    self.plane,
                    plane=normalized["plane"],
                    source=normalized["source"],
                    destination=normalized["destination"],
                    service=normalized["service"],
                    permission=normalized["permission"],
                    path=normalized["path"],
                )
                current_result = str(trace["final"]["result"])
                assertion_ok = current_result == normalized["expected"]
            except Exception as exc:
                trace = None
                current_result = "ERROR"
                assertion_ok = False
                preview_error = str(exc)
            preview = {
                "operation": "set",
                "before": current,
                "after": normalized,
                "current_result": current_result,
                "assertion_ok": assertion_ok,
                "trace": trace,
            }
            if trace is None:
                preview["error"] = preview_error
            impact = {
                "requires_confirmation": True,
                "destructive": False,
                "warning": (
                    "This changes a saved policy safety assertion."
                    if current
                    else "This creates a saved policy safety assertion."
                ),
                "required": bool(normalized["required"]),
                "current_assertion_ok": assertion_ok,
            }
            confirmation = CONFIRM_CHANGE

        issued = self._issue_plan(
            actor_id=actor_id,
            operation_class="CHANGE",
            operation="policy-regression-test.%s" % action,
            resource_type="policy-regression-test",
            resource_ref=str(normalized["name"]),
            expected_revision=expected_revision,
            payload={
                "kind": "policy-regression-test",
                "operation": action,
                "definition": normalized,
                "no_change": no_change,
            },
            impact=impact,
            confirmation_class=confirmation,
        )
        issued.update({"preview": preview, "no_change": no_change})
        return issued

    def apply_definition(
        self,
        *,
        actor_id: str,
        change_plan_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        row = self._load_plan(actor_id, change_plan_id)
        if (
            str(row["operation_class"]) != "CHANGE"
            or not str(row["operation"]).startswith("policy-regression-test.")
        ):
            raise ControlPlaneError(
                "Change Plan is not a Policy Regression Test change."
            )
        expected_confirmation = str(row["confirmation_class"] or "")
        if str(confirmation or "").strip().upper() != expected_confirmation:
            raise ControlPlaneError(
                "Policy Regression Test apply requires explicit confirmation '%s'."
                % expected_confirmation
            )
        try:
            document = json.loads(str(row["payload_json"]))
            if document.get("kind") != "policy-regression-test":
                raise ControlPlaneError("Change Plan payload is invalid.")
            action = str(document.get("operation") or "")
            definition = dict(document.get("definition") or {})
            if action == "set":
                definition = normalize_policy_test(definition)
            elif action == "delete":
                definition = {
                    "name": _text(
                        definition.get("name"),
                        "Policy Regression Test name",
                        max_len=MAX_POLICY_TEST_NAME,
                    )
                }
            else:
                raise ControlPlaneError("Change Plan payload is invalid.")
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
            return {"status": "NO_CHANGE", "revision": current}

        def writer():
            if action == "delete":
                existing = self._existing(definition["name"])
                if not existing:
                    raise ControlPlaneError(
                        "Policy Regression Test '%s' was not found." % definition["name"]
                    )
                self.plane.conn.execute(
                    "DELETE FROM management_policy_tests WHERE id=?",
                    (existing["id"],),
                )
                return {
                    "entity": {
                        "type": "policy-regression-test",
                        "id": str(existing["id"]),
                        "name": str(existing["name"]),
                    },
                    "operation": "delete",
                }

            existing = self._existing(definition["name"])
            now = utc_now_iso()
            next_revision = self.plane._next_revision()
            if existing:
                self.plane.conn.execute(
                    "UPDATE management_policy_tests SET "
                    "plane=?,source=?,destination=?,service=?,permission=?,path=?,"
                    "expected=?,required=?,enabled=?,row_version=row_version+1,"
                    "updated_revision=?,updated_at=? WHERE id=?",
                    (
                        definition["plane"],
                        definition["source"],
                        definition["destination"],
                        definition["service"],
                        definition["permission"],
                        definition["path"],
                        definition["expected"],
                        1 if definition["required"] else 0,
                        1 if definition["enabled"] else 0,
                        next_revision,
                        now,
                        existing["id"],
                    ),
                )
                ident = str(existing["id"])
                op = "update"
            else:
                ident = "prt_" + secrets.token_hex(12)
                self.plane.conn.execute(
                    "INSERT INTO management_policy_tests("
                    "id,name,plane,source,destination,service,permission,path,expected,"
                    "required,enabled,row_version,created_revision,updated_revision,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)",
                    (
                        ident,
                        definition["name"],
                        definition["plane"],
                        definition["source"],
                        definition["destination"],
                        definition["service"],
                        definition["permission"],
                        definition["path"],
                        definition["expected"],
                        1 if definition["required"] else 0,
                        1 if definition["enabled"] else 0,
                        next_revision,
                        next_revision,
                        now,
                        now,
                    ),
                )
                op = "create"
            return {
                "entity": {
                    "type": "policy-regression-test",
                    "id": ident,
                    "name": definition["name"],
                },
                "operation": op,
            }

        try:
            result = self.plane._mutate(
                "web policy-regression-test %s %s"
                % (action, definition["name"]),
                "apply saved Policy Regression Test change",
                writer,
                expected_revision=expected_revision,
                confirm=True,
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
            "result": result,
        }
