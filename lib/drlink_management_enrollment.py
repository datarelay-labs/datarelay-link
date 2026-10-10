#!/usr/bin/env python3
"""DRL3-3 Web/Core enrollment guidance over existing allocator authority."""
from __future__ import annotations

import importlib.util
import json
import os
import secrets
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from drlink_control_db import ControlPlaneError
import drlink_qualified_artifacts as artifacts
import frp_enrollment_lifecycle as lifecycle
import frp_audit
import frp_control_locks
import frp_pki
import frp_server_config
import frp_zero_touch

SUPPORTED_PLATFORMS = frozenset({"linux", "macos", "windows"})
DEFAULT_ZERO_TOUCH_TTL = 3600
MAX_ZERO_TOUCH_TTL = 24 * 3600
DEFAULT_MANUAL_TTL = 600
MAX_MANUAL_TTL = 30 * 86400
MAX_LABEL = 128
MAX_NOTE = 1024


def _load_allocator():
    here = Path(__file__).resolve()
    candidates = (
        here.parent.parent / "server" / "frp-port-allocator.py",
        here.parent / "frp-port-allocator.py",
        Path("/usr/local/lib/drlink/frp-port-allocator.py"),
    )
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("drlink_management_allocator", str(path))
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    raise ControlPlaneError("Enrollment allocator authority is unavailable.")


def _root_path(root: Optional[str], absolute: str) -> Path:
    if root:
        return Path(root) / absolute.lstrip("/")
    return Path(absolute)


