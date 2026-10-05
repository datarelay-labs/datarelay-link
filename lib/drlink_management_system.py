"""Browser-safe DRLink 3.0 system/lifecycle management helpers.

This service exposes bounded system operations through the shared Core boundary.
It reuses canonical version, certificate, disaster-recovery, and support-bundle
tools without creating a parallel authority path. Artifact-producing operations
write only to Core-owned directories and never expose archive contents via Web.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import drlink_mcp_tls as mcp_tls
from drlink_control_db import ControlPlaneError
from drlink_control_plane import ControlPlane
from frp_version_identity import identity_from_kv, read_version_file

_MAX_TOOL_OUTPUT = 16 * 1024
AUDIT_RETENTION_CONTROL_DAYS_DEFAULT = 365
AUDIT_RETENTION_ACCESS_DAYS_DEFAULT = 90
AUDIT_RETENTION_MAX_EVENTS_DEFAULT = 500_000
AUDIT_RETENTION_MIN_DAYS = 1
AUDIT_RETENTION_MAX_DAYS = 3650
AUDIT_RETENTION_MIN_EVENTS = 1_000
AUDIT_RETENTION_MAX_EVENTS = 5_000_000
AUDIT_RETENTION_MAX_CAPACITY_PRUNE = 100_000
AUDIT_EXPORT_SCHEMA_VERSION = 1
AUDIT_EXPORT_MAX_EVENTS = 50_000
AUDIT_EXPORT_MAX_BYTES = 64 * 1024 * 1024


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

    @staticmethod
    def _redacted_certificate_view(view: dict[str, Any]) -> dict[str, Any]:
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
            "contact_email",
            "cloud_compatible",
            "private_ca_warning",
            "last_failure_class",
            "last_renewal_at",
        )
        return {key: view.get(key) for key in allowed}

    def certificate_status(self) -> dict[str, Any]:
        plane = ControlPlane(self.root, read_only=True)
        try:
            view = mcp_tls.status_view(plane, self.root)
        finally:
            plane.close()
        return self._redacted_certificate_view(view)

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

    def certificate_configure(
        self,
        settings: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        allowed = {
            "mode",
            "hostname",
            "contact_email",
            "acme_environment",
        }
        supplied = {
            key: settings[key]
            for key in allowed
            if key in settings
        }
        if not supplied:
            raise ControlPlaneError("At least one certificate setting is required.")
        mcp_tls.require_public_frontend(self.root)
        plane = ControlPlane(self.root)
        try:
            try:
                state = mcp_tls.configure_intent(
                    plane,
                    mode=supplied.get("mode"),
                    hostname=supplied.get("hostname"),
                    contact_email=supplied.get("contact_email"),
                    acme_environment=supplied.get("acme_environment"),
                    actor=actor_id,
                )
            except mcp_tls.McpTlsError as exc:
                raise ControlPlaneError(
                    "%s (%s)" % (exc, exc.failure_class)
                ) from exc
            plane._audit(
                revision=int(plane.current_revision()),
                action="web certificate configure",
                entity_type="certificate",
                entity_id=str(state.get("hostname") or "mcp-tls"),
                operation="configure",
                after="mode=%s" % str(state.get("mode") or ""),
                actor=actor_id,
                interface="WEB",
            )
            return {
                "status": "CONFIGURED",
                "certificate": self._redacted_certificate_view(
                    mcp_tls.status_view(plane, self.root)
                ),
                "authoritative_mutation": True,
            }
        finally:
            plane.close()

    def certificate_issue(self, *, actor_id: str) -> dict[str, Any]:
        mcp_tls.require_public_frontend(self.root)
        plane = ControlPlane(self.root)
        try:
            state = mcp_tls.load_state(plane)
            hostname = str(state.get("hostname") or "").strip()
            if not hostname:
                raise ControlPlaneError(
                    "Certificate hostname is not configured. Configure MCP TLS hostname first."
                )
            try:
                mcp_tls.issue_and_activate(
                    plane,
                    self.root,
                )
            except mcp_tls.McpTlsError as exc:
                plane._audit(
                    revision=int(plane.current_revision()),
                    action="web certificate issue",
                    entity_type="certificate",
                    entity_id=hostname,
                    operation="issue",
                    result="failed",
                    impact=str(exc.failure_class or "TLS_ISSUE_FAILED"),
                    actor=actor_id,
                    interface="WEB",
                )
                raise ControlPlaneError(
                    "%s (%s)" % (exc, exc.failure_class)
                ) from exc
            plane._audit(
                revision=int(plane.current_revision()),
                action="web certificate issue",
                entity_type="certificate",
                entity_id=hostname,
                operation="issue",
                actor=actor_id,
                interface="WEB",
            )
            return {
                "status": "ISSUED",
                "certificate": self._redacted_certificate_view(
                    mcp_tls.status_view(plane, self.root)
                ),
                "authoritative_mutation": True,
            }
        finally:
            plane.close()

    def certificate_import(
        self,
        *,
        cert_pem: str,
        key_pem: str,
        chain_pem: str = "",
        actor_id: str,
    ) -> dict[str, Any]:
        cert_text = str(cert_pem or "")
        key_text = str(key_pem or "")
        chain_text = str(chain_pem or "")
        if not cert_text.strip() or not key_text.strip():
            raise ControlPlaneError("Certificate and private key PEM are required.")
        if len(cert_text) > 32 * 1024 or len(key_text) > 24 * 1024 or len(chain_text) > 32 * 1024:
            raise ControlPlaneError("Certificate import material is too large.")
        mcp_tls.require_public_frontend(self.root)
        staging = self._owned_output_dir("var/lib/drlink/certificate-import-staging")
        plane = ControlPlane(self.root)
        try:
            state = mcp_tls.load_state(plane)
            hostname = str(state.get("hostname") or "").strip()
            if not hostname:
                raise ControlPlaneError(
                    "Certificate hostname is not configured. Configure MCP TLS hostname first."
                )
            with tempfile.TemporaryDirectory(prefix="web-cert-", dir=str(staging)) as tmp:
                work = Path(tmp)
                cert_path = work / "certificate.pem"
                key_path = work / "private-key.pem"
                chain_path = work / "chain.pem"
                cert_path.write_text(cert_text, encoding="utf-8")
                key_path.write_text(key_text, encoding="utf-8")
                os.chmod(cert_path, 0o600)
                os.chmod(key_path, 0o600)
                chain_arg: Optional[str] = None
                if chain_text.strip():
                    chain_path.write_text(chain_text, encoding="utf-8")
                    os.chmod(chain_path, 0o600)
                    chain_arg = str(chain_path)
                try:
                    mcp_tls.import_user_certificate(
                        plane,
                        self.root,
                        cert_path=str(cert_path),
                        key_path=str(key_path),
                        chain_path=chain_arg,
                    )
                except mcp_tls.McpTlsError as exc:
                    plane._audit(
                        revision=int(plane.current_revision()),
                        action="web certificate import",
                        entity_type="certificate",
                        entity_id=hostname,
                        operation="import",
                        result="failed",
                        impact=str(exc.failure_class or "TLS_IMPORT_FAILED"),
                        actor=actor_id,
                        interface="WEB",
                    )
                    raise ControlPlaneError(
                        "%s (%s)" % (exc, exc.failure_class)
                    ) from exc
            plane._audit(
                revision=int(plane.current_revision()),
                action="web certificate import",
                entity_type="certificate",
                entity_id=hostname,
                operation="import",
                actor=actor_id,
                interface="WEB",
            )
            return {
                "status": "IMPORTED",
                "certificate": self._redacted_certificate_view(
                    mcp_tls.status_view(plane, self.root)
                ),
                "authoritative_mutation": True,
            }
        finally:
            plane.close()

    def certificate_renew(self, *, actor_id: str) -> dict[str, Any]:
        mcp_tls.require_public_frontend(self.root)
        plane = ControlPlane(self.root)
        try:
            hostname = str(mcp_tls.load_state(plane).get("hostname") or "").strip()
            if not hostname:
                raise ControlPlaneError(
                    "Certificate hostname is not configured. Configure MCP TLS hostname first."
                )
            try:
                result = dict(
                    mcp_tls.renew_if_due(
                        plane,
                        self.root,
                        force=False,
                    )
                )
            except mcp_tls.McpTlsError as exc:
                plane._audit(
                    revision=int(plane.current_revision()),
                    action="web certificate renew",
                    entity_type="certificate",
                    entity_id=hostname,
                    operation="renew",
                    result="failed",
                    impact=str(exc.failure_class or "TLS_RENEW_FAILED"),
                    actor=actor_id,
                    interface="WEB",
                )
                raise ControlPlaneError(
                    "%s (%s)" % (exc, exc.failure_class)
                ) from exc
            renewed = bool(result.get("renewed"))
            reason = str(result.get("reason") or ("renewed" if renewed else "unknown"))
            failure_class = str(result.get("failure_class") or "")
            plane._audit(
                revision=int(plane.current_revision()),
                action="web certificate renew",
                entity_type="certificate",
                entity_id=hostname,
                operation="renew",
                result="ok" if renewed or reason in (
                    "not_due",
                    "backoff",
                    "renewal_not_applicable",
                    "renewal_disabled",
                ) else "failed",
                impact=failure_class or reason,
                actor=actor_id,
                interface="WEB",
            )
            view = self._redacted_certificate_view(
                mcp_tls.status_view(plane, self.root)
            )
            return {
                "renewed": renewed,
                "reason": reason,
                "failure_class": failure_class,
                "certificate": view,
                "authoritative_mutation": renewed or reason == "failed",
            }
        finally:
            plane.close()

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

    def _owned_output_dir(self, relative: str) -> Path:
        base = self.root_path.resolve()
        directory = self.root_path / relative
        current = self.root_path
        for part in Path(relative).parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise ControlPlaneError(
                    "Refusing system artifact directory that traverses a symlink."
                )
        existed = directory.exists()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        resolved = directory.resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ControlPlaneError(
                "System artifact directory escaped the Data Relay Link root."
            ) from exc
        if not existed:
            os.chmod(resolved, 0o700)
        return resolved

    @staticmethod
    def _artifact_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _artifact_path(
        self,
        *,
        directory: str,
        prefix: str,
    ) -> tuple[str, Path]:
        output_dir = self._owned_output_dir(directory)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = "%s-%s-%s.tar.gz" % (prefix, stamp, secrets.token_hex(4))
        actual = output_dir / name
        canonical = "/" + str(Path(directory) / name)
        return canonical, actual

    def _artifact_env(self, *, actor_id: str) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("DRLINK_CONFIRM", None)
        env.pop("FRP_RESTORE_YES", None)
        env["DRLINK_ACTOR"] = str(actor_id or "").strip()
        env["DRLINK_INTERFACE"] = "WEB"
        if self.root and self.root != "/":
            env["FRP_DEPLOY_TEST_ROOT"] = self.root
        return env

    def _run_artifact_tool(
        self,
        *,
        command: list[str],
        canonical_path: str,
        actual_path: Path,
        actor_id: str,
        timeout: int,
        protected: bool,
        sanitized: bool,
    ) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=self._artifact_env(actor_id=actor_id),
            )
        except subprocess.TimeoutExpired as exc:
            raise ControlPlaneError("System artifact generation timed out.") from exc
        if proc.returncode != 0:
            detail = _safe_text(proc.stderr or proc.stdout).strip()
            if detail:
                raise ControlPlaneError(
                    "System artifact generation failed: %s" % detail
                )
            raise ControlPlaneError("System artifact generation failed.")
        if not actual_path.is_file() or actual_path.is_symlink():
            raise ControlPlaneError(
                "System artifact generation reported success without a safe output file."
            )
        return {
            "status": "CREATED",
            "path": canonical_path,
            "size_bytes": int(actual_path.stat().st_size),
            "sha256": self._artifact_digest(actual_path),
            "protected_artifact": bool(protected),
            "sanitized": bool(sanitized),
            "download_exposed": False,
            "authoritative_mutation": False,
        }

    @staticmethod
    def _audit_retention_config_from_conn(conn) -> dict[str, int]:
        defaults = {
            "audit_retention_control_days": AUDIT_RETENTION_CONTROL_DAYS_DEFAULT,
            "audit_retention_access_days": AUDIT_RETENTION_ACCESS_DAYS_DEFAULT,
            "audit_retention_max_events": AUDIT_RETENTION_MAX_EVENTS_DEFAULT,
        }
        out: dict[str, int] = {}
        for key, default in defaults.items():
            row = conn.execute(
                "SELECT value FROM system_meta WHERE key=?", (key,)
            ).fetchone()
            try:
                value = int(row[0]) if row is not None else int(default)
            except (TypeError, ValueError):
                value = int(default)
            out[key] = value
        return {
            "control_days": out["audit_retention_control_days"],
            "access_days": out["audit_retention_access_days"],
            "max_events": out["audit_retention_max_events"],
        }

    @staticmethod
    def _validate_audit_retention(
        *, control_days: int, access_days: int, max_events: int
    ) -> dict[str, int]:
        try:
            control = int(control_days)
            access = int(access_days)
            capacity = int(max_events)
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError(
                "Audit retention values must be integers."
            ) from exc
        if control < AUDIT_RETENTION_MIN_DAYS or control > AUDIT_RETENTION_MAX_DAYS:
            raise ControlPlaneError(
                "CONTROL retention must be between %d and %d days."
                % (AUDIT_RETENTION_MIN_DAYS, AUDIT_RETENTION_MAX_DAYS)
            )
        if access < AUDIT_RETENTION_MIN_DAYS or access > AUDIT_RETENTION_MAX_DAYS:
            raise ControlPlaneError(
                "ACCESS_DECISION retention must be between %d and %d days."
                % (AUDIT_RETENTION_MIN_DAYS, AUDIT_RETENTION_MAX_DAYS)
            )
        if capacity < AUDIT_RETENTION_MIN_EVENTS or capacity > AUDIT_RETENTION_MAX_EVENTS:
            raise ControlPlaneError(
                "Audit event capacity must be between %d and %d."
                % (AUDIT_RETENTION_MIN_EVENTS, AUDIT_RETENTION_MAX_EVENTS)
            )
        return {
            "control_days": control,
            "access_days": access,
            "max_events": capacity,
        }

    def audit_retention_status(self) -> dict[str, Any]:
        from drlink_control_db import connect_read_only, db_path

        conn = connect_read_only(root=self.root)
        try:
            config = self._audit_retention_config_from_conn(conn)
            rows = conn.execute(
                "SELECT COALESCE(category,'CONTROL') AS category,COUNT(*) AS n "
                "FROM audit_events GROUP BY COALESCE(category,'CONTROL') "
                "ORDER BY category"
            ).fetchall()
            counts = {str(row["category"]): int(row["n"] or 0) for row in rows}
            total = sum(counts.values())
            oldest = conn.execute(
                "SELECT occurred_at FROM audit_events WHERE occurred_at IS NOT NULL "
                "ORDER BY occurred_at ASC,id ASC LIMIT 1"
            ).fetchone()
            newest = conn.execute(
                "SELECT occurred_at FROM audit_events WHERE occurred_at IS NOT NULL "
                "ORDER BY occurred_at DESC,id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        path = db_path(self.root)
        try:
            db_size = int(path.stat().st_size)
        except OSError:
            db_size = 0
        return {
            "config": config,
            "counts": counts,
            "total_events": total,
            "oldest_event_at": str(oldest[0]) if oldest else "",
            "newest_event_at": str(newest[0]) if newest else "",
            "db_size_bytes": db_size,
            "capacity_exceeded": total > int(config["max_events"]),
            "capacity_policy": (
                "Age retention applies separately to CONTROL/SECURITY_LIFECYCLE and "
                "ACCESS_DECISION. Capacity pruning removes oldest ACCESS_DECISION only; "
                "CONTROL/SECURITY is never silently deleted for capacity."
            ),
            "authoritative_mutation": False,
        }

    def audit_retention_configure(
        self,
        *,
        control_days: int,
        access_days: int,
        max_events: int,
        actor_id: str,
        interface: str,
    ) -> dict[str, Any]:
        new_config = self._validate_audit_retention(
            control_days=control_days,
            access_days=access_days,
            max_events=max_events,
        )
        plane = ControlPlane(self.root)
        try:
            old_config = self._audit_retention_config_from_conn(plane.conn)
            plane.conn.execute("BEGIN IMMEDIATE")
            try:
                for key, value in (
                    ("audit_retention_control_days", new_config["control_days"]),
                    ("audit_retention_access_days", new_config["access_days"]),
                    ("audit_retention_max_events", new_config["max_events"]),
                ):
                    plane.conn.execute(
                        "INSERT OR REPLACE INTO system_meta(key,value) VALUES (?,?)",
                        (key, str(value)),
                    )
                plane._audit(
                    revision=0,
                    action="configure audit retention",
                    entity_type="audit-retention",
                    entity_id="global",
                    operation="audit.retention.configure",
                    before=json.dumps(old_config, sort_keys=True, separators=(",", ":")),
                    after=json.dumps(new_config, sort_keys=True, separators=(",", ":")),
                    impact="retention configuration only; no events deleted",
                    result="ok",
                    actor=actor_id,
                    interface=interface,
                )
                plane.conn.execute("COMMIT")
            except Exception:
                plane.conn.execute("ROLLBACK")
                raise
        finally:
            plane.close()
        return {
            "status": "CONFIGURED",
            "config": new_config,
            "previous": old_config,
            "authoritative_mutation": True,
            "configuration_revision_created": False,
        }

    def audit_retention_run(
        self,
        *,
        actor_id: str,
        interface: str,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        plane = ControlPlane(self.root)
        try:
            config = self._audit_retention_config_from_conn(plane.conn)
            control_cutoff = (
                current - timedelta(days=int(config["control_days"]))
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            access_cutoff = (
                current - timedelta(days=int(config["access_days"]))
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            plane.conn.execute("BEGIN IMMEDIATE")
            try:
                control_deleted = plane.conn.execute(
                    "DELETE FROM audit_events "
                    "WHERE category IN ('CONTROL','SECURITY_LIFECYCLE') "
                    "AND occurred_at IS NOT NULL AND occurred_at < ?",
                    (control_cutoff,),
                ).rowcount
                access_deleted = plane.conn.execute(
                    "DELETE FROM audit_events "
                    "WHERE category='ACCESS_DECISION' "
                    "AND occurred_at IS NOT NULL AND occurred_at < ?",
                    (access_cutoff,),
                ).rowcount
                total = int(
                    plane.conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
                    or 0
                )
                target_before_audit = max(0, int(config["max_events"]) - 1)
                excess = max(0, total - target_before_audit)
                prune_requested = min(
                    excess, AUDIT_RETENTION_MAX_CAPACITY_PRUNE
                )
                capacity_ids = [
                    int(row[0])
                    for row in plane.conn.execute(
                        "SELECT id FROM audit_events "
                        "WHERE category='ACCESS_DECISION' "
                        "ORDER BY occurred_at ASC,id ASC LIMIT ?",
                        (prune_requested,),
                    ).fetchall()
                ] if prune_requested else []
                capacity_deleted = 0
                for offset in range(0, len(capacity_ids), 500):
                    chunk = capacity_ids[offset : offset + 500]
                    placeholders = ",".join("?" for _ in chunk)
                    capacity_deleted += plane.conn.execute(
                        "DELETE FROM audit_events WHERE id IN (%s)" % placeholders,
                        tuple(chunk),
                    ).rowcount
                remaining_before_audit = int(
                    plane.conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
                    or 0
                )
                remaining_excess = max(
                    0, remaining_before_audit - target_before_audit
                )
                summary = {
                    "control_deleted": int(control_deleted or 0),
                    "access_deleted": int(access_deleted or 0),
                    "capacity_deleted": int(capacity_deleted or 0),
                    "remaining_excess": remaining_excess,
                    "control_cutoff": control_cutoff,
                    "access_cutoff": access_cutoff,
                    "max_events": int(config["max_events"]),
                }
                plane._audit(
                    revision=0,
                    action="run audit retention",
                    entity_type="audit-retention",
                    entity_id="global",
                    operation="audit.retention.run",
                    after=json.dumps(summary, sort_keys=True, separators=(",", ":")),
                    impact=(
                        "explicit age/capacity retention; capacity pruning targets "
                        "ACCESS_DECISION only"
                    ),
                    result="ok" if remaining_excess == 0 else "capacity_guardrail_exceeded",
                    actor=actor_id,
                    interface=interface,
                )
                plane.conn.execute("COMMIT")
            except Exception:
                plane.conn.execute("ROLLBACK")
                raise
        finally:
            plane.close()
        return {
            "status": (
                "COMPLETE" if summary["remaining_excess"] == 0 else "ATTENTION_REQUIRED"
            ),
            "config": config,
            **summary,
            "capacity_guardrail_satisfied": summary["remaining_excess"] == 0,
            "max_capacity_prune_per_run": AUDIT_RETENTION_MAX_CAPACITY_PRUNE,
            "authoritative_mutation": True,
            "configuration_revision_created": False,
        }

    def audit_export_create(
        self,
        *,
        filters: dict[str, Any],
        actor_id: str,
        interface: str,
    ) -> dict[str, Any]:
        from drlink_management_service import ManagementQueryService

        allowed = {
            "start",
            "end",
            "category",
            "event_type",
            "actor",
            "resource",
            "result",
            "correlation",
        }
        unknown = sorted(set(filters or {}) - allowed)
        if unknown:
            raise ControlPlaneError(
                "Audit export has unsupported filters: %s." % ", ".join(unknown)
            )
        clean = {
            key: str(value or "").strip()
            for key, value in dict(filters or {}).items()
            if str(value or "").strip()
        }
        output_dir = self._owned_output_dir("var/lib/drlink/audit-exports")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = "drlink-audit-%s-%s.ndjson" % (stamp, secrets.token_hex(4))
        actual = output_dir / name
        canonical = "/" + str(Path("var/lib/drlink/audit-exports") / name)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".drlink-audit-", suffix=".tmp", dir=str(output_dir)
        )
        count = 0
        bytes_written = 0
        cursor: Optional[str] = None
        try:
            with os.fdopen(fd, "wb") as handle, ManagementQueryService(
                self.root
            ) as query:
                meta = {
                    "record_type": "audit-export-meta",
                    "schema_version": AUDIT_EXPORT_SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "filters": clean,
                    "max_events": AUDIT_EXPORT_MAX_EVENTS,
                    "max_bytes": AUDIT_EXPORT_MAX_BYTES,
                }
                first = (
                    json.dumps(meta, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode("utf-8")
                handle.write(first)
                bytes_written += len(first)
                while True:
                    page = query.audit_query(
                        start=clean.get("start"),
                        end=clean.get("end"),
                        category=clean.get("category"),
                        event_type=clean.get("event_type"),
                        actor=clean.get("actor"),
                        resource=clean.get("resource"),
                        result=clean.get("result"),
                        correlation=clean.get("correlation"),
                        cursor=cursor,
                        limit=200,
                    )
                    for item in page.items:
                        if count >= AUDIT_EXPORT_MAX_EVENTS:
                            raise ControlPlaneError(
                                "Audit export exceeds the %d-event bound."
                                % AUDIT_EXPORT_MAX_EVENTS
                            )
                        line = (
                            json.dumps(
                                {
                                    "record_type": "audit-event",
                                    "schema_version": AUDIT_EXPORT_SCHEMA_VERSION,
                                    "event": item,
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                            + "\n"
                        ).encode("utf-8")
                        if bytes_written + len(line) > AUDIT_EXPORT_MAX_BYTES:
                            raise ControlPlaneError(
                                "Audit export exceeds the %d-byte bound."
                                % AUDIT_EXPORT_MAX_BYTES
                            )
                        handle.write(line)
                        bytes_written += len(line)
                        count += 1
                    cursor = page.next_cursor
                    if not cursor:
                        break
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, actual)
            os.chmod(actual, 0o600)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

        plane = ControlPlane(self.root)
        try:
            plane._audit(
                revision=0,
                action="export audit",
                entity_type="audit-export",
                entity_id=canonical,
                operation="audit.export",
                after=json.dumps(
                    {
                        "path": canonical,
                        "event_count": count,
                        "filters": clean,
                        "sha256": self._artifact_digest(actual),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                impact="manual filtered NDJSON export; no audit rows modified",
                result="ok",
                actor=actor_id,
                interface=interface,
            )
        finally:
            plane.close()
        return {
            "status": "CREATED",
            "path": canonical,
            "size_bytes": int(actual.stat().st_size),
            "sha256": self._artifact_digest(actual),
            "event_count": count,
            "filters": clean,
            "schema_version": AUDIT_EXPORT_SCHEMA_VERSION,
            "sanitized": True,
            "download_exposed": False,
            "authoritative_mutation": False,
        }

    def inventory_export_create(self, *, actor_id: str) -> dict[str, Any]:
        """Create a bounded sanitized inventory NDJSON artifact."""
        from drlink_control_db import connect_read_only

        limits = {
            "managed_hosts": 100,
            "remote_services": 1000,
            "managed_host_groups": 200,
            "managed_host_tags": 1000,
        }
        conn = connect_read_only(root=self.root)
        try:
            counts = {
                "managed_hosts": int(
                    conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] or 0
                ),
                "remote_services": int(
                    conn.execute(
                        "SELECT COUNT(*) FROM published_services WHERE released=0"
                    ).fetchone()[0]
                    or 0
                ),
                "managed_host_groups": int(
                    conn.execute("SELECT COUNT(*) FROM client_groups").fetchone()[0] or 0
                ),
                "managed_host_tags": int(
                    conn.execute("SELECT COUNT(*) FROM client_tags").fetchone()[0] or 0
                ),
            }
            exceeded = [
                key for key, value in counts.items() if value > limits[key]
            ]
            if exceeded:
                raise ControlPlaneError(
                    "Inventory export exceeds bounded 3.0 limits: %s."
                    % ", ".join(
                        "%s=%s>%s" % (key, counts[key], limits[key])
                        for key in exceeded
                    )
                )

            records: list[dict[str, Any]] = []
            for row in conn.execute(
                "SELECT id,label,hostname,status,trust_status,connected,last_seen,"
                "agent_heartbeat_at,agent_lifecycle_state,agent_platform,agent_version "
                "FROM clients ORDER BY LOWER(COALESCE(NULLIF(label,''),NULLIF(hostname,''),id)),id"
            ):
                records.append(
                    {
                        "resource_type": "managed-host",
                        "id": row["id"],
                        "label": row["label"] or "",
                        "hostname": row["hostname"] or "",
                        "status": row["status"],
                        "trust_status": row["trust_status"],
                        "connected": bool(row["connected"]),
                        "last_seen": row["last_seen"],
                        "agent_heartbeat_at": row["agent_heartbeat_at"],
                        "agent_lifecycle_state": row["agent_lifecycle_state"],
                        "agent_platform": row["agent_platform"],
                        "agent_version": row["agent_version"],
                    }
                )
            for row in conn.execute(
                "SELECT s.id,s.name,s.client_id,"
                "COALESCE(NULLIF(c.label,''),NULLIF(c.hostname,''),c.id) AS managed_host,"
                "s.service_type,s.target_mode,s.target_host,s.target_port,s.public_port,"
                "s.enabled FROM published_services s "
                "LEFT JOIN clients c ON c.id=s.client_id "
                "WHERE s.released=0 ORDER BY LOWER(s.name),s.id"
            ):
                records.append(
                    {
                        "resource_type": "remote-service",
                        "id": row["id"],
                        "name": row["name"],
                        "managed_host_id": row["client_id"],
                        "managed_host": row["managed_host"] or row["client_id"],
                        "service_type": row["service_type"],
                        "target_mode": row["target_mode"],
                        "target_host": row["target_host"],
                        "target_port": row["target_port"],
                        "public_port": row["public_port"],
                        "enabled": bool(row["enabled"]),
                    }
                )
            for row in conn.execute(
                "SELECT id,name,description FROM client_groups ORDER BY LOWER(name),id"
            ):
                members = [
                    str(item[0])
                    for item in conn.execute(
                        "SELECT client_id FROM client_group_members "
                        "WHERE group_id=? ORDER BY client_id",
                        (row["id"],),
                    )
                ]
                records.append(
                    {
                        "resource_type": "managed-host-group",
                        "id": row["id"],
                        "name": row["name"],
                        "description": row["description"] or "",
                        "managed_host_ids": members,
                    }
                )
            for row in conn.execute(
                "SELECT client_id,key,value FROM client_tags "
                "ORDER BY client_id,key"
            ):
                records.append(
                    {
                        "resource_type": "managed-host-tag",
                        "managed_host_id": row["client_id"],
                        "key": row["key"],
                        "value": row["value"],
                    }
                )
        finally:
            conn.close()

        output_dir = self._owned_output_dir("var/lib/drlink/exports")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = "drlink-inventory-%s-%s.ndjson" % (stamp, secrets.token_hex(4))
        actual = output_dir / name
        canonical = "/" + str(Path("var/lib/drlink/exports") / name)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".drlink-inventory-", suffix=".tmp", dir=str(output_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                meta = {
                    "record_type": "inventory-export-meta",
                    "schema_version": 1,
                    "generated_at": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "actor": str(actor_id or "")[:256],
                    "counts": counts,
                    "limits": limits,
                    "bounded": True,
                    "authoritative": False,
                }
                handle.write(
                    json.dumps(meta, sort_keys=True, separators=(",", ":"))
                    + "\n"
                )
                for record in records:
                    handle.write(
                        json.dumps(record, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, actual)
            os.chmod(actual, 0o600)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
        return {
            "status": "CREATED",
            "path": canonical,
            "size_bytes": int(actual.stat().st_size),
            "sha256": self._artifact_digest(actual),
            "record_count": len(records),
            "counts": counts,
            "limits": limits,
            "sanitized": True,
            "download_exposed": False,
            "authoritative_mutation": False,
        }

    def backup_create(self, *, actor_id: str) -> dict[str, Any]:
        canonical, actual = self._artifact_path(
            directory="var/lib/drlink/backups",
            prefix="server-backup",
        )
        tool = _tool_path(self.root_path, "frp-backup")
        return self._run_artifact_tool(
            command=[sys.executable, str(tool), str(actual)],
            canonical_path=canonical,
            actual_path=actual,
            actor_id=actor_id,
            timeout=120,
            protected=True,
            sanitized=False,
        )

    def restore_apply(
        self,
        path: str,
        *,
        actor_id: str,
        confirmation: str,
    ) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != "RESTORE":
            raise ControlPlaneError(
                "Restore requires explicit confirmation 'RESTORE'."
            )
        requested, actual = self._backup_target(path)
        validation = self.backup_validate(requested)
        if not bool(validation.get("valid")):
            detail = _safe_text(
                str(validation.get("error") or validation.get("output") or "")
            ).strip()
            raise ControlPlaneError(
                "Backup validation failed before restore."
                + ((" " + detail) if detail else "")
            )
        tool = _tool_path(self.root_path, "frp-restore")
        try:
            proc = subprocess.run(
                [sys.executable, str(tool), "--yes", str(actual)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
                env=self._artifact_env(actor_id=actor_id),
            )
        except subprocess.TimeoutExpired as exc:
            raise ControlPlaneError(
                "Restore timed out. Check recovery status before retrying."
            ) from exc
        output = _safe_text(proc.stdout)
        error = _safe_text(proc.stderr)
        if proc.returncode != 0:
            detail = (error or output).strip()
            raise ControlPlaneError(
                "Restore failed through the canonical recovery path."
                + ((" " + detail) if detail else "")
            )
        return {
            "status": "RESTORED",
            "path": requested,
            "summary": "Restore completed through the canonical recovery path.",
            "web_reauth_required": True,
            "sessions_must_be_revoked": True,
            "recovery_authority": True,
            "authoritative_mutation": True,
        }

    def support_bundle_create(self, *, actor_id: str) -> dict[str, Any]:
        canonical, actual = self._artifact_path(
            directory="var/lib/drlink/support-bundles",
            prefix="drlink-support",
        )
        tool = _tool_path(self.root_path, "frp-support-bundle")
        return self._run_artifact_tool(
            command=[sys.executable, str(tool), "--output", str(actual)],
            canonical_path=canonical,
            actual_path=actual,
            actor_id=actor_id,
            timeout=60,
            protected=False,
            sanitized=True,
        )

    @staticmethod
    def _update_state(output: str) -> str:
        for line in str(output or "").splitlines():
            key, sep, value = line.partition(":")
            if not sep or key.strip().lower() != "update":
                continue
            normalized = value.strip().lower()
            if normalized == "available":
                return "AVAILABLE"
            if normalized in ("not needed", "up to date", "current"):
                return "NOT_NEEDED"
        return "UNKNOWN"

    def update_check(self, target: str) -> dict[str, Any]:
        normalized = str(target or "").strip().lower()
        if normalized == "product":
            tool = _tool_path(self.root_path, "frp-project-update")
            command = ["bash", str(tool), "--check"]
            timeout = 180
        elif normalized in ("engine", "relay-engine"):
            tool = _tool_path(self.root_path, "frp-update")
            command = ["bash", str(tool), "--check"]
            timeout = 120
            normalized = "engine"
        else:
            raise ControlPlaneError("Update target must be product or engine.")
        env = os.environ.copy()
        env.pop("DRLINK_CONFIRM", None)
        env.pop("FRP_RESTORE_YES", None)
        if self.root and self.root != "/":
            if normalized == "product":
                env["FRP_SERVER_TEST_ROOT"] = self.root
            else:
                env["FRP_UPDATE_ROOT"] = self.root
                env["FRP_UPDATE_TEST_HARNESS"] = "1"
                env["FRP_UPDATE_HOOK_SKIP_SYSTEMD"] = "1"
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ControlPlaneError("Update check timed out.") from exc
        output = _safe_text(proc.stdout)
        error = _safe_text(proc.stderr)
        if proc.returncode != 0:
            detail = (error or output).strip()
            raise ControlPlaneError(
                "Update check failed."
                + ((" " + detail) if detail else "")
            )
        return {
            "target": normalized,
            "status": "CHECKED",
            "availability": self._update_state(output),
            "output": output,
            "error": error,
            "authoritative_mutation": False,
        }

    def update_engine_apply(self, *, actor_id: str) -> dict[str, Any]:
        tool = _tool_path(self.root_path, "frp-update")
        env = self._artifact_env(actor_id=actor_id)
        if self.root and self.root != "/":
            env["FRP_UPDATE_ROOT"] = self.root
            env["FRP_UPDATE_TEST_HARNESS"] = "1"
            env["FRP_UPDATE_HOOK_SKIP_SYSTEMD"] = "1"
        try:
            proc = subprocess.run(
                ["bash", str(tool)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ControlPlaneError(
                "Relay Engine update timed out. Check update/recovery status before retrying."
            ) from exc
        output = _safe_text(proc.stdout)
        error = _safe_text(proc.stderr)
        if proc.returncode != 0:
            combined = (output + "\n" + error).strip()
            suffix = " RECOVERY_REQUIRED" if "RECOVERY_REQUIRED" in combined else ""
            detail = (error or output).strip()
            raise ControlPlaneError(
                "Relay Engine update failed.%s%s"
                % (
                    suffix,
                    ((" " + detail) if detail else ""),
                )
            )
        plane = ControlPlane(self.root)
        try:
            plane._audit(
                revision=int(plane.current_revision()),
                action="web relay-engine update",
                entity_type="system-update",
                entity_id="relay-engine",
                operation="update",
                actor=actor_id,
                interface="WEB",
            )
        finally:
            plane.close()
        return {
            "target": "engine",
            "status": "UPDATED",
            "output": output,
            "authoritative_mutation": True,
        }

    def status(self) -> dict[str, Any]:
        backup_dir = self.root_path / "var/lib/drlink/backups"
        support_dir = self.root_path / "var/lib/drlink/support-bundles"
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
            "support_bundle": {
                "directory": "/var/lib/drlink/support-bundles",
                "directory_present": support_dir.is_dir(),
                "create_available": self._tool_available("frp-support-bundle"),
                "sanitized": True,
            },
            "update": {
                "product_check_available": self._tool_available("frp-project-update"),
                "product_apply_via_web": False,
                "product_apply_phase": "DRL3-7_WEB_PACKAGE_LIFECYCLE",
                "engine_check_available": self._tool_available("frp-update"),
                "engine_apply_via_web": self._tool_available("frp-update"),
            },
        }

    def _tool_available(self, name: str) -> bool:
        try:
            _tool_path(self.root_path, name)
        except ControlPlaneError:
            return False
        return True
