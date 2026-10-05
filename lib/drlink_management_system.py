"""Browser-safe DRLink 3.0 system/lifecycle management helpers.

This service exposes only bounded OBSERVE/TEST operations. It reuses the
canonical version, certificate, and disaster-recovery validators without
creating a parallel authority path.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import drlink_mcp_tls as mcp_tls
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from frp_version_identity import identity_from_kv, read_version_file

_MAX_TOOL_OUTPUT = 16 * 1024


def _root_path(root: Optional[str]) -> Path:
    text = str(root or "").strip()
    return Path(text) if text and text != "/" else Path("/")


def _tool_path(root: Path, name: str) -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parent.parent / "tools" / name,
        root / "usr/local/sbin" / name,
        root / "usr/local/lib/drlink" / name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ControlPlaneError("%s is not installed." % name)


def _safe_text(value: str) -> str:
    text = str(value or "")
    if len(text) > _MAX_TOOL_OUTPUT:
        return text[:_MAX_TOOL_OUTPUT] + "\n[output truncated]"
    return text


class ManagementSystemService:
    """Core-owned system status and validation operations for Web Management."""

    def __init__(self, root: Optional[str] = None):
        self.root = str(root or "")
        self.root_path = _root_path(root)

    def _read_identity(self) -> dict[str, Any]:
        version_path = self.root_path / "etc/drlink/version"
        values: dict[str, str] = {}
        if version_path.is_file():
            try:
                values = read_version_file(version_path)
            except (OSError, ValueError):
                values = {}
        project_version = str(values.get("PROJECT_VERSION") or "unknown")
        display_identity = project_version
        channel = str(values.get("RELEASE_CHANNEL") or "unknown")
        source_ref = str(values.get("SOURCE_REF") or "")
        source_head = str(values.get("SOURCE_HEAD") or "")
        if project_version != "unknown":
            try:
                derived = identity_from_kv(values)
            except ValueError:
                derived = {}
            display_identity = str(derived.get("display_identity") or display_identity)
            channel = str(derived.get("channel") or channel)
            source_ref = str(derived.get("source_ref") or source_ref)
            source_head = str(derived.get("source_head") or source_head)
        return {
            "project_version": project_version,
            "display_identity": display_identity,
            "relay_engine_version": str(values.get("FRP_VERSION") or "unknown"),
            "channel": channel,
            "source_ref": source_ref or "unknown",
            "source_head": source_head or "unknown",
            "bundle_sha256": str(values.get("BUNDLE_SHA256") or ""),
        }

    def certificate_status(self) -> dict[str, Any]:
        plane = ControlPlane(self.root, read_only=True)
        try:
            view = mcp_tls.status_view(plane, self.root)
        finally:
            plane.close()
        allowed = (
            "url",
            "frontend_available",
            "deployment_mode",
            "mode",
            "hostname",
            "certificate",
            "issuer",
            "expires",
            "days_remaining",
            "auto_renewal",
            "fingerprint_sha256",
            "acme_environment",
            "cloud_compatible",
            "private_ca_warning",
            "last_failure_class",
            "last_renewal_at",
        )
        return {key: view.get(key) for key in allowed}

    def certificate_preflight(self) -> dict[str, Any]:
        plane = ControlPlane(self.root, read_only=True)
        try:
            state = mcp_tls.load_state(plane)
        finally:
            plane.close()
        hostname = str(state.get("hostname") or "").strip()
        if not hostname:
            raise ControlPlaneError(
                "Certificate hostname is not configured. Configure MCP TLS hostname first."
            )
        mode = str(state.get("mode") or mcp_tls.DEFAULT_PUBLIC_CLOUD_TLS_MODE)
        require_public = mode == mcp_tls.MODE_AUTO_ACME
        result = dict(
            mcp_tls.preflight_hostname(
                hostname,
                require_public_dns=require_public,
            )
        )
        result["mode"] = mode
        result["authoritative_mutation"] = False
        return result

    def _backup_target(self, path: str) -> tuple[str, Path]:
        requested = str(path or "").strip()
        if not requested:
            raise ControlPlaneError("Backup path is required.")
        canonical_prefix = "/var/lib/drlink/backups/"
        if not requested.startswith(canonical_prefix):
            raise ControlPlaneError(
                "Web backup validation is limited to /var/lib/drlink/backups/."
            )
        relative = requested[len(canonical_prefix) :]
        if not relative or relative in (".", ".."):
            raise ControlPlaneError("A backup archive file is required.")
        backup_root = (self.root_path / "var/lib/drlink/backups").resolve()
        candidate = (backup_root / relative).resolve()
        try:
            candidate.relative_to(backup_root)
        except ValueError as exc:
            raise ControlPlaneError(
                "Backup path must remain under /var/lib/drlink/backups/."
            ) from exc
        return requested, candidate

    def backup_validate(self, path: str) -> dict[str, Any]:
        requested, target = self._backup_target(path)
        tool = _tool_path(self.root_path, "frp-restore")
        env = os.environ.copy()
        env.pop("DRLINK_CONFIRM", None)
        env.pop("FRP_RESTORE_YES", None)
        if self.root and self.root != "/":
            env["FRP_DEPLOY_TEST_ROOT"] = self.root
        try:
            proc = subprocess.run(
                [sys.executable, str(tool), "--validate", str(target)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ControlPlaneError("Backup validation timed out.") from exc
        output = _safe_text(proc.stdout)
        error = _safe_text(proc.stderr)
        return {
            "path": requested,
            "valid": proc.returncode == 0,
            "returncode": int(proc.returncode),
            "output": output,
            "error": error,
            "authoritative_mutation": False,
        }

    def status(self) -> dict[str, Any]:
        backup_dir = self.root_path / "var/lib/drlink/backups"
        return {
            "read_only": True,
            "side_effect_free": True,
            "identity": self._read_identity(),
            "certificate": self.certificate_status(),
            "backup": {
                "directory": "/var/lib/drlink/backups",
                "directory_present": backup_dir.is_dir(),
                "create_available": self._tool_available("frp-backup"),
                "validate_available": self._tool_available("frp-restore"),
                "restore_available": self._tool_available("frp-restore"),
            },
        }

    def _tool_available(self, name: str) -> bool:
        try:
            _tool_path(self.root_path, name)
        except ControlPlaneError:
            return False
        return True
