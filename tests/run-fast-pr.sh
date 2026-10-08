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
python3 tests/test-guided-configuration-input.py
python3 tests/test-repl-live-inventory.py
python3 tests/test-client-python-runtime.py
python3 tests/test-cli-reconciliation-role-parser-regression.py
python3 tests/test-permission-dependency-recovery.py
python3 tests/test-internet-access-recovery-guidance.py
python3 tests/test-enrollment-retention-recovery-guidance.py
python3 tests/test-public-help-required-operands.py
python3 tests/test-native-restore-confirmation.py
python3 tests/test-full-e2e-public-recovery-regressions.py
python3 tests/test-native-public-consent.py
bash tests/test-status-surface-parity.sh
python3 tests/test-enrollment-public-guidance.py
python3 tests/test-no-legacy-current-surface.py
python3 tests/test-canonical-runtime-policy.py
python3 tests/test-v24-upgrade-reconcile.py
python3 tests/test-doctor-proxy-identity.py
python3 tests/test-agent-catalog-progress.py
bash tests/test-fresh-client-source-provenance.sh
python3 tests/test-fresh-client-trust-bootstrap.py
python3 tests/test-zero-touch-windows-pin.py
python3 tests/test-v24-final-closure.py
python3 tests/test-v24-doc-consistency.py
python3 tests/test-v24-cli-ai-master-closure.py
python3 tests/test-v24-cli-workflow-semantic-parity.py

echo "=== derived artifact closure ==="
bash tests/test-change-closure-artifacts.sh

echo "=== repository safety ==="
./scripts/secret-scan.sh
./scripts/check-public-metadata.sh
git diff --check HEAD

echo "FAST_PR=PASS"
