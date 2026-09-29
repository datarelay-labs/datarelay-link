#!/usr/bin/env bash
# Live prior-stable v2.3.0 → v2.4.0 candidate upgrade qualification.
#
# Published prior stable is immutable tag v2.3.0.
# v2.2.1 remains an older published release for historical/rollback evidence only.
# v2.3.1 was not manufactured and is not an upgrade baseline.
#
# Requires:
#   - The immutable v2.3.0 tree (FRP_V230_TREE, a checkout whose VERSION is
#     PROJECT_VERSION=2.3.0, or git archive of tag v2.3.0)
#   - SSH to FRP_E2E_SERVER_ALIAS (default frp-e2e-server)
#
# Flow:
#   1. Purge both canonical v2.4 and legacy v2.3 product state
#   2. Install immutable v2.3.0 and prove its real legacy paths/runtime
#   3. Seed non-empty v2.3 Remote Access, identity, group/tag and Access Control state
#   4. Create a v2.3 backup and sanitized same-run golden fingerprint
#   5. Upgrade to the current v2.4 candidate via bootstrap --upgrade
#   6. Verify SQLite migration, identity/port/metadata/policy preservation and
#      availability of new v2.4 functionality
#
# Immutable v2.3.0 did not include Controlled Egress. This harness must not
# manufacture v2.4-era egress-control.json as prior-stable state.
#
# A missing prior-stable tree or a version mismatch fails closed. Do not
# report that result as an excluded BLOCKED pass.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/prod-qual-common.sh
source "$ROOT/tests/lib/prod-qual-common.sh"

OUT="${FRP_E2E_OUT_DIR:-$ROOT/e2e-reports/v230-to-v240-upgrade-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
PROD_QUAL_SUMMARY="$OUT/summary.txt"
PROD_QUAL_GATES="$OUT/gates.env"
PROD_QUAL_FAILS=0
: >"$PROD_QUAL_SUMMARY"
: >"$PROD_QUAL_GATES"

SERVER="${FRP_E2E_SERVER_ALIAS:-frp-e2e-server}"
PRIOR_STABLE_VERSION=2.3.0
PRIOR_STABLE_TAG="v${PRIOR_STABLE_VERSION}"
GOLDEN="${FRP_E2E_GOLDEN_BASELINE:-$OUT/golden/${PRIOR_STABLE_TAG}-upgrade-baseline}"
V230_TREE="${FRP_V230_TREE:-${FRP_PRIOR_STABLE_TREE:-}}"
if [[ -z "$V230_TREE" ]]; then
  for cand in \
    "/home/aella/datarelay-link-dev" \
    "$(dirname "$ROOT")/datarelay-link-dev" \
    "$(dirname "$ROOT")/datarelay-link"; do
    if [[ -f "$cand/VERSION" ]] && grep -q "^PROJECT_VERSION=${PRIOR_STABLE_VERSION}$" "$cand/VERSION" 2>/dev/null; then
      V230_TREE="$cand"
      break
    fi
  done
fi
if [[ -z "$V230_TREE" ]] && git -C "$ROOT" rev-parse --verify "refs/tags/${PRIOR_STABLE_TAG}" >/dev/null 2>&1; then
  V230_TREE="$OUT/prior-stable-${PRIOR_STABLE_TAG}"
  mkdir -p "$V230_TREE"
  git -C "$ROOT" archive "$PRIOR_STABLE_TAG" | tar -x -C "$V230_TREE"
fi
HEAD="$(pq_head_sha)"
WORKTREE_CLEAN_START=NO
if git -C "$ROOT" diff --quiet && git -C "$ROOT" diff --cached --quiet; then
  WORKTREE_CLEAN_START=YES
fi
A019_CANONICAL_EVIDENCE="${FRP_E2E_A019_CANONICAL_EVIDENCE:-$ROOT/e2e-reports/release-qualification/a019-v230-to-v240.json}"
PROJECT_VERSION="$(awk -F= '/^PROJECT_VERSION=/{print $2}' "$ROOT/VERSION")"
PUBLIC_HOSTNAME="${FRP_E2E_PUBLIC_HOSTNAME:-221.139.249.113.nip.io}"
PUBLIC_IP="${FRP_E2E_SERVER_IP:-221.139.249.113}"

