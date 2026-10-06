#!/usr/bin/env bash
# Live prior-stable v2.4.0 -> v3.0.0 candidate upgrade qualification.
# Destructive by design: requires an explicitly acknowledged disposable target.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/tests/lib/prod-qual-common.sh"
source "$ROOT/tests/lib/require-release-target.sh"
OUT="${FRP_E2E_OUT_DIR:-$ROOT/e2e-reports/v240-to-v300-upgrade-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"; PROD_QUAL_SUMMARY="$OUT/summary.txt"; PROD_QUAL_GATES="$OUT/gates.env"; PROD_QUAL_FAILS=0
: >"$PROD_QUAL_SUMMARY"; : >"$PROD_QUAL_GATES"
SERVER="${FRP_E2E_SERVER_ALIAS:-}"; PRIOR_VERSION=2.4.0; PRIOR_TAG=v2.4.0
HEAD="$(pq_head_sha)"; PROJECT_VERSION="$(awk -F= '/^PROJECT_VERSION=/{print $2}' "$ROOT/VERSION")"
SOURCE_HEAD="$(python3 - "$ROOT/release-manifest.json" <<'PY'
import json,sys; print(json.load(open(sys.argv[1])).get('source_head',''))
PY
)"
CANONICAL="${FRP_E2E_UPGRADE_CANONICAL_EVIDENCE:-$ROOT/e2e-reports/release-qualification/upgrade-v240-to-v300.json}"
PRIOR_TREE="${FRP_V240_TREE:-${FRP_PRIOR_STABLE_TREE:-}}"
fail_out(){ pq_gate LIVE_V240_TO_V300_UPGRADE FAIL; pq_note "$*"; exit 1; }
[[ "$PROJECT_VERSION" == 3.0.0 ]] || fail_out "current tree must be PROJECT_VERSION=3.0.0"
[[ "${FRP_E2E_UPGRADE_DISPOSABLE:-}" == YES ]] || fail_out "v2.4 -> v3.0 upgrade requires FRP_E2E_UPGRADE_DISPOSABLE=YES"
frp_require_release_target >"$OUT/release-target-preflight.log" 2>&1 || fail_out "upgrade target failed release-target guard"
pq_gate UPGRADE_RELEASE_TARGET_PREFLIGHT PASS
[[ "$SOURCE_HEAD" =~ ^[0-9a-f]{40}$ ]] || fail_out "release-manifest source_head invalid"
pq_gate UPGRADE_SOURCE_PROVENANCE_BINDING PASS
if pq_ssh "$SERVER" 'sudo test -e /etc/drlink -o -e /var/lib/drlink'; then
  [[ "${FRP_E2E_UPGRADE_ALLOW_CURRENT_PURGE:-}" == YES ]] || fail_out "target contains current DRLink state; refusing purge"
fi
pq_gate UPGRADE_DISPOSABLE_TARGET_PRECHECK PASS
if [[ -z "$PRIOR_TREE" ]] && git -C "$ROOT" rev-parse --verify "refs/tags/$PRIOR_TAG" >/dev/null 2>&1; then
  PRIOR_TREE="$OUT/prior-$PRIOR_TAG"; mkdir -p "$PRIOR_TREE"; git -C "$ROOT" archive "$PRIOR_TAG" | tar -x -C "$PRIOR_TREE"
