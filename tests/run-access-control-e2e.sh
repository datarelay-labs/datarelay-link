#!/usr/bin/env bash
# Current v2.4 Remote Access real E2E.
# Proves policy explain + actual allow/deny + live rule update, then restores the pre-run ConfigurationBundle.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
SERVER="${FRP_E2E_SERVER_ALIAS:-frp-e2e-server}"
CLIENT_HOST="${FRP_ACCESS_E2E_CLIENT:-${FRP_E2E_CLIENT_ALIAS:-frp-e2e-client}}"
SOURCE_A_HOST="${FRP_ACCESS_E2E_SOURCE_A:-frp-e2e-rocky8}"
SOURCE_B_HOST="${FRP_ACCESS_E2E_SOURCE_B:-frp-e2e-linux114}"
RUN_ID="${FRP_E2E_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${FRP_ACCESS_E2E_OUT:-$ROOT/e2e-reports/remote-access-$RUN_ID}"
mkdir -p "$OUT_DIR"
exec > >(tee -a "$OUT_DIR/run.log") 2>&1

pass(){ echo "PASS $1"; }
fail(){ echo "FAIL $1" >&2; echo "TARGETED_REAL_E2E=FAIL" >"$OUT_DIR/result.env"; restore || true; exit 1; }
blocker(){ echo "ENVIRONMENT_BLOCKER $1" >&2; echo "TARGETED_REAL_E2E=ENVIRONMENT_BLOCKER" >"$OUT_DIR/result.env"; restore || true; exit 2; }
sshx(){ local h="$1"; shift; ssh "${SSH_OPTS[@]}" "$h" "$@"; }

PRE="/tmp/drlink-remote-access-pre-$RUN_ID.yaml"
SRC_A="e2e-ra-a-${RUN_ID: -6}"
SRC_B="e2e-ra-b-${RUN_ID: -6}"
RULE="e2e-ra-${RUN_ID: -6}"
RESTORE_ARMED=0

restore(){
  if [[ "$RESTORE_ARMED" == "1" ]]; then
    printf 'y\n' | sshx "$SERVER" "sudo drlink system apply configuration '$PRE'" >/dev/null 2>&1 || true
    sshx "$SERVER" "sudo rm -f '$PRE'" >/dev/null 2>&1 || true
    RESTORE_ARMED=0
  fi
}
trap restore EXIT

for h in "$SERVER" "$CLIENT_HOST" "$SOURCE_A_HOST" "$SOURCE_B_HOST"; do
  sshx "$h" 'echo ok' >/dev/null || blocker "unreachable host $h"
done

SOURCE_A_IP="$(sshx "$SOURCE_A_HOST" 'curl -4 -fsS --max-time 8 https://ifconfig.me' | tr -d '\r\n')"
SOURCE_B_IP="$(sshx "$SOURCE_B_HOST" 'curl -4 -fsS --max-time 8 https://ifconfig.me' | tr -d '\r\n')"
[[ -n "$SOURCE_A_IP" && -n "$SOURCE_B_IP" && "$SOURCE_A_IP" != "$SOURCE_B_IP" ]] || blocker "distinct source IPs required"

CLIENT_ID="$(sshx "$CLIENT_HOST" "sudo python3 -c \"import json; print(json.load(open('/etc/frp/client-state.json')).get('machine_id') or '')\"" | tr -d '\r\n')"
[[ "$CLIENT_ID" =~ ^[0-9a-f]{32}$ ]] || blocker "Agent machine_id unavailable"
PREFIX="${CLIENT_ID:0:8}"
HOST_NAME="$(sshx "$SERVER" "sudo drlink show managed-hosts" | awk -v p="$PREFIX" '$1 ~ ("^" p) {print $2; exit}')"
[[ -n "$HOST_NAME" ]] || blocker "Managed Host name not found for $PREFIX"

