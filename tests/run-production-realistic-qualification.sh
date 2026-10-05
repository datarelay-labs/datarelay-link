#!/usr/bin/env bash
# Production-realistic qualification orchestrator (PASS1 / PASS2).
# Does NOT merge, tag, or release.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/prod-qual-common.sh
source "$ROOT/tests/lib/prod-qual-common.sh"

# shellcheck source=lib/require-release-target.sh
source "$ROOT/tests/lib/require-release-target.sh"
frp_require_release_target || exit 1

PASS_NAME="${1:-PASS1}"
RUN_ID="${FRP_E2E_QUAL_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${FRP_E2E_QUAL_OUT:-$ROOT/e2e-reports/prod-qual-${PASS_NAME,,}-$RUN_ID}"
mkdir -p "$OUT"
PROD_QUAL_OUT="$OUT"
PROD_QUAL_SUMMARY="$OUT/summary.txt"
PROD_QUAL_GATES="$OUT/gates.env"
PROD_QUAL_FAILS=0
: >"$PROD_QUAL_SUMMARY"
: >"$PROD_QUAL_GATES"

FROZEN_HEAD="$(pq_head_sha)"
export PROD_QUAL_OUT PROD_QUAL_SUMMARY PROD_QUAL_GATES
export FRP_E2E_PUBLIC_HOSTNAME FRP_E2E_SERVER_IP FRP_E2E_SERVER_ALIAS
export FRP_E2E_SOAK_SECONDS="${FRP_E2E_SOAK_SECONDS:-1800}"
export FRP_E2E_CHURN_SECONDS="${FRP_E2E_CHURN_SECONDS:-300}"
# Matrix already performs a fleet server reboot; extra reboot is optional.
export FRP_E2E_QUAL_SERVER_REBOOT="${FRP_E2E_QUAL_SERVER_REBOOT:-0}"
# CI already green for candidate; local run-all still runs unless skipped.
export FRP_E2E_QUAL_SKIP_LOCAL="${FRP_E2E_QUAL_SKIP_LOCAL:-0}"

PROJECT_VERSION="$(awk -F= '/^PROJECT_VERSION=/{print $2}' "$ROOT/VERSION")"
pq_note "PHASE=DATA_RELAY_LINK_${PROJECT_VERSION//./_}_FINAL_PRODUCTION_REALISTIC_QUALIFICATION"
pq_note "PASS_NAME=$PASS_NAME RUN_ID=$RUN_ID OUT=$OUT"
pq_note "FROZEN_HEAD=$FROZEN_HEAD"
pq_note "STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "PASS_NAME=$PASS_NAME" >>"$PROD_QUAL_GATES"
echo "FROZEN_HEAD=$FROZEN_HEAD" >>"$PROD_QUAL_GATES"
echo "${PASS_NAME}_HEAD=$FROZEN_HEAD" >>"$PROD_QUAL_GATES"

# Prior-stable upgrade evidence is a mandatory exact-HEAD prerequisite.
# v2.4 keeps historical A-019. v3.0 owns a v2.4 -> v3.0 transition record.
if [[ "$PROJECT_VERSION" == 3.* ]]; then
  UPGRADE_EVIDENCE="${FRP_E2E_UPGRADE_EVIDENCE:-$ROOT/e2e-reports/release-qualification/upgrade-v240-to-v300.json}"
  UPGRADE_GATE=UPGRADE_V240_TO_V300
  UPGRADE_LABEL="v2.4 -> v3.0"
  REQUIRED_UPGRADE_GATES="UPGRADE_RELEASE_TARGET_PREFLIGHT,UPGRADE_SOURCE_PROVENANCE_BINDING,UPGRADE_DISPOSABLE_TARGET_PRECHECK,V240_BOOTSTRAP_STAGED,V240_VERSION_IDENTITY,V240_BACKUP,V240_BACKUP_RESTORABLE,V300_BOOTSTRAP_STAGED,UPGRADE_CONTROL_DB_MIGRATED,UPGRADE_POLICY_STATE_PRESERVED,UPGRADE_MANAGED_HOST_STATE_PRESERVED,UPGRADE_RUNTIME_HEALTH,UPGRADE_V240_BACKUP_RETAINED,UPGRADE_REBOOT_RECOVERY,UPGRADE_WEB_OPTIONALITY_PRESERVED,UPGRADE_HEAD_UNCHANGED,LIVE_V240_TO_V300_UPGRADE"
