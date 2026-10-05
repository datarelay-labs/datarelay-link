"""Fail-closed exact-build coordinator for Web-triggered Core product updates.

The browser never executes the project updater directly.  It writes a bounded,
root-owned request and activates a fixed systemd one-shot.  The worker obtains
the optional Web package from the same immutable source ref as the Core
candidate, verifies its SHA256, stops Web, updates Core through the canonical
project updater, proves the installed Core source identity matches the Web
package, and only then reinstalls/restarts Web.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

JOB_RE = re.compile(r"^pupd_[0-9a-f]{24}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMMUTABLE_REF_RE = re.compile(
    r"^(?:[0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?)$"
)
VALID_CHANNELS = frozenset({"development", "preview", "stable"})
WEB_ARTIFACT = "dist/data-relay-link-web.tar.gz"
RAW_BASE = "https://raw.githubusercontent.com/datarelay-labs/datarelay-link"
MAX_STATUS_ERROR = 2048


class ProductUpdateError(RuntimeError):
    pass


def _root(root: Optional[str]) -> Path:
    text = str(root or "").strip()
    return Path(text) if text and text != "/" else Path("/")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir(root: Optional[str]) -> Path:
    return _root(root) / "var/lib/drlink/product-update"


def _validate_job_id(job_id: str) -> str:
    text = str(job_id or "").strip()
    if not JOB_RE.fullmatch(text):
        raise ProductUpdateError("Invalid product update job ID.")
    return text


def _validate_sha(value: str, label: str = "source HEAD") -> str:
    text = str(value or "").strip().lower()
    if not SHA_RE.fullmatch(text):
        raise ProductUpdateError("%s must be an exact 40-character Git SHA." % label)
    return text


def _validate_ref(value: str) -> str:
    text = str(value or "").strip()
    if not IMMUTABLE_REF_RE.fullmatch(text):
        raise ProductUpdateError(
            "Web product update requires an immutable exact-SHA, stable tag, or release-candidate tag."
        )
    return text


def _atomic_json(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp-%d" % os.getpid())
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            os.write(fd, data.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        os.chmod(path, mode)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProductUpdateError("Product update state is unreadable.") from exc
    if not isinstance(value, dict):
        raise ProductUpdateError("Product update state is invalid.")
    return value


def request_path(root: Optional[str], job_id: str) -> Path:
    return _state_dir(root) / (_validate_job_id(job_id) + ".request.json")


def status_path(root: Optional[str], job_id: str) -> Path:
    return _state_dir(root) / (_validate_job_id(job_id) + ".status.json")


def read_installed_identity(root: Optional[str]) -> dict[str, str]:
    path = _root(root) / "etc/drlink/version"
    values: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = raw.partition("=")
            if sep:
                values[key.strip()] = value.strip()
    except OSError as exc:
        raise ProductUpdateError("Installed product identity is unavailable.") from exc
    return {
        "project_version": values.get("PROJECT_VERSION", ""),
        "release_channel": values.get("RELEASE_CHANNEL", ""),
        "source_ref": values.get("SOURCE_REF", ""),
        "source_head": values.get("SOURCE_HEAD", ""),
        "bundle_sha256": values.get("BUNDLE_SHA256", ""),
    }


def create_request(
    root: Optional[str],
    *,
    actor_id: str,
    identity: dict[str, Any],
    job_id: Optional[str] = None,
) -> dict[str, Any]:
    import secrets

    ident = _validate_job_id(job_id or ("pupd_" + secrets.token_hex(12)))
    source_ref = _validate_ref(str(identity.get("source_ref") or ""))
    source_head = _validate_sha(str(identity.get("source_head") or ""))
    channel = str(identity.get("channel") or identity.get("release_channel") or "").strip().lower()
    if channel not in VALID_CHANNELS:
        raise ProductUpdateError("Installed release channel is not safe for Web product update.")
    actor = str(actor_id or "").strip()
    if not actor or len(actor) > 256:
        raise ProductUpdateError("Product update actor identity is invalid.")
    web_unit = _root(root) / "etc/systemd/system/drlink-web.service"
    if not web_unit.is_file():
        raise ProductUpdateError("Optional Web Management is not installed.")

    state_dir = _state_dir(root)
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(state_dir, 0o700)
    except OSError:
        pass
    request = {
        "schema_version": 1,
        "job_id": ident,
        "actor_id": actor,
        "created_at": _utc_now(),
        "installed_project_version": str(identity.get("project_version") or ""),
        "installed_source_ref": source_ref,
        "installed_source_head": source_head,
        "release_channel": channel,
        "web_was_installed": True,
    }
    req_path = request_path(root, ident)
    try:
        fd = os.open(str(req_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ProductUpdateError("Product update job ID collision.") from exc
    try:
        os.write(fd, (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    status = {
        "schema_version": 1,
        "job_id": ident,
        "status": "QUEUED",
        "created_at": request["created_at"],
        "updated_at": request["created_at"],
        "source_ref": source_ref,
        "source_head": source_head,
        "recovery_required": False,
    }
    _atomic_json(status_path(root, ident), status)
    return status


def read_status(root: Optional[str], job_id: str) -> dict[str, Any]:
    return _read_json(status_path(root, job_id))


def mark_failed(root: Optional[str], job_id: str, message: str, *, recovery_required: bool = False) -> None:
    ident = _validate_job_id(job_id)
    try:
        current = read_status(root, ident)
    except ProductUpdateError:
        current = {"schema_version": 1, "job_id": ident, "created_at": _utc_now()}
    current.update(
        {
            "status": "FAILED",
            "updated_at": _utc_now(),
            "error": str(message or "Product update failed.")[:MAX_STATUS_ERROR],
            "recovery_required": bool(recovery_required),
        }
    )
    _atomic_json(status_path(root, ident), current)


def _write_status(root: Optional[str], job_id: str, **changes: Any) -> dict[str, Any]:
    current = read_status(root, job_id)
    current.update(changes)
    current["updated_at"] = _utc_now()
    _atomic_json(status_path(root, job_id), current)
    return current


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_for(sums_path: Path, artifact: str) -> str:
    found: list[str] = []
    for raw in sums_path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) == 2 and parts[1] == artifact and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            found.append(parts[0].lower())
    if len(found) != 1:
        raise ProductUpdateError("Release checksum metadata does not bind the Web package exactly once.")
    return found[0]


def _safe_extract(bundle: Path, dest: Path) -> Path:
    prefix = "data-relay-link-web/"
    with tarfile.open(bundle, "r:gz") as tf:
        members = tf.getmembers()
        if not members:
            raise ProductUpdateError("Web package is empty.")
        for member in members:
            name = member.name
            if not name.startswith(prefix) or name.startswith("/") or ".." in Path(name).parts:
                raise ProductUpdateError("Web package contains an unsafe path.")
            if member.issym() or member.islnk() or member.isdev():
                raise ProductUpdateError("Web package contains an unsupported link/device entry.")
        tf.extractall(dest, filter="data")
    root = dest / "data-relay-link-web"
    if not (root / "install-web.sh").is_file():
        raise ProductUpdateError("Web package is missing its installer.")
    return root


def _package_identity(package_root: Path, requested_ref: str, requested_channel: str) -> dict[str, str]:
    try:
        manifest = json.loads((package_root / "release-manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProductUpdateError("Web package release manifest is invalid.") from exc
    source_head = _validate_sha(str(manifest.get("source_head") or ""), "Web package source HEAD")
    source_ref = str(
        manifest.get("immutable_source_ref") or manifest.get("git_ref") or ""
    ).strip()
    if source_ref != requested_ref:
        raise ProductUpdateError("Web package source ref does not match the requested Core update ref.")
    channel = str(manifest.get("channel") or "").strip().lower()
    if channel != requested_channel:
        raise ProductUpdateError("Web package release channel does not match the Core update channel.")
    return {
        "project_version": str(manifest.get("project_version") or ""),
        "source_ref": source_ref,
        "source_head": source_head,
        "release_channel": channel,
    }


def _download_exact_package(ref: str, channel: str, temp: Path) -> tuple[Path, dict[str, str], str]:
    sums = temp / "SHA256SUMS"
    manifest = temp / "release-manifest.json"
    bundle = temp / "data-relay-link-web.tar.gz"
    base = "%s/%s" % (RAW_BASE, ref)
    for url, dest in (
        (base + "/SHA256SUMS", sums),
        (base + "/release-manifest.json", manifest),
        (base + "/" + WEB_ARTIFACT, bundle),
    ):
        proc = subprocess.run(
            ["curl", "-fL", "--retry", "3", "--connect-timeout", "10", "--max-time", "120", "-o", str(dest), url],
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
        if proc.returncode != 0:
            raise ProductUpdateError("Failed to download exact-build Web update artifact.")
    expected = _checksum_for(sums, WEB_ARTIFACT)
    actual = _sha256(bundle)
    if actual != expected:
        raise ProductUpdateError("Web update artifact SHA256 verification failed.")
    extracted = temp / "web"
    extracted.mkdir()
    package_root = _safe_extract(bundle, extracted)
    shutil.copy2(manifest, package_root / "release-manifest.json")
    identity = _package_identity(package_root, ref, channel)
    return package_root, identity, actual


def _local_package(source: Path, requested_channel: str) -> tuple[Path, dict[str, str], str]:
    if not (source / "install-web.sh").is_file():
        raise ProductUpdateError("Local product-update source has no Web package installer.")
    proc = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise ProductUpdateError("Local product-update source has no exact Git HEAD.")
    head = _validate_sha(proc.stdout.strip(), "local source HEAD")
    return source, {
        "project_version": "",
        "source_ref": head,
        "source_head": head,
        "release_channel": requested_channel,
    }, "local-source:" + head


def _run_checked(command: list[str], *, env: dict[str, str], timeout: int, label: str) -> subprocess.CompletedProcess[str]:
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
        raise ProductUpdateError("%s timed out." % label) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if len(detail) > 1024:
            detail = detail[:1024] + " [truncated]"
        raise ProductUpdateError("%s failed.%s" % (label, (" " + detail) if detail else ""))
    return proc


def _systemctl(command: str) -> bool:
    proc = subprocess.run(
        ["systemctl", command, "drlink-web.service"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return proc.returncode == 0


def _audit(root: Optional[str], *, actor: str, action: str, result: str, reason: str = "") -> None:
    try:
        from drlink_control_plane import ControlPlane

        plane = ControlPlane(str(_root(root)) if str(_root(root)) != "/" else None)
        try:
            plane._audit(
                revision=int(plane.current_revision()),
                action=action,
                entity_type="system-update",
                entity_id="product",
                operation="update",
                actor=actor,
                interface="WEB",
                category="SECURITY_LIFECYCLE",
                result=result,
                impact=reason,
            )
        finally:
            plane.close()
    except Exception:
        # Status file + journal remain recovery evidence; audit is best effort
        # after a potentially failed code/schema transition.
        pass


def run_job(job_id: str, root: Optional[str] = None) -> dict[str, Any]:
    ident = _validate_job_id(job_id)
    root_path = _root(root or os.environ.get("DRLINK_PRODUCT_UPDATE_ROOT"))
    root_arg = None if str(root_path) == "/" else str(root_path)
    request = _read_json(request_path(root_arg, ident))
    actor = str(request.get("actor_id") or "system:web-update")
    lock_path = _state_dir(root_arg) / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    core_updated = False
    web_stopped = False
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProductUpdateError("Another product update is already running.") from exc

        installed_before = read_installed_identity(root_arg)
        if (
            installed_before["source_ref"] != request.get("installed_source_ref")
            or installed_before["source_head"].lower() != str(request.get("installed_source_head") or "").lower()
        ):
            raise ProductUpdateError("Product update request is stale; installed Core identity changed.")
        ref = _validate_ref(str(request.get("installed_source_ref") or ""))
        channel = str(request.get("release_channel") or "").strip().lower()
        if channel not in VALID_CHANNELS:
            raise ProductUpdateError("Product update release channel is invalid.")

        _write_status(root_arg, ident, status="PREPARING", recovery_required=False)
        source_env = str(os.environ.get("DRLINK_PRODUCT_UPDATE_SOURCE") or "").strip()
        with tempfile.TemporaryDirectory(prefix="drlink-product-update-") as tmp_text:
            temp = Path(tmp_text)
            if source_env:
                if str(root_path) == "/":
                    raise ProductUpdateError("Local product-update source is test-only.")
                package_root, package_identity, web_digest = _local_package(Path(source_env), channel)
                ref = package_identity["source_ref"]
            else:
                package_root, package_identity, web_digest = _download_exact_package(ref, channel, temp)

            _write_status(
                root_arg,
                ident,
                status="READY",
                target_source_ref=package_identity["source_ref"],
                target_source_head=package_identity["source_head"],
                web_bundle_sha256=web_digest,
            )

            if str(root_path) == "/":
                if not _systemctl("stop"):
                    raise ProductUpdateError("Failed to stop Web Management before Core update.")
                web_stopped = True

            _write_status(root_arg, ident, status="UPDATING_CORE")
            env = os.environ.copy()
            env.pop("DRLINK_CONFIRM", None)
            env["DRLINK_ACTOR"] = actor
            env["DRLINK_INTERFACE"] = "WEB"
            env["FRP_EXPECTED_SOURCE_REF"] = package_identity["source_ref"]
            env["FRP_EXPECTED_SOURCE_HEAD"] = package_identity["source_head"]
            env["FRP_RELEASE_CHANNEL"] = channel
            if str(root_path) != "/":
                env["FRP_SERVER_TEST_ROOT"] = str(root_path)
            if source_env:
                update_tool = package_root / "tools/frp-project-update"
                update_command = ["bash", str(update_tool), "--source", str(package_root)]
            else:
                update_tool = root_path / "usr/local/lib/drlink/frp-project-update"
                if not update_tool.is_file():
                    raise ProductUpdateError("Canonical product updater is not installed.")
                update_command = ["bash", str(update_tool)]
            _run_checked(update_command, env=env, timeout=600, label="Core product update")
            core_updated = True

            installed_after = read_installed_identity(root_arg)
            if (
                installed_after["source_ref"] != package_identity["source_ref"]
                or installed_after["source_head"].lower() != package_identity["source_head"]
            ):
                raise ProductUpdateError(
                    "Updated Core identity does not match the verified Web package; Web remains stopped."
                )

            _write_status(root_arg, ident, status="UPDATING_WEB")
            install_env = os.environ.copy()
            install_env["DRLINK_WEB_INSTALL_SKIP_SYSTEMD"] = "1"
            install_env["DRLINK_WEB_SOURCE_REF"] = package_identity["source_ref"]
            install_env["DRLINK_WEB_SOURCE_HEAD"] = package_identity["source_head"]
            install_env["DRLINK_WEB_BUNDLE_SHA256"] = web_digest
            if str(root_path) != "/":
                install_env["DRLINK_WEB_INSTALL_ROOT"] = str(root_path)
            _run_checked(
                ["bash", str(package_root / "install-web.sh")],
                env=install_env,
                timeout=120,
                label="Exact-build Web package install",
            )
            marker = root_path / "usr/local/share/drlink-web/build.json"
            marker_data = _read_json(marker)
            if (
                str(marker_data.get("source_ref") or "") != package_identity["source_ref"]
                or str(marker_data.get("source_head") or "").lower() != package_identity["source_head"]
            ):
                raise ProductUpdateError("Installed Web build marker does not match updated Core identity.")

            if str(root_path) == "/":
                subprocess.run(["systemctl", "daemon-reload"], timeout=30, check=False)
                if not _systemctl("start"):
                    raise ProductUpdateError("Updated Web Management failed to start.")
                web_stopped = False

            result = _write_status(
                root_arg,
                ident,
                status="SUCCEEDED",
                completed_at=_utc_now(),
                recovery_required=False,
                core_source_ref=installed_after["source_ref"],
                core_source_head=installed_after["source_head"],
            )
            _audit(root_arg, actor=actor, action="web product update completed", result="SUCCESS")
            return result
    except Exception as exc:
        recovery_required = bool(core_updated)
        if web_stopped and not core_updated and str(root_path) == "/":
            _systemctl("start")
        message = str(exc) or "Product update failed."
        mark_failed(root_arg, ident, message, recovery_required=recovery_required)
        _audit(
            root_arg,
            actor=actor,
            action="web product update failed",
            result="FAIL",
            reason="RECOVERY_REQUIRED" if recovery_required else "UPDATE_FAILED",
        )
        if isinstance(exc, ProductUpdateError):
            raise
        raise ProductUpdateError(message) from exc
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass
