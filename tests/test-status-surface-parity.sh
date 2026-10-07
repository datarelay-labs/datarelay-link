#!/usr/bin/env bash
# Public status surfaces must share the v2.4 SQLite-backed status model.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
SERVER="$WORK/server"
cleanup() {
  chmod 700 "$SERVER/var/lib/drlink" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

fail() { echo "FAIL $1" >&2; exit 1; }
pass() { echo "PASS $1"; }

mkdir -p "$SERVER/etc/drlink" "$SERVER/var/lib/drlink"
cat >"$SERVER/etc/drlink/config.json" <<'JSON'
{
  "role": "server",
  "deployment_mode": "direct",
  "public_host": "203.0.113.10"
}
JSON
PYTHONPATH="$ROOT/lib" DRLINK_TEST_ROOT="$SERVER" python3 - <<'PY'
from drlink_control_plane import ControlPlane
p = ControlPlane()
p.upsert_client("status-parity-host", label="status-parity")
p.close()
PY

export FRP_CTL_FORCE_DRLINK=1
export FRP_CTL_CMD_NAME=drlink
export FRP_CTL_BIN_DIR="$ROOT/tools"
export FRP_CTL_TEST_ROOT="$SERVER"
export FRP_DEPLOY_TEST_ROOT="$SERVER"
export FRP_SKIP_SYSTEMD=1

"$ROOT/tools/frpctl" show status >"$WORK/show.out"
"$ROOT/tools/frpctl" system status >"$WORK/system.out"
cmp -s "$WORK/show.out" "$WORK/system.out" || {
  diff -u "$WORK/show.out" "$WORK/system.out" >&2 || true
  fail "show/system status mismatch"
}
grep -q 'Control DB' "$WORK/show.out" || fail "Control DB missing"
grep -q 'DB Revision' "$WORK/show.out" || fail "DB Revision missing"
grep -q 'Managed Hosts' "$WORK/show.out" || fail "Managed Hosts missing"
if grep -qE '^Clients[[:space:]]*:|^Registry (schema|state)[[:space:]]*:' "$WORK/show.out"; then
  fail "legacy registry model leaked into public status"
fi
pass "PUBLIC_STATUS_SQLITE_PARITY"

# A broken/unreadable control DB must fail rather than print an error with rc=0.
chmod 000 "$SERVER/var/lib/drlink"
set +e
"$ROOT/tools/frpctl" show status >"$WORK/denied.out" 2>"$WORK/denied.err"
rc=$?
set -e
chmod 700 "$SERVER/var/lib/drlink"
[[ "$rc" -ne 0 ]] || fail "control DB failure returned rc=0"
pass "PUBLIC_STATUS_ERROR_RC_NONZERO"

echo "STATUS_SURFACE_PARITY=PASS"