else
  UPGRADE_EVIDENCE="${FRP_E2E_A019_EVIDENCE:-$ROOT/e2e-reports/release-qualification/a019-v230-to-v240.json}"
  UPGRADE_GATE=UPGRADE_V230_TO_V240
  UPGRADE_LABEL="v2.3 -> v2.4 A-019"
  REQUIRED_UPGRADE_GATES="A019_RELEASE_TARGET_PREFLIGHT,A019_SOURCE_PROVENANCE_BINDING,A019_DISPOSABLE_TARGET_PRECHECK,V230_BOOTSTRAP_STAGED,V230_VERSION_IDENTITY,V230_LEGACY_LAYOUT_RUNTIME,V230_STATE_SEED,V230_NO_EGRESS_FIXTURE,V230_BACKUP,V230_BACKUP_RESTORABLE,V230_GOLDEN_EVIDENCE,V240_BOOTSTRAP_STAGED,UPGRADE_CLIENT_ID_PRESERVED,UPGRADE_PUBLIC_PORT_PRESERVED,UPGRADE_GROUP_TAG_STATE_PRESERVED,UPGRADE_METADATA_MIGRATION_MARKED,UPGRADE_RESTRICTIVE_POLICY_PRESERVED,UPGRADE_RUNTIME_HEALTH,UPGRADE_V230_BACKUP_RETAINED,UPGRADE_REBOOT_RECOVERY,UPGRADE_FIXED_TCP_AVAILABLE,A019_HEAD_UNCHANGED,LIVE_V230_TO_V240_UPGRADE"
fi
UPGRADE_LOG="$OUT/prior-stable-upgrade-evidence.log"
if python3 - "$UPGRADE_EVIDENCE" "$FROZEN_HEAD" "$ROOT/release-manifest.json" "$REQUIRED_UPGRADE_GATES" >"$UPGRADE_LOG" 2>&1 <<'PY'
import json, sys
from pathlib import Path
path, expected, manifest_path, required_csv = Path(sys.argv[1]), sys.argv[2].lower(), Path(sys.argv[3]), sys.argv[4]
if not path.is_file(): raise SystemExit("upgrade evidence missing: %s" % path)
doc=json.loads(path.read_text(encoding="utf-8"))
if doc.get("schema_version") != 1: raise SystemExit("upgrade evidence schema_version must be 1")
if str(doc.get("git_head") or "").lower()!=expected: raise SystemExit("upgrade git_head does not match frozen HEAD")
if str(doc.get("provenance_head") or "").lower()!=expected: raise SystemExit("upgrade provenance_head does not match frozen HEAD")
manifest=json.loads(manifest_path.read_text(encoding="utf-8")); expected_source=str(manifest.get("source_head") or "").lower()
if not expected_source or str(doc.get("source_head") or "").lower()!=expected_source: raise SystemExit("upgrade source_head does not match release-manifest source_head")
if str(doc.get("end_head") or "").lower()!=expected or doc.get("head_unchanged") is not True: raise SystemExit("upgrade did not finish on the same HEAD")
if doc.get("worktree_clean_start") is not True or doc.get("worktree_clean_end") is not True: raise SystemExit("upgrade evidence must come from a clean worktree")
if doc.get("release_target_qualified") is not True: raise SystemExit("upgrade evidence must come from an approved release target")
if doc.get("final_status") != "PASS": raise SystemExit("upgrade final_status is not PASS")
gates=doc.get("gates")
if not isinstance(gates,dict): raise SystemExit("upgrade gates are missing")
for key in filter(None, required_csv.split(',')):
    if gates.get(key)!="PASS": raise SystemExit("upgrade required gate %s=%s"%(key,gates.get(key)))
for key,value in gates.items():
    if value in {"FAIL","BLOCKED","NOT_RUN"}: raise SystemExit("upgrade blocking gate %s=%s"%(key,value))
print("PRIOR_STABLE_UPGRADE_EVIDENCE=PASS"); print("UPGRADE_HEAD=%s"%expected)
PY
then
  cat "$UPGRADE_LOG"
  pq_gate "$UPGRADE_GATE" PASS
else
  cat "$UPGRADE_LOG" >&2 || true
  pq_gate "$UPGRADE_GATE" BLOCKED
  pq_note "ERROR: clean exact-HEAD $UPGRADE_LABEL evidence is required before production-realistic qualification"
  exit 1
fi

