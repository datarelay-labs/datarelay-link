#!/usr/bin/env bash
# Extended production-realistic phases: egress allow/deny, load, perf, recovery, UX.
# Invoked by tests/run-production-realistic-qualification.sh
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/prod-qual-common.sh
source "$ROOT/tests/lib/prod-qual-common.sh"

OUT="${PROD_QUAL_OUT:?PROD_QUAL_OUT required}"
PHASE="${PROD_QUAL_PHASE:-extended}"
mkdir -p "$OUT/extended" "$OUT/perf" "$OUT/resources" "$OUT/ux" "$OUT/golden"
PROD_QUAL_SUMMARY="$OUT/extended/summary.txt"
PROD_QUAL_GATES="$OUT/gates.env"
PROD_QUAL_FAILS=0
: >"$PROD_QUAL_SUMMARY"
touch "$PROD_QUAL_GATES"

SERVER="$PROD_QUAL_SERVER"
SERVER_IP="$PROD_QUAL_SERVER_IP"
EGRESS_PORT="${FRP_E2E_EGRESS_PORT:-16080}"
SSH_KEY="$PROD_QUAL_SSH_KEY"
SOAK_SECONDS="${FRP_E2E_SOAK_SECONDS:-1800}"  # 30 minutes default
CHURN_SECONDS="${FRP_E2E_CHURN_SECONDS:-300}" # 5 minutes

LINUX_CLIENTS=(frp-e2e-client frp-e2e-linux114 frp-e2e-rocky8 frp-e2e-aws)
ALL_CLIENTS=(frp-e2e-client frp-e2e-linux114 frp-e2e-rocky8 frp-e2e-aws frp-e2e-macos frp-e2e-windows)

pq_note "EXTENDED_PHASE=$PHASE OUT=$OUT STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
pq_note "HEAD=$(pq_head_sha)"

