#!/usr/bin/env python3
"""Isolated Server-side staging for externally signed DRLink 3.0 Agent artifacts.

Release private keys never enter the Server or staged artifact tree.
The caller supplies an independently pinned release public-key fingerprint.
This module does not publish to the installed artifact root or enable Apply.
"""
from __future__ import annotations

import hmac
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

import drlink_qualified_artifacts as QA
import drlink_v30_agent_artifact as SIGNED
import frp_mgmt_auth as MGMT

SIGNATURE_REL = "agent/manifest.sig"
MAX_STAGE_BYTES = 512 * 1024 * 1024
MAX_STAGE_FILES = 256


def _deny(message: str) -> None:
    raise SIGNED.AgentArtifactError("AGENT_ARTIFACT_UNQUALIFIED: " + message)


def _trusted_pubkey(
    public_key_file: str | Path, pinned_fingerprint: str,
    artifact_root: Path,
) -> str:
    """Never take signing authority from a manifest or the artifact tree."""
    pubfile = Path(public_key_file).resolve(strict=True)
    if pubfile.is_relative_to(artifact_root.resolve(strict=True)):
        _deny("release verification key must come from outside the distribution")
    if not isinstance(pinned_fingerprint, str) or not SIGNED.SHA64.fullmatch(
        pinned_fingerprint
    ):
        _deny("independent pinned release-key fingerprint is required")
    pem = SIGNED._read_bounded_regular(str(pubfile), 8192).decode("ascii")
    try:
        computed = MGMT.pubkey_fingerprint(pem)
    except (OSError, ValueError, RuntimeError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: release public key is invalid"
        ) from exc
    if not hmac.compare_digest(computed, pinned_fingerprint):
        _deny("trusted release-key fingerprint mismatch")
    return pem


def _distribution_files_are_safe(root: Path) -> None:
    """Reject special files and symlink substitution before staging."""
    count = 0
    total = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        for entry in dirs + files:
            path = Path(current) / entry
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                _deny("artifact tree contains symlink")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                _deny("artifact tree contains special file")
            if stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    _deny("artifact tree contains hardlinked file")
                count += 1
                total += info.st_size
                if count > MAX_STAGE_FILES or total > MAX_STAGE_BYTES:
                    _deny("artifact tree exceeds bounded stage limits")


def _require_agent_payload_allowlist(root: Path, *, signed: bool) -> None:
    """Only canonical Agent installer files and the approved signature sidecar."""
    directory = root / "agent"
    if not directory.is_dir() or directory.is_symlink():
        _deny("artifact candidate is missing the Agent installer directory")
    allowed = {"bootstrap-client.sh", "bootstrap-client.ps1"}
    if signed:
        allowed.add("manifest.sig")
    actual = {item.name for item in directory.iterdir()}
    if "bootstrap-client.sh" not in actual or actual - allowed:
        _deny("Agent artifact tree contains unsigned or unexpected files")
    if signed and "manifest.sig" not in actual:
        _deny("signed Agent distribution is missing its detached signature")


def _require_frp_artifact_allowlist(root: Path) -> None:
    """Reject unlisted files reachable through the Server's /artifacts/frp/ path."""
    frp = root / "frp"
    if not frp.exists():
        return
    try:
        manifest = QA.load_manifest(root)
    except QA.ArtifactError as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: artifact manifest is unavailable"
        ) from exc
    allowed = {
        str(item.get("relative_path") or "")
        for item in manifest.get("artifacts") or ()
        if isinstance(item, dict)
        and str(item.get("relative_path") or "").startswith("frp/")
    }
    for path in frp.rglob("*"):
        if path.is_file():
            name = "frp/" + path.relative_to(frp).as_posix()
            if name not in allowed:
                _deny("FRP artifact tree contains unlisted distribution file")


