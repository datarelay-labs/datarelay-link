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
