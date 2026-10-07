#!/usr/bin/env bash
# Canonical Data Relay Link shell/REPL contract.
# Uses isolated fixtures only; never mutates a live host.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

chmod +x "$ROOT/tools/frpctl" "$ROOT/tools/frp-client"

CTL="$ROOT/tools/frpctl"
export FRP_CTL_FORCE_DRLINK=1
export FRP_CTL_CMD_NAME=drlink
export FRP_CTL_BIN_DIR="$ROOT/tools"
export FRP_CLIENT_LIB="$ROOT/lib/frp-client-common.sh"
export FRP_SKIP_SYSTEMD=1
export HOME="$WORKDIR/home"
mkdir -p "$HOME"

write_client_tree() {
  local tree="$1"
  mkdir -p "$tree/etc/frp" "$tree/etc/drlink"
  python3 - "$tree/etc/frp/client-state.json" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "schema_version": 1,
    "allocator_url": "https://127.0.0.1:9/enroll",
    "frp_server": "203.0.113.10",
    "frp_server_port": 443,
    "hostname": "ctl-client",
    "machine_id": "00112233445566778899aabbccddeeff",
    "host_id": "ctl-client-00112233",
    "services": {
        "ssh": {
            "id": "ssh", "name": "SSH", "preset": "ssh", "protocol": "tcp",
            "local_ip": "127.0.0.1", "local_port": 22, "remote_port": 6002,
            "enabled": True, "ssh_user": "aella",
        }
    },
}, indent=2, sort_keys=True) + "\n")
PY
  cat >"$tree/etc/drlink/version" <<'EOF'
PROJECT_VERSION=1.4.0
FRP_VERSION=0.71.0
EOF
}

write_server_tree() {
  local tree="$1"
  mkdir -p "$tree/etc/drlink" "$tree/var/lib/drlink"
  python3 - "$tree/etc/drlink/config.json" "$tree/var/lib/drlink/registry.json" <<'PY'
import json, sys
from pathlib import Path
cfg, reg = Path(sys.argv[1]), Path(sys.argv[2])
cfg.write_text(json.dumps({
    "public_ip": "203.0.113.10",
    "public_host": "203.0.113.10",
    "control_port": 443,
    "port_start": 6000,
    "port_end": 6098,
    "listen_port": 6099,
    "allocator_public_url": "https://203.0.113.10:6099/enroll",
    "registry_file": "/var/lib/drlink/registry.json",
}, indent=2, sort_keys=True) + "\n")
reg.write_text(json.dumps({
    "schema_version": 2,
    "reserved": [],
    "clients": {
        "aabbccdd0011": {
            "hostname": "dp-os-upgrade",
            "label": "oci-e2e-renamed",
            "mgmt_status": "enrolled",
            "services": {
                "ssh": {"id": "ssh", "remote_port": 6000, "enabled": True}
            },
        },
    },
}, indent=2, sort_keys=True) + "\n")
PY
  # Current v2.4 Server authority is SQLite. Keep the legacy registry fixture
  # only for compatibility/status context, but initialize the canonical control
  # plane so public Server commands exercise the real authoritative state path.
  python3 - "$ROOT/lib" "$tree" <<'PYDB'
import sys
sys.path.insert(0, sys.argv[1])
from drlink_control_plane import ControlPlane
plane = ControlPlane(sys.argv[2])
plane.close()
PYDB
  cat >"$tree/etc/drlink/version" <<'EOF'
PROJECT_VERSION=1.4.0
FRP_VERSION=0.71.0
EOF
}

prompt_count() {
  grep -cE '^(frpctl|drlink)>' "$1"
}