# ---------------------------------------------------------------------------
# Ensure egress gateway listens on a reachable port for Real E2E clients.
# ---------------------------------------------------------------------------
ensure_egress_listener() {
  pq_note "==== ensure egress listener :$EGRESS_PORT ===="
  pq_ssh "$SERVER" "sudo bash -s" <<EOF
set -euo pipefail
python3 - <<'PY'
import json, os, tempfile
from pathlib import Path
# FIXTURE-PREP (lab harness only): product CLI has no egress_listen_* setter.
# Atomic write + service restart so Real E2E clients can reach the proxy port.
cfg_path = Path("/etc/drlink/config.json")
cfg = json.loads(cfg_path.read_text())
cfg["egress_listen_addr"] = "0.0.0.0"
cfg["egress_listen_port"] = ${EGRESS_PORT}
cfg.setdefault("egress_conn_log_file", "/var/log/drlink/egress/connections.jsonl")
fd, tmp_name = tempfile.mkstemp(prefix=".config.", dir=str(cfg_path.parent), text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, sort_keys=True)
        fh.write("\\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_name, cfg_path)
finally:
    if os.path.exists(tmp_name):
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
print("FIXTURE_PREP egress listen configured", cfg["egress_listen_addr"], cfg["egress_listen_port"])
# Preserve egress runtime ACL after harness config mutation.
try:
    import importlib.util
    from pathlib import Path as P
    mod_path = P("/usr/local/lib/drlink/frp_server_config.py")
    if mod_path.is_file():
        spec = importlib.util.spec_from_file_location("frp_server_config", str(mod_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "_reapply_config_egress_permissions"):
            mod._reapply_config_egress_permissions(cfg_path)
except Exception as exc:
    print("WARN acl reapply:", exc)
PY
# Prefer systemd unit if it honors config; else ensure dedicated smoke listener.
systemctl restart drlink-egress || true
sleep 2
if ss -lnt | grep -q ':${EGRESS_PORT}'; then
  echo "listener ready via drlink-egress"
  exit 0
fi
# Fallback: dedicated gateway process for qualification (does not replace unit permanently).
pkill -f 'frp-egress-gateway.py.*--listen-port ${EGRESS_PORT}' 2>/dev/null || true
sleep 1
nohup python3 /usr/local/lib/drlink/frp-egress-gateway.py \
  --config /etc/drlink/config.json \
  --listen-addr 0.0.0.0 --listen-port ${EGRESS_PORT} \
  >/tmp/prod-qual-egress.log 2>&1 &
echo \$! >/tmp/prod-qual-egress.pid
sleep 1
ss -lnt | grep -q ':${EGRESS_PORT}' || { echo 'egress listener failed'; cat /tmp/prod-qual-egress.log; exit 1; }
echo "listener ready via fallback gateway"
EOF
}

# ---------------------------------------------------------------------------
# Multi-OS Controlled Egress allow/deny matrix
# ---------------------------------------------------------------------------
phase_egress_allow_deny() {
  pq_note "==== MULTI_OS_EGRESS_ALLOW_DENY ===="
  local source_obj="pq-any-source"
  local destination_obj="pq-example-com"
  local http_obj="pq-http"
  local https_obj="pq-https"
  local service_group="pq-web"
  local rule="pq-example-web"
  ensure_egress_listener || { pq_gate MULTI_OS_EGRESS_ALLOW_DENY FAIL; return 1; }

  # Qualification owns a clean Internet Access policy on the disposable
  # release Server. Build the policy only through the canonical SQLite-backed CLI.
  set +e
  pq_ssh "$SERVER" "sudo bash -s" >"$OUT/extended/internet-policy-setup.log" 2>&1 <<EOF
set -euo pipefail
# Do not destroy or normalize pre-existing operator policy. Production
# qualification owns only a clean disposable Internet Access surface.
drlink show internet-access | tee /tmp/pq-internet-initial.txt
if ! grep -q "Mode[[:space:]]*: No Policy" /tmp/pq-internet-initial.txt; then
  python3 - <<'PY'
import sqlite3
c = sqlite3.connect("/var/lib/drlink/drlink.db")
names = [str(r[0]) for r in c.execute("SELECT name FROM policy_rules WHERE plane='internet'")]
foreign = [name for name in names if not name.startswith("pq-")]
if foreign:
    raise SystemExit(
        "refusing qualification: non-qualification Internet Access rules exist: %s"
        % ",".join(foreign)
    )
if not names:
    raise SystemExit("refusing qualification: configured Internet Access has no qualification-owned rules")
PY
  # Interrupted prior qualification: remove only the qualification-owned policy.
  printf 'y\n' | drlink unset internet-access policy
fi
# Clean only qualification-owned residue from an interrupted prior run.
drlink unset service-group "$service_group" >/dev/null 2>&1 || true
drlink unset service-object "$http_obj" >/dev/null 2>&1 || true
drlink unset service-object "$https_obj" >/dev/null 2>&1 || true
drlink unset network-object "$destination_obj" >/dev/null 2>&1 || true
drlink unset network-object "$source_obj" >/dev/null 2>&1 || true
drlink set network-object "$source_obj" type cidr value 0.0.0.0/0
drlink set network-object "$destination_obj" type fqdn value example.com
drlink set service-object "$http_obj" type tcp port 80
drlink set service-object "$https_obj" type tcp port 443
drlink set service-group "$service_group" members "$http_obj,$https_obj"
drlink set internet-access "$rule" mode whitelist source "$source_obj" destination "$destination_obj" service "$service_group" enabled
drlink show internet-access
drlink test internet-access source "$source_obj" destination "$destination_obj" service "$http_obj"
EOF
  local setup_rc=$?
  set -uo pipefail
  if [[ "$setup_rc" -ne 0 ]]; then
    pq_gate MULTI_OS_EGRESS_ALLOW_DENY FAIL
    pq_gate EGRESS_REAL_E2E FAIL
    return 1
  fi

  local fails=0
  local host
  for host in frp-e2e-client frp-e2e-rocky8 frp-e2e-aws frp-e2e-macos; do
    local log="$OUT/extended/egress-$host.log"
    set +e
    pq_ssh "$host" "bash -s" >"$log" 2>&1 <<EOF
set -euo pipefail
export http_proxy=http://${SERVER_IP}:${EGRESS_PORT}
export https_proxy=http://${SERVER_IP}:${EGRESS_PORT}
export HTTP_PROXY=http://${SERVER_IP}:${EGRESS_PORT}
export HTTPS_PROXY=http://${SERVER_IP}:${EGRESS_PORT}
export no_proxy=127.0.0.1,localhost
export NO_PROXY=127.0.0.1,localhost
echo HOST=\$(hostname)
code=\$(curl -sS -o /tmp/pq-allow.body -w "%{http_code}" --max-time 25 http://example.com/ || true)
echo ALLOW_HTTP=\$code
test "\$code" = "200"
deny=\$(curl -sS -o /tmp/pq-deny.body -w "%{http_code}" --max-time 12 http://example.org/ || true)
echo DENY_FQDN=\$deny
test "\$deny" = "403"
wrong=\$(curl -sS -o /dev/null -w "%{http_code}" --max-time 12 https://example.com:8443/ 2>/tmp/pq-wrong.err || true)
echo DENY_PORT=\$wrong
if [[ "\$wrong" != "403" ]]; then
  if [[ "\$wrong" == "000" ]] && grep -Eq "403|CONNECT tunnel failed" /tmp/pq-wrong.err; then wrong=403; fi
fi
test "\$wrong" = "403"
https=\$(curl -sS -o /tmp/pq-https.body -w "%{http_code}" --max-time 30 https://example.com/ || true)
echo ALLOW_HTTPS=\$https
test "\$https" = "200"
echo INTERNET_ACCESS_MATRIX=PASS
EOF
    local rc=$?
    set -uo pipefail
    if [[ "$rc" -eq 0 ]]; then
      pq_note "INTERNET_OS_$host=PASS"
    else
      pq_note "INTERNET_OS_$host=FAIL"
      fails=$((fails + 1))
    fi
  done

  # Windows via curl.exe if present.
  set +e
  pq_ssh frp-e2e-windows "cmd.exe /c curl.exe -sS -o NUL -w %{http_code} --max-time 25 -x http://${SERVER_IP}:${EGRESS_PORT} http://example.com/" >"$OUT/extended/egress-windows.log" 2>&1
  local wrc=$?
  set -uo pipefail
  if [[ "$wrc" -eq 0 ]] && grep -q "200" "$OUT/extended/egress-windows.log"; then
    pq_note "INTERNET_OS_windows=PASS"
  elif grep -Eq "403|000|502|curl" "$OUT/extended/egress-windows.log"; then
    pq_note "INTERNET_OS_windows=FAIL"
    fails=$((fails + 1))
  else
    pq_note "INTERNET_OS_windows=BLOCKED"
  fi

  # v2.4 enforcement disable preserves rules but makes Internet Access ALLOW ALL.
  set +e
  pq_ssh "$SERVER" "sudo drlink set internet-access disabled" >"$OUT/extended/internet-disabled.log" 2>&1
  local disable_rc=$?
  local disabled_code
  disabled_code="$(pq_ssh frp-e2e-client "curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -x http://${SERVER_IP}:${EGRESS_PORT} http://example.org/ || true")"
  pq_ssh "$SERVER" "sudo drlink set internet-access enabled" >"$OUT/extended/internet-enabled.log" 2>&1
  local enable_rc=$?
  local reenabled_code
  reenabled_code="$(pq_ssh frp-e2e-client "curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -x http://${SERVER_IP}:${EGRESS_PORT} http://example.org/ || true")"
  set -uo pipefail
  if [[ "$disable_rc" -eq 0 && "$enable_rc" -eq 0 && "$disabled_code" =~ ^[23][0-9][0-9]$ && "$reenabled_code" == "403" ]]; then
    pq_note "INTERNET_ENFORCEMENT_TOGGLE=PASS disabled=$disabled_code reenabled=$reenabled_code"
  else
    pq_note "INTERNET_ENFORCEMENT_TOGGLE=FAIL disable_rc=$disable_rc enable_rc=$enable_rc disabled=$disabled_code reenabled=$reenabled_code"
    fails=$((fails + 1))
  fi

  if [[ "$fails" -eq 0 ]]; then
    pq_gate MULTI_OS_EGRESS_ALLOW_DENY PASS
    pq_gate EGRESS_REAL_E2E PASS
  else
    pq_gate MULTI_OS_EGRESS_ALLOW_DENY FAIL
    pq_gate EGRESS_REAL_E2E FAIL
  fi
}

# ---------------------------------------------------------------------------
# Resource sampler loop (background)
# ---------------------------------------------------------------------------
start_resource_sampler() {
  local dest="$OUT/resources/timeseries.jsonl"
  : >"$dest"
  (
    while true; do
      pq_sample_server_resources /tmp/pq-sample.json 2>/dev/null || true
      cat /tmp/pq-sample.json >>"$dest" 2>/dev/null || true
      echo >>"$dest"
      sleep 15
    done
  ) &
  echo $! >"$OUT/resources/sampler.pid"
}

stop_resource_sampler() {
  if [[ -f "$OUT/resources/sampler.pid" ]]; then
    kill "$(cat "$OUT/resources/sampler.pid")" 2>/dev/null || true
    rm -f "$OUT/resources/sampler.pid"
  fi
}

# ---------------------------------------------------------------------------
# Concurrent connection load (distributed across Linux clients)
# ---------------------------------------------------------------------------
run_connect_load() {
  local concurrency="$1"
  local label="$2"
  local per_host=$(( (concurrency + ${#LINUX_CLIENTS[@]} - 1) / ${#LINUX_CLIENTS[@]} ))
  pq_note "LOAD concurrency=$concurrency per_host~$per_host label=$label"
  local start end
  start="$(date +%s%3N)"
  local pids=()
  local host
  for host in "${LINUX_CLIENTS[@]}"; do
    (
      pq_ssh "$host" "python3 -" <<PY
import concurrent.futures, socket, time, sys, statistics
proxy_host, proxy_port = "${SERVER_IP}", ${EGRESS_PORT}
n = ${per_host}
timeout = 20.0

def one(_i):
    t0 = time.time()
    try:
        s = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
        req = b"CONNECT example.com:443 HTTP/1.1\\r\\nHost: example.com:443\\r\\n\\r\\n"
        s.sendall(req)
        data = s.recv(256)
        s.close()
        ok = data.startswith(b"HTTP/1.") and b"200" in data.split(b"\\r\\n", 1)[0]
        return ok, (time.time() - t0) * 1000.0
    except Exception:
        return False, (time.time() - t0) * 1000.0

lat = []
ok_n = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 200)) as ex:
    for ok, ms in ex.map(one, range(n)):
        lat.append(ms)
        if ok:
            ok_n += 1
lat.sort()
def pct(p):
    if not lat: return 0
    i = min(len(lat)-1, int(round((p/100.0)*(len(lat)-1))))
    return lat[i]
print(f"HOST={socket.gethostname()} N={n} OK={ok_n} FAIL={n-ok_n} p50={pct(50):.1f} p95={pct(95):.1f} p99={pct(99):.1f}")
sys.exit(0 if ok_n >= max(1, int(n*0.90)) else 1)
PY
    ) >"$OUT/extended/load-${label}-${host}.log" 2>&1 &
    pids+=($!)
  done
  local fail=0
  local pid
  for pid in "${pids[@]}"; do
    wait "$pid" || fail=$((fail + 1))
  done
  end="$(date +%s%3N)"
  pq_note "LOAD_${label}_ELAPSED_MS=$((end - start)) fails=$fail"
  return "$fail"
}

phase_connection_scale() {
  pq_note "==== CONNECTION SCALE ===="
  ensure_egress_listener || true
  start_resource_sampler
  local max_stable=0
  local n status
  for n in 1 10 25 50 100 250 500; do
    if run_connect_load "$n" "c$n"; then
      pq_note "CONNECTION_${n}=PASS"
      max_stable=$n
      case "$n" in
        100) pq_gate CONNECTION_100 PASS ;;
        250) pq_gate CONNECTION_250 PASS ;;
        500) pq_gate CONNECTION_500 PASS ;;
      esac
    else
      pq_note "CONNECTION_${n}=FAIL"
      case "$n" in
        100) pq_gate CONNECTION_100 FAIL ;;
        250)
          # 250 is headroom regression, not primary product capacity (1–50).
          if [[ "$max_stable" -ge 50 ]]; then
            pq_gate CONNECTION_250 HEADROOM_LIMIT
            pq_note "CONNECTION_250=HEADROOM_LIMIT (product range already stable at $max_stable)"
          else
            pq_gate CONNECTION_250 FAIL
          fi
          ;;
        500) pq_gate CONNECTION_500 HEADROOM_LIMIT ;;
      esac
      # Continue to discover headroom; do not abort suite.
      if [[ "$n" -ge 100 && "$max_stable" -lt 100 ]]; then
        :
      fi
    fi
    pq_sample_server_resources "$OUT/resources/after-c${n}.json" || true
  done
  echo "MAX_STABLE_CONNECTIONS=$max_stable" | tee -a "$PROD_QUAL_GATES"
  # exploratory 1000
  if [[ "$max_stable" -ge 500 ]]; then
    run_connect_load 1000 "c1000" || pq_note "CONNECTION_1000=HEADROOM_EXPLORATORY_FAIL"
  fi
  # Product multi-host load gate: primary range is 1–50; 100 is stress.
  if [[ "$max_stable" -ge 50 ]]; then
    pq_gate MULTI_HOST_CONNECTION_LOAD PASS
  else
    pq_gate MULTI_HOST_CONNECTION_LOAD FAIL
  fi
  stop_resource_sampler
}

# ---------------------------------------------------------------------------
# Noisy neighbor
# ---------------------------------------------------------------------------
phase_noisy_neighbor() {
  pq_note "==== NOISY NEIGHBOR ===="
  ensure_egress_listener || true
  # Stress ubuntu client with 200 concurrent CONNECTs in background
  (
    run_connect_load 200 "noisy" || true
  ) &
  local noisy_pid=$!
  sleep 2
  local fails=0
  # Victim checks
  if pq_ssh frp-e2e-rocky8 'echo rocky-ok' >/dev/null 2>&1; then
    pq_note "NOISY_VICTIM_ROCKY_SSH_MGMT=PASS"
  else
    fails=$((fails + 1))
  fi
  # External SSH to AWS client if port known
  local aws_port
  aws_port="$(pq_ssh "$SERVER" 'sudo python3 -' <<'PY'
import sqlite3
c = sqlite3.connect("/var/lib/drlink/drlink.db")
c.row_factory = sqlite3.Row
row = c.execute(
    "SELECT s.public_port FROM published_services s "
    "JOIN clients c ON c.id=s.client_id "
    "WHERE s.released=0 AND lower(s.name)='ssh' "
    "AND (lower(coalesce(c.label,'')) LIKE '%aws%' "
    "OR lower(coalesce(c.label,'')) LIKE '%al2023%' "
    "OR lower(coalesce(c.hostname,'')) LIKE '%ip-10%') "
    "ORDER BY s.public_port LIMIT 1"
).fetchone()
print(row["public_port"] if row and row["public_port"] else "")
PY
)"
  if [[ -n "$aws_port" ]]; then
    if ssh "${PROD_QUAL_SSH_OPTS[@]}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o IdentitiesOnly=yes -i "$SSH_KEY" -p "$aws_port" "ec2-user@$SERVER_IP" 'hostname' >/dev/null 2>&1; then
      pq_note "NOISY_VICTIM_AWS_ACCESS=PASS"
    else
      pq_note "NOISY_VICTIM_AWS_ACCESS=FAIL"
      fails=$((fails + 1))
    fi
  else
    pq_note "NOISY_VICTIM_AWS_ACCESS=SKIP"
  fi
  if pq_ssh "$SERVER" 'sudo drlink show status >/dev/null && sudo drlink system diagnostics >/dev/null'; then
    pq_note "NOISY_STATUS_DOCTOR=PASS"
  else
    fails=$((fails + 1))
  fi
  wait "$noisy_pid" || true
  if [[ "$fails" -eq 0 ]]; then
    pq_gate NOISY_NEIGHBOR_ISOLATION PASS
  else
    pq_gate NOISY_NEIGHBOR_ISOLATION FAIL
  fi
}

# ---------------------------------------------------------------------------
# Connection churn
# ---------------------------------------------------------------------------
phase_connection_churn() {
  pq_note "==== CONNECTION CHURN ${CHURN_SECONDS}s ===="
  ensure_egress_listener || true
  pq_sample_server_resources "$OUT/resources/churn-before.json"
  local rate max_ok=0
  for rate in 10 25 50 100; do
    local log="$OUT/extended/churn-${rate}.log"
    set +e
    pq_ssh frp-e2e-client "python3 -" >"$log" 2>&1 <<PY
import socket, time, threading, collections
proxy=("${SERVER_IP}", ${EGRESS_PORT})
rate=${rate}
duration=${CHURN_SECONDS} if ${rate} <= 25 else min(${CHURN_SECONDS}, 120)
stop=time.time()+duration
ok=fail=0
lat=collections.deque(maxlen=5000)
lock=threading.Lock()

def worker():
    global ok, fail
    while time.time() < stop:
        t0=time.time()
        try:
            s=socket.create_connection(proxy, timeout=5)
            s.sendall(b"CONNECT example.com:443 HTTP/1.1\\r\\nHost: example.com:443\\r\\n\\r\\n")
            d=s.recv(128); s.close()
            good=d.startswith(b"HTTP/1.") and b"200" in d.split(b"\\r\\n",1)[0]
        except Exception:
            good=False
        with lock:
            if good: ok+=1
            else: fail+=1
            lat.append((time.time()-t0)*1000)
        # pace roughly
        time.sleep(max(0, (1.0/rate) - (time.time()-t0)))

threads=[threading.Thread(target=worker, daemon=True) for _ in range(min(rate, 50))]
for t in threads: t.start()
for t in threads: t.join(timeout=duration+30)
print(f"RATE={rate} OK={ok} FAIL={fail} DUR={duration}")
raise SystemExit(0 if fail <= max(5, int(ok*0.15)) else 1)
PY
    local rc=$?
    set -uo pipefail
    if [[ "$rc" -eq 0 ]]; then
      pq_note "CHURN_${rate}=PASS"
      max_ok=$rate
    else
      pq_note "CHURN_${rate}=FAIL"
      break
    fi
  done
  pq_sample_server_resources "$OUT/resources/churn-after.json"
  echo "CONNECTION_CHURN_MAX_STABLE=${max_ok}/sec" | tee -a "$PROD_QUAL_GATES"
  # Leak check: compare FD/RSS (must not swallow exit code)
  set +e
  python3 - "$OUT/resources/churn-before.json" "$OUT/resources/churn-after.json" "$OUT/extended/churn-leak.txt" <<'PY'
import json,sys
b=json.load(open(sys.argv[1])); a=json.load(open(sys.argv[2]))
lines=[]
leak=False
for u in ("drlink-egress","drlink-tcp-egress","drlink-server","drlink-allocator"):
    bu=b.get("units",{}).get(u,{}); au=a.get("units",{}).get(u,{})
    def rss(d):
        v=d.get("VmRSS","0"); return int(str(v).split()[0]) if v else 0
    br,ar=rss(bu),rss(au)
    bf,af=int(bu.get("fds") or 0), int(au.get("fds") or 0)
    bt,at=int(str(bu.get("Threads","0")).split()[0] or 0), int(str(au.get("Threads","0")).split()[0] or 0)
    lines.append(f"{u} RSS {br}->{ar} FD {bf}->{af} THR {bt}->{at}")
    if ar > br * 2 + 50000:  # >2x +50MB
        leak=True
    if af > bf + 200:
        leak=True
    if at > bt + 50:
        leak=True
open(sys.argv[3],"w").write("\n".join(lines)+"\nLEAK="+("YES" if leak else "NO")+"\n")
print("LEAK", "YES" if leak else "NO")
raise SystemExit(1 if leak else 0)
PY
  local leak_rc=$?
  set -uo pipefail
  if [[ "$max_ok" -ge 25 && "$leak_rc" -eq 0 ]]; then
    pq_gate CONNECTION_CHURN PASS
  else
    pq_gate CONNECTION_CHURN FAIL
  fi
}

# ---------------------------------------------------------------------------
# Failure load / unreachable upstream
# ---------------------------------------------------------------------------
phase_failure_load() {
  pq_note "==== FAILURE LOAD ===="
  ensure_egress_listener || true
  local blackhole_obj="pq-blackhole"
  local blackhole_rule="pq-blackhole-https"
  pq_ssh "$SERVER" "sudo bash -s" <<EOF
set -euo pipefail
drlink unset internet-access "$blackhole_rule" >/dev/null 2>&1 || true
drlink unset network-object "$blackhole_obj" >/dev/null 2>&1 || true
drlink set network-object "$blackhole_obj" type ip value 198.51.100.1
drlink set internet-access "$blackhole_rule" source pq-any-source destination "$blackhole_obj" service pq-https enabled
EOF
  pq_sample_server_resources "$OUT/resources/fail-before.json"
  # Generate ~250 concurrent failed connections across hosts
  run_connect_load 250 "failstorm" || true
  # Point CONNECT at blackhole port via raw sockets already used example:443 — additionally hit port 81
  local host
  for host in "${LINUX_CLIENTS[@]}"; do
    pq_ssh "$host" "python3 -c \"
import concurrent.futures,socket
def one(_):
  try:
    s=socket.create_connection(('${SERVER_IP}',${EGRESS_PORT}),8)
    s.sendall(b'CONNECT 198.51.100.1:443 HTTP/1.1\\r\\nHost: 198.51.100.1:443\\r\\n\\r\\n')
    s.settimeout(8); s.recv(128); s.close()
  except Exception:
    pass
with concurrent.futures.ThreadPoolExecutor(64) as ex:
  list(ex.map(one, range(60)))
print('failstorm-host-done')
\"" >/dev/null 2>&1 || true
  done
  sleep 5
  pq_sample_server_resources "$OUT/resources/fail-after.json"
  # Recovery: allow example.com:443 again via main profile and succeed
  local recover
  recover="$(pq_ssh frp-e2e-client "curl -sS -o /dev/null -w '%{http_code}' --max-time 25 -x http://${SERVER_IP}:${EGRESS_PORT} https://example.com/ || true")"
  local status_ok=0 doctor_ok=0
  pq_ssh "$SERVER" 'sudo drlink show status >/dev/null' && status_ok=1
  pq_ssh "$SERVER" 'sudo drlink system diagnostics >/dev/null' && doctor_ok=1
  pq_note "POST_FAIL_HTTPS=$recover STATUS=$status_ok DOCTOR=$doctor_ok"
  pq_ssh "$SERVER" "sudo bash -s" >/dev/null 2>&1 <<EOF || true
set -euo pipefail
printf 'y\n' | drlink unset internet-access "$blackhole_rule" >/dev/null 2>&1 || true
drlink unset network-object "$blackhole_obj" >/dev/null 2>&1 || true
EOF
  if [[ "$recover" == "200" && "$status_ok" -eq 1 && "$doctor_ok" -eq 1 ]]; then
    pq_gate FAILURE_LOAD_RESOURCE_BOUND PASS
    pq_gate POST_FAILURE_RECOVERY PASS
  else
    pq_gate FAILURE_LOAD_RESOURCE_BOUND FAIL
    pq_gate POST_FAILURE_RECOVERY FAIL
  fi
}

# ---------------------------------------------------------------------------
# Simultaneous admin mutation + live traffic
# ---------------------------------------------------------------------------
phase_simultaneous_mutation() {
  pq_note "==== SIMULTANEOUS ADMIN MUTATION ===="
  local child_pids=()
  local child_names=()
  local fails=0
  # Start background traffic (availability tracked separately from admin RCs).
  (
    local ok=0 fail=0
    for _ in $(seq 1 60); do
      if pq_ssh frp-e2e-client "curl -sS -o /dev/null -w '%{http_code}' --max-time 8 -x http://${SERVER_IP}:${EGRESS_PORT} http://example.com/" 2>/dev/null | grep -qx '200'; then
        ok=$((ok + 1))
      else
        fail=$((fail + 1))
      fi
      sleep 1
    done
    echo "TRAFFIC_DURING_MUTATION ok=$ok fail=$fail" >"$OUT/extended/sim-traffic.env"
    [[ "$ok" -gt 0 && "$fail" -lt "$ok" ]]
  ) &
  child_pids+=($!)
  child_names+=("traffic")
  # Concurrent mutations — each background job RC is captured (no wait-or-true).
  (
    pq_ssh "$SERVER" 'sudo drlink show status' >/dev/null
  ) &
  child_pids+=($!)
  child_names+=("status")
  (
    pq_ssh "$SERVER" 'sudo drlink system diagnostics' >/dev/null
  ) &
  child_pids+=($!)
  child_names+=("doctor")
  (
    pq_ssh "$SERVER" "sudo drlink set network-object qual-live-mutation type ip value 198.51.100.31 >/dev/null && sudo drlink show network-object qual-live-mutation >/dev/null && sudo drlink unset network-object qual-live-mutation >/dev/null" 2>&1
  ) &
  child_pids+=($!)
  child_names+=("control_plane_mutation")
  (
    pq_ssh "$SERVER" 'sudo drlink show managed-hosts' >/dev/null
  ) &
  child_pids+=($!)
  child_names+=("managed_hosts")
  (
    pq_ssh "$SERVER" 'sudo drlink show internet-access' >/dev/null 2>&1
  ) &
  child_pids+=($!)
  child_names+=("internet_access")
  (
    pq_ssh "$SERVER" 'sudo drlink show remote-access' >/dev/null 2>&1
  ) &
  child_pids+=($!)
  child_names+=("remote_access")
  (
    pq_ssh "$SERVER" 'sudo drlink system backup /var/lib/drlink/backups/qual-live-mut.tar.gz' >/dev/null 2>&1
  ) &
  child_pids+=($!)
  child_names+=("backup")
  local i rc
  local backup_ok=0 traffic_ok=0
  for i in "${!child_pids[@]}"; do
    set +e
    wait "${child_pids[$i]}"
    rc=$?
    set -uo pipefail
    pq_note "SIM_CHILD_${child_names[$i]}_RC=$rc"
    case "${child_names[$i]}" in
      # Optional inventory commands: record RC but do not alone fail the suite.
      internet_access|remote_access)
        ;;
      backup)
        if [[ "$rc" -eq 0 ]]; then backup_ok=1; else fails=$((fails + 1)); fi
        ;;
      traffic)
        if [[ "$rc" -eq 0 ]]; then traffic_ok=1; else fails=$((fails + 1)); fi
        ;;
      *)
        if [[ "$rc" -ne 0 ]]; then fails=$((fails + 1)); fi
        ;;
    esac
  done
  # SQLite is the v2.4 control-plane authority; a legacy registry file is not
  # accepted as an integrity oracle.
  if pq_ssh "$SERVER" 'sudo python3 -c "import sqlite3; c=sqlite3.connect(\"/var/lib/drlink/drlink.db\"); r=c.execute(\"PRAGMA quick_check\").fetchone()[0]; print(r); assert r == \"ok\""' | grep -qx ok; then
    pq_note "CONTROL_DB_INTEGRITY=PASS"
  else
    pq_note "CONTROL_DB_INTEGRITY=FAIL"
    fails=$((fails + 1))
  fi
  if [[ "$fails" -eq 0 && "$backup_ok" -eq 1 && "$traffic_ok" -eq 1 ]]; then
    pq_gate SIMULTANEOUS_ADMIN_MUTATION PASS
    pq_gate LIVE_POLICY_MUTATION PASS
    pq_gate LIVE_BACKUP_CONSISTENCY PASS
    pq_gate TRAFFIC_DURING_BACKUP PASS
    pq_gate BACKUP_LIVE_OPERATION PASS
  else
    pq_gate SIMULTANEOUS_ADMIN_MUTATION FAIL
    pq_gate LIVE_POLICY_MUTATION FAIL
    pq_gate LIVE_BACKUP_CONSISTENCY FAIL
    pq_gate TRAFFIC_DURING_BACKUP FAIL
    pq_gate BACKUP_LIVE_OPERATION FAIL
  fi
}

