#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/frp-common.sh
. "$ROOT/lib/frp-common.sh"
# shellcheck source=../lib/frp-server-upgrade.sh
. "$ROOT/lib/frp-server-upgrade.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL $*" >&2; exit 1; }
pass() { echo "PASS $*"; }

# Legacy paths migrate into canonical Data Relay Link roots.
TREE="$WORK/legacy"
mkdir -p \
  "$TREE/etc/frp-auto-deploy/pki" \
  "$TREE/var/lib/frp-auto-deploy" \
  "$TREE/usr/local/lib/frp-auto-deploy" \
  "$TREE/usr/local/bin" \
  "$TREE/usr/local/sbin" \
  "$TREE/etc/systemd/system"
printf 'cfg\n' >"$TREE/etc/frp-auto-deploy/config.json"
printf 'reg\n' >"$TREE/var/lib/frp-auto-deploy/registry.json"
printf 'lib\n' >"$TREE/usr/local/lib/frp-auto-deploy/frp-common.sh"
cat >"$TREE/etc/systemd/system/frps.service" <<'EOF'
[Unit]
Description=FRP Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
printf 'old-cli\n' >"$TREE/usr/local/bin/frpctl"
printf '#!/bin/bash\necho drlink\n' >"$TREE/usr/local/bin/drlink"
chmod 0755 "$TREE/usr/local/bin/drlink"
printf 'new-unit\n' >"$TREE/etc/systemd/system/drlink-server.service"

FRP_SERVER_TEST_ROOT="$TREE" frp_migrate_legacy_product_paths || fail "path migrate"
[[ -f "$TREE/etc/drlink/config.json" ]] || fail "config not migrated"
[[ -f "$TREE/var/lib/drlink/registry.json" ]] || fail "registry not migrated"
[[ -f "$TREE/usr/local/lib/drlink/frp-common.sh" ]] || fail "lib not migrated"
[[ ! -e "$TREE/etc/frp-auto-deploy" ]] || fail "legacy etc remains"
pass "LEGACY_PATH_MIGRATE"

FRP_SERVER_TEST_ROOT="$TREE" frp_migrate_legacy_systemd_units || fail "unit migrate"
[[ -f "$TREE/etc/systemd/system/drlink-server.service" ]] || fail "new unit missing"
[[ ! -f "$TREE/etc/systemd/system/frps.service" ]] || fail "old unit remains"
[[ ! -e "$TREE/usr/local/bin/frpctl" ]] || fail "frpctl still on PATH"
[[ -x "$TREE/usr/local/bin/drlink" ]] || fail "drlink missing"
pass "LEGACY_UNIT_AND_CLI_RETIRE"

# Dual-role: frpc.service migrates to drlink-client when client-state exists.
DUAL="$WORK/dual"
mkdir -p "$DUAL/etc/systemd/system" "$DUAL/etc/frp" "$DUAL/usr/local/bin"
cat >"$DUAL/etc/systemd/system/frpc.service" <<'EOF'
[Unit]
Description=FRP Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frpc -c /etc/frp/frpc.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
printf '{}\n' >"$DUAL/etc/frp/client-state.json"
printf '#!/bin/bash\necho drlink\n' >"$DUAL/usr/local/bin/drlink"
chmod 0755 "$DUAL/usr/local/bin/drlink"
FRP_SERVER_SOURCE="$ROOT" FRP_SERVER_TEST_ROOT="$DUAL" frp_migrate_legacy_systemd_units || fail "dual migrate"
[[ -f "$DUAL/etc/systemd/system/drlink-client.service" ]] || fail "drlink-client not created"
[[ ! -f "$DUAL/etc/systemd/system/frpc.service" ]] || fail "frpc remains"
pass "LEGACY_DUAL_ROLE_CLIENT_UNIT"

# Unrelated administrator frpc.service must be preserved.
ADMIN="$WORK/admin"
mkdir -p "$ADMIN/etc/systemd/system" "$ADMIN/usr/local/bin"
cat >"$ADMIN/etc/systemd/system/frpc.service" <<'EOF'
[Unit]
Description=Company Custom FRP Tunnel
After=network-online.target

[Service]
Type=simple
ExecStart=/opt/custom/frpc -c /opt/custom/frpc.ini
Restart=always

