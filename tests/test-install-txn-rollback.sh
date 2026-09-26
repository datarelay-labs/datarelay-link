#!/usr/bin/env bash
# Server installer snapshot/restore must reverse project-owned mutations without
# touching CA/token/registry/reservations.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
TREE="$WORKDIR/root"
SNAP="$WORKDIR/snap"
mkdir -p \
  "$TREE/etc/drlink/pki" \
  "$TREE/etc/frp" \
  "$TREE/etc/systemd/system" \
  "$TREE/usr/local/lib/drlink" \
  "$TREE/usr/local/sbin" \
  "$TREE/var/lib/drlink/enrollments" \
  "$TREE/var/lib/drlink/bootstrap"

# Pre-cutover Direct state
printf 'mode=direct\n' >"$TREE/etc/drlink/config.json"
printf 'bindPort = 443\n' >"$TREE/etc/frp/frps.toml"
printf 'token-secret\n' >"$TREE/etc/frp/server_token"
chmod 600 "$TREE/etc/frp/server_token"
printf '{"schema_version":2,"clients":{},"reserved":{}}\n' >"$TREE/var/lib/drlink/registry.json"
chmod 600 "$TREE/var/lib/drlink/registry.json"
printf 'CA' >"$TREE/etc/drlink/pki/ca.key"
chmod 600 "$TREE/etc/drlink/pki/ca.key"
printf 'ca-crt' >"$TREE/etc/drlink/pki/ca.crt"
printf 'unit-frps\n' >"$TREE/etc/systemd/system/drlink-server.service"
printf 'lib\n' >"$TREE/usr/local/lib/drlink/frp-common.sh"
printf 'tool\n' >"$TREE/usr/local/sbin/frpctl"
printf '1.9.1\n' >"$TREE/etc/drlink/version"
TOKEN_SHA="$(sha256sum "$TREE/etc/frp/server_token" | awk '{print $1}')"
REG_SHA="$(sha256sum "$TREE/var/lib/drlink/registry.json" | awk '{print $1}')"
CA_SHA="$(sha256sum "$TREE/etc/drlink/pki/ca.key" | awk '{print $1}')"

export FRP_SERVER_TEST_ROOT="$TREE"
python3 "$ROOT/lib/frp_install_txn.py" snapshot --root "$TREE" --dest "$SNAP" \
  || fail "snapshot"

# Mutate toward single443 mixed state
printf 'mode=single443\n' >"$TREE/etc/drlink/config.json"
printf 'bindPort = 7000\n' >"$TREE/etc/frp/frps.toml"
printf 'frontend\n' >"$TREE/etc/drlink/frontend.conf"
printf 'unit-frontend\n' >"$TREE/etc/systemd/system/drlink-frontend.service"
printf 'newlib\n' >"$TREE/usr/local/lib/drlink/frp-common.sh"
printf '2.1.0\n' >"$TREE/etc/drlink/version"
# Attempt (forbidden) "rollback" side effects must not be performed by restore
printf 'token-rotated\n' >"$TREE/etc/frp/server_token"
printf '{"schema_version":2,"clients":{"x":{}},"reserved":{"1":1}}\n' \
  >"$TREE/var/lib/drlink/registry.json"
printf 'CA-rotated' >"$TREE/etc/drlink/pki/ca.key"

python3 "$ROOT/lib/frp_install_txn.py" restore --root "$TREE" --dest "$SNAP" \
  || fail "restore"

grep -q 'mode=direct' "$TREE/etc/drlink/config.json" || fail "config not restored"
grep -q 'bindPort = 443' "$TREE/etc/frp/frps.toml" || fail "toml not restored"
[[ ! -f "$TREE/etc/drlink/frontend.conf" ]] || fail "frontend.conf should be absent again"
[[ ! -f "$TREE/etc/systemd/system/drlink-frontend.service" ]] || fail "frontend unit should be absent again"
grep -q '^lib$' "$TREE/usr/local/lib/drlink/frp-common.sh" || fail "lib not restored"
grep -q '1.9.1' "$TREE/etc/drlink/version" || fail "version not restored"

# Protected paths must never be rolled back/rotated by the txn helper.
# Mutations applied after the snapshot must remain (restore skips them).
grep -q 'token-rotated' "$TREE/etc/frp/server_token" || fail "token must not be restored/deleted"
grep -q '"x"' "$TREE/var/lib/drlink/registry.json" || fail "registry must not be restored"
grep -q 'CA-rotated' "$TREE/etc/drlink/pki/ca.key" || fail "CA must not be restored"
[[ "$(sha256sum "$TREE/etc/frp/server_token" | awk '{print $1}')" != "$TOKEN_SHA" ]] \
  || fail "token unexpectedly restored to snapshot value"
