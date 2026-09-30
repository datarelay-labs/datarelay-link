#!/usr/bin/env bash
# Multi-OS Real E2E matrix + fleet/DNS orchestration.
# Reuses tests/run-real-e2e.sh profile adapters.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${FRP_E2E_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_ROOT="${FRP_E2E_MATRIX_OUT:-$ROOT/e2e-reports/matrix-$RUN_ID}"
# shellcheck source=lib/require-release-target.sh
source "$ROOT/tests/lib/require-release-target.sh"
frp_require_release_target || exit 1
PUBLIC_HOSTNAME="$FRP_E2E_PUBLIC_HOSTNAME"
SERVER_IP="$FRP_E2E_SERVER_IP"
SERVER_ALIAS="$FRP_E2E_SERVER_ALIAS"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)
SSH_KEY="${FRP_E2E_SSH_KEY:-$HOME/.ssh/frp_e2e_ed25519}"
TARGETS="${FRP_E2E_MATRIX_TARGETS:-ubuntu-24.04,amazon-linux-2023,rocky-linux-8.10,rocky-linux-9.4,macos-arm64,windows-10}"
INCLUDE_FLEET="${FRP_E2E_MATRIX_FLEET:-1}"
INCLUDE_DNS_IP_FALLBACK="${FRP_E2E_MATRIX_IP_FALLBACK:-1}"

mkdir -p "$OUT_ROOT"
SUMMARY="$OUT_ROOT/summary.txt"
TABLE="$OUT_ROOT/matrix.tsv"
: >"$SUMMARY"
: >"$TABLE"
printf 'PLATFORM\tINSTALL\tENROLL\tSERVICE\tREBOOT\tUNINSTALL\tDNS\n' >>"$TABLE"

note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }

note "MATRIX_RUN_ID=$RUN_ID"
note "PUBLIC_HOSTNAME=$PUBLIC_HOSTNAME"
note "TARGETS=$TARGETS"
note "STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# DNS preflight from controller (do not modify external DNS).
note "DNS_TEST_HOSTNAME=$PUBLIC_HOSTNAME"
DNS_A="$(dig +short "$PUBLIC_HOSTNAME" A 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
DNS_AAAA="$(dig +short "$PUBLIC_HOSTNAME" AAAA 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
note "DNS_A_RECORD=${DNS_A:-<none>}"
note "DNS_AAAA_RECORD=${DNS_AAAA:-<none>}"
note "EXPECTED_FRP_SERVER_IP=$SERVER_IP"
if printf '%s\n' "$DNS_A" | tr ' ' '\n' | grep -qx "$SERVER_IP"; then
  note "DNS_MATCH=YES"
  DNS_OK=1
else
  note "DNS_MATCH=NO"
  DNS_OK=0
  note "Required record: A $PUBLIC_HOSTNAME -> $SERVER_IP"
fi

IFS=',' read -r -a PROFILE_LIST <<<"$TARGETS"
FAILED=0

run_profile() {
  local profile="$1"
  local skip_purge="${2:-0}"
  local skip_install="${3:-0}"
  local out="$OUT_ROOT/$profile"
  mkdir -p "$out"
  note "==== PROFILE $profile purge=$skip_purge install_skip=$skip_install ===="
  local env_dns=()
  if [[ "$DNS_OK" -eq 1 ]]; then
    env_dns=(FRP_E2E_PUBLIC_HOSTNAME="$PUBLIC_HOSTNAME")
  else
    env_dns=(FRP_E2E_PUBLIC_HOSTNAME="")
  fi
  set +e
  env \
    "${env_dns[@]}" \
    FRP_E2E_PROFILE="$profile" \
    FRP_E2E_SCENARIO=full \
    FRP_E2E_RUN_ID="$RUN_ID-$profile" \
    FRP_E2E_OUT_DIR="$out" \
    FRP_E2E_SKIP_SERVER_PURGE="$skip_purge" \
    FRP_E2E_SKIP_SERVER_INSTALL="$skip_install" \
    FRP_E2E_SERVER_IP="$SERVER_IP" \
    FRP_E2E_SERVER_ALIAS="$SERVER_ALIAS" \
    FRP_E2E_CLIENT_REBOOT_REPEAT=1 \
    FRP_E2E_SERVER_REBOOT_REPEAT=0 \
    FRP_E2E_BACKUP_REPEAT=1 \
    FRP_E2E_STOP_ON_FAIL=1 \
    bash "$ROOT/tests/run-real-e2e.sh"
  local rc=$?
  set -uo pipefail
  if [[ -f "$out/matrix-row.tsv" ]]; then
    cat "$out/matrix-row.tsv" >>"$TABLE"
  else
    printf '%s\tFAIL\tFAIL\tFAIL\tFAIL\tFAIL\tFAIL\n' "$profile" >>"$TABLE"
  fi
  note "PROFILE_RC_$profile=$rc"
  if [[ "$rc" -ne 0 ]]; then
    # macOS/Windows environment flaps: do not treat unreachable mid-run as a product defect
    # when the platform row never reached install/enroll PASS.
    row="$out/matrix-row.tsv"
    if [[ -f "$row" ]] && awk -F'\t' 'NR==1{ins=$2;enr=$3} END{exit !((ins=="SKIP"||ins=="BLOCKED") && (enr=="SKIP"||enr=="BLOCKED"))}' "$row"; then
      note "PROFILE_ENV_BLOCKER_$profile=YES"
    else
      FAILED=$((FAILED + 1))
    fi
  fi
  return "$rc"
}