# --- Precheck ---
# Fail closed before the matrix, macOS retry, fleet rebuild, reboot, or any
# other destructive path. A failed host precheck must not be ignored.
pq_note "==== INFRA PRECHECK ===="
if ! pq_precheck_hosts; then
  pq_note "ERROR: host precheck failed; refusing matrix and destructive qualification paths"
  exit 1
fi

# Stable qualification requires retained real ChatGPT owner/UI
# acceptance evidence bound to this exact provenance/content bundle. Fail before
# any matrix install/reboot when the evidence is missing, stale, or incomplete.
CHATGPT_OWNER_EVIDENCE="${FRP_E2E_CHATGPT_OWNER_EVIDENCE:-$ROOT/e2e-reports/chatgpt-owner-acceptance.json}"
CHATGPT_OWNER_LOG="$OUT/chatgpt-owner-acceptance.log"
if python3 "$ROOT/scripts/check-chatgpt-owner-acceptance.py" \
    --root "$ROOT" --evidence "$CHATGPT_OWNER_EVIDENCE" >"$CHATGPT_OWNER_LOG" 2>&1; then
  cat "$CHATGPT_OWNER_LOG"
  pq_gate CHATGPT_PLUS_OWNER_UI_ACCEPTANCE PASS
  pq_gate MCP_REAL_E2E PASS
  pq_gate CHATGPT_PLUS_USER_AUTH PASS
  pq_gate CHATGPT_PLUS_TOOL_DISCOVERY PASS
  pq_gate CHATGPT_PLUS_ALLOW_DENY PASS
else
  cat "$CHATGPT_OWNER_LOG" >&2 || true
  pq_gate CHATGPT_PLUS_OWNER_UI_ACCEPTANCE BLOCKED
  pq_gate MCP_REAL_E2E BLOCKED
  pq_gate CHATGPT_PLUS_USER_AUTH BLOCKED
  pq_gate CHATGPT_PLUS_TOOL_DISCOVERY BLOCKED
  pq_gate CHATGPT_PLUS_ALLOW_DENY BLOCKED
  pq_note "ERROR: real ChatGPT Plus owner/UI acceptance evidence is required before destructive qualification"
  exit 1
fi

# macOS reverse SSH is intermittent; wait before matrix so we do not claim PASS on BLOCKED.
if ! pq_ssh frp-e2e-macos 'echo ok' >/dev/null 2>&1; then
  # Short wait: Linux matrix profiles run first and give the tunnel more time.
  pq_wait_macos 24 || pq_note "WARN proceeding; macOS may BLOCKED and will be retried"
fi

# --- Multi-OS functional matrix (fleet build) ---
pq_note "==== REAL E2E MATRIX ===="
MATRIX_OUT="$OUT/matrix"
mkdir -p "$MATRIX_OUT"
set +e
env \
  FRP_E2E_MATRIX_OUT="$MATRIX_OUT" \
  FRP_E2E_RUN_ID="${PASS_NAME,,}-matrix-$RUN_ID" \
  FRP_E2E_PUBLIC_HOSTNAME="$FRP_E2E_PUBLIC_HOSTNAME" \
  FRP_E2E_SERVER_IP="$FRP_E2E_SERVER_IP" \
  FRP_E2E_SERVER_ALIAS="$FRP_E2E_SERVER_ALIAS" \
  FRP_E2E_MATRIX_TARGETS="${FRP_E2E_MATRIX_TARGETS:-ubuntu-24.04,amazon-linux-2023,rocky-linux-8.10,macos-arm64,windows-10}" \
  FRP_E2E_MATRIX_FLEET=1 \
  FRP_E2E_MATRIX_IP_FALLBACK=1 \
  bash "$ROOT/tests/run-real-e2e-matrix.sh" \
  | tee "$OUT/matrix.log"
MATRIX_RC=$?
set -uo pipefail
pq_note "MATRIX_RC=$MATRIX_RC"

# Always parse matrix.tsv — MATRIX_RC=0 can still include BLOCKED macOS rows.
if pq_matrix_platform_gate "$MATRIX_OUT/matrix.tsv"; then
  pq_gate FUNCTIONAL_FULL_MATRIX PASS
  pq_gate ZERO_TOUCH_REAL_E2E PASS
  pq_gate SERVICE_LIFECYCLE_REAL_E2E PASS
