#!/usr/bin/env python3
"""Isolated qualification bridge: signed Agent candidate -> canonical updater.

No public rollout/Job dispatch is connected here. Only a pre-marked private
sandbox below the machine's temp directory can invoke the updater; real Host
installation, signer provisioning and public Apply remain separately gated.
"""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

import drlink_v30_agent_artifact as SIGNED
from drlink_v30_agent_local_trust import reverify_local_staged_agent_update

SANDBOX_MARKER = ".drlink-signed-updater-isolated-test-only"
_MARKER_BYTES = b"DRLINK_SIGNED_AGENT_UPDATER_ISOLATED_TEST_ONLY\n"
_PRESERVE = (
    "etc/frp/client-state.json",
    "etc/frp/frpc.toml",
    "etc/frp/access-info.txt",
    "etc/frp/client-identity.key",
    "etc/frp/client-identity.pub",
    "etc/frp/client-identity.mac",
    "etc/drlink/allocator-ca.crt",
    "etc/drlink/agent-release-verification.pub",
    "etc/drlink/agent-release-verification.sha256",
    "usr/local/bin/frpc",
)
_RESTORE = (
    "etc/drlink/version",
    "usr/local/bin/drlink",
    "usr/local/bin/frp-client",
    "usr/local/lib/drlink/runtime-sha256.json",
    "usr/local/lib/drlink/drlink_v30_agent_artifact.py",
    "usr/local/lib/drlink/drlink_v30_agent_local_trust.py",
)
_TEST_FAILURE_HOOKS = frozenset({"install", "verify", "version", "after-mgmt-origin"})


def _deny(reason: str) -> None:
    raise SIGNED.AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: " + reason)


def _isolated_root(root: str | Path) -> Path:
    candidate = Path(root)
    temp = Path(tempfile.gettempdir()).resolve(strict=True)
    if not candidate.is_absolute() or candidate.is_symlink():
        _deny("isolated Agent test root must be an absolute non-symlink path")
    try:
        selected = candidate.resolve(strict=True)
        info = selected.stat()
        marker = selected / SANDBOX_MARKER
        markinfo = marker.lstat()
        if (selected == temp or temp not in selected.parents
            or selected != candidate
            or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077
            or not stat.S_ISREG(markinfo.st_mode) or markinfo.st_nlink != 1
            or markinfo.st_mode & 0o077
            or marker.read_bytes() != _MARKER_BYTES):
            _deny("isolated Agent update requires a private marked test root")
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: isolated Agent test root is unavailable"
        ) from exc
    # The canonical installer touches more than the snapshot list (units,
    # binaries, transaction metadata). A test root must have NO filesystem
    # links capable of redirecting those writes outside its private tree.
    for path in selected.rglob("*"):
        if path.is_symlink():
            _deny("isolated Agent root contains a symlinked update path")
    return selected