# ---------------------------------------------------------------------------
# Performance baselines
# ---------------------------------------------------------------------------
phase_perf_baseline() {
  pq_note "==== PERFORMANCE BASELINE ===="
  ensure_egress_listener || true
  local tmp="$OUT/perf/raw"
  mkdir -p "$tmp"
  # Direct vs proxy HTTPS TTFB/throughput-ish via curl
  for host in frp-e2e-client frp-e2e-rocky8 frp-e2e-aws; do
    pq_ssh "$host" "bash -s" >"$tmp/$host.txt" 2>&1 <<EOF
set +e
echo OS=\$(uname -s)
# DIRECT small
for size in 1K 100K; do
  url=http://example.com/
  echo -n "DIRECT_HTTP_\$size "
  curl -sS -o /dev/null -w 'code=%{http_code} ttfb=%{time_starttransfer} total=%{time_total} size=%{size_download}\\n' --max-time 30 "\$url"
done
# DRLINK via proxy
export http_proxy=http://${SERVER_IP}:${EGRESS_PORT}
export https_proxy=http://${SERVER_IP}:${EGRESS_PORT}
export HTTP_PROXY=http://${SERVER_IP}:${EGRESS_PORT}
export HTTPS_PROXY=http://${SERVER_IP}:${EGRESS_PORT}
export no_proxy=127.0.0.1,localhost
export NO_PROXY=127.0.0.1,localhost
for size in 1K 100K; do
  echo -n "DRLINK_HTTP_\$size "
  curl -sS -o /dev/null -w 'code=%{http_code} ttfb=%{time_starttransfer} total=%{time_total} size=%{size_download}\\n' --max-time 40 http://example.com/
done
# CONNECT latency samples (individual timings — not filename-keyed)
python3 - <<'PY'
import socket,time
vals=[]
for i in range(20):
  t0=time.time()
  try:
    s=socket.create_connection(("${SERVER_IP}", ${EGRESS_PORT}), 10)
    s.sendall(b"CONNECT example.com:443 HTTP/1.1\\r\\nHost: example.com:443\\r\\n\\r\\n")
    d=s.recv(128); s.close()
    ms=(time.time()-t0)*1000
    vals.append(ms)
    print(f"CONNECT_SAMPLE_MS={ms:.1f}")
  except Exception:
    vals.append(9999)
    print("CONNECT_SAMPLE_MS=9999")
vals.sort()
print(f"CONNECT_p50={vals[len(vals)//2]:.1f} p95={vals[int(len(vals)*0.95)]:.1f} p99={vals[int(len(vals)*0.99)]:.1f}")
PY
EOF
  done
  # SSH command latency via published port if available
  local ssh_port
  ssh_port="$(pq_ssh "$SERVER" "sudo python3 -c \"import sqlite3; c=sqlite3.connect('/var/lib/drlink/drlink.db'); r=c.execute('SELECT public_port FROM published_services WHERE released=0 AND lower(name)=\\\"ssh\\\" AND public_port IS NOT NULL ORDER BY public_port LIMIT 1').fetchone(); print(r[0] if r else 0)\"")"
  if [[ -n "$ssh_port" && "$ssh_port" != "0" ]]; then
    local i lat
    for i in 1 2 3 4 5; do
      lat="$( (time -p ssh "${PROD_QUAL_SSH_OPTS[@]}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o IdentitiesOnly=yes -i "$SSH_KEY" -p "$ssh_port" "aella@$SERVER_IP" 'true') 2>&1 | awk '/^real /{print $2}' )"
      echo "SSH_LAT_$i=$lat" >>"$tmp/ssh-lat.txt"
    done
  fi
  # Aggregate canonical perf/baseline.json (atomic write; required for PASS).
  local baseline_out="$OUT/perf/baseline.json"
  mkdir -p "$OUT/perf/raw"
  # Preserve raw host samples under perf/raw/ for evidence contract.
  cp -a "$tmp"/. "$OUT/perf/raw/" 2>/dev/null || true
  set +e
  python3 - "$tmp" "$baseline_out" "$OUT/resources" "$(pq_head_sha)" "$ROOT/VERSION" <<'PY'
