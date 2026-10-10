#!/usr/bin/env bash
set -euo pipefail
ROOT="${DRLINK_WEB_INSTALL_ROOT:-}"
dst() { printf '%s' "${ROOT}$1"; }
if [[ -z "$ROOT" && "$(id -u)" -ne 0 ]]; then
  echo "ERROR: uninstall-web.sh requires root." >&2
  exit 2
fi
if [[ -z "$ROOT" ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now drlink-web.service >/dev/null 2>&1 || true
fi
rm -f \
  "$(dst /etc/systemd/system/drlink-web.service)" \
  "$(dst /usr/local/lib/drlink/drlink-web.py)" \
  "$(dst /usr/local/lib/drlink/drlink_web_service.py)" \
  "$(dst /usr/local/lib/drlink/drlink_web_management_policy.py)" \
  "$(dst /usr/local/lib/drlink/drlink_web_connectivity.py)" \
  "$(dst /usr/local/lib/drlink/drlink_web_auth.py)" \
  "$(dst /usr/local/lib/drlink/drlink_foundation_security.py)" \
  "$(dst /usr/local/lib/drlink/datarelay_onprem_security-0.10.0.dev0-py3-none-any.whl)" \
  "$(dst /usr/local/bin/drlink-web-bootstrap)" \
  "$(dst /usr/local/bin/drlink-web-recovery)" \
  "$(dst /usr/local/bin/drlink-web-operator)"
rm -rf "$(dst /usr/local/share/drlink-web)"
if [[ -z "$ROOT" ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
fi
# Core-owned operator/MFA metadata and /var/lib/drlink/web-auth.key are preserved.
echo "DRLINK_WEB_UNINSTALL=PASS"
echo "CORE_STATE_PRESERVED=YES"