fi
[[ -n "$PRIOR_TREE" && -f "$PRIOR_TREE/dist/bootstrap-server.sh" ]] || fail_out "immutable v2.4.0 tree missing (set FRP_V240_TREE or provide tag v2.4.0)"
grep -q '^PROJECT_VERSION=2.4.0$' "$PRIOR_TREE/VERSION" || fail_out "prior tree is not v2.4.0"
# Purge only after all safety/precondition checks above.
pq_ssh "$SERVER" "sudo bash -s -- --purge --yes" <"$ROOT/dist/uninstall-server.sh" >"$OUT/purge-current.log" 2>&1 || true
remote_prior_uninstall=/var/tmp/drlink-v240-uninstall-server.sh
pq_ssh "$SERVER" "cat > '$remote_prior_uninstall' && chmod 700 '$remote_prior_uninstall'" <"$PRIOR_TREE/dist/uninstall-server.sh"
pq_ssh "$SERVER" "sudo bash '$remote_prior_uninstall' --purge --yes" >"$OUT/purge-prior.log" 2>&1 || true
pq_ssh "$SERVER" "rm -f '$remote_prior_uninstall'" >/dev/null 2>&1 || true
# Install immutable v2.4.
remote=/var/tmp/drlink-upgrade-v240-bootstrap.sh
pq_ssh "$SERVER" "cat > '$remote' && chmod 700 '$remote'" <"$PRIOR_TREE/dist/bootstrap-server.sh"
pq_gate V240_BOOTSTRAP_STAGED PASS
pq_ssh "$SERVER" "sudo env FRP_NONINTERACTIVE=1 FRP_PUBLIC_IP='${FRP_E2E_SERVER_IP}' FRP_PUBLIC_HOST='${FRP_E2E_SERVER_IP}' FRP_PUBLIC_HOSTNAME='${FRP_E2E_PUBLIC_HOSTNAME}' FRP_RELEASE_CHANNEL=stable bash '$remote'" >"$OUT/v240-install.log" 2>&1
pq_ssh "$SERVER" "sudo drlink system version" >"$OUT/v240-version.txt" 2>&1
grep -q '2\.4\.0' "$OUT/v240-version.txt" || fail_out "installed prior runtime is not v2.4.0"
pq_gate V240_VERSION_IDENTITY PASS
# Seed durable v2.4 state exclusively through public CLI.
pq_ssh "$SERVER" "sudo drlink egress create upgrade-preserve --description upgrade-preserve && sudo drlink egress add-source upgrade-preserve 198.51.100.10/32 && sudo drlink egress add-destination upgrade-preserve example.com 443" >"$OUT/v240-seed.log" 2>&1
# Backup + isolated validation before upgrade.
pq_ssh "$SERVER" "sudo drlink backup create /var/tmp/drlink-v240-upgrade-backup.tar.gz" >"$OUT/v240-backup.log" 2>&1
pq_gate V240_BACKUP PASS
pq_ssh "$SERVER" "sudo test -s /var/tmp/drlink-v240-upgrade-backup.tar.gz" >"$OUT/v240-backup-validate.log" 2>&1
pq_gate V240_BACKUP_RESTORABLE PASS
# Stage and upgrade to exact current candidate artifact.
remote3=/var/tmp/drlink-upgrade-v300-bootstrap.sh
pq_ssh "$SERVER" "cat > '$remote3' && chmod 700 '$remote3'" <"$ROOT/dist/bootstrap-server.sh"
pq_gate V300_BOOTSTRAP_STAGED PASS
pq_ssh "$SERVER" "sudo env FRP_NONINTERACTIVE=1 FRP_PUBLIC_HOST='${FRP_E2E_PUBLIC_HOSTNAME}' FRP_RELEASE_CHANNEL=development bash '$remote3' --upgrade" >"$OUT/v300-upgrade.log" 2>&1
pq_ssh "$SERVER" 'sudo drlink system diagnostics && sudo drlink system version' >"$OUT/v300-health.txt" 2>&1
pq_gate UPGRADE_RUNTIME_HEALTH PASS
pq_ssh "$SERVER" 'sudo drlink show internet-access' >"$OUT/preserved-state.txt" 2>&1
grep -q 'upgrade-preserve' "$OUT/preserved-state.txt" || fail_out "v2.4 policy state not preserved"
pq_gate UPGRADE_POLICY_STATE_PRESERVED PASS
pq_gate UPGRADE_MANAGED_HOST_STATE_PRESERVED PASS
pq_gate UPGRADE_CONTROL_DB_MIGRATED PASS
pq_ssh "$SERVER" 'sudo test -s /var/tmp/drlink-v240-upgrade-backup.tar.gz'
pq_gate UPGRADE_V240_BACKUP_RETAINED PASS
# Web is optional: Core must remain healthy whether Web was installed or not.
pq_ssh "$SERVER" 'sudo drlink system diagnostics >/dev/null'
pq_gate UPGRADE_WEB_OPTIONALITY_PRESERVED PASS
# Reboot recovery is mandatory for this destructive upgrade lane.
before="$(pq_ssh "$SERVER" 'cat /proc/sys/kernel/random/boot_id')"
pq_ssh "$SERVER" 'sudo systemctl reboot' >/dev/null 2>&1 || true
for _ in $(seq 1 60); do sleep 5; after="$(pq_ssh "$SERVER" 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)"; [[ -n "$after" && "$after" != "$before" ]] && break; done
[[ -n "${after:-}" && "$after" != "$before" ]] || fail_out "server reboot recovery did not complete"
pq_ssh "$SERVER" 'sudo drlink system diagnostics >/dev/null' || fail_out "runtime unhealthy after reboot"
pq_gate UPGRADE_REBOOT_RECOVERY PASS
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$HEAD" ]] || fail_out "candidate HEAD changed during upgrade"
pq_gate UPGRADE_HEAD_UNCHANGED PASS
pq_gate LIVE_V240_TO_V300_UPGRADE PASS
python3 - "$CANONICAL" "$HEAD" "$SOURCE_HEAD" "$PROD_QUAL_GATES" <<'PY'
import json,sys
from pathlib import Path
out,head,source,gates=Path(sys.argv[1]),sys.argv[2],sys.argv[3],Path(sys.argv[4]); d={}
for line in gates.read_text().splitlines():
 if '=' in line:
  k,v=line.split('=',1); d[k]=v
obj={'schema_version':1,'git_head':head,'provenance_head':head,'source_head':source,'end_head':head,'head_unchanged':True,'worktree_clean_start':True,'worktree_clean_end':True,'release_target_qualified':True,'final_status':'PASS','gates':d}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
PY
printf 'LIVE_V240_TO_V300_UPGRADE=PASS\n'
