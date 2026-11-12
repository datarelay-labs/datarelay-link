#!/usr/bin/env bash
# Regression: an active MCP service may not bind /healthz until after 10 probes.
# Mock systemd and HTTP; never touch live services or ports.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export FRP_SERVER_SOURCED=1
. "$ROOT/install-server.sh"

frp_server_skip_systemd() { return 1; }
frp_wait_unit_active() { return 0; }
frp_allocator_ready_timeout_sec() { printf '%s' "${TEST_TIMEOUT:-2}"; }
frp_allocator_ready_interval_sec() { printf '%s' "0.02"; }
frp_server_sleep() { sleep 0.02; }
frp_server_journalctl() { echo "MOCK-JOURNAL $*"; }
frp_server_systemctl() {
  case "$1" in
    is-active)
      ACTIVE_CALLS=$((ACTIVE_CALLS + 1))
      if [[ "$TEST_DIE_AT" -gt 0 && "$ACTIVE_CALLS" -ge "$TEST_DIE_AT" ]]; then
        return 3
      fi
      return 0 ;;
    status) echo "MOCK-STATUS $2"; return 0 ;;
  esac
  return 1
}
frp_server_curl() {
  local n
  n="$(cat "$WORK/calls")"
  n=$((n + 1))
  echo "$n" >"$WORK/calls"
  if [[ "$TEST_HTTP_FAIL" == 1 || "$n" -le "$TEST_FAIL_FIRST" ]]; then
    printf '%s' "000"
    return 7
  fi
  printf '%s' "$TEST_CODE"
  return 0
}
reset() {
  echo 0 >"$WORK/calls"
  ACTIVE_CALLS=0
  TEST_TIMEOUT=2
  TEST_HTTP_FAIL=0
  TEST_FAIL_FIRST=0
  TEST_DIE_AT=0
  TEST_CODE=200
}
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

reset
frp_server_health_mcp_bridge >"$WORK/immediate.out" 2>"$WORK/immediate.err" ||
  fail "immediate readiness"
[[ "$(cat "$WORK/calls")" == 1 ]] || fail "immediate probe count"
pass "MCP_IMMEDIATE_READY"

reset
TEST_FAIL_FIRST=12
frp_server_health_mcp_bridge >"$WORK/delayed.out" 2>"$WORK/delayed.err" ||
  fail "delayed readiness beyond old 10 probes"
[[ "$(cat "$WORK/calls")" == 13 ]] || fail "delayed probe count"
grep -q 'Waiting for MCP bridge HTTP listener' "$WORK/delayed.err" ||
  fail "wait reason absent"
pass "MCP_DELAYED_READY_AFTER_TEN_PROBES"

reset
TEST_HTTP_FAIL=1
TEST_TIMEOUT=1
if frp_server_health_mcp_bridge >"$WORK/timeout.out" 2>"$WORK/timeout.err"; then
  fail "never-ready health must fail"
fi
grep -q 'not ready within 1s' "$WORK/timeout.err" || fail "timeout marker"
grep -q 'last HTTP 000' "$WORK/timeout.err" || fail "transport status"
grep -q 'MOCK-STATUS drlink-mcp-bridge' "$WORK/timeout.err" || fail "unit status absent"
grep -q 'MOCK-JOURNAL' "$WORK/timeout.err" || fail "journal absent"
pass "MCP_BOUNDED_TIMEOUT_WITH_DIAGNOSTICS"

reset
TEST_FAIL_FIRST=1000
TEST_DIE_AT=3
TEST_TIMEOUT=9
if frp_server_health_mcp_bridge >"$WORK/dead.out" 2>"$WORK/dead.err"; then
  fail "dead service must fail"
fi
grep -q 'stopped before /healthz' "$WORK/dead.err" || fail "dead-service reason absent"
pass "MCP_DEAD_SERVICE_FAST_FAIL"

reset
TEST_CODE=503
TEST_TIMEOUT=1
if frp_server_health_mcp_bridge >"$WORK/bad.out" 2>"$WORK/bad.err"; then
  fail "HTTP 503 must not pass"
fi
grep -q 'last HTTP 503' "$WORK/bad.err" || fail "HTTP error detail"
pass "MCP_NON_200_DENIED"

echo MCP_BRIDGE_READINESS_TEST=PASS
