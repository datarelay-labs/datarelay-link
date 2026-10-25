#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FRP_CLIENT_SOURCED=1
. "$ROOT/install-client.sh"
frp_client_systemctl() {
  case "$1" in
    show) printf '%s\n' "${LOAD_STATE:-not-found}" ;;
    is-active) printf '%s\n' "${ACTIVE_STATE:-inactive}"; return 3 ;;
    disable|stop|enable|restart) return 5 ;;
    *) return 1 ;;
  esac
}
frp_client_systemctl_query() { frp_client_systemctl "$@"; }
frp_client_restore_one_linux_unit drlink-client absent disabled inactive
if LOAD_STATE=loaded frp_client_restore_one_linux_unit drlink-client present enabled active; then
  echo 'FAIL present unit activation failure was ignored' >&2
  exit 1
fi
if ACTIVE_STATE=active frp_client_restore_one_linux_unit drlink-client absent disabled inactive; then
  echo 'FAIL active missing unit was reported restored' >&2
  exit 1
fi
echo 'ABSENT_UNIT_ROLLBACK=PASS'