else
  # Retry macOS once if blocked and tunnel recovers.
  if grep -q $'macos-arm64\tBLOCKED' "$MATRIX_OUT/matrix.tsv" 2>/dev/null; then
    pq_note "==== MACOS RETRY AFTER BLOCKED ===="
    if pq_wait_macos 60; then
      set +e
      env \
        FRP_E2E_PROFILE=macos-arm64 \
        FRP_E2E_SCENARIO=full \
        FRP_E2E_SKIP_SERVER_PURGE=1 \
        FRP_E2E_SKIP_SERVER_INSTALL=1 \
        FRP_E2E_OUT_DIR="$OUT/macos-retry" \
        FRP_E2E_RUN_ID="${PASS_NAME,,}-macos-retry-$RUN_ID" \
        FRP_E2E_PUBLIC_HOSTNAME="$FRP_E2E_PUBLIC_HOSTNAME" \
        FRP_E2E_SERVER_IP="$FRP_E2E_SERVER_IP" \
        FRP_E2E_SERVER_ALIAS="$FRP_E2E_SERVER_ALIAS" \
        bash "$ROOT/tests/run-real-e2e.sh" | tee "$OUT/macos-retry.log"
      set -uo pipefail
      if [[ -f "$OUT/macos-retry/matrix-row.tsv" ]] && awk -F'\t' 'NR==1{exit !($2=="PASS" && $3=="PASS" && $4=="PASS")}' "$OUT/macos-retry/matrix-row.tsv"; then
        pq_gate MACOS_REAL_E2E PASS
        # Rewrite matrix row for summary
        grep -v $'macos-arm64\t' "$MATRIX_OUT/matrix.tsv" >"$MATRIX_OUT/matrix.tsv.tmp" || true
        cat "$OUT/macos-retry/matrix-row.tsv" >>"$MATRIX_OUT/matrix.tsv.tmp"
        mv "$MATRIX_OUT/matrix.tsv.tmp" "$MATRIX_OUT/matrix.tsv"
      else
        pq_gate MACOS_REAL_E2E FAIL
      fi
    else
      pq_gate MACOS_REAL_E2E BLOCKED
    fi
  fi
  if grep -Eq '=(FAIL|BLOCKED)$' <(grep -E '^(UBUNTU|ROCKY|AWS_LINUX|WINDOWS|MACOS)_REAL_E2E=' "$PROD_QUAL_GATES"); then
    pq_gate FUNCTIONAL_FULL_MATRIX FAIL
  else
    pq_gate FUNCTIONAL_FULL_MATRIX PASS
    pq_gate ZERO_TOUCH_REAL_E2E PASS
    pq_gate SERVICE_LIFECYCLE_REAL_E2E PASS
  fi
fi

# Matrix uninstalls macOS/Windows at profile end; re-enroll them for live multi-OS fleet.
pq_note "==== LIVE FLEET REBUILD (macos/windows keep) ===="
set +e
pq_wait_macos 30 || true
for profile in macos-arm64 windows-10; do
  [[ "$profile" == "macos-arm64" ]] && ! pq_ssh frp-e2e-macos 'echo ok' >/dev/null 2>&1 && {
    pq_note "SKIP fleet-keep macos: SSH down"
    continue
  }
  env \
    FRP_E2E_PROFILE="$profile" \
    FRP_E2E_SCENARIO=full \
    FRP_E2E_SKIP_UNINSTALL=1 \
    FRP_E2E_SKIP_SERVER_PURGE=1 \
    FRP_E2E_SKIP_SERVER_INSTALL=1 \
    FRP_E2E_CLIENT_REBOOT_REPEAT=0 \
    FRP_E2E_SERVER_REBOOT_REPEAT=0 \
    FRP_E2E_BACKUP_REPEAT=0 \
    FRP_E2E_STOP_ON_FAIL=1 \
    FRP_E2E_OUT_DIR="$OUT/fleet-keep-$profile" \
    FRP_E2E_RUN_ID="${PASS_NAME,,}-fleetkeep-$profile-$RUN_ID" \
    FRP_E2E_PUBLIC_HOSTNAME="$FRP_E2E_PUBLIC_HOSTNAME" \
    FRP_E2E_SERVER_IP="$FRP_E2E_SERVER_IP" \
    FRP_E2E_SERVER_ALIAS="$FRP_E2E_SERVER_ALIAS" \
    bash "$ROOT/tests/run-real-e2e.sh" \
    | tee "$OUT/fleet-keep-$profile.log"