[Install]
WantedBy=multi-user.target
EOF
printf 'new\n' >"$ADMIN/etc/systemd/system/drlink-client.service"
printf '#!/bin/bash\necho drlink\n' >"$ADMIN/usr/local/bin/drlink"
chmod 0755 "$ADMIN/usr/local/bin/drlink"
FRP_SERVER_TEST_ROOT="$ADMIN" frp_migrate_legacy_systemd_units || fail "admin migrate"
[[ -f "$ADMIN/etc/systemd/system/frpc.service" ]] || fail "admin frpc removed"
[[ -f "$ADMIN/etc/systemd/system/drlink-client.service" ]] || fail "canonical missing"
pass "UNRELATED_ADMIN_FRPC_PRESERVED"

# Unrelated administrator frps.service must be preserved when drlink-server exists.
ADMIN_S="$WORK/admin-server"
mkdir -p "$ADMIN_S/etc/systemd/system" "$ADMIN_S/usr/local/bin"
cat >"$ADMIN_S/etc/systemd/system/frps.service" <<'EOF'
[Unit]
Description=Company Custom FRP Server
After=network-online.target

[Service]
Type=simple
ExecStart=/opt/custom/frps -c /opt/custom/frps.ini
Restart=always

[Install]
WantedBy=multi-user.target
EOF
printf 'new\n' >"$ADMIN_S/etc/systemd/system/drlink-server.service"
printf '#!/bin/bash\necho drlink\n' >"$ADMIN_S/usr/local/bin/drlink"
chmod 0755 "$ADMIN_S/usr/local/bin/drlink"
FRP_SERVER_TEST_ROOT="$ADMIN_S" frp_migrate_legacy_systemd_units 2>"$WORK/admin-s.err" \
  || fail "admin server migrate"
[[ -f "$ADMIN_S/etc/systemd/system/frps.service" ]] || fail "admin frps removed"
[[ -f "$ADMIN_S/etc/systemd/system/drlink-server.service" ]] || fail "canonical server missing"
grep -q 'non-product frps.service' "$WORK/admin-s.err" || fail "missing admin frps warn"
# Ownership fingerprints for server legacy unit
PROD_S="$WORK/prod-frps.service"
cat >"$PROD_S" <<'EOF'
[Unit]
Description=Data Relay Link Server (legacy unit name; use drlink-server)

[Service]
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
EOF
frp_legacy_server_unit_is_product_owned "$PROD_S" || fail "product frps not owned"
frp_legacy_server_unit_is_product_owned "$ADMIN_S/etc/systemd/system/frps.service" \
  && fail "admin frps incorrectly owned"
pass "UNRELATED_ADMIN_FRPS_PRESERVED"

# Prior-stable server cutover must preserve frontend enablement by deployment mode.
# The helper is exercised in installer test mode so no host systemd is touched.
frp_server_fs() { printf '%s' "${FRP_SERVER_TEST_ROOT:-}$1"; }
frp_server_skip_systemd() { return 0; }
frp_server_test_mode() { return 0; }
frp_legacy_server_unit_is_product_owned() { return 0; }

run_frontend_cutover_fixture() {
  local tree="$1" mode="$2"
  mkdir -p "$tree/etc/systemd/system" "$tree/etc/drlink" "$tree/var/lib/drlink"
  printf '{"deployment_mode":"%s"}\n' "$mode" >"$tree/etc/drlink/config.json"
  printf 'legacy\n' >"$tree/etc/systemd/system/frp-frontend.service"
  printf 'canonical\n' >"$tree/etc/systemd/system/drlink-frontend.service"
  : >"$tree/actions.log"
  frp_server_record_action() { printf '%s\n' "$1" >>"$tree/actions.log"; }
  FRP_SERVER_TEST_ROOT="$tree" frp_server_upgrade_retire_legacy_server_units \
    || fail "frontend cutover ${mode}"
}

CUT_DIRECT="$WORK/cutover-direct"
run_frontend_cutover_fixture "$CUT_DIRECT" direct
grep -qx 'disable --now frp-frontend' "$CUT_DIRECT/actions.log" \
  || fail "direct legacy frontend not disabled"
grep -qx 'disable --now drlink-frontend' "$CUT_DIRECT/actions.log" \
  || fail "direct canonical frontend not kept disabled"
if grep -qx 'enable drlink-frontend' "$CUT_DIRECT/actions.log"; then
  fail "direct canonical frontend incorrectly enabled"
fi
pass "LEGACY_CUTOVER_DIRECT_FRONTEND_DISABLED"

