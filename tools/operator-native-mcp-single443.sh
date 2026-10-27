#!/usr/bin/env bash
# DRLink v2.4 Native MCP: on-host single443 + native Let's Encrypt ACME HTTP-01.
# This changes the existing DEV Server only; no Cloudflare, second VM or Agent.
# --check: read-only; --apply: root + TTY confirmation; --issue: retry cert;
# --verify: external CA-trusted TLS, MCP HTTP 401 and canonical OAuth.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DOMAIN=mcp.link.xdr.ooo
BRANCH=feat/v240-server-native-mcp-20261026
BACKUP_DIR=/var/backups/drlink-native-mcp-single443
CONFIG=/etc/drlink/config.json

git_scoped() { git -c "safe.directory=$ROOT" -C "$ROOT" "$@"; }

mode_now() {
  python3 - "$CONFIG" <<'PY'
import json,sys
from pathlib import Path
try:
    data=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(str(data.get("deployment_mode") or "direct").lower().replace("-","").replace("_",""))
except Exception:
    print("UNREADABLE")
PY
}

check_dns() {
  local address
  address="$(getent ahostsv4 "$DOMAIN" | awk 'NR == 1 {print $1}')"
  if [[ -z "$address" ]] ||
     ! ip -o -4 addr show scope global | awk '{split($4, a, "/"); print a[1]}' | grep -Fxq "$address"; then
    echo "ERROR: $DOMAIN DNS does not match any IPv4 assigned to this dev Server" >&2
    return 1
  fi
  echo "MCP_HOSTNAME_DNS_LOCAL_INTERFACE=PASS"
}

