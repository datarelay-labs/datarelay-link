#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${DRLINK_WEB_INSTALL_ROOT:-}"
MANIFEST="$BASE_DIR/lib/web-project-files.manifest"

dst() { printf '%s' "${ROOT}$1"; }

if [[ -z "$ROOT" && "$(id -u)" -ne 0 ]]; then
  echo "ERROR: install-web.sh requires root." >&2
  exit 2
fi
if [[ ! -f "$(dst /var/lib/drlink/drlink.db)" ]]; then
  echo "ERROR: Data Relay Link Core must be installed before the optional Web package." >&2
  exit 1
fi
[[ -f "$MANIFEST" ]] || { echo "ERROR: Web package manifest is missing." >&2; exit 1; }

while read -r src dest mode kind extra; do
  [[ -z "${src:-}" || "$src" == \#* ]] && continue
  [[ -z "${extra:-}" ]] || { echo "ERROR: invalid Web manifest row: $src" >&2; exit 1; }
  [[ "$src" != /* && "$dest" != /* && "$src" != *".."* && "$dest" != *".."* ]] || {
    echo "ERROR: unsafe Web manifest path." >&2
    exit 1
  }
  case "$mode" in
    0644|0755) ;;
    *) echo "ERROR: unsupported Web manifest mode: $mode" >&2; exit 1 ;;
  esac
  [[ "$kind" =~ ^(python|systemd|static)$ ]] || {
    echo "ERROR: unsupported Web manifest kind: $kind" >&2
    exit 1
  }
  source_path="$BASE_DIR/$src"
  target_path="$(dst "/$dest")"
  [[ -f "$source_path" ]] || { echo "ERROR: missing Web package file: $src" >&2; exit 1; }
  install -d -m 0755 "$(dirname "$target_path")"
  install -m "$mode" "$source_path" "$target_path"
done < "$MANIFEST"

# Bind the installed optional Web package to its exact source identity. A
# Web-triggered Core update verifies this marker before the service is allowed
# to restart, preventing silent Core/Web build skew.
source_ref="${DRLINK_WEB_SOURCE_REF:-}"
source_head="${DRLINK_WEB_SOURCE_HEAD:-}"
bundle_sha="${DRLINK_WEB_BUNDLE_SHA256:-}"
project_version=""
if [[ -f "$BASE_DIR/VERSION" ]]; then
  project_version="$(awk -F= '$1=="PROJECT_VERSION"{print $2; exit}' "$BASE_DIR/VERSION")"
fi
if [[ -z "$source_head" ]] && command -v git >/dev/null 2>&1 && git -C "$BASE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  source_head="$(git -C "$BASE_DIR" rev-parse HEAD 2>/dev/null || true)"
  source_ref="${source_ref:-$source_head}"
fi
if [[ -z "$source_head" && -f "$BASE_DIR/release-manifest.json" ]]; then
  readarray -t _web_identity < <(python3 - "$BASE_DIR/release-manifest.json" <<'PY'
import json, sys
m=json.load(open(sys.argv[1], encoding="utf-8"))
print(str(m.get("immutable_source_ref") or m.get("git_ref") or ""))
print(str(m.get("source_head") or ""))
print(str(m.get("project_version") or ""))
PY
)
  source_ref="${source_ref:-${_web_identity[0]:-}}"
  source_head="${_web_identity[1]:-}"
  project_version="${project_version:-${_web_identity[2]:-}}"
fi
if [[ ! "$source_head" =~ ^[0-9a-fA-F]{40}$ || -z "$source_ref" ]]; then
  echo "ERROR: Web package exact source identity is unavailable." >&2
  exit 1
fi
build_marker="$(dst /usr/local/share/drlink-web/build.json)"
python3 - "$build_marker" "$project_version" "$source_ref" "$source_head" "$bundle_sha" <<'PY'
import json, os, sys
path, version, ref, head, digest = sys.argv[1:]
payload={
    "schema_version": 1,
    "project_version": version,
    "source_ref": ref,
    "source_head": head.lower(),
    "bundle_sha256": digest,
}
tmp=path+".tmp-%d" % os.getpid()
with open(tmp,"w",encoding="utf-8") as f:
    json.dump(payload,f,sort_keys=True,separators=(",",":"))
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
os.chmod(tmp,0o644)
os.replace(tmp,path)
PY

if [[ "${DRLINK_WEB_INSTALL_SKIP_SYSTEMD:-0}" != "1" && -z "$ROOT" ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable --now drlink-web.service
fi

echo "DRLINK_WEB_INSTALL=PASS"
echo "LISTEN_DEFAULT=127.0.0.1:8741"
echo "FIRST_ADMIN_BOOTSTRAP=/usr/local/bin/drlink-web-bootstrap"
