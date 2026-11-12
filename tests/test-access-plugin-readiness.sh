#!/usr/bin/env bash
# Access /healthz readiness integration seam: real installer functions,
# mocked systemd/curl only. No installed server or runtime is changed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export FRP_SERVER_SOURCED=1
. "$ROOT/install-server.sh"
export FRP_SERVER_TEST_ROOT="$WORK/host"
mkdir -p "$FRP_SERVER_TEST_ROOT/etc/drlink"

frp_server_skip_systemd() { return 1; }
frp_allocator_ready_timeout_sec() { printf '%s' "${TEST_TIMEOUT:-2}"; }
frp_allocator_ready_interval_sec() { printf '%s' 0.02; }
frp_server_sleep() { sleep 0.02; }
frp_server_systemctl() {
  case "$1" in
    is-active)
      [[ "${3:-}" == drlink-access ]] || return 3
      ACTIVE_CALLS=$((ACTIVE_CALLS+1))
      if (( TEST_DIE_AT > 0 && ACTIVE_CALLS >= TEST_DIE_AT )); then return 3; fi
      return 0 ;;
    status) echo "MOCK-STATUS ${2:-}" ;;
    *) return 1 ;;
  esac
}
frp_server_journalctl() { echo "MOCK-JOURNAL"; }
frp_server_curl() {
  local url="${*: -1}"
  printf '%s' "$url" >"$WORK/last-url"
  local n
  n="$(cat "$WORK/calls")"
  n=$((n+1))
  printf '%s' "$n" >"$WORK/calls"
  if (( n <= TEST_FAIL_FIRST )) || [[ "$TEST_HTTP_FAIL" == 1 ]]; then
    printf '000'
    return 7
  fi
  printf '%s' "$TEST_CODE"
}
reset() {
  printf 0 >"$WORK/calls"
  ACTIVE_CALLS=0
  TEST_TIMEOUT=2
  TEST_HTTP_FAIL=0
  TEST_FAIL_FIRST=0
  TEST_DIE_AT=0
  TEST_CODE=200
  rm -f "$FRP_SERVER_TEST_ROOT/etc/drlink/config.json"
}
fail() { echo "FAIL $1" >&2; exit 1; }
pass() { echo "PASS $1"; }

reset
frp_server_health_access >"$WORK/out" 2>"$WORK/err" || fail "immediate"
[[ "$(cat "$WORK/calls")" == 1 ]] || fail "double request on immediate"
[[ "$(cat "$WORK/last-url")" == "http://127.0.0.1:6101/healthz" ]] || fail "wrong default port"
pass "ACCESS_ONE_PROBE_IMMEDIATE"

reset
TEST_FAIL_FIRST=12
frp_server_health_access >"$WORK/out" 2>"$WORK/err" || fail "delayed listen"
[[ "$(cat "$WORK/calls")" == 13 ]] || fail "fixed old 10-probe ceiling"
grep -q 'Waiting for access plugin HTTP listener' "$WORK/err" || fail "missing wait"
pass "ACCESS_DELAYED_LISTENER_GT_10_PROBES"

reset
printf '%s\n' '{"access_plugin_addr":"127.0.0.1:6191"}' >"$FRP_SERVER_TEST_ROOT/etc/drlink/config.json"
frp_server_health_access >"$WORK/out" 2>"$WORK/err" || fail "configured port"
[[ "$(cat "$WORK/last-url")" == "http://127.0.0.1:6191/healthz" ]] || fail "configured port ignored"
pass "ACCESS_CONFIGURED_LISTENER"

reset
TEST_HTTP_FAIL=1
TEST_TIMEOUT=1
if frp_server_health_access >"$WORK/out" 2>"$WORK/err"; then fail "connection refusal should fail"; fi
grep -q 'not ready within 1s' "$WORK/err" || fail "timeout signal"
grep -q 'last HTTP 000' "$WORK/err" || fail "curl error malformed"
! grep -q '000000' "$WORK/err" || fail "double-000 regression"
grep -q 'MOCK-STATUS drlink-access' "$WORK/err" || fail "unit status missing"
grep -q 'MOCK-JOURNAL' "$WORK/err" || fail "journal missing"
pass "ACCESS_TIMEOUT_DIAGNOSTICS"

reset
TEST_DIE_AT=3
TEST_FAIL_FIRST=1000
TEST_TIMEOUT=9
if frp_server_health_access >"$WORK/out" 2>"$WORK/err"; then fail "dead unit passed"; fi
grep -q 'access plugin stopped before /healthz' "$WORK/err" || fail "dead unit marker"
pass "ACCESS_DEAD_SERVICE_FAIL_CLOSED"

reset
TEST_CODE=503
TEST_TIMEOUT=1
if frp_server_health_access >"$WORK/out" 2>"$WORK/err"; then fail "HTTP 503 passed"; fi
grep -q 'last HTTP 503' "$WORK/err" || fail "HTTP status missing"
pass "ACCESS_HTTP_503_FAIL_CLOSED"

reset
export FRP_INSTALL_HOOK_HEALTH_FAIL=1
if frp_server_health_access >"$WORK/out" 2>"$WORK/err"; then fail "simulated hook passed"; fi
[[ "$(cat "$WORK/calls")" == 0 ]] || fail "hook touched HTTP"
unset FRP_INSTALL_HOOK_HEALTH_FAIL
pass "ACCESS_HEALTH_INJECTION_PRESERVED"

echo ACCESS_PLUGIN_READINESS_TEST=PASS
