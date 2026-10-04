#!/usr/bin/env python3
"""Build deterministic optional Data Relay Link Web package."""
from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/data-relay-link-web.tar.gz"
MANIFEST = ROOT / "lib/web-project-files.manifest"
BUILD_FILES = (
    "install-web.sh",
    "uninstall-web.sh",
    "lib/web-project-files.manifest",
    "web/package.json",
    "web/package-lock.json",
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


def package_files() -> tuple[str, ...]:
    return tuple(dict.fromkeys((*BUILD_FILES, *manifest_sources())))


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
