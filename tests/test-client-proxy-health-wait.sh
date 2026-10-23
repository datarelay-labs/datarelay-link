#!/usr/bin/env bash
# Regression: client proxy readiness must poll drlink-client (not legacy frpc)
# and tolerate a short bounded startup delay before declaring HEALTH_CHECK_FAILED.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL $*" >&2; exit 1; }
pass() { echo "PASS $*"; }

# Source contract: never poll the retired frpc unit name for readiness.
if grep -nE 'journalctl[[:space:]]+-u[[:space:]]+frpc' \
  "$ROOT/lib/frp-client-common.sh" "$ROOT/install-client.sh"; then
  fail "client health still polls journalctl -u frpc"
fi
grep -q 'frp_client_runtime_unit' "$ROOT/lib/frp-client-common.sh" \
  || fail "missing frp_client_runtime_unit helper"
grep -q 'drlink-client' "$ROOT/lib/frp-client-common.sh" \
  || fail "wait path must name drlink-client"
pass "SOURCE_USES_DRLINK_CLIENT_UNIT"

BIN="$WORK/bin"
mkdir -p "$BIN" "$WORK/state"
cat >"$BIN/journalctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
unit=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u) unit="$2"; shift 2 ;;
    -n) shift 2 ;;
    --no-pager) shift ;;
    *) shift ;;
  esac
done
state_dir="${FRP_FAKE_JOURNAL_STATE:?}"
count_file="$state_dir/count"
count=0
[[ -f "$count_file" ]] && count="$(cat "$count_file")"
count=$((count + 1))
printf '%s\n' "$count" >"$count_file"
printf 'UNIT=%s\n' "$unit" >>"$state_dir/units"
if [[ "$unit" != "drlink-client" ]]; then
  # Wrong unit yields empty logs forever (the pre-fix race condition).
  exit 0
fi
# Become healthy only after several polls to exercise bounded retry.
if (( count < 4 )); then
  exit 0
fi
cat <<'LOG'
login to server success
[host-ssh] start proxy success
LOG
EOF
chmod 0755 "$BIN/journalctl"

# shellcheck source=../lib/frp-common.sh
. "$ROOT/lib/frp-common.sh"
# shellcheck source=../lib/frp-client-common.sh
. "$ROOT/lib/frp-client-common.sh"

export PATH="$BIN:$PATH"
export FRP_FAKE_JOURNAL_STATE="$WORK/state"
export FRP_PROXY_WAIT_SLEEP_S=0
export FRP_PROXY_WAIT_MAX_ATTEMPTS=12
export FRP_PROXY_WAIT_MAX_SLEEP_S=0

if ! wait_for_proxies host-ssh; then
  fail "wait_for_proxies failed despite delayed healthy drlink-client logs"
fi
[[ "$(cat "$WORK/state/count")" -ge 4 ]] || fail "did not retry across startup delay"
if grep -q 'UNIT=frpc' "$WORK/state/units"; then
  fail "wait_for_proxies queried legacy frpc unit"
fi
grep -q 'UNIT=drlink-client' "$WORK/state/units" || fail "did not query drlink-client"
pass "DELAYED_STARTUP_BOUNDED_RETRY"

# Genuine failure still fails closed when logs never become healthy.
rm -f "$WORK/state/count" "$WORK/state/units"
cat >"$BIN/journalctl" <<'EOF'
#!/usr/bin/env bash
unit=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u) unit="$2"; shift 2 ;;
    *) shift ;;
  esac
done
printf 'UNIT=%s\n' "$unit" >>"${FRP_FAKE_JOURNAL_STATE}/units"
exit 0
EOF
chmod 0755 "$BIN/journalctl"
export FRP_PROXY_WAIT_MAX_ATTEMPTS=3
if wait_for_proxies host-ssh; then
  fail "wait_for_proxies must fail closed when proxies never become healthy"
fi
grep -q 'UNIT=drlink-client' "$WORK/state/units" || fail "fail-closed path must still query drlink-client"
pass "GENUINE_FAILURE_FAIL_CLOSED"

# Linux journal cursor causality: evidence before --after-cursor must not PASS.
rm -f "$WORK/state/count" "$WORK/state/units"
cat >"$BIN/journalctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
unit=""
after_cursor=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u) unit="$2"; shift 2 ;;
    --after-cursor) after_cursor="$2"; shift 2 ;;
    --show-cursor)
      echo "-- cursor: linux-cursor-gen2"
      exit 0
      ;;
    -n|--no-pager) shift ;;
    *) shift ;;
  esac
done
printf 'UNIT=%s AFTER=%s\n' "$unit" "$after_cursor" >>"${FRP_FAKE_JOURNAL_STATE}/units"
if [[ "$unit" != "drlink-client" ]]; then
  exit 0
