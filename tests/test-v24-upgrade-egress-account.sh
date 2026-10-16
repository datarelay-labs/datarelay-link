#!/usr/bin/env bash
# No actual users/groups are created by this isolated upgrade-preflight test.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
export FRP_SERVER_SOURCED=1
. "$ROOT/install-server.sh"
frp_server_test_mode() { return 1; }
frp_server_ensure_sandbox_dirs() { touch "$TEMP/prepared"; }
getent() {
  [[ "${GETENT_MISSING:-}" != "$2" ]] && [[ "$2" == 'drlink-egress' ]]
}
frp_server_upgrade_ensure_egress_account
[[ -f "$TEMP/prepared" ]] || { echo 'FAIL upgrade did not prepare account' >&2; exit 1; }
export GETENT_MISSING=drlink-egress
if frp_server_upgrade_ensure_egress_account >/dev/null 2>"$TEMP/failed.err"; then
  echo 'FAIL upgrade accepted missing account' >&2
  exit 1
fi
grep -q 'system user/group missing' "$TEMP/failed.err"
unset GETENT_MISSING
frp_server_ensure_sandbox_dirs() { return 5; }
if frp_server_upgrade_ensure_egress_account >/dev/null 2>"$TEMP/prepare.err"; then
  echo 'FAIL upgrade swallowed runtime preparation failure' >&2
  exit 1
fi
frp_server_test_mode() { return 0; }
frp_server_upgrade_ensure_egress_account
echo 'EGRESS_ACCOUNT_UPGRADE_PREFLIGHT=PASS'