CUT_443="$WORK/cutover-single443"
run_frontend_cutover_fixture "$CUT_443" single443
grep -qx 'disable --now frp-frontend' "$CUT_443/actions.log" \
  || fail "single443 legacy frontend not disabled"
grep -qx 'enable drlink-frontend' "$CUT_443/actions.log" \
  || fail "single443 canonical frontend not enabled"
if grep -qx 'disable --now drlink-frontend' "$CUT_443/actions.log"; then
  fail "single443 canonical frontend incorrectly disabled"
fi
pass "LEGACY_CUTOVER_SINGLE443_FRONTEND_ENABLED"

# Clean install layout: drlink on PATH, frpctl only as internal backend.
CLEAN="$WORK/clean"
mkdir -p "$CLEAN/usr/local/bin" "$CLEAN/usr/local/lib/drlink"
install -m 0755 "$ROOT/tools/frpctl" "$CLEAN/usr/local/lib/drlink/frpctl"
install -m 0755 "$ROOT/tools/drlink" "$CLEAN/usr/local/bin/drlink"
[[ -x "$CLEAN/usr/local/bin/drlink" ]] || fail "clean drlink"
[[ ! -e "$CLEAN/usr/local/bin/frpctl" ]] || fail "clean has PATH frpctl"
help_out="$(FRP_CTL_TEST_ROOT="$CLEAN/root-missing" PATH="$CLEAN/usr/local/bin:$PATH" \
  "$CLEAN/usr/local/bin/drlink" --help 2>&1 || true)"
# Backend resolves via absolute /usr/local/lib/drlink only when installed system-wide.
# For harness, invoke with backend beside wrapper by placing both under a prefix.
PREFIX="$WORK/prefix"
mkdir -p "$PREFIX/bin" "$PREFIX/lib"
install -m 0755 "$ROOT/tools/frpctl" "$PREFIX/lib/frpctl"
# Wrapper looks for sibling tools/frpctl or /usr/local/lib/drlink/frpctl.
# Emulate source-tree layout for this assertion:
install -m 0755 "$ROOT/tools/drlink" "$PREFIX/bin/drlink"
install -m 0755 "$ROOT/tools/frpctl" "$PREFIX/bin/../tools/frpctl" 2>/dev/null || true
mkdir -p "$PREFIX/tools"
install -m 0755 "$ROOT/tools/frpctl" "$PREFIX/tools/frpctl"
install -m 0755 "$ROOT/tools/drlink" "$PREFIX/tools/drlink"
out="$("$PREFIX/tools/drlink" --help)"
grep -q 'Usage: drlink' <<<"$out" || fail "drlink help"
grep -q 'Data Relay Link' <<<"$out" || fail "product name"
pass "CLEAN_INSTALL_DRLINK_ONLY"

TREE_CFG="$WORK/config-paths"
mkdir -p "$TREE_CFG/etc/frp-auto-deploy" "$TREE_CFG/var/lib/frp-auto-deploy" "$TREE_CFG/var/log/frp-auto-deploy" "$TREE_CFG/usr/local/lib/frp-auto-deploy"
cat >"$TREE_CFG/etc/frp-auto-deploy/config.json" <<'JSON'
{
  "enrollments_dir": "/var/lib/frp-auto-deploy/enrollments",
  "access_conn_log_file": "/var/log/frp-auto-deploy/access-conn.jsonl",
  "tls_ca_cert": "/etc/frp-auto-deploy/pki/ca.crt",
  "nested": {"paths": ["/usr/local/lib/frp-auto-deploy/helper.py", "/run/frp-auto-deploy/x"]},
  "client_installer_url": "https://example.invalid/xdr-labs/frp-auto-deploy/v2.3.0/bootstrap.sh"
}
JSON
FRP_SERVER_TEST_ROOT="$TREE_CFG" frp_migrate_legacy_product_paths >/dev/null
python3 - "$TREE_CFG/etc/drlink/config.json" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
assert d["enrollments_dir"] == "/var/lib/drlink/enrollments"
assert d["access_conn_log_file"] == "/var/log/drlink/access-conn.jsonl"
assert d["tls_ca_cert"] == "/etc/drlink/pki/ca.crt"
assert d["nested"]["paths"] == ["/usr/local/lib/drlink/helper.py", "/run/drlink/x"]
assert "frp-auto-deploy" in d["client_installer_url"]
PY
echo "PASS LEGACY_CONFIG_PATH_CANONICALIZATION"

echo "LEGACY_IDENTITY_MIGRATION_TEST=PASS"