fi
if [[ -n "$after_cursor" ]]; then
  # Only post-cursor generation is visible.
  if [[ "$after_cursor" == "linux-cursor-gen1" ]]; then
    cat <<'LOG'
login to server success
[host-ssh] start proxy success
LOG
  fi
  exit 0
fi
# Without a cursor, stale pre-generation lines would appear — wait path must pass one.
cat <<'LOG'
[stale] start proxy success
LOG
EOF
chmod 0755 "$BIN/journalctl"

unset FRP_PROXY_WAIT_CURSOR || true
CURSOR_LINUX="$(frp_client_journal_cursor)"
[[ "$CURSOR_LINUX" == "linux-cursor-gen2" ]] || fail "Linux cursor capture failed (got: $CURSOR_LINUX)"
# Wrong/old cursor yields empty after-cursor logs → fail closed.
export FRP_PROXY_WAIT_CURSOR="linux-cursor-stale"
export FRP_PROXY_WAIT_MAX_ATTEMPTS=3
if wait_for_proxies host-ssh; then
  fail "Linux wait must fail closed for unknown after-cursor generation"
fi
# Fresh matching cursor yields proxy success → PASS.
export FRP_PROXY_WAIT_CURSOR="linux-cursor-gen1"
export FRP_PROXY_WAIT_MAX_ATTEMPTS=4
if ! wait_for_proxies host-ssh; then
  fail "Linux wait must PASS for after-cursor proxy-success evidence"
fi
grep -q 'AFTER=linux-cursor-gen1' "$WORK/state/units" || fail "Linux wait did not honor after-cursor"
pass "LINUX_PROXY_WAIT_REGRESSION"
pass "LINUX_STALE_CURSOR_CAUSALITY"

# A management-only install has no client-unit journal before its first
# Remote Service. Capture a real system-journal boundary, then require fresh
# client-unit evidence after that boundary; unrelated/stale logs cannot pass.
rm -f "$WORK/state/units" "$WORK/state/fresh-client"
cat >"$BIN/journalctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
unit=""
after_cursor=""
show_cursor=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u) unit="$2"; shift 2 ;;
    --after-cursor) after_cursor="$2"; shift 2 ;;
    --show-cursor) show_cursor=1; shift ;;
    -n) shift 2 ;;
    *) shift ;;
  esac
done
state_dir="${FRP_FAKE_JOURNAL_STATE:?}"
printf 'UNIT=%s AFTER=%s CURSOR=%s\n' "$unit" "$after_cursor" "$show_cursor" >>"$state_dir/units"
if (( show_cursor )); then
  # No drlink-client invocation has ever written a journal entry.
  if [[ -z "$unit" && ! -f "$state_dir/journal-unavailable" ]]; then
    printf '%s\n' '-- cursor: system-before-first-client'
  fi
  exit 0
fi
if [[ "$unit" != "drlink-client" || "$after_cursor" != "system-before-first-client" ]]; then
  # An unrelated unit (or a read without the boundary) has misleading success.
  printf '%s\n' 'login to server success' '[host-ssh] start proxy success'
  exit 0
fi
if [[ -f "$state_dir/fresh-client" ]]; then
  printf '%s\n' 'login to server success' '[host-ssh] start proxy success'
fi
EOF
chmod 0755 "$BIN/journalctl"

CURSOR_FIRST_CLIENT="$(frp_client_journal_cursor)"
[[ "$CURSOR_FIRST_CLIENT" == "system-before-first-client" ]] \
  || fail "first client activation requires an existing system journal cursor"
export FRP_PROXY_WAIT_CURSOR="$CURSOR_FIRST_CLIENT"
if wait_for_proxies host-ssh; then
  fail "unrelated/stale journal success must not qualify the first client activation"
fi
touch "$WORK/state/fresh-client"
if ! wait_for_proxies host-ssh; then
  fail "fresh client login and proxy success after the system cursor must qualify"
fi
grep -q 'UNIT=drlink-client AFTER=system-before-first-client CURSOR=0' "$WORK/state/units" \
  || fail "readiness must remain client-unit and post-cursor scoped"
pass "FIRST_CLIENT_ACTIVATION_WITH_EMPTY_UNIT_JOURNAL"
pass "FIRST_CLIENT_FRESH_SCOPED_EVIDENCE_REQUIRED"

touch "$WORK/state/journal-unavailable"
[[ -z "$(frp_client_journal_cursor)" ]] \
  || fail "unavailable journal must not produce fabricated generation evidence"
pass "UNAVAILABLE_JOURNAL_HAS_NO_SYNTHETIC_CURSOR"

echo "CLIENT_PROXY_HEALTH_WAIT_TEST=PASS"
