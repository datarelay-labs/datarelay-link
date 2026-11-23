#!/usr/bin/env bash
# Real installer reports an actual side-effect-free Zero-Touch preflight;
# never label the installed Server 'Zero-Touch ready' on DNS alone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d /tmp/drlink-zt-readiness.XXXXXX)"
trap 'rm -rf "$T"' EXIT
export FRP_SERVER_SOURCED=1
# shellcheck source=../install-server.sh
. "$ROOT/install-server.sh"
BASE_DIR="$T"
mkdir -p "$T/tools"
frp_server_test_mode() { [[ -n "${FRP_SERVER_TEST_ROOT:-}" ]]; }
export FRP_SERVER_TEST_ROOT="$T/isolated"
out="$(frp_report_zero_touch_readiness)"
[[ "$out" == *'NOT_CHECKED (isolated installation test)'* ]] || { echo "FAIL isolated readiness: $out"; exit 1; }
unset FRP_SERVER_TEST_ROOT
out="$(frp_report_zero_touch_readiness)"
[[ "$out" == *'NOT_READY (preflight tool missing)'* ]] || { echo "FAIL missing preflight: $out"; exit 1; }
cat > "$T/tools/frp-create-client" <<'PY'
import os,sys
assert sys.argv[1:] == ['--preflight-zero-touch','--platform','linux'],sys.argv
if os.getenv('DRLINK_MOCK_UNTRUSTED') == '1':
    print('ERROR: public TLS chain is untrusted; no enrollment ticket was issued')
    raise SystemExit(2)
print('Zero-Touch prerequisites verified; no ticket was issued.')
PY
out="$(frp_report_zero_touch_readiness)"
[[ "$out" == *'READY (read-only, no ticket issued)'* ]] || { echo "FAIL valid readiness: $out"; exit 1; }
export DRLINK_MOCK_UNTRUSTED=1
out="$(frp_report_zero_touch_readiness)"
[[ "$out" == *'NOT_READY (no ticket issued)'* ]] || { echo "FAIL untrusted TLS readiness: $out"; exit 1; }
[[ "$out" == *'public TLS chain is untrusted'* ]] || { echo "FAIL missing TLS diagnosis: $out"; exit 1; }
[[ "$out" == *'matching IP SAN'* ]] || { echo "FAIL missing private CA guidance: $out"; exit 1; }
unset DRLINK_MOCK_UNTRUSTED
! grep -q 'Zero-Touch.*READY' "$T/tools/frp-create-client"
# The status is read-only and never writes an enrollment or secret.
[[ ! -d "$T/var/lib/drlink/enrollments" ]]
echo 'ZERO_TOUCH_INSTALLER_TLS_READINESS=PASS'
