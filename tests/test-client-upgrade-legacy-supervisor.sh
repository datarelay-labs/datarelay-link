#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export FRP_CLIENT_SOURCED=1 FRP_CLIENT_TEST_ROOT="$WORK/tree"
export FRP_SYSTEMCTL_BIN="$WORK/systemctl" CASE_LOG="$WORK/actions"
. "$ROOT/install-client.sh"
mkdir -p "$FRP_CLIENT_TEST_ROOT/etc/systemd/system"
cat >"$FRP_CLIENT_TEST_ROOT/etc/systemd/system/frpc.service" <<'UNIT'
[Unit]
Description=FRP Client
[Service]
ExecStart=/usr/local/bin/frpc -c /etc/frp/frpc.toml
UNIT
cat >"$FRP_SYSTEMCTL_BIN" <<'CTL'
#!/bin/sh
printf '%s\n' "$*" >>"$CASE_LOG"
case "$1" in
  is-enabled) echo enabled ;;
  is-active) echo active ;;
esac
exit 0
CTL
chmod +x "$FRP_SYSTEMCTL_BIN"
backup="$(frp_client_upgrade_backup_tools)"
grep -qx 'frpc present enabled active' "$backup/linux-systemd.state"
cmp "$backup/legacy-frpc.service" "$FRP_CLIENT_TEST_ROOT/etc/systemd/system/frpc.service"
rm "$FRP_CLIENT_TEST_ROOT/etc/systemd/system/frpc.service"
frp_client_upgrade_restore_tools "$backup"
frp_client_restore_linux_unit_state "$backup"
cmp "$backup/legacy-frpc.service" "$FRP_CLIENT_TEST_ROOT/etc/systemd/system/frpc.service"
grep -qx 'enable frpc' "$CASE_LOG"
grep -qx 'restart frpc' "$CASE_LOG"
# Upgrade retires the owned prior supervisor before starting either worker or
# the canonical relay. No actual host services are changed by these hooks.
frp_retire_legacy_client_unit() { echo retire-legacy >>"$WORK/order"; }
frp_client_activate_lifecycle_unit() { echo lifecycle >>"$WORK/order"; }
frp_client_activate_ai_agent_unit() { echo ai >>"$WORK/order"; }
frp_client_activate_linux_runtime_units 1
[[ "$(head -1 "$WORK/order")" == retire-legacy ]]
echo 'LEGACY_SUPERVISOR_UPGRADE_ROLLBACK=PASS'
