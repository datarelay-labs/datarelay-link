#!/usr/bin/env bash
# Fast deterministic PR gate. Full run-all.sh remains stable-candidate/release qualification.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

echo "=== shell syntax ==="
git ls-files -z '*.sh' | xargs -0 -r -n 1 bash -n --
./tests/test-shell-syntax-enumeration.sh

echo "=== Python compile ==="
git ls-files '*.py' -z | xargs -0 -r python3 -m py_compile

echo "=== version and release governance ==="
./scripts/check-version-consistency.sh
./tests/test-version-governance.sh

echo "=== public CLI / contract regressions ==="
./tests/test-cli-catalog-parity.sh
python3 tests/test-public-cli-grammar-parity.py
python3 tests/test-cli-feature-scenario-remediation.py
python3 tests/test-cli-only-e2e-delta-triage.py
python3 tests/test-guided-configuration-input.py
python3 tests/test-repl-live-inventory.py
python3 tests/test-client-python-runtime.py
python3 tests/test-cli-reconciliation-role-parser-regression.py
python3 tests/test-permission-dependency-recovery.py
python3 tests/test-internet-access-recovery-guidance.py
python3 tests/test-doctor-egress-sqlite-authority.py
python3 tests/test-doctor-permission-guidance.py
python3 tests/test-agent-status-policy-generation.py
python3 tests/test-enrollment-retention-recovery-guidance.py
python3 tests/test-public-help-required-operands.py
python3 tests/test-native-restore-confirmation.py
python3 tests/test-audit-tail-validation.py
python3 tests/test-public-audit-control-history.py
python3 tests/test-full-e2e-public-recovery-regressions.py
python3 tests/test-cli-rule-selector-and-runtime-recovery.py
python3 tests/test-native-public-consent.py
python3 tests/test-client-uninstall-arguments.py
python3 tests/test-v24-agent-bundle-synchronization-lock.py
python3 tests/test-frpc-proxy-isolation.py
bash tests/test-agent-candidate-payload.sh
bash tests/test-status-surface-parity.sh
bash tests/test-proxy-readiness-session-causality.sh
bash tests/test-client-proxy-health-wait.sh
bash tests/test-macos-proxy-wait-cursor.sh
python3 tests/test-enrollment-public-guidance.py
python3 tests/test-no-legacy-current-surface.py
python3 tests/test-canonical-runtime-policy.py
python3 tests/test-runtime-generation-atomicity.py
python3 tests/test-server-fixed-pool-migration.py
python3 tests/test-v24-agent-bundle-absent-idempotency.py
python3 tests/test-v24-bundle-preview-writer-isolation.py
python3 tests/test-zero-touch-command-exit.py
python3 tests/test-egress-runtime-no-list-permission.py
python3 tests/test-v24-upgrade-reconcile.py
python3 tests/test-doctor-proxy-identity.py
python3 tests/test-doctor-agent-runtime-projection.py
python3 tests/test-agent-idle-runtime-health.py
python3 tests/test-agent-catalog-progress.py
bash tests/test-fresh-client-source-provenance.sh
python3 tests/test-fresh-client-trust-bootstrap.py
python3 tests/test-zero-touch-windows-pin.py
python3 tests/test-v24-final-closure.py
python3 tests/test-v24-bundle-duplicate-mapping-keys.py
python3 tests/test-v24-doc-consistency.py
python3 tests/test-v24-cli-ai-master-closure.py
python3 tests/test-v24-cli-workflow-semantic-parity.py
python3 tests/test-v24-readonly-selector-operands.py
python3 tests/test-v24-admin-concurrency-ux.py
python3 tests/test-v24-reference-delete-serialization.py
python3 tests/test-v24-reference-delete-upsert-race.py
python3 tests/test-v24-network-object-remote-reference.py
python3 tests/test-p013-policy-hotpath.py
python3 tests/test-v24-offline-tombstone-duplicate.py

echo "=== derived artifact closure ==="
bash tests/test-change-closure-artifacts.sh

echo "=== repository safety ==="
./scripts/secret-scan.sh
./scripts/check-public-metadata.sh
git diff --check HEAD

echo "FAST_PR=PASS"
