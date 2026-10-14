#!/usr/bin/env python3
"""Prepare a reproducible PRIVATE Link Web install candidate with Foundation RC41.

Never publishes private Foundation packages, changes public Link default pins,
installs on the live host, starts daemons, or authorizes product release.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGER = Path(__file__).with_name("stage-link-foundation-rc41.py")
spec = importlib.util.spec_from_file_location("private_foundation_rc41_stage", STAGER)
assert spec and spec.loader
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class PrivateBundleError(ValueError):
    """Fail closed on unsafe private Web packaging or unverified source."""


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args], text=True,
        timeout=30, stderr=subprocess.DEVNULL,
    ).strip()


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_output(private_root: Path, output_dir: Path) -> Path:
    root = stage.private_scratch_root(private_root)
    if not output_dir.is_absolute() or output_dir.is_symlink():
        raise PrivateBundleError("Private output must be an absolute non-symlink path")
    requested = output_dir.resolve(strict=False)
    if root not in requested.parents:
        raise PrivateBundleError("Private output must be inside the approved 0700 root")
    if requested.exists():
        if not requested.is_dir() or any(requested.iterdir()):
            raise PrivateBundleError("Private output directory must be empty")
        if requested.stat().st_mode & 0o077:
            raise PrivateBundleError("Private output directory must be owner-only")
    else:
        requested.mkdir(mode=0o700)
    return requested


def unpack_link_source(target: Path, link_head: str) -> None:
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", link_head],
        capture_output=True, timeout=60, check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as files:
        for member in files.getmembers():
            parts = Path(member.name).parts
            if (not parts or member.name.startswith("/") or ".." in parts
                    or member.issym() or member.islnk()
                    or not (member.isfile() or member.isdir())):
                raise PrivateBundleError("Link Git archive has unsafe entries")
        files.extractall(target, filter="data")


def clear_old_packages_in_private_export(web: Path, private_root: Path) -> int:
    """Remove only historic public pins in an isolated Git-exported Web tree."""
    root = stage.private_scratch_root(private_root)
    resolved = web.resolve(strict=True)
    if root not in resolved.parents:
        raise PrivateBundleError("Cannot edit Foundation packages outside private staging")
    packs = web / ".foundation" / "packs"
    if packs.is_symlink() or not packs.is_dir():
        raise PrivateBundleError("Private Web archive directory is invalid")
    files = list(packs.iterdir())
    if not files:
        raise PrivateBundleError("Historic fallback inventory not found in private export")
    for item in files:
        if (item.is_symlink() or not item.is_file()
                or not item.name.startswith("datarelay-labs-")
                or not item.name.endswith(".tgz")):
            raise PrivateBundleError("Unexpected private export package member")
    for item in files:
        item.unlink()
    packs.rmdir()
    return len(files)


def _exec(command: list[str], *, cwd: Path, env: dict | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=360)


def _qualify_tar(bundle: Path, link_head: str, workspace: Path) -> int:
    from_package = "data-relay-link-web/"
    with tarfile.open(bundle, "r:gz") as tar:
        members = tar.getmembers()
        for m in members:
            if (not m.name.startswith(from_package) or ".." in Path(m.name).parts
                    or m.issym() or m.islnk() or not m.isfile()):
                raise PrivateBundleError("Invalid private Web distribution entry")
        archive_names = {m.name for m in members}
        packs = [n for n in archive_names if
                 n.startswith(from_package + "web/.foundation/packs/") and
                 n.endswith(".tgz")]
        if len(packs) != len(stage.gate.PACKAGE_SHA256):
            raise PrivateBundleError("RC41 Web bundle must contain all ten archives")
        for short, expected in stage.gate.PACKAGE_SHA256.items():
            name = (from_package + "web/.foundation/packs/datarelay-labs-" +
                    short + "-" + stage.gate.VERSION + ".tgz")
            if name not in archive_names:
                raise PrivateBundleError("Missing pinned private Foundation archive")
            file = tar.extractfile(name)
            if file is None or hashlib.sha256(file.read()).hexdigest() != expected:
                raise PrivateBundleError("Private RC41 archive SHA256 mismatch")
        for static in ("index.html", "app.js", "styles.css",
                       "foundation.css", "favicon.svg"):
            if from_package + "web/dist/" + static not in archive_names:
                raise PrivateBundleError("Missing Web runtime static file")
    return len(packs)


def disposable_install(bundle: Path, source_head: str, sha: str, root: Path) -> None:
    extracted = root / "unpacked"
    extracted.mkdir()
    with tarfile.open(bundle, "r:gz") as tar:
        # This was just verified as having regular, safe, single-root members.
        tar.extractall(extracted, filter="data")
    private_repo = extracted / "data-relay-link-web"
    target = root / "fake-installed-root"
    target.mkdir()
    db = target / "var/lib/drlink/drlink.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA user_version=0")
    env = dict(os.environ)
    env.update(
        DRLINK_WEB_INSTALL_ROOT=str(target),
        DRLINK_WEB_INSTALL_SKIP_SYSTEMD="1",
        DRLINK_WEB_SOURCE_HEAD=source_head,
        DRLINK_WEB_SOURCE_REF=source_head,
        DRLINK_WEB_BUNDLE_SHA256=sha,
    )
    result = subprocess.run(
        ["bash", "install-web.sh"], cwd=private_repo,
        env=env, capture_output=True, text=True, timeout=60, check=True,
    )
    if "DRLINK_WEB_INSTALL=PASS" not in result.stdout:
        raise PrivateBundleError("Disposable Web installer has no PASS receipt")
    installed = target / "usr/local/share/drlink-web"
    for file in ("index.html", "app.js", "styles.css",
                 "foundation.css", "favicon.svg"):
        if _digest(installed / file) != _digest(private_repo / "web/dist" / file):
            raise PrivateBundleError("Disposable installed Web asset differs")
    marker = json.loads((installed / "build.json").read_text(encoding="utf-8"))
    if marker.get("source_head") != source_head or marker.get("bundle_sha256") != sha:
        raise PrivateBundleError("Disposable Web source/bundle marker mismatch")


def build_private_candidate(
    source_checkout: Path, pack_dir: Path, source_manifest: Path,
    private_root: Path, output_dir: Path
) -> dict[str, str | int]:
    private_root = stage.private_scratch_root(private_root)
    current_head = _git("rev-parse", "HEAD")
    if len(current_head) != 40 or _git("status", "--porcelain"):
        raise PrivateBundleError("Link checkout must be clean and source-pinned")
    output_dir = validate_output(private_root, output_dir)
    with tempfile.TemporaryDirectory(prefix="link-rc41-package-", dir=private_root) as tmp:
        scratch = Path(tmp)
        work = scratch / "link"
        work.mkdir()
        unpack_link_source(work, current_head)
        web = work / "web"
        # Git archive brings the public pf8.4 rollback files into the PRIVATE
        # copy. Remove only those copies before immutable RC41 package staging.
        clear_old_packages_in_private_export(web, private_root)
        stage.stage_reproduced_private_packages(
            source_checkout, pack_dir, source_manifest, web,
        )
        stage.verify_private_web_runtime(web)
        private_bundle = work / "dist" / "data-relay-link-web.tar.gz"
        _exec([sys.executable, "scripts/build-web-bundle.py"], cwd=work)
        first_sha = _digest(private_bundle)
        _exec([sys.executable, "scripts/build-web-bundle.py"], cwd=work)
        if _digest(private_bundle) != first_sha:
            raise PrivateBundleError("Web distribution is not deterministic")
        count = _qualify_tar(private_bundle, current_head, scratch)
        disposable_install(private_bundle, current_head, first_sha, scratch)
        name = ("data-relay-link-web-foundation-rc41-" +
                current_head[:12] + ".private.tar.gz")
        destination = output_dir / name
        shutil.copyfile(private_bundle, destination)
        destination.chmod(0o600)
        if _digest(destination) != first_sha:
            raise PrivateBundleError("Final private candidate digest mismatch")
        receipt = {
            "schema_version": 1,
            "private_unpublished": True,
            "live_product_installed": False,
            "user_e2e_pass": False,
            "source_head": current_head,
            "foundation_head": stage.gate.SOURCE,
            "foundation_version": stage.gate.VERSION,
            "foundation_package_count": count,
            "bundle_sha256": first_sha,
            "bundle_file": name,
            "disposable_install": "PASS",
            "web_suites": "PASS",
            "publisher_authenticated": False,
        }
        (output_dir / "private-build-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-source-checkout", required=True, type=Path)
    parser.add_argument("--verified-package-dir", required=True, type=Path)
    parser.add_argument("--source-package-manifest", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = build_private_candidate(
            args.private_source_checkout, args.verified_package_dir,
            args.source_package_manifest, args.private_root, args.output_dir,
        )
    except (PrivateBundleError, stage.StageError, stage.gate.CandidateError,
            OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print("RC41_PRIVATE_LINK_WEB_BUNDLE=BLOCKED")
        print("REASON=" + str(exc))
        return 1
    print("RC41_PRIVATE_LINK_WEB_BUNDLE=PASS")
    print("FOUNDATION_HEAD=" + str(receipt["foundation_head"]))
    print("LINK_HEAD=" + str(receipt["source_head"]))
    print("SHA256=" + str(receipt["bundle_sha256"]))
    print("BUNDLE=" + str(receipt["bundle_file"]))
    print("LIVE_PRODUCT_UNCHANGED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
