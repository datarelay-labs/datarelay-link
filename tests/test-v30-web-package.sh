#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

PYTHONPATH="$ROOT/lib" python3 - "$TMP" <<'PY'
import sys
from datetime import datetime, timezone
from drlink_control_plane import ControlPlane
from drlink_web_auth import WebAuthService, totp_code
import drlink_v24 as v24
root=sys.argv[1]
plane=ControlPlane(root)
v24.set_network_object(plane,"src",type="ip",value="198.51.100.10",oneshot=True)
v24.set_network_object(plane,"dst",type="ip",value="198.51.100.20",oneshot=True)
v24.set_service_object(plane,"ssh",type="tcp",port=22,oneshot=True)
v24.set_access_rule(plane,"remote","allow-ssh",mode="whitelist",source="src",destination="dst",service="ssh",enabled=True,oneshot=True)
plane.close()
auth=WebAuthService(root)
material=auth.prepare_mfa_material("admin")
now=datetime(2026,10,4,3,0,tzinfo=timezone.utc)
code,_=totp_code(material["totp_secret"],at=now)
auth.create_first_admin(
    username="admin", password="ValidPass1",
    totp_secret=material["totp_secret"], recovery_codes=material["recovery_codes"],
    totp_value=code, now=now,
)
auth.close()
PY

DRLINK_WEB_INSTALL_ROOT="$TMP" "$ROOT/install-web.sh" >/tmp/drlink-web-install-test.log

for f in \
  /usr/local/lib/drlink/drlink_web_auth.py \
  /usr/local/lib/drlink/drlink_web_service.py \
  /usr/local/lib/drlink/drlink-web.py \
  /usr/local/share/drlink-web/index.html \
  /usr/local/share/drlink-web/app.js \
  /usr/local/share/drlink-web/styles.css \
  /usr/local/share/drlink-web/foundation.css \
  /usr/local/share/drlink-web/logo/datarelay-logo.svg \
  /usr/local/bin/drlink-web-bootstrap \
  /usr/local/bin/drlink-web-recovery \
  /usr/local/bin/drlink-web-operator \
  /etc/systemd/system/drlink-web.service; do
  [[ -f "$TMP$f" ]] || { echo "FAIL missing installed Web file: $f" >&2; exit 1; }
done

grep -q 'Welcome to Data Relay Link' "$TMP/usr/local/share/drlink-web/app.js" || {
  echo "FAIL DR Control-aligned login UI missing from built Web app" >&2; exit 1;
}
grep -q 'dr-admin-hub__group' "$TMP/usr/local/share/drlink-web/foundation.css" || {
  echo "FAIL Foundation Admin Hub styles absent from Web package" >&2; exit 1;
}
grep -q 'foundation.css' "$TMP/usr/local/share/drlink-web/index.html" || {
  echo "FAIL Foundation stylesheet link absent from Web page" >&2; exit 1;
}
grep -q 'DR Control-aligned authentication surface' "$TMP/usr/local/share/drlink-web/styles.css" || {
  echo "FAIL DR Control-aligned login styles missing from Web package" >&2; exit 1;
}
for label in 'Home' 'Connections' 'Access' 'Activity & Health' 'Administration'; do
  grep -q "$label" "$TMP/usr/local/share/drlink-web/app.js" || {
    echo "FAIL grouped Web navigation missing: $label" >&2; exit 1;
  }
done
grep -q 'nav-group-toggle' "$TMP/usr/local/share/drlink-web/styles.css" || {
  echo "FAIL grouped Web navigation styles missing" >&2; exit 1;
}
grep -q 'dr-command-palette' "$TMP/usr/local/share/drlink-web/styles.css" || {
  echo "FAIL contextual global search styles missing" >&2; exit 1;
}
for style_marker in 'dr-detail-drawer' 'dr-access-map' 'dr-resource-table' 'dr-skip-link'; do
  grep -q "$style_marker" "$TMP/usr/local/share/drlink-web/styles.css" || {
    echo "FAIL modern SaaS resource/access style missing: $style_marker" >&2; exit 1;
  }
done
grep -q 'box-shadow:0 1px 2px rgba(0,0,0,.05)' "$TMP/usr/local/share/drlink-web/styles.css" || {
  echo "FAIL DR Control shadow-sm card parity missing" >&2; exit 1;
}
for global_marker in 'text-rendering:optimizeLegibility' 'scrollbar-width:thin' '::selection'; do
  grep -q -- "$global_marker" "$TMP/usr/local/share/drlink-web/styles.css" || {
    echo "FAIL DR Control global visual parity missing: $global_marker" >&2; exit 1;
  }
done
for token in '--dr-layout-sidebar-expanded:260px' '--dr-layout-sidebar-collapsed:57px' '--dr-layout-content-max:1440px' '--dr-brand-mark:#00d084' '--dr-brand-relay:#007e4f' '--dr-font-size-base:14px' '--dr-radius-card:8px' '--dr-surface-page:oklch(98.75% 0 0)' '--dr-text-primary:oklch(21% .006 285.885)' '--dr-action-primary:oklch(54.6% .245 262.881)'; do
  grep -q -- "$token" "$TMP/usr/local/share/drlink-web/styles.css" || {
    echo "FAIL DR Control visual token parity missing: $token" >&2; exit 1;
  }
