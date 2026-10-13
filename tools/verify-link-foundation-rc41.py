#!/usr/bin/env python3
"""Read-only, independently pinned private Foundation RC41 consumer preflight.

This tool does not extract archives, install dependencies, publish code, or
authorize a release. The bundled receipt is never its own trust anchor.
"""
from __future__ import annotations

import argparse
import hashlib
import tarfile
from pathlib import Path

SOURCE = "46ddb60cad8eae7b1718588cd19421e61b5300e7"
VERSION = "0.1.0-rc.41"
EXPECTED_SIZE = 171540
BUNDLE_SHA256 = "628dd4d6fd8ccb1d39dd6cc33982a3411fedcca405aa193b3654505fcaaefb48"
WHEEL_NAME = "datarelay_onprem_security-0.10.0.dev0-py3-none-any.whl"
WHEEL_SHA256 = "cad95d8ba2d707690ccdfc8ca097e9e746d8ace0f27d70c1c4c638bc663399b8"
PACKAGE_SHA256 = {
    "auth-ui": "4f106957a23833469d990eda1e5f8252137365290cd1170a0b8a9093051557d5",
    "foundation": "febb1afabe218e57326cdb668bd1d193c15fec90bf166ad5012a4c7d077368e5",
    "foundation-cli": "a422f71f131ae290c38a47c0a92263c0041b0753239e6fb007263e60c5ef5049",
    "icons": "9be6ed7a7b6a4997a977ea4cfbefaf004552c337330fff5feb907ffddd0aaed1",
    "product-shell": "804588099b48379a36bd80b61e5c90dbfd23a2d53afa02865b99ab1f2308f49e",
    "system-admin-ui": "ac6ab650af6bb60fc17497be8858b298d87feb6a0573833e948a4c75867f4666",
    "system-contracts": "441cbee69f52f5eacb9246525de0ac1211b18cd32299e13e14e1c97a862de8ff",
    "testkit": "9764f6f90f3eb3814ddb7e21512aac11d069f706fd696682c2d381080cb7bcf0",
    "tokens": "8e97a56bfcfcd2107a394d40cf072f514e2457ebef105b34badc55b9bd8e8574",
    "ui": "b4232099d614c73480983416c5ecb5aa2a5f8390ad68cf044289f3edcf141940",
}
METADATA = {
    "README-CANDIDATE.txt",
    "SHA256SUMS",
    "byte-evidence.json",
    "foundation.lock.json",
    "handoff-receipt.json",
    "onprem-security-candidate.json",
    "release-manifest.json",
}
MAX_MEMBERS = 64
MAX_MEMBER_BYTES = 8 * 1024 * 1024


class CandidateError(ValueError):
    """Fail closed on an untrusted or incomplete package candidate."""


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _member_digest(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    payload = archive.extractfile(member)
    if payload is None:
        raise CandidateError("Required member is not a readable regular file")
    h = hashlib.sha256()
    size = 0
    with payload:
        for block in iter(lambda: payload.read(1024 * 1024), b""):
            size += len(block)
            if size > MAX_MEMBER_BYTES:
                raise CandidateError("Archive member exceeds limit")
            h.update(block)
    if size != member.size:
        raise CandidateError("Archive member size mismatch")
    return h.hexdigest()


def verify_bundle(
    bundle: Path,
    *,
    source_head: str = SOURCE,
    version: str = VERSION,
    expected_sha256: str = BUNDLE_SHA256,
    expected_size: int = EXPECTED_SIZE,
    package_hashes: dict[str, str] | None = None,
    wheel_sha256: str = WHEEL_SHA256,
) -> int:
    """Verify a private handoff without extracting or trusting its own receipt.

    Overridden expectations are only for independently constructed unit fixtures;
    the product CLI always uses the source-locked literal RC41 expectations.
    """
    package_hashes = PACKAGE_SHA256 if package_hashes is None else package_hashes
    if not (bundle.is_file() and not bundle.is_symlink()):
        raise CandidateError("Candidate must be a regular non-symlink file")
    if bundle.stat().st_size != expected_size or expected_size <= 0:
        raise CandidateError("Candidate byte length does not match independent pin")
    if digest_file(bundle) != expected_sha256:
        raise CandidateError("Candidate SHA256 does not match independent pin")

    prefix = source_head + "/"
    required = {
        prefix + "archives/datarelay-labs-" + short + "-" + version + ".tgz": hash_
        for short, hash_ in package_hashes.items()
    }
    required[prefix + WHEEL_NAME] = wheel_sha256
    required_metadata = {prefix + name for name in METADATA}
    seen: set[str] = set()
    try:
        with tarfile.open(bundle, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > MAX_MEMBERS:
                raise CandidateError("Archive has too many members")
            for item in members:
                name = item.name
                components = name.split("/")
                if (not name.startswith(prefix) or name.startswith("/")
                        or "\\" in name or any(part in ("", ".", "..") for part in components[:-1])
                        or item.issym() or item.islnk() or not (item.isdir() or item.isfile())):
                    raise CandidateError("Archive contains an unsafe member")
                if name in seen:
                    raise CandidateError("Archive contains a duplicate member")
                seen.add(name)
                if item.isfile() and item.size > MAX_MEMBER_BYTES:
                    raise CandidateError("Archive member exceeds limit")
                if name in required:
                    if not item.isfile() or _member_digest(archive, item) != required[name]:
                        raise CandidateError("Package or Wheel SHA256 mismatch: " + name.rsplit("/", 1)[-1])
            if not set(required).issubset(seen):
                raise CandidateError("Candidate missing required package or Wheel")
            if not required_metadata.issubset(seen):
                raise CandidateError("Candidate missing required provenance metadata")
            archive_package_names = {
                name for name in seen if name.startswith(prefix + "archives/")
                and name.endswith(".tgz")
            }
            if archive_package_names != set(required) - {prefix + WHEEL_NAME}:
                raise CandidateError("Unexpected or omitted package family")
    except (tarfile.TarError, OSError) as exc:
        raise CandidateError("Candidate archive is unreadable or corrupt") from exc
    return len(package_hashes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True,
                        help="Private owner-supplied RC41 archive; never commit to public Link Git")
    args = parser.parse_args()
    try:
        count = verify_bundle(args.bundle)
    except (CandidateError, OSError) as exc:
        print("PRIVATE_FOUNDATION_RC41=FAIL")
        print("REASON=" + str(exc))
        return 1
    print("PRIVATE_FOUNDATION_RC41=PASS")
    print("ORIGINAL_SOURCE_HEAD=" + SOURCE)
    print("PACKAGE_COUNT=" + str(count))
    print("PRODUCT_INSTALLED=NOT_VERIFIED")
    print("RELEASE_APPROVED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