done
pq_ssh "$PROD_QUAL_SERVER" 'sudo drlink show managed-hosts' | tee "$OUT/live-fleet-clients.txt"
ONLINE_N="$(grep -ci ONLINE "$OUT/live-fleet-clients.txt" || true)"
pq_note "REAL_CLIENTS_ONLINE=$ONLINE_N"
if [[ "${ONLINE_N:-0}" -ge 3 ]]; then
  pq_gate MULTI_HOST_SIMULTANEOUS_OPERATION PASS
else
  pq_note "WARN live fleet online count low: $ONLINE_N"
  pq_gate MULTI_HOST_SIMULTANEOUS_OPERATION FAIL
fi
# Map server reboot recovery from matrix evidence when extra reboot skipped.
# Presence of a log heading alone is NOT evidence of recovery success.
if [[ "${FRP_E2E_QUAL_SERVER_REBOOT}" != "1" ]]; then
  if [[ -f "$OUT/matrix.log" ]] && grep -q 'FLEET server reboot' "$OUT/matrix.log" 2>/dev/null; then
    recovery_status=""
    if [[ -f "$MATRIX_OUT/fleet-reboot-recovery.env" ]]; then
      # shellcheck disable=SC1090
      recovery_status="$(grep -E '^FLEET_REBOOT_RECOVERY=' "$MATRIX_OUT/fleet-reboot-recovery.env" | tail -n1 | cut -d= -f2-)"
    fi
    if [[ "$recovery_status" == "PASS" ]] \
      && [[ -f "$MATRIX_OUT/fleet-after-reboot.txt" ]] \
      && grep -qi ONLINE "$MATRIX_OUT/fleet-after-reboot.txt" 2>/dev/null; then
      pq_gate SERVER_REBOOT_RECOVERY PASS
      pq_gate CLIENT_RESTART_RECOVERY PASS
      pq_gate RECONNECT_STORM PASS
    else
      pq_note "matrix reboot heading present but recovery evidence missing/failed (status=${recovery_status:-absent})"
      pq_gate SERVER_REBOOT_RECOVERY FAIL
      pq_gate CLIENT_RESTART_RECOVERY FAIL
      pq_gate RECONNECT_STORM FAIL
    fi
  fi
fi
set -uo pipefail

# --- Feature Real E2Es (reuse) ---
run_feature() {
  local name="$1" script="$2"
  local o="$OUT/features/$name"
  mkdir -p "$o"
  pq_note "==== FEATURE $name ===="
  set +e
  env FRP_E2E_OUT_DIR="$o" FRP_ACCESS_E2E_OUT="$o" FRP_BACKUP_E2E_OUT="$o" \
      FRP_SUPPORT_E2E_OUT="$o" FRP_PROFILES_E2E_OUT="$o" FRP_HEALTH_E2E_OUT="$o" \
      bash "$script" | tee "$o/run.log"
  local rc=$?
  set -uo pipefail
  pq_note "FEATURE_${name}_RC=$rc"
  return "$rc"
}

if run_feature access "$ROOT/tests/run-access-control-e2e.sh"; then
  pq_gate ACCESS_REAL_E2E PASS
  pq_gate ACCESS_FAIL_CLOSED PASS
  pq_gate ACCESS_POLICY_LIVE_UPDATE PASS
else
  pq_gate ACCESS_REAL_E2E FAIL
fi

if run_feature backup "$ROOT/tests/run-backup-restore-integrity-e2e.sh"; then
  pq_gate BACKUP_CONTENT PASS
  pq_gate RESTORE_REAL_FLEET PASS
  pq_gate CORRUPT_CURRENT_RESTORE PASS
else
  pq_gate BACKUP_CONTENT FAIL
  pq_gate RESTORE_REAL_FLEET FAIL
  pq_gate CORRUPT_CURRENT_RESTORE FAIL
fi

if run_feature support "$ROOT/tests/run-support-bundle-e2e.sh"; then
  pq_gate SUPPORT_BUNDLE_REAL_E2E PASS
  pq_gate SUPPORT_BUNDLE_CONTENT PASS
  pq_gate SECRET_REDACTION PASS
else
  pq_gate SUPPORT_BUNDLE_REAL_E2E FAIL
fi

# Profiles / health remain product features; gate outcomes explicitly.
# Do not swallow RC with || true — enabled features must affect final PASS.
if run_feature profiles "$ROOT/tests/run-service-profiles-e2e.sh"; then
  pq_gate SERVICE_PROFILES_REAL_E2E PASS