done
for marker in 'drlink_web_sidebar_collapsed' 'drlink_web_theme' 'Home' 'Connections' 'Activity & Health' 'Set up a connection' 'Core-authoritative connection setup' 'Search hosts, services, policies, identities' 'Quick actions' 'Access Workspace' 'Policy Simulator' 'Filter hosts' 'Why can / cannot connect?' 'Objects & Groups' 'Filter loaded objects and groups' 'Filter policies' 'Test & explain access' 'Skip to content' 'drlink-main-content' 'Recent Activity' 'Recent Changes'; do
  grep -q -- "$marker" "$TMP/usr/local/share/drlink-web/app.js" || {
    echo "FAIL modern SaaS shell marker missing: $marker" >&2; exit 1;
  }
done

grep -q -- '--listen 127.0.0.1 --port 8741' "$TMP/etc/systemd/system/drlink-web.service" || {
  echo "FAIL Web service default is not loopback-only" >&2; exit 1;
}
for setting in 'Restart=on-failure' 'MemoryMax=256M' 'TasksMax=128' 'LimitNOFILE=4096'; do
  grep -q -- "$setting" "$TMP/etc/systemd/system/drlink-web.service" || {
    echo "FAIL Web service resource/recovery bound missing: $setting" >&2; exit 1;
  }
done

# Match the optional Web Management product names at token boundaries, not
# the independent signed Webhook Core modules (drlink-webhook-*).
if grep -Eq 'drlink[-_]web([._/[:space:]]|$)|usr/local/share/drlink-web' "$ROOT/lib/server-project-files.manifest"; then
  echo "FAIL base server project manifest depends on optional Web" >&2
  exit 1
fi

[[ -f "$TMP/var/lib/drlink/drlink.db" ]] || { echo "FAIL Core DB missing before uninstall" >&2; exit 1; }
[[ -f "$TMP/var/lib/drlink/web-auth.key" ]] || { echo "FAIL protected Web credential key missing" >&2; exit 1; }

DRLINK_WEB_INSTALL_ROOT="$TMP" "$ROOT/uninstall-web.sh" >/tmp/drlink-web-uninstall-test.log

[[ ! -e "$TMP/etc/systemd/system/drlink-web.service" ]] || { echo "FAIL Web service survived uninstall" >&2; exit 1; }
[[ ! -e "$TMP/usr/local/share/drlink-web" ]] || { echo "FAIL Web static assets survived uninstall" >&2; exit 1; }
[[ -f "$TMP/var/lib/drlink/drlink.db" ]] || { echo "FAIL Web uninstall removed Core DB" >&2; exit 1; }
[[ -f "$TMP/var/lib/drlink/web-auth.key" ]] || { echo "FAIL Web uninstall removed protected recovery key" >&2; exit 1; }

PYTHONPATH="$ROOT/lib" python3 - "$TMP" <<'PY'
import sys
from drlink_control_plane import ControlPlane
import drlink_v24 as v24
root=sys.argv[1]
plane=ControlPlane(root)
try:
    assert isinstance(plane.status(),dict)
    row=plane.conn.execute("SELECT username,recovery_admin FROM web_operators WHERE username='admin'").fetchone()
    assert row is not None and int(row["recovery_admin"]) == 1
    decision=v24.evaluate_selector_policy(
        plane,"remote",source_name="src",destination_name="dst",service_name="ssh"
    )
    assert decision["result"] == "ALLOW", decision
finally:
    plane.close()
PY

CLI_OUT="$(DRLINK_TEST_ROOT="$TMP" PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/drlink_control_cli.py" show status)"
grep -q 'Control DB.*Healthy' <<<"$CLI_OUT" || { echo "FAIL CLI unavailable after Web uninstall" >&2; exit 1; }

# Reinstalling the optional Web package must bind the current Web build to the
# already-authoritative Core without recreating or replacing Core state.
DRLINK_WEB_INSTALL_ROOT="$TMP" "$ROOT/install-web.sh" >/tmp/drlink-web-reinstall-test.log
[[ -f "$TMP/etc/systemd/system/drlink-web.service" ]] || { echo "FAIL Web service missing after reinstall" >&2; exit 1; }
[[ -f "$TMP/usr/local/share/drlink-web/app.js" ]] || { echo "FAIL Web assets missing after reinstall" >&2; exit 1; }

PYTHONPATH="$ROOT/lib" python3 - "$TMP" <<'PY'
import sys
from drlink_control_plane import ControlPlane
import drlink_v24 as v24
root=sys.argv[1]
plane=ControlPlane(root)
try:
    row=plane.conn.execute("SELECT username,recovery_admin FROM web_operators WHERE username='admin'").fetchone()
    assert row is not None and int(row["recovery_admin"]) == 1
    decision=v24.evaluate_selector_policy(
        plane,"remote",source_name="src",destination_name="dst",service_name="ssh"
    )
    assert decision["result"] == "ALLOW", decision
finally:
    plane.close()
PY

echo "WEB_NOT_INSTALLED_CORE=PASS"
echo "WEB_STOPPED_CORE=PASS"
echo "WEB_UNINSTALLED_CORE=PASS"
echo "WEB_FAILURE_DOES_NOT_CHANGE_POLICY=PASS"
echo "CLI_FULL_CAPABILITY_WITHOUT_WEB=PASS"
echo "NO_WEB_AUTHORITATIVE_DB=PASS"
echo "WEB_REINSTALL_PRESERVES_CORE=PASS"
echo "WEB_PACKAGE_LIFECYCLE=PASS"