run_repl() {
  local tree="$1" outfile="$2" rc
  shift 2
  export FRP_CTL_TEST_ROOT="$tree"
  rm -f "${TMPDIR:-/tmp}/frpctl-test-input.$$"     "${TMPDIR:-/tmp}/frpctl-test-input.$$.pos"     "${TMPDIR:-/tmp}/frpctl-test-input.${PPID}"     "${TMPDIR:-/tmp}/frpctl-test-input.${PPID}.pos" 2>/dev/null || true
  FRP_CTL_TEST_INPUT="$(printf '%s\n' "$@")"
  export FRP_CTL_TEST_INPUT
  set +e
  "$CTL" >"$outfile" 2>"${outfile}.err"
  rc=$?
  set -e
  cat "${outfile}.err" >>"$outfile"
  unset FRP_CTL_TEST_INPUT
  rm -f "${TMPDIR:-/tmp}/frpctl-test-input.$$"     "${TMPDIR:-/tmp}/frpctl-test-input.$$.pos"     "${TMPDIR:-/tmp}/frpctl-test-input.${PPID}"     "${TMPDIR:-/tmp}/frpctl-test-input.${PPID}.pos" 2>/dev/null || true
  return "$rc"
}

expect_rejected() {
  local label="$1"
  shift
  local out="$WORKDIR/reject-${label}.out" err="$WORKDIR/reject-${label}.err" rc
  set +e
  "$CTL" "$@" >"$out" 2>"$err"
  rc=$?
  set -e
  [[ "$rc" -ne 0 ]] || fail "$label unexpectedly succeeded"
  cat "$out" "$err" >"$WORKDIR/reject-${label}.combined"
}

CLIENT="$WORKDIR/client"
SERVER="$WORKDIR/server"
BOTH="$WORKDIR/both"
write_client_tree "$CLIENT"
write_server_tree "$SERVER"
write_client_tree "$BOTH"
write_server_tree "$BOTH"

# ---------------------------------------------------------------------------
# Canonical help and unknown-command behavior
# ---------------------------------------------------------------------------
export FRP_CTL_TEST_ROOT="$SERVER"
export FRP_DEPLOY_TEST_ROOT="$SERVER"
"$CTL" help >"$WORKDIR/help.out"
grep -q 'help managed-hosts' "$WORKDIR/help.out" || fail "help managed-hosts"
grep -q 'help internet-access' "$WORKDIR/help.out" || fail "help internet-access"
grep -q 'help commands' "$WORKDIR/help.out" || fail "help commands"
! grep -q 'help clients' "$WORKDIR/help.out" || fail "help leaked clients"

"$CTL" help managed-hosts >"$WORKDIR/help-managed-hosts.out"
grep -q 'Managed Hosts' "$WORKDIR/help-managed-hosts.out" || fail "managed-host help"
grep -q 'show managed-hosts' "$WORKDIR/help-managed-hosts.out" || fail "managed-host help command"

expect_rejected help-clients help clients
grep -q 'Unknown help topic: clients' "$WORKDIR/reject-help-clients.combined"   || fail "obsolete help topic did not fail closed"

expect_rejected help-objects help objects
grep -q 'Unknown help topic: objects' "$WORKDIR/reject-help-objects.combined"   || fail "obsolete object help topic did not fail closed"

if "$CTL" definitely-not-a-command >"$WORKDIR/unknown.out" 2>"$WORKDIR/unknown.err"; then
  fail "unknown command should fail"
fi
grep -qi 'unknown command' "$WORKDIR/unknown.err" || fail "unknown command message"
pass "FRPCTL_CANONICAL_HELP"
# ---------------------------------------------------------------------------
# Client role: canonical direct paths + provenance
# ---------------------------------------------------------------------------
export FRP_CTL_TEST_ROOT="$CLIENT"
export FRP_CLIENT_TEST_ROOT="$CLIENT"
"$CTL" show status >"$WORKDIR/client-status.out"
grep -q 'Data Relay Link' "$WORKDIR/client-status.out" || fail "client status header"
grep -q 'Remote Services' "$WORKDIR/client-status.out" || fail "client status remote services"