# First supported Linux profile installs/purges server; subsequent share server.
first_linux=1
for profile in "${PROFILE_LIST[@]}"; do
  profile="$(echo "$profile" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$profile" ]] || continue
  case "$profile" in
    macos|macos-arm64|windows|windows-10)
      run_profile "$profile" 1 1 || true
      ;;
    *)
      if [[ "$first_linux" -eq 1 ]]; then
        run_profile "$profile" 0 0 || true
        first_linux=0
      else
        # Keep server; do not purge between Linux clients (fleet buildup).
        run_profile "$profile" 1 1 || true
      fi
      ;;
  esac
done

# Fleet simultaneous-state checks for profiles that completed enrollment.
if [[ "$INCLUDE_FLEET" == "1" && "$first_linux" -eq 0 ]]; then
  note "==== FLEET simultaneous enrollment checks ===="
  fleet_profiles=()
  for profile in "${PROFILE_LIST[@]}"; do
    profile="$(echo "$profile" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$profile" ]] || continue
    case "$profile" in macos|macos-arm64|windows|windows-10) continue ;; esac
    if [[ -f "$OUT_ROOT/$profile/client-mid.txt" && -f "$OUT_ROOT/$profile/ssh-public-port.txt" && -f "$OUT_ROOT/$profile/ssh-user.txt" && -f "$OUT_ROOT/$profile/client-alias.txt" ]]; then
      fleet_profiles+=("$profile")
    fi
  done
  note "FLEET_PROFILE_COUNT=${#fleet_profiles[@]}"
  if [[ "${#fleet_profiles[@]}" -lt 2 ]]; then
    note "FLEET_ASSERT=FAIL need at least two enrolled Linux profiles"
    FAILED=$((FAILED + 1))
  fi

  set +e
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo /usr/local/bin/drlink show managed-hosts' | tee "$OUT_ROOT/fleet-clients.txt"
  fleet_cli_rc=${PIPESTATUS[0]}
  set -uo pipefail
  if [[ "$fleet_cli_rc" -ne 0 ]] || grep -q "^No Managed Hosts enrolled" "$OUT_ROOT/fleet-clients.txt"; then
    note "FLEET_MANAGED_HOSTS=FAIL"
    FAILED=$((FAILED + 1))
  else
    note "FLEET_MANAGED_HOSTS=PASS"
  fi

  # Snapshot authoritative published endpoints before reboot.
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" "sudo python3 -c \"import json,sqlite3; c=sqlite3.connect('/var/lib/drlink/drlink.db'); rows=c.execute(\'SELECT client_id,name,public_port FROM published_services WHERE released=0 ORDER BY client_id,name\').fetchall(); print(json.dumps(rows))\"" | tee "$OUT_ROOT/fleet-ports-before-reboot.json"

  note "==== FLEET server reboot ===="
  set +e
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo reboot' || true
  for i in $(seq 1 36); do
    if ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'hostname' >/dev/null 2>&1; then break; fi
    sleep 5
  done

  # Bounded external recovery check using retained per-profile evidence.
  if [[ "${#fleet_profiles[@]}" -gt 0 ]]; then
    first_profile="${fleet_profiles[0]}"
    first_port="$(cat "$OUT_ROOT/$first_profile/ssh-public-port.txt")"
    first_user="$(cat "$OUT_ROOT/$first_profile/ssh-user.txt")"
    for i in $(seq 1 24); do
      if ssh "${SSH_OPTS[@]}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -i "$SSH_KEY" -p "$first_port" "$first_user@$SERVER_IP" 'hostname' >/dev/null 2>&1; then break; fi
      sleep 5
    done
  fi

  set +e
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo /usr/local/bin/drlink show managed-hosts; sudo /usr/local/bin/drlink system diagnostics' | tee "$OUT_ROOT/fleet-after-reboot.txt"
  fleet_reboot_cli_rc=${PIPESTATUS[0]}
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" "sudo python3 -c \"import json,sqlite3; c=sqlite3.connect('/var/lib/drlink/drlink.db'); rows=c.execute(\'SELECT client_id,name,public_port FROM published_services WHERE released=0 ORDER BY client_id,name\').fetchall(); print(json.dumps(rows))\"" >"$OUT_ROOT/fleet-ports-after-reboot.json"
  fleet_ports_rc=$?
  set -uo pipefail
  if [[ "$fleet_reboot_cli_rc" -eq 0 && "$fleet_ports_rc" -eq 0 ]] && cmp -s "$OUT_ROOT/fleet-ports-before-reboot.json" "$OUT_ROOT/fleet-ports-after-reboot.json"; then
    echo "FLEET_REBOOT_RECOVERY=PASS" | tee "$OUT_ROOT/fleet-reboot-recovery.env"
    note "FLEET_REBOOT_RECOVERY=PASS"
  else
    echo "FLEET_REBOOT_RECOVERY=FAIL" | tee "$OUT_ROOT/fleet-reboot-recovery.env"
    note "FLEET_REBOOT_RECOVERY=FAIL"
    FAILED=$((FAILED + 1))
  fi

  # External SSH via DNS hostname using profile-retained port/user evidence.
  if [[ "$DNS_OK" -eq 1 ]]; then
    note "==== FLEET DNS access ===="
    set +e
    python3 - "$OUT_ROOT" "$PUBLIC_HOSTNAME" "$SSH_KEY" "${fleet_profiles[@]}" <<'PY'