else
  pq_gate SERVICE_PROFILES_REAL_E2E FAIL
fi
if run_feature health "$ROOT/tests/run-target-health-e2e.sh"; then
  pq_gate TARGET_HEALTH_REAL_E2E PASS
else
  pq_gate TARGET_HEALTH_REAL_E2E FAIL
fi
if run_feature shorturl "$ROOT/tests/run-short-url-e2e.sh"; then
  pq_gate SHORTURL_REAL_E2E PASS
  pq_gate SHORTURL_SERVER_UPGRADE PASS
  pq_gate SHORTURL_RELEASE_GATE PASS
else
  pq_gate SHORTURL_REAL_E2E FAIL
  pq_gate SHORTURL_SERVER_UPGRADE FAIL
  pq_gate SHORTURL_RELEASE_GATE FAIL
fi

# Status/doctor truthfulness after fleet
if pq_ssh "$PROD_QUAL_SERVER" 'sudo drlink show status >/dev/null && sudo drlink system diagnostics >/dev/null'; then
  pq_gate STATUS_TRUTHFULNESS PASS
  pq_gate DOCTOR_TRUTHFULNESS PASS
else
  pq_gate STATUS_TRUTHFULNESS FAIL
  pq_gate DOCTOR_TRUTHFULNESS FAIL
fi

# --- Extended load/perf/recovery/UX ---
chmod +x "$ROOT/tests/run-prod-qual-extended.sh" "$ROOT/tests/lib/prod-qual-common.sh"
set +e
PROD_QUAL_OUT="$OUT" PROD_QUAL_PHASE="$PASS_NAME" \
  bash "$ROOT/tests/run-prod-qual-extended.sh" | tee "$OUT/extended.log"
EXT_RC=$?
set -uo pipefail
pq_note "EXTENDED_RC=$EXT_RC"
# Merge extended gates
if [[ -f "$OUT/gates.env" ]]; then
  sort -u "$OUT/gates.env" -o "$OUT/gates.env"
fi

# --- Server reboot recovery (fleet already has one from matrix; optional second) ---
if [[ "${FRP_E2E_QUAL_SERVER_REBOOT:-1}" == "1" ]]; then
  pq_note "==== SERVER REBOOT RECOVERY ===="
  set +e
  pq_ssh "$PROD_QUAL_SERVER" 'sudo reboot' || true
  for i in $(seq 1 48); do
    if pq_ssh "$PROD_QUAL_SERVER" 'hostname' >/dev/null 2>&1; then
      break
    fi
    sleep 5
  done
  sleep 20
  if pq_ssh "$PROD_QUAL_SERVER" 'sudo drlink system diagnostics >/dev/null && sudo systemctl is-active drlink-server drlink-allocator drlink-access drlink-egress drlink-tcp-egress'; then
    pq_gate SERVER_REBOOT_RECOVERY PASS
  else
    pq_gate SERVER_REBOOT_RECOVERY FAIL
  fi
  # Client reconnect convergence
  sleep 30
  if pq_ssh "$PROD_QUAL_SERVER" 'sudo drlink show managed-hosts' | tee "$OUT/after-server-reboot-clients.txt" | grep -qi ONLINE; then
    pq_gate CLIENT_RESTART_RECOVERY PASS
    pq_gate RECONNECT_STORM PASS
  else
    pq_gate CLIENT_RESTART_RECOVERY FAIL
    pq_gate RECONNECT_STORM FAIL
  fi
  set -uo pipefail
fi