"$CTL" system version >"$WORKDIR/client-version.out"
grep -q 'Data Relay Link: 1.4.0-dev' "$WORKDIR/client-version.out" || fail "client display identity"
grep -q 'Channel: development' "$WORKDIR/client-version.out" || fail "client channel"
grep -q 'Source HEAD: unknown' "$WORKDIR/client-version.out" || fail "client source head"
grep -q 'Relay Engine (FRP): 0.71.0' "$WORKDIR/client-version.out" || fail "client engine version"
grep -q 'Role: Agent Host' "$WORKDIR/client-version.out" || fail "client role"
! grep -q 'Project version' "$WORKDIR/client-version.out" || fail "legacy project version label"
! grep -q 'Bundle SHA256: unknown' "$WORKDIR/client-version.out" || fail "unknown bundle provenance"

export FRP_CTL_DRY_RUN=1
"$CTL" system update product >"$WORKDIR/client-update-product.out"
grep -qx 'DISPATCH frp-client update' "$WORKDIR/client-update-product.out"   || fail "client product update dispatch"
"$CTL" system update engine >"$WORKDIR/client-update-engine.out"
grep -qx 'DISPATCH frp-update' "$WORKDIR/client-update-engine.out"   || fail "client engine update dispatch"
unset FRP_CTL_DRY_RUN
for retired in status update info services manage client-status frp-update; do
  expect_rejected "client-root-${retired}" "$retired"
  grep -qi 'unknown command' "$WORKDIR/reject-client-root-${retired}.combined"     || fail "retired client root $retired missing rejection"
done
pass "FRPCTL_CLIENT_CANONICAL_ROOTS"

# ---------------------------------------------------------------------------
# Server role: status parity + canonical update paths
# ---------------------------------------------------------------------------
unset FRP_CLIENT_TEST_ROOT
export FRP_CTL_TEST_ROOT="$SERVER"
export FRP_DEPLOY_TEST_ROOT="$SERVER"

"$CTL" show status >"$WORKDIR/server-status.out"
"$CTL" system status >"$WORKDIR/server-system-status.out"
status_lines="$(wc -l <"$WORKDIR/server-status.out")"
head -n "$status_lines" "$WORKDIR/server-system-status.out" >"$WORKDIR/server-system-status-prefix.out"
cmp -s "$WORKDIR/server-status.out" "$WORKDIR/server-system-status-prefix.out"   || { diff -u "$WORKDIR/server-status.out" "$WORKDIR/server-system-status-prefix.out" >&2 || true; fail "status summary preservation"; }
grep -q 'DRLink Server' "$WORKDIR/server-status.out" || fail "server role"
grep -q 'Control DB' "$WORKDIR/server-status.out" || fail "server control DB"
grep -q '^Server Settings$' "$WORKDIR/server-system-status.out" || fail "server settings heading"
grep -q '^Public hostname ' "$WORKDIR/server-system-status.out" || fail "server public hostname setting"
grep -q '^Bootstrap hostname ' "$WORKDIR/server-system-status.out" || fail "server bootstrap hostname setting"
grep -q '^Linux/macOS Agent installer ' "$WORKDIR/server-system-status.out" || fail "server installer setting"
grep -q '^Windows Agent installer ' "$WORKDIR/server-system-status.out" || fail "server windows installer setting"

"$CTL" system version >"$WORKDIR/server-version.out"
grep -q 'Data Relay Link: 1.4.0-dev' "$WORKDIR/server-version.out" || fail "server display identity"
grep -q 'Role: DRLink Server' "$WORKDIR/server-version.out" || fail "server version role"
! grep -q 'Project version' "$WORKDIR/server-version.out" || fail "server legacy version label"

export FRP_CTL_DRY_RUN=1
"$CTL" system update product >"$WORKDIR/server-update-product.out"
grep -qx 'DISPATCH frp-project-update' "$WORKDIR/server-update-product.out"   || fail "server product update dispatch"
"$CTL" system update engine >"$WORKDIR/server-update-engine.out"
grep -qx 'DISPATCH frp-update' "$WORKDIR/server-update-engine.out"   || fail "server engine update dispatch"
"$CTL" system backup /tmp/drlink-test-backup.tar.gz >"$WORKDIR/server-backup.out"
grep -qx 'DISPATCH frp-backup /tmp/drlink-test-backup.tar.gz' "$WORKDIR/server-backup.out"   || fail "server backup dispatch"
unset FRP_CTL_DRY_RUN

