#!/usr/bin/env python3
"""Fail-closed offline release-signature and installed-lineage gates for 3.0 Agents.

This is a verification primitive, NOT a runnable Agent updater. It never
downloads, installs, starts, or rolls back an Agent. A separate qualified
release-signing trust anchor must be supplied by its caller. The enrolled
Agent's own management key is never a release-signing authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

import frp_mgmt_auth as MGMT
from drlink_agent_payload import (
    AGENT_CRITICAL_LINEAGE_FILES, RUNTIME_MANIFEST_NAME, verify_installed_lineage,
)

MAX_MANIFEST_BYTES = 128 * 1024
MAX_BUNDLE_BYTES = 32 * 1024 * 1024
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-rc\.\d+)?$")
CHANNELS = frozenset({"development", "preview", "stable"})
AGENT_REL = "agent/bootstrap-client.sh"


class AgentArtifactError(ValueError):
    """One bounded public error class for an unqualified update candidate."""


def _fail(reason: str) -> None:
    raise AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: " + reason)


def _sha256_regular_file(path: Path) -> tuple[str, int]:
    """Read a downloaded bundle by descriptor, never through a symlink."""
    if not hasattr(os, "O_NOFOLLOW"):
        _fail("safe artifact file-open is unavailable")
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: bundle is unavailable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _fail("bundle must be a single regular file")
        if not 0 < info.st_size <= MAX_BUNDLE_BYTES:
            _fail("bundle size is outside the qualified limit")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest(), info.st_size
    finally:
        os.close(fd)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite_json(_: str) -> None:
    raise ValueError("non-finite JSON value")


def verify_signed_agent_bundle(
    *,
    manifest_bytes: bytes,
    signature_b64: str,
    trusted_release_public_key: str,
    bundle_path: str | Path,
    target: Mapping[str, Any],
    expected_channel: str,
) -> dict[str, Any]:
    """Verify detached ECDSA P-256 signature over *exact manifest bytes*.

    The already downloaded Server-local manifest, detached signature and bundle
    are untrusted until checked against the caller-pinned release public key and
    exact immutable target. No public key is ever learned from the manifest.
    """
    if not isinstance(manifest_bytes, bytes) or not 0 < len(manifest_bytes) <= MAX_MANIFEST_BYTES:
        _fail("signed manifest is missing or too large")
    if not isinstance(signature_b64, str) or not 64 <= len(signature_b64) <= 512:
        _fail("release signature is missing or malformed")
    try:
        base64.b64decode(signature_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: invalid signature encoding") from exc
    if not isinstance(trusted_release_public_key, str) or not trusted_release_public_key:
        _fail("pinned release public key is required")
    try:
        valid_signature = MGMT.verify_signature(
            trusted_release_public_key, manifest_bytes, signature_b64
        )
    except (ValueError, OSError, RuntimeError) as exc:
        raise AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: invalid release signer") from exc
    if not valid_signature:
        _fail("release signature verification failed")

    try:
        manifest = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_json,
        )
    except (UnicodeError, ValueError) as exc:
        raise AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: invalid signed manifest") from exc
    if (not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1):
        _fail("unsupported signed manifest schema")
    if manifest.get("qualification_status") != "PASS":
        _fail("signed manifest is not qualified")
    if not isinstance(target, Mapping):
        _fail("rollout target identity is missing")
    source = target.get("source_ref")
    digest = target.get("sha256")
    version = target.get("version")
    channel = str(expected_channel or "")
    if (not isinstance(source, str) or not SHA40.fullmatch(source)
        or not isinstance(digest, str) or not SHA64.fullmatch(digest)
        or not isinstance(version, str) or not VERSION.fullmatch(version)
        or channel not in CHANNELS):
        _fail("rollout target requires exact SHA, version, digest and channel")
    if (manifest.get("source_head") != source
        or manifest.get("git_ref") != source
        or manifest.get("immutable_source_ref") != source
        or manifest.get("project_version") != version
        or manifest.get("channel") != channel):
        _fail("signed build identity does not match requested rollout")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) > 100:
        _fail("signed manifest artifact list is invalid")
    matches = [
        row for row in artifacts
        if isinstance(row, dict) and row.get("relative_path") == AGENT_REL
    ]
    if len(matches) != 1:
        _fail("signed Linux Agent artifact entry is missing or duplicated")
    item = matches[0]
    if (item.get("artifact_type") != "agent-installer"
        or item.get("platform") != "linux"
        or item.get("source_head") != source
        or item.get("sha256") != digest):
        _fail("signed Agent entry does not match requested build")
    size = item.get("size")
    if type(size) is not int or not 0 < size <= MAX_BUNDLE_BYTES:
        _fail("signed Agent artifact size is invalid")
    real_digest, real_size = _sha256_regular_file(Path(bundle_path))
    if real_digest != digest or real_size != size:
        _fail("downloaded Agent bundle differs from signed artifact")
    return {
        "signature_verified": True,
        "source_ref": source,
        "version": version,
        "channel": channel,
        "sha256": digest,
        "size": real_size,
        "update_completed": False,
        "post_update_health_verified": False,
        "rollback_verified": False,
    }


def verify_installed_agent_lineage(
    root: str | Path, *, verified_bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Check installed identity and critical module hashes after an updater run.

    This is NOT a health or rollback probe; a successful result cannot be used
    alone to complete a staged Agent update Job.
    """
    if not isinstance(verified_bundle, Mapping) or verified_bundle.get("signature_verified") is not True:
        _fail("verified signed bundle is required")
    base = Path(root)
    path = base / "etc/drlink/version"
    try:
        if path.is_symlink():
            _fail("installed version path is a symlink")
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: installed version missing") from exc
    values: dict[str, str] = {}
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() in {"PROJECT_VERSION", "RELEASE_CHANNEL", "SOURCE_REF", "SOURCE_HEAD", "BUNDLE_SHA256"}:
            if key.strip() in values:
                _fail("duplicate installed version metadata")
            values[key.strip()] = value.strip()
    expected = {
        "PROJECT_VERSION": verified_bundle["version"],
        "RELEASE_CHANNEL": verified_bundle["channel"],
        "SOURCE_REF": verified_bundle["source_ref"],
        "SOURCE_HEAD": verified_bundle["source_ref"],
        "BUNDLE_SHA256": verified_bundle["sha256"],
    }
    if any(values.get(k) != v for k, v in expected.items()):
        _fail("installed product identity does not match signed rollout")
    libdir = base / "usr/local/lib/drlink"
    if not (libdir / RUNTIME_MANIFEST_NAME).is_file():
        _fail("installed Agent runtime manifest is absent")
    if (libdir / RUNTIME_MANIFEST_NAME).is_symlink():
        _fail("installed Agent runtime manifest is a symlink")
    # A checksum match is insufficient when a live security-critical module
    # can be redirected through a symlink or a second hardlink.
    for filename in (*AGENT_CRITICAL_LINEAGE_FILES, RUNTIME_MANIFEST_NAME):
        try:
            info = (libdir / filename).lstat()
        except OSError as exc:
            raise AgentArtifactError(
                "AGENT_ARTIFACT_UNQUALIFIED: critical Agent runtime file missing"
            ) from exc
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _fail("critical Agent runtime file is not a standalone regular file")
    try:
        failures = verify_installed_lineage(libdir)
    except (OSError, ValueError) as exc:
        raise AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: installed runtime is unreadable") from exc
    if failures:
        _fail("installed Agent runtime hashes do not match")
    return {
        "installed_identity_verified": True,
        "runtime_lineage_verified": True,
        "post_update_health_verified": False,
        "rollback_verified": False,
    }