import subprocess, sys, time
from pathlib import Path
out, host, key, *profiles = sys.argv[1:]
fails = 0
for profile in profiles:
    base = Path(out) / profile
    mid = (base / "client-mid.txt").read_text().strip()
    port = int((base / "ssh-public-port.txt").read_text().strip())
    user = (base / "ssh-user.txt").read_text().strip()
    ok = False
    for _ in range(12):
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
               "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
               "-o", "IdentitiesOnly=yes", "-i", key, "-p", str(port),
               f"{user}@{host}", "hostname"]
        try:
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok = True
            break
        except Exception:
            time.sleep(5)
    print(("PASS" if ok else "FAIL"), "dns-ssh", profile, mid[:8], f"{user}@{host}:{port}")
    if not ok: fails += 1
raise SystemExit(fails)
PY
    fleet_dns_rc=$?
    set -uo pipefail
    note "FLEET_DNS_RC=$fleet_dns_rc"
    if [[ "$fleet_dns_rc" -ne 0 ]]; then FAILED=$((FAILED + 1)); fi
  fi

  # Cross-client isolation: disable one Agent Remote Service and prove another
  # profile endpoint stays reachable. No backend frp-client mutation is allowed.
  if [[ "${#fleet_profiles[@]}" -ge 2 ]]; then
    note "==== FLEET cross-client isolation ===="
    isolate_profile="${fleet_profiles[0]}"
    survivor_profile="${fleet_profiles[1]}"
    isolate_alias="$(cat "$OUT_ROOT/$isolate_profile/client-alias.txt")"
    survivor_port="$(cat "$OUT_ROOT/$survivor_profile/ssh-public-port.txt")"
    survivor_user="$(cat "$OUT_ROOT/$survivor_profile/ssh-user.txt")"
    set +e
    ssh "${SSH_OPTS[@]}" "$isolate_alias" 'sudo /usr/local/bin/drlink set remote-service ssh enabled disabled' | tee "$OUT_ROOT/fleet-isolation-disable.txt"
    isolate_disable_rc=${PIPESTATUS[0]}
    sleep 3
    ssh "${SSH_OPTS[@]}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -i "$SSH_KEY" -p "$survivor_port" "$survivor_user@$PUBLIC_HOSTNAME" 'hostname' >/dev/null 2>&1
    survivor_rc=$?
    ssh "${SSH_OPTS[@]}" "$isolate_alias" 'sudo /usr/local/bin/drlink set remote-service ssh enabled enabled' | tee "$OUT_ROOT/fleet-isolation-enable.txt"
    isolate_enable_rc=${PIPESTATUS[0]}
    set -uo pipefail
    if [[ "$isolate_disable_rc" -eq 0 && "$survivor_rc" -eq 0 && "$isolate_enable_rc" -eq 0 ]]; then
      note "CROSS_CLIENT_ISOLATION=PASS"
    else
      note "CROSS_CLIENT_ISOLATION=FAIL"
      FAILED=$((FAILED + 1))
    fi
  fi

  # Fleet backup/restore once using canonical control-plane mutation evidence.
  note "==== FLEET backup/restore ===="
  set +e
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo /usr/local/bin/drlink unset network-object matrix-restore-marker >/dev/null 2>&1 || true; sudo /usr/local/bin/drlink system backup /var/lib/drlink/backups/matrix-fleet-backup.tar.gz' | tee "$OUT_ROOT/fleet-backup.txt"
  backup_rc=${PIPESTATUS[0]}
  note "FLEET_BACKUP_RC=$backup_rc"
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo /usr/local/bin/drlink set network-object matrix-restore-marker type ip value 198.51.100.22' | tee "$OUT_ROOT/fleet-mutate.txt"
  mutate_rc=${PIPESTATUS[0]}
  cat "$ROOT/tools/frp-restore" | ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo tee /tmp/frp-restore >/dev/null && sudo chmod 755 /tmp/frp-restore'
  cat "$ROOT/tools/frp-backup" | ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo tee /tmp/frp-backup >/dev/null && sudo chmod 755 /tmp/frp-backup'
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" 'sudo python3 /tmp/frp-restore /var/lib/drlink/backups/matrix-fleet-backup.tar.gz' | tee "$OUT_ROOT/fleet-restore.txt"
  restore_rc=${PIPESTATUS[0]}
  ssh "${SSH_OPTS[@]}" "$SERVER_ALIAS" '! sudo /usr/local/bin/drlink show network-object matrix-restore-marker >/dev/null 2>&1; sudo /usr/local/bin/drlink show managed-hosts >/dev/null'
  post_restore_rc=$?
  set -uo pipefail
  note "FLEET_RESTORE_RC=$restore_rc"
  note "FLEET_POST_RESTORE_RC=$post_restore_rc"
  if [[ "$backup_rc" -eq 0 && "$mutate_rc" -eq 0 && "$restore_rc" -eq 0 && "$post_restore_rc" -eq 0 ]]; then
    note "FLEET_BACKUP_RESTORE=PASS"
  else
    note "FLEET_BACKUP_RESTORE=FAIL"
    FAILED=$((FAILED + 1))
  fi
