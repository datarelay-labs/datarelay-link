#!/usr/bin/env python3
"""Bounded read-only HTTPS preflight for a signed Server-local Agent candidate.

The caller MUST resolve the origin and CA from persisted Agent enrollment,
not from a Management Job payload or the manifest being downloaded. This
module never runs an installer, publishes a candidate, or changes Host state.
"""
from __future__ import annotations

import hmac
import http.client
import ssl
import tempfile
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import drlink_v30_agent_artifact as SIGNED
import frp_mgmt_auth as MGMT

CONNECT_TIMEOUT = 10
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
        if advertised:
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


def verify_enrolled_server_candidate(
    *,
    enrolled_https_origin: str,
    enrollment_ca_file: str | Path,
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
    target: Mapping[str, Any],
    expected_channel: str,
) -> dict[str, Any]:
    """Fetch and verify exactly one pinned signed candidate, without Apply.

    Both trust inputs are local, independently configured Agent state. Neither
    trusted public key nor pinned fingerprint is downloaded from the Server.
    """
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

    # No lasting downloaded artifacts. The same exact bundle bytes are
    # checked by the cryptographic verifier before this function returns.
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
    return {
        "transport": "ENROLLED_SERVER_HTTPS",
        "signature_verified": result["signature_verified"],
        "source_ref": result["source_ref"],
        "sha256": result["sha256"],
        "version": result["version"],
        "channel": result["channel"],
        "artifact_size": result["size"],
        "update_completed": False,
        "post_update_health_verified": False,
        "rollback_verified": False,
    }
