"""Link PF-12C read-only offline archive byte qualification; never update a host.

The caller pins a manifest SHA256 separately. This proves *bytes*, not publisher
identity: the product's privileged installer must verify a trusted signature,
recovery/backup state and final revision before any future install operation.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator

from drlink_foundation_security import (
    FoundationArtifactKind,
    FoundationArtifactProof,
    FoundationInstalledProduct,
    FoundationOfflineArtifact,
    FoundationUpgradeEvidence,
    foundation_preview_offline_upgrade,
    foundation_verify_stream_sha256,
)

MAX_OFFLINE_ARCHIVE_BYTES = 2 * 1024**3
MAX_MANIFEST_BYTES = 64 * 1024
MAX_VERSION_BYTES = 8192
_READ_SIZE = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_HEAD = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_MANIFEST_KEYS = frozenset({
    "schema_version", "product_ref", "release_ref", "version", "kind",
    "artifact_sha256", "artifact_bytes", "publisher_key_ref",
})


class OfflinePreflightError(ValueError):
    """Non-sensitive typed failure suitable for a local CLI diagnostic."""


@contextmanager
def _safe_regular_file(path: Path | str, limit: int) -> Iterator[tuple[Any, os.stat_result]]:
    """No-follow directory FD walk and inode-stable read of an exact regular file."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        raise OfflinePreflightError("invalid_offline_source")
    parent_fd = None
    file_fd = None
    try:
        parent_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for part in path.parts[1:-1]:
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            os.close(parent_fd)
            parent_fd = next_fd
        file_fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        initial = os.fstat(file_fd)
        if (
            not stat.S_ISREG(initial.st_mode)
            or initial.st_nlink != 1
            or not 0 < initial.st_size <= limit
        ):
            raise OfflinePreflightError("invalid_offline_source")
        with os.fdopen(file_fd, "rb") as stream:
            file_fd = None
            yield stream, initial
            final = os.fstat(stream.fileno())
            if (
                (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns)
                != (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns)
            ):
                raise OfflinePreflightError("offline_source_changed")
    except OSError as exc:
        raise OfflinePreflightError("invalid_offline_source") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _single_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise OfflinePreflightError("invalid_offline_manifest")
        result[name] = value
    return result


def _manifest(path: Path | str, expected_sha256: str) -> tuple[dict[str, Any], str]:
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise OfflinePreflightError("manifest_integrity_invalid")
    with _safe_regular_file(path, MAX_MANIFEST_BYTES) as (stream, _info):
        source = stream.read(MAX_MANIFEST_BYTES + 1)
    digest = hashlib.sha256(source).hexdigest()
    if digest != expected_sha256:
        raise OfflinePreflightError("manifest_integrity_invalid")
    try:
        obj = json.loads(source.decode("utf-8"), object_pairs_hook=_single_object)
        if not isinstance(obj, dict) or set(obj) != _MANIFEST_KEYS:
            raise OfflinePreflightError("invalid_offline_manifest")
        if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
            raise OfflinePreflightError("invalid_offline_manifest")
        if type(obj["artifact_bytes"]) is not int or not 0 < obj["artifact_bytes"] <= MAX_OFFLINE_ARCHIVE_BYTES:
            raise OfflinePreflightError("invalid_offline_manifest")
    except (UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise OfflinePreflightError("invalid_offline_manifest") from exc
    return obj, digest


def _installed_product(root: Path | str) -> FoundationInstalledProduct:
    path = Path(root) / "etc/drlink/version"
    with _safe_regular_file(path, MAX_VERSION_BYTES) as (stream, _info):
        try:
            lines = stream.read(MAX_VERSION_BYTES + 1).decode("utf-8").splitlines()
        except UnicodeError as exc:
            raise OfflinePreflightError("installed_identity_unavailable") from exc
    fields: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key in fields:
            raise OfflinePreflightError("installed_identity_unavailable")
        fields[key] = value.strip().strip('"').strip("'")
    head = fields.get("SOURCE_HEAD", "").lower()
    if not _HEAD.fullmatch(head):
        raise OfflinePreflightError("installed_identity_unavailable")
    try:
        # Schema revision is deliberately UNKNOWN (0); all schema gates stay BLOCKED.
        return FoundationInstalledProduct(
            product_ref="drlink",
            installed_version=fields["PROJECT_VERSION"],
            current_revision="git-" + head,
            schema_revision=0,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise OfflinePreflightError("installed_identity_unavailable") from exc


def preflight_offline_release(
    *, root: Path | str, artifact_path: Path | str,
    manifest_path: Path | str, expected_manifest_sha256: str,
) -> dict[str, Any]:
    """Read-only actual-byte integrity + pessimistic shared upgrade blockers.

    No untrusted manifest flags can supply publisher/signature/permission facts.
    A matching supplied checksum is not an authenticated provenance proof.
    """
    item, manifest_digest = _manifest(manifest_path, expected_manifest_sha256)
    try:
        artifact = FoundationOfflineArtifact(
            product_ref=item["product_ref"],
            release_ref=item["release_ref"],
            version=item["version"],
            kind=FoundationArtifactKind(item["kind"]),
            artifact_sha256=item["artifact_sha256"],
            manifest_sha256=manifest_digest,
            artifact_bytes=item["artifact_bytes"],
            publisher_key_ref=item["publisher_key_ref"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise OfflinePreflightError("invalid_offline_manifest") from exc
    installed = _installed_product(root)
    with _safe_regular_file(artifact_path, MAX_OFFLINE_ARCHIVE_BYTES) as (stream, _info):
        def read_chunks():
            while True:
                part = stream.read(_READ_SIZE)
                if not part:
                    break
                yield part
        try:
            bytes_ok = foundation_verify_stream_sha256(
                read_chunks(), expected_sha256=artifact.artifact_sha256,
                expected_bytes=artifact.artifact_bytes,
            )
        except ValueError as exc:
            raise OfflinePreflightError("invalid_offline_source") from exc
    proof = FoundationArtifactProof(
        expected_artifact_sha256=artifact.artifact_sha256,
        expected_manifest_sha256=manifest_digest,
        verified_publisher_key_ref=artifact.publisher_key_ref,
        artifact_bytes_hashed=bytes_ok,
        manifest_bytes_hashed=True,
        manifest_signature_verified=False,
        publisher_trust_verified=False,
        provenance_verified=False,
    )
    evidence = FoundationUpgradeEvidence(
        expected_live_revision=installed.current_revision,
    )
    preview = foundation_preview_offline_upgrade(installed, artifact, proof, evidence)
    if preview.may_submit_to_product_installer:
        raise OfflinePreflightError("unexpected_upgrade_authority")
    return {
        "status": "BLOCKED",
        "product_ref": preview.product_ref,
        "installed_version": preview.installed_version,
        "target_version": preview.target_version,
        "release_ref": preview.release_ref,
        "artifact_bytes_verified": bytes_ok,
        "manifest_bytes_verified": True,
        "publisher_signature_verified": False,
        "publisher_trust_verified": False,
        "provenance_verified": False,
        "may_submit_to_installer": False,
        "upgrade_authorized": False,
        "blockers": [reason.value for reason in preview.blockers],
        "read_only": True,
        "authoritative_mutation": False,
        "meaning": "Actual bytes checked; publisher, recovery and installer authority NOT established.",
    }
