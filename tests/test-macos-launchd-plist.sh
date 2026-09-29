#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export FRP_TEST_UNAME_S=Darwin
export FRP_CLIENT_TEST_ROOT="$TMP/root"
export FRP_MACOS_STATE_ROOT="$TMP/state"
. "$ROOT/lib/frp-common.sh"

out="$TMP/rendered.plist"
frp_macos_render_plist "$out"
python3 - "$out" "$TMP/root$TMP/state" <<'PY'
import plistlib,sys
with open(sys.argv[1],"rb") as f: p=plistlib.load(f)
state=sys.argv[2]
assert p["Label"] == "com.datarelay.drlink.frpc"
# Pinned boot path: wrapper then frpc -c config (pre-start invalidation).
assert p["ProgramArguments"] == [
    state + "/lib/drlink-frpc-launch",
    state + "/bin/frpc",
    "-c",
    state + "/frpc.toml",
]
assert p["RunAtLoad"] is True
assert p["KeepAlive"]["SuccessfulExit"] is False
assert p["KeepAlive"]["NetworkState"] is True
assert p["StandardOutPath"] == state+"/logs/frpc.out.log"
assert "@" not in repr(p)
PY

# Wrapper itself must invalidate the live macOS Agent DB, then exec argv.
# Prove wrapper-driven root=None resolution (FRP_MACOS_STATE_ROOT), not a
# separate helper-only call + argv-only exec.
wrapper="$ROOT/client/drlink-frpc-launch"
[[ -x "$wrapper" ]] || { echo "ERROR: wrapper not executable"; exit 1; }

# Realistic macOS Agent layout selected by ControlPlane(None)/select_live_control_db.
mkdir -p "$FRP_MACOS_STATE_ROOT/state"
printf '%s\n' '{"client_id":"agent-boot-test"}' >"$FRP_MACOS_STATE_ROOT/client-state.json"
printf '%s\n' 'serverAddr = "127.0.0.1"' >"$FRP_MACOS_STATE_ROOT/frpc.toml"
: >"$FRP_MACOS_STATE_ROOT/client-identity.key"

PYTHONPATH="$ROOT/lib" python3 <<'PY'
from pathlib import Path
from drlink_control_plane import ControlPlane
import drlink_v24 as v24

# root=None must resolve through FRP_MACOS_STATE_ROOT markers.
plane = ControlPlane(None)
v24.ensure_v2_schema(plane.conn)
plane.conn.execute(
    "INSERT OR REPLACE INTO agent_remote_services"
    "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
    "pending_allocation, delete_pending, pool_class, reason, runtime_verified, updated_at) "
    "VALUES ('ssh-access', 'this-host', 'ssh', 1, 'HEALTHY', 'drlink.local', 6012, 0, 0, "
    "'normal', '', 1, '2026-09-18T00:00:00Z')"
)
plane.conn.commit()
db_file = Path(plane.db_file)
plane.close()
assert db_file.is_file(), db_file
assert str(db_file).endswith("state/drlink.db"), db_file
print("MACOS_BOOT_SEED=%s" % db_file)
PY

marker="$TMP/frpc-saw-state.txt"
fake_frpc="$TMP/fake-frpc"
cat >"$fake_frpc" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$ROOT/lib\${PYTHONPATH:+:\$PYTHONPATH}"
export FRP_MACOS_STATE_ROOT="$FRP_MACOS_STATE_ROOT"
python3 - "$marker" "\$@" <<'PY'
import sys
from drlink_control_plane import ControlPlane

marker = sys.argv[1]
argv = sys.argv[2:]
plane = ControlPlane(None)
row = plane.conn.execute(
    "SELECT runtime_verified, status FROM agent_remote_services WHERE name='ssh-access'"
).fetchone()
plane.close()
verified = int(row["runtime_verified"] or 0) if row else -1
status = str(row["status"] if row else "")
with open(marker, "w", encoding="utf-8") as fh:
    fh.write("verified=%s status=%s\n" % (verified, status))
if verified != 0:
    raise SystemExit("frpc started before wrapper cleared runtime_verified")
if status.upper() == "HEALTHY":
    raise SystemExit("frpc started while Agent status still HEALTHY")
print("FRPC_ARGV=%s" % " ".join(argv))
PY
EOF
chmod 755 "$fake_frpc"

# Install-layout: launcher lives beside lib modules (production /usr/local/lib/drlink).
install_lib="$TMP/install-lib"
mkdir -p "$install_lib"
cp -a "$wrapper" "$install_lib/drlink-frpc-launch"
chmod 755 "$install_lib/drlink-frpc-launch"
cp -a "$ROOT"/lib/*.py "$install_lib/"

out_exec="$(
  env -u FRP_DEPLOY_TEST_ROOT -u FRP_CTL_TEST_ROOT -u FRP_SERVER_TEST_ROOT -u DRLINK_TEST_ROOT \
    FRP_MACOS_STATE_ROOT="$FRP_MACOS_STATE_ROOT" \
    "$install_lib/drlink-frpc-launch" "$fake_frpc" -c "$TMP/frpc.toml"
)"
[[ "$out_exec" == "FRPC_ARGV=-c $TMP/frpc.toml" ]] || {
  echo "ERROR: wrapper did not exec frpc with pinned args: $out_exec" >&2
  exit 1
}
[[ -f "$marker" ]] || {
  echo "ERROR: fake frpc did not record pre-exec Agent DB state" >&2
  exit 1
}
grep -qx 'verified=0 status=DEGRADED' "$marker" || {
  echo "ERROR: wrapper did not demote macOS Agent DB before frpc: $(cat "$marker")" >&2
  exit 1
}
echo "MACOS_BOOT_WRAPPER_INVALIDATE=PASS"

# Packaging destinations must ship the wrapper explicitly.
. "$ROOT/lib/frp-client-common.sh"
frp_client_upgrade_destinations | grep -qx 'usr/local/lib/drlink/drlink-frpc-launch:0755:client/drlink-frpc-launch'

echo "MACOS_LAUNCHD_PLIST_TEST=PASS"
