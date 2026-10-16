#!/usr/bin/env bash
# Current v2.4 targeted Real E2E: canonical Server backup/restore plus corrupt-current contract.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${FRP_BACKUP_E2E_OUT:-$ROOT/e2e-reports/backup-integrity-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_DIR"

echo "=== Current v2.4 backup/restore Real E2E ==="
env \
  FRP_E2E_PROFILE="${FRP_E2E_PROFILE:-baseline-linux}" \
  FRP_E2E_SCENARIO=backup-repeat \
  FRP_E2E_BACKUP_REPEAT=1 \
  FRP_E2E_SKIP_SERVER_INSTALL=1 \
  FRP_E2E_SKIP_SERVER_PURGE=1 \
  FRP_E2E_CLIENT_ALIAS="${FRP_E2E_CLIENT_ALIAS:-frp-e2e-client}" \
  FRP_E2E_OUT_DIR="$OUT_DIR/real" \
  FRP_E2E_RUN_ID="backup-current-$(date -u +%Y%m%dT%H%M%SZ)" \
  bash "$ROOT/tests/run-real-e2e.sh"

echo "=== Corrupt-current restore deterministic contract ==="
python3 "$ROOT/tests/test-restore-corrupt-current.py"
python3 "$ROOT/tests/test-restore-preflight.py"

cat >"$OUT_DIR/result.env" <<'EOF'
TARGETED_REAL_E2E=PASS
BACKUP_RESTORE_REAL_FLEET=PASS
CORRUPT_CURRENT_RESTORE_CONTRACT=PASS
EOF
echo "TARGETED_REAL_E2E=PASS"