check_nginx_sites() {
  local path
  for path in /etc/nginx/sites-enabled /etc/nginx/conf.d; do
    if [[ -d "$path" ]] && [[ -n "$(find "$path" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      echo "ERROR: distro nginx has configured sites at $path; refusing to stop it" >&2
      return 1
    fi
  done
  echo "DISTRO_NGINX_SITES=EMPTY"
}

source_integrity() {
  local current head remote
  current="$(git_scoped branch --show-current)"
  head="$(git_scoped rev-parse HEAD)"
  remote="$(git_scoped rev-parse "refs/remotes/origin/$BRANCH")"
  if [[ "$current" != "$BRANCH" || "$head" != "$remote" ]] ||
     ! git_scoped diff --quiet || ! git_scoped diff --cached --quiet; then
    echo "ERROR: expected clean, pushed v2.4 Native MCP worktree" >&2
    return 1
  fi
  if [[ "$(sed -n 's/^PROJECT_VERSION=//p' "$ROOT/VERSION")" != "2.4.0" ]]; then
    echo "ERROR: expected v2.4.0 source" >&2
    return 1
  fi
  echo "PINNED_SOURCE_HEAD=$head"
}

root_only() {
  if [[ "$EUID" != 0 ]]; then
    echo "ERROR: use authorized owner SSH and sudo" >&2
    return 1
  fi
}

readiness() {
  source_integrity
  check_dns
  check_nginx_sites
  if [[ "$(hostname -f)" != "dev-drlink" ]]; then
    echo "ERROR: wrong host" >&2
    return 1
  fi
  systemctl is-active --quiet drlink-server.service
  echo "INSTALLED_MODE=$(mode_now)"
  echo "DISTRO_NGINX_ACTIVE=$(systemctl is-active nginx.service || true)"
  echo "DISTRO_NGINX_ENABLED=$(systemctl is-enabled nginx.service 2>/dev/null || true)"
  python3 "$ROOT/tools/native-mcp-letsencrypt-preflight.py"
}

issue_certificate() {
  root_only
  check_dns
  if [[ "$(mode_now)" != "single443" ]]; then
    echo "ERROR: current Server is not single443" >&2
    return 1
  fi
  systemctl is-active --quiet drlink-frontend.service
  /usr/local/bin/drlink set mcp-tls hostname "$DOMAIN"
  /usr/local/bin/drlink set mcp-tls mode auto-acme
  /usr/local/bin/drlink set mcp-tls acme-environment production
  /usr/local/bin/drlink system certificate preflight
  echo "LETS_ENCRYPT_HTTP01=START; ensure public TCP/80 can reach the challenge frontend."
  /usr/local/bin/drlink system certificate issue
  /usr/local/bin/drlink system certificate status

  # Server discovery is opt-in; real AI Access remains DENY by default.
  # Explicit developer file/command executor remains OFF.
  if [[ ! -f /usr/local/lib/drlink/drlink_mcp_server_executor.py ]]; then
    echo "ERROR: installed Server lacks Native MCP executor" >&2
    return 1
  fi
  local override=/etc/systemd/system/drlink-mcp-bridge.service.d/native-self.conf
  install -d -m 0755 "$(dirname "$override")"
  if [[ -f "$override" ]]; then
    grep -Fqx 'Environment=DRLINK_MCP_SERVER_SELF_ENABLED=1' "$override" || {
      echo "ERROR: unexpected existing Native MCP override" >&2; return 1;
    }
  else
    printf '%s\n' '[Service]' \
      'Environment=DRLINK_MCP_SERVER_SELF_ENABLED=1' \
      'Environment=DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0' >"$override"
    chmod 0644 "$override"
  fi
  systemctl daemon-reload
  systemctl restart drlink-mcp-bridge.service
  systemctl is-active --quiet drlink-mcp-bridge.service
  echo "SERVER_SELF_DISCOVERY=ENABLED"
  echo "DEVELOPER_LOCAL_EXEC=DENY_DEFAULT"
  python3 "$ROOT/tools/native-mcp-letsencrypt-preflight.py" --verify-public
}

switch_and_issue() {
  root_only
  readiness
  if [[ "$(mode_now)" != "direct" ]]; then
    echo "ERROR: not in Direct mode; use --issue if already single443" >&2
    return 1
  fi
  if [[ ! -r /dev/tty ]]; then
    echo "ERROR: interactive SSH operator approval terminal required" >&2
    return 1
  fi
  local choice=""
  echo "The existing DRLink Server/FRP services will restart in single443 mode."
  echo "A consistent root-only backup is made before any service change."
  read -r -p "Type SWITCH to authorize this DEV mode change: " choice </dev/tty
  if [[ "$choice" != "SWITCH" ]]; then
    echo "Cancelled without mutation."
    return 2
  fi
  install -d -m 0700 "$BACKUP_DIR"
  local dest="$BACKUP_DIR/server-before-single443-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
  /usr/bin/python3 "$ROOT/tools/frp-backup" "$dest"
  /usr/bin/python3 "$ROOT/tools/frp-restore" --validate "$dest"
  echo "DRLINK_CONSISTENT_BACKUP_VALIDATED=PASS"
  echo "ROOT_ONLY_BACKUP=$dest"

  # Single443 installer does not take over an active/ENABLED distro nginx.
  # Both sites-enabled and conf.d must be empty before stopping.
  check_nginx_sites
  local nginx_was_active=0 nginx_was_enabled=0
  systemctl is-active --quiet nginx.service && nginx_was_active=1 || :
  systemctl is-enabled --quiet nginx.service && nginx_was_enabled=1 || :
  systemctl stop nginx.service
  systemctl disable nginx.service
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$ROOT"
  export FRP_DEPLOYMENT_MODE=single443 FRP_CONFIRM_MODE_SWITCH=yes
  export FRP_RELEASE_CHANNEL=development
  export FRP_EXPECTED_SOURCE_REF
  FRP_EXPECTED_SOURCE_REF="$(git_scoped rev-parse HEAD)"

  echo "DRLINK_SINGLE443_MODE_SWITCH=START"
  if ! (cd "$ROOT" && bash ./install-server.sh </dev/null); then
    # Restore the ORIGINAL distro service if the installer rolled back to
    # Direct mode and no new frontend owns public TCP/443. Never start both.
    if [[ "$(mode_now)" == "direct" ]] &&
       ! systemctl is-active --quiet drlink-frontend.service; then
      if [[ "$nginx_was_enabled" == "1" ]]; then
        systemctl enable nginx.service || echo "WARNING: nginx re-enable failed" >&2
      fi
      if [[ "$nginx_was_active" == "1" ]]; then
        systemctl start nginx.service || echo "WARNING: nginx restart failed" >&2
      fi
      echo "PREEXISTING_NGINX_RESTORED_AFTER_FAILED_SWITCH=PASS"
    else
      echo "ERROR: failed install left a non-Direct frontend state; inspect backup and units before retry" >&2
    fi
    echo "ERROR: product installer failed; no certificate command was attempted" >&2
    return 1
  fi
  if [[ "$(mode_now)" != "single443" ]]; then
    echo "ERROR: installer did not reach single443; use protected backup and installer recovery" >&2
    return 1
  fi
  systemctl is-active --quiet drlink-server.service
  systemctl is-active --quiet drlink-frontend.service
  systemctl is-active --quiet drlink-mcp-bridge.service
  echo "DRLINK_SINGLE443_MODE_SWITCH=PASS"
  issue_certificate
}

case "${1:---check}" in
  --check) readiness ;;
  --apply) switch_and_issue ;;
  --issue) issue_certificate ;;
  --verify) python3 "$ROOT/tools/native-mcp-letsencrypt-preflight.py" --verify-public ;;
  *) echo "Usage: $0 --check|--apply|--issue|--verify" >&2; exit 2 ;;
esac
