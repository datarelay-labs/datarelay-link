#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
TREE="$WORK/tree"
mkdir -p "$TREE/etc/drlink/pki" "$TREE/var/lib/drlink/enrollments" "$TREE/var/lib/drlink/bootstrap"
# A hermetic Private-CA endpoint must carry an IP SAN matching the allocator.
# An invented DNS name is not a publicly trusted compact Zero-Touch issuer.
python3 "$ROOT/lib/frp_pki.py" ensure --pki-dir "$TREE/etc/drlink/pki" --public-host 203.0.113.10 >/dev/null
python3 - "$TREE" <<'PY'
import json, sys
from pathlib import Path
root=Path(sys.argv[1])
(root/'etc/drlink/config.json').write_text(json.dumps({
  'enrollments_dir':'/var/lib/drlink/enrollments',
  'bootstrap_dir':'/var/lib/drlink/bootstrap',
  'tls_ca_cert':'/etc/drlink/pki/ca.crt',
  'deployment_mode': 'direct',
  'public_ip': '203.0.113.10',
  'frp_control_public_port': 8443,
  'allocator_public_url': 'https://203.0.113.10:8443/enroll',
  'client_installer_url':'https://example.test/bootstrap-client.sh',
})+'\n')
PY
export FRP_DEPLOY_TEST_ROOT="$TREE"
python3 "$ROOT/tools/frp-create-client" --one-line --client-name pending-a >"$WORK/create.out"
TICKET="$(sed -nE 's~^curl -kfsS https://[^/]+/([A-Za-z0-9_-]{6})\|sudo bash$~\1~p' "$WORK/create.out")"
ID="$(awk '/^Enrollment ID:/{print $3;exit}' "$WORK/create.out")"
python3 - "$TICKET" "$ID" "$TREE/var/lib/drlink/bootstrap" <<'PYINDEX'
import hashlib,json,sys,re
from pathlib import Path
locator,tid,root=sys.argv[1:]
assert re.fullmatch(r'[A-Za-z0-9_-]{6}',locator)
digest=hashlib.sha256(locator.encode()).hexdigest()
index=json.loads((Path(root)/'entry-locators'/(digest+'.json')).read_text())
assert index['ticket_id']==tid
assert json.loads((Path(root)/(tid+'.json')).read_text())['entry_locator_hash']==digest
PYINDEX
SECRET="$TICKET"
python3 "$ROOT/tools/frp-enrollments" >"$WORK/list.out"
grep -q 'ID.*TYPE.*LABEL.*CREATED.*EXPIRES.*STATE' "$WORK/list.out"
grep -qE "${ID}[[:space:]]+zero-touch[[:space:]]+pending-a.*pending" "$WORK/list.out"
! grep -Fq "$SECRET" "$WORK/list.out"
python3 "$ROOT/tools/frp-enrollment-revoke" "$ID" >"$WORK/revoke.out"
python3 "$ROOT/tools/frp-enrollments" >"$WORK/revoked.out"
grep -qE "${ID}[[:space:]]+zero-touch.*revoked" "$WORK/revoked.out"
! grep -Fq "$SECRET" "$WORK/revoked.out"
python3 - "$TREE/var/lib/drlink/bootstrap/$ID.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r.get('revoked_at')
PY
echo "PENDING_ENROLLMENTS_TEST=PASS"