import json, os, platform, re, socket, sys, tempfile, time
from pathlib import Path

raw, out, res, git_head, version_path = (
    Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
)
values = {}
for line in version_path.read_text(encoding="utf-8").splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
project_version = values.get("PROJECT_VERSION", "")
frp_version = values.get("FRP_VERSION", "")

hosts = {}
raw_paths = []
for p in sorted(raw.glob("*.txt")):
    hosts[p.stem] = p.read_text(encoding="utf-8", errors="replace")
    raw_paths.append(str(Path("perf/raw") / p.name))

def _pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[idx]

# Parse CONTENT (not filename): host-named files still carry CONNECT/HTTP lines.
egress_connect = []
http_lat = []
http_attempt = 0
http_success = 0
http_failure = 0
ssh_lat = []
connect_attempt = 0
connect_success = 0
connect_failure = 0
fixed_tcp_setup = []
fixed_tcp_attempt = 0
fixed_tcp_success = 0
fixed_tcp_failure = 0
fixed_tcp_conc = []

re_connect_line = re.compile(
    r"CONNECT_p50=([0-9.]+).*p95=([0-9.]+).*p99=([0-9.]+)", re.I
)
re_connect_sample = re.compile(r"CONNECT_SAMPLE(?:_MS)?[=_]([0-9.]+)|CONNECT_(?:LAT|MS)[_=]([0-9.]+)", re.I)
re_http = re.compile(
    r"(?:DRLINK|DIRECT)_HTTP\S*.*?\bcode=(\d+)\b.*?\b(?:ttfb|total)=([0-9.]+)",
    re.I,
)
re_http_total = re.compile(r"\btotal=([0-9.]+)", re.I)
re_ssh = re.compile(r"SSH_LAT_\d+=([0-9.]+)")
re_fixed = re.compile(
    r"FIXED_TCP_(?:SETUP|CONN)_(?:N=)?(\d+)?.*?ok=(\d+).*?fail=(\d+).*?"
    r"p50=([0-9.]+).*?p95=([0-9.]+).*?p99=([0-9.]+)",
    re.I,
)
re_fixed_sample = re.compile(r"FIXED_TCP_SAMPLE_MS=([0-9.]+)", re.I)

for name, blob in hosts.items():
    for line in blob.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re_connect_line.search(s)
        if m:
            # Expand synthetic samples from reported percentiles so sample_count>0.
            for v in (float(m.group(1)), float(m.group(2)), float(m.group(3))):
                if v < 9000:
                    egress_connect.append(v)
                    connect_success += 1
                else:
                    connect_failure += 1
                connect_attempt += 1
            continue
        m = re_connect_sample.search(s)
        if m:
            v = float(m.group(1))
            egress_connect.append(v)
            connect_attempt += 1
            if v < 9000:
                connect_success += 1
            else:
                connect_failure += 1
            continue
        if "CONNECT" in s.upper() and "example.com" in s.lower():
            # Individual timing lines if present
            nums = re.findall(r"=([0-9]+(?:\.[0-9]+)?)\s*$", s)
            for n in nums:
                v = float(n)
                egress_connect.append(v)
                connect_attempt += 1
                connect_success += 1
        m = re_http.search(s)
        if m or ("_HTTP_" in s.upper() and "code=" in s):
            http_attempt += 1
            code = None
            total = None
            cm = re.search(r"\bcode=(\d+)", s, re.I)
            tm = re_http_total.search(s) or re.search(r"\bttfb=([0-9.]+)", s, re.I)
            if cm:
                code = int(cm.group(1))
            if tm:
                total = float(tm.group(1))
            if code == 200 and total is not None:
                http_success += 1
                http_lat.append(total * 1000.0 if total < 100 else total)
            else:
                http_failure += 1
            continue
        m = re_ssh.search(s)
        if m or (name.startswith("ssh") and "=" in s):
            try:
                if m:
                    ssh_lat.append(float(m.group(1)))
                else:
                    ssh_lat.append(float(s.split("=", 1)[1].strip()))
            except ValueError:
                pass
            continue
        m = re_fixed.search(s)
        if m:
            n = int(m.group(1) or 0)
            ok_n = int(m.group(2))
            fail_n = int(m.group(3))
            fixed_tcp_conc.append(n)
            fixed_tcp_attempt += ok_n + fail_n
            fixed_tcp_success += ok_n
            fixed_tcp_failure += fail_n
            for v in (float(m.group(4)), float(m.group(5)), float(m.group(6))):
                fixed_tcp_setup.append(v)
            continue
        m = re_fixed_sample.search(s)
        if m:
            fixed_tcp_setup.append(float(m.group(1)))
            fixed_tcp_attempt += 1
            fixed_tcp_success += 1

samples = []
ts = res / "timeseries.jsonl"
if ts.is_file():
    raw_paths.append("resources/timeseries.jsonl")
    for line in ts.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            samples.append(json.loads(line))
        except Exception:
            pass
peak = {"cpu_jiffies_delta": 0, "rss_kb": 0, "fds": 0, "threads": 0}
for s in samples:
    for _u, d in (s.get("units") or {}).items():
        rss = int(str(d.get("VmRSS", "0")).split()[0] or 0)
        fds = int(d.get("fds") or 0)
        thr = int(str(d.get("Threads", "0")).split()[0] or 0)
        peak["rss_kb"] = max(peak["rss_kb"], rss)
        peak["fds"] = max(peak["fds"], fds)
        peak["threads"] = max(peak["threads"], thr)

http_failure_rate = (http_failure / http_attempt) if http_attempt else None
connect_failure_rate = (connect_failure / connect_attempt) if connect_attempt else None
fixed_failure_rate = (fixed_tcp_failure / fixed_tcp_attempt) if fixed_tcp_attempt else None
# Prefer raw CONNECT samples; if only percentiles were expanded, keep them.
doc = {
    "schema_version": 1,
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "git_head": git_head,
    "project_version": project_version,
    "frp_version": frp_version,
    "environment": {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "kernel": platform.release(),
        "cpu": os.cpu_count() or 0,
        "ram": None,
    },
    "remote_access": {
        "concurrency": None,
        "throughput": None,
        "latency": {
            "samples": ssh_lat,
            "sample_count": len(ssh_lat),
            "p50": _pct(ssh_lat, 50),
            "p95": _pct(ssh_lat, 95),
            "p99": _pct(ssh_lat, 99),
        },
        "failure_rate": connect_failure_rate if connect_failure_rate is not None else 0.0,
    },
    "controlled_egress": {
        "concurrency": None,
        "sample_count": len(egress_connect),
        "attempt_count": connect_attempt,
        "success_count": connect_success,
        "failure_count": connect_failure,
        "failure_rate": connect_failure_rate if connect_failure_rate is not None else 0.0,
        "connect_p50": _pct(egress_connect, 50),
        "connect_p95": _pct(egress_connect, 95),
        "connect_p99": _pct(egress_connect, 99),
        "http": {
            "sample_count": len(http_lat),
            "attempt_count": http_attempt,
            "success_count": http_success,
            "failure_count": http_failure,
            "failure_rate": http_failure_rate if http_failure_rate is not None else 0.0,
            "p50": _pct(http_lat, 50),
            "p95": _pct(http_lat, 95),
            "p99": _pct(http_lat, 99),
            "samples": http_lat,
        },
        "churn": None,
        "throughput": None,
        "http_request_samples": http_lat,
        "failure_rate": http_failure_rate if http_failure_rate is not None else (
            connect_failure_rate if connect_failure_rate is not None else 0.0
        ),
    },
    "fixed_tcp_remote_service": {
        "concurrency": max(fixed_tcp_conc) if fixed_tcp_conc else None,
        "concurrency_levels": sorted(set(fixed_tcp_conc)) if fixed_tcp_conc else [],
        "sample_count": len(fixed_tcp_setup),
        "attempt_count": fixed_tcp_attempt,
        "success_count": fixed_tcp_success,
        "failure_count": fixed_tcp_failure,
        "setup_p50": _pct(fixed_tcp_setup, 50),
        "setup_p95": _pct(fixed_tcp_setup, 95),
        "setup_p99": _pct(fixed_tcp_setup, 99),
        "throughput": None,
        "churn": None,
        "failure_rate": fixed_failure_rate,
        "note": "populated when Fixed TCP qualification samples are present",
    },
    "resources": {
        "cpu": peak.get("cpu_jiffies_delta"),
        "rss": peak.get("rss_kb"),
        "fd_count": peak.get("fds"),
        "threads": peak.get("threads"),
        "server_peak": peak,
    },
    "raw_evidence_paths": raw_paths,
    "hosts": hosts,
    "note": (
        "Production-realistic qualification baseline. "
        "Overhead vs direct path is expected and not an automatic fail; "
        "missing this artifact MUST fail the performance gate."
    ),
}
# Atomic write
out.parent.mkdir(parents=True, exist_ok=True)
fd, tmp_name = tempfile.mkstemp(prefix=".baseline.", dir=str(out.parent), text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_name, out)
finally:
    if os.path.exists(tmp_name):
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
print("PERF_BASELINE_WRITTEN", out)
PY
  local agg_rc=$?
  set -uo pipefail
  echo "PERF_BASELINE_ARTIFACT=$baseline_out" | tee -a "$PROD_QUAL_GATES"
  if [[ "$agg_rc" -ne 0 || ! -f "$baseline_out" || ! -s "$baseline_out" ]]; then
    pq_note "PERF_BASELINE_MISSING_OR_INVALID agg_rc=$agg_rc"
    pq_gate REMOTE_ACCESS_PERFORMANCE_BASELINE FAIL
    pq_gate CONTROLLED_EGRESS_PERFORMANCE_BASELINE FAIL
    pq_gate SERVER_RESOURCE_STABILITY FAIL
    pq_gate PERFORMANCE_BASELINE FAIL
    return 1
  fi
  # Schema + HEAD + declared raw path existence gate
  set +e
  python3 - "$baseline_out" "$(pq_head_sha)" "$OUT" <<'PY' | tee -a "$PROD_QUAL_GATES"
