#!/usr/bin/env python3
"""Local-only Linux Agent trust binding for signed DRLink 3.0 update candidates.

An Agent may verify and stage a remotely supplied immutable target only using
its OWN persisted enrollment URL/CA and separately provisioned release-signing
verification root. Nothing in a Job, manifest, environment override, or
untrusted download may select the transport origin, CA or signer.
No key provisioning, updater Apply, service mutation or rollback occurs here.
"""
from __future__ import annotations

import hmac
import json
import re
import stat
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import drlink_v30_agent_artifact as SIGNED
import drlink_v30_agent_artifact_transport as TRANSPORT
import frp_mgmt_auth as MGMT

STATE_FILE = "etc/frp/client-state.json"
AGENT_IDENTITY_KEY = "etc/frp/client-identity.key"
AGENT_IDENTITY_PUB = "etc/frp/client-identity.pub"
AGENT_IDENTITY_MAC = "etc/frp/client-identity.mac"
ENROLLMENT_CA = "etc/drlink/allocator-ca.crt"
RELEASE_PUB = "etc/drlink/agent-release-verification.pub"
RELEASE_PIN = "etc/drlink/agent-release-verification.sha256"
PRIVATE_STAGE = "var/lib/drlink/signed-agent-candidates"
_MAX_LOCAL_STATE = 64 * 1024
_MACHINE_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def _deny(reason: str) -> None:
    raise SIGNED.AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: " + reason)


def _secure_trust_parents(root: Path, relative: str) -> None:
    """Reject symlink/writable directory indirection within Agent authority."""
    current = root
    for name in Path(relative).parts[:-1]:
        current = current / name
        try:
            info = current.lstat()
        except OSError as exc:
            raise SIGNED.AgentArtifactError(
                "AGENT_ARTIFACT_UNQUALIFIED: local Agent trust directory is missing"
            ) from exc
        if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
            or (root == Path("/") and info.st_uid != 0)):
            _deny("local Agent trust directory is not secure")


def _fixed_file(root: Path, relative: str, *, limit: int) -> bytes:
    """Reject rewritable/symlinked local authority (without exposing material)."""
    _secure_trust_parents(root, relative)
    path = root / relative
    try:
        info = path.lstat()
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: required local Agent trust file missing"
        ) from exc
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_mode & 0o022
        or (root == Path("/") and info.st_uid != 0)):
        _deny("local Agent trust file has an untrusted owner or mode")
    return SIGNED._read_bounded_regular(str(path), limit)


def _enrolled_https_origin(state: Mapping[str, Any]) -> str:
    """Same WSS single-443 origin correction as existing Client updater."""
    raw = state.get("allocator_url")
    if not isinstance(raw, str) or not raw.strip():
        _deny("persisted Agent allocator URL is missing")
    try:
        parts = urlsplit(raw.strip())
        port = 443 if parts.port is None else parts.port
        hostname = parts.hostname or ""
    except ValueError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: Agent enrollment origin is invalid"
        ) from exc
    if (parts.scheme != "https" or not hostname or parts.username
        or parts.password or parts.query or parts.fragment
        or port < 1 or port > 65535
        or any(ord(ch) <= 32 or ord(ch) == 127 for ch in raw)):
        _deny("persisted Agent allocator URL is not trusted HTTPS")
    if (str(state.get("frp_transport") or "").lower() == "wss"
        and parts.port == 6099):
        try:
            public_port = int(state.get("frp_server_port"))
        except (TypeError, ValueError):
            public_port = 0
        if not 1 <= public_port <= 65535 or public_port == 6099:
            _deny("WSS Agent update origin has no qualified public HTTPS port")
        port = public_port
    host = "[" + hostname + "]" if ":" in hostname else hostname
    origin = "https://" + host + ((":" + str(port)) if port != 443 else "")
    TRANSPORT._parse_https_origin(origin)
    return origin


