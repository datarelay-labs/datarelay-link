#!/usr/bin/env python3
"""Bounded read-only HTTPS preflight for a signed Server-local Agent candidate.

The caller MUST resolve the origin and CA from persisted Agent enrollment,
not from a Management Job payload or the manifest being downloaded. This
module never runs an installer, publishes a candidate, or changes Host state.
"""
from __future__ import annotations

import hmac
import http.client
import os
import shutil
import ssl
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import drlink_v30_agent_artifact as SIGNED
import frp_mgmt_auth as MGMT

CONNECT_TIMEOUT = 10
MAX_STAGED_CANDIDATES_PER_AGENT = 3
ARTIFACT_ENDPOINTS = (
    ("/artifacts/manifest.json", SIGNED.MAX_MANIFEST_BYTES),
    ("/artifacts/agent/manifest.sig", 1024),
    ("/artifacts/agent/bootstrap-client.sh", SIGNED.MAX_BUNDLE_BYTES),
)


def _deny(reason: str) -> None:
    raise SIGNED.AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: " + reason)


def _parse_https_origin(origin: str) -> tuple[str, int]:
    value = str(origin or "").strip()
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in value):
        _deny("invalid enrolled HTTPS Server origin")
    try:
        parsed = urlsplit(value)
        port = 443 if parsed.port is None else parsed.port
        host = parsed.hostname or ""
    except ValueError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: invalid HTTPS Server origin"
        ) from exc
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or port < 1 or port > 65535):
        _deny("Server-local artifact origin must be an enrolled HTTPS authority")
    return host, port


def _tls_context(enrollment_ca: str | Path) -> ssl.SSLContext:
    try:
        pem = SIGNED._read_bounded_regular(str(enrollment_ca), 128 * 1024)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_verify_locations(cadata=pem.decode("ascii"))
        return context
    except (UnicodeError, ssl.SSLError, ValueError, OSError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: trusted enrollment CA is unavailable"
        ) from exc


def _https_get(
    host: str, port: int, path: str, limit: int, context: ssl.SSLContext
) -> bytes:
    # http.client makes precisely one HTTPS request; unlike urllib, it cannot
    # transparently follow an HTTP redirect to a new host or plaintext origin.
    conn = http.client.HTTPSConnection(
        host=host, port=port, context=context, timeout=CONNECT_TIMEOUT,
    )
    try:
        conn.request("GET", path, headers={"Accept": "application/octet-stream"})
        response = conn.getresponse()
        if response.status != 200:
            _deny("signed Server-local artifact endpoint is unavailable")
        advertised = response.getheader("Content-Length")
        if advertised is not None:
            try:
                length = int(advertised)
            except ValueError:
                _deny("Server-local artifact Content-Length is invalid")
            if length < 1 or length > limit:
                _deny("Server-local artifact is outside bounded size")
        data = response.read(limit + 1)
        if not 0 < len(data) <= limit:
            _deny("Server-local artifact is missing or exceeds bounded size")
        if advertised is not None and len(data) != length:
            _deny("Server-local artifact was truncated")
        return data
    except SIGNED.AgentArtifactError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: signed Server-local HTTPS fetch failed"
        ) from exc
    finally:
        conn.close()


def _release_signer(
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
) -> str:
    if (not isinstance(pinned_release_key_fingerprint, str)
        or not SIGNED.SHA64.fullmatch(pinned_release_key_fingerprint)):
        _deny("a pinned release public-key fingerprint is required")
    try:
        signer = SIGNED._read_bounded_regular(
            str(trusted_release_public_key_file), 8192
        ).decode("ascii")
        actual_key = MGMT.pubkey_fingerprint(signer)
    except (UnicodeError, ValueError, OSError, RuntimeError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: trusted release key is unavailable"
        ) from exc
    if not hmac.compare_digest(actual_key, pinned_release_key_fingerprint):
        _deny("trusted release public-key fingerprint mismatch")
    return signer