for retired in clients client-info client-set create-client enroll revoke release-service release-client backup server-status; do
  expect_rejected "server-root-${retired}" "$retired"
  grep -qi 'unknown command' "$WORKDIR/reject-server-root-${retired}.combined"     || fail "retired server root $retired missing rejection"
done
pass "FRPCTL_SERVER_CANONICAL_ROOTS"
pass "FRPCTL_STATUS_PARITY"

# ---------------------------------------------------------------------------
# Retired parser-only resources fail closed with current guidance
# ---------------------------------------------------------------------------
expect_rejected show-clients show clients
grep -qi 'managed-hosts' "$WORKDIR/reject-show-clients.combined" || fail "show clients guidance"
expect_rejected show-client show client dp1
grep -qi 'managed-host' "$WORKDIR/reject-show-client.combined" || fail "show client guidance"
expect_rejected set-client set client dp1 label production
grep -qi 'managed-host' "$WORKDIR/reject-set-client.combined" || fail "set client guidance"
expect_rejected unset-client unset client dp1
grep -qi 'managed-host' "$WORKDIR/reject-unset-client.combined" || fail "unset client guidance"
expect_rejected show-services show services
grep -qi 'remote-service' "$WORKDIR/reject-show-services.combined" || fail "show services guidance"
expect_rejected set-service set service ssh target-port 2222
grep -qi 'remote-service' "$WORKDIR/reject-set-service.combined" || fail "set service guidance"
expect_rejected system-services system services apply
grep -qi 'remote-service' "$WORKDIR/reject-system-services.combined" || fail "system services guidance"
expect_rejected show-internet show internet
grep -qi 'internet-access' "$WORKDIR/reject-show-internet.combined" || fail "show internet guidance"
expect_rejected test-internet test internet 10.0.0.5 example.com 443
grep -qi 'internet-access' "$WORKDIR/reject-test-internet.combined" || fail "test internet guidance"
expect_rejected show-fixed-tcp show fixed-tcp
grep -qi 'Service Object' "$WORKDIR/reject-show-fixed-tcp.combined" || fail "fixed-tcp guidance"
expect_rejected show-access-log show access-log
grep -qi 'system audit' "$WORKDIR/reject-show-access-log.combined" || fail "access-log guidance"
expect_rejected show-groups show groups
grep -qi 'managed-host-group' "$WORKDIR/reject-show-groups.combined" || fail "group guidance"
pass "FRPCTL_RETIRED_SURFACE_FAIL_CLOSED"

# ---------------------------------------------------------------------------
# Guided menu / REPL use the same canonical identity renderer
# ---------------------------------------------------------------------------
export FRP_CTL_TEST_ROOT="$CLIENT"
export FRP_CLIENT_TEST_ROOT="$CLIENT"
export FRP_CTL_TEST_MENU=1
run_repl "$CLIENT" "$WORKDIR/client-menu.out" menu exit || fail "client menu"
unset FRP_CTL_TEST_MENU
grep -q 'Data Relay Link: 1.4.0-dev' "$WORKDIR/client-menu.out" || fail "client menu identity"
grep -q 'Channel: development' "$WORKDIR/client-menu.out" || fail "client menu channel"
grep -q 'Source HEAD: unknown' "$WORKDIR/client-menu.out" || fail "client menu head"
grep -q 'Role: Agent Host' "$WORKDIR/client-menu.out" || fail "client menu role"
grep -q '1) Remote Services' "$WORKDIR/client-menu.out" || fail "client menu remote services"
! grep -q 'Project version' "$WORKDIR/client-menu.out" || fail "client menu raw project version"
! grep -q 'Bundle SHA256.*unknown' "$WORKDIR/client-menu.out" || fail "client menu unknown bundle"

