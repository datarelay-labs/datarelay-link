#!/usr/bin/env bash
# Fixed root-locator entry: CLI, TLS route, expiry/revoke, OS binding, redaction.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1" >&2; exit 1; }

entry_locator() {
  sed -nE 's~^curl -kfsS https://[^/]+/([A-Za-z0-9_-]{8})\|sudo bash$~\1~p' "$1"
}
entry_id() {
  awk '/^Enrollment ID:/{print $3;exit}' "$1"
}

WORKDIR="$(mktemp -d)"
ALLOC_PID=""
# shellcheck source=lib/frp-test-procs.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/frp-test-procs.sh"
frp_test_arm_cleanup

TREE="$WORKDIR/tree"
mkdir -p "$TREE/etc/drlink/pki" \
  "$TREE/etc/frp" \
  "$TREE/var/lib/drlink/enrollments" \
  "$TREE/var/lib/drlink/bootstrap" \
  "$TREE/usr/local/lib/drlink" \
  "$TREE/var/log/drlink"
echo 'token-test' >"$TREE/etc/frp/server_token"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$TREE/etc/drlink/pki/ca.key" \
  -out "$TREE/etc/drlink/pki/ca.crt" \
  -days 1 -subj "/CN=frp-test-ca" >/dev/null 2>&1 \
  || fail "openssl ca"
cp "$TREE/etc/drlink/pki/ca.crt" "$TREE/etc/drlink/pki/server.crt"
cp "$TREE/etc/drlink/pki/ca.key" "$TREE/etc/drlink/pki/server.key"

cp "$ROOT/lib/frp_zero_touch.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/lib/drlink_qualified_artifacts.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/lib/frp_pki.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/lib/frp_mgmt_auth.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/lib/frp_client_registry.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/lib/frp_server_config.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/lib/frp_control_locks.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/lib/frp_audit.py" "$TREE/usr/local/lib/drlink/"
cp "$ROOT/server/frp-port-allocator.py" "$TREE/usr/local/lib/drlink/"

FRP_TEST_ALLOC_PORT="$(python3 - <<'P'
import socket
s = socket.socket()
s.bind(('127.0.0.1', 0))
print(s.getsockname()[1])
s.close()
P
)"
export FRP_TEST_ALLOC_PORT

python3 - "$TREE/etc/drlink/config.json" "$TREE" "$FRP_TEST_ALLOC_PORT" <<'PY'
import json
import sys
from pathlib import Path

tree = Path(sys.argv[2])
port = int(sys.argv[3])
cfg = {
    "public_ip": "203.0.113.10",
    "control_port": 443,
    "frp_control_public_port": 443,
    "port_start": 6000,
    "port_end": 6098,
    "listen_host": "127.0.0.1",
    "listen_port": port,
    "allocator_listen_port": port,
    "allocator_public_url": "https://203.0.113.10:%s/enroll" % port,
    "client_installer_url": (
        "https://example.test/data-relay-link/dist/bootstrap-client.sh"
    ),
    "windows_client_installer_url": (
        "https://example.test/data-relay-link/dist/bootstrap-client.ps1"
    ),
    "tls_ca_cert": str(tree / "etc/drlink/pki/ca.crt"),
    "tls_server_cert": str(tree / "etc/drlink/pki/server.crt"),
    "tls_server_key": str(tree / "etc/drlink/pki/server.key"),
    "enrollments_dir": str(tree / "var/lib/drlink/enrollments"),
    "bootstrap_dir": str(tree / "var/lib/drlink/bootstrap"),
    "registry_file": str(tree / "var/lib/drlink/registry.json"),
    "token_file": str(tree / "etc/frp/server_token"),
    "control_plane_root": str(tree),
}
Path(sys.argv[1]).write_text(json.dumps(cfg, indent=2) + "\n")
(tree / "var/lib/drlink/registry.json").write_text(
    json.dumps({"schema_version": 2, "clients": {}, "reserved": []}) + "\n"
)
PY