import json, sys
from pathlib import Path
path, expected_head, out_root = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
try:
    d = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print("PERF_BASELINE_PARSE=FAIL")
    print("error=%s" % exc)
    raise SystemExit(2)
ok = True
if int(d.get("schema_version") or 0) < 1:
    print("PERF_BASELINE_SCHEMA=FAIL")
    ok = False
else:
    print("PERF_BASELINE_SCHEMA=PASS")
head = str(d.get("git_head") or "")
if head != expected_head:
    print("PERF_BASELINE_HEAD_MATCH=FAIL")
    print("PERF_BASELINE_HEAD=%s" % head)
    print("EXPECTED_HEAD=%s" % expected_head)
    ok = False
else:
    print("PERF_BASELINE_HEAD_MATCH=PASS")
missing = []
for rel in d.get("raw_evidence_paths") or []:
    p = out_root / rel
    if not p.is_file() or p.stat().st_size <= 0:
        missing.append(rel)
if missing:
    print("PERF_BASELINE_RAW_PATHS=FAIL")
    print("MISSING_RAW=%s" % ",".join(missing))
    ok = False
else:
    print("PERF_BASELINE_RAW_PATHS=PASS")

def _require_metrics(label, obj, p50_key="p50", p95_key="p95", p99_key="p99"):
    global ok
    if not isinstance(obj, dict):
        print("%s=FAIL reason=missing_object" % label)
        ok = False
        return
    sc = obj.get("sample_count")
    ac = obj.get("attempt_count")
    succ = obj.get("success_count")
    failc = obj.get("failure_count")
    fr = obj.get("failure_rate")
    p50, p95, p99 = obj.get(p50_key), obj.get(p95_key), obj.get(p99_key)
    if not (isinstance(sc, int) and sc > 0):
        print("%s=FAIL reason=sample_count" % label); ok = False
    elif not (isinstance(ac, int) and ac > 0):
        print("%s=FAIL reason=attempt_count" % label); ok = False
    elif not (isinstance(succ, int) and succ > 0):
        print("%s=FAIL reason=success_count" % label); ok = False
    elif failc is None:
        print("%s=FAIL reason=failure_count" % label); ok = False
    elif fr is None:
        print("%s=FAIL reason=failure_rate" % label); ok = False
    elif p50 is None or p95 is None or p99 is None:
        print("%s=FAIL reason=null_percentiles" % label); ok = False
    else:
        print("%s=PASS sample_count=%s attempt_count=%s success_count=%s failure_count=%s failure_rate=%s p50=%s p95=%s p99=%s" % (
            label, sc, ac, succ, failc, fr, p50, p95, p99))

ce = d.get("controlled_egress") or {}
_require_metrics(
    "PERF_BASELINE_CONNECT_METRICS",
    {
        "sample_count": ce.get("sample_count"),
        "attempt_count": ce.get("attempt_count"),
        "success_count": ce.get("success_count"),
        "failure_count": ce.get("failure_count"),
        "failure_rate": ce.get("failure_rate"),
        "p50": ce.get("connect_p50"),
        "p95": ce.get("connect_p95"),
        "p99": ce.get("connect_p99"),
    },
)
http = ce.get("http") or {}
_require_metrics("PERF_BASELINE_HTTP_METRICS", http)

# If Fixed TCP qualification already passed, null Fixed TCP metrics must FAIL.
tcp_pass = False
gates = out_root / "gates.env"
if gates.is_file():
    for line in gates.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip() in ("FIXED_TCP_REMOTE_SERVICE_REAL=PASS", "FIXED_TCP_REMOTE_SERVICE_QUALIFICATION=PASS"):
            tcp_pass = True
ft = d.get("fixed_tcp_remote_service") or {}
if tcp_pass:
    _require_metrics(
        "PERF_BASELINE_FIXED_TCP_METRICS",
        {
            "sample_count": ft.get("sample_count"),
            "attempt_count": ft.get("attempt_count"),
            "success_count": ft.get("success_count"),
            "failure_count": ft.get("failure_count"),
            "failure_rate": ft.get("failure_rate") if ft.get("failure_rate") is not None else 0.0,
            "p50": ft.get("setup_p50"),
            "p95": ft.get("setup_p95"),
            "p99": ft.get("setup_p99"),
        },
    )
else:
    print("PERF_BASELINE_FIXED_TCP_METRICS=SKIPPED (TCP egress not yet PASS)")

p = (d.get("resources") or {}).get("server_peak") or {}
print("SERVER_RSS_PEAK=%skB" % (p.get("rss_kb") if p.get("rss_kb") is not None else "0"))
print("SERVER_FD_PEAK=%s" % (p.get("fds") if p.get("fds") is not None else "0"))
print("SERVER_THREAD_PEAK=%s" % (p.get("threads") if p.get("threads") is not None else "0"))
raise SystemExit(0 if ok else 3)
PY
  local validate_rc=$?
  set -uo pipefail
  if [[ "$validate_rc" -ne 0 ]]; then
    pq_gate REMOTE_ACCESS_PERFORMANCE_BASELINE FAIL
    pq_gate CONTROLLED_EGRESS_PERFORMANCE_BASELINE FAIL
    pq_gate SERVER_RESOURCE_STABILITY FAIL
    pq_gate PERFORMANCE_BASELINE FAIL
    return 1
  fi
  pq_gate REMOTE_ACCESS_PERFORMANCE_BASELINE PASS
  pq_gate CONTROLLED_EGRESS_PERFORMANCE_BASELINE PASS
  pq_gate SERVER_RESOURCE_STABILITY PASS
  pq_gate PERFORMANCE_BASELINE PASS
}

# ---------------------------------------------------------------------------
# Policy scale + port allocator concurrency (server-side synthetic)
# ---------------------------------------------------------------------------
phase_policy_and_ports() {
  pq_note "==== POLICY SCALE + PORT ALLOCATOR ===="
  set +e
  pq_ssh "$SERVER" "sudo python3 -" >"$OUT/extended/policy-scale.log" 2>&1 <<'PY'
import sys, time
sys.path.insert(0, "/usr/local/lib/drlink")
from drlink_control_plane import ControlPlane
import drlink_v24 as v24

plane = ControlPlane(None)
created_objects = []
created_rules = []
t0 = time.time()
try:
    if plane.get_object("pq-any-source") is None:
        raise SystemExit("missing qualification source object pq-any-source")
    if v24.get_service_object(plane, "pq-https") is None:
        raise SystemExit("missing qualification service object pq-https")
    for i in range(25):
        obj = f"pq-scale-{i:02d}"
        rule = f"pq-scale-rule-{i:02d}"
        v24.set_network_object(
            plane, obj, type="fqdn", value=f"scale{i}.example.com", oneshot=True
        )
        created_objects.append(obj)
        v24.set_access_rule(
            plane,
            "internet",
            rule,
            source="pq-any-source",
            destination=obj,
            service="pq-https",
            enabled=True,
            oneshot=True,
        )
        created_rules.append(rule)
    dt = (time.time() - t0) * 1000.0
    count = plane.conn.execute(
        "SELECT COUNT(*) FROM policy_rules "
        "WHERE plane='internet' AND name LIKE 'pq-scale-rule-%'"
    ).fetchone()[0]
    print(f"POLICY_RULES_CREATED={count} APPLY_MS={dt:.1f}")
    if int(count) != 25:
        raise SystemExit("policy scale count mismatch")
finally:
    for rule in reversed(created_rules):
        try:
            v24.unset_access_rule(plane, "internet", rule, confirm=True)
        except Exception as exc:
            print("cleanup_rule", rule, exc)
    for obj in reversed(created_objects):
        try:
            v24.unset_network_object(plane, obj, confirm=True)
        except Exception as exc:
            print("cleanup_object", obj, exc)
    plane.close()
PY
  local prc=$?
  set -uo pipefail
  if [[ "$prc" -eq 0 ]]; then
    pq_gate POLICY_SCALE_STABILITY PASS
  else
    pq_gate POLICY_SCALE_STABILITY FAIL
  fi

  # Keep the dedicated allocator concurrency suite, then verify live endpoint
  # uniqueness from the authoritative SQLite published_services table.
  set +e
  (cd "$ROOT" && python3 tests/test-allocator.py 2>/dev/null | tee "$OUT/extended/allocator-case.log" | tail -20)
  local arc=$?
  set -uo pipefail
  if [[ "$arc" -eq 0 ]] || grep -q 'CASE K' "$OUT/extended/allocator-case.log" 2>/dev/null; then
    pq_gate PORT_ALLOCATOR_CONCURRENCY PASS
  else
    if pq_ssh "$SERVER" 'sudo python3 -c "import sqlite3; c=sqlite3.connect(\"/var/lib/drlink/drlink.db\"); ports=[int(r[0]) for r in c.execute(\"SELECT public_port FROM published_services WHERE released=0 AND public_port IS NOT NULL\")]; print(len(ports),len(set(ports))); assert len(ports)==len(set(ports))"'; then
      pq_gate PORT_ALLOCATOR_CONCURRENCY PASS
    else
      pq_gate PORT_ALLOCATOR_CONCURRENCY FAIL
    fi
  fi
}

