#!/usr/bin/env bash
# Enable the dedicated mcp.link.xdr.ooo -> access.xdr.ooo Native MCP route.
# Assumes owner configured Cloudflare named Tunnel and public hostname for:
#   mcp.link.xdr.ooo -> http://127.0.0.1:16106
# This does NOT reinstall DRLink, change existing FRP TCP/443, or use another VM.
# The human owner enters the Cloudflare connector token ONLY into a hidden TTY.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
HOST=mcp.link.xdr.ooo
RESOURCE=https://mcp.link.xdr.ooo/mcp
DEV_PUBLIC_IPV4=221.139.249.111
HEAD_SHA="$(git rev-parse HEAD)"

# This is a nested hostname under xdr.ooo: basic Cloudflare Universal SSL
# does NOT automatically cover it. Never apply the Native OAuth service
# change until a trusted, hostname-matching public edge certificate exists.
edge_tls_check() {
  /usr/bin/python3 - <<'PY'
import socket, ssl, sys
host = "mcp.link.xdr.ooo"
try:
    with socket.create_connection((host, 443), timeout=7) as s:
        with ssl.create_default_context().wrap_socket(s, server_hostname=host) as tls:
            if not tls.version():
                raise ValueError("No negotiated TLS protocol")
except (OSError, ValueError, ssl.SSLError) as exc:
    print("CLOUDFLARE_EDGE_TLS=NOT_READY (%s)" % type(exc).__name__, file=sys.stderr)
    print("For nested mcp.link.xdr.ooo, configure Total TLS, an Advanced Certificate or a custom certificate in Cloudflare.", file=sys.stderr)
    raise SystemExit(1)
print("CLOUDFLARE_EDGE_TLS=PASS")
PY
}

if [[ "${1:---check}" == "--check" ]]; then
  echo "CHATGPT_NATIVE_MCP_URL=$RESOURCE"
  echo "SOURCE_HEAD=$HEAD_SHA"
  python3 tools/operator-native-mcp-domain.py --check
  python3 tools/operator-native-mcp-cloudflare.py --check
  dns="$(dig +short A "$HOST" | head -1 || true)"
  if [[ -z "$dns" || "$dns" == "$DEV_PUBLIC_IPV4" ]]; then
    echo "CLOUDFLARE_PUBLIC_HOSTNAME=NOT_YET_ROUTED"
    echo "Cloudflare Dashboard must replace existing mcp.link.xdr.ooo A with Tunnel route."
  else
    echo "CLOUDFLARE_PUBLIC_HOSTNAME=DNS_CHANGED (requires HTTPS OAuth verification)"
    if ! edge_tls_check; then
      echo "CLOUDFLARE_TLS_HOSTNAME_COVERAGE=REQUIRES_CERTIFICATE"
    fi
  fi
  echo "FRP_443_UNCHANGED=PASS"
  exit 0
fi

if [[ "${1:-}" != "--apply" ]]; then
  echo "Usage: bash tools/activate-native-mcp-link.sh --check|--apply" >&2
  exit 2
fi
if [[ ! -t 0 ]]; then
  echo "ERROR: interactive SSH terminal needed for privileged operator consent and private token entry" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: assigned Native MCP worktree is not clean" >&2
  exit 1
fi
if [[ "$HEAD_SHA" != "$(git rev-parse origin/feat/v240-server-native-mcp-20261026)" ]]; then
  echo "ERROR: local Native MCP HEAD is not the pushed exact candidate" >&2
  exit 1
fi
dns="$(dig +short A "$HOST" | head -1 || true)"
if [[ -z "$dns" || "$dns" == "$DEV_PUBLIC_IPV4" ]]; then
  echo "ERROR: DNS still points directly to FRP :443; configure Cloudflare Tunnel public hostname first" >&2
  exit 1
fi
edge_tls_check

echo "Activate $RESOURCE using only access.xdr.ooo Native MCP and Cloudflare edge TLS."
echo "No Agent, Server Peer, OpenAI Tunnel, or FRP mode change."
read -r -p "Type ACTIVATE to continue: " approval
if [[ "$approval" != "ACTIVATE" ]]; then
  echo "Cancelled without changes."
  exit 2
fi

# Operator-controlled root work is limited to the existing isolated Preview.
if python3 tools/operator-native-mcp-domain.py --check | grep -q 'NATIVE_PREVIEW_DOMAIN=legacy-mcp.xdr.ooo'; then
  sudo /usr/bin/python3 tools/operator-native-mcp-domain.py --preflight
  sudo /usr/bin/python3 tools/operator-native-mcp-domain.py --apply
fi
sudo /usr/bin/python3 tools/operator-native-mcp-domain.py --verify

# This user service reads the connector token from a user-owned 0600 file.
# The token never appears in argv, logs, ChatGPT or Git.
python3 tools/operator-native-mcp-cloudflare.py --activate
python3 tools/operator-native-mcp-cloudflare.py --verify

echo
echo "ACCESS_NATIVE_MCP_PUBLIC_READY=PASS"
echo "CUSTOM_CHATGPT_MCP_URL=$RESOURCE"
echo "USER_CHATGPT_OAUTH_AND_AI_ACCESS=NOT_YET_TESTED"
echo "DESKTOP_COMMANDER_DECOMMISSION=NOT_YET_AUTHORIZED"