unset FRP_CLIENT_TEST_ROOT
export FRP_CTL_TEST_ROOT="$SERVER"
export FRP_CTL_TEST_MENU=1
run_repl "$SERVER" "$WORKDIR/server-menu.out" menu exit || fail "server menu"
unset FRP_CTL_TEST_MENU
grep -q 'Data Relay Link: 1.4.0-dev' "$WORKDIR/server-menu.out" || fail "server menu identity"
grep -q 'Role: DRLink Server' "$WORKDIR/server-menu.out" || fail "server menu role"
grep -qE '[0-9]+\) Managed Hosts' "$WORKDIR/server-menu.out" || fail "server menu managed hosts"
grep -qE '[0-9]+\) Internet Access' "$WORKDIR/server-menu.out" || fail "server menu internet access"
! grep -qE '[0-9]+\) Clients' "$WORKDIR/server-menu.out" || fail "server menu clients leak"
pass "FRPCTL_MENU_IDENTITY_PARITY"

# Persistent client REPL.
export FRP_CLIENT_TEST_ROOT="$CLIENT"
run_repl "$CLIENT" "$WORKDIR/client-repl.out" "show status" help "system version" exit   || fail "client repl"
grep -q 'Data Relay Link: 1.4.0-dev' "$WORKDIR/client-repl.out" || fail "client repl identity"
grep -q 'Role: Agent Host' "$WORKDIR/client-repl.out" || fail "client repl role"
grep -q 'Remote Services' "$WORKDIR/client-repl.out" || fail "client repl status"
[[ "$(prompt_count "$WORKDIR/client-repl.out")" -ge 3 ]] || fail "client repl persistence"
# Unknown/obsolete command must not terminate the REPL.
run_repl "$CLIENT" "$WORKDIR/client-recovery.out" status "show status" exit   || fail "client recovery repl"
grep -qi 'unknown command: status' "$WORKDIR/client-recovery.out" || fail "obsolete root rejection"
grep -q 'Remote Services' "$WORKDIR/client-recovery.out" || fail "repl did not recover after obsolete root"
[[ "$(prompt_count "$WORKDIR/client-recovery.out")" -ge 3 ]] || fail "repl recovery prompts"
pass "FRPCTL_REPL_RECOVERY"

# Unknown help topic is non-zero but REPL remains usable.
unset FRP_CLIENT_TEST_ROOT
run_repl "$SERVER" "$WORKDIR/help-recovery.out" "help clients" "help managed-hosts" exit   || fail "help recovery repl"
grep -q 'Unknown help topic: clients' "$WORKDIR/help-recovery.out" || fail "unknown help topic"
grep -q 'Command failed with exit code 2.' "$WORKDIR/help-recovery.out" || fail "unknown help rc"
grep -q 'Managed Hosts' "$WORKDIR/help-recovery.out" || fail "canonical help after failure"
pass "FRPCTL_HELP_EXIT_STATUS"

# Context discovery is catalog-driven.
run_repl "$SERVER" "$WORKDIR/context.out" "?" "show ?" "set ?" "system ?" exit   || fail "context repl"
grep -q 'managed-hosts' "$WORKDIR/context.out" || fail "show discovery managed-hosts"
grep -q 'managed-host-group' "$WORKDIR/context.out" || fail "group discovery"
grep -q 'network-object' "$WORKDIR/context.out" || fail "set discovery network-object"
grep -q 'update' "$WORKDIR/context.out" || fail "system discovery update"
! grep -qE '^[[:space:]]*clients([[:space:]]|$)' "$WORKDIR/context.out" || fail "context clients leak"
pass "FRPCTL_CONTEXT_DISCOVERY"
# ---------------------------------------------------------------------------
# Safety: no shell execution, no persistent history, no-TTY behavior
# ---------------------------------------------------------------------------
CANARY="$WORKDIR/canary.txt"
run_repl "$SERVER" "$WORKDIR/noshell.out"   '!ls' shell exec bash "/bin/touch ${CANARY}" exit || fail "noshell repl"
grep -q 'arbitrary shell execution is not allowed' "$WORKDIR/noshell.out" || fail "shell rejection"
[[ ! -e "$CANARY" ]] || fail "shell canary created"
if grep -nE '(^|[[:space:]])eval |bash -c |sh -c |system\(' "$ROOT/tools/frpctl"; then
  fail "unsafe command dispatch"