def _fetch_verified_bytes(
    *,
    enrolled_https_origin: str,
    enrollment_ca_file: str | Path,
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
    target: Mapping[str, Any],
    expected_channel: str,
) -> tuple[dict[str, Any], bytes, bytes, bytes, str]:
    """Fetch one bound Server candidate and verify exactly the fetched bytes."""
    signer = _release_signer(
        trusted_release_public_key_file, pinned_release_key_fingerprint
    )
    host, port = _parse_https_origin(enrolled_https_origin)
    context = _tls_context(enrollment_ca_file)
    manifest = _https_get(host, port, *ARTIFACT_ENDPOINTS[0], context)
    raw_signature = _https_get(host, port, *ARTIFACT_ENDPOINTS[1], context)
    bundle = _https_get(host, port, *ARTIFACT_ENDPOINTS[2], context)
    try:
        signature = raw_signature.decode("ascii").strip()
    except UnicodeError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: detached release signature encoding invalid"
        ) from exc
    # The original read-only probe still removes this temporary candidate.
    with tempfile.TemporaryDirectory(prefix="drlink-v30-agent-candidate-") as tmp:
        path = Path(tmp) / "bootstrap-client.sh"
        with path.open("xb") as handle:
            handle.write(bundle)
        path.chmod(0o600)
        result = SIGNED.verify_signed_agent_bundle(
            manifest_bytes=manifest, signature_b64=signature,
            trusted_release_public_key=signer, bundle_path=path,
            target=target, expected_channel=expected_channel,
        )
    return result, manifest, raw_signature, bundle, signer


def _preflight_result(verified: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "transport": "ENROLLED_SERVER_HTTPS",
        "signature_verified": verified["signature_verified"],
        "source_ref": verified["source_ref"],
        "sha256": verified["sha256"],
        "version": verified["version"],
        "channel": verified["channel"],
        "artifact_size": verified["size"],
        "update_completed": False,
        "post_update_health_verified": False,
        "rollback_verified": False,
    }


def verify_enrolled_server_candidate(
    *,
    enrolled_https_origin: str,
    enrollment_ca_file: str | Path,
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
    target: Mapping[str, Any],
    expected_channel: str,
) -> dict[str, Any]:
    """Read-only verification. Never persist downloaded bytes or invoke Apply."""
    verified, _, _, _, _ = _fetch_verified_bytes(
        enrolled_https_origin=enrolled_https_origin,
        enrollment_ca_file=enrollment_ca_file,
        trusted_release_public_key_file=trusted_release_public_key_file,
        pinned_release_key_fingerprint=pinned_release_key_fingerprint,
        target=target, expected_channel=expected_channel,
    )
    return _preflight_result(verified)


def _private_candidate_dir(path: Path) -> Path:
    """An explicit local private directory, never an implicitly created path."""
    if path.is_symlink():
        _deny("Agent candidate directory cannot be a symlink")
    try:
        info = path.stat()
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: Agent candidate directory missing"
        ) from exc
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        _deny("Agent candidate directory must be private (0700)")
    return path.resolve(strict=True)


def _write_private_file(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def verify_staged_enrolled_candidate(
    *,
    candidate_dir: str | Path,
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
    target: Mapping[str, Any],
    expected_channel: str,
) -> dict[str, Any]:
    """Recheck original signed bytes, key and file contents before future Apply."""
    root = _private_candidate_dir(Path(candidate_dir))
    try:
        agent_info = (root / "agent").lstat()
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: staged Agent directory missing"
        ) from exc
    if not stat.S_ISDIR(agent_info.st_mode) or agent_info.st_mode & 0o077:
        _deny("staged Agent directory must be private and cannot be a symlink")
    try:
        if ({p.name for p in root.iterdir()} != {"manifest.json", "agent"}
            or {p.name for p in (root / "agent").iterdir()}
                != {"manifest.sig", "bootstrap-client.sh"}):
            _deny("staged Agent candidate contains unexpected files")
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: staged Agent candidate is unreadable"
        ) from exc
    for rel in ("manifest.json", "agent/manifest.sig", "agent/bootstrap-client.sh"):
        path = root / rel
        try:
            info = path.lstat()
        except OSError as exc:
            raise SIGNED.AgentArtifactError(
                "AGENT_ARTIFACT_UNQUALIFIED: staged Agent file is missing"
            ) from exc
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_mode & 0o077):
            _deny("staged Agent file is not a private regular file")
    signer = _release_signer(
        trusted_release_public_key_file, pinned_release_key_fingerprint
    )
    manifest = SIGNED._read_bounded_regular(
        str(root / "manifest.json"), SIGNED.MAX_MANIFEST_BYTES
    )
    raw_signature = SIGNED._read_bounded_regular(
        str(root / "agent/manifest.sig"), 1024
    )
    try:
        signature = raw_signature.decode("ascii").strip()
    except UnicodeError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: staged signature encoding invalid"
        ) from exc
    result = SIGNED.verify_signed_agent_bundle(
        manifest_bytes=manifest, signature_b64=signature,
        trusted_release_public_key=signer,
        bundle_path=root / "agent/bootstrap-client.sh",
        target=target, expected_channel=expected_channel,
    )
    return {**_preflight_result(result), "candidate_staged": True}