# --- Local automated suite gates (once per PASS; skip heavy if FRP_E2E_QUAL_SKIP_LOCAL=1) ---
if [[ "${FRP_E2E_QUAL_SKIP_LOCAL:-0}" != "1" ]]; then
  pq_note "==== LOCAL AUTOMATED GATES ===="
  set +e
  (cd "$ROOT" && ./tests/run-all.sh) >"$OUT/run-all.log" 2>&1
  echo "RUN_ALL_RC=$?" | tee -a "$PROD_QUAL_GATES"
  (cd "$ROOT" && ./tests/test-orphan-suite-coverage.sh) >"$OUT/orphan.log" 2>&1
  echo "ORPHAN_RC=$?" | tee -a "$PROD_QUAL_GATES"
  (cd "$ROOT" && ./scripts/verify-sha256sums.sh) >"$OUT/sha256.log" 2>&1
  echo "SHA256_RC=$?" | tee -a "$PROD_QUAL_GATES"
  (cd "$ROOT" && ./scripts/secret-scan.sh) >"$OUT/secret.log" 2>&1
  echo "SECRET_RC=$?" | tee -a "$PROD_QUAL_GATES"
  set -uo pipefail
  grep -q 'RUN_ALL_RC=0' "$PROD_QUAL_GATES" && pq_gate RUN_ALL PASS || pq_gate RUN_ALL FAIL
  grep -q 'ORPHAN_RC=0' "$PROD_QUAL_GATES" && pq_gate ORPHAN_TEST_CHECK PASS || pq_gate ORPHAN_TEST_CHECK FAIL
  grep -q 'SHA256_RC=0' "$PROD_QUAL_GATES" && pq_gate SHA256SUMS PASS || pq_gate SHA256SUMS FAIL
  grep -q 'SECRET_RC=0' "$PROD_QUAL_GATES" && pq_gate SECRET_SCAN PASS || pq_gate SECRET_SCAN FAIL
  # Source/dist + public metadata integrity — execute for real.
  set +e
  (cd "$ROOT" && ./scripts/build-bundles.sh >/dev/null && git diff --exit-code -- dist/) >"$OUT/source-dist-parity.log" 2>&1
  echo "SOURCE_DIST_RC=$?" | tee -a "$PROD_QUAL_GATES"
  (cd "$ROOT" && ./scripts/verify-release-manifest-artifacts.sh) >"$OUT/release-manifest.log" 2>&1
  echo "RELEASE_MANIFEST_RC=$?" | tee -a "$PROD_QUAL_GATES"
  (cd "$ROOT" && ./scripts/check-public-metadata.sh) >"$OUT/public-metadata.log" 2>&1
  echo "PUBLIC_METADATA_RC=$?" | tee -a "$PROD_QUAL_GATES"
  set -uo pipefail
  grep -q 'SOURCE_DIST_RC=0' "$PROD_QUAL_GATES" && pq_gate SOURCE_DIST_PARITY PASS || pq_gate SOURCE_DIST_PARITY FAIL
  grep -q 'RELEASE_MANIFEST_RC=0' "$PROD_QUAL_GATES" && pq_gate RELEASE_MANIFEST_CROSSCHECK PASS || pq_gate RELEASE_MANIFEST_CROSSCHECK FAIL
  grep -q 'PUBLIC_METADATA_RC=0' "$PROD_QUAL_GATES" && pq_gate PUBLIC_METADATA_SCAN PASS || pq_gate PUBLIC_METADATA_SCAN FAIL
  # Bundle parity: rebuilt dist matches SHA256SUMS + no dirty dist tree.
  if grep -q 'SHA256_RC=0' "$PROD_QUAL_GATES" && grep -q 'SOURCE_DIST_RC=0' "$PROD_QUAL_GATES"; then
    pq_gate BUNDLE_PARITY PASS
  else
    pq_gate BUNDLE_PARITY FAIL
  fi
  # Targeted tests are the run-all suite for this harness.
  grep -q 'RUN_ALL_RC=0' "$PROD_QUAL_GATES" && pq_gate TARGETED_TESTS PASS || pq_gate TARGETED_TESTS FAIL
  # CI matrices are external; mark NOT_RUN unless GH evidence is provided.
  if [[ -n "${FRP_E2E_QUAL_CI_EVIDENCE:-}" && -f "${FRP_E2E_QUAL_CI_EVIDENCE}" ]]; then
    # shellcheck disable=SC1090
    source "${FRP_E2E_QUAL_CI_EVIDENCE}"
    [[ "${LINT_CI:-}" == "PASS" ]] && pq_gate LINT_CI PASS || pq_gate LINT_CI FAIL
    [[ "${WINDOWS_CI:-}" == "PASS" ]] && pq_gate WINDOWS_CI PASS || pq_gate WINDOWS_CI FAIL
    [[ "${MACOS_CI:-}" == "PASS" ]] && pq_gate MACOS_CI PASS || pq_gate MACOS_CI FAIL
    [[ "${DISTRO_MATRIX:-}" == "PASS" ]] && pq_gate DISTRO_MATRIX PASS || pq_gate DISTRO_MATRIX FAIL
  else
    pq_gate LINT_CI NOT_RUN
    pq_gate WINDOWS_CI NOT_RUN
    pq_gate MACOS_CI NOT_RUN
    pq_gate DISTRO_MATRIX NOT_RUN
  fi
