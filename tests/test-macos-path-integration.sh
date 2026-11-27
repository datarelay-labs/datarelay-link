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

[[ "$(frp_client_state_path)" == "$TMP/root$TMP/state/client-state.json" ]]
[[ "$(frp_client_path /usr/local/bin/frpc)" == "$TMP/root$TMP/state/bin/frpc" ]]
[[ "$(frp_client_path /usr/local/bin/frpctl)" == "$TMP/root$TMP/prefix/bin/frpctl" ]]
[[ "$(frp_txn_marker_path client)" == "$TMP/root$TMP/state/state/client-update-pending.json" ]]
[[ "$(frp_txn_marker_path server)" == "$TMP/root$TMP/state/state/server-update-pending.json" ]]

# Product-owned runtime selection is durable, and invalid provenance or a
# writable runtime directory never becomes a root execution path.
runtime="$TMP/root$TMP/state/runtime/python"
mkdir -p "$runtime/bin"
chmod 0755 "$TMP/root$TMP/state" "$TMP/root$TMP/state/runtime" "$runtime" "$runtime/bin"
printf '%s\n' e1b27b6f634cf9c01722ebae87be0b08c98a21e5b123edbdf3a0e7bf4b57e0ee >"$runtime/.drlink-runtime-sha256"
printf '#!/bin/sh\nexit 0\n' >"$runtime/bin/python3.11"
chmod 0755 "$runtime/bin/python3.11"
ln -s python3.11 "$runtime/bin/python3"
[[ "$(frp_macos_managed_python)" == "$runtime/bin/python3" ]]
[[ "$(frp_macos_lifecycle_python)" == "$runtime/bin/python3" ]]
old_path="$PATH"
frp_select_compatible_python
[[ "$_FRP_COMPAT_PYTHON_BIN" == "$runtime/bin/python3" ]]
[[ "$(type -P python3)" == "$runtime/bin/python3" ]]
export PATH="$old_path"
hash -r
chmod 0777 "$runtime/bin"
if frp_macos_managed_python >/dev/null; then
  echo 'ERROR: accepted writable managed Python directory' >&2; exit 1
fi
chmod 0755 "$runtime/bin"
chmod 0777 "$runtime/bin/python3.11"
if frp_macos_managed_python >/dev/null; then
  echo 'ERROR: accepted writable managed Python executable' >&2; exit 1
fi
chmod 0755 "$runtime/bin/python3.11"
printf 'tampered\n' >"$runtime/.drlink-runtime-sha256"
if frp_macos_managed_python >/dev/null; then
  echo 'ERROR: accepted unqualified managed Python marker' >&2; exit 1
fi
echo MACOS_MANAGED_RUNTIME_SELECTION=PASS

FRP_TEST_UNAME_S=Linux
[[ "$(frp_platform_map_path /etc/frp/frpc.toml)" == /etc/frp/frpc.toml ]]
echo "MACOS_PATH_INTEGRATION_TEST=PASS"
