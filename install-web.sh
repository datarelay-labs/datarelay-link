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

if [[ -z "$ROOT" ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable --now drlink-web.service
fi

echo "DRLINK_WEB_INSTALL=PASS"
echo "LISTEN_DEFAULT=127.0.0.1:8741"
echo "FIRST_ADMIN_BOOTSTRAP=/usr/local/bin/drlink-web-bootstrap"