# Serve a real hash-bound inert fixture from the canonical artifact layout.
python3 - "$TREE" <<'PYART'
import json, hashlib, sys
from pathlib import Path
root = Path(sys.argv[1]) / "usr/local/share/drlink/artifacts"
agent = root / "agent"
agent.mkdir(parents=True)
head = "a" * 40
items = []
for name, platform, arch in (("bootstrap-client.sh","linux","any"),("bootstrap-client.ps1","windows","amd64")):
    p = agent / name
    p.write_text("# isolated fixture\n")
    items.append(dict(artifact_type="agent-installer",platform=platform,architecture=arch,
                      relative_path="agent/"+name,source_head=head,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(root/"manifest.json").write_text(json.dumps(dict(drlink_version="2.4.0",frp_version="0.71.0",source_head=head,immutable_source_ref=head,channel="development",qualification_status="PASS",artifacts=items)))
PYART
export FRP_DEPLOY_TEST_ROOT="$TREE"
export FRP_AUDIT_LOG="$TREE/var/log/drlink/audit.jsonl"

python3 "$ROOT/tools/frp-server-set" bootstrap-hostname bootstrap.example.com \
  >"$WORKDIR/set-boot.out" || fail "set bootstrap-hostname"
grep -q 'bootstrap.example.com' "$TREE/etc/drlink/config.json" \
  || fail "bootstrap_hostname not persisted"
grep -q 'Bootstrap hostname set' "$WORKDIR/set-boot.out" || fail "set message"
if grep -qiE 'certbot|dns provider|open firewall|configure nat|invoke acme|automatic acme' \
  "$WORKDIR/set-boot.out"; then
  fail "set bootstrap-hostname implied automatic infra work"
fi
pass "BOOTSTRAP_HOSTNAME_SET"

python3 "$ROOT/tools/frp-server-set" bootstrap-hostname --unset >/dev/null
python3 "$ROOT/tools/frp-create-client" --one-line --client-name no-override >"$WORKDIR/ip.out"
grep -Eq '^curl -kfsS https://203\.0\.113\.10:[0-9]+/[A-Za-z0-9_-]{8}\|sudo bash$' "$WORKDIR/ip.out" || fail "numeric IP command"
pass "DEFAULT_NO_SILENT_LONG_COMMAND"
if python3 "$ROOT/tools/frp-create-client" --one-line --long-bootstrap --client-name rejected-old-mode >"$WORKDIR/legacy.out" 2>"$WORKDIR/legacy.err"; then
  fail "removed long-form issuance option was accepted"
fi
grep -q 'unrecognized arguments' "$WORKDIR/legacy.err"
pass "LEGACY_LONG_FORM_REMOVED"

python3 "$ROOT/tools/frp-server-set" bootstrap-hostname bootstrap.example.com >/dev/null
issue() { python3 "$ROOT/tools/frp-create-client" --one-line "$@"; }
OUT_MGMT="$WORKDIR/mgmt.out"
issue --client-name short-mgmt --note mgmt >"$OUT_MGMT"
OUT_SSH="$WORKDIR/ssh.out"
issue --ssh --client-name short-ssh --note ssh >"$OUT_SSH"
SERVICES="$WORKDIR/services.json"
cat >"$SERVICES" <<'JSON'
[{"id":"ssh","preset":"ssh","local_ip":"127.0.0.1","local_port":22},
 {"id":"http","preset":"http","local_ip":"127.0.0.1","local_port":8080}]
JSON
OUT_MULTI="$WORKDIR/multi.out"
issue --services-file "$SERVICES" --client-name short-multi >"$OUT_MULTI"
for f in "$OUT_MGMT" "$OUT_SSH" "$OUT_MULTI"; do
  grep -Eq '^curl -kfsS https://bootstrap\.example\.com/[A-Za-z0-9_-]{8}\|sudo bash$' "$f"
  ! grep -Eq 'bt1\.|zt1\.|/i/' "$f"
done
pass "MANAGEMENT_ONLY_SHORT_URL"
pass "SSH_ONLY_SHORT_URL"
pass "MULTI_SERVICE_SHORT_URL"
OUT_WINDOWS="$WORKDIR/windows.out"
issue --platform windows --rdp --client-name short-rdp >"$OUT_WINDOWS"
grep -Eq '^iex\(curl\.exe -kfsS https://bootstrap\.example\.com/[A-Za-z0-9_-]{8}\|Out-String\)$' "$OUT_WINDOWS"
! grep -Eq 'bt1\.|zt1\.|/i/' "$OUT_WINDOWS"
WIN_LOCATOR="$(sed -nE 's~^iex\(curl\.exe -kfsS https://[^/]+/([A-Za-z0-9_-]{8})\|Out-String\)$~\1~p' "$OUT_WINDOWS")"
pass "WINDOWS_ONE_LINE"
TICKET="$(entry_locator "$OUT_SSH")"
TICKET_ID="$(entry_id "$OUT_SSH")"
TICKET_FILE="$TREE/var/lib/drlink/bootstrap/${TICKET_ID}.json"
[[ -f "$TICKET_FILE" && ${#TICKET} == 8 && ${#WIN_LOCATOR} == 8 ]] || fail "entry index missing"
ALLOC_LOG="$WORKDIR/alloc.log"
python3 "$ROOT/server/frp-port-allocator.py" --config "$TREE/etc/drlink/config.json" \
  >"$ALLOC_LOG" 2>&1 &
ALLOC_PID=$!

ready=0
for _ in $(seq 1 50); do
  if FRP_TEST_ALLOC_PORT="$FRP_TEST_ALLOC_PORT" python3 - <<'PY' 2>/dev/null
import os
import socket
import ssl
port = int(os.environ['FRP_TEST_ALLOC_PORT'])
s = socket.create_connection(('127.0.0.1', port), 0.2)
ctx = ssl._create_unverified_context()
ctx.wrap_socket(s, server_hostname='localhost')
s.close()
PY
  then
    ready=1
    break
  fi
  sleep 0.1
done
[[ "$ready" == "1" ]] || { cat "$ALLOC_LOG"; fail "allocator did not start"; }

python3 - "$TICKET_FILE" <<'PY' || fail "ticket already completed"
import json
import sys
d = json.load(open(sys.argv[1]))
assert d.get('completed_at') in (None, ''), d
print('ok')
PY

ORIGIN="https://127.0.0.1:${FRP_TEST_ALLOC_PORT}"
SCRIPT1="$WORKDIR/script1.sh"
curl -fsSk "$ORIGIN/$TICKET" -o "$SCRIPT1"
curl -fsSk -A 'WindowsPowerShell/5.1' "$ORIGIN/$TICKET" -o "$WORKDIR/script2.sh"
cmp "$SCRIPT1" "$WORKDIR/script2.sh"
grep -q '^#!/bin/bash' "$SCRIPT1"
grep -q 'FRP_BOOTSTRAP_LOCATOR=' "$SCRIPT1"
! grep -Eq '^FRP_BOOTSTRAP_TICKET=|bt1\.|PACKAGE=|curl -k|curl --insecure' "$SCRIPT1"
curl -fsSk "$ORIGIN/$WIN_LOCATOR" -o "$WORKDIR/windows.ps1"
grep -q 'Get-FileHash -Algorithm SHA256' "$WORKDIR/windows.ps1"
grep -q 'FRP_BOOTSTRAP_LOCATOR' "$WORKDIR/windows.ps1"
! grep -Eq 'bt1\.|--insecure' "$WORKDIR/windows.ps1"
curl -sSk -o /dev/null -w '%{http_code}' "$ORIGIN/$TICKET?platform=windows" | grep -qx 404
pass "WINDOWS_AND_LINUX_DISPATCH"
python3 - "$TICKET_FILE" <<'PYSTATE'
import json,sys
d=json.load(open(sys.argv[1]))
assert not d.get('bound_machine_id') and not d.get('completed_at')
assert not d['entry_approval']['candidates']
PYSTATE
HDRS="$WORKDIR/headers.txt"
curl -sSk -D "$HDRS" -o /dev/null "$ORIGIN/$TICKET"
for header in 'Cache-Control: no-store' 'Pragma: no-cache' 'X-Content-Type-Options: nosniff' 'Referrer-Policy: no-referrer'; do
  grep -qi "$header" "$HDRS"
done
pass "GET_NO_CONSUME"
curl -sSk -o "$WORKDIR/bad.txt" -w '%{http_code}' "$ORIGIN/ZT000000" | grep -qx 404
grep -qx 'bootstrap unavailable' "$WORKDIR/bad.txt"
! grep -qiE 'secret|token|private|traceback|/var/lib' "$WORKDIR/bad.txt"
pass "GET_INVALID_SAFE"
sleep 0.2
! grep -F "$TICKET" "$ALLOC_LOG"
grep -q 'GET /<redacted>' "$ALLOC_LOG"
pass "URL_LOG_REDACTION"
# Public locator is never a credential; direct legacy redemption must fail.
python3 - "$TICKET" "$ORIGIN" <<'PYREDEEM'
import json,ssl,sys,urllib.request,urllib.error
req=urllib.request.Request(sys.argv[2]+'/bootstrap/redeem',data=json.dumps({
    'ticket':sys.argv[1],'machine_id':'machine-a','hostname':'host-a'}).encode(),
    headers={'Content-Type':'application/json'})
try:
    urllib.request.urlopen(req,context=ssl._create_unverified_context(),timeout=5)
    raise AssertionError('locator redeemed')
except urllib.error.HTTPError as exc:
    assert exc.code==403,exc.code
PYREDEEM
pass "LOCATOR_NOT_CREDENTIAL"
python3 - "$TICKET_FILE" <<'PYEXPIRE'
import json,sys,time
p=sys.argv[1]; d=json.load(open(p)); d['expires_at']=int(time.time())-10
with open(p,'w') as f:json.dump(d,f)
PYEXPIRE
curl -sSk -o /dev/null -w '%{http_code}' "$ORIGIN/$TICKET" | grep -qx 404
pass "EXPIRATION_GET"
issue --client-name rev-test >"$WORKDIR/rev.out"
TICKET2="$(entry_locator "$WORKDIR/rev.out")"
python3 "$ROOT/tools/frp-enrollment-revoke" "$(entry_id "$WORKDIR/rev.out")" >/dev/null
curl -sSk -o /dev/null -w '%{http_code}' "$ORIGIN/$TICKET2" | grep -qx 404
pass "REVOCATION_GET"
python3 "$ROOT/tools/frp-server-set" hostname access.example.com >/dev/null
python3 - "$TREE/etc/drlink/config.json" <<'PYCFG'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['public_hostname']=='access.example.com'
assert d['bootstrap_hostname']=='bootstrap.example.com'
PYCFG
pass "PUBLIC_HOSTNAME_SEMANTICS_UNCHANGED"
NEW_INSTALLER='https://example.test/bootstrap-client-reloaded.sh'
python3 - "$TREE/etc/drlink/config.json" "$NEW_INSTALLER" <<'PYCFG'
import json,sys,time
from pathlib import Path
p=Path(sys.argv[1]);d=json.loads(p.read_text());d['client_installer_url']=sys.argv[2];p.write_text(json.dumps(d)+'\n');time.sleep(.05)
PYCFG
issue --client-name reload-test >"$WORKDIR/reload.out"
curl -fsSk "$ORIGIN/$(entry_locator "$WORKDIR/reload.out")" -o "$WORKDIR/reload.sh"
! grep -Fq "$NEW_INSTALLER" "$WORKDIR/reload.sh"
grep -Fq "/artifacts/agent/bootstrap-client.sh" "$WORKDIR/reload.sh"
pass "LEGACY_INSTALLER_OVERRIDE_IGNORED_WITHOUT_RESTART"
PYTHONPATH="$ROOT/lib" python3 - "$TICKET" <<'PYREDACT'
import frp_zero_touch as z,sys
sample='GET /'+sys.argv[1]+' HTTP/1.1'
assert z.redact_text(sample)=='GET /<redacted> HTTP/1.1'
PYREDACT
pass "REDACT_HELPER"

# Real short-URL E2E mutates Server bootstrap_hostname and installer-url while
# exercising fallback behavior. It must restore both before reporting PASS so
# later Zero-Touch commands cannot silently regress from compact HTTPS to long pinned-CA output
# or advertise a stale installer source.
RUNNER="$ROOT/tests/run-short-url-e2e.sh"
grep -q '^snapshot_server_settings()' "$RUNNER" || fail "real E2E missing Server settings snapshot"
grep -q '^restore_server_settings()' "$RUNNER" || fail "real E2E missing Server settings restore"
grep -q "trap 'cleanup_all' EXIT" "$RUNNER" || fail "real E2E EXIT trap does not restore Server settings"
snapshot_line="$(grep -n '^snapshot_server_settings$' "$RUNNER" | tail -1 | cut -d: -f1)"
mutate_line="$(grep -n 'set-bootstrap.log' "$RUNNER" | head -1 | cut -d: -f1)"
restore_line="$(grep -n 'restore_server_settings || fail "restore server settings"' "$RUNNER" | tail -1 | cut -d: -f1)"
pass_line="$(grep -n 'note "SHORT_URL_REAL_E2E=PASS"' "$RUNNER" | tail -1 | cut -d: -f1)"
[[ -n "$snapshot_line" && -n "$mutate_line" && "$snapshot_line" -lt "$mutate_line" ]] \
  || fail "real E2E snapshots Server settings after mutation"
[[ -n "$restore_line" && -n "$pass_line" && "$restore_line" -lt "$pass_line" ]] \
  || fail "real E2E reports PASS before Server settings restore"
pass "REAL_E2E_RESTORES_MUTATED_SERVER_SETTINGS"

echo "ZERO_TOUCH_SHORT_URL_TEST=PASS"
