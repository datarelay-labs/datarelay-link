#!/usr/bin/env bash
# Prior-stable --check must not migrate installed paths or create symlinks.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TREE="$TMP/target"
mkdir -p "$TREE/etc/frp-auto-deploy/pki" "$TREE/etc/frp" "$TREE/var/lib/frp-auto-deploy"
python3 "$ROOT/lib/frp_pki.py" ensure --pki-dir "$TREE/etc/frp-auto-deploy/pki" --public-host "203.0.113.10" >/dev/null
python3 - "$TREE" <<'PY'
import json,sys
from pathlib import Path
tree=Path(sys.argv[1])
(tree/'etc/frp-auto-deploy/config.json').write_text(json.dumps({
    'public_host': '203.0.113.10',
    'frp_control_public_port': 7000,
    'frp_control_listen_port': 7000,
    'allocator_public_url': 'https://203.0.113.10:6099/enroll',
    'allocator_listen_port': 6099,
    'tls_ca_cert': '/etc/frp-auto-deploy/pki/ca.crt',
    'deployment_mode': 'direct',
}) + '\n')
(tree/'etc/frp-auto-deploy/version').write_text('PROJECT_VERSION=2.3.0\nRELEASE_CHANNEL=stable\nSOURCE_REF=v2.3.0\n')
(tree/'etc/frp/server_token').write_text('fixture-secret-not-real\n')
(tree/'var/lib/frp-auto-deploy/registry.json').write_text(json.dumps({
    'schema_version': 2, 'reserved': [], 'clients': {},
})+'\n')
PY
snapshot() {
  python3 - "$TREE" <<'PY'
import hashlib,sys,os
from pathlib import Path
root=Path(sys.argv[1])
h=hashlib.sha256()
for p in sorted(root.rglob('*')):
    st=p.lstat()
    h.update(repr((str(p.relative_to(root)),st.st_mode,st.st_size,
                   st.st_mtime_ns,st.st_uid,st.st_gid)).encode())
    if p.is_file():
        h.update(hashlib.sha256(p.read_bytes()).digest())
    if p.is_symlink():
        h.update(os.readlink(p).encode())
print(h.hexdigest())
PY
}
BEFORE="$(snapshot)"
export FRP_SERVER_TEST_ROOT="$TREE"
export FRP_RELEASE_CHANNEL=development
export PYTHONDONTWRITEBYTECODE=1
bash "$ROOT/install-server.sh" --upgrade --check --source "$ROOT" >"$TMP/check.out" 2>"$TMP/check.err" || {
  cat "$TMP/check.out"
  cat "$TMP/check.err" >&2
  exit 1
}
cat "$TMP/check.out"
test "$BEFORE" = "$(snapshot)" || { echo 'FAIL: read-only check mutated prior stable state' >&2; exit 1; }
test ! -e "$TREE/etc/drlink" || { echo 'FAIL: legacy config was migrated' >&2; exit 1; }
test ! -e "$TREE/var/lib/drlink" || { echo 'FAIL: legacy state was migrated' >&2; exit 1; }
grep -q 'State mutation.*NO' "$TMP/check.out" || { echo 'FAIL: check not read-only' >&2; exit 1; }
echo "PRIOR_STABLE_UPDATE_CHECK_READONLY=PASS"
