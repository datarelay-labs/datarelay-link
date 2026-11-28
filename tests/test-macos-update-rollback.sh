#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export FRP_TEST_UNAME_S=Darwin
export FRP_MACOS_STATE_ROOT="$TMP/state"
export FRP_MACOS_PREFIX="$TMP/prefix"
export FRP_CLIENT_TEST_ROOT="$TMP/root"
. "$ROOT/lib/frp-client-common.sh"

# SIP forbids writing /usr/bin on macOS; secure_path copy is Linux-only.
if frp_client_upgrade_destinations | grep '^usr/bin/drlink:' >/dev/null; then
  echo "FAIL: Darwin upgrade destinations must not include usr/bin/drlink" >&2
  exit 1
fi
(
  export FRP_TEST_UNAME_S=Linux
  if ! frp_client_upgrade_destinations | grep '^usr/bin/drlink:' >/dev/null; then
    echo "FAIL: Linux upgrade destinations must include usr/bin/drlink" >&2
    exit 1
  fi
)

while IFS=: read -r rel mode src; do
  live="$(frp_client_path "/$rel")"
  mkdir -p "$(dirname "$live")"
  printf 'original:%s\n' "$rel" >"$live"
  chmod "$mode" "$live"
done < <(frp_client_upgrade_destinations)
# The native package's nested Linux/macOS assets must be in the same upgrade
# snapshot inventory as Python runtime files.
for asset in \
  native/aarch64-unknown-linux-gnu/libdrlink_egress.so \
  native/aarch64-unknown-linux-gnu/libdrlink_mcp_runtime.so \
  native/aarch64-unknown-linux-gnu/runtime-build.json \
  native/aarch64-apple-darwin/libdrlink_egress.dylib \
  native/aarch64-apple-darwin/libdrlink_mcp_runtime.dylib \
  native/aarch64-apple-darwin/runtime-build.json \
  native/x86_64-unknown-linux-gnu/libdrlink_egress.so \
  native/x86_64-unknown-linux-gnu/libdrlink_mcp_runtime.so \
  native/x86_64-unknown-linux-gnu/runtime-build.json; do
  grep -qx "usr/local/lib/drlink/$asset:0644:lib/$asset" < <(frp_client_upgrade_destinations) || {
    echo "FAIL: native asset missing from Agent upgrade snapshot inventory: $asset" >&2
    exit 1
  }
done
version="$(frp_client_version_file)"
mkdir -p "$(dirname "$version")"
printf 'PROJECT_VERSION=2.2.1\nFRP_VERSION=0.71.0\n' >"$version"

backup="$(frp_client_upgrade_backup_tools "$ROOT")"
while IFS=: read -r rel mode src; do
  printf 'mutated\n' >"$(frp_client_path "/$rel")"
done < <(frp_client_upgrade_destinations)
printf 'mutated\n' >"$version"

frp_client_upgrade_restore_tools "$backup"
frp_client_upgrade_verify_restored "$backup"
grep -q '^original:' "$(frp_client_path /usr/local/bin/drlink)"
grep -q '^original:' "$(frp_client_path /usr/local/lib/drlink/frpctl)"
grep -q '^PROJECT_VERSION=2.2.1' "$version"
for asset in \
  native/aarch64-unknown-linux-gnu/libdrlink_egress.so \
  native/aarch64-unknown-linux-gnu/libdrlink_mcp_runtime.so \
  native/aarch64-unknown-linux-gnu/runtime-build.json \
  native/aarch64-apple-darwin/libdrlink_egress.dylib \
  native/aarch64-apple-darwin/libdrlink_mcp_runtime.dylib \
  native/aarch64-apple-darwin/runtime-build.json \
  native/x86_64-unknown-linux-gnu/libdrlink_egress.so \
  native/x86_64-unknown-linux-gnu/libdrlink_mcp_runtime.so \
  native/x86_64-unknown-linux-gnu/runtime-build.json; do
  grep -qx "original:usr/local/lib/drlink/$asset" \
    "$(frp_client_path "/usr/local/lib/drlink/$asset")" || {
      echo "FAIL: Agent rollback did not restore native asset: $asset" >&2
      exit 1
    }
done

# Recover an interrupted pre-native update from the old flat snapshot layout.
# New native files absent from the old manifest are removed to restore Python
# fallback, while an ambiguous duplicate basename is rejected before mutation.
legacy="$TMP/legacy-snapshot"
mkdir -m 700 "$legacy"
printf 'present usr/local/bin/drlink\npresent version\n' >"$legacy/manifest"
printf 'legacy-cli\n' >"$legacy/drlink"
printf 'PROJECT_VERSION=2.2.0\nFRP_VERSION=0.71.0\n' >"$legacy/version"
live_cli="$(frp_client_path /usr/local/bin/drlink)"
printf 'live-cli\n' >"$live_cli"
printf 'new-native\n' \
  >"$(frp_client_path /usr/local/lib/drlink/native/aarch64-apple-darwin/libdrlink_egress.dylib)"
frp_client_upgrade_restore_tools "$legacy"
frp_client_upgrade_verify_restored "$legacy"
grep -q '^legacy-cli$' "$live_cli"
[[ ! -e "$(frp_client_path /usr/local/lib/drlink/native/aarch64-apple-darwin/libdrlink_egress.dylib)" ]]
grep -q '^PROJECT_VERSION=2.2.0' "$(frp_client_version_file)"
echo "PASS LEGACY_SNAPSHOT_COMPATIBLE_RECOVERY"

ambiguous="$TMP/legacy-ambiguous"
mkdir -m 700 "$ambiguous"
printf 'present usr/local/lib/drlink/native/x86_64-unknown-linux-gnu/libdrlink_egress.so\npresent usr/local/lib/drlink/native/aarch64-unknown-linux-gnu/libdrlink_egress.so\n' \
  >"$ambiguous/manifest"
printf 'ambiguous-native\n' >"$ambiguous/libdrlink_egress.so"
printf 'preserve-live-cli\n' >"$live_cli"
if frp_client_upgrade_restore_tools "$ambiguous"; then
  echo "FAIL: ambiguous legacy basenames were accepted" >&2
  exit 1
fi
grep -q '^preserve-live-cli$' "$live_cli"
echo "PASS LEGACY_AMBIGUITY_REJECTED_BEFORE_MUTATION"
echo "MACOS_UPDATE_ROLLBACK_TEST=PASS"