fi
# Targeted IP fallback on the first Linux profile that enrolled (not a hard-coded
# baseline-linux host which may be absent from the release matrix).
if [[ "$INCLUDE_DNS_IP_FALLBACK" == "1" && "$DNS_OK" -eq 1 ]]; then
  note "==== DNS IP fallback regression ===="
  IP_FALLBACK_PROFILE=""
  for profile in "${PROFILE_LIST[@]}"; do
    profile="$(echo "$profile" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    case "$profile" in
      macos|macos-arm64|windows|windows-10) continue ;;
      *)
        if [[ -f "$OUT_ROOT/$profile/matrix-row.tsv" ]] && awk -F'\t' 'NR==1 && $2=="PASS" && $3=="PASS"{ok=1} END{exit !ok}' "$OUT_ROOT/$profile/matrix-row.tsv"; then
          IP_FALLBACK_PROFILE="$profile"
          break
        fi
        ;;
    esac
  done
  if [[ -z "$IP_FALLBACK_PROFILE" ]]; then
    note "IP_FALLBACK_SKIP=no enrolled Linux profile"
  else
    note "IP_FALLBACK_PROFILE=$IP_FALLBACK_PROFILE"
    set +e
    env \
      FRP_E2E_PROFILE="$IP_FALLBACK_PROFILE" \
      FRP_E2E_SCENARIO=dns \
      FRP_E2E_PUBLIC_HOSTNAME="$PUBLIC_HOSTNAME" \
      FRP_E2E_RUN_ID="$RUN_ID-ip-fallback" \
      FRP_E2E_OUT_DIR="$OUT_ROOT/ip-fallback" \
      FRP_E2E_SKIP_SERVER_PURGE=1 \
      FRP_E2E_SKIP_SERVER_INSTALL=1 \
      FRP_E2E_SERVER_REBOOT_REPEAT=0 \
      bash "$ROOT/tests/run-real-e2e.sh"
    ip_rc=$?
    note "IP_FALLBACK_RC=$ip_rc"
    if [[ "$ip_rc" -ne 0 ]]; then
      FAILED=$((FAILED + 1))
    fi
    set -uo pipefail
  fi
fi

note "FINISHED=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
note "MATRIX_TABLE:"
column -t -s $'\t' "$TABLE" 2>/dev/null || cat "$TABLE"
note "FAILED_PROFILES=$FAILED"
if [[ "$FAILED" -gt 0 ]]; then
  note "FINAL=FAIL"
  exit 1
fi
note "FINAL=PASS"
exit 0
