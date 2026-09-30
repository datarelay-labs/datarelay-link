#!/usr/bin/env bash
# Hardened units must be able to chmod /run/drlink during ExecStartPre.
# ProtectSystem=strict leaves /run read-only, and RuntimeDirectory=drlink/<leaf>
# only makes that leaf writable on systemd 255. The parent needs ReadWritePaths.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d /var/tmp/drlink-rtprep.XXXXXX)"
RUN_NAME="drlink-rtprep-$$"
RUN_PARENT="/run/${RUN_NAME}"
# PrivateTmp hides /tmp and /var/tmp inside the unit, so paths the sandbox must
# see live under /var/lib, outside those mounts.
SERVICE_ROOT="/var/lib/rtprep-$$"
PROOF="${SERVICE_ROOT}/proof"
GROUP="drlinkrt$$"
UNIT_NAME="drlink-rtprep-$$"
cleanup() {
  if [[ "${LIVE_STARTED:-0}" == 1 ]]; then
    sudo systemctl stop "${UNIT_NAME}.service" >/dev/null 2>&1 || true
    sudo rm -f "/run/systemd/system/${UNIT_NAME}.service"
    sudo systemctl daemon-reload >/dev/null 2>&1 || true
    sudo rm -rf "$RUN_PARENT" "$SERVICE_ROOT"
    sudo userdel "$GROUP" >/dev/null 2>&1 || true
    sudo groupdel "$GROUP" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

path_covered() {
  local path="$1" entry
  shift
  for entry in "$@"; do
    entry="${entry#-}"
    if [[ "$path" == "$entry" || "$path" == "$entry"/* ]]; then
      return 0
    fi
  done
  return 1
}

static_unit() {
  local unit="$1" base rw_line pre
  base="$(basename "$unit")"
  pre="$(grep -E '^ExecStartPre=' "$unit" || true)"
  [[ "$pre" == *"/run/drlink"* ]] || return 0
  grep -q '^ProtectSystem=strict$' "$unit" || fail "$base lost ProtectSystem=strict"
  grep -q '^NoNewPrivileges=true$' "$unit" || fail "$base lost NoNewPrivileges"
  rw_line="$(grep -E '^ReadWritePaths=' "$unit" || true)"
  [[ -n "$rw_line" ]] || fail "$base missing ReadWritePaths"
  # shellcheck disable=SC2086
  set -- ${rw_line#ReadWritePaths=}
  path_covered /run/drlink "$@" || fail "$base cannot write /run/drlink"
  path_covered /run/drlink/egress "$@" || fail "$base cannot write /run/drlink/egress"
  path_covered /var/log/drlink "$@" || fail "$base cannot write /var/log/drlink"
  path_covered /var/log/drlink/egress "$@" || fail "$base cannot write /var/log/drlink/egress"
  pass "STATIC_${base}"
}

shopt -s nullglob
units=("$ROOT"/server/*.service)
[[ ${#units[@]} -gt 0 ]] || fail "no unit files"
checked=0
for unit in "${units[@]}"; do
  if grep -q '/run/drlink' "$unit" && grep -q '^ProtectSystem=strict$' "$unit"; then
    static_unit "$unit"
    checked=$((checked + 1))
  fi
done
[[ "$checked" -ge 9 ]] || fail "expected the hardened runtime-prep units, found $checked"
pass "STATIC_RUNTIME_PREP_COVERAGE"

if [[ ! -d /run/systemd/system ]] || ! command -v systemctl >/dev/null 2>&1; then
  echo "SKIP live systemd runtime prep (systemd is not PID 1)"
  exit 0
fi
if [[ "$(id -u)" -ne 0 ]] && ! sudo -n true >/dev/null 2>&1; then
  fail "systemd is available but passwordless root is required for the live prep proof"
fi

# The unit prep treats the name as both a user (id) and a group (chown).
sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$GROUP"
sudo mkdir -p "$PROOF"
sudo chown "$(id -u):$(id -g)" "$SERVICE_ROOT" "$PROOF"
LIVE_STARTED=1

live_unit() {
  local src="$1" base rendered
  base="$(basename "$src" .service)"
  rendered="${WORKDIR}/${base}.service"
  sed \
    -e "s#/run/drlink#${RUN_PARENT}#g" \
    -e "s#^RuntimeDirectory=drlink/#RuntimeDirectory=${RUN_NAME}/#" \
    -e "s#/var/log/drlink#${SERVICE_ROOT}/log/drlink#g" \
    -e "s#/var/lib/drlink#${SERVICE_ROOT}/lib/drlink#g" \
    -e "s#/etc/drlink#${SERVICE_ROOT}/etc/drlink#g" \
    -e "s#/etc/frp#${SERVICE_ROOT}/etc/frp#g" \
    -e "s#g=drlink-egress#g=${GROUP}#" \
    -e "s#^User=.*#User=root#" \
    -e "s#^Group=.*#Group=root#" \
    -e 's#^Type=.*#Type=oneshot#' \
    -e '/^Restart=/d' \
    -e '/^RestartSec=/d' \
    -e "s#^ExecStart=.*#ExecStart=/bin/sh ${PROOF}/check.sh#" \
    -e "s#^ExecStartPre=/bin/sh -c '#ExecStartPre=/bin/sh -c 'set -eu; #" \
    "$src" >"$rendered"

  sudo chown -R "$(id -u):$(id -g)" "$SERVICE_ROOT"
  mkdir -p \
    "${SERVICE_ROOT}/log/drlink/egress" \
    "${SERVICE_ROOT}/lib/drlink/runtime" \
    "${SERVICE_ROOT}/etc/drlink" \
    "${SERVICE_ROOT}/etc/frp"
  : >"${SERVICE_ROOT}/etc/drlink/config.json"
  : >"${SERVICE_ROOT}/lib/drlink/drlink.db"
  : >"${SERVICE_ROOT}/lib/drlink/drlink.db-wal"
  : >"${SERVICE_ROOT}/lib/drlink/drlink.db-shm"
  cat >"${PROOF}/check.sh" <<EOF
#!/bin/sh
set -eu
parent=\$(stat -c %a '${RUN_PARENT}')
egress=\$(stat -c %a '${RUN_PARENT}/egress')
printf '%s\n' "\$parent" > '${SERVICE_ROOT}/log/drlink/parent.mode'
printf '%s\n' "\$egress" > '${SERVICE_ROOT}/log/drlink/egress.mode'
test "\$parent" = 710
test "\$egress" = 700
EOF
  chmod 755 "${PROOF}/check.sh"
  rm -f "${SERVICE_ROOT}/log/drlink/parent.mode" "${SERVICE_ROOT}/log/drlink/egress.mode"
  sudo rm -rf "$RUN_PARENT"
  sudo cp "$rendered" "/run/systemd/system/${UNIT_NAME}.service"
  sudo systemctl daemon-reload
  sudo systemctl reset-failed "${UNIT_NAME}.service" >/dev/null 2>&1 || true
  if ! sudo systemctl start "${UNIT_NAME}.service"; then
    sudo journalctl -u "${UNIT_NAME}.service" -n 40 --no-pager >&2 || true
    fail "live prep failed for $base"
  fi
  [[ "$(sudo cat "${SERVICE_ROOT}/log/drlink/parent.mode")" == "710" ]] || fail "$base parent mode"
  [[ "$(sudo cat "${SERVICE_ROOT}/log/drlink/egress.mode")" == "700" ]] || fail "$base egress mode"
  if sudo journalctl -u "${UNIT_NAME}.service" -n 40 --no-pager | grep -q 'Read-only file system'; then
    fail "$base still hit a read-only runtime path"
  fi
  sudo systemctl stop "${UNIT_NAME}.service" >/dev/null 2>&1 || true
  pass "LIVE_${base}"
}

for unit in "${units[@]}"; do
  if grep -q '/run/drlink' "$unit" && grep -q '^ProtectSystem=strict$' "$unit"; then
    live_unit "$unit"
  fi
done
pass "LIVE_RUNTIME_PREP"
