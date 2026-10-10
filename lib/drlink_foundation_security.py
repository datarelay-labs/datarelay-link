"""Verify exact offline Foundation wheel before DRLink Web imports security primitives.

The wheel is one shared upstream implementation, shipped as an optional Web
package member. Never depend on a mutable git ref or network/pip at runtime.
A missing/tampered/mismatched wheel fails closed at Web auth import.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import sys

FOUNDATION_SOURCE_HEAD = "59b8199d6182e0bed2b25307736edb4dad32a246"
FOUNDATION_VERSION = "0.10.0.dev0"
FOUNDATION_WHEEL_SHA256 = "6c7c4c8b425fb181e0c10c61aa7ec4ea47c24121379db2c5230251a3bdbc40db"
FOUNDATION_WHEEL_NAME = "datarelay_onprem_security-0.10.0.dev0-py3-none-any.whl"


def _verify_wheel() -> Path:
    wheel = Path(__file__).resolve().with_name(FOUNDATION_WHEEL_NAME)
    try:
        info = wheel.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != 36276:
            raise ValueError("wheel is not a pinned regular file")
        with wheel.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        if digest != FOUNDATION_WHEEL_SHA256:
            raise ValueError("wheel SHA256 mismatch")
    except (OSError, ValueError) as exc:
        raise RuntimeError("DRLINK_FOUNDATION_SECURITY_WHEEL_UNAVAILABLE") from exc
    return wheel


_WHEEL = _verify_wheel()
_WHEEL_PATH = str(_WHEEL)
if _WHEEL_PATH not in sys.path:
    sys.path.insert(0, _WHEEL_PATH)
from datarelay_onprem_security import (  # noqa: E402
    ArtifactKind as FoundationArtifactKind,
    ArtifactProof as FoundationArtifactProof,
    InstalledProduct as FoundationInstalledProduct,
    OfflineArtifact as FoundationOfflineArtifact,
    UpgradeEvidence as FoundationUpgradeEvidence,
    preview_offline_upgrade as foundation_preview_offline_upgrade,
    verify_stream_sha256 as foundation_verify_stream_sha256,
    AllowEntry as FoundationAllowEntry,
    Decision as FoundationIngressDecision,
    ManagementPolicy as FoundationManagementPolicy,
    SurfacePolicy as FoundationSurfacePolicy,
    authorize_management as foundation_authorize_management,
    canonical_network as foundation_canonical_network,
    code_at as foundation_totp_code_at,
    new_totp_secret as foundation_new_totp_secret,
    verify_totp as foundation_verify_totp,
)
import datarelay_onprem_security as _package  # noqa: E402

# A preloaded module of the same name from another environment is NOT a
# trusted substitute for the byte-verified wheel shipped with this product.
if not str(getattr(_package, "__file__", "")).startswith(_WHEEL_PATH + "/"):
    raise RuntimeError("DRLINK_FOUNDATION_SECURITY_IMPORT_MISMATCH")

__all__ = [
    "FOUNDATION_SOURCE_HEAD",
    "FOUNDATION_VERSION",
    "FOUNDATION_WHEEL_SHA256",
    "FoundationArtifactKind",
    "FoundationArtifactProof",
    "FoundationInstalledProduct",
    "FoundationOfflineArtifact",
    "FoundationUpgradeEvidence",
    "foundation_preview_offline_upgrade",
    "foundation_verify_stream_sha256",
    "FoundationAllowEntry",
    "FoundationIngressDecision",
    "FoundationManagementPolicy",
    "FoundationSurfacePolicy",
    "foundation_authorize_management",
    "foundation_canonical_network",
    "foundation_new_totp_secret",
    "foundation_totp_code_at",
    "foundation_verify_totp",
]