REMOTE_SERVICE="${FRP_ACCESS_E2E_REMOTE_SERVICE:-ssh}"
SERVICE_OBJECT="${FRP_ACCESS_E2E_SERVICE_OBJECT:-ssh}"
REMOTE_OUT="$(sshx "$CLIENT_HOST" "sudo drlink show remote-service '$REMOTE_SERVICE'")" || blocker "Remote Service $REMOTE_SERVICE unavailable"
PUBLIC_PORT="$(printf '%s\n' "$REMOTE_OUT" | sed -n 's/^Endpoint[[:space:]]*: .*:\([0-9][0-9]*\)$/\1/p' | tail -n1)"
[[ -n "$PUBLIC_PORT" ]] || blocker "Remote Service endpoint unavailable"
SERVER_IP="$(sshx "$SERVER" 'curl -4 -fsS --max-time 8 https://ifconfig.me' | tr -d '\r\n')"

probe(){
  local host="$1"
  sshx "$host" "python3 - <<'PY'
import socket,sys
s=socket.socket(); s.settimeout(6)
try:
    s.connect(('$SERVER_IP', int('$PUBLIC_PORT')))
    data=s.recv(64)
except Exception:
    sys.exit(1)
finally:
    try:s.close()
    except Exception:pass
sys.exit(0 if data.startswith(b'SSH-') else 1)
PY"
}

sshx "$SERVER" "sudo drlink system export configuration '$PRE'" >/dev/null || blocker "cannot export pre-run configuration"
RESTORE_ARMED=1

# Establish an isolated deny-by-default Remote Access policy for this test.
printf 'y\n' | sshx "$SERVER" "sudo drlink unset remote-access policy" >/dev/null 2>&1 || true
sshx "$SERVER" "sudo drlink set network-object '$SRC_A' type ip value '$SOURCE_A_IP'"
sshx "$SERVER" "sudo drlink set network-object '$SRC_B' type ip value '$SOURCE_B_IP'"
sshx "$SERVER" "sudo drlink set remote-access '$RULE' mode whitelist source '$SRC_A' destination '$HOST_NAME' service '$SERVICE_OBJECT' enabled"

sshx "$SERVER" "sudo drlink test remote-access source '$SRC_A' destination '$HOST_NAME' service '$SERVICE_OBJECT'" | tee "$OUT_DIR/test-a.txt" | grep -q 'Effective Result.*ALLOW' || fail "A explain is not ALLOW"
sshx "$SERVER" "sudo drlink test remote-access source '$SRC_B' destination '$HOST_NAME' service '$SERVICE_OBJECT'" | tee "$OUT_DIR/test-b.txt" | grep -q 'Effective Result.*DENY' || fail "B explain is not DENY"
probe "$SOURCE_A_HOST" || fail "A actual traffic not allowed"
if probe "$SOURCE_B_HOST"; then fail "B actual traffic unexpectedly allowed"; fi
pass "REMOTE_ACCESS_ALLOW_DENY"

# Live policy update: move the same rule from A to B and verify traffic flips.
sshx "$SERVER" "sudo drlink set remote-access '$RULE' source '$SRC_B' enabled"
sshx "$SERVER" "sudo drlink test remote-access source '$SRC_A' destination '$HOST_NAME' service '$SERVICE_OBJECT'" | grep -q 'Effective Result.*DENY' || fail "A explain did not flip to DENY"
sshx "$SERVER" "sudo drlink test remote-access source '$SRC_B' destination '$HOST_NAME' service '$SERVICE_OBJECT'" | grep -q 'Effective Result.*ALLOW' || fail "B explain did not flip to ALLOW"
if probe "$SOURCE_A_HOST"; then fail "A actual traffic still allowed after live update"; fi
probe "$SOURCE_B_HOST" || fail "B actual traffic not allowed after live update"
pass "REMOTE_ACCESS_POLICY_LIVE_UPDATE"

restore
trap - EXIT
cat >"$OUT_DIR/result.env" <<EOF
TARGETED_REAL_E2E=PASS
ACCESS_REAL_E2E=PASS
ACCESS_FAIL_CLOSED=PASS
ACCESS_POLICY_LIVE_UPDATE=PASS
EOF
echo "TARGETED_REAL_E2E=PASS"