[[ "$(sha256sum "$TREE/var/lib/drlink/registry.json" | awk '{print $1}')" != "$REG_SHA" ]] \
  || fail "registry unexpectedly restored"
[[ "$(sha256sum "$TREE/etc/drlink/pki/ca.key" | awk '{print $1}')" != "$CA_SHA" ]] \
  || fail "CA unexpectedly restored"
pass "TXN_RESTORE_PROJECT_STATE"
pass "TXN_NEVER_TOUCH_CA_TOKEN_REGISTRY"

# Failure-injection hooks exist for meaningful install phases.
for hook in \
  FRP_INSTALL_HOOK_FRONTEND_PROXY_FAIL \
  FRP_INSTALL_HOOK_HEALTH_FAIL \
  FRP_INSTALL_HOOK_START_FAIL \
  FRP_INSTALL_HOOK_ENABLE_FAIL \
  FRP_INSTALL_HOOK_DEP_FAIL
do
  grep -q "$hook" "$ROOT/install-server.sh" || fail "missing failure hook $hook"
done
grep -q 'frp_server_fail_after_mutation' "$ROOT/install-server.sh" || fail "missing fail-after-mutation helper"
grep -q 'frp_server_create_snapshot' "$ROOT/install-server.sh" || fail "missing snapshot call site"
grep -q 'frp_verify_frontend_proxy_health' "$ROOT/install-server.sh" || fail "missing frontend proxy gate"
pass "TXN_FAILURE_HOOKS_PRESENT"

python3 - "$ROOT" <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "lib"))
import frp_install_txn
os.environ["FRP_INSTALL_TXN_HOOK_SYSTEMD_FAIL"] = "1"
os.environ.pop("FRP_SERVER_TEST_ROOT", None)
ok = frp_install_txn.apply_service_states({
    "services": {
        "skipped": False,
        "units": [{"unit": "drlink-server.service", "enabled": "enabled", "active": "active"}],
    }
}, skip=False)
if ok:
    raise SystemExit("systemd hook should fail apply_service_states")
print("SYSTEMD_HOOK_OK")
PY
pass "ROLLBACK_SYSTEMD_FAILURE_TEST"

# Failed upgrade after legacy unit retirement must restore the prior supervisor
# and public CLI, and must stop the new unit before restarting the old one.
LEGACY="$WORKDIR/legacy-root"
LSNAP="$WORKDIR/legacy-snap"
LSTATE="$WORKDIR/legacy-state"
mkdir -p \
  "$LEGACY/etc/systemd/system" \
  "$LEGACY/usr/local/bin" \
  "$LEGACY/usr/local/sbin" \
  "$LSTATE"
printf 'legacy-frps\n' >"$LEGACY/etc/systemd/system/frps.service"
printf 'legacy-cli\n' >"$LEGACY/usr/local/bin/frpctl"
printf 'legacy-status\n' >"$LEGACY/usr/local/sbin/frp-server-status"
for unit in frps.service drlink-server.service drlink-client.service; do
  echo not-found >"$LSTATE/${unit}.load"
  echo not-found >"$LSTATE/${unit}.enabled"
  echo inactive >"$LSTATE/${unit}.active"