tree_channel() {
  python3 - "$1/release-manifest.json" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
channel = str(data.get("channel") or "").strip().lower()
if channel not in ("development", "dev", "preview", "stable"):
    raise SystemExit("unsupported release-manifest channel: %r" % channel)
if channel == "dev":
    channel = "development"
print(channel)
PY
}

fail_out() {
  pq_gate LIVE_V230_TO_V240_UPGRADE FAIL
  pq_note "$*"
  exit 1
}

[[ -n "$V230_TREE" && -f "$V230_TREE/dist/bootstrap-server.sh" ]] || fail_out "v2.3.0 tree missing (set FRP_V230_TREE to the immutable v2.3.0 tree)"
grep -q "^PROJECT_VERSION=${PRIOR_STABLE_VERSION}$" "$V230_TREE/VERSION" || fail_out "prior-stable tree is not PROJECT_VERSION=${PRIOR_STABLE_VERSION}"
[[ "$PROJECT_VERSION" == "2.4.0" ]] || fail_out "current tree must be PROJECT_VERSION=2.4.0 (got $PROJECT_VERSION)"
V230_CHANNEL="$(tree_channel "$V230_TREE")"
V240_CHANNEL="$(tree_channel "$ROOT")"

pq_note "LIVE_V230_TO_V240_UPGRADE start HEAD=$HEAD PROJECT_VERSION=$PROJECT_VERSION"
pq_note "OUT=$OUT GOLDEN=$GOLDEN V230_TREE=$V230_TREE"
pq_note "V230_CHANNEL=$V230_CHANNEL V240_CHANNEL=$V240_CHANNEL"
pq_note "WORKTREE_CLEAN_START=$WORKTREE_CLEAN_START"

# --- 0) Purge both generations so v2.3.0 is a genuine clean prior-stable install ---
pq_note "Purging canonical v2.4 and legacy v2.3 server state"
pq_ssh "$SERVER" 'sudo rm -f /var/lib/drlink/server-lifecycle.lock /var/lib/drlink/server-lifecycle.lock.pid /var/lib/frp-auto-deploy/server-lifecycle.lock /var/lib/frp-auto-deploy/server-lifecycle.lock.pid' \
  >"$OUT/stale-lock-cleanup.log" 2>&1 || true
pq_gate STALE_LIFECYCLE_LOCK_CLEANUP PASS

set +e
pq_ssh "$SERVER" "sudo bash -s -- --purge --yes" \
  <"$ROOT/dist/uninstall-server.sh" >"$OUT/server-purge-v240.log" 2>&1
purge_v240_rc=$?
pq_ssh "$SERVER" "sudo bash -s -- --purge --yes" \
  <"$V230_TREE/dist/uninstall-server.sh" >"$OUT/server-purge-v230.log" 2>&1
purge_v230_rc=$?
set -uo pipefail

if ! pq_ssh "$SERVER" 'sudo test ! -e /etc/drlink && sudo test ! -e /var/lib/drlink && sudo test ! -e /etc/frp-auto-deploy && sudo test ! -e /var/lib/frp-auto-deploy && sudo test ! -e /etc/systemd/system/drlink-server.service && sudo test ! -e /etc/systemd/system/drlink-allocator.service && sudo test ! -e /etc/systemd/system/frps.service && sudo test ! -e /etc/systemd/system/frp-port-allocator.service'; then
  pq_gate V230_PURGE FAIL
  {
    echo "v2.4 purge rc=$purge_v240_rc"
    tail -40 "$OUT/server-purge-v240.log" || true
    echo "v2.3 purge rc=$purge_v230_rc"
    tail -40 "$OUT/server-purge-v230.log" || true
  } | tee -a "$PROD_QUAL_SUMMARY"
  fail_out "server still has canonical or legacy product state after dual purge"
fi
pq_gate V230_PURGE PASS

# --- 1) Fresh v2.3.0 install on server ---
pq_note "Installing release-equivalent v2.3.0 from $V230_TREE (FRP_RELEASE_CHANNEL=$V230_CHANNEL)"
set +e
pq_ssh "$SERVER" "sudo env \
  FRP_PUBLIC_HOSTNAME='$PUBLIC_HOSTNAME' \
  FRP_PUBLIC_IP='$PUBLIC_IP' \
  FRP_RELEASE_CHANNEL='$V230_CHANNEL' \
  bash -s --" \
  <"$V230_TREE/dist/bootstrap-server.sh" >"$OUT/v230-install.log" 2>&1