def _reserve_private_candidate_dir(parent: Path) -> Path:
    """Atomically reserve a bounded candidate slot across Agent processes.

    Linux/macOS flock on the existing private directory avoids creating a
    publicly discoverable or mutable lockfile. No stale candidate is deleted.
    """
    try:
        import fcntl
    except ImportError:
        _deny("Agent platform has no supported candidate staging lock")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        _deny("safe Agent candidate directory locking is unavailable")
    try:
        descriptor = os.open(
            str(parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: private staging directory unavailable"
        ) from exc
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise SIGNED.AgentArtifactError(
                "AGENT_ARTIFACT_UNQUALIFIED: another Agent stage is in progress"
            ) from exc
        existing = sum(
            item.name.startswith(".drlink-signed-agent-")
            for item in parent.iterdir()
        )
        if existing >= MAX_STAGED_CANDIDATES_PER_AGENT:
            _deny("too many staged Agent candidates; explicit reconciliation required")
        return Path(tempfile.mkdtemp(prefix=".drlink-signed-agent-", dir=parent))
    finally:
        os.close(descriptor)


def stage_enrolled_server_candidate(
    *,
    enrolled_https_origin: str,
    enrollment_ca_file: str | Path,
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
    target: Mapping[str, Any],
    expected_channel: str,
    staging_parent: str | Path,
) -> dict[str, Any]:
    """Retain only verified exact bytes in a private candidate directory.

    Not an updater or a public management endpoint. The future Agent worker
    must reverify the stored candidate just before invoking its canonical
    rollback-capable updater; the downloaded Server cannot select this path.
    """
    parent = _private_candidate_dir(Path(staging_parent))
    # Storage is a bounded Agent-local resource. Do not silently clean up
    # older candidates: a crash may have left an operation outcome uncertain.
    pending = sum(
        item.name.startswith(".drlink-signed-agent-")
        for item in parent.iterdir()
    )
    if pending >= MAX_STAGED_CANDIDATES_PER_AGENT:
        _deny("too many staged Agent candidates; explicit reconciliation required")
    verified, manifest, signature, bundle, _ = _fetch_verified_bytes(
        enrolled_https_origin=enrolled_https_origin,
        enrollment_ca_file=enrollment_ca_file,
        trusted_release_public_key_file=trusted_release_public_key_file,
        pinned_release_key_fingerprint=pinned_release_key_fingerprint,
        target=target, expected_channel=expected_channel,
    )
    candidate = _reserve_private_candidate_dir(parent)
    complete = False
    try:
        candidate.chmod(0o700)
        agent = candidate / "agent"
        agent.mkdir(mode=0o700)
        _write_private_file(candidate / "manifest.json", manifest)
        _write_private_file(agent / "manifest.sig", signature)
        _write_private_file(agent / "bootstrap-client.sh", bundle)
        result = verify_staged_enrolled_candidate(
            candidate_dir=candidate,
            trusted_release_public_key_file=trusted_release_public_key_file,
            pinned_release_key_fingerprint=pinned_release_key_fingerprint,
            target=target, expected_channel=expected_channel,
        )
        if (not result["signature_verified"]
            or result["sha256"] != verified["sha256"]):
            _deny("staged Agent artifact differs from verified download")
        complete = True
        return {**result, "candidate_dir": str(candidate)}
    finally:
        if not complete:
            shutil.rmtree(candidate, ignore_errors=True)
