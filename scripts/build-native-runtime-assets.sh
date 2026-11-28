#!/usr/bin/env bash
# Build the bounded Rust runtime libraries for this host with the pinned toolchain.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for crate in native/drlink-egress native/drlink-mcp-runtime; do
  if ! git diff --quiet HEAD -- "$crate/Cargo.toml" "$crate/Cargo.lock" "$crate/src" \
    || [[ -n "$(git ls-files --others --exclude-standard -- "$crate/Cargo.toml" "$crate/Cargo.lock" "$crate/src")" ]]; then
    echo "ERROR: Rust source tree must be committed before packaging ($crate)" >&2
    exit 1
  fi
done

rust_info="$(rustc +1.75.0 -vV)"
host_target="$(sed -n 's/^host: //p' <<<"$rust_info")"
target="${DRLINK_NATIVE_TARGET:-$host_target}"
[[ -n "$host_target" && -n "$target" ]] || {
  echo "ERROR: pinned rustc did not report a host target" >&2
  exit 1
}
case "$target" in
  x86_64-unknown-linux-gnu|aarch64-unknown-linux-gnu|aarch64-apple-darwin|x86_64-apple-darwin) ;;
  *) echo "ERROR: unsupported native runtime packaging target: $target" >&2; exit 1 ;;
esac
linker="${DRLINK_NATIVE_LINKER:-cc}"
linker_version="$("$linker" --version | head -n 1)"

cargo +1.75.0 build --release --locked --target "$target" \
  --manifest-path native/drlink-egress/Cargo.toml
cargo +1.75.0 build --release --locked --target "$target" \
  --manifest-path native/drlink-mcp-runtime/Cargo.toml

case "$target" in
  *apple-darwin) extension=dylib ;;
  *) extension=so ;;
esac
out="lib/native/$target"
mkdir -p "$out"
install -m 0644 "native/drlink-egress/target/$target/release/libdrlink_egress.$extension" \
  "$out/libdrlink_egress.$extension"
install -m 0644 "native/drlink-mcp-runtime/target/$target/release/libdrlink_mcp_runtime.$extension" \
  "$out/libdrlink_mcp_runtime.$extension"
if [[ "$target" == *apple-darwin ]]; then
  "${DRLINK_NATIVE_STRIP:-strip}" -S \
    "$out/libdrlink_egress.$extension" "$out/libdrlink_mcp_runtime.$extension"
else
  "${DRLINK_NATIVE_STRIP:-strip}" --strip-unneeded \
    "$out/libdrlink_egress.$extension" "$out/libdrlink_mcp_runtime.$extension"
fi

python3 - "$out/runtime-build.json" "$target" "$rust_info" \
  "$linker" "$linker_version" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

output, target, rust_info = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
linker, linker_version = sys.argv[4], sys.argv[5]
root = Path.cwd()
source_head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

def digest(relative):
    path = root / relative
    return hashlib.sha256(path.read_bytes()).hexdigest()

payload = {
    "schema": 1,
    "source_head": source_head,
    "target": target,
    "rustc": next((line.partition(": ")[2] for line in rust_info.splitlines()
                   if line.startswith("release: ")), "unknown"),
    "linker": linker,
    "linker_version": linker_version,
    "build_script": digest("scripts/build-native-runtime-assets.sh"),
    "cargo_locks": {
        "drlink-egress": digest("native/drlink-egress/Cargo.lock"),
        "drlink-mcp-runtime": digest("native/drlink-mcp-runtime/Cargo.lock"),
    },
    "libraries": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.parent.glob("libdrlink_*"))
    },
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
echo "NATIVE_RUNTIME_ASSETS=PASS target=$target source_head=$(git rev-parse --short HEAD)"
