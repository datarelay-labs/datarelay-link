#!/usr/bin/env bash
# U-013: legacy Agent menu (tools/frp-client + lib/frp-client-common.sh) uses the
# same navigation semantics as the drlink menus:
#   ?  = context help, stay on the current menu/step
#   0  = previous menu (submenus) / cancel the current entry (steps)
#   top-level menu: 0 is explained ("top menu, enter N to exit"), never a silent exit
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'frp_reset_test_input; rm -rf "$WORKDIR"' EXIT

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

export FRP_CLIENT_SOURCED=1
export FRP_SKIP_CONNECTIVITY_CHECK=1
# shellcheck source=../install-client.sh
. "$ROOT/install-client.sh"

run_add_menu() {
  local input="$1"
  frp_reset_test_input
  export FRP_CLIENT_TEST_INPUT="$input"
  PAYLOAD=""
  frp_ux_prompt_new_service PAYLOAD >"$WORKDIR/add.out" 2>"$WORKDIR/add.err" || true
  unset FRP_CLIENT_TEST_INPUT
  frp_reset_test_input
}

count_line() { grep -c -x -- "$2" "$1" || true; }

# --- the Add-service menu advertises ? and 0 ---------------------------------
frp_ux_add_service_menu >"$WORKDIR/menu.out"
grep -q '? Help' "$WORKDIR/menu.out" || fail "add menu must advertise ? Help"
grep -q '0 Back' "$WORKDIR/menu.out" || fail "add menu must advertise 0 Back"
pass "add-service menu advertises ? and 0"

# --- 0 returns to the previous menu without an error --------------------------
run_add_menu $'0\n'
[[ -z "$PAYLOAD" ]] || fail "0 must not produce a service payload"
if grep -q 'ERROR' "$WORKDIR/add.err" "$WORKDIR/add.out"; then fail "0 must not be an error in a submenu"; fi
pass "0 goes back from the add-service submenu"

# --- ? shows menu help and stays (menu is shown again) -------------------------
run_add_menu $'?\n0\n'
grep -q 'Menu help' "$WORKDIR/add.out" "$WORKDIR/add.err" || fail "? must show menu help"
[[ "$(count_line "$WORKDIR/add.out" '1) SSH')" == 2 ]] || fail "? must keep the user in the menu (menu shown twice)"
if grep -q 'ERROR' "$WORKDIR/add.err" "$WORKDIR/add.out"; then fail "? must not be an error"; fi
pass "? shows context help and stays in the submenu"

# --- invalid input: guidance names the keys that exist here --------------------
run_add_menu $'zzz\n0\n'
grep -q 'ERROR: select 1-5' "$WORKDIR/add.err" "$WORKDIR/add.out" || fail "invalid input keeps the select 1-N prefix"
grep -q '0 to go back' "$WORKDIR/add.err" "$WORKDIR/add.out" || fail "submenu error must name 0 as go back"
if grep -q 'Choose Back/Cancel' "$WORKDIR/add.err" "$WORKDIR/add.out"; then fail "must not mention a missing Cancel item"; fi
pass "submenu error guidance names 0"

# --- step prompts: ? helps and stays; the default still works afterwards ------
run_add_menu $'1\n?\n\n\n\n\n'
grep -q 'stays on this step' "$WORKDIR/add.err" "$WORKDIR/add.out" || fail "? on a step must say it stays on the step"
python3 - "$PAYLOAD" <<'PY' || fail "? on a step must keep the step and still accept the default"
import json, sys
p = json.loads(sys.argv[1])
assert p.get("id") == "ssh" or p.get("service_id") == "ssh" or "ssh" in json.dumps(p), p
PY
pass "? on a step shows help and stays on the step"

# --- SSH step prompts: 0 cancels without creating a stale service --------------
# Check all three SSH fields under set -e, with an explicit Back afterwards.
# A bare failing step used to exit the script before the menu could resume.
for step in id host port; do
  case "$step" in
    id)   input=$'1\n0\n0\n' ;;
    host) input=$'1\n\n0\n0\n' ;;
    port) input=$'1\n\n\n0\n0\n' ;;
  esac
  run_add_menu "$input"
  [[ -z "$PAYLOAD" ]] || fail "0 on SSH $step must not create a service"
  grep -q 'Cancelled' "$WORKDIR/add.err" "$WORKDIR/add.out" ||
    fail "0 on SSH $step must report cancellation"
  [[ "$(count_line "$WORKDIR/add.out" '1) SSH')" == 2 ]] ||
    fail "0 on SSH $step must return to the Add Service menu"
  pass "0 on SSH $step cancels draft and returns to menu"
done

# --- frp_menu_nav: shared classification for the top-level menu ---------------
nav_out="$(frp_menu_nav top "Agent menu" 8 0 2>&1)" && rc=0 || rc=$?
[[ "$rc" == 11 ]] || fail "top-level 0 must be classified as 'not available here' (rc=$rc)"
grep -q 'top menu' <<<"$nav_out" || fail "top-level 0 must explain that this is the top menu"
grep -q 'Enter 8 to exit' <<<"$nav_out" || fail "top-level 0 must name the Exit number"
nav_out="$(frp_menu_nav top "Agent menu" 8 '?' 2>&1)" && rc=0 || rc=$?
[[ "$rc" == 10 ]] || fail "? must be classified as help (rc=$rc)"
grep -q 'Menu help' <<<"$nav_out" || fail "? must print menu help"
grep -q 'You stay in this menu' <<<"$nav_out" || fail "help must say the user stays"
frp_menu_nav top "Agent menu" 8 3 >/dev/null 2>&1 && rc=0 || rc=$?
[[ "$rc" == 0 ]] || fail "a normal choice passes through (rc=$rc)"
frp_menu_nav sub "Add a service" 5 0 >/dev/null 2>&1 && rc=0 || rc=$?
[[ "$rc" == 12 ]] || fail "submenu 0 is back (rc=$rc)"
pass "frp_menu_nav classifies ?, 0 and numbers consistently"

# --- end of input (Ctrl-D / exhausted script) must leave the menu, not loop ----
eof_probe() {
  local input="$1"
  (
    frp_reset_test_input
    export FRP_CLIENT_TEST_INPUT="$input"
    PAYLOAD=""
    frp_ux_prompt_new_service PAYLOAD >"$WORKDIR/eof.out" 2>"$WORKDIR/eof.err"
    echo "rc=$?" >"$WORKDIR/eof.rc"
  ) &
  local pid=$! waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 0.2
    waited=$((waited + 1))
    if (( waited > 75 )); then
      kill -9 "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 1
    fi
  done
  wait "$pid" 2>/dev/null || true
  return 0
}
eof_probe $'zzz\n' || fail "end of input at the add-service menu must not loop forever"
grep -q 'End of input' "$WORKDIR/eof.err" "$WORKDIR/eof.out" || fail "end of input must be reported once"
[[ "$(grep -c 'ERROR: select' "$WORKDIR/eof.err" || true)" -le 1 ]] || fail "end of input must not repeat the invalid-input error"
pass "end of input leaves the menu"

echo
echo "FRP_LEGACY_MENU_NAVIGATION_TEST=PASS"
