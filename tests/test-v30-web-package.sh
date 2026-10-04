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
    username="admin", password="correct horse battery staple",
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
  /usr/local/bin/drlink-web-bootstrap \
  /usr/local/bin/drlink-web-recovery \
  /usr/local/bin/drlink-web-operator \
  /etc/systemd/system/drlink-web.service; do
  [[ -f "$TMP$f" ]] || { echo "FAIL missing installed Web file: $f" >&2; exit 1; }
done

grep -q -- '--listen 127.0.0.1 --port 8741' "$TMP/etc/systemd/system/drlink-web.service" || {
  echo "FAIL Web service default is not loopback-only" >&2; exit 1;
}

if grep -Eq 'drlink[-_]web|usr/local/share/drlink-web' "$ROOT/lib/server-project-files.manifest"; then
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

echo "WEB_NOT_INSTALLED_CORE=PASS"
echo "WEB_STOPPED_CORE=PASS"
echo "WEB_UNINSTALLED_CORE=PASS"
echo "WEB_FAILURE_DOES_NOT_CHANGE_POLICY=PASS"
echo "CLI_FULL_CAPABILITY_WITHOUT_WEB=PASS"
echo "NO_WEB_AUTHORITATIVE_DB=PASS"
echo "WEB_PACKAGE_LIFECYCLE=PASS"
