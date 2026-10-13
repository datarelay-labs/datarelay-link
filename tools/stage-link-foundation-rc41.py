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


def prepare_copy(web_source: Path, scratch_web: Path):
    if not (web_source / "package.json").is_file():
        raise StageError("Link Web source/package.json missing")
    shutil.copytree(
        web_source, scratch_web,
        ignore=shutil.ignore_patterns(".foundation", "node_modules", "dist", "package-lock.json"),
    )


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


def validate_installed_family(scratch_web: Path) -> None:
    for short in gate.PACKAGE_SHA256:
        package = scratch_web / "node_modules" / "@datarelay-labs" / short / "package.json"
        if not package.is_file():
            raise StageError("Installed Foundation package missing: " + short)
        obj = json.loads(package.read_text(encoding="utf-8"))
        if obj.get("name") != "@datarelay-labs/" + short or obj.get("version") != gate.VERSION:
            raise StageError("Installed Foundation package identity/version mismatch: " + short)


def run_private_compatibility(bundle: Path, private_root: Path, web_source: Path, *, run=subprocess.run) -> None:
    # The only production-callable verification uses the independent literal
    # expected archive length and outer/inner digest; no CLI test overrides.
    gate.verify_bundle(bundle)
    private_root = private_scratch_root(private_root)
    if web_source.resolve(strict=True) != (REPO / "web").resolve(strict=True):
        raise StageError("Only the checked-out Link Web source is accepted")
    with tempfile.TemporaryDirectory(prefix="drlink-foundation-rc41-", dir=private_root) as scratch:
        scratch_web = Path(scratch) / "web"
        prepare_copy(web_source, scratch_web)
        stage_archives(bundle, scratch_web)
        env = dict(os.environ)
        env["CI"] = "true"
        env["npm_config_offline"] = "true"
        for command in (
            ["npm", "install", "--offline", "--ignore-scripts", "--no-audit",
             "--no-fund", "--package-lock=false"],
            ["npm", "run", "build"],
            ["npm", "run", "test:administration"],
            ["npm", "run", "test:journey"],
        ):
            run(command, cwd=scratch_web, env=env, check=True, timeout=300)
            if command[1] == "install":
                validate_installed_family(scratch_web)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        run_private_compatibility(args.bundle, args.private_root, REPO / "web")
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