inst_rc=$?
set -uo pipefail
if [[ "$inst_rc" -ne 0 ]]; then
  pq_gate V230_INSTALL FAIL
  tail -80 "$OUT/v230-install.log" | tee -a "$PROD_QUAL_SUMMARY" || true
  fail_out "v2.3.0 install failed rc=$inst_rc"
fi
pq_gate V230_INSTALL PASS

# Confirm installed version identity and immutable v2.3 runtime/layout.
v230_ver="$(pq_ssh "$SERVER" 'sudo cat /etc/frp-auto-deploy/version 2>/dev/null || true')"
printf '%s\n' "$v230_ver" >"$OUT/v230-version.txt"
if ! grep -q 'PROJECT_VERSION=2\.3\.0' <<<"$v230_ver"; then
  pq_gate V230_VERSION_IDENTITY FAIL
  fail_out "legacy v2.3 version file missing PROJECT_VERSION=2.3.0: $v230_ver"
fi
pq_gate V230_VERSION_IDENTITY PASS

if ! pq_ssh "$SERVER" 'sudo test -f /etc/frp-auto-deploy/config.json && sudo test -f /var/lib/frp-auto-deploy/registry.json && sudo test -f /var/lib/frp-auto-deploy/access-control.json && sudo test ! -e /etc/drlink/config.json && sudo test ! -e /var/lib/drlink/drlink.db && systemctl is-active --quiet frps.service && systemctl is-active --quiet frp-port-allocator.service && systemctl is-active --quiet frp-access-plugin.service'; then
  pq_gate V230_LEGACY_LAYOUT_RUNTIME FAIL
  fail_out "immutable v2.3.0 did not start from its real legacy paths/services"
fi
pq_gate V230_LEGACY_LAYOUT_RUNTIME PASS

# --- 2) Seed stable v2.3 Remote Access + identity/group/tag state ---
# IMPORTANT: registry schema must remain v2 (allocator rejects schema 1).
# Immutable v2.3.0 has no Controlled Egress; do not manufacture egress state.
pq_ssh "$SERVER" 'sudo python3 -' >"$OUT/seed.log" 2>&1 <<'PY'
import json, os, time
from pathlib import Path

reg_path = Path("/var/lib/frp-auto-deploy/registry.json")
acl_path = Path("/var/lib/frp-auto-deploy/access-control.json")

now = int(time.time())
machine_id = "aabbccdd00112233445566778899aabb"
service_id = "ssh"
remote_port = 6010
group_id = "grp_00112233"

if reg_path.is_file():
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
else:
    reg = {"schema_version": 2, "reserved": [], "clients": {}}
if not isinstance(reg, dict):
    raise SystemExit("registry.json is not an object")
reg["schema_version"] = 2
reg.setdefault("reserved", [])
if not isinstance(reg.get("reserved"), list):
    raise SystemExit("registry reserved must be an array")
# Owned service ports are represented by the service record, not duplicated in reserved.
reg["reserved"] = [p for p in reg["reserved"] if p != remote_port]
reg["groups"] = {
    group_id: {
        "name": "upgrade-lab",
        "description": "legacy v2.3 upgrade group",
        "created_at": now,
        "updated_at": now,
    }
}
clients = reg.get("clients")
if not isinstance(clients, dict):
    clients = {}
    reg["clients"] = clients
clients[machine_id] = {
    "hostname": "upgrade-e2e-client",
    "label": "v230-upgrade-seed",
    "note": "seeded for live upgrade qualification",
    "tags": {"qual": "v230-to-v240", "site": "lab"},
    "group_ids": [group_id],
    "mgmt_status": "legacy",
    "services": {
        service_id: {
            "name": "SSH",
            "protocol": "tcp",
            "remote_port": remote_port,
            "local_port": 22,
            "local_ip": "127.0.0.1",
            "preset": "ssh",
            "ssh_user": "aella",
            "enabled": True,
        }
    },
    "created_at": now,
    "updated_at": now,
}
reg_path.parent.mkdir(parents=True, exist_ok=True)
reg_path.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(reg_path, 0o600)