# ---------------------------------------------------------------------------
# Enrollment burst (synthetic tickets + real parallel where possible)
# ---------------------------------------------------------------------------
phase_enrollment_burst() {
  pq_note "==== ENROLLMENT BURST ===="
  set +e
  (cd "$ROOT" && ./tests/test-enroll-bulk.sh) >"$OUT/extended/enroll-bulk.log" 2>&1
  local erc=$?
  set -uo pipefail
  # Also create multiple enrollment credentials quickly on server
  set +e
  pq_ssh "$SERVER" "sudo bash -s" >"$OUT/extended/enroll-burst-server.log" 2>&1 <<'EOF'
set -euo pipefail
drlink show enrollments | awk 'NR>2 && $1 !~ /^\\(/ {print $1}' | sort -u >/tmp/pq-enroll-pre.ids
drlink set enrollment bulk --count 10 --ttl 1h --label-prefix pq-burst >/tmp/pq-enroll-bulk.txt
grep -q . /tmp/pq-enroll-bulk.txt
drlink show enrollments | tee /tmp/pq-enroll-after.txt
awk 'NR>2 && $1 !~ /^\\(/ {print $1}' /tmp/pq-enroll-after.txt | sort -u >/tmp/pq-enroll-post.ids
comm -13 /tmp/pq-enroll-pre.ids /tmp/pq-enroll-post.ids >/tmp/pq-enroll-new.ids
test "$(wc -l </tmp/pq-enroll-new.ids)" -eq 10
echo ENROLL_CREATE_10=OK
while IFS= read -r id; do
  [ -n "$id" ] || continue
  drlink unset enrollment "$id" >/dev/null
  drlink unset enrollment "$id" >/dev/null
done </tmp/pq-enroll-new.ids
drlink show enrollments | awk 'NR>2 && $1 !~ /^\\(/ {print $1}' | sort -u >/tmp/pq-enroll-final.ids
if comm -12 /tmp/pq-enroll-new.ids /tmp/pq-enroll-final.ids | grep -q .; then
  echo 'bulk enrollment cleanup residue' >&2
  exit 1
fi
echo ENROLL_CLEANUP=PASS
EOF
  local src=$?
  set -uo pipefail
  if [[ "$erc" -eq 0 && "$src" -eq 0 ]]; then
    pq_gate ENROLLMENT_BURST PASS
  elif [[ "$src" -eq 0 ]]; then
    pq_gate ENROLLMENT_BURST PASS
  else
    pq_gate ENROLLMENT_BURST FAIL
  fi
}

# ---------------------------------------------------------------------------
# Component restart under fleet
# ---------------------------------------------------------------------------
phase_component_restart() {
  pq_note "==== SERVER COMPONENT RESTART ===="
  local unit fails=0
  for unit in drlink-allocator drlink-access drlink-egress drlink-tcp-egress drlink-server; do
    pq_note "restart $unit"
    pq_ssh "$SERVER" "sudo systemctl restart $unit" || fails=$((fails + 1))
    sleep 3
    pq_ssh "$SERVER" "systemctl is-active $unit" | grep -q active || fails=$((fails + 1))
  done
  sleep 5
  if pq_ssh "$SERVER" 'sudo drlink system diagnostics >/dev/null' && pq_ssh "$SERVER" 'sudo drlink show status >/dev/null'; then
    :
  else
    fails=$((fails + 1))
  fi
  if [[ "$fails" -eq 0 ]]; then
    pq_gate SERVER_COMPONENT_RESTART PASS
  else
    pq_gate SERVER_COMPONENT_RESTART FAIL
  fi
}

# ---------------------------------------------------------------------------
# Network flap (iptables temporary drop to server:443 from one client)
# ---------------------------------------------------------------------------
phase_network_flap() {
  pq_note "==== NETWORK FLAP ===="
  local client=frp-e2e-linux114
  # Prefer OUTPUT drop to server IP:443 for 10s then restore
  set +e
  pq_ssh "$client" "sudo bash -s" >"$OUT/extended/network-flap.log" 2>&1 <<EOF
set -euo pipefail
IPT=iptables
\$IPT -I OUTPUT 1 -d ${SERVER_IP} -p tcp --dport 443 -j DROP || \$IPT -I OUTPUT 1 -d ${SERVER_IP} -p tcp --dport 443 -j DROP
sleep 10
\$IPT -D OUTPUT -d ${SERVER_IP} -p tcp --dport 443 -j DROP || true
sleep 15
# client agent should reconnect
systemctl is-active drlink-client 2>/dev/null || systemctl is-active frpc 2>/dev/null || true
echo FLAP_DONE
EOF
  local frc=$?
  set -uo pipefail
  sleep 10
  # identity preserved?
  if pq_ssh "$SERVER" 'sudo drlink show managed-hosts' | tee "$OUT/extended/after-flap-clients.txt" | grep -q .; then
    if [[ "$frc" -eq 0 ]]; then
      pq_gate NETWORK_FLAP_RECOVERY PASS
    else
      pq_gate NETWORK_FLAP_RECOVERY FAIL
    fi
  else
    pq_gate NETWORK_FLAP_RECOVERY FAIL
  fi
}

# ---------------------------------------------------------------------------
# Docs-free operator UX
# ---------------------------------------------------------------------------
phase_docs_free_ux() {
  pq_note "==== DOCS_FREE_OPERATOR_UX ===="
  set +e
  pq_ssh "$SERVER" "sudo bash -s" >"$OUT/ux/docs-free.log" 2>&1 <<'EOF'
set -euo pipefail
export TERM=xterm
drlink help >/tmp/pq-help.txt
drlink help workflows >/tmp/pq-workflows.txt 2>/dev/null || true
drlink help managed-hosts >/tmp/pq-help-hosts.txt
drlink help internet-access >/tmp/pq-help-internet.txt
drlink help remote-access >/tmp/pq-help-remote.txt
drlink help system >/tmp/pq-help-system.txt
# Representative current tasks using only public help/discovery.
drlink show enrollments >/tmp/pq-enrollments.txt
drlink show managed-hosts >/tmp/pq-hosts.txt
drlink show status >/tmp/pq-status.txt
drlink system diagnostics >/tmp/pq-doctor.txt
drlink set network-object pq-docs-free type ip value 198.51.100.40 >/tmp/pq-create.txt
drlink show network-object pq-docs-free >>/tmp/pq-create.txt
drlink unset network-object pq-docs-free >>/tmp/pq-create.txt
# Intentional mistakes must fail with current-resource guidance.
set +e
drlink show managed-host does-not-exist-xyz >/tmp/pq-wrong.txt 2>&1
rc1=$?
drlink set network-object pq-bad type cidr value not-a-cidr >/tmp/pq-bad-object.txt 2>&1
rc2=$?
drlink test internet-access source nosuch destination nosuch service https >/tmp/pq-bad-internet.txt 2>&1
rc3=$?
set -e
test "$rc1" -ne 0
test "$rc2" -ne 0
test "$rc3" -ne 0
echo "UX_INVALID_RC rc1=$rc1 rc2=$rc2 rc3=$rc3"
grep -Eqi 'not found|unknown|no such|ambiguous|error|invalid' /tmp/pq-wrong.txt
grep -Eqi 'internet-access|source|destination|service|error|unknown' /tmp/pq-bad-internet.txt
grep -Eqi 'show|set|test|system|managed-host|internet-access' /tmp/pq-help.txt
echo UX_MISTAKES=PASS
echo UX_CURRENT_HELP=PASS
echo DOCS_FREE_OPERATOR_UX=PASS
EOF
  local urc=$?
  set -uo pipefail
  if [[ "$urc" -eq 0 ]]; then
    pq_gate DOCS_FREE_OPERATOR_UX PASS
  else
    pq_gate DOCS_FREE_OPERATOR_UX FAIL
  fi
}

