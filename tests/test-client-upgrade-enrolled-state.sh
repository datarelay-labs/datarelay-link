#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export FRP_CLIENT_SOURCED=1 FRP_CLIENT_TEST_ROOT="$WORK/tree"
export _FRP_CLIENT_CANDIDATE_PAYLOAD_LIBDIR="$ROOT/lib"
. "$ROOT/install-client.sh"
mkdir -p "$FRP_CLIENT_TEST_ROOT/etc/frp-auto-deploy" "$FRP_CLIENT_TEST_ROOT/etc/frp"
legacy="$FRP_CLIENT_TEST_ROOT/etc/frp-auto-deploy/allocator-ca.crt"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=upgrade-fixture \
  -keyout "$WORK/fixture.key" -out "$legacy" >/dev/null 2>&1
fp="$(frp_ca_fingerprint_file "$legacy")"
python3 - "$FRP_CLIENT_TEST_ROOT/etc/frp/client-state.json" "$fp" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps(dict(
    machine_id='aabbccddeeff00112233445566778899', hostname='prior-agent',
    frp_server='server.example', allocator_ca_sha256=sys.argv[2],
    services={'ssh':dict(id='ssh', preset='ssh', local_port=4022, remote_port=6003, enabled=True)})))
PY
state_before="$(sha256sum "$FRP_CLIENT_TEST_ROOT/etc/frp/client-state.json")"
frp_client_upgrade_migrate_allocator_ca
cmp "$legacy" "$(frp_allocator_ca_path)"
frp_client_upgrade_project_enrolled_catalog
frp_client_upgrade_project_enrolled_catalog
python3 - "$FRP_CLIENT_TEST_ROOT" "$ROOT/lib" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
from drlink_control_plane import ControlPlane
p = ControlPlane(sys.argv[1])
try:
    rows = p.conn.execute('SELECT * FROM agent_remote_services').fetchall()
    assert len(rows) == 1
    assert rows[0]['endpoint_port'] == 6003 and rows[0]['enrollment_seed'] == 1
    assert p.conn.execute('SELECT port FROM service_objects WHERE name=?', (rows[0]['service_object'],)).fetchone()[0] == 4022
finally:
    p.close()
PY
[[ "$(sha256sum "$FRP_CLIENT_TEST_ROOT/etc/frp/client-state.json")" == "$state_before" ]]
# Existing canonical trust is never replaced, and a recorded mismatching pin
# fails migration before creating a canonical file.
printf 'preserved-canonical-trust\n' >"$(frp_allocator_ca_path)"
frp_client_upgrade_migrate_allocator_ca
grep -qx 'preserved-canonical-trust' "$(frp_allocator_ca_path)"
rm "$(frp_allocator_ca_path)"
python3 - "$FRP_CLIENT_TEST_ROOT/etc/frp/client-state.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['allocator_ca_sha256'] = '0' * 64
p.write_text(json.dumps(data))
PY
if frp_client_upgrade_migrate_allocator_ca >/dev/null 2>&1; then
  echo 'FAIL mismatching enrolled pin accepted' >&2
  exit 1
fi
[[ ! -e "$(frp_allocator_ca_path)" ]]
echo 'ENROLLED_UPGRADE_STATE=PASS'
