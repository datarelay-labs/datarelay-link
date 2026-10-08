#!/usr/bin/env python3
"""Build deterministic optional Data Relay Link Web package."""
from __future__ import annotations

import gzip
import hashlib
import re
import json
import io
import stat
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/data-relay-link-web.tar.gz"
MANIFEST = ROOT / "lib/web-project-files.manifest"
BUILD_FILES = (
    "VERSION",
    "install-web.sh",
    "uninstall-web.sh",
    "lib/web-project-files.manifest",
    "web/package.json",
    "web/package-lock.json",
    "web/foundation.lock.json",
    "web/src/main.tsx",
)


def manifest_sources() -> tuple[str, ...]:
    sources: list[str] = []
    for lineno, raw in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        parts = text.split()
        if len(parts) != 4:
            raise SystemExit("invalid Web package manifest line %d" % lineno)
        src, dest, mode, kind = parts
        if src.startswith("/") or dest.startswith("/") or ".." in Path(src).parts or ".." in Path(dest).parts:
            raise SystemExit("unsafe Web package manifest line %d" % lineno)
        if mode not in ("0644", "0755") or kind not in ("python", "systemd", "static"):
            raise SystemExit("invalid Web package manifest line %d" % lineno)
        sources.append(src)
    if len(sources) != len(set(sources)):
        raise SystemExit("duplicate Web package manifest source")
    return tuple(sources)


def foundation_pack_sources(root: Path = ROOT) -> tuple[str, ...]:
    """Validate the exact vendored tgz bytes using explicit archive checksums.

    sha256 identifies the staged package DIRECTORY. archive_sha256 identifies
    the separately produced tgz; these two digests are not interchangeable.
    """
    data = json.loads((root / "web/foundation.lock.json").read_text(encoding="utf-8"))
    version = data.get("version")
    packages = data.get("packages")
    head = data.get("source_head")
    if (
        not isinstance(version, str)
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-[A-Za-z0-9.-]+", version)
        or not isinstance(head, str)
        or not re.fullmatch("[0-9a-f]{40}", head)
        or data.get("commit") != head
        or not isinstance(packages, list)
        or len(packages) != 10
    ):
        raise SystemExit("invalid pinned Foundation package manifest")
    paths = []
    known = {
        "tokens", "icons", "ui", "product-shell", "auth-ui",
        "system-contracts", "system-admin-ui", "testkit", "foundation", "foundation-cli",
    }
    seen = set()
    for entry in packages:
        name = entry.get("path") if isinstance(entry, dict) else None
        archive_sha = entry.get("archive_sha256") if isinstance(entry, dict) else None
        staged_sha = entry.get("sha256") if isinstance(entry, dict) else None
        if (
            not isinstance(name, str)
            or name not in known
            or name in seen
            or entry.get("name") != "@datarelay-labs/" + name
            or not isinstance(archive_sha, str)
            or not re.fullmatch("[0-9a-f]{64}", archive_sha)
            or not isinstance(staged_sha, str)
            or not re.fullmatch("[0-9a-f]{64}", staged_sha)
        ):
            raise SystemExit("invalid Foundation package entry:" + str(name))
        seen.add(name)
        relative = "web/.foundation/packs/datarelay-labs-%s-%s.tgz" % (name, version)
        archive = root / relative
        if root.is_symlink() or any(
            (root / Path(*Path(relative).parts[:index])).is_symlink()
            for index in range(1, len(Path(relative).parts))
        ):
            raise SystemExit("foundation-archive-unsafe:" + name)
        try:
            info = archive.lstat()
        except FileNotFoundError:
            raise SystemExit("foundation-archive-missing:" + name) from None
        # Never package a symlink or hard-linked external file even if its
        # current bytes match the pinned digest.
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SystemExit("foundation-archive-unsafe:" + name)
        with archive.open("rb") as file:
            actual = hashlib.file_digest(file, "sha256").hexdigest()
        if actual != archive_sha:
            raise SystemExit("foundation-archive-sha-mismatch:" + name)
        paths.append(relative)
    if seen != known:
        raise SystemExit("invalid Foundation package set")
    return tuple(paths)


def package_files() -> tuple[str, ...]:
    return tuple(dict.fromkeys((*BUILD_FILES, *foundation_pack_sources(), *manifest_sources())))


FILES = package_files()


def normalized(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if info.isfile():
        if info.name.endswith(
            (
                "install-web.sh",
                "uninstall-web.sh",
                "drlink-web.py",
                "drlink-web-bootstrap",
                "drlink-web-recovery",
                "drlink-web-operator",
            )
        ):
            info.mode = 0o755
        else:
            info.mode = 0o644
    return info


def build(output: Path = OUTPUT) -> Path:
    # Recheck vendored bytes immediately before emitting the distributable.
    foundation_pack_sources()
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("missing Web package files: %s" % ", ".join(missing))
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name in sorted(FILES):
            tf.add(ROOT / name, arcname="data-relay-link-web/" + name, filter=normalized)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(buffer.getvalue())
    return output


if __name__ == "__main__":
    print(build())
