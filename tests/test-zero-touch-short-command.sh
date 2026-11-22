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
handle='A'*22
assert len(zt.short_url_command('bootstrap.example.test',handle))<=200
try:
    zt.short_url_command('bootstrap.example.test','bt1.'+'a'*16+'.'+'b'*64)
    raise AssertionError('accepted raw ticket in public /i/ URL')
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
python3 "$ROOT/tools/frp-create-client" --one-line --client-name short-zt --note 'pkg' \
  >"$OUT" || { cat "$OUT"; fail "create one-line"; }
grep -q 'Zero-touch Agent command' "$OUT" || fail "header"
grep -q 'https://bootstrap.example.test/i/' "$OUT" || fail "short URL missing"
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
FRP_BOOTSTRAP_TICKET="bt1.$(printf 'b%.0s' {1..16}).$(printf 'c%.0s' {1..64})"
FRP_ZERO_TOUCH=1
export FRP_ALLOCATOR_URL FRP_ALLOCATOR_CA_SHA256 FRP_BOOTSTRAP_TICKET FRP_ZERO_TOUCH
frp_zero_touch_require_inputs || fail 'direct bootstrap environment rejected'
pass 'ZERO_TOUCH_DIRECT_ENV'
echo "ZERO_TOUCH_SHORT_COMMAND_TEST=PASS"