else
  pq_note "SKIP local automated gates (FRP_E2E_QUAL_SKIP_LOCAL=1); marking NOT_RUN (not PASS)"
  pq_gate RUN_ALL NOT_RUN
  pq_gate ORPHAN_TEST_CHECK NOT_RUN
  pq_gate SHA256SUMS NOT_RUN
  pq_gate SECRET_SCAN NOT_RUN
  pq_gate TARGETED_TESTS NOT_RUN
  pq_gate SOURCE_DIST_PARITY NOT_RUN
  pq_gate BUNDLE_PARITY NOT_RUN
  pq_gate RELEASE_MANIFEST_CROSSCHECK NOT_RUN
  pq_gate PUBLIC_METADATA_SCAN NOT_RUN
  pq_gate LINT_CI NOT_RUN
  pq_gate WINDOWS_CI NOT_RUN
  pq_gate MACOS_CI NOT_RUN
  pq_gate DISTRO_MATRIX NOT_RUN
fi

# Write machine-readable summary only after the terminal PASS/FAIL gate exists.
# A pre-terminal summary can otherwise report UNKNOWN while the shell exits 0.
pq_write_summary() {
  python3 - "$OUT" "$(pq_head_sha)" "$PASS_NAME" <<'PY' || true
import json, sys
from pathlib import Path
out, head, pass_name = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
gates = {}
gates_path = out / "gates.env"
if gates_path.is_file():
    for line in gates_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            gates[k.strip()] = v.strip()
evidence = {}
for rel in ("perf/baseline.json", "summary.txt", "matrix.log", "extended.log", "failures.txt"):
    p = out / rel
    if p.is_file() and p.stat().st_size > 0:
        evidence[rel] = True
    elif rel == "perf/baseline.json":
        evidence[rel] = False
doc = {
    "schema_version": 1,
    "pass_name": pass_name,
    "git_head": head,
    "gates": gates,
    "evidence_paths": evidence,
    "final_status": gates.get(pass_name, "UNKNOWN"),
}
(out / "summary.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

# Final HEAD check
END_HEAD="$(pq_head_sha)"
echo "END_HEAD=$END_HEAD" >>"$PROD_QUAL_GATES"
if [[ "$END_HEAD" == "$FROZEN_HEAD" ]]; then
  echo "HEAD_UNCHANGED=YES" >>"$PROD_QUAL_GATES"
else
  echo "HEAD_UNCHANGED=NO" >>"$PROD_QUAL_GATES"
fi

# Determine pass result.
# Client *_SSH precheck flaps (esp. macOS reverse tunnel) must not fail the pass
# when the corresponding *_REAL_E2E gate later PASSes.
if grep -q '^MACOS_REAL_E2E=PASS$' "$PROD_QUAL_GATES" && grep -q '^MACOS_SSH=FAIL$' "$PROD_QUAL_GATES"; then
  pq_gate MACOS_SSH PASS
fi
# Mandatory gates may never disappear into NOT_RUN. FAIL, BLOCKED, and NOT_RUN
# all prevent a qualification PASS; HEADROOM_LIMIT remains an explicitly bounded
# capacity outcome handled separately.
FAIL_COUNT="$(grep -E '=(FAIL|BLOCKED|NOT_RUN)$' "$PROD_QUAL_GATES" \
  | grep -Ev '^(UBUNTU|ROCKY|AWS_LINUX|WINDOWS|MACOS|UBUNTU24)_SSH=' \
  | grep -Ev '=HEADROOM_LIMIT$' \
  | wc -l | tr -d ' ')"
FINAL_RC=0
if [[ "${FAIL_COUNT:-0}" -eq 0 ]]; then
  pq_gate "$PASS_NAME" PASS
  pq_note "FINAL_${PASS_NAME}=PASS"
else
  pq_gate "$PASS_NAME" FAIL
  pq_note "FINAL_${PASS_NAME}=FAIL FAIL_COUNT=$FAIL_COUNT"
  grep -E '=(FAIL|BLOCKED|NOT_RUN)$' "$PROD_QUAL_GATES" | grep -Ev '^(UBUNTU|ROCKY|AWS_LINUX|WINDOWS|MACOS|UBUNTU24)_SSH=' | tee "$OUT/failures.txt" || true
  FINAL_RC=1
fi

pq_write_summary
exit "$FINAL_RC"