def _snapshot(root: Path, paths: tuple[str, ...]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for rel in paths:
        path = root / rel
        if not path.exists():
            result[rel] = None
        elif path.is_file() and not path.is_symlink():
            result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            _deny("sandbox update contains an unsafe state path")
    return result


def _same_state(root: Path, baseline: dict[str, str | None]) -> bool:
    return _snapshot(root, tuple(baseline)) == baseline


def _sandbox_client_status(root: Path, verified: Mapping[str, Any], env: dict[str, str]) -> bool:
    """Read-only installed CLI probe; never a substitute for live systemd health."""
    client = root / "usr/local/bin/frp-client"
    client_lib = root / "usr/local/lib/drlink/frp-client-common.sh"
    if not client.is_file() or not client_lib.is_file():
        _deny("installed Agent status CLI is unavailable")
    status_env = dict(env)
    status_env["FRP_CLIENT_LIB"] = str(client_lib)
    try:
        observed = subprocess.run(
            ["bash", str(client), "status"], env=status_env,
            stdin=subprocess.DEVNULL, start_new_session=True,
            capture_output=True, text=True, timeout=30, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: isolated installed status timed out"
        ) from exc
    expected = {
        "Role": "Client",
        "Project version": verified["version"],
        "Release channel": verified["channel"],
        "Source ref": verified["source_ref"],
        "Bundle SHA256": verified["sha256"],
    }
    actual: dict[str, str] = {}
    for line in observed.stdout.splitlines():
        label, separator, value = line.partition(":")
        field = label.strip()
        if separator and field in expected:
            # Do not accept stale lines copied into diagnostic prefixes, or
            # conflicting repeated keys masquerading as a successful status.
            if field in actual:
                _deny("installed Agent CLI status contains duplicate identity fields")
            actual[field] = value.strip()
    if observed.returncode or any(
        actual.get(field) != value for field, value in expected.items()
    ):
        _deny("installed Agent CLI status does not match signed target")
    return True


def run_isolated_signed_agent_update(
    *, root: str | Path, candidate_dir: str | Path,
    target: Mapping[str, Any], expected_channel: str,
    check_only: bool = False, failure_hook: str | None = None,
) -> dict[str, Any]:
    """Exercise the unmodified Client --upgrade check/install/rollback in a sandbox.

    This does not authorize a live Agent, Server-side Job or public rollout
    Apply. The private staged bytes and independent release root are reverified
    on EVERY invocation, including check-only and intentional failure cases.
    """
    base = _isolated_root(root)
    if failure_hook is not None and (check_only or failure_hook not in _TEST_FAILURE_HOOKS):
        _deny("invalid isolated updater fault-injection contract")
    verified = reverify_local_staged_agent_update(
        root=base, candidate_dir=candidate_dir, target=target,
        expected_channel=expected_channel,
    )
    preserve = _snapshot(base, _PRESERVE)
    previous = _snapshot(base, _RESTORE)
    bundle = Path(candidate_dir) / "agent/bootstrap-client.sh"
    if not hasattr(os, "O_NOFOLLOW"):
        _deny("safe signed bundle descriptor is unavailable")
    try:
        fd = os.open(str(bundle), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: signed updater bundle is unavailable"
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _deny("signed updater descriptor is not a regular file")
        digest = hashlib.sha256()
        while True:
            data = os.read(fd, 1024 * 1024)
            if not data:
                break
            digest.update(data)
        if (digest.hexdigest() != verified["sha256"]
            or info.st_size != verified["artifact_size"]):
            _deny("signed updater bytes changed after signature revalidation")
        os.lseek(fd, 0, os.SEEK_SET)
        # Pass the validated *open descriptor*, not a path that could be
        # substituted between signature verification and bash execution.
        fd_path = "/proc/self/fd/%d" % fd
        if not Path("/proc/self/fd").is_dir():
            _deny("isolated Linux signed updater descriptor execution unavailable")
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": str(base),
            "LANG": "C",
            "FRP_CLIENT_TEST_ROOT": str(base),
            "FRP_SKIP_SYSTEMD": "1",
            "FRP_SKIP_DOWNLOAD": "1",
            "FRP_CLIENT_SKIP_SERVER_VERSION_GATE": "1",
            "FRP_BUNDLE_FILE": fd_path,
            "FRP_BUNDLE_SHA256": verified["sha256"],
            "FRP_EXPECTED_SOURCE_REF": verified["source_ref"],
            "FRP_EXPECTED_SOURCE_HEAD": verified["source_ref"],
            "FRP_RELEASE_CHANNEL": verified["channel"],
            "FRP_EXPECTED_RELEASE_CHANNEL": verified["channel"],
            "_FRP_CLIENT_UPDATE_KIND": "bundle",
        }
        if failure_hook:
            env["FRP_CLIENT_UPGRADE_HOOK_FAIL"] = failure_hook
        command = ["bash", fd_path, "--upgrade"]
        if check_only:
            command.append("--check")
        try:
            proc = subprocess.run(
                command, env=env, pass_fds=(fd,), capture_output=True,
                text=True, stdin=subprocess.DEVNULL, start_new_session=True,
                timeout=180, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            _deny("isolated canonical updater timed out; result unknown")
    finally:
        os.close(fd)
    if not _same_state(base, preserve):
        _deny("canonical updater changed persistent Agent identity/state")
    if check_only:
        if not _same_state(base, previous):
            _deny("canonical updater check unexpectedly mutated installed Agent")
        if proc.returncode:
            _deny("canonical updater check failed")
        return {
            **verified, "qualification_scope": "ISOLATED_SANDBOX",
            "sandbox_check_passed": True, "sandbox_update_completed": False,
            "post_update_health_verified": False, "rollback_verified": False,
            "public_rollout_apply_allowed": False,
        }
    if proc.returncode:
        # A printed rollback PASS is not enough: compare the actual installed
        # identity and critical runtime bytes to the pre-upgrade snapshot.
        restored = (
            "UPGRADE_ROLLBACK=PASS" in proc.stdout
            and _same_state(base, previous)
        )
        return {
            **verified, "qualification_scope": "ISOLATED_SANDBOX",
            "sandbox_update_completed": False, "sandbox_rollback_verified": restored,
            "failure_class": "EXPECTED_INJECTED_FAILURE" if failure_hook else "UPDATER_FAILED",
            "post_update_health_verified": False, "rollback_verified": False,
            "public_rollout_apply_allowed": False,
        }
    lineage = SIGNED.verify_installed_agent_lineage(base, verified_bundle=verified)
    status_verified = _sandbox_client_status(base, verified, env)
    if not _same_state(base, preserve):
        _deny("installed Agent status changed persistent Agent identity/state")
    return {
        **verified, **lineage,
        "qualification_scope": "ISOLATED_SANDBOX",
        "sandbox_update_completed": True,
        "sandbox_lineage_verified": True,
        "sandbox_readonly_status_verified": status_verified,
        # Synthetic install cannot attest a live service heartbeat/canary.
        "post_update_health_verified": False,
        "rollback_verified": False,
        "public_rollout_apply_allowed": False,
    }