list_id = "acl_001122334455"
entry_id = "ace_001122334455"
acl = {
    "schema_version": 1,
    "access_lists": {
        list_id: {
            "id": list_id,
            "name": "upgrade-allow",
            "description": "restrictive remote allowlist for upgrade qualification",
            "entries": [
                {
                    "id": entry_id,
                    "name": "office-host",
                    "cidr": "198.51.100.10/32",
                }
            ],
        }
    },
    "service_access": {
        machine_id: {
            service_id: {
                "access_mode": "ALLOWLIST",
                "access_list_id": list_id,
            }
        }
    },
}
acl_path.write_text(json.dumps(acl, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(acl_path, 0o600)

# Validate with the immutable v2.3 implementation before restarting runtime.
import sys
sys.path.insert(0, "/usr/local/lib/frp-auto-deploy")
import frp_client_registry as creg
import frp_access_control as access
groups = creg.ensure_groups_map(reg)
for gid, group in groups.items():
    creg.validate_group_id(gid)
    if not isinstance(group, dict):
        raise SystemExit("invalid v2.3 group record: %s" % gid)
    creg.validate_group_name(group.get("name"))
    creg.validate_group_description(group.get("description") or "")
for cid, client in (reg.get("clients") or {}).items():
    if not isinstance(client, dict):
        raise SystemExit("invalid v2.3 client record: %s" % cid)
    for key, value in (client.get("tags") or {}).items():
        creg.validate_tag_key(key)
        creg.validate_tag_value(value)
    for gid in creg.client_group_ids(client):
        if gid not in groups:
            raise SystemExit("client %s references unknown group %s" % (cid[:12], gid))
access.validate_access_state(acl)

import subprocess
subprocess.check_call(["systemctl", "restart", "frp-port-allocator"])
ok = False
for _ in range(30):
    rc = subprocess.call(
        ["curl", "-fsSk", "https://127.0.0.1:6099/healthz"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if rc == 0:
        ok = True
        break
    time.sleep(0.5)
if not ok:
    raise SystemExit("v2.3 allocator unhealthy after seed")

print("SEED_OK")
print(json.dumps({
    "client_id": machine_id,
    "service_id": service_id,
    "remote_port": remote_port,
    "group_id": group_id,
    "registry_schema": 2,
}))
PY
grep -q SEED_OK "$OUT/seed.log" || fail_out "state seed failed"
pq_gate V230_STATE_SEED PASS

if pq_ssh "$SERVER" 'sudo test ! -e /var/lib/frp-auto-deploy/egress-control.json'; then
  pq_gate V230_NO_EGRESS_FIXTURE PASS
else
  fail_out "immutable v2.3.0 fixture unexpectedly contains egress-control.json"
fi

# Retain real prior-stable backup evidence without copying secrets off the test host,
# and prove that the v2.3 archive can restore the seeded state in an isolated root.
V230_BACKUP_REMOTE="/var/tmp/drlink-a019-v230-backup.tar.gz"
set +e
pq_ssh "$SERVER" "sudo /usr/local/sbin/frp-backup '$V230_BACKUP_REMOTE'" >"$OUT/v230-backup.log" 2>&1
backup_rc=$?
set -uo pipefail
if [[ "$backup_rc" -ne 0 ]]; then
  pq_gate V230_BACKUP FAIL
  cat "$OUT/v230-backup.log" | tee -a "$PROD_QUAL_SUMMARY" || true
  fail_out "v2.3.0 backup failed rc=$backup_rc"
fi
pq_ssh "$SERVER" "sudo sha256sum '$V230_BACKUP_REMOTE'; sudo tar -tzf '$V230_BACKUP_REMOTE' | sort" >"$OUT/v230-backup-evidence.txt"
pq_gate V230_BACKUP PASS

set +e
pq_ssh "$SERVER" "sudo env FRP_DEPLOY_TEST_ROOT=/tmp/drlink-a019-v230-restore FRP_SKIP_SYSTEMD=1 bash -s -- '$V230_BACKUP_REMOTE'" >"$OUT/v230-restore-proof.log" 2>&1 <<'EOF'
set -euo pipefail
backup="$1"
root="$FRP_DEPLOY_TEST_ROOT"
rm -rf "$root"
mkdir -p "$root/etc" "$root/var/lib" "$root/var/log"
cp -a /etc/frp-auto-deploy "$root/etc/"
cp -a /etc/frp "$root/etc/"
cp -a /var/lib/frp-auto-deploy "$root/var/lib/"
if [[ -d /var/log/frp-auto-deploy ]]; then
  cp -a /var/log/frp-auto-deploy "$root/var/log/"
fi
before="$(sha256sum /var/lib/frp-auto-deploy/registry.json | awk '{print $1}')"
python3 - "$root/var/lib/frp-auto-deploy/registry.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
data["clients"] = {}
p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
/usr/local/sbin/frp-restore "$backup"
after="$(sha256sum "$root/var/lib/frp-auto-deploy/registry.json" | awk '{print $1}')"
test "$before" = "$after"
echo V230_BACKUP_RESTORE_PROOF=PASS
rm -rf "$root"
EOF
restore_rc=$?
set -uo pipefail
if [[ "$restore_rc" -ne 0 ]] || ! grep -q '^V230_BACKUP_RESTORE_PROOF=PASS$' "$OUT/v230-restore-proof.log"; then
  pq_gate V230_BACKUP_RESTORABLE FAIL
  cat "$OUT/v230-restore-proof.log" | tee -a "$PROD_QUAL_SUMMARY" || true
  fail_out "v2.3.0 backup restore proof failed rc=$restore_rc"
fi
pq_gate V230_BACKUP_RESTORABLE PASS

# Pre-upgrade fingerprint
pq_ssh "$SERVER" 'sudo python3 -' >"$OUT/pre-upgrade-fingerprint.json" <<'PY'
import json
from pathlib import Path

def load(path):
    p = Path(path)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

reg = load("/var/lib/frp-auto-deploy/registry.json") or {}
acl = load("/var/lib/frp-auto-deploy/access-control.json") or {}
groups = reg.get("groups") or {}
clients = []
for mid, c in (reg.get("clients") or {}).items():
    if not isinstance(c, dict):
        continue
    services = []
    for sid, svc in (c.get("services") or {}).items():
        if isinstance(svc, dict):
            services.append({
                "service_id": sid,
                "remote_port": svc.get("remote_port"),
                "local_port": svc.get("local_port"),
            })
    group_names = []
    for gid in c.get("group_ids") or []:
        group = groups.get(gid) or {}
        group_names.append(group.get("name") or gid)
    clients.append({
        "machine_id": mid,
        "client_id": mid,
        "tags": c.get("tags") or {},
        "groups": sorted(group_names),
        "services": services,
    })
doc = {
    "registry_schema": reg.get("schema_version"),
    "access_lists": sorted((acl.get("access_lists") or {}).keys()),
    "clients": clients,
    "version_file": Path("/etc/frp-auto-deploy/version").read_text(encoding="utf-8")
        if Path("/etc/frp-auto-deploy/version").is_file() else "",
}
print(json.dumps(doc, indent=2, sort_keys=True))
PY
mkdir -p "$GOLDEN"
cp "$OUT/pre-upgrade-fingerprint.json" "$GOLDEN/pre-upgrade-fingerprint.json"
cp "$OUT/v230-version.txt" "$GOLDEN/version.txt"
cp "$OUT/v230-backup-evidence.txt" "$GOLDEN/backup-evidence.txt"
pq_gate V230_GOLDEN_EVIDENCE PASS

# --- 3) Upgrade to current v2.4 tree ---
# Prefer stdin bootstrap from the candidate tree so we do not depend on an unpublished tag.
# Match FRP_RELEASE_CHANNEL to the candidate tree manifest (same rule as short-url E2E).
pq_note "Upgrading server to v2.4 candidate from current tree (FRP_RELEASE_CHANNEL=$V240_CHANNEL)"
set +e
pq_ssh "$SERVER" "sudo env \
  FRP_PUBLIC_HOSTNAME='$PUBLIC_HOSTNAME' \
  FRP_PUBLIC_IP='$PUBLIC_IP' \
  FRP_RELEASE_CHANNEL='$V240_CHANNEL' \
  bash -s -- --upgrade" \
  <"$ROOT/dist/bootstrap-server.sh" >"$OUT/server-upgrade.log" 2>&1
up_rc=$?
set -uo pipefail
if [[ "$up_rc" -ne 0 ]]; then
  pq_gate UPGRADE_SERVER FAIL
  tail -80 "$OUT/server-upgrade.log" | tee -a "$PROD_QUAL_SUMMARY" || true
  fail_out "upgrade failed rc=$up_rc"
fi
pq_gate UPGRADE_SERVER PASS

# Post-upgrade fingerprint
pq_ssh "$SERVER" 'sudo python3 -' >"$OUT/post-upgrade-fingerprint.json" <<'PY'
import json
import sqlite3
from pathlib import Path

db_path = Path("/var/lib/drlink/drlink.db")
if not db_path.is_file():
    raise SystemExit("missing canonical v2.4 control DB")
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
clients = []
for c in conn.execute("SELECT id FROM clients ORDER BY id"):
    cid = str(c["id"])
    services = [
        {
            "service_id": str(s["name"]),
            "remote_port": s["public_port"],
            "local_port": s["target_port"],
        }
        for s in conn.execute(
            "SELECT name, public_port, target_port FROM published_services "
            "WHERE client_id = ? AND released = 0 ORDER BY name",
            (cid,),
        )
    ]
    tags = {
        str(t["key"]): str(t["value"])
        for t in conn.execute(
            "SELECT key, value FROM client_tags WHERE client_id = ? ORDER BY key", (cid,)
        )
    }
    groups = [
        str(g["name"])
        for g in conn.execute(
            "SELECT g.name FROM client_group_members m "
            "JOIN client_groups g ON g.id = m.group_id "
            "WHERE m.client_id = ? ORDER BY g.name",
            (cid,),
        )
    ]
    clients.append({
        "machine_id": cid,
        "client_id": cid,
        "tags": tags,
        "groups": groups,
        "services": services,
    })
marker = conn.execute(
    "SELECT value FROM system_meta WHERE key = 'legacy_v23_client_metadata_migrated'"
).fetchone()
doc = {
    "clients": clients,
    "metadata_marker": marker["value"] if marker else "",
    "version_file": Path("/etc/drlink/version").read_text(encoding="utf-8")
        if Path("/etc/drlink/version").is_file() else "",
    "tcp_unit": Path("/etc/systemd/system/drlink-tcp-egress.service").is_file()
        or Path("/lib/systemd/system/drlink-tcp-egress.service").is_file(),
    "legacy_state_path_present": Path("/var/lib/frp-auto-deploy").exists(),
}
print(json.dumps(doc, indent=2, sort_keys=True))
PY

python3 - "$OUT/pre-upgrade-fingerprint.json" "$OUT/post-upgrade-fingerprint.json" "$PROJECT_VERSION" <<'PY' | tee -a "$PROD_QUAL_GATES"
import json, sys
from pathlib import Path
pre = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
post = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
want_ver = sys.argv[3]
ok = True

def gate(name, cond):
    global ok
    print(f"{name}={'PASS' if cond else 'FAIL'}")
    if not cond:
        ok = False

pre_ids = sorted(c.get("client_id") for c in pre.get("clients") or [])
post_ids = sorted(c.get("client_id") for c in post.get("clients") or [])
gate("UPGRADE_CLIENT_ID_PRESERVED", pre_ids == post_ids and len(pre_ids) > 0)

def svc_map(doc):
    out = {}
    for c in doc.get("clients") or []:
        for s in c.get("services") or []:
            out[(c.get("client_id"), s.get("service_id"))] = s.get("remote_port")
    return out

gate("UPGRADE_SERVICE_ID_PRESERVED", set(svc_map(pre)) == set(svc_map(post)) and len(svc_map(pre)) > 0)
gate("UPGRADE_PUBLIC_PORT_PRESERVED", svc_map(pre) == svc_map(post))

def meta(doc):
    rows = []
    for c in doc.get("clients") or []:
        rows.append((
            c.get("client_id"),
            json.dumps(c.get("tags") or {}, sort_keys=True),
            json.dumps(c.get("groups") or c.get("group") or [], sort_keys=True, default=str),
        ))
    return sorted(rows)

gate("UPGRADE_GROUP_TAG_STATE_PRESERVED", meta(pre) == meta(post))
gate("UPGRADE_METADATA_MIGRATION_MARKED", post.get("metadata_marker") == "1")
gate("UPGRADE_LEGACY_STATE_PATH_RETIRED", not bool(post.get("legacy_state_path_present")))
gate("UPGRADE_VERSION_FILE", want_ver in str(post.get("version_file") or ""))
gate("UPGRADE_TCP_UNIT_PRESENT", bool(post.get("tcp_unit")))
print("COMPARE_OK=%s" % ("PASS" if ok else "FAIL"))
raise SystemExit(0 if ok else 1)
PY
up_cmp=$?

# Effective authorization must survive, not only legacy file identity.
pq_ssh "$SERVER" 'sudo python3 -' >"$OUT/policy-preservation.log" 2>&1 <<'PY'
import sys
sys.path.insert(0, "/usr/local/lib/drlink")
from drlink_control_plane import ControlPlane
import drlink_v24 as v24

plane = ControlPlane(None)
host = "v230-upgrade-seed"
remote_allow = plane.evaluate_remote_access("198.51.100.10", host, "tcp", 22)
remote_deny = plane.evaluate_remote_access("203.0.113.99", host, "tcp", 22)
remote_rules = plane.conn.execute(
    "SELECT COUNT(*) FROM policy_rules WHERE plane = 'remote'"
).fetchone()[0]
internet_rules = plane.conn.execute(
    "SELECT COUNT(*) FROM policy_rules WHERE plane = 'internet'"
).fetchone()[0]
remote_mode = v24.get_access_policy(plane, "remote").get("mode")
internet_mode = v24.get_access_policy(plane, "internet").get("mode")
print("REMOTE_ALLOW=%s" % remote_allow.get("action"))
print("REMOTE_DENY=%s" % remote_deny.get("action"))
print("REMOTE_DENY_REASON=%s" % remote_deny.get("reason"))
print("REMOTE_RULES=%s" % remote_rules)
print("INTERNET_RULES=%s" % internet_rules)
print("REMOTE_MODE=%s" % remote_mode)
print("INTERNET_MODE=%s" % internet_mode)
ok = (
    remote_allow.get("action") == "ALLOW"
    and remote_deny.get("action") == "DENY"
    and "No Policy (ALLOW)" not in str(remote_deny.get("reason"))
    and int(remote_rules) > 0
    and remote_mode == "whitelist"
    and int(internet_rules) == 0
    and internet_mode is None
)
print("POLICY_PRESERVED=%s" % ("PASS" if ok else "FAIL"))
raise SystemExit(0 if ok else 1)
PY
if grep -q 'POLICY_PRESERVED=PASS' "$OUT/policy-preservation.log"; then
  pq_gate UPGRADE_RESTRICTIVE_POLICY_PRESERVED PASS
else
  pq_gate UPGRADE_RESTRICTIVE_POLICY_PRESERVED FAIL
  cat "$OUT/policy-preservation.log" | tee -a "$PROD_QUAL_SUMMARY" || true
  up_cmp=1
fi

# Runtime health after upgrade
set +e
pq_ssh "$SERVER" 'sudo drlink doctor >/tmp/drlink-doctor-upgrade.txt 2>&1; sudo drlink show status >/tmp/drlink-status-upgrade.txt 2>&1; systemctl is-active drlink-server drlink-allocator drlink-access drlink-egress; systemctl cat drlink-tcp-egress >/dev/null 2>&1; echo TCP_UNIT_RC=$?'
rt_rc=$?
set -uo pipefail
pq_ssh "$SERVER" 'sudo cat /tmp/drlink-doctor-upgrade.txt' >"$OUT/doctor.txt" || true
pq_ssh "$SERVER" 'sudo cat /tmp/drlink-status-upgrade.txt' >"$OUT/status.txt" || true
if [[ "$rt_rc" -eq 0 ]]; then
  pq_gate UPGRADE_RUNTIME_HEALTH PASS
else
  pq_gate UPGRADE_RUNTIME_HEALTH FAIL
  up_cmp=1
fi

# The prior-stable product backup is lab evidence and must survive the upgrade
# byte-for-byte. Same-version restore was already proven before mutation.
v230_backup_sha="$(awk 'NR==1 {print $1}' "$OUT/v230-backup-evidence.txt")"
post_backup_sha="$(pq_ssh "$SERVER" "sudo sha256sum '$V230_BACKUP_REMOTE'" 2>/dev/null | awk 'NR==1 {print $1}')"
if [[ -n "$v230_backup_sha" && "$post_backup_sha" == "$v230_backup_sha" ]]; then
  pq_gate UPGRADE_V230_BACKUP_RETAINED PASS
else
  pq_gate UPGRADE_V230_BACKUP_RETAINED FAIL
  up_cmp=1
fi

# A-019 requires post-upgrade reboot recovery. Require a real boot-id change,
# successful reconnect, and healthy v2.4 runtime after boot.
boot_before="$(pq_ssh "$SERVER" 'cat /proc/sys/kernel/random/boot_id')"
set +e
pq_ssh "$SERVER" 'sudo systemctl reboot' >/dev/null 2>&1
set -uo pipefail
reboot_ok=0
for _ in $(seq 1 60); do
  sleep 5
  boot_after="$(pq_ssh "$SERVER" 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)"
  if [[ -n "$boot_after" && "$boot_after" != "$boot_before" ]] \
    && pq_ssh "$SERVER" 'sudo drlink doctor >/tmp/drlink-doctor-a019-reboot.txt 2>&1 && systemctl is-active --quiet drlink-server drlink-allocator drlink-access drlink-egress'; then
    reboot_ok=1
    break
  fi
done
pq_ssh "$SERVER" 'sudo cat /tmp/drlink-doctor-a019-reboot.txt 2>/dev/null || true' >"$OUT/doctor-after-reboot.txt" || true
if [[ "$reboot_ok" -eq 1 ]]; then
  pq_gate UPGRADE_REBOOT_RECOVERY PASS
else
  pq_gate UPGRADE_REBOOT_RECOVERY FAIL
  up_cmp=1
fi

# Fixed TCP is a v2.4 Service Object subtype. Prove the new capability
# is usable after upgrade, then remove the temporary test object.
set +e
pq_ssh "$SERVER" 'sudo drlink set service-object a019-fixed type fixed-tcp port 1521 >/tmp/fixed-tcp.txt 2>&1 && sudo drlink show service-object a019-fixed >>/tmp/fixed-tcp.txt 2>&1'
fixed_tcp_rc=$?
set -uo pipefail
pq_ssh "$SERVER" 'sudo cat /tmp/fixed-tcp.txt' >"$OUT/fixed-tcp.txt" || true
pq_ssh "$SERVER" 'sudo drlink unset service-object a019-fixed >/dev/null 2>&1 || true' || true
if [[ "$fixed_tcp_rc" -eq 0 ]]; then
  pq_gate UPGRADE_FIXED_TCP_AVAILABLE PASS
else
  pq_gate UPGRADE_FIXED_TCP_AVAILABLE FAIL
  up_cmp=1
fi

END_HEAD="$(pq_head_sha)"
WORKTREE_CLEAN_END=NO
if git -C "$ROOT" diff --quiet && git -C "$ROOT" diff --cached --quiet; then
  WORKTREE_CLEAN_END=YES
fi
if [[ "$END_HEAD" == "$HEAD" ]]; then
  pq_gate A019_HEAD_UNCHANGED PASS
else
  pq_gate A019_HEAD_UNCHANGED FAIL
  up_cmp=1
fi
pq_note "WORKTREE_CLEAN_END=$WORKTREE_CLEAN_END"

if [[ "$up_cmp" -eq 0 ]] && ! grep -q '=FAIL$' "$PROD_QUAL_GATES"; then
  pq_gate LIVE_V230_TO_V240_UPGRADE PASS
  pq_note "LIVE_V230_TO_V240_UPGRADE=PASS"
  python3 - "$OUT" "$HEAD" "$END_HEAD" "$WORKTREE_CLEAN_START" "$WORKTREE_CLEAN_END" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
head, end_head, clean_start, clean_end = sys.argv[2:]
gates = {}
for line in (out / "gates.env").read_text().splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        gates[k] = v
doc = {
    "schema_version": 1,
    "git_head": head,
    "end_head": end_head,
    "head_unchanged": end_head == head,
    "worktree_clean_start": clean_start == "YES",
    "worktree_clean_end": clean_end == "YES",
    "gates": gates,
    "final_status": gates.get("LIVE_V230_TO_V240_UPGRADE"),
    "evidence": {
        "golden": "golden/",
        "pre": "pre-upgrade-fingerprint.json",
        "post": "post-upgrade-fingerprint.json",
        "upgrade_log": "server-upgrade.log",
    },
}
(out / "summary.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY
  if [[ "$WORKTREE_CLEAN_START" == "YES" && "$WORKTREE_CLEAN_END" == "YES" ]]; then
    mkdir -p "$(dirname "$A019_CANONICAL_EVIDENCE")"
    cp "$OUT/summary.json" "$A019_CANONICAL_EVIDENCE"
    pq_note "A019_CANONICAL_EVIDENCE=$A019_CANONICAL_EVIDENCE"
  else
    pq_note "A019_CANONICAL_EVIDENCE=NOT_PUBLISHED_DIRTY_WORKTREE"
  fi
  exit 0
fi
pq_gate LIVE_V230_TO_V240_UPGRADE FAIL
pq_note "LIVE_V230_TO_V240_UPGRADE=FAIL"
exit 1
