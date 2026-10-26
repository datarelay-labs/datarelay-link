#!/usr/bin/env bash
# Connect ChatGPT to the access.xdr.ooo-hosted Native MCP through the existing
# publicly trusted mcp.xdr.ooo TLS endpoint. Does not install DRLink Agent,
# request an Enrollment Code, alter FRP TCP/443, or replace primary MCP /mcp.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
SHA="$(git rev-parse HEAD)"
RELAY_USER="aella@mcp.link.datarelay.run"
RELAY_TOOL="/home/aella/operator-native-mcp-relay.py"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile=/home/aella/.ssh/known_hosts
  -i /home/aella/.ssh/mcp_link_ed25519)

if [[ "${1:---check}" == "--apply" ]] && [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "ERROR: Candidate worktree has uncommitted changes. No deployment." >&2
  exit 1
fi
if [[ "$SHA" != "$(git rev-parse origin/feat/v240-server-native-mcp-20261026)" ]]; then
  echo "ERROR: Candidate HEAD does not match pushed draft branch." >&2
  exit 1
fi

echo "Direct ChatGPT MCP: https://mcp.xdr.ooo/access/mcp"
echo "Candidate exact SHA: $SHA"
echo "Public proxy: existing CA-trusted mcp.xdr.ooo with scoped /access paths"
echo "Target backend: access.xdr.ooo Native MCP 127.0.0.1:16106"
echo "Existing /mcp endpoint, DRLink Server and FRP 443: preserved"
echo "Developer local execution: remains disabled"
echo

if [[ "${1:---check}" == "--check" ]]; then
  # The root-owned upgrade ledger is intentionally not readable by aella.
  # Inspect only the public local listener; privileged upgrade preflight is
  # performed separately by sudo inside --apply.
  systemctl is-active --quiet drlink-mcp-native-preview.service
  response="$(curl -sS --max-time 6 -X POST -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' -o /dev/null -w '%{http_code}' http://127.0.0.1:16106/mcp)"
  if [[ "$response" != "401" ]]; then
    echo "ERROR: Native MCP local authentication boundary is not 401 (got $response)" >&2
    exit 1
  fi
  "${SSH[@]}" "$RELAY_USER" "test -f '$RELAY_TOOL' && ss -lnt | grep -q '127.0.0.1:16107'"
  echo "DIRECT_NATIVE_MCP_NONROOT_CHECK=PASS"
  echo "Run: bash tools/activate-native-mcp.sh --apply"
  exit 0
fi
if [[ "${1:-}" != "--apply" ]]; then
  echo "Usage: bash tools/activate-native-mcp.sh --check|--apply" >&2
  exit 2
fi
if [[ ! -t 0 ]]; then
  echo "ERROR: An interactive operator terminal is required." >&2
  exit 2
fi
read -r -p "Type APPLY to activate access.xdr.ooo Native MCP publicly: " consent
if [[ "$consent" != "APPLY" ]]; then
  echo "Cancelled without changes."
  exit 2
fi

# All root actions are explicit and run by the human-authorized SSH operator.
sudo /usr/bin/python3 tools/operator-native-mcp-upgrade.py --preflight --expected-head "$SHA"
sudo /usr/bin/python3 tools/operator-native-mcp-upgrade.py --apply --expected-head "$SHA"
sudo /usr/bin/python3 tools/operator-native-mcp-upgrade.py --verify

"${SSH[@]}" "$RELAY_USER" \
  "sudo /usr/bin/python3 '$RELAY_TOOL' --preflight && sudo /usr/bin/python3 '$RELAY_TOOL' --apply && sudo /usr/bin/python3 '$RELAY_TOOL' --verify"

python3 tools/check-native-mcp-public.py

echo
echo "ACCESS_NATIVE_MCP_PUBLIC_READY=PASS"
echo "ChatGPT custom MCP URL: https://mcp.xdr.ooo/access/mcp"
echo "Next: connect via ChatGPT Plugins > Add custom MCP server > OAuth."
echo "Explicit AI Identity/AI Access consent is still required for tool execution."