def verify_signed_server_tree(
    root: str | Path,
    *,
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
    target: Mapping[str, Any],
    expected_channel: str,
) -> dict[str, Any]:
    """Validate fully staged Server-local bytes and detached signature.

    The Server's historical QA manifest+SHA contract still applies. A separate
    release signature binds the exact manifest bytes, SHA, channel and bundle.
    """
    artifact_root = Path(root).resolve(strict=True)
    if not artifact_root.is_dir():
        _deny("artifact root is not a directory")
    _distribution_files_are_safe(artifact_root)
    _require_agent_payload_allowlist(artifact_root, signed=True)
    _require_frp_artifact_allowlist(artifact_root)
    pem = _trusted_pubkey(
        trusted_release_public_key_file,
        pinned_release_key_fingerprint,
        artifact_root,
    )
    try:
        QA.verify_tree(artifact_root)
    except (QA.ArtifactError, ValueError, OSError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: Server-local SHA256SUMS validation failed"
        ) from exc
    manifest = SIGNED._read_bounded_regular(
        str(artifact_root / "manifest.json"), SIGNED.MAX_MANIFEST_BYTES,
    )
    signature = SIGNED._read_bounded_regular(
        str(artifact_root / SIGNATURE_REL), 1024,
    ).decode("ascii").strip()
    verified = SIGNED.verify_signed_agent_bundle(
        manifest_bytes=manifest, signature_b64=signature,
        trusted_release_public_key=pem,
        bundle_path=artifact_root / SIGNED.AGENT_REL,
        target=target,
        expected_channel=expected_channel,
    )
    return {
        "staged_signature_verified": True,
        "key_fingerprint": pinned_release_key_fingerprint,
        "target": verified,
        "signed_manifest_endpoint": "/artifacts/" + SIGNATURE_REL,
        "published": False,
        "update_completed": False,
        "rollback_verified": False,
    }


def stage_signed_candidate(
    unsigned_artifact_root: str | Path,
    *,
    detached_signature_file: str | Path,
    trusted_release_public_key_file: str | Path,
    pinned_release_key_fingerprint: str,
    target: Mapping[str, Any],
    expected_channel: str,
    staging_parent: str | Path,
) -> dict[str, Any]:
    """Copy and verify to a new isolated candidate directory, never publish.

    An external authorized signer creates the detached signature over the exact
    manifest bytes. Staging neither receives nor uses the release PRIVATE key.
    The destination is a unique new private candidate dir for operator review.
    """
    src = Path(unsigned_artifact_root).resolve(strict=True)
    parent = Path(staging_parent).resolve(strict=True)
    installed = Path(QA.INSTALLED_ARTIFACT_ROOT).resolve()
    if not src.is_dir() or not parent.is_dir():
        _deny("stage input and parent must be existing directories")
    if (src == parent or src.is_relative_to(parent)
        or parent.is_relative_to(src)):
        _deny("signed candidate staging must be outside source tree")
    if parent == installed or parent.is_relative_to(installed):
        _deny("cannot stage inside installed Server artifacts")
    _distribution_files_are_safe(src)
    _require_agent_payload_allowlist(src, signed=False)
    _require_frp_artifact_allowlist(src)
    try:
        QA.verify_tree(src)
    except (QA.ArtifactError, ValueError, OSError) as exc:
        raise SIGNED.AgentArtifactError(
            "AGENT_ARTIFACT_UNQUALIFIED: unsigned source tree failed SHA validation"
        ) from exc
    # Verify incoming signer identity and signed bytes *before* creating the
    # destination. The signer public key must never come from source artifacts.
    pem = _trusted_pubkey(
        trusted_release_public_key_file, pinned_release_key_fingerprint, src,
    )
    manifest_bytes = SIGNED._read_bounded_regular(
        str(src / "manifest.json"), SIGNED.MAX_MANIFEST_BYTES,
    )
    raw_signature = SIGNED._read_bounded_regular(
        str(detached_signature_file), 1024,
    ).decode("ascii").strip()
    SIGNED.verify_signed_agent_bundle(
        manifest_bytes=manifest_bytes, signature_b64=raw_signature,
        trusted_release_public_key=pem,
        bundle_path=src / SIGNED.AGENT_REL,
        target=target, expected_channel=expected_channel,
    )

    temp = Path(tempfile.mkdtemp(prefix=".drlink-v30-signed-candidate-", dir=parent))
    completed = False
    try:
        for entry in src.iterdir():
            destination = temp / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination, symlinks=True)
            else:
                shutil.copy2(entry, destination, follow_symlinks=False)
        signature_path = temp / SIGNATURE_REL
        # Never copy a pre-existing, unverified sidecar into the trusted output.
        if signature_path.exists() or signature_path.is_symlink():
            _deny("source tree contains a pre-existing detached signature")
        with signature_path.open("x", encoding="ascii") as handle:
            handle.write(raw_signature + "\n")
        signature_path.chmod(0o644)
        report = verify_signed_server_tree(
            temp,
            trusted_release_public_key_file=trusted_release_public_key_file,
            pinned_release_key_fingerprint=pinned_release_key_fingerprint,
            target=target, expected_channel=expected_channel,
        )
        completed = True
        return {"candidate_path": str(temp), **report}
    finally:
        if not completed:
            shutil.rmtree(temp, ignore_errors=True)
