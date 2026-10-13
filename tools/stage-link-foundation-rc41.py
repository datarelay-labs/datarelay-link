#!/usr/bin/env python3
"""Offline-only private RC41 Link Web compatibility staging.

Never modifies the checkout, real Web installation, public npm lockfile or Git.
A complete independently pinned RC41 archive must already be supplied by an
authorized private channel. No archive transport or registry publication here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
GATE = HERE / "verify-link-foundation-rc41.py"
spec = importlib.util.spec_from_file_location("drlink_rc41_gate", GATE)
if spec is None or spec.loader is None:
    raise RuntimeError("Pinned RC41 verifier unavailable")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class StageError(ValueError):
    """Insufficient product-private package or safety evidence."""


def source_head_from_lock(locked: dict) -> str:
    if not isinstance(locked, dict):
        raise StageError("Foundation lock is not a mapping")
    if (locked.get("source_head") != gate.SOURCE
            or locked.get("version") != gate.VERSION
            or locked.get("commit") != gate.SOURCE
            or locked.get("schema_version") != 1):
        raise StageError("Foundation source/version/manifest mismatch")
    rows = locked.get("packages")
    if not isinstance(rows, list) or len(rows) != len(gate.PACKAGE_SHA256):
        raise StageError("Foundation package family is incomplete")
    mapped = {}
    for row in rows:
        if not isinstance(row, dict):
            raise StageError("Invalid Foundation package manifest row")
        name = row.get("name")
        if not isinstance(name, str) or not name.startswith("@datarelay-labs/"):
            raise StageError("Invalid Foundation package identity")
        short = name.removeprefix("@datarelay-labs/")
        if short in mapped or short not in gate.PACKAGE_SHA256:
            raise StageError("Foundation package identity duplicated/unknown")
        if row.get("archive_sha256") != gate.PACKAGE_SHA256[short]:
            raise StageError("Foundation package digest conflicts with owner pin")
        mapped[short] = row
    if set(mapped) != set(gate.PACKAGE_SHA256):
        raise StageError("Incomplete Foundation package family")
    return locked["source_head"]


def pinned_web_dependencies(package: dict) -> dict:
    if not isinstance(package, dict) or not isinstance(package.get("dependencies"), dict):
        raise StageError("Link Web dependencies unavailable")
    result = json.loads(json.dumps(package))
    deps = result["dependencies"]
    for short in gate.PACKAGE_SHA256:
        name = "@datarelay-labs/" + short
        existing = deps.get(name)
        if not isinstance(existing, str) or not existing.startswith("file:.foundation/packs/"):
            raise StageError("Existing Foundation family is not an offline pinned family")
        deps[name] = (
            "file:.foundation/packs/datarelay-labs-" + short + "-" +
            gate.VERSION + ".tgz"
        )
    if len([name for name in deps if name.startswith("@datarelay-labs/")]) != len(gate.PACKAGE_SHA256):
        raise StageError("Unexpected extra Foundation dependencies")
    return result


def private_scratch_root(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise StageError("Private scratch root must exist and be an absolute non-symlink directory")
    root = path.resolve(strict=True)
    repo = REPO.resolve(strict=True)
    if root == repo or repo in root.parents or root in repo.parents:
        raise StageError("Private staging must be outside the Link repository")
    if root.stat().st_mode & 0o077:
        raise StageError("Private scratch directory must have owner-only permissions")
    return root


PRODUCT_TEST_DOCS = (
    "COMPETITOR_UI_APPLIED_MATRIX_2026-10-12.md",
    "COMPETITOR_UI_SCREEN_EVIDENCE_2026-10-11.md",
    "WEB_UX_COMPETITIVE_AUDIT_2026-10.md",
    "WEB_USER_JOURNEY_UX_ROADMAP.md",
)


def prepare_copy(web_source: Path, scratch_web: Path):
    if not (web_source / "package.json").is_file():
        raise StageError("Link Web source/package.json missing")
    # Reuse only public package-lock metadata for offline third-party dependencies.
    # npm resolves the ten *verified* RC41 archives solely in private scratch.
    shutil.copytree(
        web_source, scratch_web,
        ignore=shutil.ignore_patterns(".foundation", "node_modules", "dist"),
    )
    original_dist = web_source / "dist" / "styles.css"
    if not original_dist.is_file():
        raise StageError("Link Web source stylesheet is missing")
    (scratch_web / "dist").mkdir()
    shutil.copy2(original_dist, scratch_web / "dist" / "styles.css")
    # Native Web tests audit the exact Link-owned, PUBLIC docs and Core
    # service projection alongside source. Omitting them produces false REDs.
    root = web_source.parent
    (scratch_web.parent / "docs").mkdir(exist_ok=True)
    (scratch_web.parent / "lib").mkdir(exist_ok=True)
    for name in PRODUCT_TEST_DOCS:
        shutil.copy2(root / "docs" / name, scratch_web.parent / "docs" / name)
    shutil.copy2(root / "lib" / "drlink_management_service.py",
                 scratch_web.parent / "lib" / "drlink_management_service.py")


def stage_archives(bundle: Path, scratch_web: Path) -> None:
    destination = scratch_web / ".foundation" / "packs"
    destination.mkdir(parents=True, mode=0o700)
    prefix = gate.SOURCE + "/"
    with tarfile.open(bundle, "r:gz") as archive:
        entry = archive.extractfile(prefix + "foundation.lock.json")
        if entry is None:
            raise StageError("Verified Foundation lock entry not readable")
        with entry:
            locked = json.loads(entry.read())
        source_head_from_lock(locked)
        for short, expected in gate.PACKAGE_SHA256.items():
            filename = "datarelay-labs-" + short + "-" + gate.VERSION + ".tgz"
            entry = archive.extractfile(prefix + "archives/" + filename)
            if entry is None:
                raise StageError("Verified Foundation package missing")
            dest = destination / filename
            with entry, dest.open("xb") as target:
                shutil.copyfileobj(entry, target)
            dest.chmod(0o600)
            if gate.digest_file(dest) != expected:
                raise StageError("Staged private package digest mismatch")
    (scratch_web / "foundation.lock.json").write_text(
        json.dumps(locked, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (scratch_web / "package.json").write_text(
        json.dumps(pinned_web_dependencies(json.loads(
            (scratch_web / "package.json").read_text(encoding="utf-8")
        )), indent=2) + "\n", encoding="utf-8"
    )


def stage_reproduced_private_packages(
    source_checkout: Path, pack_dir: Path, source_manifest: Path, scratch_web: Path
) -> None:
    """Accept only exact RC41 bytes rebuilt from authenticated immutable source.

    This is NOT a transfer of the previously safety-denied private archive.
    The Foundation Git source and every tarball must already exist in the
    owner-authorized private local checkout.
    """
    private_scratch_root(source_checkout)
    if not pack_dir.is_absolute() or pack_dir.is_symlink() or not pack_dir.is_dir():
        raise StageError("Private package directory is unavailable")
    if not source_manifest.is_absolute() or source_manifest.is_symlink() or not source_manifest.is_file():
        raise StageError("Original-source package manifest is unavailable")
    repo = REPO.resolve(strict=True)
    for candidate in (pack_dir.resolve(strict=True), source_manifest.resolve(strict=True)):
        if candidate == repo or repo in candidate.parents or candidate in repo.parents:
            raise StageError("Private packages cannot be loaded from the public repository")
    head = subprocess.check_output(
        ["git", "-C", str(source_checkout), "rev-parse", "HEAD"],
        text=True, timeout=20, stderr=subprocess.DEVNULL,
    ).strip()
    if head != gate.SOURCE:
        raise StageError("Original private Foundation Git HEAD mismatch")
    dirty = subprocess.check_output(
        ["git", "-C", str(source_checkout), "status", "--porcelain"],
        text=True, timeout=20, stderr=subprocess.DEVNULL,
    )
    if dirty.strip():
        raise StageError("Original private Foundation Git checkout is modified")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("version") != gate.VERSION:
        raise StageError("Original Foundation release stage version mismatch")
    rows = manifest.get("packages")
    if not isinstance(rows, list) or len(rows) != len(gate.PACKAGE_SHA256):
        raise StageError("Original Foundation release stage package family incomplete")
    locked = dict(manifest)
    locked.update(commit=gate.SOURCE, source_head=gate.SOURCE)
    locked["packages"] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("name") != "@datarelay-labs/" + str(row.get("path")):
            raise StageError("Original package manifest identity mismatch")
        short = row["path"]
        if short not in gate.PACKAGE_SHA256:
            raise StageError("Unrecognized Foundation private package")
        if not isinstance(row.get("sha256"), str) or len(row["sha256"]) != 64:
            raise StageError("Original package source digest missing")
        locked["packages"].append({
            **row, "archive_sha256": gate.PACKAGE_SHA256[short]
        })
    source_head_from_lock(locked)
    destination = scratch_web / ".foundation" / "packs"
    destination.mkdir(parents=True, mode=0o700)
    for short, expected in gate.PACKAGE_SHA256.items():
        filename = f"datarelay-labs-{short}-{gate.VERSION}.tgz"
        candidate = pack_dir / filename
        if not candidate.is_file() or candidate.is_symlink():
            raise StageError("Required private package archive unavailable: " + short)
        if gate.digest_file(candidate) != expected:
            raise StageError("Original RC41 package SHA256 mismatch: " + short)
        staged = destination / filename
        shutil.copyfile(candidate, staged)
        staged.chmod(0o600)
        if gate.digest_file(staged) != expected:
            raise StageError("RC41 archive digest changed while staging")
    (scratch_web / "foundation.lock.json").write_text(
        json.dumps(locked, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (scratch_web / "package.json").write_text(
        json.dumps(pinned_web_dependencies(json.loads(
            (scratch_web / "package.json").read_text(encoding="utf-8")
        )), indent=2) + "\n", encoding="utf-8"
    )


def validate_installed_family(scratch_web: Path) -> None:
    for short in gate.PACKAGE_SHA256:
        package = scratch_web / "node_modules" / "@datarelay-labs" / short / "package.json"
        if not package.is_file():
            raise StageError("Installed Foundation package missing: " + short)
        obj = json.loads(package.read_text(encoding="utf-8"))
        if obj.get("name") != "@datarelay-labs/" + short or obj.get("version") != gate.VERSION:
            raise StageError("Installed Foundation package identity/version mismatch: " + short)


def verify_private_web_runtime(scratch_web: Path, *, run=subprocess.run) -> None:
    env = dict(os.environ)
    env["CI"] = "true"
    env["npm_config_offline"] = "true"
    for command in (
        ["npm", "install", "--offline", "--ignore-scripts", "--no-audit", "--no-fund"],
        ["npm", "run", "build"],
        ["npm", "run", "test:administration"],
        ["npm", "run", "test:journey"],
        ["npm", "run", "test:p0"],
    ):
        run(command, cwd=scratch_web, env=env, check=True, timeout=300)
        if command[1] == "install":
            validate_installed_family(scratch_web)


def run_private_compatibility(
    bundle: Path, private_root: Path, web_source: Path, *, run=subprocess.run
) -> None:
    # Original immutable whole-bundle receipt remains the independent authority.
    gate.verify_bundle(bundle)
    private_root = private_scratch_root(private_root)
    if web_source.resolve(strict=True) != (REPO / "web").resolve(strict=True):
        raise StageError("Only the checked-out Link Web source is accepted")
    with tempfile.TemporaryDirectory(prefix="drlink-foundation-rc41-", dir=private_root) as scratch:
        scratch_web = Path(scratch) / "web"
        prepare_copy(web_source, scratch_web)
        stage_archives(bundle, scratch_web)
        verify_private_web_runtime(scratch_web, run=run)


def run_reproduced_compatibility(
    source_checkout: Path, pack_dir: Path, source_manifest: Path,
    private_root: Path, web_source: Path, *, run=subprocess.run
) -> None:
    private_root = private_scratch_root(private_root)
    if web_source.resolve(strict=True) != (REPO / "web").resolve(strict=True):
        raise StageError("Only the checked-out Link Web source is accepted")
    with tempfile.TemporaryDirectory(prefix="drlink-foundation-rc41-", dir=private_root) as scratch:
        scratch_web = Path(scratch) / "web"
        prepare_copy(web_source, scratch_web)
        stage_reproduced_private_packages(source_checkout, pack_dir, source_manifest, scratch_web)
        verify_private_web_runtime(scratch_web, run=run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle", type=Path)
    source.add_argument("--verified-package-dir", type=Path)
    parser.add_argument("--private-source-checkout", type=Path)
    parser.add_argument("--source-package-manifest", type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.bundle is not None:
            if args.private_source_checkout or args.source_package_manifest:
                raise StageError("Whole bundle and original-source flags are mutually exclusive")
            run_private_compatibility(args.bundle, args.private_root, REPO / "web")
        else:
            if args.private_source_checkout is None or args.source_package_manifest is None:
                raise StageError("Verified original-source checkout and package manifest required")
            run_reproduced_compatibility(
                args.private_source_checkout, args.verified_package_dir,
                args.source_package_manifest, args.private_root, REPO / "web"
            )
    except (StageError, gate.CandidateError, OSError, ValueError,
            json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print("FOUNDATION_RC41_LINK_COMPATIBILITY=BLOCKED")
        print("REASON=" + str(exc))
        return 1
    print("FOUNDATION_RC41_LINK_COMPATIBILITY=PASS")
    print("FOUNDATION_SOURCE=" + gate.SOURCE)
    print("PRIVATE_STAGING_REMOVED=YES")
    print("PUBLIC_PACKAGE_PINS_UNCHANGED=YES")
    print("LIVE_PRODUCT_RC41_INSTALLED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
