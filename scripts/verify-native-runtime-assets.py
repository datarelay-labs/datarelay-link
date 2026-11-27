#!/usr/bin/env python3
"""Verify target runtime asset hashes and that native sources have not drifted."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"x86_64-unknown-linux-gnu", "aarch64-apple-darwin"}
CRATES = (
    "native/drlink-egress/Cargo.toml",
    "native/drlink-egress/Cargo.lock",
    "native/drlink-egress/src",
    "native/drlink-mcp-runtime/Cargo.toml",
    "native/drlink-mcp-runtime/Cargo.lock",
    "native/drlink-mcp-runtime/src",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, check=False)


def main() -> int:
    native_root = ROOT / "lib/native"
    records = sorted(native_root.glob("*/runtime-build.json"))
    targets = {record.parent.name for record in records}
    missing = REQUIRED - targets
    if missing:
        print("ERROR: packaged Rust runtime target(s) missing: " + ", ".join(sorted(missing)), file=sys.stderr)
        return 1
    for record_path in records:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        target_dir = record_path.parent
        target = target_dir.name
        if record.get("target") != target:
            raise SystemExit(f"ERROR: target mismatch in {record_path}")
        source_head = record.get("source_head", "")
        if not source_head or git("cat-file", "-e", f"{source_head}^{{commit}}").returncode != 0:
            raise SystemExit(f"ERROR: source HEAD is unavailable in {record_path}")
        if git("merge-base", "--is-ancestor", source_head, "HEAD").returncode != 0:
            raise SystemExit(f"ERROR: runtime source HEAD is not an ancestor of repository HEAD: {target}")
        if git("diff", "--quiet", source_head, "HEAD", "--", *CRATES).returncode != 0:
            raise SystemExit(f"ERROR: Rust source changed since native runtime build: {target}")
        for crate, rel in (("drlink-egress", "native/drlink-egress/Cargo.lock"),
                           ("drlink-mcp-runtime", "native/drlink-mcp-runtime/Cargo.lock")):
            if record.get("cargo_locks", {}).get(crate) != digest(ROOT / rel):
                raise SystemExit(f"ERROR: Cargo.lock provenance mismatch: {target}/{crate}")
        script_hash = record.get("build_script")
        if script_hash != digest(ROOT / "scripts/build-native-runtime-assets.sh"):
            raise SystemExit(f"ERROR: native build script provenance mismatch: {target}")
        libraries = record.get("libraries", {})
        expected_ext = ".dylib" if target.endswith("apple-darwin") else ".so"
        required_names = {"libdrlink_egress" + expected_ext,
                          "libdrlink_mcp_runtime" + expected_ext}
        if not required_names.issubset(libraries):
            raise SystemExit(f"ERROR: native library inventory incomplete: {target}")
        for name, expected in libraries.items():
            asset = target_dir / name
            if not asset.is_file() or digest(asset) != expected:
                raise SystemExit(f"ERROR: native library checksum mismatch: {asset}")
    print("NATIVE_RUNTIME_ASSET_PROVENANCE=PASS targets=" + ",".join(sorted(targets)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