done
echo loaded >"$LSTATE/frps.service.load"
echo enabled >"$LSTATE/frps.service.enabled"
echo active >"$LSTATE/frps.service.active"
unset FRP_SERVER_TEST_ROOT FRP_INSTALL_TXN_HOOK_SYSTEMD_FAIL || true
cat >"$WORKDIR/legacy-systemctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
STATE="${FRP_MOCK_SYSTEMCTL_STATE:?}"
LOG="${FRP_MOCK_SYSTEMCTL_LOG:-}"
mkdir -p "$STATE"
[[ -z "$LOG" ]] || printf '%s\n' "$*" >>"$LOG"
unit=""
cmd="${1:-}"
shift || true
case "$cmd" in
  show)
    while [[ $# -gt 0 ]]; do
      case "$1" in
        -p|--value|LoadState) shift ;;
        *) unit="$1"; shift ;;
      esac
    done
    if [[ -f "${STATE}/${unit}.load" ]]; then
      cat "${STATE}/${unit}.load"
    else
      echo not-found
    fi
    exit 0
    ;;
  is-enabled)
    unit="${1:-}"
    if [[ -f "${STATE}/${unit}.enabled" ]]; then
      cat "${STATE}/${unit}.enabled"
      grep -qx enabled "${STATE}/${unit}.enabled" && exit 0
      exit 1
    fi
    echo not-found
    exit 1
    ;;
  is-active)
    unit="${1:-}"
    if [[ -f "${STATE}/${unit}.active" ]]; then
      cat "${STATE}/${unit}.active"
      grep -qx active "${STATE}/${unit}.active" && exit 0
      exit 3
    fi
    echo inactive
    exit 3
    ;;
  daemon-reload) exit 0 ;;
  reset-failed)
    # Real reset-failed clears the failed state and does not stop a running unit.
    unit="${1:-}"
    echo reset-failed >>"${STATE}/${unit}.events"
    exit 0
    ;;
  stop)
    unit="${1:-}"
    echo stop >>"${STATE}/${unit}.events"
    echo inactive >"${STATE}/${unit}.active"
    exit 0
    ;;
  restart|start)
    unit="${1:-}"
    echo "$cmd" >>"${STATE}/${unit}.events"
    echo loaded >"${STATE}/${unit}.load"
    echo active >"${STATE}/${unit}.active"
    exit 0
    ;;
  enable)
    unit="${1:-}"
    echo enable >>"${STATE}/${unit}.events"
    echo enabled >"${STATE}/${unit}.enabled"
    echo loaded >"${STATE}/${unit}.load"
    exit 0
    ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$WORKDIR/legacy-systemctl"
export FRP_INSTALL_TXN_HOOK_SYSTEMCTL="$WORKDIR/legacy-systemctl"
export FRP_MOCK_SYSTEMCTL_STATE="$LSTATE"
export FRP_MOCK_SYSTEMCTL_LOG="$WORKDIR/legacy-systemctl.log"
: >"$WORKDIR/legacy-systemctl.log"
python3 "$ROOT/lib/frp_install_txn.py" snapshot --root "$LEGACY" --dest "$LSNAP" \
  || fail "legacy snapshot"
rm -f "$LEGACY/etc/systemd/system/frps.service" \
  "$LEGACY/usr/local/bin/frpctl" \
  "$LEGACY/usr/local/sbin/frp-server-status"
printf 'new-unit\n' >"$LEGACY/etc/systemd/system/drlink-server.service"
printf 'new-cli\n' >"$LEGACY/usr/local/bin/drlink"
printf 'new-client-unit\n' >"$LEGACY/etc/systemd/system/drlink-client.service"
echo loaded >"$LSTATE/drlink-server.service.load"
echo enabled >"$LSTATE/drlink-server.service.enabled"
echo active >"$LSTATE/drlink-server.service.active"
echo loaded >"$LSTATE/drlink-client.service.load"
echo active >"$LSTATE/drlink-client.service.active"
echo not-found >"$LSTATE/frps.service.load"
echo inactive >"$LSTATE/frps.service.active"
python3 "$ROOT/lib/frp_install_txn.py" restore --root "$LEGACY" --dest "$LSNAP" --apply-services \
  || fail "legacy restore"
grep -q 'legacy-frps' "$LEGACY/etc/systemd/system/frps.service" || fail "legacy frps unit not restored"
grep -q 'legacy-cli' "$LEGACY/usr/local/bin/frpctl" || fail "legacy frpctl not restored"
grep -q 'legacy-status' "$LEGACY/usr/local/sbin/frp-server-status" || fail "legacy status tool not restored"
[[ ! -f "$LEGACY/etc/systemd/system/drlink-server.service" ]] || fail "new server unit survived rollback"
[[ ! -f "$LEGACY/usr/local/bin/drlink" ]] || fail "new drlink CLI survived rollback"
[[ ! -f "$LEGACY/etc/systemd/system/drlink-client.service" ]] || fail "migration-created client unit survived rollback"
python3 - "$WORKDIR/legacy-systemctl.log" <<'PY' || fail "legacy restart order"
import sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
stop_at = next(i for i, line in enumerate(lines) if line.startswith("stop drlink-server.service"))
restart_at = next(i for i, line in enumerate(lines) if line.startswith("restart frps.service"))
if stop_at > restart_at:
    raise SystemExit("restarted legacy frps before stopping drlink-server: %s" % lines)
if not any(line.startswith("stop drlink-client.service") for line in lines):
    raise SystemExit("did not stop migration-created drlink-client: %s" % lines)
PY
grep -qx active "$LSTATE/frps.service.active" || fail "legacy frps was not restarted"
pass "LEGACY_UPGRADE_ROLLBACK_RESTORES_PRIOR"

echo "INSTALL_TXN_ROLLBACK_TEST=PASS"
