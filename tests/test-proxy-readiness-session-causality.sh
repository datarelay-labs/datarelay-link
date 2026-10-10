#!/usr/bin/env bash
# PASS1 F004/F017: previous FRP session and failed proxy events cannot
# establish current-generation live proxy registration.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export FRP_TEST_UNAME_S=Linux
export FRP_CLIENT_TEST_ROOT="$WORK/root"
. "$ROOT/lib/frp-common.sh"
. "$ROOT/lib/frp-client-common.sh"
export FRP_PROXY_WAIT_SLEEP_S=0
export FRP_PROXY_WAIT_MAX_ATTEMPTS=1
export FRP_PROXY_WAIT_MAX_SLEEP_S=0
# Honor the same bounded line limit as the actual journal reader.
frp_client_recent_runtime_logs() { printf '%s\n' "$FIXTURE_LOGS" | tail -n "$1"; }
assert_rejected() {
  local label="$1"; shift
  if wait_for_proxies "$@"; then
    echo "FAIL $label: previously successful proxy reported ready despite later failure" >&2
    exit 1
  fi
  echo "PASS $label"
}
assert_ready() {
  local label="$1"; shift
  if ! wait_for_proxies "$@"; then
    echo "FAIL $label: current generation's verified proxy incorrectly rejected" >&2
    exit 1
  fi
  echo "PASS $label"
}
FIXTURE_LOGS=$'login to server success\n[host-ssh] start proxy success\ncontrol worker is closed'
assert_rejected 'OLD_SESSION_CLOSED' host-ssh
FIXTURE_LOGS=$'login to server success\n[host-ssh] start proxy success\ntry to reconnect\nlogin to server success'
assert_rejected 'RELOGIN_WITHOUT_REANNOUNCEMENT' host-ssh
FIXTURE_LOGS=$'login to server success\n[host-ssh] start proxy success\ntry to reconnect\nlogin to server success\n[host-ssh] start proxy success'
assert_ready 'RELOGIN_WITH_FRESH_PROXY' host-ssh
FIXTURE_LOGS=$'login to server success\n[host-ssh] start proxy success\n[host-ssh] start proxy error: bind failed'
assert_rejected 'LATER_PROXY_START_ERROR' host-ssh
FIXTURE_LOGS=$'login to server success\n[host-ssh] start proxy success\n[host-ssh] stop proxy'
assert_rejected 'LATER_PROXY_STOP' host-ssh
FIXTURE_LOGS=$'login to server success\n[host-ssh] start proxy success\n[host-http] start proxy success\n[host-http] start proxy error'
assert_rejected 'MULTI_PROXY_ONE_FAILED' host-ssh host-http
FIXTURE_LOGS=$'login to server success\n[host-ssh] start proxy success\n[host-http] start proxy error\n[host-http] start proxy success'
assert_ready 'RECOVERED_PROXY_AFTER_ERROR' host-ssh host-http
FIXTURE_LOGS=$'login server failed\n[host-ssh] start proxy success'
assert_rejected 'NO_SUCCESSFUL_LOGIN' host-ssh
# An 85-proxy batch often emits more than 400 journal lines before the last
# registration. The first login event must stay inside the bounded read.
large_names=()
FIXTURE_LOGS="login to server success"
for i in $(seq 1 85); do
  large_names+=("host-bulk-$i")
  for _line in $(seq 1 11); do
    FIXTURE_LOGS+=$'\n'"bulk proxy event $i"
  done
  FIXTURE_LOGS+=$'\n'"[host-bulk-$i] start proxy success"
done
assert_ready 'BULK_85_LOG_WINDOW_PRESERVES_FIRST_LOGIN' "${large_names[@]}"

echo 'PROXY_SESSION_CAUSALITY=PASS'
