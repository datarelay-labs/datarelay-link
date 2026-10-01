#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

python3 - "$ROOT/release-manifest.json" <<'PY' || fail "supported_frp_versions"
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
pin = data["supported_frp_versions"]["0.71.0"]
assert pin["status"] == "tested"
assert pin["websocket_path"] == "/~!frp"
assert len(pin["amd64_sha256"]) == 64
PY
pass "COMPAT_MANIFEST_PIN"

if "$ROOT/scripts/bump-frp-version.sh" 0.99.0 >/tmp/frp-bump.out 2>/tmp/frp-bump.err; then
  fail "bump without --apply succeeded"
fi
grep -q 'without --apply' /tmp/frp-bump.err || fail "bump refusal message"
pass "BUMP_REQUIRES_APPLY"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
export FRP_COMPAT_STAGE="$STAGE"
export FRP_COMPAT_OFFLINE=1
export FRP_COMPAT_RUN_ID=wsfail
printf 'package net\nconst FrpWebsocketPath = "/wrong"\n' >"$STAGE/websocket.go"
if "$ROOT/scripts/check-frp-compatibility.sh" 0.71.0 >/tmp/frp-ws.out 2>/tmp/frp-ws.err; then
  fail "wrong websocket path should fail"
fi
grep -q 'BREAKING_WEBSOCKET_PATH=FAIL' /tmp/frp-ws.out /tmp/frp-ws.err || fail "websocket fail marker"
[[ ! -f "$STAGE/report.status" ]] || fail "PASS report after websocket failure"
pass "WEBSOCKET_PATH_GATE"

# Correct websocket alone is insufficient: archive shortcuts are rejected.
printf 'package net\nconst FrpWebsocketPath = "/~!frp"\n' >"$STAGE/websocket.go"
export FRP_COMPAT_RUN_ID=wsonly
export FRP_COMPAT_SKIP_ARCHIVES=1
set +e
"$ROOT/scripts/check-frp-compatibility.sh" 0.71.0 >/tmp/frp-ws-ok.out 2>/tmp/frp-ws-skip.err
skip_rc=$?
set -e
[[ "$skip_rc" -ne 0 ]] || fail "SKIP_ARCHIVES must not produce PASS"
grep -q 'WEBSOCKET_PATH_UNCHANGED=PASS' /tmp/frp-ws-ok.out || fail "websocket pass marker missing"
grep -qi 'FRP_COMPAT_SKIP_ARCHIVES\|no longer allowed' /tmp/frp-ws-skip.err || fail "skip archives rejected"
pass "WEBSOCKET_PATH_PINNED"
pass "SKIP_ARCHIVES_REJECTED"
unset FRP_COMPAT_SKIP_ARCHIVES

python3 -m py_compile "$ROOT/scripts/check-frp-half-close.py" || fail "half-close probe parse"
grep -q 'shutdown(socket.SHUT_WR)' "$ROOT/scripts/check-frp-half-close.py" \
  || fail "half-close probe does not perform SHUT_WR"
grep -q 'FRP_HALF_CLOSE=PASS' "$ROOT/scripts/check-frp-half-close.py" \
  || fail "half-close probe PASS marker missing"
grep -q 'check-frp-half-close.py' "$ROOT/scripts/check-frp-compatibility.sh" \
  || fail "compatibility gate does not invoke half-close probe"
grep -q 'tcp_half_close.*PASS' "$ROOT/scripts/check-frp-compatibility.sh" \
  || fail "compatibility report missing half-close capability"
grep -q 'api.github.com/repos/fatedier/frp/releases/tags' "$ROOT/scripts/check-frp-compatibility.sh" \
  || fail "GitHub release asset digest fallback missing"
grep -q 'GITHUB_RELEASE_ASSET_DIGESTS=PASS' "$ROOT/scripts/check-frp-compatibility.sh" \
  || fail "release asset digest validation marker missing"
pass "TCP_HALF_CLOSE_REQUIRED"
pass "RELEASE_ASSET_DIGEST_FALLBACK"

[[ -f "$ROOT/docs/FRP_UPGRADE.md" ]] || fail "FRP_UPGRADE.md missing"
grep -q 'never installs GitHub' "$ROOT/docs/FRP_UPGRADE.md" || fail "upgrade policy"
[[ -f "$ROOT/docs/OCI_ACCEPTANCE.md" ]] || fail "OCI plan missing"
pass "UPGRADE_DOCS"

export FRP_UPSTREAM_VERSION_OVERRIDE="0.99.0"
"$ROOT/tools/frp-upstream" >/tmp/frp-up.out
grep -q 'Tested FRP    : 0.71.0' /tmp/frp-up.out || fail "tested version"
grep -q 'Upstream      : 0.99.0' /tmp/frp-up.out || fail "upstream override"
grep -q 'No update was performed' /tmp/frp-up.out || fail "no install"
grep -q 'sudo drlink system update engine' /tmp/frp-up.out || fail "canonical engine update guidance"
! grep -q 'sudo drlink frp-update' /tmp/frp-up.out || fail "legacy engine update guidance"
pass "UPSTREAM_CHECK_READONLY"

echo "FRP_COMPATIBILITY_TEST=PASS"