fi
pass "NO_ARBITRARY_SHELL_EXECUTION"

[[ ! -f "$HOME/.frpctl_history" ]] || fail "frpctl history persisted"
[[ ! -f "$HOME/.bash_history" ]] || fail "bash history persisted"
grep -q 'unset HISTFILE' "$ROOT/tools/frpctl" || fail "HISTFILE not disabled"
! grep -qE 'history -[aw]' "$ROOT/tools/frpctl" || fail "history persistence command"
pass "NO_PERSISTENT_HISTORY"

unset FRP_CTL_TEST_INPUT
export FRP_CTL_TEST_ROOT="$CLIENT"
export FRP_CLIENT_TEST_ROOT="$CLIENT"
set +e
"$CTL" </dev/null >"$WORKDIR/notty.out" 2>"$WORKDIR/notty.err"
notty_rc=$?
set -e
[[ "$notty_rc" -ne 0 ]] || fail "no-tty interactive succeeded"
grep -q 'requires a TTY' "$WORKDIR/notty.err" || fail "no-tty message"
"$CTL" show status </dev/null >"$WORKDIR/notty-status.out"
grep -q 'Remote Services' "$WORKDIR/notty-status.out" || fail "no-tty direct command"
pass "FRPCTL_NO_TTY"
# Metacharacters never become shell syntax.
unset FRP_CLIENT_TEST_ROOT
export FRP_CTL_TEST_ROOT="$SERVER"
run_repl "$SERVER" "$WORKDIR/meta.out"   'show managed-hosts *'   'show managed-hosts $(whoami)'   "show status"   exit || fail "meta repl"
grep -qiE 'metacharacter|could not parse' "$WORKDIR/meta.out" || fail "meta syntax not rejected"
grep -q 'DRLink Server' "$WORKDIR/meta.out" || fail "repl failed after meta rejection"
pass "SAFE_TOKENIZER"

# Public roots are exactly the canonical action-first roots.
python3 - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "lib"))
import frp_cli_catalog as c
import frp_ctl_grammar as g

for role in ("server", "client", "both"):
    roots = set(g.canonical_verbs(role))
    assert roots <= {"show", "set", "unset", "test", "system", "menu", "help", "exit"}, (role, roots)
    assert "show" in roots and "system" in roots

rows = json.loads((root / "lib/frp_cli_final_commands.json").read_text())
assert sum(len(r.get("aliases") or []) for r in rows) == 0
assert not [r for r in rows if r.get("hidden")]

for tokens in (
    ["status"], ["update", "engine"], ["clients"], ["services"],
    ["revoke", "client", "x"], ["create", "enrollment"],
    ["show", "groups"], ["show", "fixed-tcp"], ["show", "access-log"],
):
    result = g.match(tokens, "server")
    assert result.get("status") != "ok", (tokens, result)

stale_recovery = (
    "set client",
    "unset client",
    "show clients",
    "published-service",
    "service-preset",
    "set fixed-tcp",
    "client-groups",
    "system services discard",
    "create zero-touch",
)
for root_token in (
    "create", "add", "remove", "enable", "disable", "delete",
    "revoke", "release", "egress", "client", "service", "group", "discard",
):
    message = g.context_help([root_token], "server", names=[], clients=[])
    for stale in stale_recovery:
        assert stale not in message, (root_token, stale, message)
PY
pass "FRPCTL_GREENFIELD_SURFACE"

git -C "$ROOT" diff --check -- tools/frpctl lib/frp_ctl_grammar.py lib/frp_cli_catalog.py tests/test-frpctl.sh

echo "FRPCTL_TESTS=PASS"