def resolve_local_agent_update_trust(root: str | Path | None = None) -> dict[str, Any]:
    """Return LOCAL fixed trust sources; reject missing/unprovisioned enrollment.

    The release verifier and its fingerprint are provisioned out of band.
    This function NEVER creates keys or accepts caller-supplied URL/key paths.
    """
    base = Path(root) if root is not None else Path("/")
    if not base.is_absolute() or base.is_symlink() or not base.is_dir():
        _deny("Agent trust root must be an existing absolute directory")
    base = base.resolve(strict=True)
    raw_state = _fixed_file(base, STATE_FILE, limit=_MAX_LOCAL_STATE)
    try:
        state = json.loads(
            raw_state.decode("utf-8"),
            object_pairs_hook=SIGNED._unique_json_object,
            parse_constant=SIGNED._reject_nonfinite_json,
        )
    except (UnicodeError, ValueError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: persisted enrollment state is invalid"
        ) from exc
    if not isinstance(state, dict) or not _MACHINE_ID.fullmatch(
        str(state.get("machine_id") or "")
    ):
        _deny("Agent must have persisted enrollment identity")

    # Verify established identity exists; never read the private key contents.
    _secure_trust_parents(base, AGENT_IDENTITY_KEY)
    key = base / AGENT_IDENTITY_KEY
    try:
        info = key.lstat()
    except OSError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: Agent enrollment identity is unavailable"
        ) from exc
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_mode & 0o077
        or (base == Path("/") and info.st_uid != 0)):
        _deny("Agent enrollment key is not private")
    try:
        pub = _fixed_file(base, AGENT_IDENTITY_PUB, limit=8192).decode("ascii")
        MGMT.canonicalize_pubkey_pem(pub)
    except (ValueError, OSError, RuntimeError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: Agent identity public key is invalid"
        ) from exc
    _fixed_file(base, AGENT_IDENTITY_MAC, limit=8192)
    ca_path = base / ENROLLMENT_CA
    _fixed_file(base, ENROLLMENT_CA, limit=128 * 1024)
    release_public = base / RELEASE_PUB
    try:
        pem = _fixed_file(base, RELEASE_PUB, limit=8192).decode("ascii")
        raw_pin = _fixed_file(base, RELEASE_PIN, limit=256).decode("ascii").strip()
    except UnicodeError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: local release verification metadata is invalid"
        ) from exc
    if not SIGNED.SHA64.fullmatch(raw_pin):
        _deny("local Agent release signer fingerprint is missing or malformed")
    try:
        actual = MGMT.pubkey_fingerprint(pem)
    except (ValueError, OSError, RuntimeError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: local release signer key is invalid"
        ) from exc
    if not hmac.compare_digest(actual, raw_pin):
        _deny("local release signer and independent fingerprint disagree")
    _secure_trust_parents(base, PRIVATE_STAGE)
    stage_path = base / PRIVATE_STAGE
    TRANSPORT._private_candidate_dir(stage_path)
    return {
        "enrolled_https_origin": _enrolled_https_origin(state),
        "enrollment_ca_file": ca_path,
        "trusted_release_public_key_file": release_public,
        "pinned_release_key_fingerprint": raw_pin,
        "staging_parent": stage_path,
    }


def preflight_local_enrolled_agent_update(
    *, root: str | Path | None = None, target: Mapping[str, Any],
    expected_channel: str,
) -> dict[str, Any]:
    """Read-only signed candidate preflight with on-disk Agent trust only."""
    trust = resolve_local_agent_update_trust(root)
    trust.pop("staging_parent")
    return TRANSPORT.verify_enrolled_server_candidate(
        **trust, target=target, expected_channel=expected_channel,
    )


def stage_local_enrolled_agent_update(
    *, root: str | Path | None = None, target: Mapping[str, Any],
    expected_channel: str,
) -> dict[str, Any]:
    """Stage a trusted candidate; no updater/rollback or installation occurs."""
    return TRANSPORT.stage_enrolled_server_candidate(
        **resolve_local_agent_update_trust(root),
        target=target, expected_channel=expected_channel,
    )


def reverify_local_staged_agent_update(
    *, root: str | Path | None = None, candidate_dir: str | Path,
    target: Mapping[str, Any], expected_channel: str,
) -> dict[str, Any]:
    """Only allow rechecking a candidate under THIS Agent's private stage."""
    trust = resolve_local_agent_update_trust(root)
    parent = trust["staging_parent"]
    candidate = Path(candidate_dir)
    if (not candidate.is_absolute() or candidate.is_symlink()
        or candidate.parent != parent
        or not candidate.name.startswith(".drlink-signed-agent-")):
        _deny("staged Agent candidate is outside its local trusted staging root")
    return TRANSPORT.verify_staged_enrolled_candidate(
        candidate_dir=candidate,
        trusted_release_public_key_file=trust["trusted_release_public_key_file"],
        pinned_release_key_fingerprint=trust["pinned_release_key_fingerprint"],
        target=target, expected_channel=expected_channel,
    )
