#!/usr/bin/env bash
# Static contract: Real E2E operator workflows must use canonical drlink.
# Fixture/evidence reads may still mention internal paths; this gate only
# rejects direct management/dispatch of backend tools in run-real-e2e.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
E2E="$ROOT/tests/run-real-e2e.sh"
fail() { echo "FAIL $1" >&2; exit 1; }
pass() { echo "PASS $1"; }

[[ -f "$E2E" ]] || fail "missing run-real-e2e.sh"

# Forbidden: direct backend management used as the operator path.
if grep -nE \
  '/usr/local/lib/drlink/frp-create-client|/usr/local/bin/frp-client |/usr/local/lib/drlink/frp-server-set|frp-client add-service|frp-client set-service|frp-client enable-service|frp-client disable-service|frp-client apply-pending|frp-client sync' \
  "$E2E" | grep -v '^#' >/dev/null; then
  grep -nE \
    '/usr/local/lib/drlink/frp-create-client|/usr/local/bin/frp-client |/usr/local/lib/drlink/frp-server-set|frp-client add-service|frp-client set-service|frp-client enable-service|frp-client disable-service|frp-client apply-pending|frp-client sync' \
    "$E2E" >&2 || true
  fail "Real E2E still invokes backend tools for operator workflows"
fi
pass "NO_DIRECT_BACKEND_OPERATOR_CALLS"

# Forbidden: drlink failure falling through to backend still counts as PASS.
if grep -nE \
  'drlink[^|]*\|\|[[:space:]]*(sudo[[:space:]]+)?(/usr/local/(bin|lib/drlink)/)?frp-(create-client|client|server-set|release|set-)' \
  "$E2E" >/dev/null; then
  grep -nE \
    'drlink[^|]*\|\|[[:space:]]*(sudo[[:space:]]+)?(/usr/local/(bin|lib/drlink)/)?frp-(create-client|client|server-set|release|set-)' \
    "$E2E" >&2 || true
  fail "Real E2E still has drlink||backend escape hatch"
fi
pass "NO_DRLINK_BACKEND_FALLBACK"

# Forbidden: direct config.json mutation for installer URL pinning.
if grep -nE "config\.json.*client_installer_url|c\['client_installer_url'\]|c\['windows_client_installer_url'\]" "$E2E" >/dev/null; then
  grep -nE "config\.json.*client_installer_url|c\['client_installer_url'\]|c\['windows_client_installer_url'\]" "$E2E" >&2 || true
  fail "Real E2E still patches config.json for installer URLs"
fi
pass "NO_DIRECT_INSTALLER_JSON_PATCH"

# Required: canonical installer pin + guided zero-touch via the public CLI.
grep -q "set server installer-url" "$E2E" || fail "missing canonical set server installer-url pin"
grep -q "set server windows-installer-url" "$E2E" || fail "missing canonical set server windows-installer-url pin"
grep -q 'drlink set client"' "$E2E" || fail "missing public set client onboarding"
grep -q "FRP_CTL_TEST_INPUT" "$E2E" || fail "zero-touch must use FRP_CTL_TEST_INPUT under sudo use_pty"
grep -q "base64" "$E2E" || fail "zero-touch TEST_INPUT must be base64-safe across remote shells"
# Guided answers must include the post-identity service-mode choice (SSH only).
grep -Fq '\"$note_text\" '\''1'\'' \"$TUNNEL_SSH_USER\"' "$E2E" \
  || grep -Fq "\"\$note_text\" '1' \"\$TUNNEL_SSH_USER\"" "$E2E" \
  || fail "zero-touch guided answers missing SSH-only step"
pass "CANONICAL_INSTALLER_AND_ZERO_TOUCH"

# Server installer URLs have one canonical public path; standalone compatibility
# spellings must not parse on the unreleased v2.4 surface.
python3 - "$ROOT" <<'PY' || fail "Server installer URL canonical grammar regression"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "lib"))
import frp_cli_catalog as c
import frp_ctl_grammar as g

url = "https://example.com/install-client.sh"
canonical = ["set", "server", "installer-url", url]
cmd = c.find(canonical, role="server")
if cmd is None or cmd["path"] != ("set", "server"):
    raise SystemExit("canonical catalog path missing: %r" % (cmd,))
matched = g.match(canonical, role="server")
if matched.get("status") != "ok" or matched.get("action") != "set_installer_url":
    raise SystemExit("canonical match failed: %r" % matched)

legacy = ["set", "installer-url", url]
if c.find(legacy, role="server") is not None:
    raise SystemExit("standalone installer-url remains in public catalog")
legacy_match = g.match(legacy, role="server")
if legacy_match.get("status") == "ok":
    raise SystemExit("standalone installer-url still executes: %r" % legacy_match)

server_unset = c.find(["unset", "server"], role="server")
server_unset_values = tuple((server_unset or {}).get("args", ({},))[0].get("complete") or ())
if "hostname" in server_unset_values:
    raise SystemExit("hostname compatibility spelling remains discoverable: %r" % (server_unset_values,))

for legacy_hostname in (
    ["unset", "server", "hostname"],
    ["set", "server", "hostname", "example.com"],
):
    legacy_hostname_match = g.match(legacy_hostname, role="server")
    if legacy_hostname_match.get("status") == "ok":
        raise SystemExit("legacy server hostname spelling still executes: %r" % legacy_hostname_match)
print("ok")
PY
pass "SERVER_INSTALLER_URL_SINGLE_CANONICAL_PATH"

echo "REAL_E2E_CANONICAL_CLI_CONTRACT=PASS"
