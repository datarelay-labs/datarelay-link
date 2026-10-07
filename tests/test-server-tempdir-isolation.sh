#!/usr/bin/env bash
# Installer temporary work must not corrupt the caller's standard TMPDIR.
# Sources functions only; never installs or changes a live service.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT
export FRP_SERVER_SOURCED=1
. "$ROOT/install-server.sh"
mkdir -p "$WORK/caller temp"
export TMPDIR="$WORK/caller temp"
printf 'caller owned\n' > "$TMPDIR/sentinel"
parent_tmp="$TMPDIR"
parent_trap="$(trap -p EXIT)"
for cycle in 1 2; do
  frp_server_begin_tmp
  [[ "$TMPDIR" == "$parent_tmp" ]] || { echo 'FAIL caller TMPDIR overwritten'; exit 1; }
  [[ -d "$FRP_SERVER_TMPDIR" && "$FRP_SERVER_TMPDIR" != "$TMPDIR" ]]
  [[ "$(stat -c '%a' "$FRP_SERVER_TMPDIR")" == 700 ]]
  private_tmp="$FRP_SERVER_TMPDIR"
  frp_server_end_tmp
  [[ ! -e "$private_tmp" && -z "${FRP_SERVER_TMPDIR:-}" ]]
  [[ "$TMPDIR" == "$parent_tmp" && -f "$TMPDIR/sentinel" ]]
  [[ "$(trap -p EXIT)" == "$parent_trap" ]]
  probe="$(mktemp)"
  [[ "$probe" == "$parent_tmp/"* ]]
  rm -f -- "$probe"
  echo "PASS exported TMPDIR preserved, secure cleanup, and repeated cycle $cycle"
done
(
  # This child must not run the parent fixture cleanup on exit.
  trap - EXIT
  unset TMPDIR
  frp_server_begin_tmp
  [[ ! ${TMPDIR+x} ]]
  private_tmp="$FRP_SERVER_TMPDIR"
  frp_server_end_tmp
  [[ ! ${TMPDIR+x} && ! -e "$private_tmp" ]]
)
echo 'PASS unset TMPDIR remains unset'
# EXIT without explicit end must remove only the installer-owned directory.
export PROBE_ROOT="$WORK" INSTALLER_SOURCE="$ROOT/install-server.sh"
bash -c '
  set -euo pipefail
  export FRP_SERVER_SOURCED=1
  . "$INSTALLER_SOURCE"
  frp_server_begin_tmp
  printf "%s\n" "$FRP_SERVER_TMPDIR" > "$PROBE_ROOT/exit-path"
'
[[ ! -e "$(<"$WORK/exit-path")" && -f "$TMPDIR/sentinel" ]]
echo 'PASS EXIT cleans installer directory and preserves caller directory'
echo 'SERVER_TMPDIR_ISOLATION=PASS'