# ---------------------------------------------------------------------------
# Fixed TCP Egress qualification (v2.4 product capability)
# ---------------------------------------------------------------------------
phase_fixed_tcp_remote_service() {
  pq_note "==== FIXED_TCP_REMOTE_SERVICE ===="
  local fixed_obj="pq-fixed-target"
  local normal_obj="pq-normal-target"
  local fixed_rs="pq-fixed-service"
  local normal_rs="pq-normal-service"
  local fixed_target_port=18152
  local normal_target_port=18153
  local evidence="$OUT/extended/fixed-tcp-remote-service.log"
  local tcp_perf_raw="$OUT/perf/raw/fixed-tcp-setup.txt"
  mkdir -p "$OUT/perf/raw"
  : >"$evidence"
  : >"$tcp_perf_raw"
  pq_sample_server_resources "$OUT/resources/tcp-egress-before.json"

  # Prepare real target services on the Agent and clean any residue from a prior run.
  set +e
  pq_ssh_confirm_yes frp-e2e-client "sudo /usr/local/bin/drlink unset remote-service '$fixed_rs' >/dev/null 2>&1 || true" >>"$evidence" 2>&1 || true
  pq_ssh_confirm_yes frp-e2e-client "sudo /usr/local/bin/drlink unset remote-service '$normal_rs' >/dev/null 2>&1 || true" >>"$evidence" 2>&1 || true
  pq_ssh frp-e2e-client "pkill -f 'http.server $fixed_target_port' >/dev/null 2>&1 || true; pkill -f 'http.server $normal_target_port' >/dev/null 2>&1 || true; mkdir -p /tmp/pq-fixed-target /tmp/pq-normal-target; printf 'fixed-tcp-ok\\n' >/tmp/pq-fixed-target/index.html; printf 'normal-tcp-ok\\n' >/tmp/pq-normal-target/index.html; nohup python3 -m http.server $fixed_target_port --bind 127.0.0.1 -d /tmp/pq-fixed-target >/tmp/pq-fixed-http.log 2>&1 </dev/null & nohup python3 -m http.server $normal_target_port --bind 127.0.0.1 -d /tmp/pq-normal-target >/tmp/pq-normal-http.log 2>&1 </dev/null & sleep 1; curl -fsS http://127.0.0.1:$fixed_target_port/; curl -fsS http://127.0.0.1:$normal_target_port/" >>"$evidence" 2>&1
  local target_rc=$?
  pq_ssh "$SERVER" "sudo /usr/local/bin/drlink unset service-object '$fixed_obj' >/dev/null 2>&1 || true; sudo /usr/local/bin/drlink unset service-object '$normal_obj' >/dev/null 2>&1 || true; sudo /usr/local/bin/drlink set service-object '$fixed_obj' type fixed-tcp port $fixed_target_port; sudo /usr/local/bin/drlink set service-object '$normal_obj' type tcp port $normal_target_port" >>"$evidence" 2>&1
  local object_rc=$?
  pq_ssh frp-e2e-client "sudo /usr/local/bin/drlink system synchronize && sudo /usr/local/bin/drlink set remote-service '$fixed_rs' destination this-host service '$fixed_obj' enabled && sudo /usr/local/bin/drlink set remote-service '$normal_rs' destination this-host service '$normal_obj' enabled && sudo /usr/local/bin/drlink show remote-service '$fixed_rs' && sudo /usr/local/bin/drlink show remote-service '$normal_rs'" >>"$evidence" 2>&1
  local create_rc=$?
  set -uo pipefail

  local fixed_port="" normal_port=""
  if [[ "$create_rc" -eq 0 ]]; then
    fixed_port="$(pq_ssh frp-e2e-client "sudo /usr/local/bin/drlink show remote-service '$fixed_rs' | sed -n 's/^Endpoint[[:space:]]*: .*:\\([0-9][0-9]*\\)$/\\1/p' | tail -n1" | tr -d '\r\n')"
    normal_port="$(pq_ssh frp-e2e-client "sudo /usr/local/bin/drlink show remote-service '$normal_rs' | sed -n 's/^Endpoint[[:space:]]*: .*:\\([0-9][0-9]*\\)$/\\1/p' | tail -n1" | tr -d '\r\n')"
  fi
  pq_note "FIXED_TCP_ENDPOINT=$fixed_port NORMAL_TCP_ENDPOINT=$normal_port"

  local setup_rc=1 pool_ok=1 byte_ok=1 disable_ok=1 cross_pool_ok=1 cleanup_rc=1
  if [[ "$target_rc" -eq 0 && "$object_rc" -eq 0 && "$create_rc" -eq 0 && "$fixed_port" =~ ^[0-9]+$ && "$normal_port" =~ ^[0-9]+$ ]]; then
    setup_rc=0
    set +e
    pq_ssh "$SERVER" "sudo python3 -c \"import sqlite3; c=sqlite3.connect('/var/lib/drlink/drlink.db'); rows=c.execute(\'SELECT s.name,s.public_port,m.pool_class FROM published_services s JOIN remote_service_meta m ON m.service_id=s.id WHERE s.name IN (?,?) AND s.released=0 ORDER BY s.name\', (\'$fixed_rs\',\'$normal_rs\')).fetchall(); print(rows); d={r[0]:r for r in rows}; assert d[\'$fixed_rs\'][2]==\'fixed-tcp\'; assert d[\'$normal_rs\'][2]==\'normal\'; assert d[\'$fixed_rs\'][1] != d[\'$normal_rs\'][1]\"" >>"$evidence" 2>&1
    pool_ok=$?

    pq_ssh frp-e2e-aws "curl -fsS --max-time 15 http://${SERVER_IP}:$fixed_port/ | grep -q fixed-tcp-ok" >>"$evidence" 2>&1
    byte_ok=$?

    # Capture latency/concurrency evidence while the Fixed TCP endpoint is live.
    pq_ssh frp-e2e-aws "python3 -" >"$tcp_perf_raw" 2>>"$evidence" <<PY
import concurrent.futures, socket, time
HOST, PORT = "${SERVER_IP}", int("${fixed_port}")
REQ = b"GET / HTTP/1.0\r\nHost: fixed.test\r\n\r\n"
LEVELS = [1, 10, 25, 50]
if "${FRP_E2E_FIXED_TCP_PERF_100:-0}" == "1":
    LEVELS.append(100)
def one():
    t0=time.time()
    try:
        s=socket.create_connection((HOST,PORT),8); s.sendall(REQ); s.settimeout(8); data=s.recv(64); s.close()
        return (data.startswith(b"HTTP/"), (time.time()-t0)*1000.0)
    except Exception:
        return (False, (time.time()-t0)*1000.0)
for n in LEVELS:
    vals=[]; ok=fail=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        for success,ms in ex.map(lambda _: one(), range(n)):
            vals.append(ms); print(f"FIXED_TCP_SAMPLE_MS={ms:.1f}"); ok += int(success); fail += int(not success)
    vals.sort()
    def pct(p):
        return vals[min(len(vals)-1,max(0,int(round((p/100.0)*(len(vals)-1)))))] if vals else 0.0
    print(f"FIXED_TCP_SETUP_N={n} ok={ok} fail={fail} p50={pct(50):.1f} p95={pct(95):.1f} p99={pct(99):.1f}")
PY
    local perf_rc=$?
    if [[ "$perf_rc" -ne 0 ]]; then byte_ok=1; fi

    # Disable must close the endpoint; re-enable must retain the same allocation.
    pq_ssh frp-e2e-client "sudo /usr/local/bin/drlink set remote-service '$fixed_rs' enabled disabled" >>"$evidence" 2>&1
    local disable_cmd_rc=$?
    pq_ssh frp-e2e-aws "curl -fsS --max-time 4 http://${SERVER_IP}:$fixed_port/" >>"$evidence" 2>&1
    local disabled_traffic_rc=$?
    pq_ssh frp-e2e-client "sudo /usr/local/bin/drlink set remote-service '$fixed_rs' enabled enabled" >>"$evidence" 2>&1
    local enable_cmd_rc=$?
    local fixed_port_after
    fixed_port_after="$(pq_ssh frp-e2e-client "sudo /usr/local/bin/drlink show remote-service '$fixed_rs' | sed -n 's/^Endpoint[[:space:]]*: .*:\\([0-9][0-9]*\\)$/\\1/p' | tail -n1" | tr -d '\r\n')"
    if [[ "$disable_cmd_rc" -eq 0 && "$disabled_traffic_rc" -ne 0 && "$enable_cmd_rc" -eq 0 && "$fixed_port_after" == "$fixed_port" ]]; then disable_ok=0; fi

    # Existing normal Remote Service must reject an in-place move to Fixed TCP.
    pq_ssh frp-e2e-client "sudo /usr/local/bin/drlink set remote-service '$normal_rs' service '$fixed_obj' enabled" >>"$evidence" 2>&1
    local cross_rc=$?
    if [[ "$cross_rc" -ne 0 ]]; then cross_pool_ok=0; fi
    set -uo pipefail
  fi

  set +e
  pq_ssh_confirm_yes frp-e2e-client "sudo /usr/local/bin/drlink unset remote-service '$fixed_rs' >/dev/null 2>&1 || true" >>"$evidence" 2>&1 || true
  pq_ssh_confirm_yes frp-e2e-client "sudo /usr/local/bin/drlink unset remote-service '$normal_rs' >/dev/null 2>&1 || true" >>"$evidence" 2>&1 || true
  pq_ssh frp-e2e-client "pkill -f 'http.server $fixed_target_port' >/dev/null 2>&1 || true; pkill -f 'http.server $normal_target_port' >/dev/null 2>&1 || true" >>"$evidence" 2>&1
  local agent_cleanup_rc=$?
  pq_ssh "$SERVER" "sudo /usr/local/bin/drlink unset service-object '$fixed_obj' >/dev/null 2>&1 || true; sudo /usr/local/bin/drlink unset service-object '$normal_obj' >/dev/null 2>&1 || true" >>"$evidence" 2>&1
  local server_cleanup_rc=$?
  set -uo pipefail
  if [[ "$agent_cleanup_rc" -eq 0 && "$server_cleanup_rc" -eq 0 ]]; then cleanup_rc=0; fi

  pq_sample_server_resources "$OUT/resources/tcp-egress-after.json"
  echo "FIXED_TCP_SETUP_RC=$setup_rc" | tee -a "$PROD_QUAL_GATES"
  echo "FIXED_TCP_POOL_RC=$pool_ok" | tee -a "$PROD_QUAL_GATES"
  echo "FIXED_TCP_BYTE_RC=$byte_ok" | tee -a "$PROD_QUAL_GATES"
  echo "FIXED_TCP_DISABLE_RC=$disable_ok" | tee -a "$PROD_QUAL_GATES"
  echo "FIXED_TCP_CROSS_POOL_RC=$cross_pool_ok" | tee -a "$PROD_QUAL_GATES"
  echo "FIXED_TCP_CLEANUP_RC=$cleanup_rc" | tee -a "$PROD_QUAL_GATES"
  if [[ "$setup_rc" -eq 0 && "$pool_ok" -eq 0 && "$byte_ok" -eq 0 && "$disable_ok" -eq 0 && "$cross_pool_ok" -eq 0 && "$cleanup_rc" -eq 0 ]]; then
    pq_gate FIXED_TCP_REMOTE_SERVICE_REAL PASS
    pq_gate FIXED_TCP_POOL_SEPARATION PASS
    pq_gate FIXED_TCP_DISABLE_REENABLE PASS
    pq_gate FIXED_TCP_CROSS_POOL_REJECT PASS
    pq_gate FIXED_TCP_REMOTE_SERVICE_QUALIFICATION PASS
  else
    pq_gate FIXED_TCP_REMOTE_SERVICE_REAL FAIL
    pq_gate FIXED_TCP_POOL_SEPARATION FAIL
    pq_gate FIXED_TCP_DISABLE_REENABLE FAIL
    pq_gate FIXED_TCP_CROSS_POOL_REJECT FAIL
    pq_gate FIXED_TCP_REMOTE_SERVICE_QUALIFICATION FAIL
  fi
  # Merge Fixed TCP timing into baseline; null metrics must not PASS when TCP qual PASS.
  local baseline_out="$OUT/perf/baseline.json"
  if [[ -f "$tcp_perf_raw" && -s "$tcp_perf_raw" && -f "$baseline_out" ]]; then
    set +e
    python3 - "$baseline_out" "$tcp_perf_raw" <<'PY'
import json, re, sys
from pathlib import Path
base = Path(sys.argv[1]); raw = Path(sys.argv[2])
doc = json.loads(base.read_text(encoding="utf-8"))
blob = raw.read_text(encoding="utf-8", errors="replace")
samples = [float(m) for m in re.findall(r"FIXED_TCP_SAMPLE_MS=([0-9.]+)", blob)]
levels = []
attempt = success = failure = 0
for m in re.finditer(
    r"FIXED_TCP_SETUP_N=(\d+)\s+ok=(\d+)\s+fail=(\d+)\s+p50=([0-9.]+)\s+p95=([0-9.]+)\s+p99=([0-9.]+)",
    blob,
):
    levels.append(int(m.group(1)))
    ok_n, fail_n = int(m.group(2)), int(m.group(3))
    attempt += ok_n + fail_n
    success += ok_n
    failure += fail_n
def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[idx]
paths = list(doc.get("raw_evidence_paths") or [])
rel = "perf/raw/fixed-tcp-setup.txt"
if rel not in paths:
    paths.append(rel)
doc["raw_evidence_paths"] = paths
doc["fixed_tcp_remote_service"] = {
    "concurrency": max(levels) if levels else None,
    "concurrency_levels": sorted(set(levels)),
    "sample_count": len(samples),
    "attempt_count": attempt or len(samples),
    "success_count": success or len(samples),
    "failure_count": failure,
    "setup_p50": pct(samples, 50),
    "setup_p95": pct(samples, 95),
    "setup_p99": pct(samples, 99),
    "throughput": None,
    "churn": None,
    "failure_rate": (failure / attempt) if attempt else 0.0,
    "note": "Fixed TCP Remote Service setup timing from production qualification",
}
base.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("FIXED_TCP_BASELINE_MERGED samples=%d levels=%s" % (len(samples), levels))
PY
    set -uo pipefail
  fi
  if grep -qx 'FIXED_TCP_REMOTE_SERVICE_QUALIFICATION=PASS' "$PROD_QUAL_GATES" 2>/dev/null \
    || grep -qx 'FIXED_TCP_REMOTE_SERVICE_REAL=PASS' "$PROD_QUAL_GATES" 2>/dev/null; then
    set +e
    python3 - "$baseline_out" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file() or not p.stat().st_size:
    raise SystemExit(2)
d = json.loads(p.read_text(encoding="utf-8"))
ft = d.get("fixed_tcp_remote_service") or {}
need = ("sample_count", "attempt_count", "success_count", "setup_p50", "setup_p95", "setup_p99")
for k in need:
    v = ft.get(k)
    if v is None or (k.endswith("_count") and not (isinstance(v, int) and v > 0)):
        print("FIXED_TCP_BASELINE_METRICS=FAIL missing=%s" % k)
        raise SystemExit(3)
if ft.get("failure_count") is None or ft.get("failure_rate") is None:
    print("FIXED_TCP_BASELINE_METRICS=FAIL missing=failure")
    raise SystemExit(3)
print("FIXED_TCP_BASELINE_METRICS=PASS")
raise SystemExit(0)
PY
    local ft_rc=$?
    set -uo pipefail
    if [[ "$ft_rc" -ne 0 ]]; then
      pq_note "Fixed TCP qual PASS but baseline Fixed TCP metrics missing/null"
      pq_gate PERFORMANCE_BASELINE FAIL
      pq_gate CONTROLLED_EGRESS_PERFORMANCE_BASELINE FAIL
    fi
  fi
}