def _config(root: Optional[str]) -> dict[str, Any]:
    path = _root_path(root, "/etc/drlink/config.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControlPlaneError("Server enrollment configuration is unavailable.") from exc
    if not isinstance(data, dict):
        raise ControlPlaneError("Server enrollment configuration is invalid.")
    return data


def _text(value: Any, field: str, maximum: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ControlPlaneError("%s is required." % field)
    if len(text) > maximum:
        raise ControlPlaneError("%s is too long." % field)
    if any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in text):
        raise ControlPlaneError("%s contains unsupported control characters." % field)
    return text


def _ttl(value: Any) -> int:
    if value is None:
        return DEFAULT_ZERO_TOUCH_TTL
    if isinstance(value, bool):
        raise ControlPlaneError("Enrollment TTL must be an integer number of seconds.")
    try:
        ttl = int(value)
    except (TypeError, ValueError) as exc:
        raise ControlPlaneError("Enrollment TTL must be an integer number of seconds.") from exc
    if ttl < 60 or ttl > MAX_ZERO_TOUCH_TTL:
        raise ControlPlaneError("Zero-Touch TTL must be between 60 and 86400 seconds.")
    return ttl


def _manual_ttl(value: Any) -> int:
    if value is None:
        return DEFAULT_MANUAL_TTL
    if isinstance(value, bool):
        raise ControlPlaneError("Enrollment TTL must be an integer number of seconds.")
    try:
        ttl = int(value)
    except (TypeError, ValueError) as exc:
        raise ControlPlaneError("Enrollment TTL must be an integer number of seconds.") from exc
    if ttl < 60 or ttl > MAX_MANUAL_TTL:
        raise ControlPlaneError("Manual Enrollment TTL must be between 60 and 2592000 seconds.")
    return ttl


def _iso_from_epoch(value: int) -> str:
    return datetime.fromtimestamp(int(value), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _manual_command(context: dict[str, str]) -> str:
    env_parts = [
        "FRP_ALLOCATOR_URL=%s" % shlex.quote(context["allocator_url"]),
        "FRP_ALLOCATOR_CA_SHA256=%s" % shlex.quote(context["ca_sha256"]),
    ]
    return frp_zero_touch.pinned_ca_manual_linux_command(
        context["installer_url"],
        context["allocator_url"],
        context["ca_sha256"],
        env_parts,
    )


def _state_paths(root: Optional[str], cfg: dict[str, Any]) -> tuple[Path, Path]:
    enroll_raw = str(cfg.get("enrollments_dir") or "").strip()
    if not enroll_raw:
        raise ControlPlaneError("Server enrollments_dir is not configured.")
    enrollments = _root_path(root, enroll_raw)
    bootstrap_raw = str(cfg.get("bootstrap_dir") or "").strip()
    bootstrap = (
        _root_path(root, bootstrap_raw)
        if bootstrap_raw
        else enrollments.parent / "bootstrap"
    )
    return enrollments, bootstrap


def _allocator_cfg(root: Optional[str], cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg)
    enrollments, bootstrap = _state_paths(root, cfg)
    out["enrollments_dir"] = str(enrollments)
    out["bootstrap_dir"] = str(bootstrap)
    registry = str(cfg.get("registry_file") or "").strip()
    out["registry_file"] = str(
        _root_path(root, registry) if registry else enrollments.parent / "registry.json"
    )
    ca = str(cfg.get("tls_ca_cert") or "/etc/drlink/pki/ca.crt")
    out["tls_ca_cert"] = str(_root_path(root, ca))
    return out


def _installer_context(root: Optional[str], cfg: dict[str, Any], platform: str) -> dict[str, str]:
    allocator_url = str(cfg.get("allocator_public_url") or "").strip()
    if not allocator_url.lower().startswith("https://"):
        raise ControlPlaneError("Allocator public URL must be configured with HTTPS.")
    ca_path = _root_path(root, str(cfg.get("tls_ca_cert") or "/etc/drlink/pki/ca.crt"))
    if not ca_path.is_file():
        raise ControlPlaneError("Allocator CA certificate is unavailable.")
    try:
        ca_sha256 = frp_pki.fingerprint_from_cert_file(ca_path)
    except Exception as exc:
        raise ControlPlaneError("Allocator CA fingerprint is unavailable.") from exc
    artifact_platform = "windows" if platform == "windows" else "linux"
    try:
        installer_url = artifacts.agent_installer_url(allocator_url, artifact_platform)
    except Exception as exc:
        raise ControlPlaneError(str(exc)) from exc
    return {
        "allocator_url": allocator_url,
        "ca_sha256": ca_sha256,
        "installer_url": installer_url,
    }


def _render_command(
    *,
    platform: str,
    cfg: dict[str, Any],
    context: dict[str, str],
    raw_ticket: str,
    ticket_record: dict[str, Any],
) -> str:
    short_handle = str(ticket_record.get("_short_handle") or "")
    bootstrap_host = str(frp_server_config.short_url_hostname(cfg) or "").strip()
    if platform == "windows":
        renderer = ticket_record.get("windows_renderer") or {}
        stage1 = str(renderer.get("stage1_sha256") or "") if isinstance(renderer, dict) else ""
        if bootstrap_host and short_handle and stage1:
            return frp_zero_touch.windows_strict_launcher(bootstrap_host, short_handle, stage1)
        sums = artifacts.artifact_sha256sums_url(context["allocator_url"])
        return frp_zero_touch.pinned_ca_windows_command(
            context["installer_url"],
            context["allocator_url"],
            context["ca_sha256"],
            raw_ticket,
            sums,
        )
    if bootstrap_host and short_handle:
        return frp_zero_touch.short_url_command(bootstrap_host, short_handle)
    package = frp_zero_touch.encode_zero_touch_package(
        context["allocator_url"], context["ca_sha256"], raw_ticket
    )
    return frp_zero_touch.pinned_ca_linux_command(
        context["installer_url"],
        context["allocator_url"],
        context["ca_sha256"],
        package,
    )


class ManagementEnrollmentService:
    """Issue display-once Zero-Touch guidance without creating a second authority."""

    def __init__(self, root: Optional[str] = None):
        self.root = root

    def issue_zero_touch(
        self,
        *,
        platform: str,
        ttl_seconds: Optional[int] = None,
        label: str = "",
        note: str = "",
        actor_id: str = "web:unknown",
        pre_approved: bool = False,
    ) -> dict[str, Any]:
        if type(pre_approved) is not bool:
            raise ControlPlaneError("Pre-approve this enrollment must be boolean.")
        target = str(platform or "").strip().lower()
        if target not in SUPPORTED_PLATFORMS:
            raise ControlPlaneError("Unsupported Agent platform: %s" % platform)
        ttl = _ttl(ttl_seconds)
        safe_label = _text(label, "Managed Host label", MAX_LABEL)
        safe_note = _text(note, "Enrollment note", MAX_NOTE)
        cfg = _config(self.root)
        normalized_cfg = _allocator_cfg(self.root, cfg)
        context = _installer_context(self.root, cfg, target)
        allocator = _load_allocator()
        try:
            services = allocator.normalize_services([])
        except Exception as exc:
            raise ControlPlaneError("Enrollment service scope is invalid.") from exc
        enrollments, bootstrap = _state_paths(self.root, cfg)
        try:
            raw_ticket, enroll_record, ticket_record = allocator.issue_bootstrap_ticket(
                enrollments,
                bootstrap,
                services,
                ttl,
                safe_note,
                label=safe_label,
                cfg=normalized_cfg,
                pre_approved=pre_approved,
                pre_approval_actor=str(actor_id) if pre_approved else "",
            )
        except Exception as exc:
            raise ControlPlaneError("Zero-Touch enrollment issuance failed: %s" % exc) from exc
        command = _render_command(
            platform=target,
            cfg=cfg,
            context=context,
            raw_ticket=raw_ticket,
            ticket_record=ticket_record,
        )
        frp_audit.try_emit(
            "enrollment.created",
            actor=str(actor_id or "web:unknown"),
            details={
                "mode": "zero-touch",
                "platform": target,
                "label": safe_label,
                "enrollment_id": str(ticket_record.get("id") or ""),
                "ttl_seconds": ttl,
                "pre_approved": pre_approved,
            },
        )
        return {
            "pre_approved": pre_approved,
            "enrollment_id": str(ticket_record.get("id") or ""),
            "enrollment_record_id": str(enroll_record.get("id") or ""),
            "mode": "zero-touch",
            "platform": target,
            "state": "pending",
            "expires_at": str(enroll_record.get("expires_at_iso") or ""),
            "ttl_seconds": ttl,
            "command": command,
            "display_once": True,
            "management_only": True,
            "next_step": "Run the command once on the target Agent host, then watch Managed Hosts for the first successful connection.",
        }

    def issue_manual(
        self,
        *,
        platform: str,
        ttl_seconds: Optional[int] = None,
        label: str = "",
        note: str = "",
        actor_id: str = "web:unknown",
    ) -> dict[str, Any]:
        target = str(platform or "").strip().lower()
        if target not in ("linux", "macos"):
            raise ControlPlaneError(
                "Manual Enrollment supports Linux/macOS; use Zero-Touch for Windows."
            )
        ttl = _manual_ttl(ttl_seconds)
        safe_label = _text(label, "Managed Host label", MAX_LABEL)
        safe_note = _text(note, "Enrollment note", MAX_NOTE)
        cfg = _config(self.root)
        context = _installer_context(self.root, cfg, target)
        enrollments, _bootstrap = _state_paths(self.root, cfg)
        allocator = _load_allocator()
        enrollments.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(enrollments, 0o700)
        except OSError:
            pass
        state_dir = enrollments.resolve().parent
        record = None
        for _attempt in range(8):
            enrollment_id = secrets.token_hex(8)
            secret = secrets.token_hex(32)
            path = enrollments / (enrollment_id + ".json")
            if path.exists():
                continue
            now = int(time.time())
            record = {
                "id": enrollment_id,
                "secret": secret,
                "created_at": _iso_from_epoch(now),
                "expires_at": now + ttl,
                "expires_at_iso": _iso_from_epoch(now + ttl),
                "bound_machine_id": None,
                "used_at": None,
                "note": safe_note,
                "label": safe_label,
            }
            with frp_control_locks.acquire_state_dir_control_locks(state_dir):
                if path.exists():
                    record = None
                    continue
                allocator.atomic_write_json(path, record, mode=0o600)
            break
        if record is None:
            raise ControlPlaneError("Failed to allocate a unique Manual Enrollment Code.")
        try:
            lifecycle.maybe_run_retention_cleanup(
                _allocator_cfg(self.root, cfg), force=True, audit_emit=frp_audit.try_emit
            )
        except Exception:
            pass
        command = _manual_command(context)
        frp_audit.try_emit(
            "enrollment.created",
            actor=str(actor_id or "web:unknown"),
            details={
                "mode": "manual",
                "platform": target,
                "label": safe_label,
                "enrollment_id": record["id"],
                "ttl_seconds": ttl,
            },
        )
        return {
            "enrollment_id": record["id"],
            "mode": "manual",
            "platform": target,
            "state": "pending",
            "expires_at": record["expires_at_iso"],
            "ttl_seconds": ttl,
            "enrollment_code": "%s.%s" % (record["id"], record["secret"]),
            "command": command,
            "display_once": True,
            "management_only": True,
            "next_step": "Run the command on the target host and enter the displayed Enrollment Code when prompted.",
        }

    def list_enrollments(self, *, limit: int = 50) -> dict[str, Any]:
        cfg = _config(self.root)
        enrollments, bootstrap = _state_paths(self.root, cfg)
        count = max(1, min(int(limit), 100))
        now = int(time.time())
        rows = lifecycle.collect_logical_enrollments(enrollments, bootstrap, now=now)
        items: list[dict[str, Any]] = []
        for row in reversed(rows[-count:]):
            rec = row.get("ticket_record") or row.get("enroll_record") or {}
            expires = rec.get("expires_at")
            try:
                remaining = max(0, int(expires) - now) if expires is not None else None
            except (TypeError, ValueError):
                remaining = None
            items.append(
                {
                    "id": str(row.get("id") or ""),
                    "type": str(row.get("type") or ""),
                    "state": str(row.get("state") or ""),
                    "created_at": str(rec.get("created_at") or ""),
                    "expires_at": expires,
                    "remaining_seconds": remaining,
                    "label": str(rec.get("label") or ""),
                    "note": str(rec.get("note") or ""),
                    "pair_error": str(row.get("pair_error") or ""),
                    "pre_approved": (
                        row.get("type") == "zero-touch"
                        and not row.get("pair_error")
                        and rec.get("pre_approved") is True
                    ),
                    "first_host_admission": (
                        "INVALID_PAIR" if row.get("pair_error")
                        else "APPROVED"
                        if row.get("type") == "zero-touch" and rec.get("pre_approved") is True
                        else "PENDING_APPROVAL"
                    ),
                }
            )
        return {"items": items, "total": len(rows)}
