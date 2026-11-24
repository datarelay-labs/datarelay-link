#!/usr/bin/env bash
# Zero-Touch short-handle launcher and direct environment.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

python3 - "$ROOT/lib/frp_zero_touch.py" <<'PYCODE'
import importlib.util,sys
spec=importlib.util.spec_from_file_location('zt',sys.argv[1])
zt=importlib.util.module_from_spec(spec);spec.loader.exec_module(zt)
locator='A3xK9m'
assert zt.render_entry_command('bootstrap.example.test',locator,'linux')=='curl -kfsS https://bootstrap.example.test/A3xK9m|sudo bash'
for bad in ('A'*22,'bt1.'+'a'*16+'.'+'b'*64):
    try:
        zt.render_entry_command('bootstrap.example.test',bad,'linux')
        raise AssertionError('accepted credential as locator')
    except ValueError:
        pass
PYCODE
pass 'ZERO_TOUCH_SHORT_HANDLE_ONLY'
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
TREE="$WORKDIR/tree"
mkdir -p "$TREE/etc/drlink/pki" "$TREE/var/lib/drlink/enrollments" \
  "$TREE/var/lib/drlink/bootstrap"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$TREE/etc/drlink/pki/ca.key" \
  -out "$TREE/etc/drlink/pki/ca.crt" \
  -days 1 -subj "/CN=frp-test-ca" >/dev/null 2>&1 \
  || fail "openssl ca"

python3 - "$TREE/etc/drlink/config.json" "$TREE" <<'PY'
import json, sys
from pathlib import Path
tree = Path(sys.argv[2])
cfg = {
  "public_ip": "203.0.113.10",
  "control_port": 443,
  "frp_control_public_port": 443,
  "port_start": 6000,
  "port_end": 6098,
  "listen_port": 6099,
  "allocator_public_url": "https://203.0.113.10/enroll",
  "client_installer_url": "https://203.0.113.10/artifacts/agent/bootstrap-client.sh",
  "windows_client_installer_url": "https://203.0.113.10/artifacts/agent/bootstrap-client.ps1",
  "tls_ca_cert": str(tree / "etc/drlink/pki/ca.crt"),
  "enrollments_dir": str(tree / "var/lib/drlink/enrollments"),
  "bootstrap_dir": str(tree / "var/lib/drlink/bootstrap"),
  "registry_file": str(tree / "var/lib/drlink/registry.json"),
  "bootstrap_hostname": "bootstrap.example.test",
}
Path(sys.argv[1]).write_text(json.dumps(cfg, indent=2) + "\n")
(tree / "var/lib/drlink/registry.json").write_text(
  json.dumps({"schema_version": 2, "clients": {}, "reserved": []}) + "\n"
)
PY

export FRP_DEPLOY_TEST_ROOT="$TREE"
OUT="$WORKDIR/one-line.out"
# The retired long command is forbidden: do not resurrect a bypass.
if python3 "$ROOT/tools/frp-create-client" --one-line --long-bootstrap \
    --client-name retired-zt >"$WORKDIR/retired.out" 2>&1; then
  fail "retired --long-bootstrap unexpectedly accepted"
fi
grep -q 'unrecognized arguments: --long-bootstrap' "$WORKDIR/retired.out" \
  || fail "retired mode did not fail closed"
# Current product uses only compact qualified bootstrap.
python3 "$ROOT/tools/frp-create-client" --one-line --client-name short-zt --note 'pkg' \
  >"$OUT" || { cat "$OUT"; fail "create one-line"; }
grep -q 'Zero-touch Agent command' "$OUT" || fail "header"
grep -Eq '^curl -kfsS https://bootstrap\.example\.test/[A-Za-z0-9_-]{6}\|sudo bash$' "$OUT" || fail "short URL missing"
if grep -q 'zt1\.' "$OUT"; then fail "legacy package emitted"; fi
if grep -qiE 'curl -fsSL --insecure .*/bootstrap-client|curl -k .*/bootstrap-client' "$OUT"; then
  fail "insecure TLS on installer fetch"
fi
if grep -q 'FRP_BOOTSTRAP_TICKET=' "$OUT"; then
  fail "legacy env block still preferred"
fi
pass "ZERO_TOUCH_SHORT_COMMAND_SHAPE"

# shellcheck source=/dev/null
source "$ROOT/lib/frp-common.sh"
# shellcheck source=/dev/null
source "$ROOT/lib/frp-client-common.sh"
FRP_ALLOCATOR_URL='https://203.0.113.10/enroll'
FRP_ALLOCATOR_CA_SHA256="$(printf 'a%.0s' {1..64})"
FRP_BOOTSTRAP_LOCATOR="A3xK9m"
FRP_ZERO_TOUCH=1
export FRP_ALLOCATOR_URL FRP_ALLOCATOR_CA_SHA256 FRP_BOOTSTRAP_LOCATOR FRP_ZERO_TOUCH
frp_zero_touch_require_inputs || fail 'direct bootstrap environment rejected'
pass 'ZERO_TOUCH_DIRECT_ENV'
echo "ZERO_TOUCH_SHORT_COMMAND_TEST=PASS"