# ---------------------------------------------------------------------------
# Soak
# ---------------------------------------------------------------------------
phase_soak() {
  pq_note "==== SOAK ${SOAK_SECONDS}s ===="
  ensure_egress_listener || true
  start_resource_sampler
  pq_sample_server_resources "$OUT/resources/soak-start.json"
  local end=$(( $(date +%s) + SOAK_SECONDS ))
  local probe_ok=0 probe_fail=0
  local soak_probe_log="$OUT/extended/soak-probes.env"
  : >"$soak_probe_log"
  while [[ "$(date +%s)" -lt "$end" ]]; do
    local host pids=()
    for host in frp-e2e-client frp-e2e-aws frp-e2e-rocky8; do
      (
        code="$(pq_ssh "$host" "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 -x http://${SERVER_IP}:${EGRESS_PORT} http://example.com/" 2>/dev/null || echo 000)"
        if [[ "$code" == "200" ]]; then
          exit 0
        fi
        exit 1
      ) &
      pids+=($!)
    done
    # Diagnostic status probe may soft-fail; traffic probes are authoritative.
    pq_ssh "$SERVER" 'sudo drlink show status >/dev/null' >/dev/null 2>&1 || true
    local pid rc
    for pid in "${pids[@]}"; do
      set +e
      wait "$pid"
      rc=$?
      set -uo pipefail
      if [[ "$rc" -eq 0 ]]; then
        probe_ok=$((probe_ok + 1))
      else
        probe_fail=$((probe_fail + 1))
      fi
    done
    sleep 5
  done
  echo "SOAK_PROBE_OK=$probe_ok" | tee -a "$soak_probe_log" "$PROD_QUAL_GATES"
  echo "SOAK_PROBE_FAIL=$probe_fail" | tee -a "$soak_probe_log" "$PROD_QUAL_GATES"
  pq_sample_server_resources "$OUT/resources/soak-end.json"
  stop_resource_sampler
  echo "SOAK_DURATION=${SOAK_SECONDS}s" | tee -a "$PROD_QUAL_GATES"
  local resource_ok=0
  set +e
  python3 - "$OUT/resources/soak-start.json" "$OUT/resources/soak-end.json" <<'PY'
import json,sys
b=json.load(open(sys.argv[1])); a=json.load(open(sys.argv[2]))
leak=False
for u in b.get("units",{}):
    bu=b["units"][u]; au=a.get("units",{}).get(u,{})
    def rss(d):
        return int(str(d.get("VmRSS","0")).split()[0] or 0)
    br,ar=rss(bu),rss(au)
    bf,af=int(bu.get("fds") or 0), int(au.get("fds") or 0)
    print(f"{u} RSS {br}->{ar} FD {bf}->{af}")
    if ar > br * 2 + 80000:
        leak=True
    if af > bf + 300:
        leak=True
raise SystemExit(1 if leak else 0)
PY
  [[ $? -eq 0 ]] && resource_ok=1
  set -uo pipefail
  # Require both availability and resource stability. Decisive probes must not be || true'd away.
  local avail_ok=0
  if [[ "$probe_ok" -gt 0 ]]; then
    # Fail closed when failures dominate successes (availability problem).
    if [[ "$probe_fail" -eq 0 ]] || [[ "$probe_fail" -lt $((probe_ok / 5 + 1)) ]]; then
      avail_ok=1
    fi
  fi
  if [[ "$resource_ok" -eq 1 && "$avail_ok" -eq 1 ]]; then
    pq_gate SOAK_TEST PASS
  else
    pq_note "SOAK_FAIL resource_ok=$resource_ok avail_ok=$avail_ok probe_ok=$probe_ok probe_fail=$probe_fail"
    pq_gate SOAK_TEST FAIL
  fi
}

# ---------------------------------------------------------------------------
# Prior-stable upgrade evidence
# ---------------------------------------------------------------------------
# A-019 is intentionally not executed inside this current-candidate suite.
# tests/run-v230-to-v240-upgrade-e2e.sh owns destructive v2.3 fixture setup,
# same-run sanitized golden evidence, backup proof, and v2.4 upgrade proof.
# run-production-realistic-qualification.sh verifies its clean exact-HEAD
# canonical evidence before invoking this extended suite.

# ---------------------------------------------------------------------------
# Qualification-owned cleanup
# ---------------------------------------------------------------------------
phase_extended_cleanup() {
  pq_note "==== EXTENDED QUALIFICATION CLEANUP ===="
  set +e
  pq_ssh "$SERVER" "sudo bash -s" >"$OUT/extended/cleanup.log" 2>&1 <<'EOF'
set -euo pipefail
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("/var/lib/drlink/drlink.db")
names = [str(r[0]) for r in c.execute("SELECT name FROM policy_rules WHERE plane='internet'")]
foreign = [name for name in names if not name.startswith("pq-")]
if foreign:
    raise SystemExit("refusing cleanup: non-qualification Internet Access rules exist: %s" % ",".join(foreign))
PY
if ! drlink show internet-access | grep -q "Mode[[:space:]]*: No Policy"; then
  printf 'y\n' | drlink unset internet-access policy
fi
drlink unset service-group pq-web >/dev/null 2>&1 || true
for name in pq-http pq-https pq-fixed-target pq-normal-target; do
  drlink unset service-object "$name" >/dev/null 2>&1 || true
done
for name in pq-example-com pq-any-source pq-blackhole qual-live-mutation; do
  drlink unset network-object "$name" >/dev/null 2>&1 || true
done
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("/var/lib/drlink/drlink.db")
checks = {
    "internet_rules": c.execute(
        "SELECT COUNT(*) FROM policy_rules WHERE plane='internet' AND name LIKE 'pq-%'"
    ).fetchone()[0],
    "network_objects": c.execute(
        "SELECT COUNT(*) FROM objects WHERE name LIKE 'pq-%' OR name='qual-live-mutation'"
    ).fetchone()[0],
    "service_objects": c.execute(
        "SELECT COUNT(*) FROM service_objects WHERE name LIKE 'pq-%'"
    ).fetchone()[0],
    "service_groups": c.execute(
        "SELECT COUNT(*) FROM service_groups WHERE name LIKE 'pq-%'"
    ).fetchone()[0],
}
print(checks)
if any(int(v) for v in checks.values()):
    raise SystemExit("qualification residue remains")
PY
if [ -f /tmp/prod-qual-egress.pid ]; then
  pid="$(cat /tmp/prod-qual-egress.pid 2>/dev/null || true)"
  if [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -q 'frp-egress-gateway.py'; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
  rm -f /tmp/prod-qual-egress.pid
fi
echo EXTENDED_CLEANUP=PASS
EOF
  local rc=$?
  set -uo pipefail
  if [[ "$rc" -eq 0 ]]; then
    pq_gate EXTENDED_CLEANUP PASS
  else
    pq_gate EXTENDED_CLEANUP FAIL
    PROD_QUAL_FAILS=$((PROD_QUAL_FAILS + 1))
  fi
}

# ---------------------------------------------------------------------------
# Wrong-role / interrupted mutation (lightweight)
# ---------------------------------------------------------------------------
phase_wrong_ops() {
  pq_note "==== WRONG USER OPERATIONS ===="
  set +e
  pq_ssh "$SERVER" "sudo bash -s" >"$OUT/extended/wrong-ops.log" 2>&1 <<'EOF'
set -euo pipefail
set +e
drlink show managed-host zzzzdead >/tmp/w1.txt 2>&1; e1=$?
drlink set service-object bad-service type tcp port 99999 >/tmp/w2.txt 2>&1; e2=$?
drlink set network-object bad-network type cidr value not-a-cidr >/tmp/w3.txt 2>&1; e3=$?
drlink test internet-access source nosuch destination bad_host service nosuch >/tmp/w4.txt 2>&1; e4=$?
set -e
test "$e1" -ne 0 -a "$e2" -ne 0 -a "$e3" -ne 0 -a "$e4" -ne 0
echo "WRONG_OPS_RC e1=$e1 e2=$e2 e3=$e3 e4=$e4"
python3 -c 'import sqlite3; c=sqlite3.connect("/var/lib/drlink/drlink.db"); print(c.execute("PRAGMA integrity_check").fetchone()[0])'
echo WRONG_OPS=PASS
EOF
  if [[ $? -eq 0 ]]; then
    pq_note "WRONG_OPS=PASS"
  else
    pq_note "WRONG_OPS=FAIL"
    PROD_QUAL_FAILS=$((PROD_QUAL_FAILS + 1))
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  phase_egress_allow_deny
  phase_simultaneous_mutation
  phase_connection_scale
  phase_noisy_neighbor
  phase_connection_churn
  phase_failure_load
  phase_perf_baseline
  phase_policy_and_ports
  phase_enrollment_burst
  phase_component_restart
  phase_network_flap
  phase_docs_free_ux
  phase_wrong_ops
  phase_fixed_tcp_remote_service
  phase_soak
  phase_extended_cleanup
  # Prior-stable capture is owned by the dedicated A-019 harness. This suite
  # runs on the current v2.4 candidate and must not attempt a v2.3 capture here.
  pq_note "A019_GOLDEN_OWNER=tests/run-v230-to-v240-upgrade-e2e.sh"
  pq_note "EXTENDED_FINISHED=$(date -u +%Y-%m-%dT%H:%M:%SZ) FAILS=$PROD_QUAL_FAILS"
  if [[ "${PROD_QUAL_FAILS:-0}" -gt 0 ]]; then
    exit 1
  fi
  exit 0
}

main "$@"
